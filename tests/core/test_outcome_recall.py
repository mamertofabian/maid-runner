"""Behavioral tests for deterministic Outcome recall."""

from __future__ import annotations

import pytest

from maid_runner.core.outcomes import OutcomeIndex, OutcomeIndexRecord
from maid_runner.core.types import (
    OutcomeLesson,
    OutcomeReviewNote,
    OutcomeValidationEvidence,
)


def test_recall_outcomes_ranks_by_deterministic_signal_weights():
    from maid_runner.core.outcome_recall import (
        OutcomeRecallMatch,
        OutcomeRecallQuery,
        recall_outcomes,
    )

    record = _record(
        "alpha",
        tags=("validation",),
        declared_paths=("maid_runner/core/manifest.py",),
        artifacts=("maid_runner/core/manifest.py:function:validate_manifest",),
        validation_commands=(("uv", "run", "pytest"),),
        lessons=(
            OutcomeLesson(
                lesson_type="testing",
                summary="Focused behavior confirms recall ranking.",
                tags=("recall",),
                paths=("docs/outcomes.md",),
            ),
        ),
        review_notes=(
            OutcomeReviewNote(
                source="implementation-review",
                severity="info",
                summary="Reviewer accepted the recall behavior.",
            ),
        ),
        validation_evidence=(
            OutcomeValidationEvidence(
                command=("uv", "run", "maid", "test"),
                status="passed",
                summary="Recall validation passed.",
            ),
        ),
    )

    matches = recall_outcomes(
        _index(record),
        OutcomeRecallQuery(
            text="focused",
            tags=("validation",),
            paths=("maid_runner/core/manifest.py",),
            artifacts=("maid_runner/core/manifest.py:function:validate_manifest",),
            validation_commands=("pytest",),
            review_text="reviewer",
            manifest_slugs=("alpha",),
        ),
    )

    assert len(matches) == 1
    assert isinstance(matches[0], OutcomeRecallMatch)
    assert matches[0].score == 340
    assert matches[0].reasons == (
        "manifest_slug:alpha (+100)",
        "path:maid_runner/core/manifest.py (+80)",
        "artifact:maid_runner/core/manifest.py:function:validate_manifest (+60)",
        "tag:validation (+40)",
        "validation_command:pytest (+30)",
        "review_text:reviewer (+20)",
        "text:focused (+10)",
    )


def test_recall_outcomes_normalizes_paths_and_text_case():
    from maid_runner.core.outcome_recall import OutcomeRecallQuery, recall_outcomes

    record = _record(
        "case-path",
        tags=("Validation",),
        declared_paths=("maid_runner/core/outcomes.py",),
        lessons=(
            OutcomeLesson(
                lesson_type="testing",
                summary="Deterministic Recall uses stable matching.",
                tags=("Outcome",),
                paths=(),
            ),
        ),
    )

    matches = recall_outcomes(
        _index(record),
        OutcomeRecallQuery(
            text="recall RECALL",
            tags=("validation", "VALIDATION"),
            paths=("./maid_runner\\core\\outcomes.py",),
        ),
    )

    assert len(matches) == 1
    assert matches[0].score == 130
    assert matches[0].reasons == (
        "path:maid_runner/core/outcomes.py (+80)",
        "tag:validation (+40)",
        "text:recall (+10)",
    )


def test_recall_outcomes_normalizes_absolute_paths_under_project_root(tmp_path):
    from maid_runner.core.outcome_recall import OutcomeRecallQuery, recall_outcomes

    record = _record(
        "absolute-path",
        declared_paths=("maid_runner/core/outcomes.py",),
    )
    absolute_query_path = (
        tmp_path / "maid_runner" / "core" / ".." / "core" / "outcomes.py"
    )

    matches = recall_outcomes(
        _index(record),
        OutcomeRecallQuery(
            paths=(str(absolute_query_path),),
            project_root=str(tmp_path),
        ),
    )

    assert [match.record.manifest_slug for match in matches] == ["absolute-path"]
    assert matches[0].reasons == ("path:maid_runner/core/outcomes.py (+80)",)


def test_recall_outcomes_does_not_match_absolute_paths_outside_project_root(tmp_path):
    from maid_runner.core.outcome_recall import OutcomeRecallQuery, recall_outcomes

    project_root = tmp_path / "repo"
    outside_path = tmp_path / "outside" / "src.py"
    record = _record(
        "relative-looking-outside",
        declared_paths=(outside_path.as_posix().lstrip("/"),),
    )

    matches = recall_outcomes(
        _index(record),
        OutcomeRecallQuery(paths=(str(outside_path),), project_root=str(project_root)),
    )

    assert matches == []


def test_recall_outcomes_full_text_does_not_search_lesson_paths():
    from maid_runner.core.outcome_recall import OutcomeRecallQuery, recall_outcomes

    record = _record(
        "lesson-path-only",
        lessons=(
            OutcomeLesson(
                lesson_type="testing",
                summary="Focused behavioral summary.",
                paths=("docs/hidden-token.md",),
            ),
        ),
    )

    matches = recall_outcomes(
        _index(record),
        OutcomeRecallQuery(text="hidden"),
    )

    assert matches == []


def test_recall_outcomes_full_text_does_not_search_lesson_types():
    from maid_runner.core.outcome_recall import OutcomeRecallQuery, recall_outcomes

    record = _record(
        "lesson-type-only",
        lessons=(
            OutcomeLesson(
                lesson_type="hidden",
                summary="Focused behavioral summary.",
                tags=("visible",),
            ),
        ),
    )

    matches = recall_outcomes(
        _index(record),
        OutcomeRecallQuery(text="hidden"),
    )

    assert matches == []


def test_recall_outcomes_requires_all_supplied_filter_fields():
    from maid_runner.core.outcome_recall import OutcomeRecallQuery, recall_outcomes

    eligible = _record(
        "eligible",
        tags=("validation",),
        declared_paths=("src/eligible.py",),
        artifacts=("src/eligible.py:function:task",),
        validation_commands=(("uv", "run", "pytest"),),
        lessons=(OutcomeLesson("testing", "General deterministic lesson."),),
        review_notes=(OutcomeReviewNote("review", "info", "Specific review note."),),
    )
    missing_review = _record(
        "missing-review",
        tags=("validation",),
        declared_paths=("src/eligible.py",),
        artifacts=("src/eligible.py:function:task",),
        validation_commands=(("uv", "run", "pytest"),),
        lessons=(OutcomeLesson("testing", "General deterministic lesson."),),
    )
    missing_path = _record(
        "missing-path",
        tags=("validation",),
        artifacts=("src/eligible.py:function:task",),
        validation_commands=(("uv", "run", "pytest"),),
        lessons=(OutcomeLesson("testing", "General deterministic lesson."),),
        review_notes=(OutcomeReviewNote("review", "info", "Specific review note."),),
    )

    matches = recall_outcomes(
        _index(missing_path, missing_review, eligible),
        OutcomeRecallQuery(
            text="general",
            tags=("validation",),
            paths=("src/eligible.py",),
            artifacts=("src/eligible.py:function:task",),
            validation_commands=("pytest",),
            review_text="specific",
        ),
    )

    assert [match.record.manifest_slug for match in matches] == ["eligible"]


def test_recall_outcomes_uses_stable_tie_breakers():
    from maid_runner.core.outcome_recall import OutcomeRecallQuery, recall_outcomes

    beta = _record(
        "beta",
        manifest_path="manifests/z-beta.manifest.yaml",
        declared_paths=("src/common.py",),
    )
    alpha = _record(
        "alpha",
        manifest_path="manifests/z-alpha.manifest.yaml",
        declared_paths=("src/common.py",),
    )

    matches = recall_outcomes(
        _index(beta, alpha),
        OutcomeRecallQuery(text="common"),
    )

    assert [match.record.manifest_slug for match in matches] == ["alpha", "beta"]


def test_recall_outcomes_limit_and_empty_query_behavior_are_explicit():
    from maid_runner.core.outcome_recall import OutcomeRecallQuery, recall_outcomes

    with pytest.raises(ValueError, match="empty"):
        recall_outcomes(_index(_record("alpha")), OutcomeRecallQuery())

    matches = recall_outcomes(
        _index(
            _record("beta", declared_paths=("src/common.py",)),
            _record("alpha", declared_paths=("src/common.py",)),
        ),
        OutcomeRecallQuery(text="common"),
        limit=1,
    )

    assert [match.record.manifest_slug for match in matches] == ["alpha"]


def _index(*records: OutcomeIndexRecord) -> OutcomeIndex:
    return OutcomeIndex(
        schema_version="1",
        generated_from="test",
        included_statuses=("completed",),
        manifest_dir="manifests",
        project_root=".",
        records=tuple(records),
    )


def _record(
    manifest_slug: str,
    *,
    manifest_path: str | None = None,
    tags: tuple[str, ...] = (),
    declared_paths: tuple[str, ...] = (),
    artifacts: tuple[str, ...] = (),
    validation_commands: tuple[tuple[str, ...], ...] = (),
    validation_evidence: tuple[OutcomeValidationEvidence, ...] = (),
    lessons: tuple[OutcomeLesson, ...] = (),
    review_notes: tuple[OutcomeReviewNote, ...] = (),
) -> OutcomeIndexRecord:
    return OutcomeIndexRecord(
        manifest_slug=manifest_slug,
        manifest_path=manifest_path or f"manifests/{manifest_slug}.manifest.yaml",
        status="completed",
        lifecycle_status="active",
        superseded_by=None,
        task_type="feature",
        created="2026-05-30",
        completed_at="2026-05-31T01:02:03Z",
        tags=tags,
        declared_paths=declared_paths,
        artifacts=artifacts,
        validation_commands=validation_commands,
        validation_evidence=validation_evidence,
        lessons=lessons,
        review_notes=review_notes,
        source_fingerprint="0" * 64,
    )
