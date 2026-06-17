"""Behavioral tests for the `maid hook scope-check` CLI command."""

from __future__ import annotations

import io
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from maid_runner.cli.commands._main import build_parser, main
from maid_runner.cli.commands.hook import cmd_hook
from maid_runner.core.manifest import load_manifest
from maid_runner.core.scope_check import (
    ScopeCheckDecision,
    declared_scope_paths,
    scope_check_path,
)


def _write_active_manifest(project_root: Path, relative_path: str) -> None:
    path = project_root / relative_path
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        """schema: "2"
goal: "Demo hook task"
type: feature
created: "2026-06-17T00:00:00Z"
files:
  create:
    - path: src/new_module.py
      artifacts:
        - kind: function
          name: new_module
  edit:
    - path: src/existing.py
      artifacts:
        - kind: function
          name: existing
  delete:
    - path: src/obsolete.py
      reason: "Removed by demo task"
  read:
    - tests/cli/test_hook_cmd.py
    - src/read_only.py
validate:
  - uv run python -m pytest -q tests/cli/test_hook_cmd.py
  - cd frontend && uv run python -m pytest -q tests/test_ui.py
"""
    )


def _payload(output: str) -> dict:
    lines = [line for line in output.splitlines() if line.strip()]
    assert len(lines) == 1
    payload = json.loads(lines[0])
    assert set(payload) == {"decision", "reason", "active_manifest"}
    return payload


def test_build_parser_registers_hook_scope_check_subcommand() -> None:
    parser = build_parser()

    args = parser.parse_args(["hook", "scope-check", "--path", "src/new_module.py"])
    stdin_args = parser.parse_args(["hook", "scope-check", "--stdin", "--strict"])

    assert args.command == "hook"
    assert args.hook_command == "scope-check"
    assert args.path == "src/new_module.py"
    assert stdin_args.stdin is True
    assert stdin_args.strict is True


def test_scope_check_allows_manifest_write_scope_manifest_and_drafts(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("MAID_ACTIVE_MANIFEST", "manifests/demo.manifest.yaml")
    _write_active_manifest(tmp_path, "manifests/demo.manifest.yaml")
    manifest = load_manifest("manifests/demo.manifest.yaml")
    declared = declared_scope_paths(manifest, tmp_path)

    assert "src/new_module.py" in declared
    assert "tests/cli/test_hook_cmd.py" in declared
    direct_decision = scope_check_path(
        "src/new_module.py",
        "manifests/demo.manifest.yaml",
        tmp_path,
    )
    assert isinstance(direct_decision, ScopeCheckDecision)
    assert direct_decision.decision == "allow"
    assert direct_decision.reason == "in-scope"
    assert direct_decision.active_manifest == "manifests/demo.manifest.yaml"

    for candidate in (
        "src/new_module.py",
        "src/existing.py",
        "src/obsolete.py",
        "manifests/demo.manifest.yaml",
        "manifests/drafts/future.manifest.yaml",
        "frontend/tests/test_ui.py",
    ):
        exit_code = main(["hook", "scope-check", "--path", candidate])
        payload = _payload(capsys.readouterr().out)

        assert exit_code == 0
        assert payload == {
            "decision": "allow",
            "reason": "in-scope",
            "active_manifest": "manifests/demo.manifest.yaml",
        }


def test_scope_check_allows_declared_test_files_but_denies_plain_read_files(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("MAID_ACTIVE_MANIFEST", "manifests/demo.manifest.yaml")
    _write_active_manifest(tmp_path, "manifests/demo.manifest.yaml")

    assert main(["hook", "scope-check", "--path", "tests/cli/test_hook_cmd.py"]) == 0
    assert _payload(capsys.readouterr().out)["decision"] == "allow"

    assert main(["hook", "scope-check", "--path", "src/read_only.py"]) == 2
    denied = _payload(capsys.readouterr().out)
    assert denied["decision"] == "deny"
    assert denied["active_manifest"] == "manifests/demo.manifest.yaml"
    assert "manifests/demo.manifest.yaml" in denied["reason"]
    assert "src/existing.py" in denied["reason"]
    assert "src/new_module.py" in denied["reason"]

    assert (
        main(
            [
                "hook",
                "scope-check",
                "--path",
                "manifests/drafts/../../src/read_only.py",
            ]
        )
        == 2
    )
    escaped = _payload(capsys.readouterr().out)
    assert escaped["decision"] == "deny"


def test_scope_check_accepts_stdin_json_path(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("MAID_ACTIVE_MANIFEST", "manifests/demo.manifest.yaml")
    monkeypatch.setattr("sys.stdin", io.StringIO('{"path": "src/existing.py"}'))
    _write_active_manifest(tmp_path, "manifests/demo.manifest.yaml")
    args = SimpleNamespace(
        hook_command="scope-check",
        stdin=True,
        path=None,
        strict=False,
    )

    exit_code = cmd_hook(args)
    payload = _payload(capsys.readouterr().out)

    assert exit_code == 0
    assert payload["decision"] == "allow"


def test_scope_check_no_active_task_defaults_to_allow_and_strict_denies(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("MAID_ACTIVE_MANIFEST", raising=False)

    assert main(["hook", "scope-check", "--path", "src/anything.py"]) == 0
    default_payload = _payload(capsys.readouterr().out)
    assert default_payload == {
        "decision": "allow",
        "reason": "no-active-task",
        "active_manifest": None,
    }

    assert main(["hook", "scope-check", "--path", "src/anything.py", "--strict"]) == 2
    strict_payload = _payload(capsys.readouterr().out)
    assert strict_payload == {
        "decision": "deny",
        "reason": "no-active-task",
        "active_manifest": None,
    }


def test_scope_check_internal_errors_fail_open_by_default_and_fail_closed_strict(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("MAID_ACTIVE_MANIFEST", "manifests/missing.manifest.yaml")

    assert main(["hook", "scope-check", "--path", "src/anything.py"]) == 1
    default_payload = _payload(capsys.readouterr().out)
    assert default_payload["decision"] == "allow"
    assert default_payload["active_manifest"] == "manifests/missing.manifest.yaml"
    assert "internal-error" in default_payload["reason"]

    assert main(["hook", "scope-check", "--path", "src/anything.py", "--strict"]) == 1
    strict_payload = _payload(capsys.readouterr().out)
    assert strict_payload["decision"] == "deny"
    assert strict_payload["active_manifest"] == "manifests/missing.manifest.yaml"
    assert "internal-error" in strict_payload["reason"]

    monkeypatch.delenv("MAID_ACTIVE_MANIFEST", raising=False)
    (tmp_path / ".maid").mkdir(exist_ok=True)
    (tmp_path / ".maid" / "active-manifest").mkdir()

    assert main(["hook", "scope-check", "--path", "src/anything.py"]) == 1
    corrupt_default = _payload(capsys.readouterr().out)
    assert corrupt_default["decision"] == "allow"
    assert corrupt_default["active_manifest"] is None
    assert "internal-error" in corrupt_default["reason"]

    assert main(["hook", "scope-check", "--path", "src/anything.py", "--strict"]) == 1
    corrupt_strict = _payload(capsys.readouterr().out)
    assert corrupt_strict["decision"] == "deny"
    assert corrupt_strict["active_manifest"] is None
    assert "internal-error" in corrupt_strict["reason"]
