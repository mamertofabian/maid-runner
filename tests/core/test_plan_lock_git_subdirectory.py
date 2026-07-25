"""Behavioral contract for legacy-baseline capture under a git subdirectory root.

MAID supports a ``project_root`` that lives in a subdirectory of the git
repository. These tests pin that ``capture_legacy_baseline_evidence`` resolves
git paths in a single project-relative namespace so the migration works in that
layout, without relaxing the dirty-path guard it depends on.
"""

from __future__ import annotations

from pathlib import Path
import subprocess

import pytest


def _git(cwd: Path, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", *args],
        cwd=cwd,
        check=True,
        capture_output=True,
        text=True,
    )


def _manifest_text(command: str) -> str:
    return f"""schema: "2"
goal: "Completed legacy task"
type: fix
created: "2026-05-01T00:00:00Z"
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
  - {command}
"""


def _write_project_files(project_root: Path) -> Path:
    """Populate a committable legacy MAID project and return its manifest path."""
    (project_root / "manifests").mkdir(parents=True)
    (project_root / "src").mkdir(parents=True)
    (project_root / "tests").mkdir(parents=True)
    (project_root / "scripts").mkdir(parents=True)
    (project_root / "src" / "demo.py").write_text(
        "def demo() -> int:\n    return 1\n", encoding="utf-8"
    )
    (project_root / "tests" / "test_demo.py").write_text(
        "from src.demo import demo\n\n\ndef test_demo() -> None:\n"
        "    assert demo() == 1\n",
        encoding="utf-8",
    )
    (project_root / "scripts" / "validate.py").write_text(
        "import sys\nsys.exit(0)\n", encoding="utf-8"
    )
    manifest_path = project_root / "manifests" / "legacy-task.manifest.yaml"
    manifest_path.write_text(
        _manifest_text("python scripts/validate.py"), encoding="utf-8"
    )
    return manifest_path


def _init_repo(repo_root: Path) -> None:
    _git(repo_root, "init", "-q")
    _git(repo_root, "config", "user.email", "maid-test@example.com")
    _git(repo_root, "config", "user.name", "MAID Test")
    _git(repo_root, "add", ".")
    _git(repo_root, "commit", "-qm", "legacy completed task")


def _strengthen_validate_command(manifest_path: Path) -> None:
    """Make the manifest dirty in the one way legacy migration permits."""
    manifest_path.write_text(
        _manifest_text("python scripts/validate.py tests/test_demo.py"),
        encoding="utf-8",
    )


def _subdirectory_project(repo_root: Path) -> tuple[Path, Path]:
    """Build a monorepo whose MAID project root is apps/frontend."""
    project_root = repo_root / "apps" / "frontend"
    manifest_path = _write_project_files(project_root)
    (repo_root / "apps" / "backend").mkdir(parents=True)
    (repo_root / "apps" / "backend" / "server.py").write_text(
        "SERVER = 1\n", encoding="utf-8"
    )
    _init_repo(repo_root)
    return project_root, manifest_path


def test_legacy_baseline_accepts_dirty_manifest_in_git_subdirectory(
    tmp_path: Path,
) -> None:
    from maid_runner.core.plan_lock import (
        LegacyBaselineEvidence,
        capture_legacy_baseline_evidence,
    )

    project_root, manifest_path = _subdirectory_project(tmp_path)
    _strengthen_validate_command(manifest_path)
    reason = "Add the already-declared behavioral test to legacy validation"

    evidence = capture_legacy_baseline_evidence(manifest_path, project_root, reason)

    assert isinstance(evidence, LegacyBaselineEvidence)
    assert evidence.reason == reason
    assert (
        evidence.baseline_commit == _git(tmp_path, "rev-parse", "HEAD").stdout.strip()
    )
    assert evidence.commands[0].exit_code == 0


def test_legacy_baseline_rejects_unrelated_dirty_path_in_git_subdirectory(
    tmp_path: Path,
) -> None:
    from maid_runner.core.plan_lock import capture_legacy_baseline_evidence

    project_root, manifest_path = _subdirectory_project(tmp_path)
    _strengthen_validate_command(manifest_path)
    (project_root / "src" / "demo.py").write_text(
        "def demo() -> int:\n    return 2\n", encoding="utf-8"
    )

    with pytest.raises(ValueError) as excinfo:
        capture_legacy_baseline_evidence(
            manifest_path, project_root, "Strengthen legacy validation"
        )

    # The path must be reported project-relative. Asserting only the suffix
    # would also pass on the unnormalized "apps/frontend/src/demo.py", which is
    # the defect under test.
    message = str(excinfo.value)
    assert "src/demo.py" in message
    assert "apps/frontend/src/demo.py" not in message


def test_legacy_baseline_rejects_untracked_path_in_git_subdirectory(
    tmp_path: Path,
) -> None:
    from maid_runner.core.plan_lock import capture_legacy_baseline_evidence

    project_root, manifest_path = _subdirectory_project(tmp_path)
    _strengthen_validate_command(manifest_path)
    (project_root / "src" / "new_impl.py").write_text("NEW = 1\n", encoding="utf-8")

    with pytest.raises(ValueError) as excinfo:
        capture_legacy_baseline_evidence(
            manifest_path, project_root, "Strengthen legacy validation"
        )

    # git ls-files --others is already project-relative. Stripping the prefix
    # from it as well would silently discard every untracked file in the
    # project, reopening the escape hatch this guard exists to close.
    message = str(excinfo.value)
    assert "src/new_impl.py" in message
    assert "apps/frontend/src/new_impl.py" not in message


def test_legacy_baseline_ignores_dirty_paths_outside_the_project_subdirectory(
    tmp_path: Path,
) -> None:
    from maid_runner.core.plan_lock import (
        LegacyBaselineEvidence,
        capture_legacy_baseline_evidence,
    )

    project_root, manifest_path = _subdirectory_project(tmp_path)
    _strengthen_validate_command(manifest_path)
    (tmp_path / "apps" / "backend" / "server.py").write_text(
        "SERVER = 2\n", encoding="utf-8"
    )

    evidence = capture_legacy_baseline_evidence(
        manifest_path, project_root, "Strengthen legacy validation"
    )

    assert isinstance(evidence, LegacyBaselineEvidence)
    assert evidence.commands[0].exit_code == 0


def test_legacy_baseline_still_rejects_unrelated_dirty_path_at_repository_root(
    tmp_path: Path,
) -> None:
    from maid_runner.core.plan_lock import capture_legacy_baseline_evidence

    manifest_path = _write_project_files(tmp_path)
    _init_repo(tmp_path)
    _strengthen_validate_command(manifest_path)
    (tmp_path / "src" / "demo.py").write_text(
        "def demo() -> int:\n    return 2\n", encoding="utf-8"
    )

    with pytest.raises(ValueError) as excinfo:
        capture_legacy_baseline_evidence(
            manifest_path, tmp_path, "Strengthen legacy validation"
        )

    assert "src/demo.py" in str(excinfo.value)
