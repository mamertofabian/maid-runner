"""Behavioral tests for the `maid validators` command."""

from __future__ import annotations

import argparse
from dataclasses import dataclass
import importlib.metadata
import json
import re

from maid_runner.validators.base import BaseValidator, CollectionResult

ENTRY_POINT_GROUP = "maid_runner.validators"


class _GoValidator(BaseValidator):
    @classmethod
    def supported_extensions(cls) -> tuple[str, ...]:
        return (".go",)

    def collect_implementation_artifacts(self, source, file_path):
        return CollectionResult(artifacts=[], language="go", file_path=str(file_path))

    def collect_behavioral_artifacts(self, source, file_path):
        return CollectionResult(artifacts=[], language="go", file_path=str(file_path))


class _PythonPluginValidator(BaseValidator):
    @classmethod
    def supported_extensions(cls) -> tuple[str, ...]:
        return (".py",)

    def collect_implementation_artifacts(self, source, file_path):
        return CollectionResult(
            artifacts=[], language="python-plugin", file_path=str(file_path)
        )

    def collect_behavioral_artifacts(self, source, file_path):
        return CollectionResult(
            artifacts=[], language="python-plugin", file_path=str(file_path)
        )


@dataclass(frozen=True)
class _FakeDistribution:
    name: str
    version: str = "1.0.0"

    @property
    def metadata(self) -> dict[str, str]:
        return {"Name": self.name}


class _FakeEntryPoint:
    def __init__(
        self,
        *,
        name: str,
        distribution: str,
        validator_class: type[BaseValidator] | None = None,
        version: str = "1.0.0",
        load_error: Exception | None = None,
    ) -> None:
        self.name = name
        self.group = ENTRY_POINT_GROUP
        self.value = f"{distribution}:{name}"
        self.dist = _FakeDistribution(distribution, version)
        self._validator_class = validator_class
        self._load_error = load_error
        self.load_count = 0

    def load(self):
        self.load_count += 1
        if self._load_error is not None:
            raise self._load_error
        return self._validator_class


class _FakeEntryPoints(tuple):
    def select(self, *, group: str | None = None):
        if group is None:
            return self
        return type(self)(ep for ep in self if ep.group == group)


def _patch_entry_points(monkeypatch, entry_points: list[_FakeEntryPoint]) -> None:
    fake_entry_points = _FakeEntryPoints(entry_points)

    def entry_points_lookup(*, group: str | None = None):
        if group is None:
            return fake_entry_points
        return fake_entry_points.select(group=group)

    monkeypatch.setattr(importlib.metadata, "entry_points", entry_points_lookup)


def _parse_text_rows(output: str) -> list[dict[str, str]]:
    lines = [line.rstrip() for line in output.splitlines() if line.strip()]
    assert lines[0].split() == ["name", "extensions", "source", "status", "detail"]
    rows = []
    for line in lines[2:]:
        name, extensions, source, status, detail = re.split(r"\s{2,}", line, maxsplit=4)
        rows.append(
            {
                "name": name,
                "extensions": [] if extensions == "-" else extensions.split(", "),
                "source": source,
                "status": status,
                "detail": None if detail == "-" else detail,
            }
        )
    return rows


def _plugin_rows(rows: list[dict[str, object]]) -> list[dict[str, object]]:
    return [row for row in rows if row["source"] != "builtin"]


def test_validators_parser_accepts_text_and_json_and_main_dispatches(
    monkeypatch, capsys
):
    from maid_runner.cli.commands._main import build_parser, main

    _patch_entry_points(monkeypatch, [])
    parser = build_parser()

    text_args = parser.parse_args(["validators"])
    json_args = parser.parse_args(["validators", "--json"])
    text_exit_code = main(["validators"])
    text_output = capsys.readouterr().out
    json_exit_code = main(["validators", "--json"])
    json_output = capsys.readouterr().out

    assert text_args.command == "validators"
    assert json_args.command == "validators"
    assert json_args.json is True
    assert text_exit_code == 0
    assert json_exit_code == 0
    assert "PythonValidator" in text_output
    assert json.loads(json_output)["validators"][0]["name"] == "PythonValidator"


def test_cmd_validators_lists_builtin_records_first(monkeypatch, capsys):
    from maid_runner.cli.commands.validators import cmd_validators

    _patch_entry_points(monkeypatch, [])

    exit_code = cmd_validators(argparse.Namespace(json=False))
    rows = _parse_text_rows(capsys.readouterr().out)

    assert exit_code == 0
    assert rows
    assert rows[0]["name"] == "PythonValidator"
    assert rows[0]["source"] == "builtin"
    assert rows[0]["status"] == "active"
    assert ".py" in rows[0]["extensions"]
    assert rows[0]["detail"] is None
    assert all(row["source"] == "builtin" for row in rows)
    assert all(row["status"] == "active" for row in rows)
    for row in rows:
        assert row["extensions"] == sorted(row["extensions"])


def test_validators_json_matches_text_rows_for_plugin_statuses(monkeypatch, capsys):
    from maid_runner.cli.commands._main import main

    entry_points = [
        _FakeEntryPoint(
            name="python",
            distribution="maid-validator-python",
            validator_class=_PythonPluginValidator,
        ),
        _FakeEntryPoint(
            name="broken",
            distribution="maid-validator-broken",
            load_error=RuntimeError("broken import"),
        ),
        _FakeEntryPoint(
            name="go",
            distribution="maid-validator-go",
            version="2.3.4",
            validator_class=_GoValidator,
        ),
    ]
    _patch_entry_points(monkeypatch, entry_points)

    text_exit_code = main(["validators"])
    text_rows = _parse_text_rows(capsys.readouterr().out)
    json_exit_code = main(["validators", "--json"])
    json_rows = json.loads(capsys.readouterr().out)["validators"]

    assert text_exit_code == 0
    assert json_exit_code == 0
    assert json_rows == text_rows
    assert [row["source"] for row in text_rows if row["source"] == "builtin"]
    assert [row["source"] for row in text_rows].index("builtin") == 0
    plugin_rows = _plugin_rows(text_rows)
    assert [(row["name"], row["status"]) for row in plugin_rows] == [
        ("broken", "error"),
        ("go", "active"),
        ("python", "conflict"),
    ]
    assert plugin_rows[0]["source"] == "maid-validator-broken 1.0.0"
    assert plugin_rows[0]["detail"] == "broken import"
    assert plugin_rows[1]["extensions"] == [".go"]
    assert plugin_rows[2]["detail"] == "conflicting extensions: .py"


def test_validators_lists_disabled_plugins_without_loading_them(monkeypatch, capsys):
    from maid_runner.cli.commands._main import main

    go_entry = _FakeEntryPoint(
        name="go",
        distribution="maid-validator-go",
        validator_class=_GoValidator,
    )
    _patch_entry_points(monkeypatch, [go_entry])
    monkeypatch.setenv("MAID_DISABLE_VALIDATOR_PLUGINS", "1")

    exit_code = main(["validators", "--json"])
    rows = json.loads(capsys.readouterr().out)["validators"]

    assert exit_code == 0
    assert go_entry.load_count == 0
    assert _plugin_rows(rows) == [
        {
            "name": "go",
            "extensions": [],
            "source": "maid-validator-go 1.0.0",
            "status": "disabled",
            "detail": "disabled by MAID_DISABLE_VALIDATOR_PLUGINS=1",
        }
    ]
