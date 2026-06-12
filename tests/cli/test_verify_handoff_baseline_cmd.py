"""CLI tests for bare handoff-gate baseline resolution in `maid verify`.

Reproduces the repository condition where committed historical manifests
declare conflicting metadata.maid_task_base values: the bare gate (no
--since/--base-ref) must resolve its task window from worktree-changed
manifests instead of storming E700/E704 across pre-existing history.
"""

from __future__ import annotations

import argparse
import json
import subprocess
from pathlib import Path

from maid_runner.cli.commands.verify import cmd_verify
from maid_runner.core.plan_lock import create_plan_lock, default_plan_lock_path
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
    tmp_path: Path,
    slug: str,
    module: str,
    function: str,
    created: str,
    task_base: str | None = None,
) -> Path:
    metadata = f"metadata:\n  maid_task_base: {task_base}\n" if task_base else ""
    manifest_path = tmp_path / "manifests" / f"{slug}.manifest.yaml"
    manifest_path.write_text(
        f"""schema: "2"
goal: "Task for {module}"
type: feature
created: "{created}"
{metadata}files:
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


def _write_history_with_stale_bases(tmp_path: Path) -> None:
    (tmp_path / "manifests").mkdir()
    (tmp_path / "src").mkdir()
    (tmp_path / "tests").mkdir()
    _write_module(tmp_path, "one", "one_demo")
    _write_manifest(
        tmp_path, "one-task", "one", "one_demo", "2026-06-01T00:00:00Z", "main"
    )
    _write_module(tmp_path, "two", "two_demo")
    _write_manifest(
        tmp_path, "two-task", "two", "two_demo", "2026-06-02T00:00:00Z", "c0ffee1"
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


def _commit_all(tmp_path: Path) -> None:
    _git(tmp_path, "init", "-q")
    _git(tmp_path, "add", ".")
    _git(tmp_path, "commit", "-q", "-m", "history")


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


def test_bare_handoff_gate_passes_on_clean_tree_with_stale_bases(
    tmp_path: Path,
    monkeypatch,
    capsys,
) -> None:
    _write_history_with_stale_bases(tmp_path)
    _commit_all(tmp_path)
    monkeypatch.chdir(tmp_path)

    exit_code = cmd_verify(
        _verify_args(require_plan_lock=True, require_red_evidence=True, json=True)
    )

    payload = json.loads(capsys.readouterr().out)
    stages = {stage["name"]: stage for stage in payload["stages"]}
    assert stages["plan_lock"]["success"] is True
    assert exit_code == 0


def test_bare_handoff_gate_scopes_to_worktree_during_task(
    tmp_path: Path,
    monkeypatch,
    capsys,
) -> None:
    _write_history_with_stale_bases(tmp_path)
    _commit_all(tmp_path)
    _write_module(tmp_path, "new", "new_demo")
    _write_manifest(tmp_path, "new-task", "new", "new_demo", "2026-06-11T00:00:00Z")
    monkeypatch.chdir(tmp_path)

    exit_code = cmd_verify(_verify_args(require_plan_lock=True, json=True))

    payload = json.loads(capsys.readouterr().out)
    errors = _stage_errors(payload, "plan_lock")
    assert exit_code == 1
    assert [error["code"] for error in errors] == [ErrorCode.PLAN_LOCK_MISSING.value]
    assert all(
        "new-task.manifest.yaml" in error["location"]["file"] for error in errors
    )


def test_integrity_errors_still_fire_on_clean_tree(
    tmp_path: Path,
    monkeypatch,
    capsys,
) -> None:
    _write_history_with_stale_bases(tmp_path)
    lock = create_plan_lock(tmp_path / "manifests" / "one-task.manifest.yaml", tmp_path)
    lock.save(default_plan_lock_path(tmp_path, "one-task"))
    _commit_all(tmp_path)
    (tmp_path / "tests" / "test_one.py").write_text(
        "from src.one import one_demo\n\n\n"
        "def test_one_demo_contract():\n    one_demo()\n    assert True\n"
    )
    monkeypatch.chdir(tmp_path)

    exit_code = cmd_verify(_verify_args(require_plan_lock=True, json=True))

    payload = json.loads(capsys.readouterr().out)
    errors = _stage_errors(payload, "plan_lock")
    assert exit_code == 1
    assert [error["code"] for error in errors] == [
        ErrorCode.BEHAVIORAL_TEST_MODIFIED_AFTER_LOCK.value
    ]
