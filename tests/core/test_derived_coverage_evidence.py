"""Behavioral contract for derived coverage evidence and approval-aware preflight.

Contract: manifests/drafts/121-23-default-derived-coverage-evidence.manifest.yaml
"""

from __future__ import annotations

import hashlib
from pathlib import Path
from types import SimpleNamespace

from maid_runner.core.manifest import load_manifest
from maid_runner.core.runtime_evidence import RuntimeCommandIdentity


def test_grouped_evidence_preflight_allows_digest_matching_approvals(
    tmp_path: Path,
) -> None:
    from maid_runner.core.runtime_evidence import grouped_evidence_preflight

    conftest = tmp_path / "conftest.py"
    conftest.write_text("# approved project conftest\n")
    _write_approvals(tmp_path, conftest, mode="derived")

    assert grouped_evidence_preflight(tmp_path, evidence_mode="derived") is True


def test_grouped_evidence_preflight_rejects_unapproved_conftest(
    tmp_path: Path,
) -> None:
    from maid_runner.core.runtime_evidence import grouped_evidence_preflight

    (tmp_path / "conftest.py").write_text("# unapproved\n")
    (tmp_path / ".maidrc.yaml").write_text(
        "artifact_coverage:\n  evidence_mode: derived\n"
    )

    assert grouped_evidence_preflight(tmp_path, evidence_mode="derived") is False


def test_exact_mode_preflight_rejects_any_in_tree_conftest(tmp_path: Path) -> None:
    from maid_runner.core.runtime_evidence import grouped_evidence_preflight

    conftest = tmp_path / "conftest.py"
    conftest.write_text("# would be approved in derived mode\n")
    _write_approvals(tmp_path, conftest, mode="exact")

    assert grouped_evidence_preflight(tmp_path, evidence_mode="exact") is False


def test_approved_conftest_collects_grouped_evidence(
    tmp_path: Path, monkeypatch
) -> None:
    from maid_runner.cli.commands.verify import _collect_artifact_coverage_evidence
    from maid_runner.core import runtime_evidence

    _write_coverage_project(tmp_path)
    conftest = tmp_path / "conftest.py"
    conftest.write_text("# approved\n")
    _write_approvals(tmp_path, conftest, mode="derived")
    sentinel = object()
    observed: list[object] = []

    def fake_collect(manifests, root, pytest_workers=None):
        observed.append((tuple(manifests), root, pytest_workers))
        return SimpleNamespace(evidence=sentinel)

    monkeypatch.setattr(runtime_evidence, "collect_runtime_evidence", fake_collect)

    evidence = _collect_artifact_coverage_evidence(
        tmp_path, "manifests", pytest_workers=8
    )

    assert evidence is sentinel
    assert observed


def test_derived_evaluation_does_not_replay_unproven_commands(tmp_path: Path) -> None:
    from maid_runner.core.artifact_coverage import (
        ArtifactCoverageReport,
        evaluate_artifact_coverage_from_evidence,
    )
    from maid_runner.core._runtime_command_executor import RuntimeCommandRecord

    manifests = _write_coverage_project(tmp_path)
    executor = _RecordingExecutor(
        RuntimeCommandRecord(
            command=("-q", "tests/test_alpha.py"),
            returncode=0,
            stdout="",
            stderr="",
            execution_data={},
            report_errors=(),
        )
    )
    evidence = _incomplete_bundle(tmp_path, manifests[0])

    result = evaluate_artifact_coverage_from_evidence(
        manifests,
        tmp_path,
        evidence,
        fallback_executor=executor,
        evidence_mode="derived",
    )

    assert executor.calls == []
    assert result.fallback_identities == ()
    report = result.reports[manifests[0].source_path]
    assert isinstance(report, ArtifactCoverageReport)
    assert report.provenance == "derived"
    assert isinstance(report.findings, tuple)
    assert "provenance" in report.to_dict()
    assert report.to_dict()["provenance"] == "derived"


def test_exact_evaluation_replays_only_escalated_identities(tmp_path: Path) -> None:
    from maid_runner.core._artifact_coverage_fallback_worker import (
        ArtifactCoverageFallbackRun,
        ArtifactCoverageFallbackWorkerResult,
    )
    from maid_runner.core._runtime_command_executor import (
        RuntimeCommandRecord,
        RuntimeFileExecution,
    )
    from maid_runner.core.artifact_coverage import (
        evaluate_artifact_coverage_from_evidence,
    )

    manifests = _write_two_coverage_manifests(tmp_path)
    record = RuntimeCommandRecord(
        command=("-q", "tests/test_alpha.py"),
        returncode=0,
        stdout="",
        stderr="",
        execution_data={
            str((tmp_path / "src/alpha.py").resolve()): RuntimeFileExecution(
                executed_lines=frozenset({2}),
                called_qualnames=frozenset({"alpha"}),
            ),
            str((tmp_path / "src/beta.py").resolve()): RuntimeFileExecution(
                executed_lines=frozenset({2}),
                called_qualnames=frozenset({"beta"}),
            ),
        },
        report_errors=(),
    )
    identities = [
        RuntimeCommandIdentity(
            manifests[0].source_path, 0, manifests[0].validate_commands[0]
        ),
        RuntimeCommandIdentity(
            manifests[1].source_path, 0, manifests[1].validate_commands[0]
        ),
    ]
    red = identities[1]
    executor = _RecordingExecutor(record)

    def _runner(
        requested,
        project_root,
        target_files,
        snapshot_backend,
        runner_executor,
        jobs,
        max_processes,
    ):
        results = tuple(
            ArtifactCoverageFallbackWorkerResult(
                identity=identity,
                command_run=record,
                material_project_writes=(),
                process_cost=1,
                errors=(),
            )
            for identity in requested
        )
        return ArtifactCoverageFallbackRun(
            results=results, serial_fallback_identities=(red,)
        )

    result = evaluate_artifact_coverage_from_evidence(
        manifests,
        tmp_path,
        _incomplete_bundle(tmp_path, manifests[0], extra=manifests[1]),
        fallback_executor=executor,
        fallback_jobs=2,
        max_processes=2,
        snapshot_backend=_UnusedBackend(),
        isolated_runner=_runner,
        evidence_mode="exact",
    )

    assert result.serial_fallback_identities == (red,)
    assert [call[2] for call in executor.calls] == [tmp_path]
    assert len(executor.calls) == 1
    assert result.reports[manifests[0].source_path].provenance == "exact"


def test_evidence_mode_rejects_unknown_values(tmp_path: Path) -> None:
    from maid_runner.core.config import load_config

    (tmp_path / ".maidrc.yaml").write_text(
        "artifact_coverage:\n  evidence_mode: ambient\n"
    )
    try:
        load_config(tmp_path)
    except ValueError as exc:
        assert "evidence_mode" in str(exc)
    else:
        raise AssertionError("expected invalid evidence_mode to fail closed")


def test_packaged_evidence_mode_default_is_exact(tmp_path: Path) -> None:
    from maid_runner.core.config import ArtifactCoverageConfig, load_config

    (tmp_path / ".maidrc.yaml").write_text("{}\n")
    config = load_config(tmp_path)
    assert isinstance(config.artifact_coverage, ArtifactCoverageConfig)
    assert config.artifact_coverage.evidence_mode == "exact"
    assert config.artifact_coverage.timeout_seconds > 0
    assert config.artifact_coverage.fallback_jobs >= 1
    assert config.artifact_coverage.fixture_lifecycle_approvals == ()
    assert config.artifact_coverage.distribution_fixture_lifecycle_approvals == ()


class _RecordingExecutor:
    def __init__(self, record: object) -> None:
        self.record = record
        self.calls: list[tuple] = []

    def execute(self, command, target_files, project_root, timeout_seconds):
        self.calls.append((command, set(target_files), project_root, timeout_seconds))
        return self.record


class _UnusedBackend:
    def create(self, project_root, required_paths, worker_id):
        raise AssertionError("derived/exact tests must not copy snapshots here")


def _write_approvals(root: Path, conftest: Path, *, mode: str) -> None:
    digest = hashlib.sha256(conftest.read_bytes()).hexdigest()
    relative = conftest.relative_to(root).as_posix()
    (root / ".maidrc.yaml").write_text(
        "artifact_coverage:\n"
        f"  evidence_mode: {mode}\n"
        "  fixture_lifecycle_approvals:\n"
        "    - context_id: fixture::dummy:session\n"
        f"      conftest_path: {relative}\n"
        f'      sha256: "{digest}"\n'
    )


def _write_coverage_project(root: Path):
    (root / "src").mkdir(parents=True)
    (root / "src/alpha.py").write_text("def alpha():\n    return 1\n")
    (root / "tests").mkdir()
    (root / "tests/test_alpha.py").write_text("from src.alpha import alpha\n")
    (root / "manifests").mkdir()
    path = root / "manifests/alpha.manifest.yaml"
    path.write_text(
        """schema: "2"
goal: "Derived coverage fixture"
type: refactor
created: "2026-08-13T00:00:00Z"
files:
  edit:
    - path: src/alpha.py
      artifacts:
        - kind: function
          name: alpha
          args: []
          returns: int
validate:
  - python -m pytest -q tests/test_alpha.py
"""
    )
    return (load_manifest(path),)


def _write_two_coverage_manifests(root: Path):
    first = _write_coverage_project(root)[0]
    (root / "src/beta.py").write_text("def beta():\n    return 1\n")
    (root / "tests/test_beta.py").write_text("from src.beta import beta\n")
    path = root / "manifests/beta.manifest.yaml"
    path.write_text(
        """schema: "2"
goal: "Second derived coverage fixture"
type: refactor
created: "2026-08-13T00:00:00Z"
files:
  edit:
    - path: src/beta.py
      artifacts:
        - kind: function
          name: beta
          args: []
          returns: int
validate:
  - python -m pytest -q tests/test_beta.py
"""
    )
    return (first, load_manifest(path))


def _incomplete_bundle(root: Path, manifest, extra=None):
    from maid_runner.core._runtime_command_executor import RuntimeCommandRecord
    from maid_runner.core.runtime_evidence import (
        RuntimeCommandEvidence,
        RuntimeEnvironmentIdentity,
        RuntimeEvidenceBundle,
        RuntimeEvidenceCompleteness,
    )

    environment = RuntimeEnvironmentIdentity(
        resolved_command_prefix=("python",),
        working_directory=str(root),
        python_identity="python",
        pytest_version="8",
        coverage_version="7",
        xdist_version=None,
        configuration_digest="cfg",
        dependency_digest="deps",
        effective_environment_digest="env",
    )
    empty = RuntimeCommandRecord((), 0, "", "", {}, ())

    def _command(item):
        return RuntimeCommandEvidence(
            identity=RuntimeCommandIdentity(
                item.source_path, 0, item.validate_commands[0]
            ),
            behavior_group_key=("pytest", (), ()),
            selected_nodeids=(),
            contexts=(),
            result=empty,
            completeness=RuntimeEvidenceCompleteness(complete=False),
            environment_identity=environment,
        )

    commands = [_command(manifest)]
    if extra is not None:
        commands.append(_command(extra))
    return RuntimeEvidenceBundle(
        commands=tuple(commands),
        content_digest="incomplete",
        environment_identities=(environment,),
        worker_ids=(),
        completeness=RuntimeEvidenceCompleteness(complete=False),
    )
