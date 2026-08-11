"""Behavioral contract for fixture-aware grouped runtime evidence."""

from __future__ import annotations

import json
import os
from pathlib import Path
from types import MappingProxyType, SimpleNamespace

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


def test_missing_runtest_reports_are_incomplete_even_with_success_exit(tmp_path):
    from maid_runner.core._runtime_evidence_pytest_plugin import RuntimeEvidencePlugin

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
