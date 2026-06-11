"""CLI tests for task-window scoping of `maid verify` plan-lock enforcement."""

from __future__ import annotations

import argparse
import json
import subprocess
from pathlib import Path

from maid_runner.cli.commands._main import main
from maid_runner.cli.commands.verify import cmd_verify
from maid_runner.core.plan_lock import default_plan_lock_path
from maid_runner.core.result import ErrorCode


def _write_module(tmp_path: Path, module: str, function: str) -> None:
    (tmp_path / "src" / f"{module}.py").write_text(
        f"def {function}() -> int:\n    value = 1\n    return value\n"
    )
    (tmp_path / "tests" / f"test_{module}.py").write_text(
        f"from src.{module} import {function}\n\n\n"
        f"def test_{function}_contract():\n    assert {function}() == 1\n"
    )


def _write_manifest(
    tmp_path: Path, slug: str, module: str, function: str, created: str
) -> Path:
    manifest_path = tmp_path / "manifests" / f"{slug}.manifest.yaml"
    manifest_path.write_text(
        f"""schema: "2"
goal: "Task for {module}"
type: feature
created: "{created}"
files:
  create:
    - path: src/{module}.py
      artifacts:
        - kind: function
          name: {function}
          returns: int
  read:
    - tests/test_{module}.py
validate:
  - python -m pytest -q tests/test_{module}.py
"""
    )
    return manifest_path


def _write_baseline_project(tmp_path: Path) -> Path:
    (tmp_path / "manifests").mkdir()
    (tmp_path / "src").mkdir()
    (tmp_path / "tests").mkdir()
    _write_module(tmp_path, "old", "old_demo")
    return _write_manifest(
        tmp_path, "old-task", "old", "old_demo", "2026-06-01T00:00:00Z"
    )


def _git(tmp_path: Path, *args: str) -> str:
    result = subprocess.run(
        ["git", "-c", "user.name=maid-test", "-c", "user.email=maid-test@example.com"]
        + list(args),
        cwd=tmp_path,
        capture_output=True,
        text=True,
        check=True,
    )
    return result.stdout.strip()


def _git_baseline_commit(tmp_path: Path) -> str:
    _git(tmp_path, "init", "-q")
    _git(tmp_path, "add", ".")
    _git(tmp_path, "commit", "-q", "-m", "baseline")
    return _git(tmp_path, "rev-parse", "HEAD")


def _add_new_task(tmp_path: Path) -> Path:
    _write_module(tmp_path, "new", "new_demo")
    return _write_manifest(
        tmp_path, "new-task", "new", "new_demo", "2026-06-11T00:00:00Z"
    )


def _verify_args(**overrides) -> argparse.Namespace:
    values = {
        "manifest_dir": "manifests/",
        "allow_empty": False,
        "fail_fast": True,
        "strict": False,
        "fail_on_warnings": False,
        "advisory": False,
        "worktree_scope": False,
        "changed_scope": False,
        "since": None,
        "base_ref": None,
        "include_tests": False,
        "test_jobs": 1,
        "require_plan_lock": False,
        "require_red_evidence": False,
        "json": False,
    }
    values.update(overrides)
    return argparse.Namespace(**values)


def _stage_errors(payload: dict, stage_name: str) -> list[dict]:
    stages = {stage["name"]: stage for stage in payload["stages"]}
    return stages[stage_name]["details"]["errors"]


def test_verify_since_baseline_scopes_e700_to_task_window_manifest(
    tmp_path: Path,
    monkeypatch,
    capsys,
) -> None:
    _write_baseline_project(tmp_path)
    baseline = _git_baseline_commit(tmp_path)
    _add_new_task(tmp_path)
    monkeypatch.chdir(tmp_path)

    exit_code = main(
        [
            "verify",
            "--require-plan-lock",
            "--since",
            baseline,
            "--no-changed-scope",
        ]
    )

    output = capsys.readouterr().out
    assert exit_code == 1
    assert "FAIL plan_lock" in output
    assert "new-task.manifest.yaml" in output
    assert "old-task.manifest.yaml" not in output


def test_verify_since_baseline_scopes_committed_task_window_manifest(
    tmp_path: Path,
    monkeypatch,
    capsys,
) -> None:
    _write_baseline_project(tmp_path)
    baseline = _git_baseline_commit(tmp_path)
    _add_new_task(tmp_path)
    _git(tmp_path, "add", ".")
    _git(tmp_path, "commit", "-q", "-m", "new task")
    monkeypatch.chdir(tmp_path)

    exit_code = main(
        [
            "verify",
            "--require-plan-lock",
            "--since",
            baseline,
            "--no-changed-scope",
        ]
    )

    output = capsys.readouterr().out
    assert exit_code == 1
    assert "FAIL plan_lock" in output
    assert "new-task.manifest.yaml" in output
    assert "old-task.manifest.yaml" not in output


def test_verify_without_baseline_scopes_to_worktree_changes(
    tmp_path: Path,
    monkeypatch,
    capsys,
) -> None:
    _write_baseline_project(tmp_path)
    _git_baseline_commit(tmp_path)
    _add_new_task(tmp_path)
    monkeypatch.chdir(tmp_path)

    exit_code = main(["verify", "--require-plan-lock", "--no-changed-scope"])

    output = capsys.readouterr().out
    assert exit_code == 1
    assert "FAIL plan_lock" in output
    assert "new-task.manifest.yaml" in output
    assert "old-task.manifest.yaml" not in output


def test_verify_clean_tree_passes_handoff_gate_despite_unlocked_history(
    tmp_path: Path,
    monkeypatch,
    capsys,
) -> None:
    _write_baseline_project(tmp_path)
    _git_baseline_commit(tmp_path)
    monkeypatch.chdir(tmp_path)

    exit_code = main(
        [
            "verify",
            "--require-plan-lock",
            "--require-red-evidence",
            "--since",
            "HEAD",
            "--no-changed-scope",
        ]
    )

    output = capsys.readouterr().out
    assert exit_code == 0
    assert "Verify: PASS" in output


def test_cmd_verify_scopes_requirement_errors_with_since_baseline(
    tmp_path: Path,
    monkeypatch,
    capsys,
) -> None:
    _write_baseline_project(tmp_path)
    baseline = _git_baseline_commit(tmp_path)
    _add_new_task(tmp_path)
    monkeypatch.chdir(tmp_path)

    exit_code = cmd_verify(
        _verify_args(
            require_plan_lock=True,
            require_red_evidence=True,
            since=baseline,
            json=True,
        )
    )

    payload = json.loads(capsys.readouterr().out)
    errors = _stage_errors(payload, "plan_lock")
    assert exit_code == 1
    codes = sorted(error["code"] for error in errors)
    assert codes == [
        ErrorCode.PLAN_LOCK_MISSING.value,
        ErrorCode.RED_PHASE_EVIDENCE_MISSING.value,
    ]
    assert all(
        "new-task.manifest.yaml" in error["location"]["file"] for error in errors
    )


def test_verify_without_git_metadata_falls_back_to_full_scope(
    tmp_path: Path,
    monkeypatch,
    capsys,
) -> None:
    _write_baseline_project(tmp_path)
    monkeypatch.chdir(tmp_path)

    exit_code = main(["verify", "--require-plan-lock", "--no-changed-scope"])

    output = capsys.readouterr().out
    assert exit_code == 1
    assert "FAIL plan_lock" in output
    assert "PLAN_LOCK_MISSING" in output
    assert "old-task.manifest.yaml" in output


def test_verify_json_reports_e706_for_corrupt_lock(
    tmp_path: Path,
    monkeypatch,
    capsys,
) -> None:
    _write_baseline_project(tmp_path)
    lock_path = default_plan_lock_path(tmp_path, "old-task")
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    lock_path.write_text("{not valid json")
    monkeypatch.chdir(tmp_path)

    exit_code = main(["verify", "--require-plan-lock", "--no-changed-scope", "--json"])

    payload = json.loads(capsys.readouterr().out)
    errors = _stage_errors(payload, "plan_lock")
    assert exit_code == 1
    assert [error["code"] for error in errors] == [ErrorCode.PLAN_LOCK_UNREADABLE.value]
