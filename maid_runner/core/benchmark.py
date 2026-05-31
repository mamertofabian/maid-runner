"""Local benchmark harness for MAID validation gates."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from pathlib import Path
import shlex
import subprocess
import time
from typing import Union


_TAIL_LIMIT = 4000


def benchmark_stage_commands(
    manifest_dir: str,
) -> "tuple[tuple[str, tuple[str, ...]], ...]":
    return (
        (
            "schema",
            (
                "maid",
                "validate",
                "--manifest-dir",
                manifest_dir,
                "--mode",
                "schema",
                "--quiet",
            ),
        ),
        (
            "behavioral",
            (
                "maid",
                "validate",
                "--manifest-dir",
                manifest_dir,
                "--mode",
                "behavioral",
                "--quiet",
            ),
        ),
        (
            "implementation",
            (
                "maid",
                "validate",
                "--manifest-dir",
                manifest_dir,
                "--mode",
                "implementation",
                "--quiet",
            ),
        ),
        (
            "maid_test",
            (
                "maid",
                "test",
                "--manifest-dir",
                manifest_dir,
                "--json",
            ),
        ),
        (
            "maid_verify",
            (
                "maid",
                "verify",
                "--manifest-dir",
                manifest_dir,
                "--keep-going",
                "--no-changed-scope",
                "--advisory",
                "--json",
            ),
        ),
    )


def run_benchmark(
    project_paths: Sequence[Union[str, Path]],
    command_prefix: Sequence[str],
    manifest_dir: str,
    repeat: int,
) -> dict[str, object]:
    if repeat < 1:
        raise ValueError("repeat must be at least 1")

    projects = tuple(project_paths) if project_paths else (".",)
    prefix = tuple(command_prefix)
    stage_commands = benchmark_stage_commands(manifest_dir)
    project_reports = []

    for project_path in projects:
        root = Path(project_path)
        stage_reports = []
        for repeat_index in range(1, repeat + 1):
            for stage_name, stage_command in stage_commands:
                command = (*prefix, *stage_command)
                stage_reports.append(
                    _run_stage(
                        project_path=root,
                        stage_name=stage_name,
                        repeat_index=repeat_index,
                        command=command,
                    )
                )

        project_success = all(stage["success"] for stage in stage_reports)
        project_reports.append(
            {
                "path": str(root),
                "success": project_success,
                "stages": stage_reports,
            }
        )

    return {
        "success": all(project["success"] for project in project_reports),
        "manifest_dir": manifest_dir,
        "repeat": repeat,
        "command_prefix": list(prefix),
        "projects": project_reports,
    }


def format_benchmark_markdown(report: Mapping[str, object]) -> str:
    lines = [
        "# MAID Benchmark",
        "",
        "| Project | Stage | Status | Duration | Exit | Command |",
        "| --- | --- | --- | ---: | ---: | --- |",
    ]
    for project in report.get("projects", []):
        if not isinstance(project, Mapping):
            continue
        project_path = str(project.get("path", ""))
        for stage in project.get("stages", []):
            if not isinstance(stage, Mapping):
                continue
            status = "PASS" if stage.get("success") else "FAIL"
            duration = _format_duration(stage.get("duration_ms"))
            exit_code = stage.get("exit_code", "")
            command = _format_command(stage.get("command", ()))
            lines.append(
                "| "
                f"{project_path} | "
                f"{stage.get('stage', '')} | "
                f"{status} | "
                f"{duration} | "
                f"{exit_code} | "
                f"`{command}` |"
            )
    return "\n".join(lines)


def _run_stage(
    *,
    project_path: Path,
    stage_name: str,
    repeat_index: int,
    command: tuple[str, ...],
) -> dict[str, object]:
    started = time.monotonic()
    try:
        completed = subprocess.run(
            command,
            cwd=project_path,
            capture_output=True,
            text=True,
            check=False,
        )
        duration_ms = (time.monotonic() - started) * 1000
        return {
            "project": str(project_path),
            "stage": stage_name,
            "repeat": repeat_index,
            "command": list(command),
            "exit_code": completed.returncode,
            "success": completed.returncode == 0,
            "duration_ms": duration_ms,
            "stdout_tail": _tail(completed.stdout),
            "stderr_tail": _tail(completed.stderr),
        }
    except OSError as exc:
        duration_ms = (time.monotonic() - started) * 1000
        return {
            "project": str(project_path),
            "stage": stage_name,
            "repeat": repeat_index,
            "command": list(command),
            "exit_code": 127,
            "success": False,
            "duration_ms": duration_ms,
            "stdout_tail": "",
            "stderr_tail": str(exc),
        }


def _tail(value: str) -> str:
    return value[-_TAIL_LIMIT:]


def _format_duration(value: object) -> str:
    if isinstance(value, int | float):
        return f"{value:.0f}ms"
    return ""


def _format_command(value: object) -> str:
    if not isinstance(value, Sequence) or isinstance(value, str):
        return ""
    return shlex.join(str(part) for part in value)
