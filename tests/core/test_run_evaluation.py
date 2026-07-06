"""Behavioral tests for deterministic run evaluation."""

from __future__ import annotations

import json
from pathlib import Path

import yaml

from maid_runner.core.plan_lock import (
    ContractDelta,
    PlanLock,
    PlanLockRevision,
    default_plan_lock_path,
)
from maid_runner.core.types import AgentProvenance


def test_clean_fully_evidenced_run_reports_expected_dimensions(
    tmp_path: Path,
) -> None:
    from maid_runner.core.run_evaluation import RunEvaluation, evaluate_run

    manifest_path = _write_manifest(
        tmp_path,
        outcome={
            "status": "completed",
            "summary": "Done",
            "agent": {
                "model": "gpt-5-codex",
                "provider": "openai",
                "client": "codex-cli",
                "skills": ["maid-implementer"],
                "source": "outcome",
            },
            "validation": [
                {
                    "command": ["uv", "run", "pytest", "-q", "tests/test_demo.py"],
                    "status": "passed",
                    "summary": "focused tests passed",
                }
            ],
        },
    )
    _write_lock(
        tmp_path,
        agent=AgentProvenance(model="lock-agent", source="flags"),
        red_evidence=_valid_red_evidence(),
        revisions=(
            PlanLockRevision(
                prior_manifest_hash="old",
                prior_test_hashes={},
                revised_at="2026-07-06T00:00:00Z",
                reason="add stricter tests",
                contract_delta=ContractDelta(
                    artifacts_added=("src/demo.py:function:extra",),
                ),
            ),
        ),
    )

    evaluation = evaluate_run(manifest_path, tmp_path)

    assert isinstance(evaluation, RunEvaluation)
    assert evaluation.manifest_slug == "demo-task"
    assert evaluation.provenance == AgentProvenance(
        model="gpt-5-codex",
        provider="openai",
        client="codex-cli",
        skills=("maid-implementer",),
        source="outcome",
    )
    assert evaluation.provenance_source == "outcome"
    assert evaluation.outcome_status == "completed"
    assert evaluation.outcome_uncorroborated_commands == ()
    assert evaluation.unevidenced_validate_commands == ()
    assert evaluation.lock_present is True
    assert evaluation.red_evidence_status == "valid"
    assert evaluation.revisions_total == 1
    assert evaluation.revisions_strengthening == 1
    assert evaluation.revisions_neutral == 0
    assert evaluation.revisions_narrowing == 0
    assert evaluation.revisions_unclassified == 0
    assert evaluation.incidents_total == 0
    assert {finding.severity for finding in evaluation.findings} == {"info"}


def test_delta_removing_validate_command_classified_narrowing_with_citation(
    tmp_path: Path,
) -> None:
    from maid_runner.core.run_evaluation import evaluate_run

    manifest_path = _write_manifest(tmp_path)
    _write_lock(
        tmp_path,
        red_evidence=_valid_red_evidence(),
        revisions=(
            PlanLockRevision(
                prior_manifest_hash="old",
                prior_test_hashes={},
                revised_at="2026-07-06T00:00:00Z",
                reason="cleanup",
                contract_delta=ContractDelta(
                    validate_commands_removed=("uv run pytest -q tests/old.py",),
                ),
            ),
        ),
    )

    evaluation = evaluate_run(manifest_path, tmp_path)

    assert evaluation.revisions_narrowing == 1
    finding = _finding(evaluation, "attention", "plan-discipline")
    assert "narrowing" in finding.summary
    assert finding.evidence == ("plan-lock:revision-1",)


def test_pre_delta_revisions_reported_unclassified_not_neutral(
    tmp_path: Path,
) -> None:
    from maid_runner.core.run_evaluation import evaluate_run

    manifest_path = _write_manifest(tmp_path)
    _write_lock(
        tmp_path,
        red_evidence=_valid_red_evidence(),
        revisions=(
            PlanLockRevision(
                prior_manifest_hash="old",
                prior_test_hashes={},
                revised_at="2026-07-06T00:00:00Z",
                reason="pre-delta revision",
                contract_delta=None,
            ),
        ),
    )

    evaluation = evaluate_run(manifest_path, tmp_path)

    assert evaluation.revisions_unclassified == 1
    assert evaluation.revisions_neutral == 0
    finding = _finding(evaluation, "info", "plan-discipline")
    assert "unclassified" in finding.summary
    assert finding.evidence == ("plan-lock:revision-1",)


def test_missing_provenance_yields_anonymous_run_warning(tmp_path: Path) -> None:
    from maid_runner.core.run_evaluation import evaluate_run

    manifest_path = _write_manifest(tmp_path)
    _write_lock(tmp_path, red_evidence=_valid_red_evidence())

    evaluation = evaluate_run(manifest_path, tmp_path)

    assert evaluation.provenance is None
    assert evaluation.provenance_source is None
    finding = _finding(evaluation, "warning", "provenance")
    assert "anonymous" in finding.summary.lower()
    assert finding.evidence == ("manifest:demo-task",)


def test_outcome_corroboration_separates_uncorroborated_and_unevidenced(
    tmp_path: Path,
) -> None:
    from maid_runner.core.run_evaluation import evaluate_run

    manifest_path = _write_manifest(
        tmp_path,
        outcome={
            "status": "completed",
            "summary": "Done",
            "validation": [
                {
                    "command": ["uv", "run", "pytest", "-q", "tests/foreign.py"],
                    "status": "passed",
                    "summary": "foreign command passed",
                }
            ],
        },
    )
    _write_lock(tmp_path, red_evidence=_valid_red_evidence())

    evaluation = evaluate_run(manifest_path, tmp_path)

    assert evaluation.outcome_uncorroborated_commands == (
        "uv run pytest -q tests/foreign.py",
    )
    assert evaluation.unevidenced_validate_commands == (
        "uv run pytest -q tests/test_demo.py",
    )
    assert _finding(evaluation, "info", "outcome-corroboration").evidence == (
        "outcome:validation[1]",
    )
    warning = _finding(evaluation, "warning", "outcome-corroboration")
    assert warning.evidence == ("manifest:validate[1]",)


def test_red_evidence_status_values_for_missing_lock_and_missing_red(
    tmp_path: Path,
) -> None:
    from maid_runner.core.run_evaluation import evaluate_run

    manifest_path = _write_manifest(tmp_path)

    no_lock = evaluate_run(manifest_path, tmp_path)
    assert no_lock.lock_present is False
    assert no_lock.red_evidence_status == "no-lock"

    _write_lock(tmp_path, red_evidence=None)
    missing_red = evaluate_run(manifest_path, tmp_path)
    assert missing_red.lock_present is True
    assert missing_red.red_evidence_status == "missing"

    _write_lock(tmp_path, red_evidence={"red": False, "commands": []})
    invalid_red = evaluate_run(manifest_path, tmp_path)
    assert invalid_red.red_evidence_status == "invalid"


def test_incident_referencing_manifest_counts_with_integrity_finding(
    tmp_path: Path,
) -> None:
    from maid_runner.core.run_evaluation import evaluate_run

    manifest_path = _write_manifest(tmp_path)
    _write_lock(tmp_path, red_evidence=_valid_red_evidence())
    incident_path = tmp_path / ".maid" / "incidents" / "20260706-demo.incident.yaml"
    incident_path.parent.mkdir(parents=True)
    incident_path.write_text(
        yaml.safe_dump(
            {
                "incident_version": 1,
                "created": "2026-07-06T00:00:00Z",
                "manifest": "manifests/demo-task.manifest.yaml",
                "gates": ["E701"],
                "packet": {"diagnostics": [{"code": "E701"}]},
                "rejected_diff": "bad",
                "chosen_diff": None,
                "pattern_tags": ["false-done"],
                "notes": None,
            },
            sort_keys=False,
        ),
        encoding="utf-8",
    )

    evaluation = evaluate_run(manifest_path, tmp_path)

    assert evaluation.incidents_total == 1
    finding = _finding(evaluation, "warning", "integrity")
    assert "incident" in finding.summary.lower()
    assert finding.evidence == ("incident:20260706-demo.incident.yaml",)


def test_malformed_incident_storage_reports_integrity_warning(
    tmp_path: Path,
) -> None:
    from maid_runner.core.run_evaluation import evaluate_run

    manifest_path = _write_manifest(tmp_path)
    _write_lock(tmp_path, red_evidence=_valid_red_evidence())
    valid_incident_path = (
        tmp_path / ".maid" / "incidents" / "20260706-demo.incident.yaml"
    )
    valid_incident_path.parent.mkdir(parents=True)
    valid_incident_path.write_text(
        yaml.safe_dump(
            {
                "incident_version": 1,
                "created": "2026-07-06T00:00:00Z",
                "manifest": "manifests/demo-task.manifest.yaml",
                "gates": ["E701"],
                "packet": {"diagnostics": [{"code": "E701"}]},
                "rejected_diff": "bad",
                "chosen_diff": None,
                "pattern_tags": ["false-done"],
                "notes": None,
            },
            sort_keys=False,
        ),
        encoding="utf-8",
    )
    incident_path = tmp_path / ".maid" / "incidents" / "broken.incident.yaml"
    incident_path.write_text("not: [valid", encoding="utf-8")

    evaluation = evaluate_run(manifest_path, tmp_path)

    assert evaluation.incidents_total == 1
    warnings = [
        finding
        for finding in evaluation.findings
        if finding.severity == "warning" and finding.category == "integrity"
    ]
    assert any(
        finding.evidence == ("incident:20260706-demo.incident.yaml",)
        for finding in warnings
    )
    assert any(
        "unreadable" in finding.summary.lower()
        and finding.evidence == ("incident:broken.incident.yaml",)
        for finding in warnings
    )


def test_malformed_plan_lock_reports_integrity_warning(
    tmp_path: Path,
) -> None:
    from maid_runner.core.run_evaluation import evaluate_run

    manifest_path = _write_manifest(tmp_path)
    lock_path = default_plan_lock_path(tmp_path, "demo-task")
    lock_path.parent.mkdir(parents=True)
    lock_path.write_text("{not json", encoding="utf-8")

    evaluation = evaluate_run(manifest_path, tmp_path)

    assert evaluation.lock_present is True
    assert evaluation.red_evidence_status == "invalid"
    warning = _finding(evaluation, "warning", "red-evidence")
    assert "unreadable" in warning.summary.lower()
    assert warning.evidence == ("plan-lock:demo-task",)
    outcome_warning = _finding(evaluation, "warning", "outcome-corroboration")
    assert "no outcome" in outcome_warning.summary.lower()
    assert outcome_warning.evidence == ("manifest:demo-task",)


def _write_manifest(
    project_root: Path,
    *,
    outcome: dict | None = None,
) -> Path:
    manifest_dir = project_root / "manifests"
    manifest_dir.mkdir(parents=True, exist_ok=True)
    (project_root / "src").mkdir(exist_ok=True)
    (project_root / "tests").mkdir(exist_ok=True)
    (project_root / "src" / "demo.py").write_text(
        "def demo() -> int:\n    return 1\n",
        encoding="utf-8",
    )
    (project_root / "tests" / "test_demo.py").write_text(
        "from src.demo import demo\n\n\n"
        "def test_demo_contract():\n"
        "    assert demo() == 1\n",
        encoding="utf-8",
    )
    payload: dict = {
        "schema": "2",
        "goal": "Demo task",
        "type": "feature",
        "created": "2026-07-06T00:00:00Z",
        "files": {
            "create": [
                {
                    "path": "src/demo.py",
                    "artifacts": [
                        {"kind": "function", "name": "demo", "returns": "int"}
                    ],
                }
            ],
            "read": ["tests/test_demo.py"],
        },
        "validate": ["uv run pytest -q tests/test_demo.py"],
    }
    if outcome is not None:
        payload["outcome"] = outcome
    manifest_path = manifest_dir / "demo-task.manifest.yaml"
    manifest_path.write_text(yaml.safe_dump(payload, sort_keys=False), encoding="utf-8")
    return manifest_path


def _write_lock(
    project_root: Path,
    *,
    red_evidence: dict | None,
    agent: AgentProvenance | None = None,
    revisions: tuple[PlanLockRevision, ...] = (),
) -> None:
    lock = PlanLock(
        manifest_path="manifests/demo-task.manifest.yaml",
        manifest_hash="hash",
        test_hashes={},
        created_at="2026-07-06T00:00:00Z",
        revision=1 + len(revisions),
        revisions=revisions,
        red_evidence=red_evidence,
        agent=agent,
    )
    lock_path = default_plan_lock_path(project_root, "demo-task")
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "manifest_path": lock.manifest_path,
        "manifest_hash": lock.manifest_hash,
        "test_hashes": lock.test_hashes,
        "created_at": lock.created_at,
        "revision": lock.revision,
        "revisions": [
            {
                "prior_manifest_hash": revision.prior_manifest_hash,
                "prior_test_hashes": revision.prior_test_hashes,
                "revised_at": revision.revised_at,
                "reason": revision.reason,
                "agent": _agent_payload(revision.agent),
                "contract_delta": _delta_payload(revision.contract_delta),
            }
            for revision in revisions
        ],
        "red_evidence": red_evidence,
        "agent": _agent_payload(agent),
    }
    lock_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def _agent_payload(agent: AgentProvenance | None) -> dict | None:
    if agent is None:
        return None
    return {
        key: value
        for key, value in {
            "model": agent.model,
            "provider": agent.provider,
            "client": agent.client,
            "skills": list(agent.skills) if agent.skills else None,
            "instructions_fingerprint": agent.instructions_fingerprint,
            "source": agent.source,
        }.items()
        if value is not None
    }


def _delta_payload(delta: ContractDelta | None) -> dict | None:
    if delta is None:
        return None
    return {
        "artifacts_added": list(delta.artifacts_added),
        "artifacts_removed": list(delta.artifacts_removed),
        "files_added": list(delta.files_added),
        "files_removed": list(delta.files_removed),
        "validate_commands_added": list(delta.validate_commands_added),
        "validate_commands_removed": list(delta.validate_commands_removed),
    }


def _valid_red_evidence() -> dict:
    return {
        "red": True,
        "captured_at": "2026-07-06T00:00:00Z",
        "commands": [
            {
                "command": "uv run pytest -q tests/test_demo.py",
                "exit_code": 1,
                "output_tail": "assert 1 == 2",
                "classification": "red",
            }
        ],
    }


def _finding(evaluation, severity: str, category: str):
    from maid_runner.core.run_evaluation import RunFinding

    matches = [
        finding
        for finding in evaluation.findings
        if finding.severity == severity and finding.category == category
    ]
    assert matches
    assert isinstance(matches[0], RunFinding)
    return matches[0]
