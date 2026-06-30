"""Regression tests for scope-only stash-backed plan-lock revision targets."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path
from types import SimpleNamespace

from maid_runner.cli.commands.plan import cmd_plan_lock, cmd_plan_revise
from maid_runner.core.plan_lock import default_plan_lock_path


def _git(project_root: Path, *args: str) -> str:
    result = subprocess.run(
        [
            "git",
            "-c",
            "user.name=maid-test",
            "-c",
            "user.email=maid-test@example.com",
            *args,
        ],
        cwd=project_root,
        check=True,
        text=True,
        capture_output=True,
    )
    return result.stdout


def _commit_all(project_root: Path, message: str) -> None:
    _git(project_root, "add", ".")
    _git(project_root, "commit", "-q", "-m", message)


def _lock_args(manifest_path: Path, project_root: Path) -> SimpleNamespace:
    return SimpleNamespace(
        plan_command="lock",
        manifest_path=str(manifest_path),
        project_root=str(project_root),
        no_run=False,
        json=False,
    )


def _revise_args(
    manifest_path: Path,
    project_root: Path,
    reason: str,
) -> SimpleNamespace:
    return SimpleNamespace(
        plan_command="revise",
        manifest_path=str(manifest_path),
        project_root=str(project_root),
        reason=reason,
        no_run=False,
        preserve_red_evidence=False,
        stash_implementation=True,
        json=False,
    )


def _lock_record(project_root: Path) -> dict:
    return json.loads(default_plan_lock_path(project_root, "scope-task").read_text())


def _write_scope_only_project(project_root: Path) -> Path:
    (project_root / "manifests").mkdir()
    (project_root / "scripts").mkdir()
    (project_root / "src").mkdir()
    (project_root / "src" / "route.py").write_text("wired = False\n")
    (project_root / "src" / "context.py").write_text("context = 'baseline'\n")
    (project_root / "scripts" / "validate_route.py").write_text(
        "from pathlib import Path\n"
        "text = Path('src/route.py').read_text()\n"
        "raise SystemExit(0 if 'wired = True' in text else 1)\n"
    )
    manifest_path = project_root / "manifests" / "scope-task.manifest.yaml"
    manifest_path.write_text(
        """schema: "2"
goal: "Scope-only task"
type: feature
created: "2026-06-29T00:00:00Z"
files:
  scope:
    - path: src/route.py
      reason: "Route wiring has no validator-visible public artifact."
  read:
    - src/context.py
    - scripts/validate_route.py
validate:
  - python scripts/validate_route.py
"""
    )
    _git(project_root, "init", "-q")
    _commit_all(project_root, "red scope contract")
    assert cmd_plan_lock(_lock_args(manifest_path, project_root)) == 0
    _commit_all(project_root, "plan lock")
    return manifest_path


def test_stash_implementation_recaptures_red_evidence_and_restores_scope_only_change(
    tmp_path: Path,
) -> None:
    manifest_path = _write_scope_only_project(tmp_path)
    route_path = tmp_path / "src" / "route.py"
    route_path.write_text("wired = True\n")

    exit_code = cmd_plan_revise(
        _revise_args(
            manifest_path,
            tmp_path,
            "review added route behavior while scope-only implementation existed",
        )
    )

    assert exit_code == 0
    assert route_path.read_text() == "wired = True\n"
    assert _git(tmp_path, "stash", "list") == ""
    record = _lock_record(tmp_path)
    assert record["revision"] == 2
    assert record["red_evidence"]["red"] is True
    assert record["red_evidence"]["commands"][0]["classification"] == "red"


def test_stash_implementation_rejects_dirty_read_only_path_with_scope_target(
    tmp_path: Path,
) -> None:
    manifest_path = _write_scope_only_project(tmp_path)
    route_path = tmp_path / "src" / "route.py"
    context_path = tmp_path / "src" / "context.py"
    route_path.write_text("wired = True\n")
    context_path.write_text("context = 'dirty'\n")
    lock_path = default_plan_lock_path(tmp_path, "scope-task")
    original_lock = lock_path.read_bytes()

    exit_code = cmd_plan_revise(
        _revise_args(
            manifest_path,
            tmp_path,
            "review added route behavior while read context was dirty",
        )
    )

    assert exit_code == 2
    assert lock_path.read_bytes() == original_lock
    assert route_path.read_text() == "wired = True\n"
    assert context_path.read_text() == "context = 'dirty'\n"
    assert _git(tmp_path, "stash", "list") == ""
