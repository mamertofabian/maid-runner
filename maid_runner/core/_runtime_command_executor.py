"""Owned runtime-evidence records and the production subprocess adapter."""

from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
from abc import abstractmethod
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from types import MappingProxyType
from typing import Protocol, TYPE_CHECKING

if TYPE_CHECKING:
    from maid_runner.core.runtime_evidence import RuntimeGroupEvidence

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

    @abstractmethod
    def execute_with_contexts(
        self,
        command: tuple[str, ...],
        target_files: set[str],
        project_root: Path,
        timeout_seconds: float,
        pytest_workers: int | str | None = None,
    ) -> RuntimeGroupEvidence: ...


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

    def execute_with_contexts(
        self,
        command: tuple[str, ...],
        target_files: set[str],
        project_root: Path,
        timeout_seconds: float,
        pytest_workers: int | str | None = None,
    ) -> RuntimeGroupEvidence:
        """Execute one contextual pytest group and combine worker evidence."""
        from maid_runner.core._pytest_command_normalization import (
            _normalize_pytest_command,
        )
        from maid_runner.core._pytest_worker_execution import (
            finalize_pytest_timing,
            prepare_pytest_command,
        )
        from maid_runner.core._test_command_execution import _run_test_command
        from maid_runner.core.runtime_evidence import (
            RuntimeGroupEvidence,
            _lenient_pytest_targets,
            combine_runtime_contexts,
        )

        root = Path(project_root).resolve()
        normalized = _normalize_pytest_command(command)
        if normalized is None and not _looks_like_pytest_command(command):
            raise ValueError("contextual runtime evidence requires a pytest command")
        selectors = (
            normalized[1]
            if normalized is not None
            else _lenient_pytest_targets(command)
        )
        prepared = prepare_pytest_command(
            command,
            project_root=root,
            pytest_workers=pytest_workers,
            command_jobs=1,
        )
        with tempfile.TemporaryDirectory(prefix="maid-runtime-evidence-") as tmp:
            tmp_path = Path(tmp)
            output_directory = tmp_path / "output"
            plugin_directory = tmp_path / "plugin"
            plugin_directory.mkdir()
            plugin_name = "_maid_runtime_evidence_plugin"
            plugin_source = Path(__file__).with_name(
                "_runtime_evidence_pytest_plugin.py"
            )
            (plugin_directory / f"{plugin_name}.py").write_text(
                plugin_source.read_text(encoding="utf-8"), encoding="utf-8"
            )
            overrides = dict(prepared.environment_overrides)
            overrides["PYTHONPATH"] = _prepend_pythonpath(
                plugin_directory, overrides.get("PYTHONPATH")
            )
            overrides["PYTEST_PLUGINS"] = _merge_plugins(
                overrides.get("PYTEST_PLUGINS") or os.environ.get("PYTEST_PLUGINS"),
                plugin_name,
            )
            overrides.update(
                {
                    "MAID_RUNTIME_EVIDENCE_OUTPUT": str(output_directory),
                    "MAID_RUNTIME_TARGET_FILES": json.dumps(sorted(target_files)),
                    "MAID_RUNTIME_SELECTORS": json.dumps(list(selectors)),
                }
            )
            result = _run_test_command(
                prepared.command,
                cwd=root,
                timeout=max(1, int(timeout_seconds)),
                environment_overrides=overrides,
            )
            finalize_pytest_timing(prepared, result, root)
            payloads = _load_runtime_evidence_payloads(output_directory)
            expected_worker_ids = _expected_xdist_worker_ids(prepared.command)
            contexts = _contexts_from_payloads(payloads, combine_runtime_contexts)
            selector_nodeids = _selector_nodeids_from_payloads(payloads, selectors)
            selected_nodeids = tuple(
                dict.fromkeys(
                    nodeid
                    for selector in selectors
                    for nodeid in selector_nodeids.get(selector, ())
                )
            )
            completeness = _completeness_from_payloads(
                payloads,
                prepared.command,
                result.exit_code,
                expected_worker_ids,
                selected_nodeids,
            )
            execution_data = _execution_data_from_contexts(contexts)
            record = RuntimeCommandRecord(
                command=prepared.command,
                returncode=result.exit_code,
                stdout=result.stdout,
                stderr=result.stderr,
                execution_data=execution_data,
                report_errors=(),
            )
            return RuntimeGroupEvidence(
                command=prepared.command,
                selected_nodeids=selected_nodeids,
                selector_nodeids=selector_nodeids,
                contexts=contexts,
                result=record,
                worker_ids=tuple(
                    sorted(
                        worker_id
                        for worker_id in {
                            str(payload.get("worker_id", "unknown"))
                            for payload in payloads
                        }
                        if not expected_worker_ids or worker_id != "main"
                    )
                ),
                completeness=completeness,
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


def _prepend_pythonpath(directory: Path, existing: str | None) -> str:
    if existing:
        return str(directory) + os.pathsep + existing
    inherited = os.environ.get("PYTHONPATH")
    if inherited:
        return str(directory) + os.pathsep + inherited
    return str(directory)


def _merge_plugins(existing: str | None, plugin_name: str) -> str:
    plugins = [
        value.strip()
        for value in (existing or "").split(",")
        if value.strip() and value.strip() != plugin_name
    ]
    plugins.append(plugin_name)
    return ",".join(plugins)


def _load_runtime_evidence_payloads(directory: Path) -> list[dict]:
    payloads: list[dict] = []
    for path in sorted(directory.glob("evidence-*.json")):
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, UnicodeError, json.JSONDecodeError):
            continue
        if isinstance(payload, dict):
            payloads.append(payload)
    return payloads


def _contexts_from_payloads(payloads: list[dict], combine) -> tuple:
    from maid_runner.core.runtime_evidence import RuntimeContextEvidence

    grouped: dict[str, list[RuntimeContextEvidence]] = {}
    order: list[str] = []
    for payload in payloads:
        for raw in payload.get("contexts", ()):
            if not isinstance(raw, dict) or not isinstance(raw.get("context_id"), str):
                continue
            context_id = raw["context_id"]
            if context_id not in grouped:
                grouped[context_id] = []
                order.append(context_id)
            execution = {
                path: RuntimeFileExecution(
                    executed_lines=frozenset(value.get("executed_lines", ())),
                    called_qualnames=frozenset(value.get("called_qualnames", ())),
                )
                for path, value in raw.get("execution_data", {}).items()
                if isinstance(path, str) and isinstance(value, dict)
            }
            grouped[context_id].append(
                RuntimeContextEvidence(
                    context_id=context_id,
                    kind=str(raw.get("kind", "unknown")),
                    consuming_nodeids=tuple(raw.get("consuming_nodeids", ())),
                    execution_data=execution,
                    fixture_scope=raw.get("fixture_scope"),
                    autouse=bool(raw.get("autouse", False)),
                    lifecycle_equivalent=bool(raw.get("lifecycle_equivalent", False)),
                )
            )
    contexts = []
    for context_id in order:
        try:
            contexts.append(combine(grouped[context_id]))
        except ValueError:
            contexts.extend(grouped[context_id])
    return tuple(contexts)


def _selector_nodeids_from_payloads(
    payloads: list[dict], selectors: tuple[str, ...]
) -> Mapping[str, tuple[str, ...]]:
    selected: dict[str, list[str]] = {selector: [] for selector in selectors}
    for payload in payloads:
        raw_mapping = payload.get("selector_nodeids", {})
        if not isinstance(raw_mapping, dict):
            continue
        for selector in selectors:
            values = raw_mapping.get(selector, ())
            if not isinstance(values, list):
                continue
            for nodeid in values:
                if isinstance(nodeid, str) and nodeid not in selected[selector]:
                    selected[selector].append(nodeid)
    return MappingProxyType(
        {selector: tuple(nodeids) for selector, nodeids in selected.items()}
    )


def _completeness_from_payloads(
    payloads: list[dict],
    command: tuple[str, ...],
    exit_code: int,
    expected_worker_ids: tuple[str, ...] = (),
    selected_nodeids: tuple[str, ...] = (),
):
    from maid_runner.core.runtime_evidence import RuntimeEvidenceCompleteness

    fields = {
        "missing_worker_ids": [],
        "unsupported_selectors": [],
        "unresolved_context_ids": [],
        "unproven_fixture_lifecycles": [],
    }
    diagnostics: list[ValidationError] = []
    actual_worker_ids = {
        str(payload.get("worker_id"))
        for payload in payloads
        if payload.get("worker_id") is not None
    }
    fields["missing_worker_ids"].extend(
        worker_id
        for worker_id in expected_worker_ids
        if worker_id not in actual_worker_ids
    )
    has_worker_payloads = any(
        payload.get("worker_id") not in {None, "main"} for payload in payloads
    )
    if has_worker_payloads:
        aggregate_reports: dict[str, dict[str, str]] = {}
        for payload in payloads:
            if payload.get("worker_id") == "main":
                continue
            raw_reports = payload.get("reports_by_node", {})
            if not isinstance(raw_reports, dict):
                continue
            for nodeid, reports in raw_reports.items():
                if not isinstance(nodeid, str) or not isinstance(reports, dict):
                    continue
                aggregate_reports.setdefault(nodeid, {}).update(
                    {
                        str(phase): str(outcome)
                        for phase, outcome in reports.items()
                        if isinstance(phase, str) and isinstance(outcome, str)
                    }
                )
        for nodeid in selected_nodeids:
            reports = aggregate_reports.get(nodeid, {})
            required = {"setup", "teardown"}
            if reports.get("setup") == "passed":
                required.add("call")
            for phase in sorted(required - set(reports)):
                fields["unresolved_context_ids"].append(f"report:{nodeid}:{phase}")
    for payload in payloads:
        raw = payload.get("completeness", {})
        if not isinstance(raw, dict):
            continue
        for name in fields:
            if (
                has_worker_payloads
                and payload.get("worker_id") == "main"
                and name != "missing_worker_ids"
            ):
                continue
            for value in raw.get(name, ()):
                if isinstance(value, str) and value not in fields[name]:
                    fields[name].append(value)
        for diagnostic in raw.get("diagnostics", ()):
            if not isinstance(diagnostic, dict):
                continue
            code_value = diagnostic.get("code", ErrorCode.INTERNAL_ERROR.value)
            try:
                code = ErrorCode(code_value)
            except ValueError:
                code = ErrorCode.INTERNAL_ERROR
            diagnostics.append(
                ValidationError(
                    code=code,
                    message=str(diagnostic.get("message", "runtime evidence failed")),
                )
            )
    if not payloads:
        diagnostics.append(
            ValidationError(
                code=ErrorCode.INTERNAL_ERROR,
                message="Runtime evidence plugin produced no output",
            )
        )
    if exit_code != 0 and not diagnostics:
        diagnostics.append(
            ValidationError(
                code=ErrorCode.INTERNAL_ERROR,
                message=f"Runtime evidence command failed: {' '.join(command)}",
            )
        )
    complete = not any(fields.values()) and not diagnostics
    return RuntimeEvidenceCompleteness(
        complete=complete,
        missing_worker_ids=tuple(fields["missing_worker_ids"]),
        unsupported_selectors=tuple(fields["unsupported_selectors"]),
        unresolved_context_ids=tuple(fields["unresolved_context_ids"]),
        unproven_fixture_lifecycles=tuple(fields["unproven_fixture_lifecycles"]),
        diagnostics=tuple(diagnostics),
    )


def _expected_xdist_worker_ids(command: tuple[str, ...]) -> tuple[str, ...]:
    for index, part in enumerate(command):
        value: str | None = None
        if part in {"-n", "--numprocesses"} and index + 1 < len(command):
            value = command[index + 1]
        elif part.startswith("--numprocesses="):
            value = part.partition("=")[2]
        elif part.startswith("-n") and len(part) > 2:
            value = part[2:]
        if value is not None:
            try:
                count = int(value)
            except ValueError:
                return ()
            return tuple(f"gw{worker}" for worker in range(max(0, count)))
    return ()


def _looks_like_pytest_command(command: tuple[str, ...]) -> bool:
    inner = command[2:] if command[:2] == ("uv", "run") else command
    return bool(inner) and (
        Path(inner[0]).name.startswith("pytest")
        or (len(inner) >= 3 and inner[1:3] == ("-m", "pytest"))
    )


def _execution_data_from_contexts(contexts: tuple) -> dict[str, RuntimeFileExecution]:
    result: dict[str, RuntimeFileExecution] = {}
    for context in contexts:
        for path, execution in context.execution_data.items():
            current = result.get(path)
            result[path] = RuntimeFileExecution(
                executed_lines=(
                    execution.executed_lines
                    if current is None
                    else current.executed_lines | execution.executed_lines
                ),
                called_qualnames=(
                    execution.called_qualnames
                    if current is None
                    else current.called_qualnames | execution.called_qualnames
                ),
            )
    return result
