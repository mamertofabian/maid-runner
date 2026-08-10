"""Behavioral contract for privacy-bounded MAID feedback bundles."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from maid_runner.core.outcomes import OutcomeIndex, OutcomeIndexRecord
from maid_runner.core.types import (
    AgentProvenance,
    OutcomeLesson,
    OutcomeReviewNote,
    OutcomeValidationEvidence,
)


def test_build_feedback_bundle_selects_only_exactly_marked_lessons() -> None:
    feedback = _feedback_api()
    index = _index(
        _record(
            "alpha",
            lessons=(
                _lesson("runner-gap", "Portable runner limitation."),
                _lesson("alpha-gap", "A second marked lesson."),
                _lesson(
                    "project-practice", "Keep this inside the project.", marker=None
                ),
                _lesson(
                    "wrong-case",
                    "A loose tag must not opt this lesson in.",
                    marker="MAID-RUNNER-FEEDBACK",
                ),
            ),
        )
    )

    bundle = feedback.build_feedback_bundle(index, "2.25.0")

    assert isinstance(bundle, feedback.FeedbackBundle)
    assert bundle.schema_version == "1"
    assert bundle.exported_with_version == "2.25.0"
    assert [record.lesson_type for record in bundle.records] == [
        "alpha-gap",
        "runner-gap",
    ]
    record = bundle.records[1]
    assert isinstance(record, feedback.FeedbackRecord)
    assert record.lesson_type == "runner-gap"
    assert record.summary == "Portable runner limitation."
    assert record.source_count == 1
    assert record.outcome_statuses == ("completed",)
    assert record.validation_statuses == ("passed",)
    assert record.review_severities == ("ready",)
    assert len(record.feedback_id) == 64


def test_build_feedback_bundle_deduplicates_sources_and_unions_evidence() -> None:
    feedback = _feedback_api()
    repeated = _lesson("validation-gap", "The runner cannot express this gate.")
    bundle = feedback.build_feedback_bundle(
        _index(
            _record(
                "alpha",
                lessons=(repeated, repeated),
                validation_status="passed",
                review_severity="P1",
            ),
            _record(
                "beta",
                lessons=(repeated,),
                status="partial",
                validation_status="failed",
                review_severity="ready",
            ),
        ),
        "2.25.0",
    )

    assert len(bundle.records) == 1
    record = bundle.records[0]
    assert record.source_count == 2
    assert record.outcome_statuses == ("completed", "partial")
    assert record.validation_statuses == ("failed", "passed")
    assert record.review_severities == ("P1", "ready")

    other_sources = feedback.build_feedback_bundle(
        _index(_record("elsewhere", lessons=(repeated,))), "9.9.9"
    )
    assert other_sources.records[0].feedback_id == record.feedback_id

    boundary_pairs = feedback.build_feedback_bundle(
        _index(
            _record(
                "collision-probe",
                lessons=(_lesson("ab", "c"), _lesson("a", "bc")),
            )
        ),
        "2.25.0",
    )
    assert (
        boundary_pairs.records[0].feedback_id != boundary_pairs.records[1].feedback_id
    )


def test_write_feedback_bundle_omits_repository_identifiers_and_refuses_overwrite(
    tmp_path: Path,
) -> None:
    feedback = _feedback_api()
    sensitive_values = (
        "/clients/secret-project",
        "manifests/customer-billing.manifest.yaml",
        "customer-billing",
        "src/private/customer_name.py",
        "CustomerSecretService",
        "uv run pytest --token super-secret",
        "reviewer@example.com",
        "Never expose Acme account 1234.",
        "sha256:private-instructions",
        "private-validation-status-acme",
        "private-review-severity-acme",
    )
    index = OutcomeIndex(
        schema_version="1",
        generated_from="generated-secret",
        included_statuses=("completed",),
        manifest_dir="manifests/customer",
        project_root=sensitive_values[0],
        records=(
            OutcomeIndexRecord(
                manifest_slug=sensitive_values[2],
                manifest_path=sensitive_values[1],
                status="completed",
                lifecycle_status="active",
                superseded_by=None,
                task_type="fix",
                created="2026-08-08",
                completed_at="2026-08-08T01:02:03Z",
                tags=("customer-acme",),
                declared_paths=(sensitive_values[3],),
                artifacts=(sensitive_values[4],),
                validation_commands=((sensitive_values[5],),),
                validation_evidence=(
                    OutcomeValidationEvidence(
                        command=(sensitive_values[5],),
                        status=sensitive_values[9],
                        summary="Private validation output.",
                    ),
                ),
                lessons=(
                    _lesson(
                        "runner-gap", "A generic and deliberately reviewed summary."
                    ),
                ),
                review_notes=(
                    OutcomeReviewNote(
                        source=sensitive_values[6],
                        severity=sensitive_values[10],
                        summary=sensitive_values[7],
                    ),
                ),
                source_fingerprint="private-source-fingerprint",
                agent=AgentProvenance(
                    model="private-model",
                    instructions_fingerprint=sensitive_values[8],
                ),
            ),
        ),
    )
    output = tmp_path / "nested" / "feedback.json"

    feedback.write_feedback_bundle(
        feedback.build_feedback_bundle(index, "2.25.0"), output
    )

    rendered = output.read_text(encoding="utf-8")
    payload = json.loads(rendered)
    assert set(payload) == {"exported_with_version", "records", "schema_version"}
    assert set(payload["records"][0]) == {
        "feedback_id",
        "lesson_type",
        "outcome_statuses",
        "review_severities",
        "source_count",
        "summary",
        "validation_statuses",
    }
    for sensitive in sensitive_values:
        assert sensitive not in rendered
    assert payload["records"][0]["validation_statuses"] == ["other"]
    assert payload["records"][0]["review_severities"] == ["other"]

    with pytest.raises(FileExistsError):
        feedback.write_feedback_bundle(
            feedback.build_feedback_bundle(index, "2.25.0"), output
        )

    feedback.write_feedback_bundle(
        feedback.FeedbackBundle("1", "2.26.0", ()), output, overwrite=True
    )
    assert json.loads(output.read_text(encoding="utf-8"))["records"] == []


def test_write_feedback_bundle_emits_stable_empty_bundle(tmp_path: Path) -> None:
    feedback = _feedback_api()
    bundle = feedback.build_feedback_bundle(_index(), "2.25.0")
    first = tmp_path / "first.json"
    second = tmp_path / "second.json"

    feedback.write_feedback_bundle(bundle, first)
    feedback.write_feedback_bundle(bundle, second)

    assert first.read_bytes() == second.read_bytes()
    assert json.loads(first.read_text(encoding="utf-8")) == {
        "exported_with_version": "2.25.0",
        "records": [],
        "schema_version": "1",
    }


def _feedback_api():
    try:
        from maid_runner.core.feedback import (
            FeedbackBundle,
            FeedbackRecord,
            build_feedback_bundle,
            write_feedback_bundle,
        )
        import maid_runner.core.feedback as feedback
    except ModuleNotFoundError:
        pytest.fail("maid_runner.core.feedback is not implemented")
    assert FeedbackBundle is feedback.FeedbackBundle
    assert FeedbackRecord is feedback.FeedbackRecord
    assert build_feedback_bundle is feedback.build_feedback_bundle
    assert write_feedback_bundle is feedback.write_feedback_bundle
    return feedback


def _lesson(
    lesson_type: str,
    summary: str,
    *,
    marker: str | None = "maid-runner-feedback",
) -> OutcomeLesson:
    tags = (marker, "private-project-tag") if marker is not None else ()
    return OutcomeLesson(
        lesson_type=lesson_type,
        summary=summary,
        tags=tags,
        paths=("private/source.py",),
    )


def _index(*records: OutcomeIndexRecord) -> OutcomeIndex:
    return OutcomeIndex(
        schema_version="1",
        generated_from="fingerprint",
        included_statuses=("completed", "partial", "failed"),
        manifest_dir="manifests",
        project_root="/private/repository",
        records=records,
    )


def _record(
    slug: str,
    *,
    lessons: tuple[OutcomeLesson, ...],
    status: str = "completed",
    validation_status: str = "passed",
    review_severity: str = "ready",
) -> OutcomeIndexRecord:
    return OutcomeIndexRecord(
        manifest_slug=slug,
        manifest_path=f"manifests/{slug}.manifest.yaml",
        status=status,
        lifecycle_status="active",
        superseded_by=None,
        task_type="fix",
        created="2026-08-08",
        completed_at="2026-08-08T01:02:03Z",
        tags=("private-manifest-tag",),
        declared_paths=(f"src/{slug}.py",),
        artifacts=(f"function:{slug}",),
        validation_commands=(("uv", "run", "pytest", f"tests/test_{slug}.py"),),
        validation_evidence=(
            OutcomeValidationEvidence(
                command=("uv", "run", "pytest"),
                status=validation_status,
                summary=f"{validation_status} evidence for {slug}.",
            ),
        ),
        lessons=lessons,
        review_notes=(
            OutcomeReviewNote(
                source="implementation-review",
                severity=review_severity,
                summary=f"{review_severity} review for {slug}.",
            ),
        ),
        source_fingerprint=f"{slug}-fingerprint",
    )
