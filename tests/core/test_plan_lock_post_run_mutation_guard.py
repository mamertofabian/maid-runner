"""Behavioral contract for legacy-baseline post-run mutation detection."""

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


def _write_project_files(project_root: Path, command: str) -> Path:
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
    (project_root / "scripts" / "validate.py").write_text(command, encoding="utf-8")
    manifest_path = project_root / "manifests" / "legacy-task.manifest.yaml"
    manifest_path.write_text(
        _manifest_text("python scripts/validate.py tests/test_demo.py"),
        encoding="utf-8",
    )
    return manifest_path


def _init_repo(repo_root: Path) -> None:
    _git(repo_root, "init", "-q")
    _git(repo_root, "config", "user.email", "maid-test@example.com")
    _git(repo_root, "config", "user.name", "MAID Test")
    _git(repo_root, "add", ".")
    _git(repo_root, "commit", "-qm", "legacy completed task")


def _subdirectory_project(repo_root: Path, command: str) -> tuple[Path, Path]:
    project_root = repo_root / "apps" / "frontend"
    manifest_path = _write_project_files(project_root, command)
    (repo_root / "apps" / "backend").mkdir(parents=True)
    (repo_root / "apps" / "backend" / "server.py").write_text(
        "SERVER = 1\n", encoding="utf-8"
    )
    _init_repo(repo_root)
    return project_root, manifest_path


def test_validation_writing_outside_the_project_root_is_rejected(
    tmp_path: Path,
) -> None:
    from maid_runner.core.plan_lock import capture_legacy_baseline_evidence

    project_root, manifest_path = _subdirectory_project(
        tmp_path,
        "from pathlib import Path\n"
        "Path('../backend/server.py').write_text('SERVER = 2\\n', encoding='utf-8')\n",
    )

    with pytest.raises(ValueError) as excinfo:
        capture_legacy_baseline_evidence(
            manifest_path, project_root, "Strengthen legacy validation"
        )

    message = str(excinfo.value)
    assert "Legacy-baseline validation created or changed unrelated path(s)" in message
    assert "apps/backend/server.py" in message


def test_validation_deleting_outside_the_project_root_is_rejected(
    tmp_path: Path,
) -> None:
    from maid_runner.core.plan_lock import capture_legacy_baseline_evidence

    project_root, manifest_path = _subdirectory_project(
        tmp_path,
        "from pathlib import Path\n" "Path('../backend/server.py').unlink()\n",
    )

    with pytest.raises(ValueError) as excinfo:
        capture_legacy_baseline_evidence(
            manifest_path, project_root, "Strengthen legacy validation"
        )

    message = str(excinfo.value)
    assert "Legacy-baseline validation created or changed unrelated path(s)" in message
    assert "apps/backend/server.py" in message


def test_pre_existing_out_of_project_dirt_still_permits_migration(
    tmp_path: Path,
) -> None:
    from maid_runner.core.plan_lock import (
        LegacyBaselineEvidence,
        capture_legacy_baseline_evidence,
    )

    project_root, manifest_path = _subdirectory_project(
        tmp_path,
        "import sys\nsys.exit(0)\n",
    )
    (tmp_path / "apps" / "backend" / "server.py").write_text(
        "SERVER = 2\n", encoding="utf-8"
    )

    evidence = capture_legacy_baseline_evidence(
        manifest_path, project_root, "Strengthen legacy validation"
    )

    assert isinstance(evidence, LegacyBaselineEvidence)
    assert evidence.commands[0].exit_code == 0
