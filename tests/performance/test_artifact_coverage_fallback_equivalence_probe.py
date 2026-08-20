"""Contract for the opt-in repository fallback-equivalence acceptance probe."""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace


def _safe_isolated_result(reports):
    return (
        reports,
        SimpleNamespace(
            fallback_identities=(),
            serial_fallback_identities=(),
            isolated_worker_errors=(),
            isolated_material_project_writes=(),
        ),
    )


def _safe_serial_result(reports):
    return reports, ()


def test_probe_rejects_report_or_order_difference(monkeypatch, tmp_path):
    from tools import check_artifact_coverage_fallback_equivalence as probe

    monkeypatch.setattr(
        probe,
        "_normalized_serial_reports",
        lambda root: _safe_serial_result(["serial"]),
    )
    monkeypatch.setattr(
        probe,
        "_normalized_grouped_reports",
        lambda root, jobs, maximum: _safe_isolated_result(["other"]),
    )

    assert probe.compare_serial_and_isolated_fallbacks(tmp_path, 2, 2, 10) == 1


def test_probe_enforces_budget_only_after_equivalence(monkeypatch, tmp_path):
    from tools import check_artifact_coverage_fallback_equivalence as probe

    monkeypatch.setattr(
        probe, "_normalized_serial_reports", lambda root: _safe_serial_result(["same"])
    )
    for slow_phase in range(3):
        calls = 0

        def isolated(root, jobs, maximum):
            nonlocal calls
            calls += 1
            return _safe_isolated_result(["same"])

        monkeypatch.setattr(probe, "_normalized_grouped_reports", isolated)
        timestamps = []
        current = 0.0
        for phase in range(3):
            timestamps.extend(
                (current, current + (11.0 if phase == slow_phase else 1.0))
            )
            current += 12.0
        moments = iter(timestamps)
        monkeypatch.setattr(probe.time, "monotonic", lambda: next(moments))

        assert probe.compare_serial_and_isolated_fallbacks(tmp_path, 2, 2, 10) == 1
        assert calls == slow_phase + 1


def test_probe_requires_three_fresh_equivalent_optimized_runs(monkeypatch, tmp_path):
    from tools import check_artifact_coverage_fallback_equivalence as probe

    monkeypatch.setattr(
        probe, "_normalized_serial_reports", lambda root: _safe_serial_result(["same"])
    )
    reports = iter(
        (
            _safe_isolated_result(["same"]),
            _safe_isolated_result(["same"]),
            _safe_isolated_result(["different"]),
        )
    )
    calls = 0

    def isolated(root, jobs, maximum):
        nonlocal calls
        calls += 1
        return next(reports)

    monkeypatch.setattr(probe, "_normalized_grouped_reports", isolated)
    moments = iter((0.0, 1.0, 1.0, 2.0, 2.0, 3.0))
    monkeypatch.setattr(probe.time, "monotonic", lambda: next(moments))

    assert probe.compare_serial_and_isolated_fallbacks(tmp_path, 2, 2, 10) == 1
    assert calls == 3


def test_probe_rejects_serial_replay_or_worker_diagnostics(monkeypatch, tmp_path):
    from tools import check_artifact_coverage_fallback_equivalence as probe

    monkeypatch.setattr(
        probe, "_normalized_serial_reports", lambda root: _safe_serial_result(["same"])
    )
    unsafe_results = (
        SimpleNamespace(
            fallback_identities=("exact",),
            serial_fallback_identities=("replayed",),
            isolated_worker_errors=(),
            isolated_material_project_writes=(),
        ),
        SimpleNamespace(
            fallback_identities=(),
            serial_fallback_identities=(),
            isolated_worker_errors=("worker failed",),
            isolated_material_project_writes=(),
        ),
        SimpleNamespace(
            fallback_identities=(),
            serial_fallback_identities=(),
            isolated_worker_errors=(),
            isolated_material_project_writes=("src/changed.py",),
        ),
    )

    for unsafe in unsafe_results:
        for unsafe_phase in range(3):
            calls = 0

            def isolated(root, jobs, maximum):
                nonlocal calls
                phase = calls
                calls += 1
                result = (
                    unsafe if phase == unsafe_phase else _safe_isolated_result([])[1]
                )
                return (["same"], result)

            monkeypatch.setattr(probe, "_normalized_grouped_reports", isolated)
            moments = iter((0.0, 1.0, 2.0, 3.0, 4.0, 5.0))
            monkeypatch.setattr(probe.time, "monotonic", lambda: next(moments))

            assert probe.compare_serial_and_isolated_fallbacks(tmp_path, 2, 2, 10) == 1
            assert calls == unsafe_phase + 1


def test_probe_rejects_errored_serial_oracle(monkeypatch, tmp_path):
    from tools import check_artifact_coverage_fallback_equivalence as probe

    monkeypatch.setattr(
        probe,
        "_normalized_serial_reports",
        lambda root: (["serial"], ("coverage command failed",)),
    )
    isolated_called = False

    def isolated(*args):
        nonlocal isolated_called
        isolated_called = True
        return _safe_isolated_result(["serial"])

    monkeypatch.setattr(probe, "_normalized_grouped_reports", isolated)

    assert probe.compare_serial_and_isolated_fallbacks(tmp_path, 2, 2, 10) == 1
    assert isolated_called is False


def test_serial_oracle_helper_extracts_artifact_coverage_errors(monkeypatch, tmp_path):
    from maid_runner.core.artifact_coverage import ArtifactCoverageReport
    from maid_runner.core.result import ErrorCode, ValidationError
    from tools import check_artifact_coverage_fallback_equivalence as probe

    error = ValidationError(ErrorCode.INTERNAL_ERROR, "oracle command failed")
    monkeypatch.setattr(probe, "_active_manifests", lambda root: ())
    monkeypatch.setattr(
        probe,
        "run_artifact_coverage_batch",
        lambda manifests, root, executor: {
            "manifests/failing.manifest.yaml": ArtifactCoverageReport((), (error,))
        },
    )

    normalized, errors = probe._normalized_serial_reports(tmp_path)

    assert normalized[0][0] == "manifests/failing.manifest.yaml"
    assert errors == (error,)


def test_probe_never_recursively_runs_repository_acceptance_in_normal_suite(
    monkeypatch,
):
    from tools import check_artifact_coverage_fallback_equivalence as probe

    monkeypatch.setenv("PYTEST_CURRENT_TEST", "ordinary suite")
    called = False

    def compare(*args):
        nonlocal called
        called = True
        return 0

    monkeypatch.setattr(probe, "compare_serial_and_isolated_fallbacks", compare)

    assert probe.main(["--project-root", str(Path.cwd())]) == 0
    assert called is False


def test_serial_oracle_checkpoints_success_and_never_failure(tmp_path):
    from maid_runner.core._runtime_command_executor import RuntimeCommandRecord
    from tools import check_artifact_coverage_fallback_equivalence as probe

    class Executor:
        def __init__(self):
            self.calls = 0

        def execute(self, command, target_files, project_root, timeout_seconds):
            self.calls += 1
            return RuntimeCommandRecord(
                tuple(command),
                0 if command != ("fail",) else 1,
                "out",
                "err",
                {},
                (),
            )

    delegate = Executor()
    cached = probe._CheckpointingExecutor(delegate, tmp_path / "cache", "current")
    assert cached.execute(("ok",), set(), tmp_path, 1).returncode == 0
    assert cached.execute(("ok",), set(), tmp_path, 1).returncode == 0
    assert delegate.calls == 1

    assert cached.execute(("fail",), set(), tmp_path, 1).returncode == 1
    assert cached.execute(("fail",), set(), tmp_path, 1).returncode == 1
    assert delegate.calls == 3
