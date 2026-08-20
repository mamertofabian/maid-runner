"""Behavioral contract for routing the exact coverage batch through lanes.

Contract: manifests/drafts/121-19-route-exact-coverage-batch-through-isolated-lanes.manifest.yaml

The legacy shared-command batch is the production deep path. These tests pin
its routing behavior: one lane preserves the serial in-place loop, configured
lanes hand deduplicated unique commands to the injected isolated runner,
escalated identities replay in place, worker failures surface loudly, and the
execution summary is disclosed in reports only when isolated execution ran.
"""

from __future__ import annotations

from contextlib import contextmanager
from pathlib import Path


def test_default_config_keeps_single_lane_serial_in_place_execution(
    tmp_path: Path,
) -> None:
    from maid_runner.core.artifact_coverage import run_artifact_coverage_batch
    from maid_runner.core.manifest import load_manifest

    manifests = [load_manifest(path) for path in _write_two_manifest_project(tmp_path)]
    executor = _RecordingExecutor(_runtime_record(tmp_path, executed={"alpha", "beta"}))
    backend = _FakeSnapshotBackend()
    runner = _FakeIsolatedRunner(_empty_fallback_run())

    reports = run_artifact_coverage_batch(
        manifests,
        tmp_path,
        executor=executor,
        snapshot_backend=backend,
        isolated_runner=runner,
    )

    assert runner.calls == []
    assert backend.create_calls == []
    assert len(executor.calls) == 1
    assert executor.calls[0][2] == tmp_path
    assert all(report.success for report in reports.values())
    assert all(report.execution is None for report in reports.values())


def test_config_fallback_jobs_route_unique_commands_through_isolated_lanes(
    tmp_path: Path,
) -> None:
    from maid_runner.core.artifact_coverage import (
        ArtifactCoverageExecutionSummary,
        run_artifact_coverage_batch,
    )
    from maid_runner.core.manifest import load_manifest

    manifests = [
        load_manifest(path)
        for path in _write_two_manifest_project(
            tmp_path, fallback_jobs=2, max_processes=4
        )
    ]
    record = _runtime_record(tmp_path, executed={"alpha", "beta"})
    executor = _RecordingExecutor(record)
    fake_runner = _FakeIsolatedRunner(None)
    fake_runner.run_factory = lambda identities: _fallback_run_for(identities, record)

    reports = run_artifact_coverage_batch(
        manifests,
        tmp_path,
        executor=executor,
        snapshot_backend=_FakeSnapshotBackend(),
        isolated_runner=fake_runner,
    )

    assert len(fake_runner.calls) == 1
    identities, _root, target_files, _backend, _executor, jobs, max_processes = (
        fake_runner.calls[0]
    )
    assert len(identities) == 1
    assert identities[0].command == (
        "python",
        "-m",
        "pytest",
        "-q",
        "tests/test_targets.py",
    )
    expected_targets = {
        str((tmp_path / "src" / "alpha.py").resolve()),
        str((tmp_path / "src" / "beta.py").resolve()),
    }
    assert target_files[identities[0]] == expected_targets
    assert (jobs, max_processes) == (2, 4)
    assert executor.calls == []
    assert all(report.success for report in reports.values())
    summaries = {report.execution for report in reports.values()}
    assert len(summaries) == 1
    summary = summaries.pop()
    assert isinstance(summary, ArtifactCoverageExecutionSummary)
    assert summary.command_count == 1
    assert summary.isolated_count == 1
    assert summary.serial_count == 0
    assert summary.lane_count == 2


def test_explicit_jobs_one_overrides_config_and_never_touches_snapshots(
    tmp_path: Path,
) -> None:
    from maid_runner.core.artifact_coverage import run_artifact_coverage_batch
    from maid_runner.core.manifest import load_manifest

    manifests = [
        load_manifest(path)
        for path in _write_two_manifest_project(
            tmp_path, fallback_jobs=4, max_processes=8
        )
    ]
    executor = _RecordingExecutor(_runtime_record(tmp_path, executed={"alpha", "beta"}))
    backend = _FakeSnapshotBackend()
    runner = _FakeIsolatedRunner(_empty_fallback_run())

    reports = run_artifact_coverage_batch(
        manifests,
        tmp_path,
        executor=executor,
        jobs=1,
        snapshot_backend=backend,
        isolated_runner=runner,
    )

    assert runner.calls == []
    assert backend.create_calls == []
    assert len(executor.calls) == 1
    assert executor.calls[0][2] == tmp_path
    assert all(report.execution is None for report in reports.values())


def test_escalated_identities_replay_in_place_only_that_subset(
    tmp_path: Path,
) -> None:
    from maid_runner.core.artifact_coverage import run_artifact_coverage_batch
    from maid_runner.core.manifest import load_manifest

    manifests = [
        load_manifest(path)
        for path in _write_two_manifest_project(
            tmp_path,
            first_command="python -m pytest -q tests/test_targets.py -k alpha",
            second_command="python -m pytest -q tests/test_targets.py -k beta",
            fallback_jobs=2,
            max_processes=4,
        )
    ]
    isolated_record = _runtime_record(tmp_path, executed={"alpha"})
    replay_record = _runtime_record(tmp_path, executed={"beta"})
    executor = _RecordingExecutor(replay_record)
    fake_runner = _FakeIsolatedRunner(None)
    fake_runner.run_factory = lambda identities: _fallback_run_for(
        identities[:1], isolated_record, escalated=identities[1:]
    )

    reports = run_artifact_coverage_batch(
        manifests,
        tmp_path,
        executor=executor,
        snapshot_backend=_FakeSnapshotBackend(),
        isolated_runner=fake_runner,
    )

    assert len(executor.calls) == 1
    replay_args, _targets, replay_root, _timeout = executor.calls[0]
    assert "beta" in replay_args
    assert replay_root == tmp_path
    assert all(report.success for report in reports.values())
    summary = next(iter(reports.values())).execution
    assert summary is not None
    assert summary.command_count == 2
    assert summary.isolated_count == 1
    assert summary.serial_count == 1


def test_isolated_worker_errors_surface_in_affected_reports(
    tmp_path: Path,
) -> None:
    from maid_runner.core.artifact_coverage import run_artifact_coverage_batch
    from maid_runner.core.manifest import load_manifest

    manifests = [
        load_manifest(path)
        for path in _write_two_manifest_project(
            tmp_path, fallback_jobs=2, max_processes=4
        )
    ]
    executor = _RecordingExecutor(_runtime_record(tmp_path, executed={"alpha", "beta"}))
    fake_runner = _FakeIsolatedRunner(None)
    fake_runner.run_factory = lambda identities: _fallback_run_for(
        identities, record=None, errors=_worker_error()
    )

    reports = run_artifact_coverage_batch(
        manifests,
        tmp_path,
        executor=executor,
        snapshot_backend=_FakeSnapshotBackend(),
        isolated_runner=fake_runner,
    )

    assert reports
    for report in reports.values():
        assert not report.success
        assert any(
            "isolated artifact-coverage" in error.message for error in report.errors
        )


def test_execution_summary_serializes_only_when_present() -> None:
    from maid_runner.core.artifact_coverage import (
        ArtifactCoverageExecutionSummary,
        ArtifactCoverageReport,
    )

    summary = ArtifactCoverageExecutionSummary(
        command_count=3,
        isolated_count=2,
        serial_count=1,
        lane_count=4,
    )
    bare = ArtifactCoverageReport(findings=(), errors=())
    disclosed = ArtifactCoverageReport(findings=(), errors=(), execution=summary)

    assert bare.success and disclosed.success
    assert bare.findings == () and bare.errors == ()
    assert "execution" not in bare.to_dict()
    assert disclosed.to_dict()["execution"] == summary.to_dict()
    assert summary.to_dict() == {
        "command_count": 3,
        "isolated_count": 2,
        "serial_count": 1,
        "lane_count": 4,
    }
    description = summary.describe()
    assert isinstance(description, str)
    for fragment in ("3", "2", "1", "4"):
        assert fragment in description


def test_isolated_reports_match_serial_oracle_for_identical_records(
    tmp_path: Path,
) -> None:
    from maid_runner.core.artifact_coverage import run_artifact_coverage_batch
    from maid_runner.core.manifest import load_manifest

    manifests = [
        load_manifest(path)
        for path in _write_two_manifest_project(
            tmp_path, fallback_jobs=2, max_processes=4
        )
    ]
    record = _runtime_record(tmp_path, executed={"alpha", "beta"})

    oracle = run_artifact_coverage_batch(
        manifests,
        tmp_path,
        executor=_RecordingExecutor(record),
        jobs=1,
    )
    fake_runner = _FakeIsolatedRunner(None)
    fake_runner.run_factory = lambda identities: _fallback_run_for(identities, record)
    isolated = run_artifact_coverage_batch(
        manifests,
        tmp_path,
        executor=_RecordingExecutor(record),
        snapshot_backend=_FakeSnapshotBackend(),
        isolated_runner=fake_runner,
    )

    oracle_dicts = {path: report.to_dict() for path, report in oracle.items()}
    isolated_dicts = {}
    for path, report in isolated.items():
        payload = report.to_dict()
        payload.pop("execution")
        isolated_dicts[path] = payload
    assert isolated_dicts == oracle_dicts


def _runtime_record(root: Path, *, executed: set[str]):
    from maid_runner.core._runtime_command_executor import (
        RuntimeCommandRecord,
        RuntimeFileExecution,
    )

    return RuntimeCommandRecord(
        command=("-q", "tests/test_targets.py"),
        returncode=0,
        stdout="",
        stderr="",
        execution_data={
            str((root / "src" / "alpha.py").resolve()): RuntimeFileExecution(
                executed_lines=frozenset({2} if "alpha" in executed else set()),
                called_qualnames=(
                    frozenset({"alpha"}) if "alpha" in executed else frozenset()
                ),
            ),
            str((root / "src" / "beta.py").resolve()): RuntimeFileExecution(
                executed_lines=frozenset({2} if "beta" in executed else set()),
                called_qualnames=(
                    frozenset({"beta"}) if "beta" in executed else frozenset()
                ),
            ),
        },
        report_errors=(),
    )


def _worker_error():
    from maid_runner.core.result import ErrorCode, Severity, ValidationError

    return (
        ValidationError(
            code=ErrorCode.INTERNAL_ERROR,
            message="isolated artifact-coverage lane failed before execution",
            severity=Severity.ERROR,
        ),
    )


def _empty_fallback_run():
    from maid_runner.core._artifact_coverage_fallback_worker import (
        ArtifactCoverageFallbackRun,
    )

    return ArtifactCoverageFallbackRun(results=(), serial_fallback_identities=())


def _fallback_run_for(identities, record, *, escalated=(), errors=()):
    from maid_runner.core._artifact_coverage_fallback_worker import (
        ArtifactCoverageFallbackRun,
        ArtifactCoverageFallbackWorkerResult,
    )

    results = tuple(
        ArtifactCoverageFallbackWorkerResult(
            identity=identity,
            command_run=record,
            material_project_writes=(),
            process_cost=1,
            errors=tuple(errors),
        )
        for identity in identities
    )
    return ArtifactCoverageFallbackRun(
        results=results,
        serial_fallback_identities=tuple(escalated),
    )


class _RecordingExecutor:
    def __init__(self, record: object) -> None:
        self.record = record
        self.calls: list[tuple[tuple[str, ...], set[str], Path, float]] = []

    def execute(
        self,
        command: tuple[str, ...],
        target_files: set[str],
        project_root: Path,
        timeout_seconds: float,
    ) -> object:
        self.calls.append((command, set(target_files), project_root, timeout_seconds))
        return self.record


class _FakeSnapshotBackend:
    def __init__(self) -> None:
        self.create_calls: list[tuple[Path, tuple[str, ...], str]] = []

    @contextmanager
    def create(self, project_root: Path, required, worker_id: str):
        self.create_calls.append((project_root, tuple(required), worker_id))
        yield type("_Snapshot", (), {"root": project_root})()


class _FakeIsolatedRunner:
    def __init__(self, run: object) -> None:
        self._run = run
        self.run_factory = None
        self.calls: list[tuple] = []

    def __call__(
        self,
        identities,
        project_root,
        target_files,
        snapshot_backend,
        executor,
        jobs,
        max_processes,
    ):
        self.calls.append(
            (
                tuple(identities),
                project_root,
                dict(target_files),
                snapshot_backend,
                executor,
                jobs,
                max_processes,
            )
        )
        if self.run_factory is not None:
            return self.run_factory(tuple(identities))
        return self._run


def _write_two_manifest_project(
    root: Path,
    *,
    first_command: str = "python -m pytest -q tests/test_targets.py",
    second_command: str = "python -m pytest -q tests/test_targets.py",
    fallback_jobs: int | None = None,
    max_processes: int | None = None,
) -> tuple[Path, Path]:
    (root / "src").mkdir()
    (root / "tests").mkdir()
    (root / "manifests").mkdir()
    (root / "src" / "__init__.py").write_text("")
    (root / "src" / "alpha.py").write_text('def alpha() -> str:\n    return "alpha"\n')
    (root / "src" / "beta.py").write_text('def beta() -> str:\n    return "beta"\n')
    (root / "tests" / "test_targets.py").write_text(
        "from src.alpha import alpha\n"
        "from src.beta import beta\n\n"
        "def test_alpha():\n"
        '    assert alpha() == "alpha"\n\n'
        "def test_beta():\n"
        '    assert beta() == "beta"\n'
    )
    if fallback_jobs is not None:
        (root / ".maidrc.yaml").write_text(
            "artifact_coverage:\n"
            f"  fallback_jobs: {fallback_jobs}\n"
            "test_execution:\n"
            f"  max_processes: {max_processes or fallback_jobs}\n"
        )
    first = _write_manifest(root, "alpha", "alpha", first_command)
    second = _write_manifest(root, "beta", "beta", second_command)
    return first, second


def _write_manifest(root: Path, slug: str, function_name: str, command: str) -> Path:
    path = root / "manifests" / f"{slug}.manifest.yaml"
    path.write_text(
        f"""schema: "2"
goal: "Cover {function_name}"
type: feature
created: "2026-08-13T00:00:00Z"
files:
  edit:
    - path: src/{function_name}.py
      artifacts:
        - kind: function
          name: {function_name}
          args: []
          returns: str
  read:
    - tests/test_targets.py
validate:
  - {command}
"""
    )
    return path
