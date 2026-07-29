"""Behavioral tests for validate-to-acceptance legacy-baseline cleanup."""

from __future__ import annotations

from pathlib import Path
import subprocess
from types import SimpleNamespace

from maid_runner.cli.commands.plan import cmd_plan_lock
from maid_runner.core.chain import ManifestChain
from maid_runner.core.plan_lock import (
    PlanLock,
    capture_legacy_baseline_evidence,
    default_plan_lock_path,
    enforce_plan_locks,
)


def _git(project_root: Path, *args: str) -> None:
    subprocess.run(
        ["git", *args],
        cwd=project_root,
        check=True,
        capture_output=True,
        text=True,
    )


def _manifest_text(*, include_manual_validate: bool, preserve_acceptance: bool) -> str:
    validate_lines = ["  - python scripts/fast.py"]
    if include_manual_validate:
        validate_lines.append("  - python scripts/manual.py --browser")
    acceptance = (
        "acceptance:\n" "  tests:\n" "    - python scripts/manual.py --browser\n"
        if preserve_acceptance
        else ""
    )
    return f"""schema: "2"
goal: "Completed legacy task"
type: fix
created: "2026-07-29T00:00:00Z"
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
{acceptance}validate:
{chr(10).join(validate_lines)}
"""


def _write_committed_project(project_root: Path) -> Path:
    (project_root / "manifests").mkdir(parents=True)
    (project_root / "src").mkdir()
    (project_root / "tests").mkdir()
    (project_root / "scripts").mkdir()
    (project_root / "src" / "demo.py").write_text(
        "def demo() -> int:\n    return 1\n", encoding="utf-8"
    )
    (project_root / "tests" / "test_demo.py").write_text(
        "from src.demo import demo\n\n\ndef test_demo() -> None:\n"
        "    assert demo() == 1\n",
        encoding="utf-8",
    )
    (project_root / "scripts" / "fast.py").write_text(
        "import sys\nsys.exit(0)\n", encoding="utf-8"
    )
    (project_root / "scripts" / "manual.py").write_text(
        "raise SystemExit('manual browser command must remain opt-in')\n",
        encoding="utf-8",
    )
    manifest_path = project_root / "manifests" / "legacy-task.manifest.yaml"
    manifest_path.write_text(
        _manifest_text(include_manual_validate=True, preserve_acceptance=False),
        encoding="utf-8",
    )
    _git(project_root, "init", "-q")
    _git(project_root, "config", "user.email", "maid-test@example.com")
    _git(project_root, "config", "user.name", "MAID Test")
    _git(project_root, "add", ".")
    _git(project_root, "commit", "-qm", "legacy completed task")
    return manifest_path


def _lock_args(manifest_path: Path, project_root: Path) -> SimpleNamespace:
    return SimpleNamespace(
        plan_command="lock",
        manifest_path=str(manifest_path),
        project_root=str(project_root),
        legacy_baseline=True,
        reason="Move manual browser validation to acceptance evidence",
        no_run=False,
        json=False,
    )


def test_legacy_baseline_accepts_validate_command_preserved_in_acceptance(
    tmp_path: Path,
) -> None:
    manifest_path = _write_committed_project(tmp_path)
    manifest_path.write_text(
        _manifest_text(include_manual_validate=False, preserve_acceptance=True),
        encoding="utf-8",
    )

    evidence = capture_legacy_baseline_evidence(
        manifest_path,
        tmp_path,
        "Move manual browser validation to acceptance evidence",
    )
    exit_code = cmd_plan_lock(_lock_args(manifest_path, tmp_path))

    assert [entry.command for entry in evidence.commands] == ["python scripts/fast.py"]
    assert exit_code == 0
    lock_path = default_plan_lock_path(tmp_path, "legacy-task")
    lock = PlanLock.load(lock_path)
    assert lock.red_evidence is None
    assert lock.legacy_baseline is not None
    assert [entry["command"] for entry in lock.legacy_baseline["commands"]] == [
        "python scripts/fast.py"
    ]

    errors = enforce_plan_locks(
        ManifestChain(tmp_path / "manifests", tmp_path),
        tmp_path,
        require_plan_lock=True,
        require_red_evidence=True,
        changed_paths={"manifests/legacy-task.manifest.yaml"},
        plan_lock_scope="task",
    )

    assert errors == ()


def test_legacy_baseline_rejects_validate_command_removed_without_acceptance_preservation(
    tmp_path: Path,
) -> None:
    manifest_path = _write_committed_project(tmp_path)
    manifest_path.write_text(
        _manifest_text(include_manual_validate=False, preserve_acceptance=False),
        encoding="utf-8",
    )

    exit_code = cmd_plan_lock(_lock_args(manifest_path, tmp_path))

    assert exit_code == 2
    assert not default_plan_lock_path(tmp_path, "legacy-task").exists()
