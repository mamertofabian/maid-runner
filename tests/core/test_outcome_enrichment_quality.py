"""Behavioral tests for enrichment prompt and digest quality warnings."""

from __future__ import annotations

import json

from maid_runner.core.outcomes import OutcomeIndex, OutcomeIndexRecord
from maid_runner.core.types import (
    OutcomeLesson,
    OutcomeReviewNote,
    OutcomeValidationEvidence,
)


def test_request_user_prompt_includes_lesson_type_frequency_table():
    from maid_runner.core.outcome_enrichment import build_enrichment_request

    index = _index(
        _record("alpha", lesson_types=("validation", "testing")),
        _record("beta", lesson_types=("validation", "workflow")),
        _record("archived", lifecycle_status="archived", lesson_types=("ignored",)),
    )

    payload = json.loads(build_enrichment_request(index).user_prompt)

    assert payload["lesson_type_frequencies"] == [
        {"lesson_type": "testing", "count": 1},
        {"lesson_type": "validation", "count": 2},
        {"lesson_type": "workflow", "count": 1},
    ]


def test_request_system_prompt_instructs_canonical_multi_member_grouping():
    from maid_runner.core.outcome_enrichment import build_enrichment_request

    prompt = build_enrichment_request(_index(_record("alpha"))).system_prompt.lower()

    assert "canonical" in prompt
    assert "every lesson_type" in prompt
    assert "8-12" in prompt
    assert "near-synonym" in prompt
    assert "validation" in prompt
    assert "multi" in prompt
    assert "member_lesson_types" in prompt


def test_request_system_prompt_requires_multi_source_recurring_entries():
    from maid_runner.core.outcome_enrichment import build_enrichment_request

    prompt = build_enrichment_request(_index(_record("alpha"))).system_prompt.lower()

    assert "digest_entries" in prompt
    assert "source_lessons" in prompt
    assert "at least two" in prompt
    assert "distinct manifests" in prompt


def test_request_system_prompt_states_coverage_and_output_schema():
    from maid_runner.core.outcome_enrichment import build_enrichment_request

    prompt = build_enrichment_request(_index(_record("alpha"))).system_prompt.lower()

    assert "coverage" in prompt
    assert "schema_version" in prompt
    assert "source_generated_from" in prompt
    assert "themes" in prompt
    assert "digest_entries" in prompt


def test_assess_quality_flags_low_coverage():
    from maid_runner.core.outcome_enrichment import (
        DigestQualityWarning,
        assess_digest_quality,
    )

    index = _index(
        _record("alpha", lesson_types=("validation", "testing")),
        _record("beta", lesson_types=("workflow", "cli")),
        _record("gamma", lesson_types=("docs",)),
    )
    digest = _digest(
        themes=(
            _theme(
                canonical_name="validation",
                member_lesson_types=("validation",),
                source_manifests=("alpha",),
            ),
        )
    )

    warnings = assess_digest_quality(digest, index)

    assert _codes(warnings) == ("low_coverage",)
    assert isinstance(warnings[0], DigestQualityWarning)
    assert warnings[0].message


def test_assess_quality_flags_singleton_theme_map():
    from maid_runner.core.outcome_enrichment import assess_digest_quality

    index = _index(
        _record("alpha", lesson_types=("validation", "testing")),
        _record("beta", lesson_types=("workflow", "cli")),
    )
    digest = _digest(
        themes=(
            _theme(
                canonical_name="validation",
                member_lesson_types=("validation",),
                source_manifests=("alpha",),
            ),
            _theme(
                canonical_name="testing",
                member_lesson_types=("testing",),
                source_manifests=("alpha",),
            ),
            _theme(
                canonical_name="workflow",
                member_lesson_types=("workflow",),
                source_manifests=("beta",),
            ),
            _theme(
                canonical_name="cli",
                member_lesson_types=("cli",),
                source_manifests=("beta",),
            ),
        )
    )

    assert _codes(assess_digest_quality(digest, index)) == ("singleton_theme_map",)


def test_assess_quality_flags_single_source_entries():
    from maid_runner.core.outcome_enrichment import assess_digest_quality

    index = _index(
        _record("alpha", lesson_types=("validation", "testing")),
        _record("beta", lesson_types=("validation", "testing")),
    )
    digest = _digest(
        themes=(
            _theme(
                canonical_name="validation",
                member_lesson_types=("validation", "testing"),
                source_manifests=("alpha", "beta"),
            ),
        ),
        entries=(
            _entry(
                theme="validation",
                source_lessons=(_lesson_ref("alpha", "validation"),),
            ),
        ),
    )

    assert _codes(assess_digest_quality(digest, index)) == ("single_source_entry",)


def test_assess_quality_returns_empty_for_strong_digest():
    from maid_runner.core.outcome_enrichment import assess_digest_quality

    index = _index(
        _record("alpha", lesson_types=("validation", "testing", "workflow")),
        _record("beta", lesson_types=("validation", "testing", "workflow", "cli")),
    )
    digest = _digest(
        themes=(
            _theme(
                canonical_name="validation",
                member_lesson_types=("validation", "testing"),
                source_manifests=("alpha", "beta"),
            ),
            _theme(
                canonical_name="delivery",
                member_lesson_types=("workflow", "cli"),
                source_manifests=("alpha", "beta"),
            ),
        ),
        entries=(
            _entry(
                theme="validation",
                source_lessons=(
                    _lesson_ref("alpha", "validation"),
                    _lesson_ref("beta", "testing"),
                ),
            ),
            _entry(
                theme="delivery",
                source_lessons=(
                    _lesson_ref("alpha", "workflow"),
                    _lesson_ref("beta", "cli"),
                ),
            ),
        ),
    )

    assert assess_digest_quality(digest, index) == ()


def test_assess_quality_never_raises():
    from maid_runner.core.outcome_enrichment import assess_digest_quality

    index = _index(_record("alpha", lesson_types=("validation", "testing")))
    degenerate_digest = _digest()

    warnings = assess_digest_quality(degenerate_digest, index)

    assert _codes(warnings) == ("low_coverage",)


def _codes(warnings: tuple[object, ...]) -> tuple[str, ...]:
    return tuple(warning.code for warning in warnings)


def _digest(
    *,
    themes: tuple[object, ...] = (),
    entries: tuple[object, ...] = (),
):
    from maid_runner.core.outcome_enrichment import EnrichmentDigest

    return EnrichmentDigest(
        schema_version="1",
        source_generated_from="fingerprint",
        advisory=True,
        themes=themes,
        digest_entries=entries,
    )


def _theme(
    *,
    canonical_name: str,
    member_lesson_types: tuple[str, ...],
    source_manifests: tuple[str, ...],
):
    from maid_runner.core.outcome_enrichment import EnrichmentTheme

    return EnrichmentTheme(
        canonical_name=canonical_name,
        member_lesson_types=member_lesson_types,
        summary="Theme summary.",
        source_manifests=source_manifests,
    )


def _entry(*, theme: str, source_lessons: tuple[object, ...]):
    from maid_runner.core.outcome_enrichment import DigestEntry

    return DigestEntry(
        theme=theme,
        summary="Digest entry summary.",
        source_lessons=source_lessons,
    )


def _lesson_ref(manifest_slug: str, lesson_type: str):
    from maid_runner.core.outcome_enrichment import LessonRef

    return LessonRef(manifest_slug=manifest_slug, lesson_type=lesson_type)


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
    lifecycle_status: str = "active",
    superseded_by: str | None = None,
    lesson_types: tuple[str, ...] = ("testing",),
) -> OutcomeIndexRecord:
    return OutcomeIndexRecord(
        manifest_slug=slug,
        manifest_path=f"manifests/{slug}.manifest.yaml",
        status="completed",
        lifecycle_status=lifecycle_status,
        superseded_by=superseded_by,
        task_type="feature",
        created="2026-05-30",
        completed_at="2026-05-31T01:02:03Z",
        tags=("outcome",),
        declared_paths=("src/outcome.py",),
        artifacts=("src/outcome.py:function:outcome_task",),
        validation_commands=(("uv", "run", "maid", "test"),),
        validation_evidence=(
            OutcomeValidationEvidence(
                command=("uv", "run", "maid", "test"),
                status="passed",
                summary="Validation passed.",
            ),
        ),
        lessons=tuple(
            OutcomeLesson(
                lesson_type=lesson_type,
                summary=f"{lesson_type} lesson.",
                tags=(lesson_type,),
                paths=("src/outcome.py",),
            )
            for lesson_type in lesson_types
        ),
        review_notes=(
            OutcomeReviewNote(
                source="implementation-review",
                severity="info",
                summary="Ready for enrichment.",
            ),
        ),
        source_fingerprint=f"{slug}-fingerprint",
    )
