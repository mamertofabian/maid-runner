"""Behavioral contract for isolated exact artifact-coverage fallbacks."""

from __future__ import annotations

import shutil
import threading
import time
from contextlib import contextmanager
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace

import pytest

from maid_runner.core._runtime_command_executor import (
    RuntimeCommandRecord,
    RuntimeFileExecution,
)
from maid_runner.core.manifest import load_manifest
from maid_runner.core.runtime_evidence import RuntimeCommandIdentity


def _write_project(root: Path, names=("alpha", "beta")):
    for directory in ("src", "tests", "manifests"):
        (root / directory).mkdir(parents=True, exist_ok=True)
    (root / "src" / "__init__.py").write_text("")
    manifests = []
    for name in names:
        (root / "src" / f"{name}.py").write_text(
            f"def {name}() -> str:\n    return '{name}'\n"
        )
        (root / "tests" / f"test_{name}.py").write_text(
            "import os\n"
            f"from src.{name} import {name}\n\n"
            f"def test_{name}():\n    assert {name}() == '{name}'\n"
            "    assert os.environ.get('COVERAGE_CORE') is None\n"
        )
        path = root / "manifests" / f"{name}.manifest.yaml"
        path.write_text(
            f"""schema: "2"
goal: "Cover {name}"
type: feature
created: "2026-08-12T00:00:00Z"
files:
  edit:
    - path: src/{name}.py
      artifacts:
        - kind: function
          name: {name}
          args: []
          returns: str
  read:
    - tests/test_{name}.py
validate:
  - python -m pytest -q tests/test_{name}.py
"""
        )
        manifests.append(load_manifest(path))
    return tuple(manifests)


def _identities(manifests):
    return tuple(
        RuntimeCommandIdentity(manifest.source_path, 0, manifest.validate_commands[0])
        for manifest in manifests
    )


def _targets(root: Path, identities):
    return {
        identity: {
            str(
                (
                    root
                    / "src"
                    / f"{Path(identity.manifest_path).stem.split('.')[0]}.py"
                ).resolve()
            )
        }
        for identity in identities
    }


class _CopySnapshotBackend:
    def __init__(self, destination: Path):
        self.destination = destination

    @contextmanager
    def create(self, project_root, required_paths, worker_id):
        root = self.destination / worker_id
        shutil.copytree(project_root, root)
        try:
            yield SimpleNamespace(
                root=root,
                environment_overrides={"MAID_SNAPSHOT": worker_id},
                environment_removals=("MAID_SOURCE_ONLY",),
            )
        finally:
            shutil.rmtree(root)


class _RecordingExecutor:
    def __init__(self, source_root: Path, *, delays=None, write=False):
        self.source_root = source_root
        self.delays = delays or {}
        self.write = write
        self.calls = []
        self.active = 0
        self.peak = 0
        self.lock = threading.Lock()

    def execute(
        self,
        command,
        target_files,
        project_root,
        timeout_seconds,
        environment_overrides=None,
        environment_removals=(),
    ):
        name = (
            "alpha"
            if any(str(part).endswith("test_alpha.py") for part in command)
            else "beta"
        )
        with self.lock:
            self.calls.append(
                (
                    tuple(command),
                    Path(project_root),
                    dict(environment_overrides or {}),
                    tuple(environment_removals),
                )
            )
            self.active += 1
            self.peak = max(self.peak, self.active)
        if self.write and name == "alpha":
            (Path(project_root) / "material.txt").write_text("alpha")
        if name == "beta" and Path(project_root) == self.source_root:
            marker = Path(project_root) / "material.txt"
            if marker.exists():
                (Path(project_root) / "reader-observed.txt").write_text(
                    marker.read_text()
                )
        time.sleep(self.delays.get(name, 0.01))
        with self.lock:
            self.active -= 1
        execution = {
            str(next(iter(target_files))): RuntimeFileExecution(
                executed_lines=frozenset({2}),
                called_qualnames=frozenset({name}),
            )
        }
        return RuntimeCommandRecord(
            command=tuple(command),
            returncode=0,
            stdout="",
            stderr="",
            execution_data=execution,
            report_errors=(),
        )


def _incomplete_evidence(root: Path, manifests):
    from maid_runner.core.runtime_evidence import collect_runtime_evidence

    class GroupExecutor:
        def execute_with_contexts(
            self,
            command,
            target_files,
            project_root,
            timeout_seconds,
            pytest_workers=None,
        ):
            from maid_runner.core.runtime_evidence import (
                RuntimeEvidenceCompleteness,
                RuntimeGroupEvidence,
            )

            return RuntimeGroupEvidence(
                command=tuple(command),
                selected_nodeids=(),
                selector_nodeids={},
                contexts=(),
                result=RuntimeCommandRecord(tuple(command), 0, "", "", {}, ()),
                worker_ids=("main",),
                completeness=RuntimeEvidenceCompleteness(
                    complete=False,
                    unproven_fixture_lifecycles=("session:autouse",),
                ),
            )

    return collect_runtime_evidence(manifests, root, executor=GroupExecutor()).evidence


def test_root_session_autouse_fixture_commands_keep_exact_process_lifetimes(tmp_path):
    from maid_runner.core._knockout_snapshot import (
        MaterializedProjectSnapshotBackend,
    )
    from maid_runner.core._artifact_coverage_fallback_worker import (
        run_isolated_artifact_coverage_fallbacks,
    )
    from maid_runner.core._runtime_command_executor import (
        SubprocessRuntimeCommandExecutor,
    )

    root = tmp_path / "project"
    manifests = _write_project(root, ("alpha",))
    (root / "tests" / "test_alpha.py").write_text(
        "def test_alpha():\n    assert True\n"
    )
    (root / "conftest.py").write_text(
        "import pytest\n"
        "from src.alpha import alpha\n\n"
        "@pytest.fixture(scope='session', autouse=True)\n"
        "def exact_session_lifecycle():\n"
        "    yield\n"
        "    alpha()\n"
    )
    identities = _identities(manifests)
    run = run_isolated_artifact_coverage_fallbacks(
        identities,
        root,
        _targets(root, identities),
        MaterializedProjectSnapshotBackend(),
        SubprocessRuntimeCommandExecutor(),
        jobs=1,
        max_processes=1,
    )

    assert [result.identity for result in run.results] == list(identities)
    assert run.results[0].command_run is not None
    execution = next(iter(run.results[0].command_run.execution_data.values()))
    assert "alpha" in execution.called_qualnames
    assert run.serial_fallback_identities == ()


def test_isolated_parallel_and_legacy_serial_reports_match_in_manifest_order(tmp_path):
    from maid_runner.core.artifact_coverage import (
        evaluate_artifact_coverage_from_evidence,
    )

    root = tmp_path / "project"
    manifests = _write_project(root)
    evidence = _incomplete_evidence(root, manifests)
    serial = evaluate_artifact_coverage_from_evidence(
        manifests,
        root,
        evidence,
        fallback_executor=_RecordingExecutor(root),
    )
    isolated = evaluate_artifact_coverage_from_evidence(
        manifests,
        root,
        evidence,
        fallback_executor=_RecordingExecutor(root),
        fallback_jobs=2,
        max_processes=2,
        snapshot_backend=_CopySnapshotBackend(tmp_path / "snapshots"),
    )

    assert list(isolated.reports) == [manifest.source_path for manifest in manifests]
    assert {key: value.to_dict() for key, value in isolated.reports.items()} == {
        key: value.to_dict() for key, value in serial.reports.items()
    }

    from maid_runner.cli.commands.validate import _run_artifact_coverage_by_manifest

    (root / ".maidrc.yaml").write_text(
        "test_execution:\n  max_processes: 2\n"
        "artifact_coverage:\n  fallback_jobs: 2\n"
    )
    cli_reports = _run_artifact_coverage_by_manifest(
        "manifests", root, evidence=evidence
    )
    assert list(cli_reports) == [manifest.source_path for manifest in manifests]


def test_disjoint_exact_fallbacks_overlap_within_process_budget(tmp_path):
    from maid_runner.core._artifact_coverage_fallback_worker import (
        run_isolated_artifact_coverage_fallbacks,
    )

    root = tmp_path / "project"
    identities = _identities(_write_project(root))
    executor = _RecordingExecutor(root, delays={"alpha": 0.02, "beta": 0.02})
    run_isolated_artifact_coverage_fallbacks(
        identities,
        root,
        _targets(root, identities),
        _CopySnapshotBackend(tmp_path / "snapshots"),
        executor,
        jobs=8,
        max_processes=2,
    )

    assert executor.peak == 2

    priority_root = tmp_path / "priority-project"
    priority_manifests = _write_project(priority_root, ("alpha", "beta", "gamma"))
    (priority_root / "tests/test_alpha.py").write_text(
        "import subprocess\n\n"
        "def test_alpha():\n"
        "    subprocess.run(['true'], check=True)\n"
    )
    (priority_root / "tests/test_beta.py").write_text(
        "def test_beta():\n    assert True\n" + "# padding\n" * 5_000
    )
    priority_identities = _identities(priority_manifests)
    priority_executor = _RecordingExecutor(priority_root)

    run_isolated_artifact_coverage_fallbacks(
        priority_identities,
        priority_root,
        _targets(priority_root, priority_identities),
        _CopySnapshotBackend(tmp_path / "priority-snapshots"),
        priority_executor,
        jobs=1,
        max_processes=1,
    )

    assert priority_executor.calls[0][0] == (
        "-q",
        "tests/test_alpha.py",
    )

    class ExclusiveRecordingExecutor(_RecordingExecutor):
        def __init__(self, source_root):
            super().__init__(source_root, delays={"alpha": 0.02, "beta": 0.02})
            self.broad_active = False
            self.overlapped_broad = False

        def execute(self, command, *args, **kwargs):
            broad = "tests/" in command
            with self.lock:
                if self.active or self.broad_active:
                    self.overlapped_broad = (
                        self.overlapped_broad or broad or self.broad_active
                    )
                if broad:
                    self.broad_active = True
            try:
                return super().execute(command, *args, **kwargs)
            finally:
                if broad:
                    with self.lock:
                        self.broad_active = False

    def run_directory_case(
        case_name, source, *, workers=2, maximum=8, conftest_source=None
    ):
        case_root = tmp_path / f"{case_name}-directory-project"
        case_manifests = _write_project(case_root)
        (case_root / "tests/test_nested.py").write_text(source)
        if conftest_source is not None:
            conftest_path = case_root / "tests/conftest.py"
            if isinstance(conftest_source, bytes):
                conftest_path.write_bytes(conftest_source)
            else:
                conftest_path.write_text(conftest_source)
        case_identities = (
            replace(
                _identities(case_manifests)[0],
                command=("pytest", "tests/", "-q"),
            ),
            _identities(case_manifests)[1],
        )
        (case_root / ".maidrc.yaml").write_text(
            "test_execution:\n"
            f"  pytest_workers: {workers}\n"
            "  pytest_dist_mode: loadscope\n"
            f"  accepted_pytest_worker_counts: [{workers}]\n"
            f"  max_processes: {maximum}\n"
        )
        case_executor = ExclusiveRecordingExecutor(case_root)
        case_run = run_isolated_artifact_coverage_fallbacks(
            case_identities,
            case_root,
            _targets(case_root, case_identities),
            _CopySnapshotBackend(tmp_path / f"{case_name}-directory-snapshots"),
            case_executor,
            jobs=2,
            max_processes=maximum,
        )
        return case_executor, case_run

    hazardous_sources = {
        "runtime-evidence": "def test_nested():\n    collect_runtime_evidence()\n",
        "knockout-batch": "def test_nested():\n    run_knockout_batch()\n",
        "git-helper": "def test_nested():\n    _git()\n",
        "validate-result": "def test_nested():\n    run_validate_commands_for_result()\n",
        "subprocess-run": "import subprocess\ndef test_nested():\n    subprocess.run([])\n",
        "subprocess-popen": "import subprocess\ndef test_nested():\n    subprocess.Popen([])\n",
        "subprocess-call": "import subprocess\ndef test_nested():\n    subprocess.call([])\n",
        "subprocess-check-call": "import subprocess\ndef test_nested():\n    subprocess.check_call([])\n",
        "subprocess-check-output": "import subprocess\ndef test_nested():\n    subprocess.check_output([])\n",
    }
    for case_name, source in hazardous_sources.items():
        case_executor, case_run = run_directory_case(case_name, source)
        assert case_executor.overlapped_broad is False, case_name
        assert [result.process_cost for result in case_run.results] == [8, 1]
        broad_call = next(
            call[0] for call in case_executor.calls if "tests/" in call[0]
        )
        assert broad_call[-4:] == ("-n", "2", "--dist", "loadscope")

    safe_executor, safe_run = run_directory_case(
        "safe", "def test_nested():\n    assert True\n"
    )
    assert safe_executor.overlapped_broad is True
    assert [result.process_cost for result in safe_run.results] == [2, 1]

    alias_executor, alias_run = run_directory_case(
        "alias",
        "import subprocess as sp\ndef test_nested():\n    sp.run([])\n",
    )
    assert alias_executor.overlapped_broad is True
    assert [result.process_cost for result in alias_run.results] == [2, 1]

    unknown_executor, unknown_run = run_directory_case(
        "unknown", "def invalid syntax\n"
    )
    assert unknown_executor.overlapped_broad is False
    assert [result.process_cost for result in unknown_run.results] == [8, 1]
    unknown_call = next(
        call[0] for call in unknown_executor.calls if "tests/" in call[0]
    )
    assert unknown_call[-4:] == ("-n", "2", "--dist", "loadscope")

    conftest_hazards = {
        **hazardous_sources,
        "module-import": "import subprocess\nsubprocess.run([])\n",
        "controller-hook": (
            "import subprocess\n"
            "def pytest_sessionstart(session):\n    subprocess.run([])\n"
        ),
        "fixture-hook": (
            "import subprocess\n"
            "def pytest_runtest_setup(item):\n    subprocess.run([])\n"
        ),
        "parse-unknown": "def invalid syntax\n",
        "read-unknown": b"\xff\xfe",
    }
    for case_name, conftest_source in conftest_hazards.items():
        fixture_executor, fixture_run = run_directory_case(
            f"conftest-{case_name}",
            "def test_nested():\n    assert True\n",
            conftest_source=conftest_source,
        )
        fixture_call = next(
            call[0] for call in fixture_executor.calls if "tests/" in call[0]
        )
        assert "-n" not in fixture_call, case_name
        assert fixture_executor.overlapped_broad is False, case_name
        assert [result.process_cost for result in fixture_run.results] == [8, 1]

    odd_executor, odd_run = run_directory_case(
        "odd-budget",
        hazardous_sources["subprocess-run"],
        maximum=5,
    )
    assert odd_executor.overlapped_broad is False
    assert [result.process_cost for result in odd_run.results] == [5, 1]

    inner_executor, inner_run = run_directory_case(
        "inner-worker-floor",
        hazardous_sources["subprocess-run"],
        workers=6,
        maximum=8,
    )
    assert inner_executor.overlapped_broad is False
    assert [result.process_cost for result in inner_run.results] == [8, 1]

    from maid_runner.core import _artifact_coverage_fallback_worker as worker_module

    with pytest.MonkeyPatch.context() as monkeypatch:
        monkeypatch.setattr(
            worker_module,
            "_parallel_child_process_permits_available",
            lambda: False,
            raising=False,
        )
        unsupported_executor, unsupported_run = run_directory_case(
            "unsupported-permits",
            hazardous_sources["subprocess-run"],
        )
    unsupported_call = next(
        call[0] for call in unsupported_executor.calls if "tests/" in call[0]
    )
    assert "-n" not in unsupported_call
    assert unsupported_executor.overlapped_broad is False
    assert [result.process_cost for result in unsupported_run.results] == [8, 1]


def test_material_write_discards_entire_batch_and_preserves_later_reader_legacy_order(
    tmp_path,
):
    from maid_runner.core.artifact_coverage import (
        evaluate_artifact_coverage_from_evidence,
    )

    root = tmp_path / "project"
    manifests = _write_project(root)
    evidence = _incomplete_evidence(root, manifests)
    result = evaluate_artifact_coverage_from_evidence(
        manifests,
        root,
        evidence,
        fallback_executor=_RecordingExecutor(root, write=True),
        fallback_jobs=2,
        max_processes=2,
        snapshot_backend=_CopySnapshotBackend(tmp_path / "snapshots"),
    )

    assert result.serial_fallback_identities == _identities(manifests)
    assert result.isolated_fallback_identities == ()
    assert result.isolated_material_project_writes
    assert result.isolated_worker_errors == ()
    assert (root / "reader-observed.txt").read_text() == "alpha"

    (root / ".venv").mkdir()

    class DependencyWritingExecutor(_RecordingExecutor):
        def execute(self, *args, **kwargs):
            project_root = Path(args[2])
            (project_root / ".venv" / "command-state.txt").write_text("changed")
            return super().execute(*args, **kwargs)

    dependency_run = evaluate_artifact_coverage_from_evidence(
        manifests,
        root,
        evidence,
        fallback_executor=DependencyWritingExecutor(root),
        fallback_jobs=2,
        max_processes=2,
        snapshot_backend=_CopySnapshotBackend(tmp_path / "dependency-snapshots"),
    )
    assert dependency_run.serial_fallback_identities == _identities(manifests)

    class FailingSnapshotBackend:
        @contextmanager
        def create(self, *args):
            raise RuntimeError("snapshot failed")
            yield

    failed_run = evaluate_artifact_coverage_from_evidence(
        manifests,
        root,
        evidence,
        fallback_executor=_RecordingExecutor(root),
        fallback_jobs=2,
        max_processes=2,
        snapshot_backend=FailingSnapshotBackend(),
    )
    assert failed_run.serial_fallback_identities == _identities(manifests)
    assert failed_run.isolated_worker_errors
    assert failed_run.isolated_material_project_writes == ()


def test_nonzero_isolated_command_discards_batch_for_exact_serial_failure_semantics(
    tmp_path,
):
    from maid_runner.core._artifact_coverage_fallback_worker import (
        run_isolated_artifact_coverage_fallbacks,
    )

    root = tmp_path / "project"
    identities = _identities(_write_project(root))

    class FailingExecutor(_RecordingExecutor):
        def execute(self, *args, **kwargs):
            return replace(super().execute(*args, **kwargs), returncode=1)

    run = run_isolated_artifact_coverage_fallbacks(
        identities,
        root,
        _targets(root, identities),
        _CopySnapshotBackend(tmp_path / "snapshots"),
        FailingExecutor(root),
        jobs=2,
        max_processes=2,
    )

    assert run.serial_fallback_identities == identities


def test_worker_loss_snapshot_failure_or_path_remap_gap_is_never_clean_success(
    tmp_path,
):
    from maid_runner.core._artifact_coverage_fallback_worker import (
        run_isolated_artifact_coverage_fallbacks,
    )

    root = tmp_path / "project"
    identities = _identities(_write_project(root))

    class EscapingExecutor(_RecordingExecutor):
        def execute(
            self, command, target_files, project_root, timeout_seconds, *environment
        ):
            record = super().execute(
                command, target_files, project_root, timeout_seconds, *environment
            )
            return replace(
                record,
                execution_data={
                    str((tmp_path / "outside.py").resolve()): RuntimeFileExecution(
                        frozenset({1}), frozenset({"outside"})
                    )
                },
            )

    class FailingSnapshotBackend:
        @contextmanager
        def create(self, *args):
            raise RuntimeError("snapshot failed")
            yield

    class LostExecutor(_RecordingExecutor):
        def execute(self, *args, **kwargs):
            raise RuntimeError("worker lost")

    cases = (
        (_CopySnapshotBackend(tmp_path / "remap-snapshots"), EscapingExecutor(root)),
        (FailingSnapshotBackend(), _RecordingExecutor(root)),
        (_CopySnapshotBackend(tmp_path / "lost-snapshots"), LostExecutor(root)),
    )
    for backend, executor in cases:
        run = run_isolated_artifact_coverage_fallbacks(
            identities,
            root,
            _targets(root, identities),
            backend,
            executor,
            jobs=2,
            max_processes=2,
        )

        assert run.serial_fallback_identities == identities
        assert any(result.errors for result in run.results)
        assert all(
            error.code.value in {"E712", "E900"}
            for result in run.results
            for error in result.errors
        )


def test_command_config_and_auto_xdist_counts_reduce_fallback_jobs(tmp_path):
    from maid_runner.core._artifact_coverage_fallback_worker import (
        run_isolated_artifact_coverage_fallbacks,
    )

    root = tmp_path / "project"
    manifests = _write_project(root)
    identities = tuple(
        replace(identity, command=(*identity.command, "-n2"))
        for identity in _identities(manifests)
    )
    executor = _RecordingExecutor(root, delays={"alpha": 0.04, "beta": 0.04})
    run = run_isolated_artifact_coverage_fallbacks(
        identities,
        root,
        _targets(root, identities),
        _CopySnapshotBackend(tmp_path / "snapshots"),
        executor,
        jobs=2,
        max_processes=2,
    )

    assert executor.peak == 1
    assert [result.process_cost for result in run.results] == [2, 2]

    (root / "pyproject.toml").write_text('[tool.pytest.ini_options]\naddopts = "-n2"\n')
    configured_executor = _RecordingExecutor(root, delays={"alpha": 0.04, "beta": 0.04})
    configured_run = run_isolated_artifact_coverage_fallbacks(
        _identities(manifests),
        root,
        _targets(root, _identities(manifests)),
        _CopySnapshotBackend(tmp_path / "configured-snapshots"),
        configured_executor,
        jobs=2,
        max_processes=2,
    )
    assert configured_executor.peak == 1
    assert [result.process_cost for result in configured_run.results] == [2, 2]

    auto = tuple(
        replace(identity, command=(*identity.command, "-nauto"))
        for identity in _identities(manifests)
    )
    auto_run = run_isolated_artifact_coverage_fallbacks(
        auto,
        root,
        _targets(root, auto),
        _CopySnapshotBackend(tmp_path / "auto-snapshots"),
        _RecordingExecutor(root),
        jobs=2,
        max_processes=2,
    )
    assert auto_run.serial_fallback_identities == auto
    assert any(result.errors for result in auto_run.results)


def test_identical_selectors_deduplicate_with_accepted_inner_xdist(tmp_path):
    from maid_runner.core._artifact_coverage_fallback_worker import (
        run_isolated_artifact_coverage_fallbacks,
    )

    root = tmp_path / "project"
    manifests = _write_project(root)
    identities = tuple(
        replace(identity, command=("pytest", "tests/", "-q"))
        for identity in _identities(manifests)
    )
    (root / ".maidrc.yaml").write_text(
        "test_execution:\n"
        "  pytest_workers: 2\n"
        "  pytest_dist_mode: loadscope\n"
        "  accepted_pytest_worker_counts: [2]\n"
        "  max_processes: 4\n"
        "artifact_coverage:\n"
        "  fallback_jobs: 2\n"
    )
    executor = _RecordingExecutor(root)
    run = run_isolated_artifact_coverage_fallbacks(
        identities,
        root,
        _targets(root, identities),
        _CopySnapshotBackend(tmp_path / "snapshots"),
        executor,
        jobs=2,
        max_processes=4,
    )

    assert len(executor.calls) == 1
    assert executor.calls[0][0][-4:] == ("-n", "2", "--dist", "loadscope")
    assert [result.identity for result in run.results] == list(identities)
    assert [result.process_cost for result in run.results] == [2, 2]
    assert run.serial_fallback_identities == ()


def test_pinned_xdist_workers_return_target_calls_and_lines(tmp_path):
    from maid_runner.core._artifact_coverage_fallback_worker import (
        run_isolated_artifact_coverage_fallbacks,
    )
    from maid_runner.core._knockout_snapshot import (
        MaterializedProjectSnapshotBackend,
    )
    from maid_runner.core._runtime_command_executor import (
        SubprocessRuntimeCommandExecutor,
    )

    root = tmp_path / "project"
    manifests = _write_project(root)
    (root / "conftest.py").write_text(
        "import os\n"
        "import subprocess\n"
        "import sys\n"
        "import time\n"
        "from subprocess import Popen as EARLY_POPEN\n"
        "from pathlib import Path\n\n"
        "import pytest\n\n"
        "def append_interval(name, phase):\n"
        "    path = Path('.pytest_cache/maid-intervals')\n"
        "    path.parent.mkdir(exist_ok=True)\n"
        "    fd = os.open(path, os.O_APPEND | os.O_CREAT | os.O_WRONLY, 0o600)\n"
        "    try:\n"
        "        os.write(fd, f'{name}:{phase}:{time.monotonic_ns()}\\n'.encode())\n"
        "    finally:\n"
        "        os.close(fd)\n\n"
        "def pytest_sessionstart(session):\n"
        "    if not os.environ.get('PYTEST_XDIST_WORKER'):\n"
        "        return\n"
        "    assert os.environ.get('PYTEST_PLUGINS') == "
        "'maid_runner.core.result,maid_runner.core.types'\n"
        "    assert not any(name.startswith('MAID_ARTIFACT_') for name in os.environ)\n"
        "    assert getattr(subprocess.Popen, '_maid_child_process_permits', False)\n"
        "    assert getattr(EARLY_POPEN, '_maid_child_process_permits', False)\n"
        "    process = EARLY_POPEN([sys.executable, '-c', 'pass'])\n"
        "    assert process.wait() == 0\n"
        "    os.environ['CONSUMER_PLUGIN_SESSIONSTART'] = 'seen'\n"
        "\ndef pytest_sessionfinish(session, exitstatus):\n"
        "    if os.environ.get('PYTEST_XDIST_WORKER'):\n"
        "        return\n"
        "    lines = Path('.pytest_cache/maid-intervals').read_text().splitlines()\n"
        "    events = {}\n"
        "    for line in lines:\n"
        "        name, phase, value = line.split(':')\n"
        "        events.setdefault(name, {})[phase] = int(value)\n"
        "    def overlaps(left, right):\n"
        "        return max(events[left]['start'], events[right]['start']) < "
        "min(events[left]['end'], events[right]['end'])\n"
        "    assert overlaps('safe-alpha', 'safe-beta')\n"
        "    hazards = ['test_hazard_one', 'test_hazard_two', "
        "'test_fixture_one', 'test_fixture_two']\n"
        "    points = sorted((events[name][phase], 1 if phase == 'start' else -1) "
        "for name in hazards for phase in ('start', 'end'))\n"
        "    active = peak = 0\n"
        "    for _, delta in points:\n"
        "        active += delta\n"
        "        peak = max(peak, active)\n"
        "    assert peak == 2\n"
    )
    interval_helper = (
        "import os, time\n"
        "from pathlib import Path\n\n"
        "def record(name):\n"
        "    path = Path('.pytest_cache/maid-intervals')\n"
        "    path.parent.mkdir(exist_ok=True)\n"
        "    def append(phase):\n"
        "        fd = os.open(path, os.O_APPEND | os.O_CREAT | os.O_WRONLY, 0o600)\n"
        "        try:\n"
        "            os.write(fd, f'{name}:{phase}:{time.monotonic_ns()}\\n'.encode())\n"
        "        finally:\n"
        "            os.close(fd)\n"
        "    ready = path.with_name(f'{name}.ready')\n"
        "    ready.touch()\n"
        "    deadline = time.monotonic() + 5\n"
        "    while len(tuple(path.parent.glob('safe-*.ready'))) < 2:\n"
        "        assert time.monotonic() < deadline\n"
        "        time.sleep(0.01)\n"
        "    append('start')\n"
        "    time.sleep(0.05)\n"
        "    append('end')\n"
    )
    (root / "tests/test_alpha.py").write_text(
        interval_helper + "\nfrom src.alpha import alpha\n\n"
        "def test_alpha():\n"
        "    assert os.environ.get('CONSUMER_PLUGIN_SESSIONSTART') == 'seen'\n"
        "    record('safe-alpha')\n"
        "    assert alpha() == 'alpha'\n"
    )
    (root / "tests/test_beta.py").write_text(
        interval_helper + "\nfrom src.beta import beta\n\n"
        "def test_beta():\n"
        "    assert os.environ.get('CONSUMER_PLUGIN_SESSIONSTART') == 'seen'\n"
        "    record('safe-beta')\n"
        "    assert beta() == 'beta'\n"
    )
    direct_hazard = root / "tests/direct_hazard"
    direct_hazard.mkdir()
    child_helper = (
        "import subprocess, sys\n"
        "from pathlib import Path\n\n"
        "def run_child(name):\n"
        "    Path('.pytest_cache').mkdir(exist_ok=True)\n"
        '    code = ("import os,sys,time; from pathlib import Path; "\n'
        '        "p=Path(sys.argv[1]); n=sys.argv[2]; "\n'
        '        "fd=os.open(p, os.O_APPEND|os.O_CREAT|os.O_WRONLY, 0o600); "\n'
        "        \"os.write(fd, f'{n}:start:{time.monotonic_ns()}\\\\n'.encode()); os.close(fd); \"\n"
        '        "time.sleep(0.05); "\n'
        '        "fd=os.open(p, os.O_APPEND|os.O_CREAT|os.O_WRONLY, 0o600); "\n'
        "        \"os.write(fd, f'{n}:end:{time.monotonic_ns()}\\\\n'.encode()); os.close(fd)\")\n"
        "    subprocess.run([sys.executable, '-c', code, "
        "'.pytest_cache/maid-intervals', name], check=True)\n\n"
    )
    (direct_hazard / "test_hazard.py").write_text(
        child_helper + "from src.alpha import alpha\n\n"
        "def test_hazard_one():\n"
        "    run_child('test_hazard_one')\n"
        "    assert alpha() == 'alpha'\n"
    )
    (direct_hazard / "test_hazard_two.py").write_text(
        child_helper + "from src.beta import beta\n\n"
        "def test_hazard_two():\n"
        "    run_child('test_hazard_two')\n"
        "    assert beta() == 'beta'\n"
    )
    fixture_hazard = root / "tests/fixture_hazard"
    fixture_hazard.mkdir()
    (fixture_hazard / "test_fixture_one.py").write_text(
        child_helper + "import pytest\n\n"
        "@pytest.fixture(autouse=True)\n"
        "def nested_fixture():\n"
        "    run_child('test_fixture_one')\n"
        "    yield\n"
        "    subprocess.run([sys.executable, '-c', 'pass'], check=True)\n\n"
        "def test_fixture_one():\n    assert True\n"
    )
    (fixture_hazard / "test_fixture_two.py").write_text(
        child_helper + "import pytest\n\n"
        "@pytest.fixture(autouse=True)\n"
        "def nested_fixture():\n"
        "    run_child('test_fixture_two')\n"
        "    yield\n"
        "    subprocess.run([sys.executable, '-c', 'pass'], check=True)\n\n"
        "def test_fixture_two():\n    assert True\n"
    )
    identities = tuple(
        replace(identity, command=("pytest", "tests/", "-q"))
        for identity in _identities(manifests)
    )
    (root / ".maidrc.yaml").write_text(
        "test_execution:\n"
        "  pytest_workers: 3\n"
        "  pytest_dist_mode: loadscope\n"
        "  accepted_pytest_worker_counts: [3]\n"
        "  max_processes: 8\n"
        "artifact_coverage:\n"
        "  fallback_jobs: 2\n"
    )
    target_files = _targets(root, identities)
    with pytest.MonkeyPatch.context() as monkeypatch:
        monkeypatch.setenv("COVERAGE_CORE", "sysmon")
        monkeypatch.setenv(
            "PYTEST_PLUGINS",
            "maid_runner.core.result,maid_runner.core.types",
        )
        run = run_isolated_artifact_coverage_fallbacks(
            identities,
            root,
            target_files,
            MaterializedProjectSnapshotBackend(),
            SubprocessRuntimeCommandExecutor(),
            jobs=2,
            max_processes=8,
        )

    assert run.serial_fallback_identities == ()
    execution = {
        Path(path).stem: data
        for path, data in run.results[0].command_run.execution_data.items()
    }
    assert execution["alpha"].executed_lines
    assert execution["beta"].executed_lines
    assert "alpha" in execution["alpha"].called_qualnames
    assert "beta" in execution["beta"].called_qualnames


def test_generated_xdist_child_process_permits_fail_closed_and_release(
    tmp_path, monkeypatch
):
    import os
    import subprocess
    import sys
    import threading
    import time
    from contextlib import contextmanager

    from maid_runner.core._runtime_command_executor import (
        _coverage_worker_plugin_source,
    )

    target_manifest = tmp_path / "targets.json"
    target_manifest.write_text("[]")
    call_directory = tmp_path / "calls"
    call_directory.mkdir()
    monkeypatch.setenv("MAID_ARTIFACT_TARGET_FILES", str(target_manifest))
    monkeypatch.setenv("MAID_ARTIFACT_CALL_DIRECTORY", str(call_directory))
    coverage_data = tmp_path / ".coverage"
    monkeypatch.setenv("MAID_ARTIFACT_COVERAGE_DATA", str(coverage_data))
    monkeypatch.setenv(
        "PYTEST_PLUGINS",
        "maid_runner.core.result,_maid_artifact_coverage_worker,maid_runner.core.types",
    )
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("PYTEST_XDIST_WORKER", raising=False)
    monkeypatch.delenv("PYTEST_XDIST_WORKER_COUNT", raising=False)

    original_popen = subprocess.Popen
    controller_namespace = {}
    exec(_coverage_worker_plugin_source(), controller_namespace)
    assert subprocess.Popen is original_popen
    assert {
        name: value
        for name, value in os.environ.items()
        if name.startswith("MAID_ARTIFACT_")
    } == {
        "MAID_ARTIFACT_TARGET_FILES": str(target_manifest),
        "MAID_ARTIFACT_CALL_DIRECTORY": str(call_directory),
        "MAID_ARTIFACT_COVERAGE_DATA": str(coverage_data),
    }
    assert os.environ["PYTEST_PLUGINS"] == (
        "maid_runner.core.result,_maid_artifact_coverage_worker,maid_runner.core.types"
    )

    monkeypatch.setenv("PYTEST_XDIST_WORKER", "gw0")
    namespace = {}
    exec(_coverage_worker_plugin_source(), namespace)
    assert getattr(subprocess.Popen, "_maid_child_process_permits", False)
    assert os.environ["PYTEST_PLUGINS"] == (
        "maid_runner.core.result,maid_runner.core.types"
    )
    assert not any(name.startswith("MAID_ARTIFACT_") for name in os.environ)
    monkeypatch.setattr(subprocess, "Popen", original_popen)
    permit_pool_class = namespace["_ChildProcessPermitPool"]
    wrapped_popen = namespace["_permit_wrapped_popen"]

    pool = permit_pool_class(call_directory, permits=2)
    first = pool.acquire()
    second = pool.acquire()
    first.__enter__()
    second.__enter__()
    acquired_third = threading.Event()

    def acquire_third():
        with pool.acquire():
            acquired_third.set()

    thread = threading.Thread(target=acquire_third)
    thread.start()
    time.sleep(0.05)
    assert acquired_third.is_set() is False
    first.__exit__(None, None, None)
    assert acquired_third.wait(1)
    second.__exit__(None, None, None)
    thread.join()

    class RecordingPool:
        def __init__(self):
            self.active = 0

        @contextmanager
        def acquire(self):
            self.active += 1
            try:
                yield
            finally:
                self.active -= 1

    class FakePopen:
        def __init__(self, *, fail=False):
            if fail:
                raise OSError("spawn failed")
            self.returncode = None
            self.done = threading.Event()

        def wait(self, *args, **kwargs):
            self.done.wait(1)
            self.returncode = 0
            return 0

        def communicate(self, *args, **kwargs):
            self.done.set()
            self.returncode = 0
            return (b"", b"")

        def poll(self):
            if self.done.is_set():
                self.returncode = 0
            return self.returncode

        def __enter__(self):
            return self

        def __exit__(self, *args):
            self.wait()

    recording = RecordingPool()
    WrappedPopen = wrapped_popen(FakePopen, recording)
    process = WrappedPopen()
    assert recording.active == 1
    assert process.poll() is None
    assert recording.active == 1
    process.done.set()
    assert process.poll() == 0
    deadline = time.monotonic() + 1
    while recording.active:
        assert time.monotonic() < deadline
        time.sleep(0.01)
    process.wait()
    assert recording.active == 0
    process.communicate()
    process.poll()
    process.__exit__(None, None, None)
    assert recording.active == 0
    process = WrappedPopen()
    process.communicate()
    assert recording.active == 0
    with WrappedPopen() as process:
        assert recording.active == 1
        process.done.set()
    assert recording.active == 0
    with pytest.raises(OSError, match="spawn failed"):
        WrappedPopen(fail=True)
    assert recording.active == 0

    actual_pool = permit_pool_class(call_directory, permits=2)
    ActualPopen = wrapped_popen(subprocess.Popen, actual_pool)
    first_unobserved = ActualPopen(
        (sys.executable, "-c", "import time; time.sleep(0.03)")
    )
    second_unobserved = ActualPopen(
        (sys.executable, "-c", "import time; time.sleep(0.03)")
    )
    replacements_ready = threading.Barrier(3, timeout=2)
    replacement_sentinel = tmp_path / "release-replacements"
    replacement_errors = []

    def launch_after_unobserved_exit():
        try:
            process = ActualPopen(
                (
                    sys.executable,
                    "-c",
                    "import pathlib,sys,time; p=pathlib.Path(sys.argv[1]); "
                    "deadline=time.monotonic()+5; "
                    'exec("while not p.exists():\\n assert time.monotonic() < deadline\\n time.sleep(0.01)")',
                    str(replacement_sentinel),
                )
            )
            replacements_ready.wait()
            process.wait()
        except BaseException as exc:
            replacement_errors.append(exc)

    launch_threads = [
        threading.Thread(target=launch_after_unobserved_exit) for _ in range(2)
    ]
    for launch_thread in launch_threads:
        launch_thread.start()
    replacements_ready.wait()
    replacement_sentinel.touch()
    for launch_thread in launch_threads:
        launch_thread.join(2)
        assert launch_thread.is_alive() is False
    assert replacement_errors == []
    assert first_unobserved.returncode == 0
    assert second_unobserved.returncode == 0

    from maid_runner.core._artifact_coverage_fallback_worker import (
        run_isolated_artifact_coverage_fallbacks,
    )
    from maid_runner.core._knockout_snapshot import (
        MaterializedProjectSnapshotBackend,
    )
    from maid_runner.core._runtime_command_executor import (
        SubprocessRuntimeCommandExecutor,
    )

    import_root = tmp_path / "import-time-conftest-project"
    import_manifests = _write_project(import_root, ("alpha",))
    (import_root / "tests/conftest.py").write_text(
        "import subprocess, sys\n"
        'code = ("import os; "\n'
        "    \"assert not any(n.startswith('MAID_ARTIFACT_') for n in os.environ); \"\n"
        "    \"assert '_maid_artifact_coverage_worker' not in os.environ.get('PYTEST_PLUGINS', '')\")\n"
        "completed = subprocess.run([sys.executable, '-c', code])\n"
        "assert completed.returncode == 0\n"
    )
    import_identities = _identities(import_manifests)
    import_run = run_isolated_artifact_coverage_fallbacks(
        import_identities,
        import_root,
        _targets(import_root, import_identities),
        MaterializedProjectSnapshotBackend(),
        SubprocessRuntimeCommandExecutor(),
        jobs=2,
        max_processes=8,
    )
    assert import_run.serial_fallback_identities == ()
    assert import_run.results[0].command_run.returncode == 0
    assert "-n" not in import_run.results[0].command_run.command

    class FailingFcntl:
        LOCK_EX = 2
        LOCK_NB = 4
        LOCK_UN = 8

        @staticmethod
        def flock(*args):
            raise OSError("permit lock failed")

    monkeypatch.setitem(namespace, "fcntl", FailingFcntl)
    with pytest.raises(OSError, match="permit lock failed"):
        with permit_pool_class(call_directory, permits=2).acquire():
            pass

    try:
        import fcntl as _fcntl
    except ImportError:
        return
    assert _fcntl.flock is not None
    monkeypatch.setitem(namespace, "fcntl", _fcntl)
    plugin_path = tmp_path / "artifact_worker_plugin.py"
    plugin_path.write_text(_coverage_worker_plugin_source())
    crash = tmp_path / "crash.py"
    crash.write_text(
        "import importlib.util, os, pathlib\n"
        f"spec = importlib.util.spec_from_file_location('worker', {str(plugin_path)!r})\n"
        "module = importlib.util.module_from_spec(spec)\n"
        "spec.loader.exec_module(module)\n"
        f"pool = module._ChildProcessPermitPool(pathlib.Path({str(call_directory)!r}), 2)\n"
        "with pool.acquire():\n    os._exit(0)\n"
    )
    crash_environment = dict(os.environ)
    crash_environment.update(
        {
            "MAID_ARTIFACT_TARGET_FILES": str(target_manifest),
            "MAID_ARTIFACT_CALL_DIRECTORY": str(call_directory),
            "MAID_ARTIFACT_COVERAGE_DATA": str(coverage_data),
        }
    )
    crash_environment.pop("PYTEST_XDIST_WORKER", None)
    completed = subprocess.run((sys.executable, str(crash)), env=crash_environment)
    assert completed.returncode == 0
    crash_pool = permit_pool_class(call_directory, permits=2)
    with crash_pool.acquire(), crash_pool.acquire():
        pass


def test_one_fallback_worker_preserves_legacy_execution(tmp_path):
    from maid_runner.core.artifact_coverage import (
        evaluate_artifact_coverage_from_evidence,
    )

    root = tmp_path / "project"
    manifests = _write_project(root)
    evidence = _incomplete_evidence(root, manifests)
    executor = _RecordingExecutor(root)
    result = evaluate_artifact_coverage_from_evidence(
        manifests, root, evidence, fallback_executor=executor, fallback_jobs=1
    )

    assert [call[1] for call in executor.calls] == [root, root]
    assert result.serial_fallback_identities == _identities(manifests)
    assert result.isolated_fallback_identities == ()


def test_worker_run_discloses_parallel_and_serial_fallback_identities(tmp_path):
    from maid_runner.core._artifact_coverage_fallback_worker import (
        ArtifactCoverageFallbackRun,
        ArtifactCoverageFallbackWorkerResult,
    )

    identity = RuntimeCommandIdentity("manifests/a.manifest.yaml", 0, ("pytest",))
    worker = ArtifactCoverageFallbackWorkerResult(identity, None, (), 1, ())
    run = ArtifactCoverageFallbackRun((worker,), (identity,))

    assert run.results == (worker,)
    assert run.serial_fallback_identities == (identity,)
    assert worker.identity == identity
    assert worker.command_run is None
    assert worker.material_project_writes == ()
    assert worker.process_cost == 1
    assert worker.errors == ()


def test_grouped_runtime_evidence_collapses_dominated_selectors_without_losing_projection(
    tmp_path,
):
    from maid_runner.core.runtime_evidence import (
        RuntimeContextEvidence,
        RuntimeEvidenceCompleteness,
        RuntimeGroupEvidence,
        collect_runtime_evidence,
    )

    manifests = _write_project(tmp_path, ("alpha", "beta", "gamma"))
    manifests = (
        replace(
            manifests[0],
            validate_commands=(("python", "-m", "pytest", "-q", "tests/"),),
        ),
        replace(
            manifests[1],
            validate_commands=(("python", "-m", "pytest", "-q", "tests/test_beta.py"),),
        ),
        replace(
            manifests[2],
            validate_commands=(
                (
                    "python",
                    "-m",
                    "pytest",
                    "-q",
                    "tests/test_gamma.py::test_gamma",
                ),
            ),
        ),
    )
    nodeids = tuple(
        f"tests/test_{name}.py::test_{name}" for name in ("alpha", "beta", "gamma")
    )

    class Executor:
        command = None
        logical_selectors = None

        def execute_with_contexts(self, command, target_files, *args, **kwargs):
            self.command = tuple(command)
            self.logical_selectors = kwargs.get("logical_selectors")
            return RuntimeGroupEvidence(
                command=tuple(command),
                selected_nodeids=nodeids,
                selector_nodeids={
                    "tests/": nodeids,
                    "tests/test_beta.py": (nodeids[1],),
                    "tests/test_gamma.py::test_gamma": (nodeids[2],),
                },
                contexts=tuple(
                    RuntimeContextEvidence(
                        context_id=f"node:{nodeid}",
                        kind="node",
                        consuming_nodeids=(nodeid,),
                        execution_data={},
                        lifecycle_equivalent=True,
                    )
                    for nodeid in nodeids
                ),
                result=RuntimeCommandRecord(tuple(command), 0, "", "", {}, ()),
                worker_ids=("main",),
                completeness=RuntimeEvidenceCompleteness(complete=True),
            )

    executor = Executor()
    run = collect_runtime_evidence(manifests, tmp_path, executor=executor)

    assert executor.command == ("python", "-m", "pytest", "tests/", "-q")
    assert executor.logical_selectors == (
        "tests/",
        "tests/test_beta.py",
        "tests/test_gamma.py::test_gamma",
    )
    assert [command.selected_nodeids for command in run.evidence.commands] == [
        nodeids,
        (nodeids[1],),
        (nodeids[2],),
    ]
    assert [command.identity.manifest_path for command in run.evidence.commands] == [
        manifest.source_path for manifest in manifests
    ]


def test_runtime_evidence_payload_contains_only_active_declared_python_targets(
    tmp_path,
):
    from maid_runner.core.runtime_evidence import _runtime_target_files

    manifests = _write_project(tmp_path)
    generated = tmp_path / ".claude-automation/session/generated.py"
    generated.parent.mkdir(parents=True)
    generated.write_text("GENERATED = True\n")
    build_output = tmp_path / "build/lib/generated.py"
    build_output.parent.mkdir(parents=True)
    build_output.write_text("GENERATED = True\n")
    undeclared = tmp_path / "src/undeclared.py"
    undeclared.write_text("UNDECLARED = True\n")

    targets = _runtime_target_files(manifests, tmp_path)

    assert targets == {
        str((tmp_path / "src/alpha.py").resolve()),
        str((tmp_path / "src/beta.py").resolve()),
    }


def test_only_digest_bound_approved_wide_fixture_reuses_evidence(tmp_path):
    import hashlib

    from maid_runner.core.artifact_coverage import (
        evaluate_artifact_coverage_from_evidence,
    )
    from maid_runner.core.runtime_evidence import collect_runtime_evidence

    manifests = _write_project(tmp_path)
    for name in ("alpha", "beta"):
        (tmp_path / f"tests/test_{name}.py").write_text(
            f"def test_{name}():\n"
            f"    from src.{name} import {name}\n"
            f"    assert {name}() == '{name}'\n"
        )
    conftest = tmp_path / "conftest.py"
    conftest.write_text(
        "import pytest\n\n"
        "@pytest.fixture(scope='session', autouse=True)\n"
        "def neutral_session():\n"
        "    yield\n"
    )
    unapproved = collect_runtime_evidence(manifests, tmp_path).evidence
    unapproved_result = evaluate_artifact_coverage_from_evidence(
        manifests, tmp_path, unapproved
    )

    assert unapproved_result.fallback_identities == tuple(
        command.identity for command in unapproved.commands
    )

    digest = hashlib.sha256(conftest.read_bytes()).hexdigest()
    (tmp_path / ".maidrc.yaml").write_text(
        "artifact_coverage:\n"
        "  fixture_lifecycle_approvals:\n"
        "    - context_id: 'fixture::neutral_session:session'\n"
        "      conftest_path: conftest.py\n"
        f"      sha256: '{digest}'\n"
    )
    approved = collect_runtime_evidence(manifests, tmp_path).evidence
    approved_result = evaluate_artifact_coverage_from_evidence(
        manifests, tmp_path, approved
    )

    assert approved_result.fallback_identities == ()
    assert all(report.success for report in approved_result.reports.values())
    from maid_runner.core.config import (
        ArtifactCoverageConfig,
        FixtureLifecycleApproval,
        load_config,
    )

    configured_coverage = load_config(tmp_path).artifact_coverage
    approval = configured_coverage.fixture_lifecycle_approvals[0]
    assert ArtifactCoverageConfig().fixture_lifecycle_approvals == ()
    assert isinstance(approval, FixtureLifecycleApproval)
    assert approval.context_id == "fixture::neutral_session:session"
    assert approval.conftest_path == "conftest.py"
    assert approval.sha256 == digest


def test_indirect_state_or_changed_wide_fixture_approval_falls_back(tmp_path):
    import hashlib

    from maid_runner.core.artifact_coverage import (
        evaluate_artifact_coverage_from_evidence,
    )
    from maid_runner.core.runtime_evidence import collect_runtime_evidence

    manifests = _write_project(tmp_path, ("alpha",))
    conftest = tmp_path / "conftest.py"
    conftest.write_text(
        "import os, pytest\n\n"
        "@pytest.fixture(scope='session', autouse=True)\n"
        "def indirect_state():\n"
        "    os.environ['INDIRECT_BRANCH'] = 'fixture'\n"
        "    yield\n"
        "    os.environ.pop('INDIRECT_BRANCH', None)\n"
    )
    (tmp_path / "tests/test_alpha.py").write_text(
        "import os\n"
        "from src.alpha import alpha\n\n"
        "def test_alpha():\n"
        "    assert os.environ['INDIRECT_BRANCH'] == 'fixture'\n"
        "    assert alpha() == 'alpha'\n"
    )
    digest = hashlib.sha256(conftest.read_bytes()).hexdigest()
    (tmp_path / ".maidrc.yaml").write_text(
        "artifact_coverage:\n"
        "  fixture_lifecycle_approvals:\n"
        "    - context_id: 'fixture::different_fixture:session'\n"
        "      conftest_path: conftest.py\n"
        f"      sha256: '{digest}'\n"
    )
    indirect = collect_runtime_evidence(manifests, tmp_path).evidence
    indirect_result = evaluate_artifact_coverage_from_evidence(
        manifests, tmp_path, indirect
    )

    assert indirect_result.fallback_identities == (indirect.commands[0].identity,)

    conftest.write_text(
        "import pytest\n"
        "from src.alpha import alpha\n\n"
        "@pytest.fixture(scope='session', autouse=True)\n"
        "def different_fixture():\n"
        "    yield\n"
        "    alpha()\n"
    )
    changed = collect_runtime_evidence(manifests, tmp_path).evidence
    changed_result = evaluate_artifact_coverage_from_evidence(
        manifests, tmp_path, changed
    )

    assert changed_result.fallback_identities == (changed.commands[0].identity,)


def test_deep_conftest_preflight_skips_speculative_evidence(tmp_path, monkeypatch):
    from maid_runner.cli.commands.verify import _collect_artifact_coverage_evidence
    from maid_runner.core import runtime_evidence

    _write_project(tmp_path, ("alpha",))
    (tmp_path / "conftest.py").write_text("# target-neutral project conftest\n")
    sentinel = object()
    observed = []

    def fake_collect(manifests, root, pytest_workers=None):
        observed.append((manifests, root, pytest_workers))
        return SimpleNamespace(evidence=sentinel)

    monkeypatch.setattr(runtime_evidence, "collect_runtime_evidence", fake_collect)

    evidence = _collect_artifact_coverage_evidence(
        tmp_path,
        "manifests",
        pytest_workers=8,
    )

    assert evidence is None
    assert observed == []
