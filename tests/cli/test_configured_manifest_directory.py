"""Behavioral coverage for configured manifest-directory CLI defaults."""

from __future__ import annotations

import json
from argparse import Namespace

import pytest
import yaml

from maid_runner.cli.commands import test as test_command
from maid_runner.cli.commands import validate as validate_command
from maid_runner.cli.commands import verify as verify_command
from maid_runner.cli.commands._main import main


CORE_COMMANDS = (
    ("validate", validate_command, "cmd_validate"),
    ("test", test_command, "cmd_test"),
    ("verify", verify_command, "cmd_verify"),
)


def _write_config(tmp_path, manifest_dir: str) -> None:
    (tmp_path / ".maidrc.yaml").write_text(
        yaml.safe_dump({"manifest_dir": manifest_dir})
    )


def test_validate_uses_configured_manifest_directory_end_to_end(
    tmp_path, monkeypatch, capsys
):
    configured_dir = tmp_path / "apps" / "example" / "manifests"
    configured_dir.mkdir(parents=True)
    _write_config(tmp_path, "apps/example/manifests/")
    (configured_dir / "configured.manifest.yaml").write_text(
        yaml.safe_dump(
            {
                "schema": "2",
                "goal": "Prove configured manifest discovery",
                "type": "feature",
                "created": "2026-08-05T04:27:59Z",
                "files": {
                    "scope": [
                        {
                            "path": "README.md",
                            "reason": "Schema-only fixture for directory discovery.",
                        }
                    ]
                },
                "validate": ["uv run python -m pytest --version"],
            }
        )
    )
    (tmp_path / "README.md").write_text("fixture\n")
    monkeypatch.chdir(tmp_path)

    exit_code = main(["validate", "--mode", "schema"])

    assert exit_code == 0
    assert "Validation Results: 1 manifests" in capsys.readouterr().out


@pytest.mark.parametrize(("command", "module", "handler_name"), CORE_COMMANDS)
def test_configured_manifest_directory_reaches_all_core_handlers(
    tmp_path, monkeypatch, command, module, handler_name
):
    _write_config(tmp_path, "apps/example/manifests/")
    monkeypatch.chdir(tmp_path)
    captured: dict[str, Namespace] = {}

    def capture(args: Namespace) -> int:
        captured["args"] = args
        return 0

    monkeypatch.setattr(module, handler_name, capture)

    assert main([command]) == 0
    assert captured["args"].manifest_dir == "apps/example/manifests/"


@pytest.mark.parametrize(("command", "module", "handler_name"), CORE_COMMANDS)
def test_explicit_manifest_directory_overrides_config_for_all_core_handlers(
    tmp_path, monkeypatch, command, module, handler_name
):
    _write_config(tmp_path, "apps/example/manifests/")
    monkeypatch.chdir(tmp_path)
    captured: dict[str, Namespace] = {}

    def capture(args: Namespace) -> int:
        captured["args"] = args
        return 0

    monkeypatch.setattr(module, handler_name, capture)

    assert main([command, "--manifest-dir", "explicit/contracts/"]) == 0
    assert captured["args"].manifest_dir == "explicit/contracts/"


@pytest.mark.parametrize("command", ("validate", "test", "verify"))
def test_invalid_config_returns_structured_error_for_directory_wide_commands(
    tmp_path, monkeypatch, capsys, command
):
    (tmp_path / ".maidrc.yaml").write_text("manifest_dir: [unterminated\n")
    monkeypatch.chdir(tmp_path)

    exit_code = main([command, "--json"])

    assert exit_code == 2
    payload = json.loads(capsys.readouterr().out)
    assert "Internal error" in payload["error"]


@pytest.mark.parametrize(
    ("argv", "module", "handler_name"),
    (
        (("validate", "manifests/one.manifest.yaml"), validate_command, "cmd_validate"),
        (
            ("test", "--manifest", "manifests/one.manifest.yaml"),
            test_command,
            "cmd_test",
        ),
    ),
)
def test_single_manifest_commands_do_not_load_irrelevant_config(
    tmp_path, monkeypatch, argv, module, handler_name
):
    (tmp_path / ".maidrc.yaml").write_text("manifest_dir: [unterminated\n")
    monkeypatch.chdir(tmp_path)
    captured: dict[str, Namespace] = {}

    def capture(args: Namespace) -> int:
        captured["args"] = args
        return 0

    monkeypatch.setattr(module, handler_name, capture)

    assert main(list(argv)) == 0
    assert captured["args"].manifest_dir == "manifests/"
