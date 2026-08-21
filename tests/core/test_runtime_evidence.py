"""Behavioral contract for fixture-aware grouped runtime evidence."""

from __future__ import annotations

import json
import os
from pathlib import Path
from types import MappingProxyType, SimpleNamespace

import pytest

from maid_runner.core.manifest import load_manifest
from maid_runner.core.result import ErrorCode, ValidationError


def _write_manifest(
    root: Path,
    slug: str,
    command: str,
    *,
    source: str = "src/target.py",
) -> Path:
    manifests = root / "manifests"
    manifests.mkdir(exist_ok=True)
    path = manifests / f"{slug}.manifest.yaml"
    path.write_text(
        f"""schema: "2"
goal: "Exercise {slug}"
type: feature
created: "2026-08-11T00:00:00Z"
files:
  edit:
    - path: {source}
      artifacts:
        - kind: function
          name: target
          args: []
          returns: bool
  read:
    - tests/test_{slug}.py
validate:
  - {command}
"""
    )
    return path


def _project(root: Path) -> None:
    source = root / "src"
    tests = root / "tests"
    source.mkdir()
    tests.mkdir()
    (source / "target.py").write_text("def target():\n    return True\n")
    for name in ("alpha", "beta"):
        (tests / f"test_{name}.py").write_text(
            "from src.target import target\n\n"
            f"def test_{name}():\n"
            "    assert target() is True\n"
        )


def test_runtime_evidence_uses_low_overhead_monitoring_without_losing_target_calls(
    tmp_path,
):
    import sys

    if not hasattr(sys, "monitoring"):
        return
    from maid_runner.core.runtime_evidence import collect_runtime_evidence

    _project(tmp_path)
    manifest = load_manifest(
        _write_manifest(
            tmp_path,
            "alpha",
            "python -m pytest -q tests/test_alpha.py",
        )
    )
    (tmp_path / "tests/test_alpha.py").write_text(
        "def test_alpha():\n"
        "    from src.target import target\n"
        "    assert target() is True\n"
    )
    (tmp_path / "conftest.py").write_text(
        "import sys\n\n"
        "def pytest_sessionstart(session):\n"
        "    assert sys.getprofile() is None\n"
    )

    run = collect_runtime_evidence([manifest], tmp_path)

    command = run.evidence.commands[0]
    assert command.result.returncode == 0, command.result.stderr
    called = {
        qualname
        for context in command.contexts
        for execution in context.execution_data.values()
        for qualname in execution.called_qualnames
    }
    assert "target" in called


def test_monitoring_preserves_generator_context_repeated_calls_and_nested_pytest(
    tmp_path,
):
    import sys

    if not hasattr(sys, "monitoring"):
        return
    from maid_runner.core.runtime_evidence import collect_runtime_evidence

    _project(tmp_path)
    manifest = load_manifest(
        _write_manifest(tmp_path, "alpha", "python -m pytest -q tests/")
    )
    (tmp_path / "conftest.py").write_text(
        "import pytest\n"
        "from src.target import target\n\n"
        "@pytest.fixture(scope='session', autouse=True)\n"
        "def lifecycle():\n"
        "    target()\n"
        "    yield\n"
        "    target()\n"
    )
    (tmp_path / "tests/nested_empty.py").write_text("VALUE = True\n")
    (tmp_path / "tests/test_alpha.py").write_text(
        "import pytest\n"
        "from src.target import target\n\n"
        "def test_alpha():\n"
        "    assert target() is True\n"
        "    assert pytest.main(['--collect-only', '-q', 'tests/nested_empty.py']) == 5\n"
    )

    command = collect_runtime_evidence([manifest], tmp_path).evidence.commands[0]

    node_contexts = [context for context in command.contexts if context.kind == "node"]
    assert len(node_contexts) == 2
    assert all(
        "target"
        in {
            name
            for execution in context.execution_data.values()
            for name in execution.called_qualnames
        }
        for context in node_contexts
    )
    fixture = next(context for context in command.contexts if context.kind == "fixture")
    assert "target" in {
        name
        for execution in fixture.execution_data.values()
        for name in execution.called_qualnames
    }
    assert any(
        item.startswith("nested-pytest:")
        for item in command.completeness.unresolved_context_ids
    )


def test_monitoring_ownership_failure_falls_back_and_restores_prior_profile(
    tmp_path, monkeypatch
):
    import sys
    from types import SimpleNamespace

    from maid_runner.core._runtime_evidence_pytest_plugin import RuntimeEvidencePlugin

    def previous(*args):
        return None

    sys.setprofile(previous)

    class Events:
        PY_START = 1
        PY_RETURN = 2
        PY_RESUME = 4
        PY_YIELD = 8
        PY_UNWIND = 16
        LINE = 32

    class UnavailableMonitoring:
        events = Events()

        @staticmethod
        def use_tool_id(*args):
            raise ValueError("occupied")

    monkeypatch.setattr(sys, "monitoring", UnavailableMonitoring())
    plugin = RuntimeEvidencePlugin(tmp_path / "evidence", frozenset())
    assert sys.getprofile() is not previous
    hook = SimpleNamespace(get_hookimpls=lambda: [])
    plugin.pytest_sessionfinish(
        SimpleNamespace(
            config=SimpleNamespace(hook=SimpleNamespace(pytest_sessionfinish=hook))
        ),
        0,
    )
    assert sys.getprofile() is previous
    sys.setprofile(None)


def test_monitoring_success_and_post_claim_failure_preserve_tool_ownership(
    tmp_path, monkeypatch
):
    import sys
    from types import SimpleNamespace

    from maid_runner.core._runtime_evidence_pytest_plugin import RuntimeEvidencePlugin

    class Events:
        PY_START = 1
        PY_RETURN = 2
        PY_RESUME = 4
        PY_YIELD = 8
        PY_UNWIND = 16
        LINE = 32

    class FakeMonitoring:
        events = Events()

        def __init__(self, *, fail_registration=False, fail_set_events=False):
            self.fail_registration = fail_registration
            self.fail_set_events = fail_set_events
            self.claimed = []
            self.registered = []
            self.event_sets = []
            self.local_event_sets = []
            self.freed = []
            self.actions = []

        def use_tool_id(self, tool_id, name):
            assert tool_id != 5  # unrelated/pre-owned slot
            self.claimed.append(tool_id)
            self.actions.append(("claim", tool_id))

        def register_callback(self, tool_id, event, callback):
            if self.fail_registration and callback is not None:
                raise RuntimeError("registration failed")
            self.registered.append((tool_id, event, callback))
            self.actions.append(("callback", tool_id, event, callback))

        def set_events(self, tool_id, events):
            if self.fail_set_events and events:
                raise RuntimeError("set events failed")
            self.event_sets.append((tool_id, events))
            self.actions.append(("events", tool_id, events))

        def set_local_events(self, tool_id, code, events):
            self.local_event_sets.append((tool_id, code, events))
            self.actions.append(("local-events", tool_id, code, events))

        def free_tool_id(self, tool_id):
            self.freed.append(tool_id)
            self.actions.append(("free", tool_id))

    hook = SimpleNamespace(get_hookimpls=lambda: [])
    session = SimpleNamespace(
        config=SimpleNamespace(hook=SimpleNamespace(pytest_sessionfinish=hook))
    )

    def previous(*args):
        return None

    sys.setprofile(previous)

    successful = FakeMonitoring()
    monkeypatch.setattr(sys, "monitoring", successful)
    plugin = RuntimeEvidencePlugin(tmp_path / "success", frozenset())
    assert sys.getprofile() is previous
    required = {1, 2, 4, 8, 16, 32}
    assert {
        event for _, event, callback in successful.registered if callback
    } == required
    plugin.pytest_sessionfinish(session, 0)
    claimed_id = successful.claimed[0]
    assert successful.event_sets[-1] == (claimed_id, 0)
    assert {
        event
        for tool_id, event, callback in successful.registered
        if tool_id == claimed_id and callback is None
    } == required
    assert successful.actions[-1] == ("free", claimed_id)
    assert successful.freed == successful.claimed
    assert 5 not in successful.freed
    assert sys.getprofile() is previous

    failing = FakeMonitoring(fail_registration=True)
    monkeypatch.setattr(sys, "monitoring", failing)
    fallback = RuntimeEvidencePlugin(tmp_path / "fallback", frozenset())
    assert failing.freed == failing.claimed
    assert sys.getprofile() is not previous
    fallback.pytest_sessionfinish(session, 0)
    assert sys.getprofile() is previous

    set_events_failure = FakeMonitoring(fail_set_events=True)
    monkeypatch.setattr(sys, "monitoring", set_events_failure)
    fallback = RuntimeEvidencePlugin(tmp_path / "set-events-fallback", frozenset())
    failed_id = set_events_failure.claimed[0]
    assert set_events_failure.event_sets[-1] == (failed_id, 0)
    assert {
        event
        for tool_id, event, callback in set_events_failure.registered
        if tool_id == failed_id and callback is None
    } == required
    assert set_events_failure.actions[-1] == ("free", failed_id)
    assert set_events_failure.freed == [failed_id]
    assert sys.getprofile() is not previous
    fallback.pytest_sessionfinish(session, 0)
    assert sys.getprofile() is previous

    no_local = FakeMonitoring()
    no_local.set_local_events = None
    monkeypatch.setattr(sys, "monitoring", no_local)
    unavailable = RuntimeEvidencePlugin(tmp_path / "no-local", frozenset())
    assert no_local.claimed == []
    assert sys.getprofile() is not previous
    unavailable.pytest_sessionfinish(session, 0)
    assert sys.getprofile() is previous

    missing = FakeMonitoring()
    missing.events = SimpleNamespace(PY_START=1, PY_RETURN=2)
    monkeypatch.setattr(sys, "monitoring", missing)
    unavailable = RuntimeEvidencePlugin(tmp_path / "missing", frozenset())
    assert missing.claimed == []
    assert sys.getprofile() is not previous
    unavailable.pytest_sessionfinish(session, 0)
    assert sys.getprofile() is previous
    sys.setprofile(None)


def test_runtime_evidence_plugin_executes_declared_hook_lifecycles(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from maid_runner.core._runtime_evidence_pytest_plugin import RuntimeEvidencePlugin

    plugin = RuntimeEvidencePlugin(
        tmp_path / "hook-evidence.json",
        frozenset(),
        expected_workers=1,
    )
    node = SimpleNamespace(
        nodeid="tests/test_sample.py::test_ok",
        _fixtureinfo=SimpleNamespace(names_closure=("sample",)),
    )
    fixturedef = SimpleNamespace(
        argname="sample",
        scope="function",
        baseid="tests/test_sample.py",
        func=lambda: None,
    )
    request = SimpleNamespace(
        node=node,
        _fixturemanager=SimpleNamespace(_getautousenames=lambda item: ()),
    )
    session_hook = SimpleNamespace(get_hookimpls=lambda: [])
    session = SimpleNamespace(
        config=SimpleNamespace(
            hook=SimpleNamespace(pytest_sessionfinish=session_hook),
        )
    )

    try:
        setup = plugin.pytest_fixture_setup(fixturedef, request)
        next(setup)
        with pytest.raises(StopIteration):
            next(setup)

        teardown = plugin.pytest_runtest_teardown(node, None)
        next(teardown)
        with pytest.raises(StopIteration):
            next(teardown)

        plugin.pytest_fixture_post_finalizer(fixturedef, request)
        plugin.pytest_runtest_logreport(
            SimpleNamespace(
                nodeid=node.nodeid,
                when="call",
                outcome="passed",
            )
        )
        monkeypatch.setenv("MAID_RUNTIME_EVIDENCE_OUTPUT", "private")
        plugin.pytest_configure_node(SimpleNamespace())

        assert "MAID_RUNTIME_EVIDENCE_OUTPUT" not in os.environ
        assert plugin.completeness.complete is True
    finally:
        plugin.pytest_sessionfinish(session, 0)


def _complete(*, complete: bool = True, **overrides):
    from maid_runner.core.runtime_evidence import RuntimeEvidenceCompleteness

    values = {
        "complete": complete,
        "missing_worker_ids": (),
        "unsupported_selectors": (),
        "unresolved_context_ids": (),
        "unproven_fixture_lifecycles": (),
        "diagnostics": (),
    }
    values.update(overrides)
    return RuntimeEvidenceCompleteness(**values)


def _context(
    context_id: str,
    nodeids: tuple[str, ...],
    *,
    kind: str = "node",
    fixture_scope: str | None = None,
    autouse: bool = False,
    lifecycle_equivalent: bool = True,
):
    from maid_runner.core._runtime_command_executor import RuntimeFileExecution
    from maid_runner.core.runtime_evidence import RuntimeContextEvidence

    return RuntimeContextEvidence(
        context_id=context_id,
        kind=kind,
        consuming_nodeids=nodeids,
        execution_data=MappingProxyType(
            {
                "/project/src/target.py": RuntimeFileExecution(
                    executed_lines=frozenset({1, 2}),
                    called_qualnames=frozenset({"target"}),
                )
            }
        ),
        fixture_scope=fixture_scope,
        autouse=autouse,
        lifecycle_equivalent=lifecycle_equivalent,
    )


def _group(
    command,
    selectors,
    contexts=(),
    *,
    completeness=None,
    workers=("main",),
):
    from maid_runner.core._runtime_command_executor import RuntimeCommandRecord
    from maid_runner.core.runtime_evidence import RuntimeGroupEvidence

    selected = tuple(
        dict.fromkeys(node for nodes in selectors.values() for node in nodes)
    )
    return RuntimeGroupEvidence(
        command=tuple(command),
        selected_nodeids=selected,
        selector_nodeids=MappingProxyType(dict(selectors)),
        contexts=tuple(contexts),
        result=RuntimeCommandRecord(
            command=tuple(command),
            returncode=0,
            stdout="2 passed",
            stderr="",
            execution_data={},
            report_errors=(),
        ),
        worker_ids=workers,
        completeness=completeness or _complete(),
    )


class _GroupExecutor:
    def __init__(self, factory):
        self.factory = factory
        self.calls = []

    def execute_with_contexts(
        self,
        command,
        target_files,
        project_root,
        timeout_seconds,
        pytest_workers=None,
    ):
        self.calls.append(
            (
                tuple(command),
                frozenset(target_files),
                Path(project_root),
                timeout_seconds,
                pytest_workers,
            )
        )
        return self.factory(tuple(command))


def test_compatible_commands_execute_once_with_exact_command_identities(tmp_path):
    from maid_runner.core.runtime_evidence import (
        RuntimeCommandEvidence,
        RuntimeCommandIdentity,
        RuntimeEnvironmentIdentity,
        RuntimeEvidenceBundle,
        RuntimeEvidenceRun,
        collect_runtime_evidence,
    )

    _project(tmp_path)
    manifests = [
        load_manifest(
            _write_manifest(
                tmp_path,
                "alpha",
                "uv run python -m pytest -q tests/test_alpha.py",
            )
        ),
        load_manifest(
            _write_manifest(
                tmp_path,
                "beta",
                "uv run python -m pytest -q tests/test_beta.py",
            )
        ),
    ]
    selectors = {
        "tests/test_alpha.py": ("tests/test_alpha.py::test_alpha",),
        "tests/test_beta.py": ("tests/test_beta.py::test_beta",),
    }
    executor = _GroupExecutor(
        lambda command: _group(
            command,
            selectors,
            contexts=(
                _context("node:alpha", selectors["tests/test_alpha.py"]),
                _context("node:beta", selectors["tests/test_beta.py"]),
            ),
        )
    )

    run = collect_runtime_evidence(
        manifests, tmp_path, executor=executor, pytest_workers=8
    )

    assert isinstance(run, RuntimeEvidenceRun)
    assert isinstance(run.evidence, RuntimeEvidenceBundle)
    assert all(
        isinstance(identity, RuntimeEnvironmentIdentity)
        for identity in run.evidence.environment_identities
    )
    assert all(
        command.environment_identity in run.evidence.environment_identities
        for command in run.evidence.commands
    )
    assert len(run.evidence.content_digest) == 64
    assert all(
        isinstance(item, RuntimeCommandIdentity) for item in run.executed_identities
    )
    assert all(
        isinstance(item, RuntimeCommandEvidence) for item in run.evidence.commands
    )
    assert all(item.behavior_group_key[0] == "pytest" for item in run.evidence.commands)
    assert len(executor.calls) == 1
    assert executor.calls[0][0] == (
        "uv",
        "run",
        "python",
        "-m",
        "pytest",
        "tests/test_alpha.py",
        "tests/test_beta.py",
        "-q",
    )
    assert executor.calls[0][-1] == 8
    assert [
        (item.manifest_path, item.command_index, item.command)
        for item in run.executed_identities
    ] == [
        (
            manifests[0].source_path,
            0,
            tuple(manifests[0].validate_commands[0]),
        ),
        (
            manifests[1].source_path,
            0,
            tuple(manifests[1].validate_commands[0]),
        ),
    ]
    assert [item.selected_nodeids for item in run.evidence.commands] == [
        selectors["tests/test_alpha.py"],
        selectors["tests/test_beta.py"],
    ]
    assert run.test_result.total == 1
    assert run.test_result.passed == 1


def test_unrelated_node_context_is_not_attributed_to_manifest_command(tmp_path):
    from maid_runner.core.runtime_evidence import collect_runtime_evidence

    _project(tmp_path)
    manifest = load_manifest(
        _write_manifest(tmp_path, "alpha", "pytest -q tests/test_alpha.py")
    )
    selected = ("tests/test_alpha.py::test_alpha",)
    executor = _GroupExecutor(
        lambda command: _group(
            command,
            {"tests/test_alpha.py": selected},
            contexts=(
                _context("selected", selected),
                _context("ambient", ("tests/test_beta.py::test_beta",)),
            ),
        )
    )

    evidence = collect_runtime_evidence([manifest], tmp_path, executor=executor)

    assert [
        context.context_id for context in evidence.evidence.commands[0].contexts
    ] == ["selected"]


def test_stateful_session_and_module_yield_fixture_setup_teardown_force_exact_fallback(
    tmp_path,
):
    from maid_runner.core.runtime_evidence import collect_runtime_evidence

    _project(tmp_path)
    (tmp_path / "conftest.py").write_text(
        "from pathlib import Path\n"
        "import pytest\n\n"
        "@pytest.fixture(scope='session', autouse=True)\n"
        "def shared_state():\n"
        "    events = Path('fixture-events.txt')\n"
        "    events.write_text('setup\\n')\n"
        "    yield\n"
        "    events.write_text(events.read_text() + 'teardown\\n')\n"
        "\n@pytest.fixture(scope='module', autouse=True)\n"
        "def module_state():\n"
        "    events = Path('fixture-events.txt')\n"
        "    events.write_text(events.read_text() + 'module-setup\\n')\n"
        "    yield\n"
        "    events.write_text(events.read_text() + 'module-teardown\\n')\n"
    )
    manifests = [
        load_manifest(_write_manifest(tmp_path, name, f"pytest tests/test_{name}.py"))
        for name in ("alpha", "beta")
    ]

    run = collect_runtime_evidence(manifests, tmp_path)

    events = (tmp_path / "fixture-events.txt").read_text().splitlines()
    assert events.count("setup") == 1
    assert events.count("teardown") == 1
    assert events.count("module-setup") == 2
    assert events.count("module-teardown") == 2
    assert all(not item.completeness.complete for item in run.evidence.commands)
    assert all(
        any(
            "shared_state" in item
            for item in command.completeness.unproven_fixture_lifecycles
        )
        for command in run.evidence.commands
    )
    conftest_path = str((tmp_path / "conftest.py").resolve())
    lines = (tmp_path / "conftest.py").read_text().splitlines()
    expected_teardowns = {
        "shared_state": next(
            index
            for index, line in enumerate(lines, start=1)
            if "teardown\\n" in line and "module-teardown" not in line
        ),
        "module_state": next(
            index
            for index, line in enumerate(lines, start=1)
            if "module-teardown" in line
        ),
    }
    for command in run.evidence.commands:
        for fixture_name, teardown_line in expected_teardowns.items():
            fixture = next(
                context
                for context in command.contexts
                if context.kind == "fixture" and fixture_name in context.context_id
            )
            execution = fixture.execution_data[conftest_path]
            assert teardown_line in execution.executed_lines
            assert fixture_name in execution.called_qualnames
    target_path = str((tmp_path / "src" / "target.py").resolve())
    assert all(
        any(
            context.kind == "node"
            and target_path in context.execution_data
            and context.execution_data[target_path].executed_lines
            and "target" in context.execution_data[target_path].called_qualnames
            for context in command.contexts
        )
        for command in run.evidence.commands
    )
    assert all(
        any(
            "module_state" in item
            for item in command.completeness.unproven_fixture_lifecycles
        )
        for command in run.evidence.commands
    )
    assert all(
        any(
            context.kind == "fixture"
            and context.fixture_scope == "session"
            and context.autouse
            and not context.lifecycle_equivalent
            for context in command.contexts
        )
        for command in run.evidence.commands
    )


def test_function_yield_fixture_setup_and_teardown_are_attributed_per_node(tmp_path):
    from maid_runner.core.runtime_evidence import collect_runtime_evidence

    _project(tmp_path)
    conftest = tmp_path / "conftest.py"
    conftest.write_text(
        "from pathlib import Path\n"
        "import pytest\n\n"
        "@pytest.fixture\n"
        "def per_node(request):\n"
        "    events = Path('fixture-events.txt')\n"
        "    before = events.read_text() if events.exists() else ''\n"
        "    events.write_text(before + 'setup:' + request.node.nodeid + '\\n')\n"
        "    yield\n"
        "    events.write_text(events.read_text() + 'teardown:' + request.node.nodeid + '\\n')\n"
    )
    for name in ("alpha", "beta"):
        (tmp_path / "tests" / f"test_{name}.py").write_text(
            "from src.target import target\n\n"
            f"def test_{name}(per_node):\n"
            "    assert target() is True\n"
        )
    manifests = [
        load_manifest(_write_manifest(tmp_path, name, f"pytest tests/test_{name}.py"))
        for name in ("alpha", "beta")
    ]

    run = collect_runtime_evidence(manifests, tmp_path)

    events = (tmp_path / "fixture-events.txt").read_text().splitlines()
    assert sorted(event.split(":", 1)[0] for event in events) == [
        "setup",
        "setup",
        "teardown",
        "teardown",
    ]
    assert all(
        command.completeness.unproven_fixture_lifecycles == ()
        for command in run.evidence.commands
    )
    conftest_path = str(conftest.resolve())
    teardown_line = next(
        index
        for index, line in enumerate(conftest.read_text().splitlines(), start=1)
        if "teardown:" in line
    )
    for command in run.evidence.commands:
        fixture = next(
            context
            for context in command.contexts
            if context.kind == "fixture" and "per_node" in context.context_id
        )
        execution = fixture.execution_data[conftest_path]
        assert teardown_line in execution.executed_lines
        assert "per_node" in execution.called_qualnames
    assert all(
        any(
            context.kind == "fixture"
            and context.fixture_scope == "function"
            and not context.autouse
            and context.lifecycle_equivalent
            and context.consuming_nodeids == command.selected_nodeids
            for context in command.contexts
        )
        for command in run.evidence.commands
    )


def test_dynamic_fixture_without_proven_closure_is_incomplete(tmp_path):
    from maid_runner.core.runtime_evidence import collect_runtime_evidence

    _project(tmp_path)
    manifest = load_manifest(
        _write_manifest(tmp_path, "alpha", "pytest tests/test_alpha.py")
    )
    executor = _GroupExecutor(
        lambda command: _group(
            command,
            {"tests/test_alpha.py": ("tests/test_alpha.py::test_alpha",)},
            completeness=_complete(
                complete=False,
                unsupported_selectors=("tests/[invalid",),
                unresolved_context_ids=("fixture:dynamic",),
            ),
        )
    )

    run = collect_runtime_evidence([manifest], tmp_path, executor=executor)

    assert run.evidence.commands[0].completeness.complete is False
    assert run.evidence.completeness.unsupported_selectors == ("tests/[invalid",)
    assert run.evidence.commands[0].completeness.unresolved_context_ids == (
        "fixture:dynamic",
    )


def test_collection_import_context_is_recorded_or_marked_for_fallback(tmp_path):
    from maid_runner.core.runtime_evidence import collect_runtime_evidence

    _project(tmp_path)
    manifest = load_manifest(
        _write_manifest(tmp_path, "alpha", "pytest tests/test_alpha.py")
    )
    node = ("tests/test_alpha.py::test_alpha",)
    collection = _context(
        "collection:tests/test_alpha.py",
        node,
        kind="collection",
        lifecycle_equivalent=False,
    )
    executor = _GroupExecutor(
        lambda command: _group(
            command,
            {"tests/test_alpha.py": node},
            contexts=(collection,),
        )
    )

    attributed = collect_runtime_evidence([manifest], tmp_path, executor=executor)

    assert attributed.evidence.commands[0].contexts == (collection,)

    unresolved_executor = _GroupExecutor(
        lambda command: _group(
            command,
            {"tests/test_alpha.py": node},
            completeness=_complete(
                complete=False,
                unresolved_context_ids=("collection:ambient",),
            ),
        )
    )
    unresolved = collect_runtime_evidence(
        [manifest], tmp_path, executor=unresolved_executor
    )
    assert unresolved.evidence.commands[0].completeness.complete is False


def test_overlapping_directory_file_and_node_selectors_map_exactly(tmp_path):
    from maid_runner.core.runtime_evidence import collect_runtime_evidence

    _project(tmp_path)
    commands = (
        "pytest tests",
        "pytest tests/test_alpha.py",
        "pytest tests/test_alpha.py::test_alpha",
    )
    manifests = [
        load_manifest(_write_manifest(tmp_path, f"selector-{index}", command))
        for index, command in enumerate(commands)
    ]
    alpha = "tests/test_alpha.py::test_alpha"
    beta = "tests/test_beta.py::test_beta"
    executor = _GroupExecutor(
        lambda command: _group(
            command,
            {
                "tests": (alpha, beta),
                "tests/test_alpha.py": (alpha,),
                "tests/test_alpha.py::test_alpha": (alpha,),
            },
            contexts=(
                _context("alpha", (alpha,)),
                _context("beta", (beta,)),
            ),
        )
    )

    run = collect_runtime_evidence(manifests, tmp_path, executor=executor)

    assert [command.selected_nodeids for command in run.evidence.commands] == [
        (alpha, beta),
        (alpha,),
        (alpha,),
    ]
    assert [
        tuple(c.context_id for c in command.contexts)
        for command in run.evidence.commands
    ] == [
        ("alpha", "beta"),
        ("alpha",),
        ("alpha",),
    ]


def test_behavior_changing_options_remain_separate_runs(tmp_path):
    from maid_runner.core.runtime_evidence import collect_runtime_evidence

    _project(tmp_path)
    manifests = [
        load_manifest(
            _write_manifest(
                tmp_path,
                name,
                f"pytest tests -k {name}",
            )
        )
        for name in ("alpha", "beta")
    ]
    executor = _GroupExecutor(
        lambda command: _group(
            command,
            {
                "tests": tuple(
                    f"tests/test_{name}.py::test_{name}"
                    for name in ("alpha", "beta")
                    if name in command
                )
            },
        )
    )

    run = collect_runtime_evidence(manifests, tmp_path, executor=executor)

    assert len(executor.calls) == 2
    assert len(run.test_result.results) == 2


def test_line_and_call_contexts_survive_worker_combine(tmp_path):
    from maid_runner.core._runtime_command_executor import RuntimeFileExecution
    from maid_runner.core.runtime_evidence import (
        RuntimeContextEvidence,
        combine_runtime_contexts,
    )

    first = _context("node:a", ("tests/test_alpha.py::test_alpha",))
    second = RuntimeContextEvidence(
        context_id=first.context_id,
        kind="node",
        consuming_nodeids=first.consuming_nodeids,
        execution_data={
            "/project/src/target.py": RuntimeFileExecution(
                executed_lines=frozenset({3}),
                called_qualnames=frozenset({"Target.method"}),
            )
        },
        fixture_scope=None,
        autouse=False,
        lifecycle_equivalent=True,
    )

    combined = combine_runtime_contexts((first, second))

    execution = combined.execution_data["/project/src/target.py"]
    assert execution.executed_lines == frozenset({1, 2, 3})
    assert execution.called_qualnames == frozenset({"target", "Target.method"})


def test_worker_loss_marks_bundle_incomplete(tmp_path):
    from maid_runner.core.runtime_evidence import collect_runtime_evidence

    _project(tmp_path)
    manifest = load_manifest(
        _write_manifest(tmp_path, "alpha", "pytest tests/test_alpha.py")
    )
    executor = _GroupExecutor(
        lambda command: _group(
            command,
            {"tests/test_alpha.py": ("tests/test_alpha.py::test_alpha",)},
            completeness=_complete(
                complete=False,
                missing_worker_ids=("gw1",),
                diagnostics=(
                    ValidationError(
                        code=ErrorCode.INTERNAL_ERROR,
                        message="runtime evidence worker gw1 was lost",
                    ),
                ),
            ),
            workers=("gw0",),
        )
    )

    run = collect_runtime_evidence([manifest], tmp_path, executor=executor)

    assert run.evidence.worker_ids == ("gw0",)
    assert run.evidence.completeness.complete is False
    assert run.evidence.completeness.missing_worker_ids == ("gw1",)
    assert run.evidence.completeness.diagnostics[0].code == ErrorCode.INTERNAL_ERROR


def test_content_change_rejects_in_memory_bundle(tmp_path):
    from maid_runner.core.runtime_evidence import (
        collect_runtime_evidence,
        runtime_evidence_is_current,
    )

    _project(tmp_path)
    manifest = load_manifest(
        _write_manifest(tmp_path, "alpha", "pytest tests/test_alpha.py")
    )
    executor = _GroupExecutor(
        lambda command: _group(
            command,
            {"tests/test_alpha.py": ("tests/test_alpha.py::test_alpha",)},
        )
    )
    bundle = collect_runtime_evidence([manifest], tmp_path, executor=executor).evidence
    assert runtime_evidence_is_current(bundle, [manifest], tmp_path) is True

    (tmp_path / "tests" / "fixture.json").write_text('{"changed": true}\n')

    assert runtime_evidence_is_current(bundle, [manifest], tmp_path) is False


def test_resolved_runner_config_dependency_or_environment_change_rejects_bundle(
    monkeypatch, tmp_path
):
    from maid_runner.core.runtime_evidence import (
        collect_runtime_evidence,
        runtime_evidence_is_current,
    )

    _project(tmp_path)
    manifest = load_manifest(
        _write_manifest(tmp_path, "alpha", "pytest tests/test_alpha.py")
    )
    executor = _GroupExecutor(
        lambda command: _group(
            command,
            {"tests/test_alpha.py": ("tests/test_alpha.py::test_alpha",)},
        )
    )
    monkeypatch.setenv("RUNTIME_EVIDENCE_TOKEN", "first")
    bundle = collect_runtime_evidence([manifest], tmp_path, executor=executor).evidence

    monkeypatch.setenv("RUNTIME_EVIDENCE_TOKEN", "second")
    assert runtime_evidence_is_current(bundle, [manifest], tmp_path) is False
    monkeypatch.setenv("RUNTIME_EVIDENCE_TOKEN", "first")
    (tmp_path / "pyproject.toml").write_text(
        "[tool.pytest.ini_options]\naddopts='-x'\n"
    )
    assert runtime_evidence_is_current(bundle, [manifest], tmp_path) is False


def test_environment_identity_stores_digests_without_raw_secret_values(
    monkeypatch, tmp_path
):
    from maid_runner.core.runtime_evidence import collect_runtime_evidence

    _project(tmp_path)
    manifest = load_manifest(
        _write_manifest(tmp_path, "alpha", "pytest tests/test_alpha.py")
    )
    secret = "do-not-persist-this-secret"
    monkeypatch.setenv("RUNTIME_EVIDENCE_SECRET", secret)
    executor = _GroupExecutor(
        lambda command: _group(
            command,
            {"tests/test_alpha.py": ("tests/test_alpha.py::test_alpha",)},
        )
    )

    identity = collect_runtime_evidence(
        [manifest], tmp_path, executor=executor
    ).evidence.environment_identities[0]

    payload = json.dumps(identity.__dict__, default=list, sort_keys=True)
    assert secret not in payload
    assert len(identity.effective_environment_digest) == 64
    assert identity.resolved_command_prefix
    assert identity.working_directory == str(tmp_path.resolve())
    assert identity.python_identity
    assert identity.pytest_version
    assert identity.coverage_version
    assert identity.configuration_digest
    assert identity.dependency_digest
    assert identity.xdist_version is None or isinstance(identity.xdist_version, str)


def test_resolved_version_probe_retries_failures_before_caching(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    from maid_runner.core import runtime_evidence

    calls = []

    def fake_run(*args, **kwargs):
        calls.append((args, kwargs))
        if len(calls) == 1:
            return SimpleNamespace(returncode=1, stdout="")
        return SimpleNamespace(
            returncode=0,
            stdout=json.dumps(
                {
                    "python": "python-ok",
                    "pytest": "pytest-ok",
                    "coverage": "coverage-ok",
                    "xdist": None,
                }
            ),
        )

    runtime_evidence._RESOLVED_VERSION_CACHE.clear()
    monkeypatch.setattr(runtime_evidence.subprocess, "run", fake_run)

    first = runtime_evidence._probe_resolved_versions(
        ("python", "-m", "pytest"),
        tmp_path,
    )
    second = runtime_evidence._probe_resolved_versions(
        ("python", "-m", "pytest"),
        tmp_path,
    )
    third = runtime_evidence._probe_resolved_versions(
        ("python", "-m", "pytest"),
        tmp_path,
    )

    assert first["python"] == "unavailable"
    assert second["python"] == "python-ok"
    assert third["python"] == "python-ok"
    assert len(calls) == 2


def test_runtime_collection_result_matches_ordinary_group_result(tmp_path):
    from maid_runner.core._runtime_command_executor import (
        RuntimeCommandExecutor,
        SubprocessRuntimeCommandExecutor,
    )
    from maid_runner.core._test_command_execution import _run_test_command
    from maid_runner.core.runtime_evidence import collect_runtime_evidence

    assert callable(RuntimeCommandExecutor.execute_with_contexts)
    assert callable(SubprocessRuntimeCommandExecutor.execute_with_contexts)

    _project(tmp_path)
    (tmp_path / "tests" / "test_alpha.py").write_text(
        "def test_alpha():\n    assert True\n"
    )
    manifest = load_manifest(
        _write_manifest(tmp_path, "alpha", "python -m pytest -q tests/test_alpha.py")
    )
    ordinary = _run_test_command(
        tuple(manifest.validate_commands[0]), cwd=tmp_path, timeout=30
    )

    run = collect_runtime_evidence([manifest], tmp_path)

    assert ordinary.success is True
    assert run.test_result.success is ordinary.success
    assert run.test_result.results[0].exit_code == ordinary.exit_code
    assert run.test_result.results[0].command == run.evidence.commands[0].result.command
    assert (
        run.test_result.results[0].exit_code
        == run.evidence.commands[0].result.returncode
    )
    (tmp_path / "tests" / "test_alpha.py").write_text(
        "from package_that_does_not_exist import value\n"
    )
    failing_ordinary = _run_test_command(
        tuple(manifest.validate_commands[0]), cwd=tmp_path, timeout=30
    )
    failing_runtime = collect_runtime_evidence([manifest], tmp_path)

    assert failing_ordinary.success is False
    assert failing_runtime.test_result.success is failing_ordinary.success
    assert (
        failing_runtime.test_result.results[0].exit_code == failing_ordinary.exit_code
    )


def test_plugin_preserves_consumer_plugins_and_does_not_leak_context_to_nested_pytest(
    monkeypatch, tmp_path
):
    from maid_runner.core._runtime_evidence_pytest_plugin import (
        RuntimeEvidencePlugin,
        pytest_addoption,
        pytest_configure,
    )

    output = tmp_path / "evidence.json"
    monkeypatch.setenv(
        "PYTEST_PLUGINS", "consumer_required_plugin,_maid_runtime_evidence_plugin"
    )
    monkeypatch.setenv("MAID_RUNTIME_EVIDENCE_OUTPUT", str(output))
    target_file = str(Path(__file__).resolve())
    monkeypatch.setenv("MAID_RUNTIME_TARGET_FILES", json.dumps([target_file]))
    registered = []
    added_options = []

    class Parser:
        def getgroup(self, name):
            assert name == "maid-runtime-evidence"
            return self

        def addoption(self, name, **kwargs):
            added_options.append(name)

    pytest_addoption(Parser())
    assert added_options == [
        "--maid-runtime-evidence-output",
        "--maid-runtime-target-files",
    ]
    options = {
        "--maid-runtime-evidence-output": None,
        "--maid-runtime-target-files": None,
    }
    config = SimpleNamespace(
        getoption=lambda name: options[name],
        pluginmanager=SimpleNamespace(
            register=lambda plugin, name: registered.append((plugin, name))
        ),
    )

    pytest_configure(config)

    assert isinstance(registered[0][0], RuntimeEvidencePlugin)
    assert os.environ["PYTEST_PLUGINS"] == "consumer_required_plugin"
    assert "MAID_RUNTIME_EVIDENCE_OUTPUT" not in os.environ
    assert "MAID_RUNTIME_TARGET_FILES" not in os.environ
    plugin = registered[0][0]
    assert plugin.output_path == output
    assert plugin.target_files == frozenset({target_file})
    assert isinstance(plugin.contexts, dict)
    from maid_runner.core.runtime_evidence import (
        RuntimeContextEvidence,
        RuntimeEvidenceCompleteness,
    )

    plugin.pytest_runtest_setup(SimpleNamespace(nodeid="tests/test_sample.py::test_ok"))
    assert all(
        isinstance(context, RuntimeContextEvidence)
        for context in plugin.contexts.values()
    )
    assert isinstance(plugin.completeness, RuntimeEvidenceCompleteness)
    assert plugin.completeness.complete is True
    assert callable(plugin.pytest_collection_modifyitems)
    assert callable(plugin.pytest_fixture_setup)
    assert callable(plugin.pytest_runtest_setup)
    assert callable(plugin.pytest_runtest_teardown)
    assert callable(plugin.pytest_fixture_post_finalizer)
    assert callable(plugin.pytest_runtest_logreport)
    assert callable(plugin.pytest_testnodedown)
    assert callable(plugin.pytest_configure_node)
    assert callable(plugin.pytest_sessionfinish)
    plugin.pytest_testnodedown(
        SimpleNamespace(gateway=SimpleNamespace(id="gw1")), "lost"
    )
    assert plugin.completeness.complete is False
    assert plugin.completeness.missing_worker_ids == ("gw1",)
    plugin.pytest_sessionfinish(SimpleNamespace(), 0)
    monkeypatch.delenv("PYTEST_PLUGINS")

    nested_root = tmp_path / "nested-project"
    nested_root.mkdir()
    _project(nested_root)
    nested_tests = nested_root / "nested"
    nested_tests.mkdir()
    (nested_tests / "test_nested.py").write_text(
        "from src.target import target\n\n"
        "def test_nested():\n"
        "    assert target() is True\n"
    )
    (nested_root / "tests" / "test_alpha.py").write_text(
        "import pytest\n\n"
        "def test_alpha():\n"
        "    assert pytest.main(['nested/test_nested.py', '-q']) == 0\n"
    )
    manifest = load_manifest(
        _write_manifest(
            nested_root,
            "alpha",
            "pytest tests/test_alpha.py",
        )
    )

    nested_run = __import__(
        "maid_runner.core.runtime_evidence", fromlist=["collect_runtime_evidence"]
    ).collect_runtime_evidence([manifest], nested_root)

    assert nested_run.evidence.completeness.complete is False
    assert any(
        value.startswith("nested-pytest:")
        for value in nested_run.evidence.completeness.unresolved_context_ids
    ), nested_run.evidence.completeness


def test_xdist_requires_every_expected_worker_payload_and_projects_nodes(tmp_path):
    from maid_runner.core.runtime_evidence import collect_runtime_evidence

    _project(tmp_path)
    manifest = load_manifest(
        _write_manifest(
            tmp_path,
            "xdist",
            "python -m pytest -n 2 --dist loadscope tests",
        )
    )

    complete = collect_runtime_evidence([manifest], tmp_path)

    assert complete.test_result.success, (
        complete.test_result.results[0].stdout + complete.test_result.results[0].stderr
    )
    assert complete.evidence.worker_ids == ("gw0", "gw1")
    assert complete.evidence.commands[0].selected_nodeids == (
        "tests/test_alpha.py::test_alpha",
        "tests/test_beta.py::test_beta",
    ), (
        complete.test_result.results[0].stdout,
        complete.test_result.results[0].stderr,
        complete.evidence,
    )
    assert complete.evidence.completeness.missing_worker_ids == ()
    assert complete.evidence.completeness.complete is True
    assert not any(
        value.startswith("report:")
        for value in complete.evidence.completeness.unresolved_context_ids
    )

    (tmp_path / "conftest.py").write_text(
        "import os\n"
        "import pytest\n\n"
        "@pytest.hookimpl(trylast=True)\n"
        "def pytest_sessionfinish(session, exitstatus):\n"
        "    if os.environ.get('PYTEST_XDIST_WORKER') != 'gw1':\n"
        "        return\n"
        "    plugin = session.config.pluginmanager.getplugin('maid-runtime-evidence-plugin')\n"
        "    (plugin.output_path / 'evidence-gw1.json').unlink(missing_ok=True)\n"
    )

    missing = collect_runtime_evidence([manifest], tmp_path)

    assert missing.evidence.completeness.complete is False
    assert missing.evidence.completeness.missing_worker_ids == ("gw1",)


def test_xdist_retains_logical_selectors_after_physical_collapse(tmp_path):
    from maid_runner.core.runtime_evidence import collect_runtime_evidence

    _project(tmp_path)
    for name in ("alpha", "beta"):
        (tmp_path / "tests" / f"test_{name}.py").write_text(
            f"def test_{name}():\n"
            "    from src.target import target\n"
            "    assert target() is True\n"
        )
    manifests = [
        load_manifest(_write_manifest(tmp_path, "all", "python -m pytest tests/")),
        load_manifest(
            _write_manifest(tmp_path, "beta", "python -m pytest tests/test_beta.py")
        ),
    ]

    run = collect_runtime_evidence(manifests, tmp_path, pytest_workers=2)

    assert run.test_result.success
    assert run.evidence.completeness.unsupported_selectors == ()
    assert [command.selected_nodeids for command in run.evidence.commands] == [
        (
            "tests/test_alpha.py::test_alpha",
            "tests/test_beta.py::test_beta",
        ),
        ("tests/test_beta.py::test_beta",),
    ]


def test_xdist_merges_disjoint_worker_selector_maps_before_support_decision(tmp_path):
    from maid_runner.core._runtime_command_executor import (
        SubprocessRuntimeCommandExecutor,
    )

    _project(tmp_path)
    (tmp_path / "conftest.py").write_text(
        "import json\n"
        "import os\n"
        "import pytest\n\n"
        "@pytest.hookimpl(trylast=True)\n"
        "def pytest_sessionfinish(session, exitstatus):\n"
        "    worker = os.environ.get('PYTEST_XDIST_WORKER')\n"
        "    if worker not in {'gw0', 'gw1'}:\n"
        "        return\n"
        "    plugin = session.config.pluginmanager.getplugin('maid-runtime-evidence-plugin')\n"
        "    if plugin is None:\n"
        "        return\n"
        "    path = plugin.output_path / ('evidence-' + worker + '.json')\n"
        "    payload = json.loads(path.read_text())\n"
        "    alpha = 'tests/test_alpha.py::test_alpha'\n"
        "    beta = 'tests/test_beta.py::test_beta'\n"
        "    missing = 'tests/test_alpha.py::missing_node'\n"
        "    payload['selector_nodeids'] = {\n"
        "        'tests/test_alpha.py': [alpha] if worker == 'gw0' else [],\n"
        "        'tests/test_beta.py': [beta] if worker == 'gw1' else [],\n"
        "        missing: [],\n"
        "    }\n"
        "    payload['completeness']['unsupported_selectors'] = (\n"
        "        ['tests/test_beta.py', missing] if worker == 'gw0'\n"
        "        else ['tests/test_alpha.py', missing]\n"
        "    )\n"
        "    path.write_text(json.dumps(payload))\n"
    )
    executor = SubprocessRuntimeCommandExecutor()
    selectors = (
        "tests/test_alpha.py",
        "tests/test_beta.py",
        "tests/test_alpha.py::missing_node",
    )

    group = executor.execute_with_contexts(
        ("python", "-m", "pytest", "tests/"),
        {str((tmp_path / "src/target.py").resolve())},
        tmp_path,
        30.0,
        pytest_workers=2,
        logical_selectors=selectors,
    )

    assert group.result.returncode == 0
    assert group.selector_nodeids["tests/test_alpha.py"] == (
        "tests/test_alpha.py::test_alpha",
    )
    assert group.selector_nodeids["tests/test_beta.py"] == (
        "tests/test_beta.py::test_beta",
    )
    assert group.completeness.unsupported_selectors == (
        "tests/test_alpha.py::missing_node",
    )


def test_dominated_missing_node_selector_remains_incomplete(tmp_path):
    from maid_runner.core.runtime_evidence import collect_runtime_evidence

    _project(tmp_path)
    valid = load_manifest(_write_manifest(tmp_path, "valid", "python -m pytest tests/"))
    invalid = load_manifest(
        _write_manifest(
            tmp_path,
            "invalid",
            "python -m pytest tests/ tests/test_alpha.py::missing_node",
        )
    )

    run = collect_runtime_evidence([valid, invalid], tmp_path, pytest_workers=2)

    assert run.test_result.success
    assert run.evidence.commands[0].selected_nodeids
    assert run.evidence.commands[0].completeness.unsupported_selectors == ()
    assert run.evidence.commands[1].completeness.complete is False
    assert run.evidence.commands[1].completeness.unsupported_selectors == (
        "tests/test_alpha.py::missing_node",
    )


def test_dominated_missing_file_selector_remains_incomplete(tmp_path):
    from maid_runner.core.runtime_evidence import collect_runtime_evidence

    _project(tmp_path)
    valid = load_manifest(_write_manifest(tmp_path, "valid", "python -m pytest tests/"))
    invalid = load_manifest(
        _write_manifest(
            tmp_path,
            "invalid",
            "python -m pytest tests/ tests/missing_test_file.py",
        )
    )

    run = collect_runtime_evidence([valid, invalid], tmp_path, pytest_workers=2)

    assert run.test_result.success
    assert run.evidence.commands[0].selected_nodeids
    assert run.evidence.commands[0].completeness.unsupported_selectors == ()
    assert run.evidence.commands[1].completeness.complete is False
    assert run.evidence.commands[1].completeness.unsupported_selectors == (
        "tests/missing_test_file.py",
    )


def test_k_deselection_maps_only_nodes_that_will_report(tmp_path):
    from maid_runner.core.runtime_evidence import collect_runtime_evidence

    _project(tmp_path)
    manifest = load_manifest(
        _write_manifest(tmp_path, "alpha", "python -m pytest tests/ -k alpha")
    )

    run = collect_runtime_evidence([manifest], tmp_path, pytest_workers=2)

    command = run.evidence.commands[0]
    assert command.selected_nodeids == ("tests/test_alpha.py::test_alpha",)
    assert not any(
        value.startswith("report:")
        for value in command.completeness.unresolved_context_ids
    )
    assert command.completeness.complete is True


def test_existing_empty_file_selector_is_supported_but_missing_node_is_not(tmp_path):
    from maid_runner.core.runtime_evidence import collect_runtime_evidence

    _project(tmp_path)
    (tmp_path / "tests/empty_anchor.py").write_text("ANCHOR = True\n")
    valid = load_manifest(
        _write_manifest(
            tmp_path,
            "valid",
            "python -m pytest tests/test_alpha.py tests/empty_anchor.py",
        )
    )
    invalid = load_manifest(
        _write_manifest(
            tmp_path,
            "invalid",
            "python -m pytest tests/test_alpha.py tests/test_alpha.py::missing_node",
        )
    )

    valid_run = collect_runtime_evidence([valid], tmp_path)

    assert valid_run.test_result.success
    assert valid_run.evidence.commands[0].completeness.unsupported_selectors == ()
    assert valid_run.evidence.commands[0].completeness.complete is True

    invalid_run = collect_runtime_evidence([invalid], tmp_path)
    assert invalid_run.evidence.commands[0].completeness.unsupported_selectors == (
        "tests/test_alpha.py::missing_node",
    )


def test_distribution_fixture_approval_requires_matching_runtime_source(tmp_path):
    import hashlib
    import inspect

    import _pytest.tmpdir

    from maid_runner.core.runtime_evidence import collect_runtime_evidence

    _project(tmp_path)
    (tmp_path / "tests/test_alpha.py").write_text(
        "def test_alpha(tmp_path_factory):\n"
        "    from src.target import target\n"
        "    assert tmp_path_factory is not None and target() is True\n"
    )
    source = Path(inspect.getsourcefile(_pytest.tmpdir)).resolve()
    digest = hashlib.sha256(source.read_bytes()).hexdigest()
    (tmp_path / ".maidrc.yaml").write_text(
        "artifact_coverage:\n"
        "  distribution_fixture_lifecycle_approvals:\n"
        "    - context_id: 'fixture::tmp_path_factory:session'\n"
        "      distribution: pytest\n"
        "      module_path: _pytest/tmpdir.py\n"
        f"      sha256: '{digest}'\n"
    )
    manifest = load_manifest(
        _write_manifest(tmp_path, "alpha", "python -m pytest tests/test_alpha.py")
    )

    approved = collect_runtime_evidence([manifest], tmp_path)

    assert approved.evidence.completeness.unproven_fixture_lifecycles == ()
    assert approved.evidence.commands[0].completeness.complete is True
    factory_context = next(
        context
        for context in approved.evidence.commands[0].contexts
        if "tmp_path_factory" in context.context_id
    )
    assert factory_context.fixture_definition_source == str(source)

    (tmp_path / "conftest.py").write_text(
        "import pytest\n\n"
        "@pytest.fixture(scope='session')\n"
        "def tmp_path_factory():\n"
        "    return object()\n"
    )
    rejected = collect_runtime_evidence([manifest], tmp_path)
    assert rejected.test_result.success
    assert "fixture::tmp_path_factory:session" in (
        rejected.evidence.completeness.unproven_fixture_lifecycles
    )
    shadow_context = next(
        context
        for context in rejected.evidence.commands[0].contexts
        if "tmp_path_factory" in context.context_id
    )
    assert shadow_context.fixture_definition_source == str(
        (tmp_path / "conftest.py").resolve()
    )


def test_test_module_fixture_approval_requires_matching_runtime_source(tmp_path):
    import hashlib

    from maid_runner.core.runtime_evidence import collect_runtime_evidence

    _project(tmp_path)
    test_source = tmp_path / "tests/test_alpha.py"
    test_source.write_text(
        "import pytest\n\n"
        "@pytest.fixture(scope='module')\n"
        "def reviewed_module():\n"
        "    return object()\n\n"
        "def test_alpha(reviewed_module):\n"
        "    from src.target import target\n"
        "    assert reviewed_module is not None and target() is True\n"
    )

    def write_approval() -> None:
        digest = hashlib.sha256(test_source.read_bytes()).hexdigest()
        (tmp_path / ".maidrc.yaml").write_text(
            "artifact_coverage:\n"
            "  fixture_lifecycle_approvals:\n"
            "    - context_id: 'fixture:tests/test_alpha.py:reviewed_module:module'\n"
            "      conftest_path: tests/test_alpha.py\n"
            f"      sha256: '{digest}'\n"
        )

    write_approval()
    manifest = load_manifest(
        _write_manifest(tmp_path, "alpha", "python -m pytest tests/test_alpha.py")
    )

    approved = collect_runtime_evidence([manifest], tmp_path)

    assert approved.test_result.success
    assert approved.evidence.completeness.unproven_fixture_lifecycles == ()
    assert approved.evidence.commands[0].completeness.complete is True
    approved_context = next(
        context
        for context in approved.evidence.commands[0].contexts
        if "reviewed_module" in context.context_id
    )
    assert approved_context.fixture_definition_source == str(test_source.resolve())

    helper_source = tmp_path / "fixture_helper.py"
    helper_source.write_text(
        "import pytest\n\n"
        "@pytest.fixture(scope='module')\n"
        "def reviewed_module():\n"
        "    return object()\n"
    )
    test_source.write_text(
        "from fixture_helper import reviewed_module\n\n"
        "def test_alpha(reviewed_module):\n"
        "    from src.target import target\n"
        "    assert reviewed_module is not None and target() is True\n"
    )
    write_approval()

    rejected = collect_runtime_evidence([manifest], tmp_path)

    assert rejected.test_result.success
    assert "fixture:tests/test_alpha.py:reviewed_module:module" in (
        rejected.evidence.completeness.unproven_fixture_lifecycles
    )
    rejected_context = next(
        context
        for context in rejected.evidence.commands[0].contexts
        if "reviewed_module" in context.context_id
    )
    assert rejected_context.fixture_definition_source == str(helper_source.resolve())


def test_digest_approval_applies_to_all_function_fixture_instances(tmp_path):
    import hashlib

    from maid_runner.core.runtime_evidence import collect_runtime_evidence

    _project(tmp_path)
    for name in ("alpha", "beta"):
        (tmp_path / "tests" / f"test_{name}.py").write_text(
            f"def test_{name}():\n"
            "    from src.target import target\n"
            "    assert target() is True\n"
        )
    conftest = tmp_path / "tests/conftest.py"
    conftest.write_text(
        "import pytest\n\n"
        "@pytest.fixture(autouse=True)\n"
        "def reviewed_lifecycle():\n"
        "    yield\n"
    )
    digest = hashlib.sha256(conftest.read_bytes()).hexdigest()
    (tmp_path / ".maidrc.yaml").write_text(
        "artifact_coverage:\n"
        "  fixture_lifecycle_approvals:\n"
        "    - context_id: 'fixture:tests:reviewed_lifecycle:function'\n"
        "      conftest_path: tests/conftest.py\n"
        f"      sha256: '{digest}'\n"
    )
    manifests = [
        load_manifest(
            _write_manifest(
                tmp_path,
                name,
                f"python -m pytest tests/test_{name}.py",
            )
        )
        for name in ("alpha", "beta")
    ]

    run = collect_runtime_evidence(manifests, tmp_path)

    assert run.evidence.completeness.unproven_fixture_lifecycles == ()
    assert all(command.completeness.complete for command in run.evidence.commands)


def test_single_logical_multi_selector_collection_context_is_exact_equivalent(tmp_path):
    from maid_runner.core.runtime_evidence import collect_runtime_evidence

    _project(tmp_path)
    manifest = load_manifest(
        _write_manifest(
            tmp_path,
            "both",
            "python -m pytest tests/test_alpha.py tests/test_beta.py",
        )
    )

    single = collect_runtime_evidence([manifest], tmp_path)

    assert single.test_result.success
    assert single.evidence.completeness.unresolved_context_ids == ()
    assert single.evidence.commands[0].completeness.complete is True

    split = [
        load_manifest(
            _write_manifest(
                tmp_path,
                name,
                f"python -m pytest tests/test_{name}.py",
            )
        )
        for name in ("alpha", "beta")
    ]
    multiple = collect_runtime_evidence(split, tmp_path)
    assert "collection:global" in multiple.evidence.completeness.unresolved_context_ids


def test_nested_test_command_environment_drops_outer_xdist_identity(monkeypatch):
    from maid_runner.core._test_command_execution import _test_command_environment

    monkeypatch.setenv("PYTEST_XDIST_WORKER", "gw7")
    monkeypatch.setenv("PYTEST_XDIST_WORKER_COUNT", "8")
    monkeypatch.setenv("MAID_UNRELATED", "retained")

    environment = _test_command_environment()

    assert "PYTEST_XDIST_WORKER" not in environment
    assert "PYTEST_XDIST_WORKER_COUNT" not in environment
    assert environment["MAID_UNRELATED"] == "retained"
    assert os.environ["PYTEST_XDIST_WORKER"] == "gw7"
    assert os.environ["PYTEST_XDIST_WORKER_COUNT"] == "8"


def test_missing_runtest_reports_are_incomplete_even_with_success_exit(
    tmp_path, monkeypatch
):
    from maid_runner.core._runtime_evidence_pytest_plugin import RuntimeEvidencePlugin

    monkeypatch.delenv("PYTEST_XDIST_WORKER", raising=False)
    monkeypatch.delenv("PYTEST_XDIST_WORKER_COUNT", raising=False)

    probe = tmp_path / "probe.py"
    probe.write_text("value = 1\n")
    target = str(probe.resolve())
    cases = {
        "zero": (),
        "setup-only": (("setup", "passed"),),
        "call-only": (("call", "passed"),),
        "missing-teardown": (("setup", "passed"), ("call", "passed")),
    }
    for name, reports in cases.items():
        plugin = RuntimeEvidencePlugin(tmp_path / name, frozenset({target}))
        exec(compile(probe.read_text(), target, "exec"), {})
        nodeid = f"tests/test_sample.py::test_{name}"
        item = SimpleNamespace(nodeid=nodeid, fixturenames=())
        plugin.pytest_collection_modifyitems(
            SimpleNamespace(), SimpleNamespace(), [item]
        )
        for when, outcome in reports:
            plugin.pytest_runtest_logreport(
                SimpleNamespace(nodeid=nodeid, when=when, outcome=outcome)
            )
        plugin.pytest_sessionfinish(SimpleNamespace(), 0)

        assert plugin.completeness.complete is False
        assert any(
            value.startswith(f"report:{nodeid}:")
            for value in plugin.completeness.unresolved_context_ids
        )


def test_manifest_command_or_worker_policy_change_rejects_bundle(tmp_path):
    from maid_runner.core.runtime_evidence import (
        collect_runtime_evidence,
        runtime_evidence_is_current,
    )

    _project(tmp_path)
    manifests = [
        load_manifest(_write_manifest(tmp_path, name, f"pytest tests/test_{name}.py"))
        for name in ("alpha", "beta")
    ]
    executor = _GroupExecutor(
        lambda command: _group(
            command,
            {
                "tests/test_alpha.py": ("tests/test_alpha.py::test_alpha",),
                "tests/test_beta.py": ("tests/test_beta.py::test_beta",),
            },
        )
    )
    bundle = collect_runtime_evidence(
        manifests, tmp_path, executor=executor, pytest_workers=2
    ).evidence

    assert runtime_evidence_is_current(bundle, manifests, tmp_path, pytest_workers=2)
    assert not runtime_evidence_is_current(
        bundle, manifests[:1], tmp_path, pytest_workers=2
    )
    assert not runtime_evidence_is_current(
        bundle, tuple(reversed(manifests)), tmp_path, pytest_workers=2
    )
    assert not runtime_evidence_is_current(
        bundle, manifests, tmp_path, pytest_workers=1
    )
