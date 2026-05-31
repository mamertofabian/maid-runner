"""Behavioral tests for deterministic Outcome insight aggregation."""

from __future__ import annotations

from maid_runner.core.outcomes import OutcomeIndex, OutcomeIndexRecord
from maid_runner.core.types import (
    OutcomeLesson,
    OutcomeReviewNote,
    OutcomeValidationEvidence,
)


def test_aggregate_outcome_insights_groups_records_deterministically():
    from maid_runner.core.outcome_insights import (
        OutcomeInsightGroup,
        OutcomeInsightsReport,
        aggregate_outcome_insights,
    )

    index = _index(
        _record(
            "beta",
            tags=("cli", "outcome"),
            declared_paths=("maid_runner/cli/commands/beta.py",),
            artifacts=("maid_runner/cli/commands/beta.py:function:cmd_beta",),
            task_type="fix",
            completed_at="2026-05-31T01:02:03+08:00",
            lesson_types=("validation",),
            review_severities=("warning",),
            validation_statuses=("passed",),
        ),
        _record(
            "alpha",
            tags=("cli", "outcome"),
            declared_paths=("maid_runner/core/alpha.py",),
            artifacts=("maid_runner/core/alpha.py:function:alpha_task",),
            task_type="feature",
            completed_at="2026-05-01T01:02:03Z",
            lesson_types=("testing",),
            review_severities=("info",),
            validation_statuses=("passed",),
        ),
    )

    report = aggregate_outcome_insights(index)

    assert isinstance(report, OutcomeInsightsReport)
    assert report.total_records == 2
    assert isinstance(report.by_tag[0], OutcomeInsightGroup)
    assert [(group.key, group.count) for group in report.by_tag] == [
        ("cli", 2),
        ("outcome", 2),
    ]
    assert report.by_tag[0].source_manifests == ("alpha", "beta")
    assert report.by_path == (
        OutcomeInsightGroup(
            key="maid_runner/cli/commands/beta.py",
            count=1,
            source_manifests=("beta",),
            lesson_types=("validation",),
            review_severities=("warning",),
        ),
        OutcomeInsightGroup(
            key="maid_runner/core/alpha.py",
            count=1,
            source_manifests=("alpha",),
            lesson_types=("testing",),
            review_severities=("info",),
        ),
    )
    assert [(group.key, group.count) for group in report.by_artifact] == [
        ("maid_runner/cli/commands/beta.py:function:cmd_beta", 1),
        ("maid_runner/core/alpha.py:function:alpha_task", 1),
    ]
    assert [(group.key, group.count) for group in report.by_change_type] == [
        ("feature", 1),
        ("fix", 1),
    ]
    assert [(group.key, group.count) for group in report.by_lesson_type] == [
        ("testing", 1),
        ("validation", 1),
    ]
    assert [(group.key, group.count) for group in report.by_review_severity] == [
        ("info", 1),
        ("warning", 1),
    ]
    assert report.by_completion_month == (
        OutcomeInsightGroup(
            key="2026-05",
            count=2,
            source_manifests=("alpha", "beta"),
            lesson_types=("testing", "validation"),
            review_severities=("info", "warning"),
        ),
    )


def test_aggregate_outcome_insights_uses_validation_evidence_statuses():
    from maid_runner.core.outcome_insights import aggregate_outcome_insights

    index = _index(
        _record(
            "alpha",
            validation_statuses=("passed", "failed", "skipped"),
            validation_commands=(("uv", "run", "pytest", "passed"),),
        )
    )

    report = aggregate_outcome_insights(index)

    assert [(group.key, group.count) for group in report.by_validation_status] == [
        ("failed", 1),
        ("passed", 1),
        ("skipped", 1),
    ]
    assert "passed" not in [group.key for group in report.by_change_type]


def test_aggregate_outcome_insights_deduplicates_source_records_and_supersession_chains():
    from maid_runner.core.outcome_insights import aggregate_outcome_insights

    duplicate = _record("duplicate", source_fingerprint="same")
    index = _index(
        duplicate,
        duplicate,
        _record("archived", lifecycle_status="archived"),
        _record("old", superseded_by="new"),
        _record("new"),
    )

    report = aggregate_outcome_insights(index)

    assert report.total_records == 2
    assert [group.key for group in report.by_tag] == ["outcome"]
    assert report.by_tag[0].count == 2
    assert report.by_tag[0].source_manifests == ("duplicate", "new")


def test_aggregate_outcome_insights_respects_group_limits():
    from maid_runner.core.outcome_insights import aggregate_outcome_insights

    index = _index(
        _record("alpha", tags=("zeta",)),
        _record("beta", tags=("alpha",)),
        _record("gamma", tags=("alpha",)),
        _record("delta", tags=("middle",)),
    )

    report = aggregate_outcome_insights(index, limit_per_group=2)

    assert [(group.key, group.count) for group in report.by_tag] == [
        ("alpha", 2),
        ("middle", 1),
    ]


def _index(*records: OutcomeIndexRecord) -> OutcomeIndex:
    return OutcomeIndex(
        schema_version="1",
        generated_from="fingerprint",
        included_statuses=("completed",),
        manifest_dir="manifests",
        project_root="/repo",
        records=records,
    )


def _record(
    slug: str,
    *,
    status: str = "completed",
    lifecycle_status: str = "active",
    superseded_by: str | None = None,
    task_type: str | None = "feature",
    completed_at: str | None = "2026-05-31T01:02:03Z",
    tags: tuple[str, ...] = ("outcome",),
    declared_paths: tuple[str, ...] = ("src/outcome.py",),
    artifacts: tuple[str, ...] = ("src/outcome.py:function:outcome_task",),
    lesson_types: tuple[str, ...] = ("testing",),
    review_severities: tuple[str, ...] = ("info",),
    validation_statuses: tuple[str, ...] = ("passed",),
    validation_commands: tuple[tuple[str, ...], ...] = (("uv", "run", "maid", "test"),),
    source_fingerprint: str | None = None,
) -> OutcomeIndexRecord:
    return OutcomeIndexRecord(
        manifest_slug=slug,
        manifest_path=f"manifests/{slug}.manifest.yaml",
        status=status,
        lifecycle_status=lifecycle_status,
        superseded_by=superseded_by,
        task_type=task_type,
        created="2026-05-30",
        completed_at=completed_at,
        tags=tags,
        declared_paths=declared_paths,
        artifacts=artifacts,
        validation_commands=validation_commands,
        validation_evidence=tuple(
            OutcomeValidationEvidence(
                command=("uv", "run", "maid", "test", validation_status),
                status=validation_status,
                summary=f"{validation_status} evidence.",
            )
            for validation_status in validation_statuses
        ),
        lessons=tuple(
            OutcomeLesson(
                lesson_type=lesson_type,
                summary=f"{lesson_type} lesson.",
                tags=(lesson_type,),
                paths=declared_paths,
            )
            for lesson_type in lesson_types
        ),
        review_notes=tuple(
            OutcomeReviewNote(
                source="implementation-review",
                severity=severity,
                summary=f"{severity} review.",
            )
            for severity in review_severities
        ),
        source_fingerprint=source_fingerprint or f"{slug}-fingerprint",
    )
