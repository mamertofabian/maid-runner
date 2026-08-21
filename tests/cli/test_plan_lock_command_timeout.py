"""Behavioral contract for bounded plan-lock evidence command timeouts."""

from __future__ import annotations

from pathlib import Path
import subprocess

import pytest

from maid_runner.cli.commands._main import build_parser, main
from maid_runner.core.plan_lock import (
    capture_legacy_baseline_evidence,
    capture_red_phase_evidence,
    default_plan_lock_path,
    PlanLock,
)
from maid_runner.core.result import TestRunResult
from maid_runner.core.types import TestStream


def _git(project_root: Path, *args: str) -> None:
    subprocess.run(
        ["git", *args],
        cwd=project_root,
        check=True,
        capture_output=True,
        text=True,
    )


def _write_project(project_root: Path, *, exit_code: int, commit: bool) -> Path:
    (project_root / "manifests").mkdir()
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
    (project_root / "scripts" / "validate.py").write_text(
        "import sys\nsys.exit(" + str(exit_code) + ")\n",
        encoding="utf-8",
    )
    manifest_path = project_root / "manifests" / "timeout.manifest.yaml"
    manifest_path.write_text(
        """schema: "2"
goal: "Capture bounded evidence"
type: fix
created: "2026-08-20T00:00:00Z"
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
""",
        encoding="utf-8",
    )
    if commit:
        _git(project_root, "init", "-q")
        _git(project_root, "config", "user.email", "maid-test@example.com")
        _git(project_root, "config", "user.name", "MAID Test")
        _git(project_root, "add", ".")
        _git(project_root, "commit", "-qm", "completed legacy task")
    return manifest_path


def _install_validation_command_clock(
    monkeypatch: pytest.MonkeyPatch, *, exit_code: int
) -> list[int]:
    from maid_runner.core import plan_lock

    observed_timeouts: list[int] = []

    def run(command, *, timeout, manifest_slug, **_kwargs):
        observed_timeouts.append(timeout)
        timed_out = timeout == 1
        return TestRunResult(
            manifest_slug=manifest_slug,
            command=tuple(command),
            exit_code=-1 if timed_out else exit_code,
            stdout="",
            stderr=f"Command timed out after {timeout}s" if timed_out else "",
            duration_ms=1.0,
            stream=TestStream.IMPLEMENTATION,
        )

    monkeypatch.setattr(plan_lock, "_run_test_command", run)
    return observed_timeouts


def test_plan_lock_parser_exposes_positive_command_timeout() -> None:
    parser = build_parser()
    default_args = parser.parse_args(["plan", "lock", "manifests/task.manifest.yaml"])
    override_args = parser.parse_args(
        [
            "plan",
            "lock",
            "manifests/task.manifest.yaml",
            "--command-timeout",
            "901",
        ]
    )

    assert default_args.command_timeout == 300
    assert override_args.command_timeout == 901
    for invalid_timeout in ("0", "-1", "not-an-integer"):
        with pytest.raises(SystemExit):
            parser.parse_args(
                [
                    "plan",
                    "lock",
                    "manifests/task.manifest.yaml",
                    "--command-timeout",
                    invalid_timeout,
                ]
            )


def test_red_capture_uses_explicit_command_timeout(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    manifest_path = _write_project(tmp_path, exit_code=1, commit=False)
    observed_timeouts = _install_validation_command_clock(monkeypatch, exit_code=1)

    with pytest.raises(ValueError, match="positive"):
        capture_red_phase_evidence(manifest_path, tmp_path, command_timeout_seconds=0)

    timed_out = capture_red_phase_evidence(
        manifest_path, tmp_path, command_timeout_seconds=1
    )
    completed = capture_red_phase_evidence(
        manifest_path, tmp_path, command_timeout_seconds=4
    )

    assert timed_out.red is False
    assert timed_out.commands[0].exit_code == -1
    assert timed_out.commands[0].classification == "invalid"
    assert "timed out after 1s" in timed_out.commands[0].output_tail
    assert completed.red is True
    assert completed.commands[0].exit_code == 1
    assert completed.commands[0].classification == "red"
    assert observed_timeouts == [1, 4]


def test_legacy_capture_uses_explicit_command_timeout(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    manifest_path = _write_project(tmp_path, exit_code=0, commit=True)
    observed_timeouts = _install_validation_command_clock(monkeypatch, exit_code=0)
    reason = "Adopt a completed timeout-controlled manifest"

    with pytest.raises(ValueError, match="positive"):
        capture_legacy_baseline_evidence(
            manifest_path,
            tmp_path,
            reason,
            command_timeout_seconds=0,
        )

    with pytest.raises(ValueError, match="exited -1"):
        capture_legacy_baseline_evidence(
            manifest_path,
            tmp_path,
            reason,
            command_timeout_seconds=1,
        )

    evidence = capture_legacy_baseline_evidence(
        manifest_path,
        tmp_path,
        reason,
        command_timeout_seconds=4,
    )

    assert evidence.commands[0].exit_code == 0
    assert evidence.commands[0].classification == "not_red"
    assert observed_timeouts == [1, 4]


def test_plan_lock_cli_forwards_command_timeout_to_legacy_capture(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    manifest_path = _write_project(tmp_path, exit_code=0, commit=True)
    observed_timeouts = _install_validation_command_clock(monkeypatch, exit_code=0)
    lock_path = default_plan_lock_path(tmp_path, "timeout")
    common_args = [
        "plan",
        "lock",
        str(manifest_path),
        "--project-root",
        str(tmp_path),
        "--legacy-baseline",
        "--reason",
        "Adopt a completed timeout-controlled manifest",
    ]

    assert main([*common_args, "--command-timeout", "1"]) == 2
    assert not lock_path.exists()
    assert main([*common_args, "--command-timeout", "4"]) == 0

    lock = PlanLock.load(lock_path)
    assert lock.red_evidence is None
    assert lock.legacy_baseline is not None
    assert lock.legacy_baseline["commands"][0]["classification"] == "not_red"
    assert observed_timeouts == [1, 4]


def test_plan_lock_cli_forwards_command_timeout_to_red_capture(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    manifest_path = _write_project(tmp_path, exit_code=1, commit=False)
    observed_timeouts = _install_validation_command_clock(monkeypatch, exit_code=1)
    lock_path = default_plan_lock_path(tmp_path, "timeout")
    common_args = [
        "plan",
        "lock",
        str(manifest_path),
        "--project-root",
        str(tmp_path),
    ]

    assert main([*common_args, "--command-timeout", "1"]) == 1
    assert not lock_path.exists()
    assert main([*common_args, "--command-timeout", "4"]) == 0

    lock = PlanLock.load(lock_path)
    assert lock.legacy_baseline is None
    assert lock.red_evidence is not None
    assert lock.red_evidence["commands"][0]["classification"] == "red"
    assert observed_timeouts == [1, 4]
