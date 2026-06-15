import json
from pathlib import Path

import pytest
import yaml

from maid_runner.cli.commands._main import build_parser, main
from maid_runner.cli.commands.incident import cmd_incident


def _record(
    *,
    created: str,
    diagnostics: list[dict],
    pattern_tags: list[str],
) -> dict:
    return {
        "incident_version": 1,
        "created": created,
        "manifest": "manifests/example.manifest.yaml",
        "gates": ["E701"],
        "packet": {"diagnostics": diagnostics},
        "rejected_diff": "rejected",
        "chosen_diff": None,
        "pattern_tags": pattern_tags,
        "notes": None,
    }


def _write_record(path: Path, record: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(yaml.safe_dump(record, sort_keys=False), encoding="utf-8")


def test_build_parser_registers_incident_suggest_temptations_options(capsys):
    parser = build_parser()

    args = parser.parse_args(
        [
            "incident",
            "suggest-temptations",
            "--paths",
            "maid_runner/core/validate.py,tests/test_validate.py",
            "--json",
        ]
    )

    assert callable(cmd_incident)
    assert args.command == "incident"
    assert args.incident_command == "suggest-temptations"
    assert args.paths == "maid_runner/core/validate.py,tests/test_validate.py"
    assert args.json is True

    with pytest.raises(SystemExit):
        parser.parse_args(["incident", "suggest-temptations"])
    assert "--paths" in capsys.readouterr().err


def test_incident_suggest_temptations_outputs_yaml_and_json(
    tmp_path, monkeypatch, capsys
):
    monkeypatch.chdir(tmp_path)
    incidents_dir = tmp_path / ".maid" / "incidents"
    _write_record(
        incidents_dir / "20260615-010203-first.incident.yaml",
        _record(
            created="2026-06-15T01:02:03Z",
            diagnostics=[{"file": "maid_runner/core/validate.py", "code": "E701"}],
            pattern_tags=["false-done", "test-weakening"],
        ),
    )
    _write_record(
        incidents_dir / "20260615-010204-second.incident.yaml",
        _record(
            created="2026-06-15T01:02:04Z",
            diagnostics=[{"file": "maid_runner/core/validate.py", "code": "E711"}],
            pattern_tags=["false-done", "runner-gaming"],
        ),
    )

    assert (
        main(
            [
                "incident",
                "suggest-temptations",
                "--paths",
                "maid_runner/core/validate.py",
            ]
        )
        == 0
    )
    yaml_entries = yaml.safe_load(capsys.readouterr().out)
    assert [set(entry) for entry in yaml_entries] == [
        {"risk", "instead"},
        {"risk", "instead"},
        {"risk", "instead"},
    ]

    assert (
        main(
            [
                "incident",
                "suggest-temptations",
                "--paths",
                "maid_runner/core/validate.py",
                "--json",
            ]
        )
        == 0
    )
    payload = json.loads(capsys.readouterr().out)
    assert [(item["tag"], item["incident_count"]) for item in payload] == [
        ("false-done", 2),
        ("runner-gaming", 1),
        ("test-weakening", 1),
    ]
    assert all(
        set(item) == {"tag", "incident_count", "risk", "instead"} for item in payload
    )


def test_incident_suggest_temptations_empty_store_reports_explicit_empty_result(
    tmp_path, monkeypatch, capsys
):
    monkeypatch.chdir(tmp_path)

    assert (
        main(
            [
                "incident",
                "suggest-temptations",
                "--paths",
                "maid_runner/core/validate.py",
            ]
        )
        == 0
    )
    assert capsys.readouterr().out == "[]\n"

    assert (
        main(
            [
                "incident",
                "suggest-temptations",
                "--paths",
                "maid_runner/core/validate.py",
                "--json",
            ]
        )
        == 0
    )
    assert json.loads(capsys.readouterr().out) == []
