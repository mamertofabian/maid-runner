"""Owned runtime-evidence records and the production subprocess adapter."""

from __future__ import annotations

import json
import subprocess
import sys
import tempfile
from abc import abstractmethod
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from types import MappingProxyType
from typing import Protocol

from maid_runner.core._test_command_execution import (
    _strict_validation_test_active,
    _test_command_environment,
)
from maid_runner.core.result import ErrorCode, ValidationError


@dataclass(frozen=True)
class RuntimeFileExecution:
    executed_lines: frozenset[int]
    called_qualnames: frozenset[str]

    def __post_init__(self) -> None:
        object.__setattr__(self, "executed_lines", frozenset(self.executed_lines))
        object.__setattr__(
            self,
            "called_qualnames",
            frozenset(self.called_qualnames),
        )


@dataclass(frozen=True)
class RuntimeCommandRecord:
    command: tuple[str, ...]
    returncode: int
    stdout: str
    stderr: str
    execution_data: Mapping[str, RuntimeFileExecution]
    report_errors: tuple[ValidationError, ...]

    def __post_init__(self) -> None:
        immutable_data = {
            path: RuntimeFileExecution(
                executed_lines=frozenset(execution.executed_lines),
                called_qualnames=frozenset(execution.called_qualnames),
            )
            for path, execution in self.execution_data.items()
        }
        object.__setattr__(self, "command", tuple(self.command))
        object.__setattr__(self, "execution_data", MappingProxyType(immutable_data))
        object.__setattr__(self, "report_errors", tuple(self.report_errors))


class RuntimeCommandExecutor(Protocol):
    @abstractmethod
    def execute(
        self,
        command: tuple[str, ...],
        target_files: set[str],
        project_root: Path,
        timeout_seconds: float,
    ) -> RuntimeCommandRecord: ...


class SubprocessRuntimeCommandExecutor:
    def execute(
        self,
        command: tuple[str, ...],
        target_files: set[str],
        project_root: Path,
        timeout_seconds: float,
    ) -> RuntimeCommandRecord:
        with tempfile.TemporaryDirectory(
            prefix="maid-artifact-coverage-command-"
        ) as tmp:
            tmp_path = Path(tmp)
            data_file = tmp_path / ".coverage"
            call_file = tmp_path / "calls.json"
            runner = _coverage_runner_script(tmp_path)
            target_file = tmp_path / "target_files.json"
            target_file.write_text(json.dumps(sorted(target_files)))
            proc = subprocess.run(
                (
                    sys.executable,
                    "-m",
                    "coverage",
                    "run",
                    "--data-file",
                    str(data_file),
                    str(runner),
                    str(call_file),
                    str(target_file),
                    "1" if _strict_validation_test_active() else "0",
                    *command,
                ),
                cwd=project_root,
                capture_output=True,
                text=True,
                env=_test_command_environment(),
                timeout=timeout_seconds,
            )
            coverage_json = tmp_path / "coverage.json"
            report_errors = _write_coverage_json(data_file, coverage_json)
            execution_data = (
                _load_execution_data(coverage_json, call_file, project_root)
                if not report_errors
                else {}
            )
            return RuntimeCommandRecord(
                command=command,
                returncode=proc.returncode,
                stdout=proc.stdout,
                stderr=proc.stderr,
                execution_data=execution_data,
                report_errors=tuple(report_errors),
            )


def _coverage_runner_script(tmp_path: Path) -> Path:
    runner = tmp_path / "artifact_coverage_runner.py"
    runner.write_text(
        """
from __future__ import annotations

import json
import sys
import threading
from pathlib import Path

call_output = Path(sys.argv[1])
target_files = set(json.loads(Path(sys.argv[2]).read_text()))
strict_validation = sys.argv[3] == "1"
pytest_args = sys.argv[4:]
calls: set[tuple[str, str, str, int]] = set()
exit_code = 1


def profile_calls(frame, event, arg):
    if event == "call":
        code = frame.f_code
        filename = code.co_filename
        if filename not in target_files:
            return profile_calls
        calls.add(
            (
                filename,
                code.co_name,
                getattr(code, "co_qualname", code.co_name),
                code.co_firstlineno,
            )
        )
    return profile_calls


sys.setprofile(profile_calls)
threading.setprofile(profile_calls)

try:
    sys.path.insert(0, str(Path.cwd()))
    import pytest
    from maid_runner.core._test_command_execution import (
        _strict_validation_test_environment,
    )

    with _strict_validation_test_environment(strict_validation, process_wide=True):
        exit_code = pytest.main(pytest_args)
finally:
    sys.setprofile(None)
    threading.setprofile(None)
    payload = [
        {"file": file, "name": name, "qualname": qualname, "firstlineno": firstlineno}
        for file, name, qualname, firstlineno in sorted(calls)
    ]
    call_output.write_text(json.dumps(payload))

raise SystemExit(exit_code)
""".lstrip()
    )
    return runner


def _write_coverage_json(
    data_file: Path,
    output_file: Path,
) -> list[ValidationError]:
    try:
        import coverage

        cov = coverage.Coverage(data_file=str(data_file))
        cov.load()
        cov.json_report(outfile=str(output_file))
    except Exception as exc:
        return [
            ValidationError(
                code=ErrorCode.INTERNAL_ERROR,
                message=f"Artifact coverage report could not be generated: {exc}",
            )
        ]
    return []


def _load_execution_data(
    report_path: Path,
    call_path: Path,
    project_root: Path,
) -> dict[str, RuntimeFileExecution]:
    data = json.loads(report_path.read_text())
    executed_by_file: dict[str, set[int]] = {}
    for file_path, file_data in data.get("files", {}).items():
        normalized_path = _normalized_source_path(file_path, project_root)
        executed_by_file.setdefault(normalized_path, set()).update(
            file_data.get("executed_lines", [])
        )
    calls_by_file: dict[str, set[str]] = {}
    if call_path.exists():
        for call in json.loads(call_path.read_text() or "[]"):
            normalized_path = _normalized_source_path(call["file"], project_root)
            calls_by_file.setdefault(normalized_path, set()).add(call["qualname"])
    return {
        file_path: RuntimeFileExecution(
            executed_lines=frozenset(executed_by_file.get(file_path, set())),
            called_qualnames=frozenset(calls_by_file.get(file_path, set())),
        )
        for file_path in executed_by_file.keys() | calls_by_file.keys()
    }


def _normalized_source_path(file_path: str, project_root: Path) -> str:
    path = Path(file_path)
    if not path.is_absolute():
        path = project_root / path
    return str(path.resolve())
