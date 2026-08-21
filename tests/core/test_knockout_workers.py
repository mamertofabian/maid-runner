from __future__ import annotations

import hashlib
import threading
import time
from dataclasses import replace
from pathlib import Path

import pytest
import yaml

from maid_runner.core.manifest import load_manifest
from maid_runner.core.result import TestRunResult
from maid_runner.core.types import TestStream


def test_independent_mutations_overlap_without_shared_snapshot_state(tmp_path):
    from maid_runner.core.knockout import run_knockout_batch

    manifests = (
        _project_manifest(tmp_path, "first", ("alpha", "beta")),
        _project_manifest(tmp_path, "second", ("gamma", "delta")),
    )
    original = (tmp_path / "src/target.py").read_bytes()
    executor = _OverlapExecutor(start_barrier=threading.Barrier(2))

    reports = run_knockout_batch(
        manifests,
        tmp_path,
        jobs=2,
        max_processes=2,
        executor=executor,
    )

    assert all(reports[manifest.source_path].success for manifest in manifests)
    assert executor.peak >= 2
    assert len(executor.roots) == 2
    assert all(root != tmp_path for root in executor.roots)
    assert (tmp_path / "src/target.py").read_bytes() == original


def test_process_budget_bounds_jobs_plus_nested_command_workers(tmp_path, monkeypatch):
    from maid_runner.core import _knockout_worker
    from maid_runner.core._knockout_worker import (
        KnockoutWorkerResult,
        execute_knockout_worker,
        resolve_knockout_process_cost,
        run_knockout_workers,
    )

    specs = tuple(
        _spec(tmp_path, name, (("pytest", "-n", cost, "tests"),))
        for name, cost in (("alpha", "2"), ("beta", "2"), ("gamma", "1"))
    )
    active_cost = 0
    peak_cost = 0
    lock = threading.Lock()
    assert callable(execute_knockout_worker)

    def execute(spec, project_root, evidence, snapshot_backend, executor):
        nonlocal active_cost, peak_cost
        cost = max(
            resolve_knockout_process_cost(command, project_root)
            for command in spec.declarations[0].commands
        )
        with lock:
            active_cost += cost
            peak_cost = max(peak_cost, active_cost)
        time.sleep(0.04)
        with lock:
            active_cost -= cost
        return KnockoutWorkerResult(spec.identity, {}, cost, ())

    monkeypatch.setattr(_knockout_worker, "execute_knockout_worker", execute)

    results = run_knockout_workers(
        specs,
        tmp_path,
        None,
        object(),
        object(),
        jobs=3,
        max_processes=3,
    )

    assert [result.identity.artifact_name for result in results] == [
        "alpha",
        "beta",
        "gamma",
    ]
    assert [result.process_cost for result in results] == [2, 2, 1]
    assert peak_cost == 3


def test_process_budget_accounts_command_and_config_pytest_worker_counts(
    tmp_path,
):
    from maid_runner.core._knockout_worker import resolve_knockout_process_cost

    (tmp_path / "pyproject.toml").write_text(
        "[tool.pytest.ini_options]\naddopts = '-n 3 --dist loadscope'\n"
    )

    assert (
        resolve_knockout_process_cost(
            ("python", "-m", "pytest", "-n", "4", "tests"), tmp_path
        )
        == 4
    )
    assert resolve_knockout_process_cost(("pytest", "tests"), tmp_path) == 3
    assert resolve_knockout_process_cost(("pytest", "-n", "0", "tests"), tmp_path) == 1
    assert resolve_knockout_process_cost(("pytest", "-n=0", "tests"), tmp_path) == 1
    assert resolve_knockout_process_cost(("pytest", "-n=2", "tests"), tmp_path) == 2
    (tmp_path / "pyproject.toml").unlink()
    assert resolve_knockout_process_cost(("pytest", "tests"), tmp_path) == 1
    assert resolve_knockout_process_cost(("python", "check.py"), tmp_path) == 1


def test_explicit_one_worker_preserves_serial_execution(tmp_path):
    from maid_runner.core.knockout import run_knockout_batch

    manifest = _project_manifest(tmp_path, "target", ("alpha", "beta"))
    executor = _OverlapExecutor()

    report = run_knockout_batch(
        (manifest,),
        tmp_path,
        jobs=1,
        max_processes=8,
        executor=executor,
    )[manifest.source_path]

    assert report.success is True
    assert executor.peak == 1


def test_worker_completion_order_preserves_manifest_declaration_order(tmp_path):
    from maid_runner.core.knockout import run_knockout_batch

    manifest = _project_manifest(tmp_path, "target", ("alpha", "beta"))
    report = run_knockout_batch(
        (manifest,),
        tmp_path,
        jobs=2,
        max_processes=2,
        executor=_OverlapExecutor(delays={"alpha": 0.08, "beta": 0.01}),
    )[manifest.source_path]

    assert [result.artifact_name for result in report.results] == ["alpha", "beta"]
    assert [error.code.value for error in report.errors] == []


@pytest.mark.parametrize("jobs", [1, 2])
def test_workers_publish_each_validated_result_before_batch_finishes(
    tmp_path, monkeypatch, jobs
):
    from maid_runner.core import _knockout_worker
    from maid_runner.core._knockout_worker import (
        KnockoutWorkerResult,
        run_knockout_workers,
    )

    specs = (
        _spec(tmp_path, "alpha", (("python", "check.py"),)),
        _spec(tmp_path, "beta", (("python", "check.py"),)),
    )
    release_beta = threading.Event()
    alpha_published = threading.Event()
    finished = threading.Event()
    results = []

    def execute(spec, *_args):
        if spec.identity.artifact_name == "beta":
            assert release_beta.wait(timeout=2)
            return KnockoutWorkerResult(spec.identity, {}, 99, ())
        return KnockoutWorkerResult(
            replace(spec.identity, artifact_name="wrong"), {}, 99, ()
        )

    def publish(result):
        results.append(result)
        if result.identity.artifact_name == "alpha":
            alpha_published.set()

    def schedule():
        try:
            results.extend(
                run_knockout_workers(
                    specs,
                    tmp_path,
                    None,
                    object(),
                    object(),
                    jobs=jobs,
                    max_processes=2,
                    on_result=publish,
                )
            )
        finally:
            finished.set()

    monkeypatch.setattr(_knockout_worker, "execute_knockout_worker", execute)
    scheduler = threading.Thread(target=schedule)
    scheduler.start()
    try:
        assert alpha_published.wait(timeout=2)
        assert not finished.is_set()
    finally:
        release_beta.set()
        scheduler.join(timeout=2)

    assert finished.is_set()
    published = results[:2]
    returned = results[2:]
    assert [result.identity.artifact_name for result in published] == ["alpha", "beta"]
    assert tuple(published) == tuple(returned)
    assert published[0].process_cost == 1
    assert [error.code.value for error in published[0].errors] == ["E712"]
    assert published[1].process_cost == 1


@pytest.mark.parametrize("jobs", [1, 2])
def test_worker_result_callback_exception_propagates(tmp_path, monkeypatch, jobs):
    from maid_runner.core import _knockout_worker
    from maid_runner.core._knockout_worker import (
        KnockoutWorkerResult,
        run_knockout_workers,
    )

    spec = _spec(tmp_path, "alpha", (("python", "check.py"),))

    def execute(spec, *_args):
        return KnockoutWorkerResult(spec.identity, {}, 1, ())

    def reject(_result):
        raise RuntimeError("checkpoint failed")

    monkeypatch.setattr(_knockout_worker, "execute_knockout_worker", execute)

    with pytest.raises(RuntimeError, match="checkpoint failed"):
        run_knockout_workers(
            (spec,),
            tmp_path,
            None,
            object(),
            object(),
            jobs=jobs,
            max_processes=1,
            on_result=reject,
        )


def test_worker_callback_publishes_prescheduling_failure(tmp_path):
    from maid_runner.core._knockout_worker import run_knockout_workers

    spec = _spec(tmp_path, "alpha", (("pytest", "-n", "3", "tests"),))
    published = []

    returned = run_knockout_workers(
        (spec,),
        tmp_path,
        None,
        object(),
        object(),
        jobs=2,
        max_processes=1,
        on_result=published.append,
    )

    assert tuple(published) == returned
    assert [error.code.value for error in published[0].errors] == ["E712"]
    assert "exceeds budget" in published[0].errors[0].message


def test_parallel_and_serial_reports_match_except_durations(tmp_path):
    from maid_runner.core.knockout import run_knockout_batch

    manifest = _project_manifest(tmp_path, "target", ("alpha", "beta"))
    serial = run_knockout_batch(
        (manifest,),
        tmp_path,
        jobs=1,
        max_processes=2,
        executor=_OverlapExecutor(),
        no_cache=True,
    )[manifest.source_path]
    parallel = run_knockout_batch(
        (manifest,),
        tmp_path,
        jobs=2,
        max_processes=2,
        executor=_OverlapExecutor(),
        no_cache=True,
    )[manifest.source_path]

    assert _without_durations(serial.to_dict()) == _without_durations(
        parallel.to_dict()
    )


def test_worker_crash_timeout_or_missing_result_is_e712(tmp_path, monkeypatch):
    from maid_runner.core import _knockout_worker
    from maid_runner.core._knockout_snapshot import MaterializedProjectSnapshotBackend
    from maid_runner.core._knockout_worker import (
        KnockoutWorkerResult,
        execute_knockout_worker,
        run_knockout_workers,
    )

    specs = (
        _spec(tmp_path, "crash", (("python", "check.py"),)),
        _spec(tmp_path, "missing", (("python", "check.py"),)),
    )

    def broken(spec, *args):
        if spec.identity.artifact_name == "crash":
            raise RuntimeError("worker crashed")
        return KnockoutWorkerResult(
            replace(spec.identity, artifact_name="wrong"), {}, 1, ()
        )

    monkeypatch.setattr(_knockout_worker, "execute_knockout_worker", broken)
    results = run_knockout_workers(specs, tmp_path, None, object(), object(), 2, 2)

    assert all(result.errors for result in results)
    assert all(
        error.code.value == "E712" for result in results for error in result.errors
    )
    assert "crashed" in results[0].errors[0].message
    assert "identity" in results[1].errors[0].message.lower()

    timeout_root = tmp_path / "timeout"
    timeout_root.mkdir()
    timeout_spec = _spec(timeout_root, "target", (("python", "check.py"),))

    class FailedCommandExecutor:
        def __init__(self, exit_code):
            self.exit_code = exit_code

        def execute(self, command, project_root, manifest_slug, *environment):
            return _result(command, self.exit_code)

    for failed_exit_code in (-1, -2):
        failed = execute_knockout_worker(
            timeout_spec,
            timeout_root,
            None,
            MaterializedProjectSnapshotBackend(),
            FailedCommandExecutor(failed_exit_code),
        )
        failed_errors = tuple(
            error for report in failed.reports.values() for error in report.errors
        )
        assert failed_errors
        assert all(error.code.value == "E712" for error in failed_errors)


def test_original_source_bytes_and_status_remain_unchanged_during_overlap(tmp_path):
    from maid_runner.core.knockout import run_knockout_batch

    manifest = _project_manifest(tmp_path, "target", ("alpha", "beta"))
    original = (tmp_path / "src/target.py").read_bytes()
    report = run_knockout_batch(
        (manifest,),
        tmp_path,
        jobs=2,
        max_processes=2,
        executor=_OverlapExecutor(),
    )[manifest.source_path]

    assert report.success is True
    assert (tmp_path / "src/target.py").read_bytes() == original
    assert not (tmp_path / "worker-state").exists()


def test_inter_declaration_side_effects_are_isolated_in_parallel_and_serial(tmp_path):
    from maid_runner.core.knockout import run_knockout_batch

    first = _project_manifest(tmp_path, "first", ("alpha",))
    second = _project_manifest(tmp_path, "second", ("alpha",))
    for jobs in (1, 2):
        executor = _StateWritingExecutor()
        reports = run_knockout_batch(
            (first, second),
            tmp_path,
            jobs=jobs,
            max_processes=2,
            executor=executor,
            no_cache=True,
        )
        assert reports[first.source_path].success is True
        assert reports[second.source_path].success is True
        assert executor.baselines_without_state == 2
        assert not (tmp_path / "declaration-state").exists()

    duplicate = _project_manifest(tmp_path, "duplicate", ("alpha", "beta", "alpha"))
    duplicate_report = run_knockout_batch(
        (duplicate,),
        tmp_path,
        jobs=2,
        max_processes=2,
        executor=_OverlapExecutor(),
        no_cache=True,
    )[duplicate.source_path]
    assert [result.artifact_name for result in duplicate_report.results] == [
        "alpha",
        "beta",
        "alpha",
    ]


class _OverlapExecutor:
    def __init__(self, delays=None, start_barrier: threading.Barrier | None = None):
        self.delays = delays or {}
        self.start_barrier = start_barrier
        self.lock = threading.Lock()
        self.active = 0
        self.peak = 0
        self.roots: set[Path] = set()

    def execute(self, command, project_root, manifest_slug, *environment):
        root = Path(project_root)
        source = (root / "src/target.py").read_text()
        artifact = _mutated_artifact(source) or _command_artifact(command)
        with self.lock:
            self.roots.add(root)
            self.active += 1
            self.peak = max(self.peak, self.active)
        try:
            if self.start_barrier is not None:
                self.start_barrier.wait(timeout=2)
            time.sleep(self.delays.get(artifact, 0.02))
        finally:
            with self.lock:
                self.active -= 1
        return _result(command, 1 if _mutated_artifact(source) else 0)


class _StateWritingExecutor(_OverlapExecutor):
    def __init__(self):
        super().__init__()
        self.first_seen_roots: set[Path] = set()
        self.baselines_without_state = 0
        self._after_mutant = False

    def execute(self, command, project_root, manifest_slug, *environment):
        root = Path(project_root)
        state = root / "declaration-state"
        mutated = "maid-knockout" in (root / "src/target.py").read_text()
        if mutated:
            self._after_mutant = True
        elif self._after_mutant:
            self._after_mutant = False
        else:
            assert not state.exists()
            self.first_seen_roots.add(root)
            self.baselines_without_state += 1
            state.write_text(manifest_slug)
        return super().execute(command, project_root, manifest_slug, *environment)


def _project_manifest(root: Path, slug: str, artifacts: tuple[str, ...]):
    # Worker scheduling uses injected executors and needs no installed packages.
    (root / ".venv").mkdir(exist_ok=True)
    (root / "src").mkdir(exist_ok=True)
    (root / "src/__init__.py").write_text("")
    (root / "src/target.py").write_text(
        "\n\n".join(
            f"def {name}():\n    return {name!r}"
            for name in ("alpha", "beta", "gamma", "delta")
        )
        + "\n"
    )
    (root / "tests").mkdir(exist_ok=True)
    (root / "tests/test_target.py").write_text("def test_placeholder(): assert True\n")
    (root / "manifests").mkdir(exist_ok=True)
    path = root / f"manifests/{slug}.manifest.yaml"
    path.write_text(
        yaml.safe_dump(
            {
                "schema": "2",
                "goal": slug,
                "type": "refactor",
                "created": "2026-08-12T00:00:00Z",
                "files": {
                    "edit": [
                        {
                            "path": "src/target.py",
                            "artifacts": [
                                {"kind": "function", "name": name, "args": []}
                                for name in artifacts
                            ],
                        }
                    ]
                },
                "validate": [f"python -m pytest -q tests --artifact={artifacts[0]}"],
            },
            sort_keys=False,
        )
    )
    return load_manifest(path)


def _spec(root: Path, name: str, commands):
    from maid_runner.core.knockout import (
        KnockoutArtifactIdentity,
        KnockoutDeclaration,
        KnockoutMutationSpec,
    )

    (root / ".venv").mkdir(exist_ok=True)
    source = root / "target.py"
    source.write_text("def target():\n    return 1\n")
    return KnockoutMutationSpec(
        KnockoutArtifactIdentity("target.py", name, "function", None),
        hashlib.sha256(source.read_bytes()).hexdigest(),
        (KnockoutDeclaration(f"{name}.yaml", name, 0, 0, tuple(commands)),),
    )


def _mutated_artifact(source: str) -> str | None:
    marker = 'raise NotImplementedError("maid-knockout")'
    if marker not in source:
        return None
    before = source[: source.index(marker)]
    return max(
        ("alpha", "beta", "gamma", "delta"),
        key=lambda name: before.rfind(f"def {name}"),
    )


def _command_artifact(command) -> str:
    value = " ".join(command)
    return next(name for name in ("alpha", "beta", "gamma", "delta") if name in value)


def _result(command, exit_code):
    return TestRunResult(
        manifest_slug="worker",
        command=tuple(command),
        exit_code=exit_code,
        stdout="",
        stderr="",
        duration_ms=1.0,
        stream=TestStream.IMPLEMENTATION,
    )


def _without_durations(value):
    if isinstance(value, dict):
        return {
            key: _without_durations(item)
            for key, item in value.items()
            if key != "duration_ms"
        }
    if isinstance(value, list):
        return [_without_durations(item) for item in value]
    return value
