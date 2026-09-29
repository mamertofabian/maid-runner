"""Regression tests for declared epic inventory in scope-only plan revision."""

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
    (project_root / "scripts" / "test_route.py").write_text(
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
    - scripts/test_route.py
validate:
  - python scripts/test_route.py
"""
    )
    _git(project_root, "init", "-q")
    _commit_all(project_root, "red scope contract")
    assert cmd_plan_lock(_lock_args(manifest_path, project_root)) == 0
    _commit_all(project_root, "plan lock")
    return manifest_path


def _declare_epic(project_root: Path, manifest_path: Path) -> Path:
    epic = project_root / "manifests" / "drafts" / "scope-task.epic.yaml"
    epic.parent.mkdir()
    epic.write_text("# manifest-kind: epic\nschema: '2'\ngoal: Scope task planning\n")
    manifest_path.write_text(
        manifest_path.read_text().replace(
            "  read:\n", "  read:\n    - manifests/drafts/scope-task.epic.yaml\n"
        )
    )
    return epic


def test_scope_revision_stashes_and_restores_declared_untracked_epic(
    tmp_path: Path,
) -> None:
    manifest = _write_scope_only_project(tmp_path)
    epic = _declare_epic(tmp_path, manifest)
    original_epic = epic.read_bytes()
    route = tmp_path / "src" / "route.py"
    route.write_text("wired = True\n")
    (tmp_path / "scripts" / "test_route.py").write_text(
        "from pathlib import Path\n"
        "epic_visible = Path('manifests/drafts/scope-task.epic.yaml').exists()\n"
        "wired = 'wired = True' in Path('src/route.py').read_text()\n"
        "raise SystemExit(0 if epic_visible or wired else 1)\n"
    )
    args = _revise_args(manifest, tmp_path, "reviewed scope and epic")
    args.allow_sibling_dirty = True

    result = cmd_plan_revise(args)

    assert result == 0
    assert route.read_text() == "wired = True\n"
    assert epic.read_bytes() == original_epic
    assert _git(tmp_path, "stash", "list") == ""
    record = _lock_record(tmp_path)
    assert record["revision"] == 2
    assert record["red_evidence"]["red"] is True


def test_scope_revision_restores_tracked_epic_after_failed_red_capture(
    tmp_path: Path,
    capsys,
) -> None:
    manifest = _write_scope_only_project(tmp_path)
    epic = _declare_epic(tmp_path, manifest)
    _commit_all(tmp_path, "declare epic context")
    epic.write_text(epic.read_text() + "# reviewed planning update\n")
    original_epic = epic.read_bytes()
    route = tmp_path / "src" / "route.py"
    route.write_text("wired = True\n")
    (tmp_path / "scripts" / "test_route.py").write_text("raise SystemExit(0)\n")
    lock = default_plan_lock_path(tmp_path, "scope-task")
    original_lock = lock.read_bytes()

    result = cmd_plan_revise(_revise_args(manifest, tmp_path, "green must fail"))

    assert result == 1
    error = capsys.readouterr().err
    assert "did not capture valid red evidence" in error
    assert "classification not_red" in error
    assert lock.read_bytes() == original_lock
    assert route.read_text() == "wired = True\n"
    assert epic.read_bytes() == original_epic
    assert _git(tmp_path, "stash", "list") == ""


def test_scope_revision_still_rejects_dirty_read_source_with_declared_epic(
    tmp_path: Path,
    capsys,
) -> None:
    manifest = _write_scope_only_project(tmp_path)
    epic = _declare_epic(tmp_path, manifest)
    original_epic = epic.read_bytes()
    route = tmp_path / "src" / "route.py"
    route.write_text("wired = True\n")
    context = tmp_path / "src" / "context.py"
    context.write_text("context = 'dirty'\n")
    original_lock = default_plan_lock_path(tmp_path, "scope-task").read_bytes()

    args = _revise_args(manifest, tmp_path, "context stays protected")
    args.allow_sibling_dirty = True
    result = cmd_plan_revise(args)

    assert result == 2
    assert default_plan_lock_path(tmp_path, "scope-task").read_bytes() == original_lock
    assert route.read_text() == "wired = True\n"
    assert "files.scope" in capsys.readouterr().err
    assert context.read_text() == "context = 'dirty'\n"
    assert epic.read_bytes() == original_epic
    assert _git(tmp_path, "stash", "list") == ""
