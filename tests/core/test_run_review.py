"""Behavioral tests for deterministic run-review request validation."""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from maid_runner.core.manifest import load_manifest
from maid_runner.core.run_evaluation import RunEvaluation, RunFinding


def test_build_review_request_itemizes_all_evidence_with_stable_ids(
    tmp_path: Path,
) -> None:
    from maid_runner.core.run_review import (
        ReviewEvidenceItem,
        ReviewRequest,
        build_review_request,
    )

    manifest = load_manifest(_write_manifest(tmp_path))
    evaluation = _evaluation()

    request = build_review_request(
        evaluation,
        manifest,
        _lock_payload(),
        diff_text=None,
    )

    evidence = {item.evidence_id: item for item in request.evidence_items}
    assert isinstance(request, ReviewRequest)
    assert request.schema_version == "1"
    assert request.manifest_slug == "demo-task"
    assert request.evaluation["manifest_slug"] == "demo-task"
    assert tuple(evidence) == (
        "revision-1",
        "outcome-lesson-1",
        "outcome-review-note-1",
        "finding-1",
        "finding-2",
    )
    assert all(isinstance(item, ReviewEvidenceItem) for item in request.evidence_items)
    assert evidence["revision-1"].kind == "revision"
    assert "Removed optional test" in evidence["revision-1"].text
    assert "validation-evidence" in evidence["outcome-lesson-1"].text
    assert "review found no blockers" in evidence["outcome-review-note-1"].text
    assert "Run provenance resolved" in evidence["finding-1"].text
    assert len(evidence) == len(request.evidence_items)


def test_build_review_request_handles_diff_presence_and_absence(
    tmp_path: Path,
) -> None:
    from maid_runner.core.run_review import build_review_request

    manifest = load_manifest(_write_manifest(tmp_path))
    evaluation = _evaluation()

    no_diff = build_review_request(evaluation, manifest, None, diff_text=None)
    with_diff = build_review_request(
        evaluation,
        manifest,
        None,
        diff_text="diff --git a/src/demo.py b/src/demo.py\n+def demo(): pass\n",
    )

    assert "diff" not in {item.evidence_id for item in no_diff.evidence_items}
    assert "No diff evidence was supplied" in no_diff.instructions
    diff_item = next(
        item for item in with_diff.evidence_items if item.evidence_id == "diff"
    )
    assert diff_item.kind == "diff"
    assert "diff --git" in diff_item.text


def test_validate_run_review_accepts_faithful_review(tmp_path: Path) -> None:
    from maid_runner.core.run_review import build_review_request, validate_run_review

    request = build_review_request(
        _evaluation(),
        load_manifest(_write_manifest(tmp_path)),
        _lock_payload(),
        diff_text=None,
    )
    review = {
        "confidence": "medium",
        "summary": "Evidence shows no blocker.",
        "findings": [
            {
                "severity": "warning",
                "summary": "The revision should be checked against its stated reason.",
                "citations": ["revision-1", "finding-2"],
            }
        ],
    }

    assert validate_run_review(review, request) == []


def test_validate_run_review_rejects_each_fabrication_mode(
    tmp_path: Path,
) -> None:
    from maid_runner.core.run_review import build_review_request, validate_run_review

    request = build_review_request(
        _evaluation(),
        load_manifest(_write_manifest(tmp_path)),
        _lock_payload(),
        diff_text=None,
    )
    review = {
        "confidence": "certain",
        "verdict": "authoritative",
        "findings": [
            {
                "severity": "critical",
                "summary": "src/fabricated.py was changed without tests.",
                "citations": ["unknown-id"],
            },
            {
                "severity": "info",
                "summary": "This finding has no evidence citations.",
                "citations": [],
            },
        ],
    }

    errors = validate_run_review(review, request)

    assert any(
        "unknown top-level key" in error and "verdict" in error for error in errors
    )
    assert any("invalid confidence" in error and "certain" in error for error in errors)
    assert any("invalid severity" in error and "critical" in error for error in errors)
    assert any(
        "unknown evidence id" in error and "unknown-id" in error for error in errors
    )
    assert any("missing evidence citations" in error for error in errors)
    assert any(
        "unevidenced file path" in error and "src/fabricated.py" in error
        for error in errors
    )


def test_validate_run_review_rejects_missing_summary_and_root_file_fabrication(
    tmp_path: Path,
) -> None:
    from maid_runner.core.run_review import build_review_request, validate_run_review

    request = build_review_request(
        _evaluation(),
        load_manifest(_write_manifest(tmp_path)),
        _lock_payload(),
        diff_text=None,
    )
    review = {
        "confidence": "high",
        "findings": [
            {
                "severity": "info",
                "citations": ["revision-1"],
            },
            {
                "severity": "warning",
                "summary": "README.md and .gitignore were changed without evidence.",
                "citations": ["revision-1"],
            },
            {
                "severity": "attention",
                "summary": "Makefile was changed without evidence.",
                "citations": ["revision-1"],
            },
        ],
    }

    errors = validate_run_review(review, request)

    assert any("missing summary" in error for error in errors)
    assert any(
        "unevidenced file path" in error and "README.md" in error for error in errors
    )
    assert any(
        "unevidenced file path" in error and ".gitignore" in error for error in errors
    )
    assert any(
        "unevidenced file path" in error and "Makefile" in error for error in errors
    )


def test_validate_run_review_rejects_fabrication_outside_finding_summary(
    tmp_path: Path,
) -> None:
    from maid_runner.core.run_review import build_review_request, validate_run_review

    request = build_review_request(
        _evaluation(),
        load_manifest(_write_manifest(tmp_path)),
        _lock_payload(),
        diff_text=None,
    )
    review = {
        "confidence": "high",
        "summary": "src/fabricated.py was changed without tests.",
        "findings": [
            {
                "severity": "info",
                "summary": "The cited revision exists.",
                "citations": ["revision-1"],
                "details": "README.md was also changed.",
            }
        ],
    }

    errors = validate_run_review(review, request)

    assert any(
        "top-level summary unevidenced file path" in error
        and "src/fabricated.py" in error
        for error in errors
    )
    assert any(
        "finding 1 unknown key" in error and "details" in error for error in errors
    )


def test_render_run_review_labels_advisory_and_inlines_citations(
    tmp_path: Path,
) -> None:
    from maid_runner.core.run_review import build_review_request, render_run_review

    request = build_review_request(
        _evaluation(),
        load_manifest(_write_manifest(tmp_path)),
        _lock_payload(),
        diff_text=None,
    )
    review = {
        "confidence": "high",
        "summary": "Review is grounded in the request evidence.",
        "findings": [
            {
                "severity": "attention",
                "summary": "The narrowing revision warrants human attention.",
                "citations": ["revision-1", "finding-2"],
            }
        ],
    }

    markdown = render_run_review(review, request)

    assert markdown.startswith("# LLM-Generated Advisory Run Review\n")
    counts_index = markdown.index("## Deterministic Counts")
    findings_index = markdown.index("## Findings")
    assert counts_index < findings_index
    assert "revisions_total: 1" in markdown
    assert "incidents_total: 0" in markdown
    assert "revision-1" in markdown
    assert "Removed optional test" in markdown

    invalid = {
        "confidence": "high",
        "findings": [
            {"severity": "warning", "summary": "Unsupported", "citations": []}
        ],
    }
    with pytest.raises(ValueError):
        render_run_review(invalid, request)


def _write_manifest(project_root: Path) -> Path:
    manifest_path = project_root / "manifests" / "demo-task.manifest.yaml"
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "schema": "2",
        "goal": "Demo task",
        "type": "feature",
        "created": "2026-07-06T00:00:00Z",
        "files": {
            "create": [
                {
                    "path": "src/demo.py",
                    "artifacts": [{"kind": "function", "name": "demo"}],
                }
            ],
            "read": ["tests/test_demo.py"],
        },
        "validate": ["uv run pytest -q tests/test_demo.py"],
        "outcome": {
            "status": "completed",
            "summary": "Done",
            "lessons": [
                {
                    "lesson_type": "validation-evidence",
                    "summary": "Validation evidence must stay tied to the manifest.",
                    "paths": ["tests/test_demo.py"],
                }
            ],
            "review_notes": [
                {
                    "source": "implementation-review",
                    "severity": "info",
                    "summary": "Independent review found no blockers.",
                }
            ],
            "validation": [
                {
                    "command": ["uv", "run", "pytest", "-q", "tests/test_demo.py"],
                    "status": "passed",
                    "summary": "Focused tests passed.",
                }
            ],
        },
    }
    manifest_path.write_text(yaml.safe_dump(payload, sort_keys=False), encoding="utf-8")
    return manifest_path


def _evaluation() -> RunEvaluation:
    return RunEvaluation(
        manifest_path="manifests/demo-task.manifest.yaml",
        manifest_slug="demo-task",
        provenance=None,
        provenance_source=None,
        outcome_status="completed",
        outcome_uncorroborated_commands=(),
        unevidenced_validate_commands=(),
        lock_present=True,
        red_evidence_status="valid",
        revisions_total=1,
        revisions_strengthening=0,
        revisions_neutral=0,
        revisions_narrowing=1,
        revisions_unclassified=0,
        incidents_total=0,
        findings=(
            RunFinding(
                severity="info",
                category="provenance",
                summary="Run provenance resolved from plan lock.",
                evidence=("plan-lock:agent",),
            ),
            RunFinding(
                severity="attention",
                category="plan-discipline",
                summary="Plan-lock revision is narrowing based on stored contract-delta removals.",
                evidence=("plan-lock:revision-1",),
            ),
        ),
    )


def _lock_payload() -> dict:
    return {
        "revisions": [
            {
                "reason": "Removed optional test after implementation review.",
                "contract_delta": {
                    "artifacts_added": [],
                    "artifacts_removed": ["src/demo.py:function:old_demo"],
                    "files_added": [],
                    "files_removed": [],
                    "validate_commands_added": [],
                    "validate_commands_removed": ["uv run pytest -q tests/old_demo.py"],
                },
            }
        ]
    }
