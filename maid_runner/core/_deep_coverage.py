"""Opt-in Python coverage evidence for risk-v1."""

from __future__ import annotations

from collections.abc import Collection
from dataclasses import dataclass
import json
from pathlib import Path
import re
import subprocess
import tempfile


@dataclass(frozen=True)
class DeepCoverageResult:
    percentages: dict[str, float]
    warnings: tuple[str, ...] = ()


def collect_deep_coverage(
    project_root: Path,
    command: tuple[str, ...],
    paths: Collection[str],
) -> DeepCoverageResult:
    if not _is_pytest_command(command):
        raise ValueError(
            "coverage_recommendation.deep.command must execute Python pytest"
        )
    non_python = sorted(path for path in paths if not path.endswith(".py"))
    python_paths = {path for path in paths if path.endswith(".py")}
    with tempfile.TemporaryDirectory(prefix="maid-coverage-") as temporary:
        report_path = Path(temporary) / "coverage.json"
        argv = [
            *command,
            "--cov=.",
            f"--cov-report=json:{report_path}",
            "--cov-report=",
        ]
        result = subprocess.run(
            argv,
            cwd=project_root,
            capture_output=True,
            text=True,
            timeout=300,
        )
        if result.returncode != 0:
            detail = (result.stderr or result.stdout).strip()
            raise ValueError(
                f"Deep coverage command failed ({result.returncode}): {detail}"
            )
        try:
            payload = json.loads(report_path.read_text(encoding="utf-8"))
        except (OSError, ValueError) as exc:
            raise ValueError(f"Deep coverage report was unavailable: {exc}") from exc

    percentages: dict[str, float] = {}
    files = payload.get("files", {}) if isinstance(payload, dict) else {}
    if isinstance(files, dict):
        for raw_path, record in files.items():
            if not isinstance(record, dict):
                continue
            summary = record.get("summary", {})
            if not isinstance(summary, dict):
                continue
            percent = summary.get("percent_covered")
            if not isinstance(percent, (int, float)):
                continue
            normalized = _relative_path(project_root, str(raw_path))
            if normalized in python_paths:
                percentages[normalized] = round(float(percent), 1)
    warnings = (
        (f"Deep coverage is Python-only; skipped {len(non_python)} non-Python file(s)",)
        if non_python
        else ()
    )
    return DeepCoverageResult(percentages, warnings)


def _is_pytest_command(command: tuple[str, ...]) -> bool:
    if not command:
        return False
    executable = Path(command[0]).name
    if executable in {"pytest", "pytest.exe"}:
        return True
    if _is_python_executable(executable):
        return len(command) >= 3 and command[1:3] == ("-m", "pytest")
    if executable == "uv" and len(command) >= 5 and command[1] == "run":
        return _is_python_executable(Path(command[2]).name) and command[3:5] == (
            "-m",
            "pytest",
        )
    return False


def _is_python_executable(name: str) -> bool:
    return bool(re.fullmatch(r"python(?:3(?:\.\d+)?)?(?:\.exe)?", name))


def _relative_path(project_root: Path, raw_path: str) -> str:
    path = Path(raw_path)
    if not path.is_absolute():
        return path.as_posix().removeprefix("./")
    try:
        return path.resolve().relative_to(project_root).as_posix()
    except ValueError:
        return path.as_posix()
