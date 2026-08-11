"""Standalone pytest plugin for fixture-aware runtime evidence."""

from __future__ import annotations

from dataclasses import dataclass, field
import inspect
import json
import os
from pathlib import Path
import sys
import tempfile
from typing import TYPE_CHECKING, Generator

import coverage
import pytest

if TYPE_CHECKING:
    from maid_runner.core.runtime_evidence import (
        RuntimeContextEvidence,
        RuntimeEvidenceCompleteness,
    )


@dataclass
class _ContextState:
    context_id: str
    kind: str
    consuming_nodeids: set[str] = field(default_factory=set)
    executed_lines: dict[str, set[int]] = field(default_factory=dict)
    called_qualnames: dict[str, set[str]] = field(default_factory=dict)
    fixture_scope: str | None = None
    autouse: bool = False
    lifecycle_equivalent: bool = False


@dataclass
class _CompletenessState:
    missing_worker_ids: set[str] = field(default_factory=set)
    unsupported_selectors: set[str] = field(default_factory=set)
    unresolved_context_ids: set[str] = field(default_factory=set)
    unproven_fixture_lifecycles: set[str] = field(default_factory=set)
    diagnostics: list[dict[str, str]] = field(default_factory=list)

    @property
    def complete(self) -> bool:
        return not (
            self.missing_worker_ids
            or self.unsupported_selectors
            or self.unresolved_context_ids
            or self.unproven_fixture_lifecycles
            or self.diagnostics
        )


class RuntimeEvidencePlugin:
    """Record collection, node, fixture, call, and worker contexts."""

    def __init__(
        self,
        output_path: Path,
        target_files: frozenset[str],
        selectors: tuple[str, ...] = (),
        expected_workers: int = 0,
    ) -> None:
        self.output_path = Path(output_path)
        self.target_files = frozenset(
            str(Path(path).resolve()) for path in target_files
        )
        self._contexts: dict[str, _ContextState] = {}
        self._completeness = _CompletenessState()
        self._selectors = tuple(selectors)
        self._selector_nodeids: dict[str, tuple[str, ...]] = {}
        self._fixture_consumers: dict[str, set[str]] = {}
        self._selected_nodeids: tuple[str, ...] = ()
        self._reports_by_node: dict[str, dict[str, str]] = {}
        self._current_context = "collection:global"
        self._worker_id = os.environ.get("PYTEST_XDIST_WORKER", "main")
        self._expected_workers = expected_workers
        self._configured_workers = 0
        self._yield_fixture_contexts: dict[tuple[object, str], str] = {}
        self._profile_restore_contexts: dict[int, str] = {}
        self._coverage = coverage.Coverage(
            data_file=str(self.output_path.with_suffix(f".{self._worker_id}.coverage")),
            include=sorted(self.target_files),
            config_file=True,
        )
        self._coverage.start()
        self._coverage.switch_context(self._current_context)
        self._previous_profile = sys.getprofile()
        sys.setprofile(self._profile_calls)

    @property
    def contexts(self) -> dict[str, RuntimeContextEvidence]:
        """Return immutable typed snapshots of all recorded contexts."""
        from maid_runner.core._runtime_command_executor import RuntimeFileExecution
        from maid_runner.core.runtime_evidence import RuntimeContextEvidence

        return {
            context_id: RuntimeContextEvidence(
                context_id=state.context_id,
                kind=state.kind,
                consuming_nodeids=tuple(sorted(state.consuming_nodeids)),
                execution_data={
                    path: RuntimeFileExecution(
                        executed_lines=frozenset(state.executed_lines.get(path, ())),
                        called_qualnames=frozenset(
                            state.called_qualnames.get(path, ())
                        ),
                    )
                    for path in set(state.executed_lines) | set(state.called_qualnames)
                },
                fixture_scope=state.fixture_scope,
                autouse=state.autouse,
                lifecycle_equivalent=state.lifecycle_equivalent,
            )
            for context_id, state in self._contexts.items()
        }

    @property
    def completeness(self) -> RuntimeEvidenceCompleteness:
        """Return immutable, explicitly typed completeness evidence."""
        from maid_runner.core.result import ErrorCode, ValidationError
        from maid_runner.core.runtime_evidence import RuntimeEvidenceCompleteness

        diagnostics = []
        for item in self._completeness.diagnostics:
            try:
                code = ErrorCode(item.get("code", ErrorCode.INTERNAL_ERROR.value))
            except ValueError:
                code = ErrorCode.INTERNAL_ERROR
            diagnostics.append(
                ValidationError(code=code, message=str(item.get("message", "")))
            )
        return RuntimeEvidenceCompleteness(
            complete=self._completeness.complete,
            missing_worker_ids=tuple(sorted(self._completeness.missing_worker_ids)),
            unsupported_selectors=tuple(
                sorted(self._completeness.unsupported_selectors)
            ),
            unresolved_context_ids=tuple(
                sorted(self._completeness.unresolved_context_ids)
            ),
            unproven_fixture_lifecycles=tuple(
                sorted(self._completeness.unproven_fixture_lifecycles)
            ),
            diagnostics=tuple(diagnostics),
        )

    def pytest_collection_modifyitems(
        self,
        session: pytest.Session,
        config: pytest.Config,
        items: list[pytest.Item],
    ) -> None:
        """Build exact selector and fixture-consumer closure maps."""
        nodeids = tuple(item.nodeid for item in items)
        self._selected_nodeids = nodeids
        self._selector_nodeids = {
            selector: tuple(
                nodeid for nodeid in nodeids if _selector_matches(selector, nodeid)
            )
            for selector in self._selectors
        }
        for selector, selected in self._selector_nodeids.items():
            if not selected:
                self._completeness.unsupported_selectors.add(selector)
        for item in items:
            for fixture_name in tuple(getattr(item, "fixturenames", ())):
                self._fixture_consumers.setdefault(fixture_name, set()).add(item.nodeid)

    @pytest.hookimpl(hookwrapper=True)
    def pytest_fixture_setup(
        self,
        fixturedef: pytest.FixtureDef,
        request: pytest.FixtureRequest,
    ) -> Generator[None, object, None]:
        """Attribute fixture setup and classify lifecycle equivalence."""
        name = str(getattr(fixturedef, "argname", "unknown"))
        scope = str(getattr(fixturedef, "scope", "unknown"))
        baseid = str(getattr(fixturedef, "baseid", ""))
        item = getattr(request, "node", None)
        nodeid = str(getattr(item, "nodeid", ""))
        context_id = _fixture_context_id(baseid, name, scope, nodeid)
        fixture_info = getattr(item, "_fixtureinfo", None)
        explicit_names = set(getattr(fixture_info, "argnames", ()))
        closure_names = set(getattr(fixture_info, "names_closure", ()))
        dynamic = bool(closure_names) and name not in closure_names
        autouse = name not in explicit_names
        lifecycle_equivalent = scope == "function" and not autouse and not dynamic
        state = self._context(
            context_id,
            "fixture",
            fixture_scope=scope,
            autouse=autouse,
            lifecycle_equivalent=lifecycle_equivalent,
        )
        if scope == "function":
            if nodeid:
                state.consuming_nodeids.add(nodeid)
        else:
            state.consuming_nodeids.update(self._fixture_consumers.get(name, ()))
        if nodeid:
            state.consuming_nodeids.add(nodeid)
        if dynamic:
            self._completeness.unresolved_context_ids.add(context_id)
        if not lifecycle_equivalent:
            self._completeness.unproven_fixture_lifecycles.add(context_id)
        function = getattr(fixturedef, "func", None)
        if function is not None and inspect.isgeneratorfunction(function):
            lifecycle_nodeid = nodeid if scope == "function" else ""
            self._yield_fixture_contexts[(function.__code__, lifecycle_nodeid)] = (
                context_id
            )
        previous = self._current_context
        self._switch_context(context_id)
        try:
            yield
        finally:
            self._switch_context(previous)

    def pytest_runtest_setup(self, item: pytest.Item) -> None:
        """Switch from collection to the selected node context."""
        context_id = f"node:{item.nodeid}"
        state = self._context(context_id, "node", lifecycle_equivalent=True)
        state.consuming_nodeids.add(item.nodeid)
        self._switch_context(context_id)

    @pytest.hookimpl(hookwrapper=True)
    def pytest_runtest_teardown(
        self,
        item: pytest.Item,
        nextitem: pytest.Item | None,
    ) -> Generator[None, object, None]:
        """Keep node attribution active through function fixture teardown."""
        self._switch_context(f"node:{item.nodeid}")
        try:
            yield
        finally:
            if nextitem is None:
                self._switch_context("session:teardown")

    def pytest_fixture_post_finalizer(
        self,
        fixturedef: pytest.FixtureDef,
        request: pytest.FixtureRequest,
    ) -> None:
        """Fail closed when fixture teardown lifecycle is not proven equal."""
        name = str(getattr(fixturedef, "argname", "unknown"))
        scope = str(getattr(fixturedef, "scope", "unknown"))
        baseid = str(getattr(fixturedef, "baseid", ""))
        nodeid = str(getattr(getattr(request, "node", None), "nodeid", ""))
        context_id = _fixture_context_id(baseid, name, scope, nodeid)
        state = self._contexts.get(context_id)
        if state is None:
            self._completeness.unresolved_context_ids.add(context_id)
            return
        function = getattr(fixturedef, "func", None)
        if function is not None and inspect.isgeneratorfunction(function):
            if not state.lifecycle_equivalent:
                self._completeness.unproven_fixture_lifecycles.add(context_id)

    def pytest_runtest_logreport(self, report: pytest.TestReport) -> None:
        """Require setup/call/teardown reports for every selected node."""
        context_id = f"node:{report.nodeid}"
        state = self._context(context_id, "node", lifecycle_equivalent=True)
        state.consuming_nodeids.add(report.nodeid)
        self._reports_by_node.setdefault(report.nodeid, {})[str(report.when)] = str(
            report.outcome
        )

    def pytest_testnodedown(self, node: object, error: object | None) -> None:
        """Record abnormal xdist worker loss."""
        if error is None:
            return
        gateway = getattr(node, "gateway", None)
        worker_id = str(getattr(gateway, "id", getattr(node, "workerid", "unknown")))
        self._completeness.missing_worker_ids.add(worker_id)
        self._completeness.diagnostics.append(
            {
                "code": "E900",
                "message": f"runtime evidence worker {worker_id} was lost",
            }
        )

    def pytest_configure_node(self, node: object) -> None:
        """Clear controller instrumentation after all workers inherited it."""
        self._configured_workers += 1
        if self._configured_workers >= self._expected_workers:
            _clear_private_instrumentation_environment()

    def pytest_sessionfinish(self, session: pytest.Session, exitstatus: int) -> None:
        """Finalize tracing and atomically write this worker's evidence."""
        sys.setprofile(self._previous_profile)
        self._coverage.stop()
        self._coverage.save()
        self._attach_coverage_lines()
        self._validate_report_completeness()
        collection = self._contexts.get("collection:global")
        if collection is not None:
            collection.consuming_nodeids.update(self._selected_nodeids)
            if len(self._selectors) > 1 and (
                collection.executed_lines or collection.called_qualnames
            ):
                self._completeness.unresolved_context_ids.add(collection.context_id)
        if exitstatus != 0:
            self._completeness.diagnostics.append(
                {"code": "E900", "message": f"pytest exited with status {exitstatus}"}
            )
        payload = {
            "worker_id": self._worker_id,
            "selected_nodeids": list(self._selected_nodeids),
            "selector_nodeids": {
                key: list(value) for key, value in self._selector_nodeids.items()
            },
            "reports_by_node": self._reports_by_node,
            "contexts": [_context_payload(value) for value in self._contexts.values()],
            "completeness": _completeness_payload(self._completeness),
            "versions": {
                "python": sys.version,
                "pytest": pytest.__version__,
                "coverage": coverage.__version__,
                "xdist": _distribution_version("pytest-xdist"),
            },
        }
        self.output_path.mkdir(parents=True, exist_ok=True)
        _atomic_write_json(
            self.output_path / f"evidence-{self._worker_id}.json",
            payload,
        )

    def _context(
        self,
        context_id: str,
        kind: str,
        *,
        fixture_scope: str | None = None,
        autouse: bool = False,
        lifecycle_equivalent: bool = False,
    ) -> _ContextState:
        current = self._contexts.get(context_id)
        if current is None:
            current = _ContextState(
                context_id=context_id,
                kind=kind,
                fixture_scope=fixture_scope,
                autouse=autouse,
                lifecycle_equivalent=lifecycle_equivalent,
            )
            self._contexts[context_id] = current
        return current

    def _switch_context(self, context_id: str) -> None:
        self._current_context = context_id
        self._coverage.switch_context(context_id)

    def _profile_calls(self, frame, event, arg):
        frame_id = id(frame)
        if event == "return" and frame_id in self._profile_restore_contexts:
            self._switch_context(self._profile_restore_contexts.pop(frame_id))
            return self._profile_calls
        if event != "call":
            return self._profile_calls
        if frame.f_code.co_name == "main" and frame.f_globals.get("__name__") in {
            "pytest",
            "_pytest.config",
        }:
            self._completeness.unresolved_context_ids.add(
                f"nested-pytest:{self._current_context}"
            )
        nodeid = (
            self._current_context.removeprefix("node:")
            if self._current_context.startswith("node:")
            else ""
        )
        fixture_context = self._yield_fixture_contexts.get((frame.f_code, nodeid))
        if fixture_context is None:
            fixture_context = self._yield_fixture_contexts.get((frame.f_code, ""))
        if fixture_context is not None and fixture_context != self._current_context:
            self._profile_restore_contexts[frame_id] = self._current_context
            self._switch_context(fixture_context)
        filename = str(Path(frame.f_code.co_filename).resolve())
        if filename not in self.target_files:
            return self._profile_calls
        context = self._context(
            self._current_context, _context_kind(self._current_context)
        )
        context.called_qualnames.setdefault(filename, set()).add(
            getattr(frame.f_code, "co_qualname", frame.f_code.co_name)
        )
        return self._profile_calls

    def _attach_coverage_lines(self) -> None:
        data = self._coverage.get_data()
        for filename in self.target_files:
            if filename not in set(data.measured_files()):
                continue
            for line, context_ids in data.contexts_by_lineno(filename).items():
                for context_id in context_ids:
                    context = self._context(context_id, _context_kind(context_id))
                    context.executed_lines.setdefault(filename, set()).add(int(line))

    def _validate_report_completeness(self) -> None:
        nodeids = (
            tuple(self._reports_by_node)
            if self._worker_id != "main"
            else self._selected_nodeids
        )
        for nodeid in nodeids:
            reports = self._reports_by_node.get(nodeid, {})
            required = {"setup", "teardown"}
            if reports.get("setup") == "passed":
                required.add("call")
            for phase in sorted(required - set(reports)):
                self._completeness.unresolved_context_ids.add(
                    f"report:{nodeid}:{phase}"
                )


def pytest_addoption(parser: pytest.Parser) -> None:
    """Register explicit options for standalone child instrumentation."""
    group = parser.getgroup("maid-runtime-evidence")
    group.addoption("--maid-runtime-evidence-output", default=None)
    group.addoption("--maid-runtime-target-files", default=None)


def pytest_configure(config: pytest.Config) -> None:
    """Register only for an explicitly instrumented child and prevent leaks."""
    output = config.getoption("--maid-runtime-evidence-output") or os.environ.get(
        "MAID_RUNTIME_EVIDENCE_OUTPUT"
    )
    targets_value = config.getoption("--maid-runtime-target-files") or os.environ.get(
        "MAID_RUNTIME_TARGET_FILES"
    )
    selectors_value = os.environ.get("MAID_RUNTIME_SELECTORS", "[]")
    if output is None or targets_value is None:
        return
    targets = json.loads(targets_value)
    selectors = json.loads(selectors_value)
    if not isinstance(targets, list) or not all(
        isinstance(item, str) for item in targets
    ):
        raise pytest.UsageError("MAID runtime target files are malformed")
    if not isinstance(selectors, list) or not all(
        isinstance(item, str) for item in selectors
    ):
        raise pytest.UsageError("MAID runtime selectors are malformed")
    worker_input = getattr(config, "workerinput", None)
    try:
        configured_processes = config.getoption("numprocesses", default=0)
    except (AttributeError, TypeError, ValueError):
        configured_processes = 0
    expected_workers = (
        configured_processes if isinstance(configured_processes, int) else 0
    )
    plugin = RuntimeEvidencePlugin(
        Path(output),
        frozenset(targets),
        tuple(selectors),
        expected_workers=expected_workers,
    )
    config.pluginmanager.register(plugin, "maid-runtime-evidence-plugin")
    if worker_input is not None or expected_workers == 0:
        _clear_private_instrumentation_environment()


def _clear_private_instrumentation_environment() -> None:
    for name in (
        "MAID_RUNTIME_EVIDENCE_OUTPUT",
        "MAID_RUNTIME_TARGET_FILES",
        "MAID_RUNTIME_SELECTORS",
    ):
        os.environ.pop(name, None)
    plugins = os.environ.get("PYTEST_PLUGINS")
    if not plugins:
        return
    retained = [
        item.strip()
        for item in plugins.split(",")
        if item.strip() and item.strip() != "_maid_runtime_evidence_plugin"
    ]
    if retained:
        os.environ["PYTEST_PLUGINS"] = ",".join(retained)
    else:
        os.environ.pop("PYTEST_PLUGINS", None)


def _selector_matches(selector: str, nodeid: str) -> bool:
    normalized = selector.replace("\\", "/").lstrip("./")
    path, separator, remainder = normalized.partition("::")
    node_path = nodeid.partition("::")[0]
    if separator:
        return nodeid == normalized or nodeid.startswith(normalized + "[")
    if node_path == path:
        return True
    return node_path.startswith(path.rstrip("/") + "/")


def _fixture_context_id(baseid: str, name: str, scope: str, nodeid: str) -> str:
    suffix = f":{nodeid}" if scope == "function" and nodeid else ""
    return f"fixture:{baseid}:{name}:{scope}{suffix}"


def _context_kind(context_id: str) -> str:
    return context_id.partition(":")[0] or "session"


def _context_payload(context: _ContextState) -> dict:
    files = set(context.executed_lines) | set(context.called_qualnames)
    return {
        "context_id": context.context_id,
        "kind": context.kind,
        "consuming_nodeids": sorted(context.consuming_nodeids),
        "execution_data": {
            path: {
                "executed_lines": sorted(context.executed_lines.get(path, ())),
                "called_qualnames": sorted(context.called_qualnames.get(path, ())),
            }
            for path in sorted(files)
        },
        "fixture_scope": context.fixture_scope,
        "autouse": context.autouse,
        "lifecycle_equivalent": context.lifecycle_equivalent,
    }


def _completeness_payload(completeness: _CompletenessState) -> dict:
    return {
        "complete": completeness.complete,
        "missing_worker_ids": sorted(completeness.missing_worker_ids),
        "unsupported_selectors": sorted(completeness.unsupported_selectors),
        "unresolved_context_ids": sorted(completeness.unresolved_context_ids),
        "unproven_fixture_lifecycles": sorted(completeness.unproven_fixture_lifecycles),
        "diagnostics": list(completeness.diagnostics),
    }


def _distribution_version(name: str) -> str | None:
    try:
        from importlib.metadata import version

        return version(name)
    except Exception:
        return None


def _atomic_write_json(path: Path, payload: object) -> None:
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{path.name}.", suffix=".tmp", dir=path.parent
    )
    temporary = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            json.dump(payload, handle, sort_keys=True)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)
