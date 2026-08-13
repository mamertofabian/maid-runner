"""Reuse ordinary tests when grouped evidence is incomplete only for coverage.

Contract: manifests/drafts/121-33-reuse-ordinary-tests-with-collection-incompleteness.manifest.yaml
"""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path

from maid_runner.cli.commands import verify as verify_mod
from tests.cli.test_reuse_ordinary_tests_after_knockout import (
    _install_implementation_probe,
    _install_snapshot_knockout,
)
from tests.cli.test_verify_deep_evidence_reuse import (
    _stage,
    _verify,
    _write_project,
)


def test_collection_global_incompleteness_still_reuses_ordinary_tests(
    tmp_path: Path, monkeypatch
) -> None:
    log = tmp_path.parent / f"{tmp_path.name}-executions.log"
    _write_project(tmp_path, log)
    monkeypatch.setenv("MAID_EVIDENCE_EXECUTION_LOG", str(log))
    _inject_bundle_incompleteness(
        monkeypatch,
        unresolved_context_ids=("collection:global",),
        unproven_fixture_lifecycles=(
            "fixture:tests/other.py:autouse:function:tests/other.py::test_other",
        ),
    )
    _install_snapshot_knockout(monkeypatch)
    executed = _install_implementation_probe(monkeypatch)

    result = _verify(tmp_path, knockout=True)

    assert _stage(result, "artifact_coverage").success is True
    assert _stage(result, "knockout").success is True
    assert _stage(result, "tests").success is True
    assert executed == []


def test_missing_workers_keep_ordinary_tests_fresh(tmp_path: Path, monkeypatch) -> None:
    log = tmp_path.parent / f"{tmp_path.name}-executions.log"
    _write_project(tmp_path, log)
    monkeypatch.setenv("MAID_EVIDENCE_EXECUTION_LOG", str(log))
    _inject_bundle_incompleteness(monkeypatch, missing_worker_ids=("gw0",))
    _install_snapshot_knockout(monkeypatch)
    executed = _install_implementation_probe(monkeypatch)

    result = _verify(tmp_path, knockout=True)

    assert _stage(result, "tests").success is True
    commands = [command for command, _slug in executed]
    assert ("python", "-m", "pytest", "-q", "tests/test_target.py") in commands


def _inject_bundle_incompleteness(monkeypatch, **fields) -> None:
    original = verify_mod._collect_artifact_coverage_evidence_run

    def wrapped(*args, **kwargs):
        run = original(*args, **kwargs)
        if run is None:
            return None
        completeness = replace(
            run.evidence.completeness,
            complete=False,
            **fields,
        )
        return replace(run, evidence=replace(run.evidence, completeness=completeness))

    monkeypatch.setattr(verify_mod, "_collect_artifact_coverage_evidence_run", wrapped)
