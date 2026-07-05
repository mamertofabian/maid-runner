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


def test_build_request_optionally_invites_grounded_improvement_hypotheses():
    from maid_runner.core.outcome_enrichment import build_enrichment_request

    prompt = build_enrichment_request(_index(_record("alpha"))).system_prompt.lower()

    assert "improvement_hypotheses" in prompt
    assert "zero to five" in prompt
    assert "at least two" in prompt
    assert "distinct manifests" in prompt
    assert "propose nothing" in prompt


@pytest.mark.parametrize(
    ("lesson_type_count", "expected_band"),
    (
        (6, "about 2-3 canonical themes"),
        (48, "about 6-8 canonical themes"),
        (78, "about 8-12 canonical themes"),
        (200, "about 8-12 canonical themes"),
    ),
)
def test_build_request_scales_theme_band_to_corpus_size(
    lesson_type_count: int,
    expected_band: str,
):
    from maid_runner.core.outcome_enrichment import build_enrichment_request

    lesson_types = tuple(f"lesson-{index:03d}" for index in range(lesson_type_count))
    index = _index(_record("alpha", lesson_types=lesson_types))

    assert expected_band in build_enrichment_request(index).system_prompt


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


def test_validate_digest_accepts_grounded_improvement_hypothesis():
    from maid_runner.core.outcome_enrichment import validate_enrichment_digest

    index = _index(
        _record("alpha", lesson_types=("validation",)),
        _record("beta", lesson_types=("testing",)),
    )
    digest = _digest(
        hypotheses=(
            _hypothesis(
                source_lessons=(
                    _lesson_ref("alpha", "validation"),
                    _lesson_ref("beta", "testing"),
                ),
            ),
        ),
    )

    assert validate_enrichment_digest(digest, index) is None


def test_validate_digest_rejects_hypothesis_non_cooccurring_source_lesson():
    from maid_runner.core.outcome_enrichment import validate_enrichment_digest

    index = _index(
        _record("alpha", lesson_types=("validation",)),
        _record("beta", lesson_types=("testing",)),
    )
    digest = _digest(
        hypotheses=(
            _hypothesis(
                source_lessons=(
                    _lesson_ref("alpha", "validation"),
                    _lesson_ref("beta", "validation"),
                ),
            ),
        ),
    )

    with pytest.raises(ValueError, match="beta.*validation"):
        validate_enrichment_digest(digest, index)


def test_validate_digest_rejects_hypothesis_with_fewer_than_two_lessons():
    from maid_runner.core.outcome_enrichment import validate_enrichment_digest

    index = _index(_record("alpha", lesson_types=("validation",)))
    digest = _digest(
        hypotheses=(
            _hypothesis(
                source_lessons=(_lesson_ref("alpha", "validation"),),
            ),
        ),
    )

    with pytest.raises(ValueError, match="at least two source lessons"):
        validate_enrichment_digest(digest, index)


def test_validate_digest_rejects_hypothesis_with_fewer_than_two_manifests():
    from maid_runner.core.outcome_enrichment import validate_enrichment_digest

    index = _index(_record("alpha", lesson_types=("validation", "testing")))
    digest = _digest(
        hypotheses=(
            _hypothesis(
                source_lessons=(
                    _lesson_ref("alpha", "validation"),
                    _lesson_ref("alpha", "testing"),
                ),
            ),
        ),
    )

    with pytest.raises(ValueError, match="at least two distinct manifests"):
        validate_enrichment_digest(digest, index)


@pytest.mark.parametrize("summary", ("", "   "))
def test_validate_digest_rejects_blank_hypothesis_summary(summary: str):
    from maid_runner.core.outcome_enrichment import validate_enrichment_digest

    index = _index(
        _record("alpha", lesson_types=("validation",)),
        _record("beta", lesson_types=("testing",)),
    )
    digest = _digest(
        hypotheses=(
            _hypothesis(
                summary=summary,
                source_lessons=(
                    _lesson_ref("alpha", "validation"),
                    _lesson_ref("beta", "testing"),
                ),
            ),
        ),
    )

    with pytest.raises(ValueError, match="hypothesis summary must not be empty"):
        validate_enrichment_digest(digest, index)


def test_validate_theme_map_ignores_invalid_hypotheses():
    from maid_runner.core.outcome_enrichment import validate_enrichment_theme_map

    index = _index(_record("alpha", lesson_types=("validation",)))
    digest = _digest(
        themes=(
            _theme(
                canonical_name="validation",
                member_lesson_types=("validation",),
                source_manifests=("alpha",),
            ),
        ),
        hypotheses=(
            _hypothesis(
                source_lessons=(_lesson_ref("alpha", "validation"),),
            ),
        ),
    )

    assert validate_enrichment_theme_map(digest, index) is None


def test_validate_theme_map_still_rejects_fabricated_theme_data():
    from maid_runner.core.outcome_enrichment import validate_enrichment_theme_map

    index = _index(_record("alpha", lesson_types=("validation",)))
    digest = _digest(
        themes=(
            _theme(
                canonical_name="validation",
                member_lesson_types=("fabricated-type",),
                source_manifests=("alpha",),
            ),
        ),
        hypotheses=(
            _hypothesis(
                source_lessons=(_lesson_ref("alpha", "validation"),),
            ),
        ),
    )

    with pytest.raises(ValueError, match="fabricated-type"):
        validate_enrichment_theme_map(digest, index)


@pytest.mark.parametrize(
    ("summary", "expected_message"),
    (
        ("", "theme summary must not be empty"),
        ("   ", "theme summary must not be empty"),
    ),
)
def test_validate_digest_rejects_empty_theme_summary(
    summary: str,
    expected_message: str,
):
    from maid_runner.core.outcome_enrichment import validate_enrichment_digest

    index = _index(_record("alpha", lesson_types=("validation",)))
    digest = _digest(
        themes=(
            _theme(
                canonical_name="validation",
                member_lesson_types=("validation",),
                source_manifests=("alpha",),
                summary=summary,
            ),
        ),
        entries=(
            _entry(
                theme="validation",
                source_lessons=(_lesson_ref("alpha", "validation"),),
            ),
        ),
    )

    with pytest.raises(ValueError, match=expected_message):
        validate_enrichment_digest(digest, index)


@pytest.mark.parametrize(
    ("summary", "expected_message"),
    (
        ("", "digest entry summary must not be empty"),
        ("   ", "digest entry summary must not be empty"),
    ),
)
def test_validate_digest_rejects_empty_entry_summary(
    summary: str,
    expected_message: str,
):
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
                summary=summary,
                source_lessons=(_lesson_ref("alpha", "validation"),),
            ),
        ),
    )

    with pytest.raises(ValueError, match=expected_message):
        validate_enrichment_digest(digest, index)


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


def test_theme_map_from_digest_returns_lesson_type_to_canonical_theme():
    from maid_runner.core.outcome_enrichment import theme_map_from_digest

    digest = _digest(
        themes=(
            _theme(
                canonical_name="validation",
                member_lesson_types=("validation", "validation-workflow"),
                source_manifests=("alpha", "beta"),
            ),
            _theme(
                canonical_name="testing",
                member_lesson_types=("test-design",),
                source_manifests=("gamma",),
            ),
        ),
    )

    assert theme_map_from_digest(digest) == {
        "test-design": "testing",
        "validation": "validation",
        "validation-workflow": "validation",
    }


def test_theme_map_from_digest_agrees_with_apply_theme_map_grouping():
    from maid_runner.core.outcome_enrichment import (
        apply_theme_map,
        theme_map_from_digest,
    )

    index = _index(
        _record("alpha", lesson_types=("validation",)),
        _record("beta", lesson_types=("validation-workflow",)),
        _record("gamma", lesson_types=("testing",)),
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

    theme_map = theme_map_from_digest(digest)
    groups = apply_theme_map(index, digest)

    assert theme_map == {
        "validation": "validation",
        "validation-workflow": "validation",
    }
    assert {group.key for group in groups} == {
        theme_map.get("validation", "validation"),
        theme_map.get("validation-workflow", "validation-workflow"),
        theme_map.get("testing", "testing"),
    }


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


def test_render_digest_markdown_lists_advisory_hypotheses_with_citations():
    from maid_runner.core.outcome_enrichment import render_digest_markdown

    digest = _digest(
        hypotheses=(
            _hypothesis(
                summary="Add a stricter validation fixture.",
                source_lessons=(
                    _lesson_ref("alpha", "validation"),
                    _lesson_ref("beta", "testing"),
                ),
            ),
        ),
    )

    markdown = render_digest_markdown(digest)

    assert "## Improvement Hypotheses (advisory)" in markdown
    assert "model-generated suggestions" in markdown
    assert "not findings, commitments, or backlog items" in markdown
    assert "Add a stricter validation fixture." in markdown
    assert "alpha:validation" in markdown
    assert "beta:testing" in markdown


def test_render_digest_markdown_omits_hypotheses_section_when_empty():
    from maid_runner.core.outcome_enrichment import render_digest_markdown

    markdown = render_digest_markdown(_digest())

    assert "Improvement Hypotheses" not in markdown


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


def test_digest_without_hypotheses_parses_empty_and_roundtrips_legacy_shape():
    from maid_runner.core.outcome_enrichment import (
        enrichment_digest_from_dict,
        enrichment_digest_to_dict,
    )

    legacy_data = {
        "advisory": True,
        "digest_entries": [],
        "schema_version": "1",
        "source_generated_from": "fingerprint",
        "themes": [],
    }

    digest = enrichment_digest_from_dict(legacy_data)

    assert digest.improvement_hypotheses == ()
    assert enrichment_digest_to_dict(digest) == legacy_data


def test_digest_roundtrip_emits_non_empty_hypotheses():
    from maid_runner.core.outcome_enrichment import (
        enrichment_digest_from_dict,
        enrichment_digest_to_dict,
    )

    digest = _digest(
        hypotheses=(
            _hypothesis(
                summary="Add a focused review bypass fixture.",
                source_lessons=(
                    _lesson_ref("alpha", "validation"),
                    _lesson_ref("beta", "testing"),
                ),
            ),
        ),
    )

    data = enrichment_digest_to_dict(digest)
    parsed = enrichment_digest_from_dict(json.loads(json.dumps(data)))

    assert data["improvement_hypotheses"] == [
        {
            "summary": "Add a focused review bypass fixture.",
            "source_lessons": [
                {"lesson_type": "validation", "manifest_slug": "alpha"},
                {"lesson_type": "testing", "manifest_slug": "beta"},
            ],
        }
    ]
    assert parsed == digest


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
    hypotheses: tuple[object, ...] = (),
):
    from maid_runner.core.outcome_enrichment import EnrichmentDigest

    return EnrichmentDigest(
        schema_version="1",
        source_generated_from=source_generated_from,
        advisory=True,
        themes=themes,
        digest_entries=entries,
        improvement_hypotheses=hypotheses,
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


def _hypothesis(
    *,
    source_lessons: tuple[object, ...],
    summary: str = "Hypothesis summary.",
):
    from maid_runner.core.outcome_enrichment import HypothesisEntry

    return HypothesisEntry(summary=summary, source_lessons=source_lessons)


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
