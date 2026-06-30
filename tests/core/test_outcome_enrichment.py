"""Behavioral tests for deterministic Outcome enrichment policy."""

from __future__ import annotations

import json

import pytest

from maid_runner.core.outcomes import OutcomeIndex, OutcomeIndexRecord
from maid_runner.core.types import (
    OutcomeLesson,
    OutcomeReviewNote,
    OutcomeValidationEvidence,
)


def test_build_request_covers_active_lesson_types_and_slugs():
    from maid_runner.core.outcome_enrichment import (
        EnrichmentRequest,
        build_enrichment_request,
    )

    index = _index(
        _record("alpha", lesson_types=("validation",)),
        _record("beta", lesson_types=("implementation",)),
        _record("inactive", lifecycle_status="archived", lesson_types=("ignored",)),
    )

    request = build_enrichment_request(index)

    assert isinstance(request, EnrichmentRequest)
    assert request.known_lesson_types == ("implementation", "validation")
    assert request.known_manifest_slugs == ("alpha", "beta")
    assert "cluster" in request.system_prompt
    assert "alpha" in request.user_prompt
    assert "validation" in request.user_prompt
    assert "inactive" not in request.user_prompt
    assert "ignored" not in request.user_prompt


def test_validate_digest_accepts_grounded_digest():
    from maid_runner.core.outcome_enrichment import validate_enrichment_digest

    index = _index(_record("alpha", lesson_types=("validation",)))
    digest = _digest(
        themes=(
            _theme(
                canonical_name="validation",
                member_lesson_types=("validation",),
                source_manifests=("alpha",),
            ),
        ),
        entries=(
            _entry(
                theme="validation",
                source_lessons=(_lesson_ref("alpha", "validation"),),
            ),
        ),
    )

    assert validate_enrichment_digest(digest, index) is None


def test_validate_digest_rejects_unknown_manifest_slug():
    from maid_runner.core.outcome_enrichment import validate_enrichment_digest

    index = _index(_record("alpha", lesson_types=("validation",)))
    digest = _digest(
        themes=(
            _theme(
                canonical_name="validation",
                member_lesson_types=("validation",),
                source_manifests=("missing",),
            ),
        ),
        entries=(
            _entry(
                theme="validation",
                source_lessons=(_lesson_ref("missing", "validation"),),
            ),
        ),
    )

    with pytest.raises(ValueError, match="missing"):
        validate_enrichment_digest(digest, index)


def test_validate_digest_rejects_non_cooccurring_lesson_type():
    from maid_runner.core.outcome_enrichment import validate_enrichment_digest

    index = _index(
        _record("alpha", lesson_types=("validation",)),
        _record("beta", lesson_types=("testing",)),
    )
    digest = _digest(
        themes=(
            _theme(
                canonical_name="validation",
                member_lesson_types=("validation",),
                source_manifests=("beta",),
            ),
        ),
        entries=(
            _entry(
                theme="validation",
                source_lessons=(_lesson_ref("beta", "validation"),),
            ),
        ),
    )

    with pytest.raises(ValueError, match="beta.*validation"):
        validate_enrichment_digest(digest, index)


def test_validate_digest_rejects_entry_with_undeclared_theme():
    from maid_runner.core.outcome_enrichment import validate_enrichment_digest

    index = _index(_record("alpha", lesson_types=("validation",)))
    digest = _digest(
        themes=(
            _theme(
                canonical_name="validation",
                member_lesson_types=("validation",),
                source_manifests=("alpha",),
            ),
        ),
        entries=(
            _entry(
                theme="fabricated-theme",
                source_lessons=(_lesson_ref("alpha", "validation"),),
            ),
        ),
    )

    with pytest.raises(ValueError, match="fabricated-theme"):
        validate_enrichment_digest(digest, index)


def test_validate_digest_rejects_source_lesson_under_wrong_theme():
    from maid_runner.core.outcome_enrichment import validate_enrichment_digest

    index = _index(_record("alpha", lesson_types=("validation", "testing")))
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
        ),
        entries=(
            _entry(
                theme="validation",
                source_lessons=(_lesson_ref("alpha", "testing"),),
            ),
        ),
    )

    with pytest.raises(ValueError, match="testing.*validation"):
        validate_enrichment_digest(digest, index)


def test_validate_digest_rejects_lesson_type_in_multiple_themes():
    from maid_runner.core.outcome_enrichment import validate_enrichment_digest

    index = _index(_record("alpha", lesson_types=("validation",)))
    digest = _digest(
        themes=(
            _theme(
                canonical_name="validation",
                member_lesson_types=("validation",),
                source_manifests=("alpha",),
            ),
            _theme(
                canonical_name="validation-process",
                member_lesson_types=("validation",),
                source_manifests=("alpha",),
            ),
        ),
        entries=(
            _entry(
                theme="validation",
                source_lessons=(_lesson_ref("alpha", "validation"),),
            ),
        ),
    )

    with pytest.raises(ValueError, match="validation"):
        validate_enrichment_digest(digest, index)


def test_apply_theme_map_collapses_fragmented_lesson_types():
    from maid_runner.core.outcome_enrichment import apply_theme_map
    from maid_runner.core.outcome_insights import OutcomeInsightGroup

    index = _index(
        _record("alpha", lesson_types=("validation",)),
        _record("beta", lesson_types=("validation-workflow",)),
    )
    digest = _digest(
        themes=(
            _theme(
                canonical_name="validation",
                member_lesson_types=("validation", "validation-workflow"),
                source_manifests=("alpha", "beta"),
            ),
        ),
        entries=(),
    )

    groups = apply_theme_map(index, digest)

    assert groups == (
        OutcomeInsightGroup(
            key="validation",
            count=2,
            source_manifests=("alpha", "beta"),
            lesson_types=("validation", "validation-workflow"),
            review_severities=("info",),
        ),
    )


def test_apply_theme_map_passes_through_unmapped_lesson_types():
    from maid_runner.core.outcome_enrichment import apply_theme_map

    index = _index(
        _record("alpha", lesson_types=("validation",)),
        _record("beta", lesson_types=("testing",)),
    )
    digest = _digest(
        themes=(
            _theme(
                canonical_name="delivery",
                member_lesson_types=("validation",),
                source_manifests=("alpha",),
            ),
        ),
        entries=(),
    )

    groups = apply_theme_map(index, digest)

    assert [(group.key, group.count) for group in groups] == [
        ("delivery", 1),
        ("testing", 1),
    ]


def test_render_digest_markdown_lists_themes_and_entries():
    from maid_runner.core.outcome_enrichment import render_digest_markdown

    digest = _digest(
        themes=(
            _theme(
                canonical_name="validation",
                member_lesson_types=("validation",),
                summary="Validation habits recur.",
                source_manifests=("alpha",),
            ),
        ),
        entries=(
            _entry(
                theme="validation",
                summary="Keep red evidence visible.",
                source_lessons=(_lesson_ref("alpha", "validation"),),
            ),
        ),
    )

    markdown = render_digest_markdown(digest)

    assert "# Outcome Enrichment Digest" in markdown
    assert "advisory" in markdown
    assert "validation" in markdown
    assert "Validation habits recur." in markdown
    assert "Keep red evidence visible." in markdown
    assert "alpha:validation" in markdown


def test_digest_is_stale_detects_fingerprint_change():
    from maid_runner.core.outcome_enrichment import digest_is_stale

    index = _index(_record("alpha"), generated_from="current-fingerprint")
    matching = _digest(source_generated_from="current-fingerprint")
    stale = _digest(source_generated_from="old-fingerprint")

    assert digest_is_stale(matching, index) is False
    assert digest_is_stale(stale, index) is True


def test_digest_roundtrips_through_dict_and_file(tmp_path):
    from maid_runner.core.outcome_enrichment import (
        enrichment_digest_from_dict,
        enrichment_digest_to_dict,
        read_enrichment_digest,
        write_enrichment_digest,
    )

    digest = _digest(
        themes=(
            _theme(
                canonical_name="validation",
                member_lesson_types=("validation",),
                source_manifests=("alpha",),
            ),
        ),
        entries=(
            _entry(
                theme="validation",
                source_lessons=(_lesson_ref("alpha", "validation"),),
            ),
        ),
    )
    data = enrichment_digest_to_dict(digest)
    path = tmp_path / "digest.json"

    parsed = enrichment_digest_from_dict(json.loads(json.dumps(data)))
    write_enrichment_digest(parsed, path)

    assert read_enrichment_digest(path) == digest


def test_active_unique_records_matches_insights_record_set():
    from maid_runner.core.outcome_insights import (
        active_unique_records,
        aggregate_outcome_insights,
    )

    duplicate = _record("duplicate", source_fingerprint="same")
    index = _index(
        duplicate,
        duplicate,
        _record("archived", lifecycle_status="archived"),
        _record("old", superseded_by="new"),
        _record("new"),
    )

    records = active_unique_records(index)
    report = aggregate_outcome_insights(index)

    assert tuple(record.manifest_slug for record in records) == ("duplicate", "new")
    assert report.total_records == len(records)
    assert report.by_tag[0].source_manifests == ("duplicate", "new")


def _digest(
    *,
    source_generated_from: str = "fingerprint",
    themes: tuple[object, ...] = (),
    entries: tuple[object, ...] = (),
):
    from maid_runner.core.outcome_enrichment import EnrichmentDigest

    return EnrichmentDigest(
        schema_version="1",
        source_generated_from=source_generated_from,
        advisory=True,
        themes=themes,
        digest_entries=entries,
    )


def _theme(
    *,
    canonical_name: str,
    member_lesson_types: tuple[str, ...],
    source_manifests: tuple[str, ...],
    summary: str = "Theme summary.",
):
    from maid_runner.core.outcome_enrichment import EnrichmentTheme

    return EnrichmentTheme(
        canonical_name=canonical_name,
        member_lesson_types=member_lesson_types,
        summary=summary,
        source_manifests=source_manifests,
    )


def _entry(
    *,
    theme: str,
    source_lessons: tuple[object, ...],
    summary: str = "Digest entry summary.",
):
    from maid_runner.core.outcome_enrichment import DigestEntry

    return DigestEntry(
        theme=theme,
        summary=summary,
        source_lessons=source_lessons,
    )


def _lesson_ref(manifest_slug: str, lesson_type: str):
    from maid_runner.core.outcome_enrichment import LessonRef

    return LessonRef(manifest_slug=manifest_slug, lesson_type=lesson_type)


def _index(
    *records: OutcomeIndexRecord,
    generated_from: str = "fingerprint",
) -> OutcomeIndex:
    return OutcomeIndex(
        schema_version="1",
        generated_from=generated_from,
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
