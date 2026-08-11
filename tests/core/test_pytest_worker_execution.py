"""Behavioral contract for duration-informed pytest worker execution."""

from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess
import sys
from types import SimpleNamespace

import pytest

from maid_runner.core._pytest_parallelism import PytestWorkerDecision


def _decision(*, use_workers: bool = True, workers: int | str = 8):
    return PytestWorkerDecision(
        use_workers=use_workers,
        workers=workers if use_workers else 1,
        predicted_duration_ms=45_000.0,
        history_state="complete",
        reason=(
            "workers:predicted-at-or-above-threshold"
            if use_workers
            else "serial:predicted-below-threshold"
        ),
    )


def _capabilities(*, available: bool = True):
    from maid_runner.core._pytest_worker_execution import PytestRunnerCapabilities

    return PytestRunnerCapabilities(
        xdist_available=available,
        xdist_version="3.8.0" if available else None,
        error=None if available else "pytest-xdist is unavailable",
    )


def _apply(
    tmp_path: Path,
    command: tuple[str, ...] = ("pytest", "tests/test_gate.py", "-q"),
    *,
    decision=None,
    capabilities=None,
    dist_mode: str = "loadscope",
    accepted_worker_counts: tuple[int, ...] = (8,),
    max_processes: int = 8,
    command_jobs: int = 1,
    explicit: bool = False,
):
    from maid_runner.core._pytest_worker_execution import apply_pytest_worker_decision

    return apply_pytest_worker_decision(
        command,
        decision or _decision(),
        capabilities or _capabilities(),
        dist_mode=dist_mode,
        accepted_worker_counts=accepted_worker_counts,
        max_processes=max_processes,
        command_jobs=command_jobs,
        project_root=tmp_path,
        explicit=explicit,
    )


def test_capability_probe_uses_resolved_consumer_environment(monkeypatch, tmp_path):
    from maid_runner.core._pytest_worker_execution import (
        probe_pytest_runner_capabilities,
    )

    observed = {}

    def fake_run(command, **kwargs):
        observed["command"] = command
        observed["cwd"] = kwargs["cwd"]
        return SimpleNamespace(
            returncode=0,
            stdout="pytest 8.4.1\nplugins: xdist-3.8.0",
            stderr="",
        )

    monkeypatch.setattr(
        "maid_runner.core._pytest_worker_execution.subprocess.run", fake_run
    )

    capability = probe_pytest_runner_capabilities(
        ("uv", "run", "python", "-m", "pytest", "tests/test_gate.py", "-q"),
        tmp_path,
    )

    assert observed == {
        "command": ("uv", "run", "python", "-m", "pytest", "--version", "--version"),
        "cwd": str(tmp_path),
    }
    assert capability.xdist_available is True
    assert capability.xdist_version == "3.8.0"


def test_explicit_missing_xdist_is_visible_failure(tmp_path):
    with pytest.raises(ValueError, match="pytest-xdist is unavailable"):
        _apply(
            tmp_path,
            capabilities=_capabilities(available=False),
            explicit=True,
        )


def test_automatic_missing_xdist_is_structured_serial_fallback(tmp_path):
    command, notice = _apply(
        tmp_path,
        capabilities=_capabilities(available=False),
        explicit=False,
    )

    assert command == ("pytest", "tests/test_gate.py", "-q")
    assert (notice.mode, notice.workers, notice.reason) == (
        "serial-fallback",
        1,
        "pytest-xdist is unavailable",
    )


def test_existing_command_worker_option_is_not_duplicated(tmp_path):
    command, notice = _apply(
        tmp_path,
        ("pytest", "tests/test_gate.py", "-n", "4", "--dist", "loadscope"),
    )

    assert command.count("-n") == 1
    assert command[command.index("-n") + 1] == "4"
    assert notice.mode == "preconfigured"
    assert notice.workers == 4


def test_automatic_worker_command_pins_accepted_loadscope_scheduler(tmp_path):
    command, notice = _apply(tmp_path)

    assert command == (
        "pytest",
        "tests/test_gate.py",
        "-q",
        "-n",
        "8",
        "--dist",
        "loadscope",
    )
    assert (notice.mode, notice.workers) == ("workers", 8)


def test_unproven_automatic_dist_mode_is_rejected(tmp_path):
    command, notice = _apply(tmp_path, dist_mode="load")

    assert command == ("pytest", "tests/test_gate.py", "-q")
    assert notice.mode == "serial-fallback"
    assert "loadscope" in notice.reason

    with pytest.raises(ValueError, match="loadscope"):
        _apply(tmp_path, dist_mode="load", explicit=True)


def test_injected_worker_count_must_be_in_repository_accepted_set(tmp_path):
    command, notice = _apply(tmp_path, accepted_worker_counts=(4,))

    assert command == ("pytest", "tests/test_gate.py", "-q")
    assert notice.mode == "serial-fallback"
    assert "accepted" in notice.reason

    with pytest.raises(ValueError, match="accepted"):
        _apply(tmp_path, accepted_worker_counts=(4,), explicit=True)


def test_process_budget_bounds_command_jobs_plus_pytest_workers(tmp_path):
    accepted, accepted_notice = _apply(
        tmp_path,
        decision=_decision(workers=4),
        accepted_worker_counts=(4,),
        max_processes=8,
        command_jobs=2,
    )
    command, notice = _apply(
        tmp_path,
        decision=_decision(workers=4),
        accepted_worker_counts=(4,),
        max_processes=7,
        command_jobs=2,
    )

    assert accepted[-4:] == ("-n", "4", "--dist", "loadscope")
    assert accepted_notice.mode == "workers"
    assert command == ("pytest", "tests/test_gate.py", "-q")
    assert notice.mode == "serial-fallback"
    assert "process budget" in notice.reason

    with pytest.raises(ValueError, match="process budget"):
        _apply(
            tmp_path,
            decision=_decision(workers=4),
            accepted_worker_counts=(4,),
            max_processes=7,
            command_jobs=2,
            explicit=True,
        )


def test_preconfigured_workers_obey_product_budget_and_command_precedence(tmp_path):
    (tmp_path / "pyproject.toml").write_text(
        "[tool.pytest.ini_options]\naddopts = '-n 8 --dist loadscope'\n"
    )

    command, notice = _apply(
        tmp_path,
        ("pytest", "tests/test_gate.py", "-n", "4", "--dist", "loadscope"),
        max_processes=8,
        command_jobs=2,
    )

    assert command.count("-n") == 1
    assert command[command.index("-n") + 1] == "4"
    assert notice.workers == 4

    with pytest.raises(ValueError, match="process budget"):
        _apply(
            tmp_path,
            ("pytest", "tests/test_gate.py", "-n", "8"),
            max_processes=8,
            command_jobs=2,
        )

    with pytest.raises(ValueError, match="bounded integer"):
        _apply(
            tmp_path,
            ("pytest", "tests/test_gate.py", "-n", "auto"),
            max_processes=64,
            command_jobs=1,
        )


def test_controller_timing_contains_every_selected_node_once(tmp_path):
    from maid_runner.core._pytest_timing_plugin import PytestTimingPlugin

    output = tmp_path / "timings.json"
    plugin = PytestTimingPlugin(
        output,
        expected_nodeids=(
            "tests/test_gate.py::test_a",
            "tests/test_gate.py::test_b",
            "tests/test_gate.py::test_skipped",
        ),
    )
    plugin.pytest_collection_finish(
        SimpleNamespace(
            items=[
                SimpleNamespace(nodeid="tests/test_gate.py::test_a"),
                SimpleNamespace(nodeid="tests/test_gate.py::test_b"),
                SimpleNamespace(nodeid="tests/test_gate.py::test_skipped"),
            ]
        )
    )
    plugin.pytest_xdist_node_collection_finished(
        SimpleNamespace(gateway=SimpleNamespace(id="gw0")),
        [
            "tests/test_gate.py::test_a",
            "tests/test_gate.py::test_b",
            "tests/test_gate.py::test_skipped",
        ],
    )
    plugin.pytest_runtest_logreport(
        SimpleNamespace(when="call", nodeid="tests/test_gate.py::test_b", duration=0.02)
    )
    plugin.pytest_runtest_logreport(
        SimpleNamespace(when="call", nodeid="tests/test_gate.py::test_a", duration=0.01)
    )
    plugin.pytest_runtest_logreport(
        SimpleNamespace(
            when="setup",
            nodeid="tests/test_gate.py::test_skipped",
            duration=0.005,
            skipped=True,
        )
    )
    plugin.pytest_sessionfinish(SimpleNamespace(), 0)

    assert json.loads(output.read_text()) == {
        "durations_ms": {
            "tests/test_gate.py::test_a": 10.0,
            "tests/test_gate.py::test_b": 20.0,
            "tests/test_gate.py::test_skipped": 5.0,
        }
    }
    assert plugin.output_path == output
    assert plugin.selected_nodeids == {
        "tests/test_gate.py::test_a",
        "tests/test_gate.py::test_b",
        "tests/test_gate.py::test_skipped",
    }
    assert plugin.completed_nodeids == plugin.selected_nodeids


def test_lost_worker_does_not_write_complete_timing_history(tmp_path):
    from maid_runner.core._pytest_timing_plugin import PytestTimingPlugin

    output = tmp_path / "timings.json"
    plugin = PytestTimingPlugin(
        output, expected_nodeids=("tests/test_gate.py::test_a",)
    )
    plugin.pytest_testnodedown(
        SimpleNamespace(gateway=SimpleNamespace(id="gw0")), "lost"
    )
    plugin.pytest_sessionfinish(SimpleNamespace(), 0)

    assert output.exists() is False
    assert plugin.incomplete_workers == {"gw0"}


def test_serial_and_worker_results_have_equivalent_normalized_payloads(tmp_path):
    serial, _ = _apply(tmp_path, decision=_decision(use_workers=False))
    worker, _ = _apply(tmp_path)

    assert (
        tuple(arg for arg in worker if arg not in {"-n", "8", "--dist", "loadscope"})
        == serial
    )


def test_worker_completion_order_does_not_reorder_structured_results(
    tmp_path, monkeypatch
):
    import time

    from maid_runner.core import test_runner
    from maid_runner.core._pytest_worker_execution import TestSchedulingNotice
    from maid_runner.core.result import TestRunResult

    def fake_prepare(command, **kwargs):
        target = command[1]
        return SimpleNamespace(
            command=command,
            environment_overrides={},
            notice=TestSchedulingNotice(
                command_group=command,
                mode="workers",
                workers=2,
                reason=f"scheduled:{target}",
            ),
        )

    def fake_run(command, **kwargs):
        if command[1].endswith("a.py"):
            time.sleep(0.03)
        return TestRunResult(
            manifest_slug=kwargs.get("manifest_slug", ""),
            command=command,
            exit_code=0,
            stdout="",
            stderr="",
            duration_ms=1.0,
        )

    monkeypatch.setattr(
        test_runner, "prepare_pytest_command", fake_prepare, raising=False
    )
    monkeypatch.setattr(
        test_runner, "finalize_pytest_timing", lambda *args: None, raising=False
    )
    monkeypatch.setattr(test_runner, "run_command", fake_run)
    notices = []

    results, passed, failed, early = test_runner._run_implementation_commands(
        [
            (("pytest", "tests/test_a.py"), "a"),
            (("pytest", "tests/test_b.py"), "b"),
        ],
        tmp_path,
        False,
        False,
        [],
        [],
        0,
        0,
        jobs=2,
        pytest_workers=2,
        scheduling_notices=notices,
    )

    assert (passed, failed, early) == (2, 0, None)
    assert [result.manifest_slug for result in results] == ["a", "b"]
    assert [notice.command_group[1] for notice in notices] == [
        "tests/test_a.py",
        "tests/test_b.py",
    ]


def test_collection_uses_resolved_consumer_environment_and_fails_closed(
    monkeypatch, tmp_path
):
    from maid_runner.core._pytest_worker_execution import (
        PytestCollectionResult,
        collect_pytest_nodeids,
    )

    tests = tmp_path / "tests"
    tests.mkdir()
    (tests / "test_gate.py").write_text(
        "import pytest\n\n"
        "@pytest.mark.parametrize('value', [1, 2])\n"
        "def test_gate(value):\n"
        "    assert value > 0\n"
    )
    collected = collect_pytest_nodeids(
        (sys.executable, "-m", "pytest", "tests/test_gate.py", "-q"), tmp_path
    )

    assert collected.nodeids == (
        "tests/test_gate.py::test_gate[1]",
        "tests/test_gate.py::test_gate[2]",
    )
    assert collected.error is None
    assert isinstance(collected, PytestCollectionResult)

    def failed_run(command, **kwargs):
        return SimpleNamespace(returncode=2, stdout="", stderr="collection failed")

    monkeypatch.setattr(
        "maid_runner.core._pytest_worker_execution.subprocess.run",
        failed_run,
    )
    failed = collect_pytest_nodeids(("pytest", "tests/test_gate.py"), tmp_path)
    assert failed.nodeids == ()
    assert "collection failed" in (failed.error or "")

    def evidence(payload):
        def write_evidence(command, **kwargs):
            Path(kwargs["env"]["MAID_COLLECTION_OUTPUT"]).write_text(payload)
            return SimpleNamespace(returncode=0, stdout="", stderr="")

        return write_evidence

    monkeypatch.setattr(
        "maid_runner.core._pytest_worker_execution.subprocess.run",
        evidence("not-json"),
    )
    malformed = collect_pytest_nodeids(("pytest", "tests/test_gate.py"), tmp_path)
    assert malformed.nodeids == ()
    assert "malformed" in (malformed.error or "")

    monkeypatch.setattr(
        "maid_runner.core._pytest_worker_execution.subprocess.run",
        evidence(json.dumps({"nodeids": ["a::test", "a::test"]})),
    )
    duplicate = collect_pytest_nodeids(("pytest", "tests/test_gate.py"), tmp_path)
    assert duplicate.nodeids == ()
    assert "duplicate" in (duplicate.error or "")


def test_timing_identity_changes_with_repository_test_or_config_content(tmp_path):
    from maid_runner.core._pytest_worker_execution import build_pytest_timing_identity

    tests = tmp_path / "tests"
    src = tmp_path / "src"
    tests.mkdir()
    src.mkdir()
    test_file = tests / "test_gate.py"
    test_file.write_text("def test_gate():\n    assert True\n")
    source_file = src / "gate.py"
    source_file.write_text("def gate():\n    return True\n")
    conftest = tmp_path / "conftest.py"
    conftest.write_text("pytest_plugins = []\n")
    config = tmp_path / "pyproject.toml"
    config.write_text("[tool.pytest.ini_options]\naddopts = '-q'\n")
    command = ("pytest", "tests/test_gate.py", "-q")
    original = build_pytest_timing_identity(command, tmp_path)
    assert build_pytest_timing_identity(command, tmp_path) == original

    test_file.write_text("def test_gate():\n    assert 1 == 1\n")
    changed_test = build_pytest_timing_identity(command, tmp_path)
    source_file.write_text("def gate():\n    return 1 == 1\n")
    changed_source = build_pytest_timing_identity(command, tmp_path)
    fixture = tests / "gate.json"
    fixture.write_text('{"enabled": true}\n')
    changed_non_python_input = build_pytest_timing_identity(command, tmp_path)
    conftest.write_text("pytest_plugins = ['example_plugin']\n")
    (tmp_path / "example_plugin.py").write_text("def pytest_configure(config): pass\n")
    changed_plugin = build_pytest_timing_identity(command, tmp_path)
    config.write_text("[tool.pytest.ini_options]\naddopts = '-qq'\n")
    changed_config = build_pytest_timing_identity(command, tmp_path)
    explicit = tmp_path / "isolated.ini"
    explicit.write_text("[pytest]\naddopts = -x\n")
    changed_explicit_config = build_pytest_timing_identity(
        ("pytest", "-c", "isolated.ini", "tests/test_gate.py"), tmp_path
    )
    changed_command = build_pytest_timing_identity(
        ("pytest", "tests/test_gate.py", "-x"), tmp_path
    )
    cache = tmp_path / ".maid" / "cache"
    cache.mkdir(parents=True)
    (cache / "timings.json").write_text('{"history": "changes"}')
    pytest_cache = tmp_path / ".pytest_cache"
    pytest_cache.mkdir()
    (pytest_cache / "nodeids").write_text('["tests/test_gate.py::test_gate"]')

    assert original[1] != changed_test[1]
    assert changed_test[1] != changed_source[1]
    assert changed_source[1] != changed_non_python_input[1]
    assert changed_non_python_input[1] != changed_plugin[1]
    assert changed_plugin[1] != changed_config[1]
    assert changed_config != changed_explicit_config
    assert changed_config[0] != changed_command[0]
    assert (
        build_pytest_timing_identity(("pytest", "tests/test_gate.py", "-x"), tmp_path)
        == changed_command
    )


def test_collection_preserves_inherited_consumer_pytest_plugins(monkeypatch, tmp_path):
    from maid_runner.core._pytest_worker_execution import collect_pytest_nodeids

    monkeypatch.setenv("PYTEST_PLUGINS", "consumer_required_plugin,other_plugin")

    def write_collection(command, **kwargs):
        plugins = kwargs["env"]["PYTEST_PLUGINS"].split(",")
        assert plugins == [
            "consumer_required_plugin",
            "other_plugin",
            "_maid_pytest_timing_plugin",
        ]
        Path(kwargs["env"]["MAID_COLLECTION_OUTPUT"]).write_text(
            json.dumps({"nodeids": ["tests/test_gate.py::test_gate"]})
        )
        return SimpleNamespace(returncode=0, stdout="", stderr="")

    monkeypatch.setattr(
        "maid_runner.core._pytest_worker_execution.subprocess.run", write_collection
    )

    collected = collect_pytest_nodeids(("pytest", "tests/test_gate.py"), tmp_path)

    assert collected.nodeids == ("tests/test_gate.py::test_gate",)
    assert collected.error is None


def test_existing_config_worker_option_is_not_duplicated(tmp_path):
    (tmp_path / "pyproject.toml").write_text(
        "[tool.pytest.ini_options]\naddopts = '-n 4 --dist loadscope'\n"
    )

    command, notice = _apply(tmp_path)

    assert "-n" not in command
    assert notice.mode == "preconfigured"
    assert notice.workers == 4


def test_automatic_policy_collects_exact_nodes_before_duration_decision(
    monkeypatch, tmp_path
):
    from maid_runner.core import _pytest_worker_execution as worker_execution
    from maid_runner.core._pytest_parallelism import PytestTimingHistoryLoad

    observed = {}
    monkeypatch.setattr(
        worker_execution,
        "collect_pytest_nodeids",
        lambda command, cwd: SimpleNamespace(
            nodeids=("tests/test_gate.py::test_gate",), error=None
        ),
        raising=False,
    )

    def fake_choose(**kwargs):
        observed["selected_nodeids"] = tuple(kwargs["selected_nodeids"])
        return _decision(use_workers=False)

    monkeypatch.setattr(
        worker_execution,
        "choose_pytest_worker_policy",
        fake_choose,
        raising=False,
    )
    monkeypatch.setattr(
        worker_execution,
        "load_pytest_timing_history",
        lambda *args, **kwargs: PytestTimingHistoryLoad(None, "missing"),
        raising=False,
    )

    worker_execution.prepare_pytest_command(
        ("pytest", "tests/test_gate.py"),
        project_root=tmp_path,
        pytest_workers=8,
        command_jobs=1,
    )

    assert observed["selected_nodeids"] == ("tests/test_gate.py::test_gate",)


def test_real_preparer_applies_worker_decision_and_fallback_precedence(
    monkeypatch, tmp_path
):
    from maid_runner.core import _pytest_worker_execution as worker_execution
    from maid_runner.core._pytest_parallelism import PytestTimingHistoryLoad

    tests = tmp_path / "tests"
    tests.mkdir()
    (tests / "test_gate.py").write_text(
        "import pytest\n\n"
        "def test_gate():\n"
        "    assert True\n\n"
        "@pytest.mark.skip(reason='platform')\n"
        "def test_skipped():\n"
        "    assert True\n"
    )
    (tmp_path / ".maidrc.yaml").write_text(
        """test_execution:
  pytest_workers: 8
  pytest_dist_mode: loadscope
  accepted_pytest_worker_counts: [8]
  parallel_threshold_seconds: 0
  parallel_without_history: false
  command_jobs: 1
  max_processes: 8
"""
    )
    monkeypatch.setattr(
        worker_execution,
        "collect_pytest_nodeids",
        lambda command, cwd: worker_execution.PytestCollectionResult(
            ("tests/test_gate.py::test_gate",), None
        ),
    )
    monkeypatch.setattr(
        worker_execution,
        "load_pytest_timing_history",
        lambda *args: PytestTimingHistoryLoad(None, "missing"),
    )
    monkeypatch.setattr(
        worker_execution,
        "choose_pytest_worker_policy",
        lambda **kwargs: _decision(workers=8),
    )
    monkeypatch.setattr(
        worker_execution,
        "probe_pytest_runner_capabilities",
        lambda command, cwd: _capabilities(),
    )

    prepared = worker_execution.prepare_pytest_command(
        ("pytest", "tests/test_gate.py", "-q"),
        project_root=tmp_path,
        pytest_workers=None,
        command_jobs=1,
    )

    assert prepared.command[-4:] == ("-n", "8", "--dist", "loadscope")
    assert prepared.notice is not None
    assert (prepared.notice.mode, prepared.notice.workers) == ("workers", 8)
    assert prepared.environment_overrides["PYTEST_PLUGINS"]
    assert prepared.environment_overrides["MAID_TIMING_OUTPUT"]

    monkeypatch.setattr(
        worker_execution,
        "probe_pytest_runner_capabilities",
        lambda command, cwd: _capabilities(available=False),
    )
    automatic = worker_execution.prepare_pytest_command(
        ("pytest", "tests/test_gate.py", "-q"),
        project_root=tmp_path,
        pytest_workers=None,
        command_jobs=1,
    )
    assert automatic.command == ("pytest", "tests/test_gate.py", "-q")
    assert automatic.notice.mode == "serial-fallback"

    with pytest.raises(ValueError, match="pytest-xdist is unavailable"):
        worker_execution.prepare_pytest_command(
            ("pytest", "tests/test_gate.py", "-q"),
            project_root=tmp_path,
            pytest_workers=8,
            command_jobs=1,
        )

    monkeypatch.setattr(
        worker_execution,
        "collect_pytest_nodeids",
        lambda command, cwd: worker_execution.PytestCollectionResult(
            (), "collection failed"
        ),
    )
    collection_fallback = worker_execution.prepare_pytest_command(
        ("pytest", "tests/test_gate.py", "-q"),
        project_root=tmp_path,
        pytest_workers=None,
        command_jobs=1,
    )
    assert collection_fallback.notice.mode == "serial-fallback"
    assert "collection failed" in collection_fallback.notice.reason

    with pytest.raises(ValueError, match="collection failed"):
        worker_execution.prepare_pytest_command(
            ("pytest", "tests/test_gate.py", "-q"),
            project_root=tmp_path,
            pytest_workers=8,
            command_jobs=1,
        )


def test_timing_plugin_loads_in_consumer_environment_without_maid_runner_import(
    tmp_path,
):
    from maid_runner.core._pytest_worker_execution import timing_plugin_environment
    from maid_runner.core._pytest_timing_plugin import (
        PytestTimingPlugin,
        pytest_addoption,
        pytest_configure,
    )

    class FakeParser:
        def __init__(self):
            self.options = []

        def getgroup(self, name):
            assert name == "maid-timing"
            return self

        def addoption(self, name, **kwargs):
            self.options.append(name)

    parser = FakeParser()
    pytest_addoption(parser)
    assert parser.options == [
        "--maid-timing-output",
        "--maid-selected-nodeids-file",
        "--maid-collection-output",
    ]

    selected = tmp_path / "selected.json"
    selected.write_text(json.dumps(["tests/test_gate.py::test_gate"]))
    timing_output = tmp_path / "timing.json"
    registered = []
    options = {
        "--maid-timing-output": str(timing_output),
        "--maid-selected-nodeids-file": str(selected),
        "--maid-collection-output": None,
    }
    config = SimpleNamespace(
        getoption=lambda name: options[name],
        pluginmanager=SimpleNamespace(
            register=lambda plugin, name: registered.append((plugin, name))
        ),
    )
    pytest_configure(config)
    assert isinstance(registered[0][0], PytestTimingPlugin)
    assert registered[0][1] == "maid-timing-plugin"

    environment, plugin_name = timing_plugin_environment(tmp_path)
    plugin_directory = Path(environment["PYTHONPATH"].split(os.pathsep, 1)[0])
    plugin_file = plugin_directory / f"{plugin_name}.py"

    assert plugin_file.is_file()
    assert "maid_runner" not in plugin_file.read_text()

    (plugin_file.parent / "sitecustomize.py").write_text(
        """import importlib.abc
import sys

class BlockMaidRunner(importlib.abc.MetaPathFinder):
    def find_spec(self, fullname, path=None, target=None):
        if fullname == 'maid_runner' or fullname.startswith('maid_runner.'):
            raise ModuleNotFoundError('maid_runner blocked in consumer environment')
        return None

sys.meta_path.insert(0, BlockMaidRunner())
"""
    )
    consumer = tmp_path / "consumer"
    consumer.mkdir()
    (consumer / "test_consumer.py").write_text(
        """try:
    import maid_runner
except ModuleNotFoundError:
    pass
else:
    raise AssertionError('maid_runner unexpectedly importable')

def test_consumer():
    assert True
"""
    )
    collection_output = tmp_path / "isolated-collection.json"
    child_env = dict(os.environ)
    child_env.update(environment)
    child_env.update(
        {
            "PYTEST_PLUGINS": plugin_name,
            "MAID_COLLECTION_OUTPUT": str(collection_output),
        }
    )

    completed = subprocess.run(
        [sys.executable, "-m", "pytest", "--collect-only", "-q"],
        cwd=consumer,
        env=child_env,
        capture_output=True,
        text=True,
        check=False,
    )

    assert completed.returncode == 0, completed.stderr
    assert json.loads(collection_output.read_text()) == {
        "nodeids": ["test_consumer.py::test_consumer"]
    }


def test_timing_finalizer_records_only_successful_exact_complete_history(tmp_path):
    from maid_runner.core._pytest_parallelism import load_pytest_timing_history
    from maid_runner.core._pytest_worker_execution import (
        PreparedPytestCommand,
        finalize_pytest_timing,
        prepare_pytest_command,
    )
    from maid_runner.core._test_command_execution import _run_test_command
    from maid_runner.core.result import TestRunResult

    tests = tmp_path / "tests"
    tests.mkdir()
    (tests / "test_gate.py").write_text(
        "import pytest\n\n"
        "def test_gate():\n"
        "    assert True\n\n"
        "@pytest.mark.skip(reason='platform')\n"
        "def test_skipped():\n"
        "    assert True\n"
    )
    prepared = prepare_pytest_command(
        (sys.executable, "-m", "pytest", "tests/test_gate.py", "-q"),
        project_root=tmp_path,
        pytest_workers=1,
        command_jobs=1,
    )
    assert isinstance(prepared, PreparedPytestCommand)
    plugin_directory = Path(
        prepared.environment_overrides["PYTHONPATH"].split(os.pathsep, 1)[0]
    )

    result = _run_test_command(
        prepared.command,
        cwd=tmp_path,
        environment_overrides=prepared.environment_overrides,
    )
    notice = finalize_pytest_timing(prepared, result, tmp_path)

    assert result.success is True
    assert notice is None
    loaded = load_pytest_timing_history(
        tmp_path,
        prepared.behavior_group_digest,
        prepared.input_digest,
    )
    assert loaded.state == "current"
    assert loaded.history is not None
    assert set(loaded.history.durations_ms) == {
        "tests/test_gate.py::test_gate",
        "tests/test_gate.py::test_skipped",
    }
    assert plugin_directory.exists() is False
    cache_file = next((tmp_path / ".maid" / "cache").glob("*.json"))
    before_failure = cache_file.read_text()

    failed_prepared = prepare_pytest_command(
        (sys.executable, "-m", "pytest", "tests/test_gate.py", "-q"),
        project_root=tmp_path,
        pytest_workers=1,
        command_jobs=1,
    )
    failed = TestRunResult(
        manifest_slug="gate",
        command=failed_prepared.command,
        exit_code=1,
        stdout="",
        stderr="failed",
        duration_ms=1.0,
    )
    discarded = finalize_pytest_timing(failed_prepared, failed, tmp_path)

    assert discarded is not None
    assert discarded.mode == "timing-discarded"
    assert cache_file.read_text() == before_failure
    failed_plugin_directory = Path(
        failed_prepared.environment_overrides["PYTHONPATH"].split(os.pathsep, 1)[0]
    )
    assert failed_plugin_directory.exists() is False


def test_timing_finalizer_discards_advisory_cache_write_failure(monkeypatch, tmp_path):
    from maid_runner.core import _pytest_worker_execution as worker_execution
    from maid_runner.core._test_command_execution import _run_test_command

    tests = tmp_path / "tests"
    tests.mkdir()
    (tests / "test_gate.py").write_text("def test_gate():\n" "    assert True\n")
    prepared = worker_execution.prepare_pytest_command(
        (sys.executable, "-m", "pytest", "tests/test_gate.py", "-q"),
        project_root=tmp_path,
        pytest_workers=1,
        command_jobs=1,
    )
    plugin_directory = Path(
        prepared.environment_overrides["PYTHONPATH"].split(os.pathsep, 1)[0]
    )
    result = _run_test_command(
        prepared.command,
        cwd=tmp_path,
        environment_overrides=prepared.environment_overrides,
    )
    monkeypatch.setattr(
        worker_execution,
        "record_pytest_timing_history",
        lambda *args, **kwargs: (_ for _ in ()).throw(OSError("read-only cache")),
    )

    notice = worker_execution.finalize_pytest_timing(prepared, result, tmp_path)

    assert result.success is True
    assert notice is not None
    assert notice.mode == "timing-discarded"
    assert "read-only cache" in notice.reason
    assert plugin_directory.exists() is False


def test_timing_plugin_rejects_missing_duplicate_nonzero_and_disagreeing_evidence(
    tmp_path,
):
    from maid_runner.core._pytest_timing_plugin import PytestTimingPlugin

    expected = ("tests/test_gate.py::test_a", "tests/test_gate.py::test_b")

    missing_output = tmp_path / "missing.json"
    missing = PytestTimingPlugin(missing_output, expected_nodeids=expected)
    missing.pytest_runtest_logreport(
        SimpleNamespace(when="call", nodeid=expected[0], duration=0.01)
    )
    missing.pytest_sessionfinish(SimpleNamespace(), 0)
    assert missing_output.exists() is False

    duplicate_output = tmp_path / "duplicate.json"
    duplicate = PytestTimingPlugin(duplicate_output, expected_nodeids=(expected[0],))
    report = SimpleNamespace(when="call", nodeid=expected[0], duration=0.01)
    duplicate.pytest_runtest_logreport(report)
    duplicate.pytest_runtest_logreport(report)
    duplicate.pytest_sessionfinish(SimpleNamespace(), 0)
    assert duplicate_output.exists() is False

    nonzero_output = tmp_path / "nonzero.json"
    nonzero = PytestTimingPlugin(nonzero_output, expected_nodeids=(expected[0],))
    nonzero.pytest_runtest_logreport(report)
    nonzero.pytest_sessionfinish(SimpleNamespace(), 1)
    assert nonzero_output.exists() is False

    disagree_output = tmp_path / "disagree.json"
    disagree = PytestTimingPlugin(disagree_output, expected_nodeids=expected)
    disagree.pytest_xdist_node_collection_finished(
        SimpleNamespace(gateway=SimpleNamespace(id="gw0")), list(expected)
    )
    disagree.pytest_xdist_node_collection_finished(
        SimpleNamespace(gateway=SimpleNamespace(id="gw1")), [expected[0]]
    )
    for nodeid in expected:
        disagree.pytest_runtest_logreport(
            SimpleNamespace(when="call", nodeid=nodeid, duration=0.01)
        )
    disagree.pytest_sessionfinish(SimpleNamespace(), 0)
    assert disagree_output.exists() is False
