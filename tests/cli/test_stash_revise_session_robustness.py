"""Behavioral coverage for stash-backed revise in busy worktree sessions."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path
from types import SimpleNamespace

from maid_runner.cli.commands._main import build_parser
from maid_runner.cli.commands.plan import cmd_plan_lock, cmd_plan_revise
from maid_runner.core.plan_lock import default_plan_lock_path


def _git(
    project_root: Path, *args: str, check: bool = True
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [
            "git",
            "-c",
            "user.name=maid-test",
            "-c",
            "user.email=maid-test@example.com",
            *args,
        ],
        cwd=project_root,
        check=check,
        text=True,
        capture_output=True,
    )


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
        legacy_baseline=False,
        reason=None,
    )


def _revise_args(
    manifest_path: Path,
    project_root: Path,
    *,
    allow_sibling_dirty: bool = False,
) -> SimpleNamespace:
    return SimpleNamespace(
        plan_command="revise",
        manifest_path=str(manifest_path),
        project_root=str(project_root),
        reason="review tightened the behavioral contract",
        no_run=False,
        preserve_red_evidence=False,
        stash_implementation=True,
        test_only_green=False,
        allow_sibling_dirty=allow_sibling_dirty,
        json=False,
    )


def _lock_record(project_root: Path) -> dict:
    return json.loads(default_plan_lock_path(project_root, "demo-task").read_text())


def _write_tracked_project(project_root: Path) -> Path:
    (project_root / "manifests").mkdir()
    (project_root / "scripts").mkdir()
    (project_root / "src").mkdir()
    (project_root / "tests").mkdir()
    (project_root / "src" / "__init__.py").write_text("")
    (project_root / "src" / "demo.py").write_text("def demo() -> int:\n    return 0\n")
    (project_root / "tests" / "test_demo.py").write_text(
        "from src.demo import demo\n\n\n"
        "def test_demo_contract():\n"
        "    assert demo() == 1\n"
    )
    (project_root / "scripts" / "validate.py").write_text(
        "from pathlib import Path\n"
        "import sys\n"
        "source = Path('src/demo.py').read_text()\n"
        "if Path('README.md').exists():\n"
        "    Path('sibling-visibility.txt').write_text('present')\n"
        "sys.exit(0 if 'return 1' in source else 1)\n"
    )
    manifest_path = project_root / "manifests" / "demo-task.manifest.yaml"
    manifest_path.write_text(
        """schema: "2"
goal: "Demo task"
type: feature
created: "2026-07-18T00:00:00Z"
files:
  edit:
    - path: src/demo.py
      artifacts:
        - kind: function
          name: demo
          args: []
          returns: int
  read:
    - tests/test_demo.py
validate:
  - python scripts/validate.py
"""
    )
    _git(project_root, "init", "-q")
    _commit_all(project_root, "red contract")
    assert cmd_plan_lock(_lock_args(manifest_path, project_root)) == 0
    _commit_all(project_root, "plan lock")
    (project_root / "src" / "demo.py").write_text("def demo() -> int:\n    return 1\n")
    return manifest_path


def _write_untracked_create_project(project_root: Path) -> Path:
    (project_root / "manifests").mkdir()
    (project_root / "scripts").mkdir()
    (project_root / "tests").mkdir()
    (project_root / "scripts" / "validate_generated.py").write_text(
        "from pathlib import Path\n"
        "import sys\n"
        "present = Path('src/generated.py').exists()\n"
        "Path('capture-state.txt').write_text('present' if present else 'absent')\n"
        "sys.exit(0 if present else 1)\n"
    )
    (project_root / "tests" / "test_generated.py").write_text(
        "def test_generated_contract():\n    assert True\n"
    )
    manifest_path = project_root / "manifests" / "demo-task.manifest.yaml"
    manifest_path.write_text(
        """schema: "2"
goal: "Generated implementation"
type: feature
created: "2026-07-18T00:00:00Z"
files:
  create:
    - path: src/generated.py
      artifacts:
        - kind: attribute
          name: VALUE
          of: module
          type: int
  read:
    - tests/test_generated.py
validate:
  - python scripts/validate_generated.py
"""
    )
    _git(project_root, "init", "-q")
    _commit_all(project_root, "red generated contract")
    assert cmd_plan_lock(_lock_args(manifest_path, project_root)) == 0
    (project_root / "capture-state.txt").unlink()
    _commit_all(project_root, "plan lock")
    return manifest_path


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
created: "2026-07-18T00:00:00Z"
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
    _commit_all(project_root, "red scope-only contract")
    assert cmd_plan_lock(_lock_args(manifest_path, project_root)) == 0
    _commit_all(project_root, "scope-only plan lock")
    return manifest_path


def test_allow_sibling_dirty_tolerates_and_records_unrelated_paths(
    tmp_path: Path, capsys
) -> None:
    manifest_path = _write_tracked_project(tmp_path)
    (tmp_path / "README.md").write_text("sibling documentation work\n")
    (tmp_path / "sibling.py").write_text("VALUE = 2\n")

    exit_code = cmd_plan_revise(
        _revise_args(manifest_path, tmp_path, allow_sibling_dirty=True)
    )

    assert exit_code == 0
    evidence = _lock_record(tmp_path)["red_evidence"]
    assert evidence["sibling_dirty_paths"] == ["README.md", "sibling.py"]
    assert (tmp_path / "README.md").read_text() == "sibling documentation work\n"
    assert (tmp_path / "sibling.py").read_text() == "VALUE = 2\n"
    assert (tmp_path / "sibling-visibility.txt").read_text() == "present"
    assert (tmp_path / "src" / "demo.py").read_text().endswith("return 1\n")
    assert "README.md, sibling.py" in capsys.readouterr().out
    assert _git(tmp_path, "stash", "list").stdout == ""


def test_default_refusal_unchanged_and_names_flag(tmp_path: Path, capsys) -> None:
    parsed = build_parser().parse_args(
        [
            "plan",
            "revise",
            "manifests/demo-task.manifest.yaml",
            "--reason",
            "busy session",
            "--stash-implementation",
            "--allow-sibling-dirty",
        ]
    )
    assert parsed.allow_sibling_dirty is True

    manifest_path = _write_tracked_project(tmp_path)
    (tmp_path / "README.md").write_text("sibling work\n")

    exit_code = cmd_plan_revise(_revise_args(manifest_path, tmp_path))

    assert exit_code == 2
    error = capsys.readouterr().err
    assert "README.md" in error
    assert "--allow-sibling-dirty" in error
    assert "files.read" in error
    assert _git(tmp_path, "stash", "list").stdout == ""


def test_allow_sibling_dirty_still_refuses_own_surface_conflicts(
    tmp_path: Path, capsys
) -> None:
    staged_root = tmp_path / "staged"
    staged_root.mkdir()
    manifest_path = _write_tracked_project(staged_root)
    _git(staged_root, "add", "src/demo.py")
    original_lock = default_plan_lock_path(staged_root, "demo-task").read_bytes()

    exit_code = cmd_plan_revise(
        _revise_args(manifest_path, staged_root, allow_sibling_dirty=True)
    )

    assert exit_code == 2
    assert (
        default_plan_lock_path(staged_root, "demo-task").read_bytes() == original_lock
    )
    assert "staged implementation path" in capsys.readouterr().err
    assert _git(staged_root, "stash", "list").stdout == ""

    scope_root = tmp_path / "scope-only"
    scope_root.mkdir()
    scope_manifest = _write_scope_only_project(scope_root)
    (scope_root / "src" / "route.py").write_text("wired = True\n")
    (scope_root / "src" / "context.py").write_text("context = 'dirty'\n")
    scope_lock = default_plan_lock_path(scope_root, "scope-task")
    original_scope_lock = scope_lock.read_bytes()

    scope_exit = cmd_plan_revise(
        _revise_args(scope_manifest, scope_root, allow_sibling_dirty=True)
    )

    assert scope_exit == 2
    assert scope_lock.read_bytes() == original_scope_lock
    assert (scope_root / "src" / "context.py").read_text() == "context = 'dirty'\n"
    scope_error = capsys.readouterr().err
    assert "src/context.py" in scope_error
    assert "own declared surface" in scope_error
    assert _git(scope_root, "stash", "list").stdout == ""


def test_untracked_files_create_is_stashed_and_restored(tmp_path: Path) -> None:
    manifest_path = _write_untracked_create_project(tmp_path)
    generated_path = tmp_path / "src" / "generated.py"
    generated_path.parent.mkdir()
    original_bytes = b"VALUE = 42\n"
    generated_path.write_bytes(original_bytes)

    exit_code = cmd_plan_revise(_revise_args(manifest_path, tmp_path))

    assert exit_code == 0
    assert (tmp_path / "capture-state.txt").read_text() == "absent"
    assert generated_path.read_bytes() == original_bytes
    assert _lock_record(tmp_path)["red_evidence"]["red"] is True
    assert _git(tmp_path, "stash", "list").stdout == ""


def test_intent_to_add_state_is_handled_or_cleanly_refused(
    tmp_path: Path, capsys
) -> None:
    manifest_path = _write_untracked_create_project(tmp_path)
    generated_path = tmp_path / "src" / "generated.py"
    generated_path.parent.mkdir()
    generated_path.write_text("VALUE = 42\n")
    _git(tmp_path, "add", "-N", "src/generated.py")

    exit_code = cmd_plan_revise(_revise_args(manifest_path, tmp_path))
    captured = capsys.readouterr()

    assert exit_code in (0, 2)
    assert generated_path.read_text() == "VALUE = 42\n"
    assert "Cannot merge" not in captured.err
    if exit_code == 0:
        assert _lock_record(tmp_path)["red_evidence"]["red"] is True
    else:
        assert "git reset -- src/generated.py" in captured.err


def test_staged_refusal_names_recovery_command(tmp_path: Path, capsys) -> None:
    manifest_path = _write_tracked_project(tmp_path)
    _git(tmp_path, "add", "src/demo.py")

    exit_code = cmd_plan_revise(_revise_args(manifest_path, tmp_path))

    assert exit_code == 2
    error = capsys.readouterr().err
    assert "src/demo.py" in error
    assert "git restore --staged src/demo.py" in error


def test_lockfile_only_green_capture_reports_dependency_limitation(
    tmp_path: Path, capsys
) -> None:
    (tmp_path / "manifests").mkdir()
    (tmp_path / "scripts").mkdir()
    (tmp_path / "tests").mkdir()
    (tmp_path / "node_modules").mkdir()
    (tmp_path / ".gitignore").write_text("node_modules/\n")
    (tmp_path / "package.json").write_text('{"version": "1"}\n')
    (tmp_path / "package-lock.json").write_text('{"version": "1"}\n')
    (tmp_path / "node_modules" / "installed-version").write_text("1\n")
    (tmp_path / "scripts" / "validate_dependency.py").write_text(
        "from pathlib import Path\n"
        "import sys\n"
        "sys.exit(0 if Path('node_modules/installed-version').read_text().strip() == '2' else 1)\n"
    )
    (tmp_path / "tests" / "test_dependency.py").write_text(
        "def test_dependency_contract():\n    assert True\n"
    )
    manifest_path = tmp_path / "manifests" / "demo-task.manifest.yaml"
    manifest_path.write_text(
        """schema: "2"
goal: "Upgrade dependency"
type: fix
created: "2026-07-18T00:00:00Z"
files:
  edit:
    - path: package.json
      artifacts:
        - kind: attribute
          name: version
          of: dependency manifest
          type: string
    - path: package-lock.json
      artifacts:
        - kind: attribute
          name: version
          of: dependency lock
          type: string
  read:
    - tests/test_dependency.py
validate:
  - python scripts/validate_dependency.py
"""
    )
    _git(tmp_path, "init", "-q")
    _commit_all(tmp_path, "red dependency contract")
    assert cmd_plan_lock(_lock_args(manifest_path, tmp_path)) == 0
    _commit_all(tmp_path, "plan lock")
    (tmp_path / "package.json").write_text('{"version": "2"}\n')
    (tmp_path / "package-lock.json").write_text('{"version": "2"}\n')
    (tmp_path / "node_modules" / "installed-version").write_text("2\n")

    exit_code = cmd_plan_revise(_revise_args(manifest_path, tmp_path))

    assert exit_code == 1
    error = capsys.readouterr().err.lower()
    assert "materialized dependency state" in error
    assert "node_modules" in error and ".venv" in error and "vendor" in error
    assert "prior dependency state" in error
    assert "legacy baseline" in error
    assert (tmp_path / "package.json").read_text() == '{"version": "2"}\n'
    assert (tmp_path / "package-lock.json").read_text() == '{"version": "2"}\n'
    assert _git(tmp_path, "stash", "list").stdout == ""
