"""Behavioral tests for the `maid task` CLI commands."""

from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from maid_runner.cli.commands._main import build_parser, main
from maid_runner.cli.commands.task import cmd_task


def _write_manifest(project_root: Path, relative_path: str) -> None:
    path = project_root / relative_path
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        """schema: "2"
goal: "Demo task"
type: feature
created: "2026-06-17T00:00:00Z"
files:
  read:
    - README.md
validate:
  - python -m pytest -q tests/test_demo.py
"""
    )


def test_build_parser_registers_task_subcommands() -> None:
    parser = build_parser()

    start_args = parser.parse_args(["task", "start", "manifests/demo.manifest.yaml"])
    stop_args = parser.parse_args(["task", "stop"])
    status_args = parser.parse_args(["task", "status", "--json"])

    assert start_args.command == "task"
    assert start_args.task_command == "start"
    assert start_args.manifest_path == "manifests/demo.manifest.yaml"
    assert stop_args.task_command == "stop"
    assert status_args.task_command == "status"
    assert status_args.json is True


def test_main_task_start_writes_active_manifest_file(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture
) -> None:
    monkeypatch.chdir(tmp_path)
    _write_manifest(tmp_path, "manifests/demo.manifest.yaml")

    exit_code = main(["task", "start", "manifests/demo.manifest.yaml"])

    assert exit_code == 0
    assert Path(".maid/active-manifest").read_text() == (
        "manifests/demo.manifest.yaml\n"
    )
    assert "manifests/demo.manifest.yaml" in capsys.readouterr().out


def test_main_task_start_rejects_invalid_manifest_path(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture
) -> None:
    monkeypatch.chdir(tmp_path)

    exit_code = main(["task", "start", "../outside.manifest.yaml"])

    assert exit_code == 2
    assert not Path(".maid/active-manifest").exists()
    assert "Error:" in capsys.readouterr().err


def test_main_task_stop_is_idempotent(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(tmp_path)

    assert main(["task", "stop"]) == 0
    assert main(["task", "stop"]) == 0


def test_cmd_task_status_json_shows_env_override_source(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture,
) -> None:
    _write_manifest(tmp_path, "manifests/file-task.manifest.yaml")
    (tmp_path / ".maid").mkdir()
    (tmp_path / ".maid" / "active-manifest").write_text(
        "manifests/file-task.manifest.yaml\n"
    )
    monkeypatch.setenv("MAID_ACTIVE_MANIFEST", "manifests/env-task.manifest.yaml")
    monkeypatch.chdir(tmp_path)
    args = SimpleNamespace(task_command="status", json=True)

    exit_code = cmd_task(args)

    assert exit_code == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload == {
        "active_manifest": "manifests/env-task.manifest.yaml",
        "source": "env",
    }


def test_main_task_status_reports_no_active_task(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture,
) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("MAID_ACTIVE_MANIFEST", raising=False)

    assert main(["task", "status"]) == 0

    assert "No active task" in capsys.readouterr().out
