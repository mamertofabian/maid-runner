"""Owned runtime-evidence records and the production subprocess adapter."""

from __future__ import annotations

import json
import os
import sys
import tempfile
from abc import abstractmethod
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from types import MappingProxyType
from typing import Protocol, TYPE_CHECKING, Union

if TYPE_CHECKING:
    from maid_runner.core.runtime_evidence import (
        RuntimeEvidenceCompleteness,
        RuntimeGroupEvidence,
    )

from maid_runner.core._test_command_execution import (
    _run_test_command,
    _strict_validation_test_active,
    _test_command_environment,
)
from maid_runner.core.result import ErrorCode, ValidationError


_ARTIFACT_XDIST_CONTROLLER_PID = "MAID_ARTIFACT_XDIST_CONTROLLER_PID"


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
        environment_overrides: Mapping[str, str] | None = None,
        environment_removals: Sequence[str] = (),
    ) -> RuntimeCommandRecord: ...

    @abstractmethod
    def execute_with_contexts(
        self,
        command: tuple[str, ...],
        target_files: set[str],
        project_root: Path,
        timeout_seconds: float,
        pytest_workers: Union[int, str, None] = None,
        logical_selectors: tuple[str, ...] | None = None,
    ) -> RuntimeGroupEvidence: ...


class SubprocessRuntimeCommandExecutor:
    def __init__(
        self,
        *,
        environment_overrides: Mapping[str, str] | None = None,
        environment_removals: Sequence[str] = (),
    ) -> None:
        self._environment_overrides = dict(environment_overrides or {})
        self._environment_removals = tuple(environment_removals)

    def _child_environment(
        self,
        environment_overrides: Mapping[str, str] | None = None,
        environment_removals: Sequence[str] = (),
    ) -> dict[str, str]:
        environment = _test_command_environment()
        for name in dict.fromkeys((*self._environment_removals, *environment_removals)):
            environment.pop(name, None)
        environment.update(self._environment_overrides)
        environment.update(environment_overrides or {})
        return environment

    def execute(
        self,
        command: tuple[str, ...],
        target_files: set[str],
        project_root: Path,
        timeout_seconds: float,
        environment_overrides: Mapping[str, str] | None = None,
        environment_removals: Sequence[str] = (),
    ) -> RuntimeCommandRecord:
        complete_removals = tuple(
            dict.fromkeys((*self._environment_removals, *environment_removals))
        )
        environment = self._child_environment(
            environment_overrides,
            environment_removals,
        )
        environment.pop(_ARTIFACT_XDIST_CONTROLLER_PID, None)
        uses_pytest_workers = _uses_pytest_workers(command, project_root)
        if not uses_pytest_workers:
            environment.setdefault("COVERAGE_CORE", "sysmon")
        with tempfile.TemporaryDirectory(
            prefix="maid-artifact-coverage-command-"
        ) as tmp:
            tmp_path = Path(tmp)
            data_file = tmp_path / ".coverage"
            call_file = tmp_path / "calls.json"
            runner = _coverage_runner_script(tmp_path)
            target_file = tmp_path / "target_files.json"
            target_file.write_text(json.dumps(sorted(target_files)))
            include_args = (
                ()
                if any("," in path for path in target_files)
                else ("--include", ",".join(sorted(target_files)))
            )
            if uses_pytest_workers:
                plugin_directory = tmp_path / "worker-plugin"
                plugin_directory.mkdir()
                plugin_name = "_maid_artifact_coverage_worker"
                (plugin_directory / f"{plugin_name}.py").write_text(
                    _coverage_worker_plugin_source(), encoding="utf-8"
                )
                environment["PYTHONPATH"] = _prepend_pythonpath(
                    plugin_directory, environment.get("PYTHONPATH")
                )
                environment["PYTEST_PLUGINS"] = _merge_plugins(
                    environment.get("PYTEST_PLUGINS"), plugin_name
                )
                environment.update(
                    {
                        "MAID_ARTIFACT_COVERAGE_DATA": str(data_file),
                        "MAID_ARTIFACT_CALL_DIRECTORY": str(tmp_path),
                        "MAID_ARTIFACT_TARGET_FILES": str(target_file),
                    }
                )
            owned_command = (
                sys.executable,
                "-m",
                "coverage",
                "run",
                "--data-file",
                str(data_file),
                *include_args,
                str(runner),
                str(call_file),
                str(target_file),
                "1" if _strict_validation_test_active() else "0",
                *command,
            )
            proc = _run_test_command(
                owned_command,
                cwd=project_root,
                timeout=timeout_seconds,
                environment_overrides=environment,
                environment_removals=tuple(
                    dict.fromkeys((*complete_removals, _ARTIFACT_XDIST_CONTROLLER_PID))
                ),
                require_descendant_ownership=True,
            )
            if proc.exit_code < 0:
                execution_data = {}
                report_errors = []
            else:
                report_errors = _combine_coverage_data(data_file, tmp_path)
                if not report_errors:
                    execution_data, load_errors = _load_target_execution_data(
                        data_file,
                        call_file,
                        project_root,
                        target_files,
                    )
                    report_errors = load_errors
                else:
                    execution_data = {}
            return RuntimeCommandRecord(
                command=command,
                returncode=proc.exit_code,
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
        pytest_workers: Union[int, str, None] = None,
        logical_selectors: tuple[str, ...] | None = None,
    ) -> RuntimeGroupEvidence:
        """Execute one contextual pytest group and combine worker evidence."""
        from maid_runner.core._pytest_command_normalization import (
            _normalize_pytest_command,
        )
        from maid_runner.core._pytest_worker_execution import (
            _prepare_pytest_command,
            finalize_pytest_timing,
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
        selectors = logical_selectors or (
            normalized[1]
            if normalized is not None
            else _lenient_pytest_targets(command)
        )
        prepared = _prepare_pytest_command(
            command,
            project_root=root,
            pytest_workers=pytest_workers,
            command_jobs=1,
            environment_overrides=self._environment_overrides,
            environment_removals=self._environment_removals,
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
            overrides = dict(self._environment_overrides)
            overrides.update(prepared.environment_overrides)
            overrides["PYTHONPATH"] = _prepend_pythonpath(
                plugin_directory, overrides.get("PYTHONPATH")
            )
            child_plugins = self._child_environment().get("PYTEST_PLUGINS")
            overrides["PYTEST_PLUGINS"] = _merge_plugins(
                overrides.get("PYTEST_PLUGINS") or child_plugins,
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
                environment_removals=self._environment_removals,
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
                _failed_nodeids=_failed_nodeids_from_payloads(payloads),
            )


def _coverage_runner_script(tmp_path: Path) -> Path:
    runner = tmp_path / "artifact_coverage_runner.py"
    runner.write_text(
        """
from __future__ import annotations

import json
import os
import sys
import threading
from pathlib import Path

target_files = set()
calls: set[tuple[str, str, str, int]] = set()
monitoring_tool_id = None
monitoring_ref = None
monitoring_disable = None


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


def monitor_call(code, instruction_offset):
    if code.co_filename in target_files:
        calls.add(
            (
                code.co_filename,
                code.co_name,
                getattr(code, "co_qualname", code.co_name),
                code.co_firstlineno,
            )
        )
    # Return the DISABLE sentinel captured at registration, never a live
    # sys.monitoring read: an instrumented test may swap sys.monitoring for a
    # stub, and re-reading it here would raise inside the callback.
    return monitoring_disable


def instrumentation_marker(frame, event, arg):
    return None


def start_call_monitoring():
    global monitoring_tool_id, monitoring_ref, monitoring_disable
    monitoring = getattr(sys, "monitoring", None)
    if monitoring is not None:
        tool_id = monitoring.PROFILER_ID
        try:
            monitoring.use_tool_id(tool_id, "maid artifact calls")
            monitoring.register_callback(
                tool_id, monitoring.events.PY_START, monitor_call
            )
            monitoring_ref = monitoring
            monitoring_disable = getattr(monitoring, "DISABLE", None)
            monitoring.set_events(tool_id, monitoring.events.PY_START)
            monitoring_tool_id = tool_id
            # Preserve the legacy observable instrumentation boundary while
            # sys.monitoring owns the actual low-overhead call collection.
            sys.setprofile(instrumentation_marker)
            threading.setprofile(instrumentation_marker)
            return
        except (RuntimeError, ValueError):
            try:
                monitoring.free_tool_id(tool_id)
            except ValueError:
                pass
    sys.setprofile(profile_calls)
    threading.setprofile(profile_calls)


def stop_call_monitoring():
    if monitoring_tool_id is not None:
        monitoring = monitoring_ref
        monitoring.set_events(monitoring_tool_id, 0)
        monitoring.register_callback(
            monitoring_tool_id, monitoring.events.PY_START, None
        )
        monitoring.free_tool_id(monitoring_tool_id)
        sys.setprofile(None)
        threading.setprofile(None)
        return
    sys.setprofile(None)
    threading.setprofile(None)


def main():
    global target_files
    call_output = Path(sys.argv[1])
    target_files = set(json.loads(Path(sys.argv[2]).read_text()))
    strict_validation = sys.argv[3] == "1"
    pytest_args = sys.argv[4:]
    start_call_monitoring()
    if "MAID_ARTIFACT_COVERAGE_DATA" not in os.environ:
        os.environ.pop("COVERAGE_CORE", None)

    try:
        sys.path.insert(0, str(Path.cwd()))
        import pytest
        from maid_runner.core._test_command_execution import (
            _strict_validation_test_environment,
        )

        with _strict_validation_test_environment(strict_validation, process_wide=True):
            return pytest.main(pytest_args)
    finally:
        stop_call_monitoring()
        payload = [
            {"file": file, "name": name, "qualname": qualname, "firstlineno": firstlineno}
            for file, name, qualname, firstlineno in sorted(calls)
        ]
        call_output.write_text(json.dumps(payload))


if __name__ == "__main__":
    raise SystemExit(main())
""".lstrip()
    )
    return runner


def _coverage_worker_plugin_source() -> str:
    return r"""
from __future__ import annotations

import json
import os
import errno
import subprocess
import sys
import threading
import time
from contextlib import contextmanager
from pathlib import Path

try:
    import fcntl
except ImportError:
    fcntl = None

_coverage = None
_calls = set()
_finished = False
_monitoring_tool_id = None
_monitoring_ref = None
_monitoring_disable = None
_coverage_data_file = Path(os.environ["MAID_ARTIFACT_COVERAGE_DATA"])
_call_directory = Path(os.environ["MAID_ARTIFACT_CALL_DIRECTORY"])
_target_files = set(json.loads(Path(os.environ["MAID_ARTIFACT_TARGET_FILES"]).read_text()))
_controller_pid_name = "MAID_ARTIFACT_XDIST_CONTROLLER_PID"
_plugin_name = "_maid_artifact_coverage_worker"


class _ChildProcessPermitPool:
    def __init__(self, directory, permits=1):
        self.directory = Path(directory)
        self.permits = permits

    @contextmanager
    def acquire(self):
        if fcntl is None:
            raise RuntimeError("process-safe child permit is unavailable")
        lock_file = None
        while lock_file is None:
            for index in range(self.permits):
                candidate = (self.directory / f"child-process-{index}.lock").open("a+")
                try:
                    fcntl.flock(candidate, fcntl.LOCK_EX | fcntl.LOCK_NB)
                except OSError as exc:
                    candidate.close()
                    if exc.errno not in (errno.EACCES, errno.EAGAIN):
                        raise
                else:
                    lock_file = candidate
                    break
            if lock_file is None:
                time.sleep(0.01)
        try:
            yield
        finally:
            fcntl.flock(lock_file, fcntl.LOCK_UN)
            lock_file.close()


def _permit_wrapped_popen(original_popen, permit_pool):
    base_popen = getattr(original_popen, "_maid_original_popen", original_popen)

    class PermitPopen(original_popen):
        _maid_child_process_permits = True
        _maid_original_popen = base_popen

        def __init__(self, *args, **kwargs):
            self._maid_permit = permit_pool.acquire()
            self._maid_permit.__enter__()
            self._maid_permit_released = False
            self._maid_permit_lock = threading.Lock()
            try:
                super().__init__(*args, **kwargs)
            except BaseException:
                self._maid_release_permit()
                raise
            threading.Thread(target=self._maid_reap, daemon=True).start()

        def _maid_release_permit(self):
            with self._maid_permit_lock:
                if self._maid_permit_released:
                    return
                self._maid_permit_released = True
            self._maid_permit.__exit__(None, None, None)

        def _maid_reap(self):
            try:
                original_popen.wait(self)
            finally:
                self._maid_release_permit()

        def wait(self, *args, **kwargs):
            result = super().wait(*args, **kwargs)
            self._maid_release_permit()
            return result

        def communicate(self, *args, **kwargs):
            result = super().communicate(*args, **kwargs)
            self._maid_release_permit()
            return result

        def poll(self):
            result = super().poll()
            if result is not None:
                self._maid_release_permit()
            return result

        def __exit__(self, *args):
            try:
                return super().__exit__(*args)
            finally:
                self._maid_release_permit()

    PermitPopen.__name__ = original_popen.__name__
    PermitPopen.__qualname__ = original_popen.__qualname__
    PermitPopen.__module__ = original_popen.__module__
    return PermitPopen


if os.environ.get("PYTEST_XDIST_WORKER"):
    _child_permits = _ChildProcessPermitPool(_call_directory, permits=2)
    subprocess.Popen = _permit_wrapped_popen(subprocess.Popen, _child_permits)
    plugins = [
        name.strip()
        for name in os.environ.get("PYTEST_PLUGINS", "").split(",")
        if name.strip() and name.strip() != _plugin_name
    ]
    if plugins:
        os.environ["PYTEST_PLUGINS"] = ",".join(plugins)
    else:
        os.environ.pop("PYTEST_PLUGINS", None)
    for name in tuple(os.environ):
        if name.startswith("MAID_ARTIFACT_"):
            os.environ.pop(name, None)


def _profile_calls(frame, event, arg):
    if event == "call":
        code = frame.f_code
        if code.co_filename in _target_files:
            _calls.add(
                (
                    code.co_filename,
                    code.co_name,
                    getattr(code, "co_qualname", code.co_name),
                    code.co_firstlineno,
                )
            )
    return _profile_calls


def _monitor_call(code, instruction_offset):
    if code.co_filename in _target_files:
        _calls.add(
            (
                code.co_filename,
                code.co_name,
                getattr(code, "co_qualname", code.co_name),
                code.co_firstlineno,
            )
        )
    # Captured at registration so a swapped sys.monitoring cannot make this
    # callback raise and poison the instrumented session.
    return _monitoring_disable


def _start_call_monitoring():
    global _monitoring_tool_id, _monitoring_ref, _monitoring_disable
    monitoring = getattr(sys, "monitoring", None)
    if monitoring is not None:
        tool_id = monitoring.PROFILER_ID
        try:
            monitoring.use_tool_id(tool_id, "maid artifact calls")
            monitoring.register_callback(
                tool_id, monitoring.events.PY_START, _monitor_call
            )
            _monitoring_ref = monitoring
            _monitoring_disable = getattr(monitoring, "DISABLE", None)
            monitoring.set_events(tool_id, monitoring.events.PY_START)
            _monitoring_tool_id = tool_id
            return
        except (RuntimeError, ValueError):
            try:
                monitoring.free_tool_id(tool_id)
            except ValueError:
                pass
    sys.setprofile(_profile_calls)
    threading.setprofile(_profile_calls)


def _stop_call_monitoring():
    if _monitoring_tool_id is not None:
        monitoring = _monitoring_ref
        monitoring.set_events(_monitoring_tool_id, 0)
        monitoring.register_callback(
            _monitoring_tool_id, monitoring.events.PY_START, None
        )
        monitoring.free_tool_id(_monitoring_tool_id)
        return
    sys.setprofile(None)
    threading.setprofile(None)


def pytest_configure(config):
    global _coverage
    if not hasattr(config, "workerinput"):
        os.environ.setdefault(_controller_pid_name, str(os.getpid()))
        return
    if not config.workerinput.get("maid_artifact_coverage_worker"):
        return
    import coverage

    _coverage = coverage.Coverage(
        data_file=str(_coverage_data_file),
        data_suffix=True,
        include=sorted(_target_files),
    )
    _coverage.start()
    os.environ.pop("COVERAGE_CORE", None)
    _start_call_monitoring()


def pytest_configure_node(node):
    if os.environ.get(_controller_pid_name) == str(os.getpid()):
        node.workerinput["maid_artifact_coverage_worker"] = True


def pytest_sessionfinish(session, exitstatus):
    _finish(session.config)


def pytest_unconfigure(config):
    _finish(config)


def _finish(config):
    global _finished
    if (
        _finished
        or _coverage is None
        or not hasattr(config, "workerinput")
        or not config.workerinput.get("maid_artifact_coverage_worker")
    ):
        return
    _finished = True
    _stop_call_monitoring()
    _coverage.stop()
    _coverage.save()
    worker_id = os.environ.get("PYTEST_XDIST_WORKER", "worker")
    output = _call_directory / f"calls-{worker_id}.json"
    output.write_text(
        json.dumps(
            [
                {"file": file, "name": name, "qualname": qualname, "firstlineno": firstlineno}
                for file, name, qualname, firstlineno in sorted(_calls)
            ]
        )
    )
""".lstrip()


def _uses_pytest_workers(command: tuple[str, ...], project_root: Path) -> bool:
    from maid_runner.core._pytest_worker_execution import _configured_workers

    configured = _configured_workers(("pytest", *command), Path(project_root))
    if configured is None:
        return False
    workers, _source = configured
    if isinstance(workers, str) and workers.startswith("="):
        workers = workers[1:]
    return workers not in {0, 1, "0", "1"}


def _combine_coverage_data(data_file: Path, directory: Path) -> list[ValidationError]:
    parallel_files = tuple(directory.glob(f"{data_file.name}.*"))
    if not parallel_files:
        return []
    try:
        import coverage

        cov = coverage.Coverage(data_file=str(data_file))
        if data_file.exists():
            cov.load()
        cov.combine(data_paths=[str(directory)], strict=True)
        cov.save()
    except Exception as exc:
        return [
            ValidationError(
                code=ErrorCode.INTERNAL_ERROR,
                message=f"Artifact coverage worker data could not be combined: {exc}",
            )
        ]
    return []


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


def _load_target_execution_data(
    data_file: Path,
    call_path: Path,
    project_root: Path,
    target_files: set[str],
) -> tuple[dict[str, RuntimeFileExecution], list[ValidationError]]:
    try:
        import coverage

        data = coverage.CoverageData(basename=str(data_file))
        data.read()
        executed_by_file = {
            _normalized_source_path(path, project_root): set(data.lines(path) or ())
            for path in target_files
        }
    except Exception as exc:
        return {}, [
            ValidationError(
                code=ErrorCode.INTERNAL_ERROR,
                message=f"Artifact coverage data could not be loaded: {exc}",
            )
        ]

    calls_by_file: dict[str, set[str]] = {}
    call_paths = (call_path, *sorted(call_path.parent.glob("calls-*.json")))
    try:
        for current_call_path in call_paths:
            if not current_call_path.exists():
                continue
            for call in json.loads(current_call_path.read_text() or "[]"):
                normalized_path = _normalized_source_path(call["file"], project_root)
                calls_by_file.setdefault(normalized_path, set()).add(call["qualname"])
    except (OSError, UnicodeError, json.JSONDecodeError, KeyError, TypeError) as exc:
        return {}, [
            ValidationError(
                code=ErrorCode.INTERNAL_ERROR,
                message=f"Artifact call data could not be loaded: {exc}",
            )
        ]
    return {
        path: RuntimeFileExecution(
            executed_lines=frozenset(executed_by_file.get(path, set())),
            called_qualnames=frozenset(calls_by_file.get(path, set())),
        )
        for path in executed_by_file.keys() | calls_by_file.keys()
    }, []


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
    call_paths = (call_path, *sorted(call_path.parent.glob("calls-*.json")))
    for current_call_path in call_paths:
        if not current_call_path.exists():
            continue
        for call in json.loads(current_call_path.read_text() or "[]"):
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
                    fixture_definition_source=(
                        str(raw["fixture_definition_source"])
                        if isinstance(raw.get("fixture_definition_source"), str)
                        else None
                    ),
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


def _reports_by_node_from_payloads(payloads: list[dict]) -> dict[str, dict[str, str]]:
    aggregate: dict[str, dict[str, str]] = {}
    for payload in payloads:
        raw_reports = payload.get("reports_by_node", {})
        if not isinstance(raw_reports, dict):
            continue
        for nodeid, reports in raw_reports.items():
            if not isinstance(nodeid, str) or not isinstance(reports, dict):
                continue
            aggregate.setdefault(nodeid, {}).update(
                {
                    str(phase): str(outcome)
                    for phase, outcome in reports.items()
                    if isinstance(phase, str) and isinstance(outcome, str)
                }
            )
    return aggregate


def _failed_nodeids_from_payloads(payloads: list[dict]) -> tuple[str, ...]:
    failed: list[str] = []
    for nodeid, reports in _reports_by_node_from_payloads(payloads).items():
        if reports.get("setup") in {"failed", "error"} or reports.get("call") in {
            "failed",
            "error",
        }:
            failed.append(nodeid)
    return tuple(failed)


def _completeness_from_payloads(
    payloads: list[dict],
    command: tuple[str, ...],
    exit_code: int,
    expected_worker_ids: tuple[str, ...] = (),
    selected_nodeids: tuple[str, ...] = (),
) -> RuntimeEvidenceCompleteness:
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
    supported_selectors = {
        selector
        for payload in payloads
        for selector, nodeids in (
            payload.get("selector_nodeids", {}).items()
            if isinstance(payload.get("selector_nodeids"), dict)
            else ()
        )
        if isinstance(selector, str)
        and isinstance(nodeids, list)
        and any(isinstance(nodeid, str) for nodeid in nodeids)
    }
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
                if name == "unsupported_selectors" and value in supported_selectors:
                    continue
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
    reports = _reports_by_node_from_payloads(payloads)
    if exit_code != 0 and not diagnostics and not reports:
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
