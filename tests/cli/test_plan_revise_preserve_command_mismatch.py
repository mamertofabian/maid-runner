"""Regression contract for preserved evidence after validate-command changes."""

from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from maid_runner.cli.commands.plan import cmd_plan_lock, cmd_plan_revise
from maid_runner.core.plan_lock import default_plan_lock_path


def _write_project(tmp_path: Path) -> Path:
    (tmp_path / "manifests").mkdir()
    (tmp_path / "tests").mkdir()
    (tmp_path / "scripts").mkdir()
    (tmp_path / "tests" / "test_demo.py").write_text(
        "def test_demo_contract():\n    assert True\n"
    )
    (tmp_path / "scripts" / "old_validate.py").write_text("raise SystemExit(1)\n")
    (tmp_path / "scripts" / "new_validate.py").write_text("raise SystemExit(1)\n")
    manifest_path = tmp_path / "manifests" / "demo-task.manifest.yaml"
    manifest_path.write_text(
        """schema: "2"
goal: "Demo task"
type: fix
created: "2026-08-03T00:00:00Z"
files:
  create:
    - path: src/demo.py
      artifacts:
        - kind: function
          name: demo
          args: []
          returns: bool
  read:
    - tests/test_demo.py
validate:
  - python scripts/old_validate.py
"""
    )
    return manifest_path


def _lock_args(manifest_path: Path, project_root: Path) -> SimpleNamespace:
    return SimpleNamespace(
        plan_command="lock",
        manifest_path=str(manifest_path),
        project_root=str(project_root),
        no_run=False,
        legacy_baseline=False,
        reason=None,
        json=False,
    )


def _revise_args(manifest_path: Path, project_root: Path) -> SimpleNamespace:
    return SimpleNamespace(
        plan_command="revise",
        manifest_path=str(manifest_path),
        project_root=str(project_root),
        reason="replace the validate command",
        no_run=False,
        preserve_red_evidence=True,
        stash_implementation=False,
        allow_sibling_dirty=False,
        test_only_green=False,
        json=False,
    )


def test_preserve_red_evidence_rejects_changed_validate_commands_without_revising_lock(
    tmp_path: Path, capsys
) -> None:
    manifest_path = _write_project(tmp_path)
    assert cmd_plan_lock(_lock_args(manifest_path, tmp_path)) == 0
    lock_path = default_plan_lock_path(tmp_path, "demo-task")
    original_lock_bytes = lock_path.read_bytes()
    original_revision = json.loads(original_lock_bytes)["revision"]
    manifest_path.write_text(
        manifest_path.read_text().replace(
            "python scripts/old_validate.py", "python scripts/new_validate.py"
        )
    )

    exit_code = cmd_plan_revise(_revise_args(manifest_path, tmp_path))

    captured = capsys.readouterr()
    assert exit_code == 2
    assert lock_path.read_bytes() == original_lock_bytes
    assert json.loads(lock_path.read_text())["revision"] == original_revision
    assert "validate commands changed" in captured.err
    assert "--stash-implementation" in captured.err


def test_preserve_red_evidence_accepts_reordered_validate_command_multiset(
    tmp_path: Path,
) -> None:
    manifest_path = _write_project(tmp_path)
    manifest_path.write_text(
        manifest_path.read_text().replace(
            "  - python scripts/old_validate.py",
            "  - python scripts/old_validate.py\n  - python scripts/new_validate.py",
        )
    )
    assert cmd_plan_lock(_lock_args(manifest_path, tmp_path)) == 0
    lock_path = default_plan_lock_path(tmp_path, "demo-task")
    original_evidence = json.loads(lock_path.read_text())["red_evidence"]
    manifest_path.write_text(
        manifest_path.read_text().replace(
            "  - python scripts/old_validate.py\n  - python scripts/new_validate.py",
            "  - python scripts/new_validate.py\n  - python scripts/old_validate.py",
        )
    )

    exit_code = cmd_plan_revise(_revise_args(manifest_path, tmp_path))

    revised_lock = json.loads(lock_path.read_text())
    assert exit_code == 0
    assert revised_lock["revision"] == 2
    assert revised_lock["red_evidence"] == original_evidence


@pytest.mark.parametrize("evidence_mode", ["red", "test_only_green"])
def test_preserve_red_evidence_rejects_existing_e707_mismatch_without_revising_lock(
    tmp_path: Path, capsys, evidence_mode: str
) -> None:
    manifest_path = _write_project(tmp_path)
    assert cmd_plan_lock(_lock_args(manifest_path, tmp_path)) == 0
    lock_path = default_plan_lock_path(tmp_path, "demo-task")
    spliced_lock = json.loads(lock_path.read_text())
    spliced_command = spliced_lock["red_evidence"]["commands"][0]
    spliced_command["command"] = "python scripts/new_validate.py"
    if evidence_mode == "test_only_green":
        spliced_lock["red_evidence"]["red"] = False
        spliced_lock["red_evidence"]["mode"] = "test_only_green"
        spliced_command["exit_code"] = 0
        spliced_command["classification"] = "not_red"
    lock_path.write_text(json.dumps(spliced_lock, indent=2))
    spliced_lock_bytes = lock_path.read_bytes()
    spliced_revision = spliced_lock["revision"]
    manifest_path.write_text(
        manifest_path.read_text().replace(
            "python scripts/old_validate.py", "python scripts/new_validate.py"
        )
    )

    exit_code = cmd_plan_revise(_revise_args(manifest_path, tmp_path))

    captured = capsys.readouterr()
    assert exit_code == 2
    assert lock_path.read_bytes() == spliced_lock_bytes
    assert json.loads(lock_path.read_text())["revision"] == spliced_revision
    assert "existing plan lock" in captured.err


@pytest.mark.parametrize("malformed_target", ["locked_contract", "red_evidence"])
def test_preserve_red_evidence_rejects_malformed_command_entries_without_revising_lock(
    tmp_path: Path, capsys, malformed_target: str
) -> None:
    manifest_path = _write_project(tmp_path)
    assert cmd_plan_lock(_lock_args(manifest_path, tmp_path)) == 0
    lock_path = default_plan_lock_path(tmp_path, "demo-task")
    malformed_lock = json.loads(lock_path.read_text())
    if malformed_target == "locked_contract":
        malformed_lock["_manifest_contract"]["validate_commands"] = [
            {"not": "a command string"}
        ]
    else:
        malformed_lock["red_evidence"]["commands"][0]["command"] = {
            "not": "a command string"
        }
    lock_path.write_text(json.dumps(malformed_lock, indent=2))
    malformed_lock_bytes = lock_path.read_bytes()
    original_revision = malformed_lock["revision"]

    exit_code = cmd_plan_revise(_revise_args(manifest_path, tmp_path))

    captured = capsys.readouterr()
    assert exit_code == 2
    assert lock_path.read_bytes() == malformed_lock_bytes
    assert json.loads(lock_path.read_text())["revision"] == original_revision
    assert "existing plan lock" in captured.err
