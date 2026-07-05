"""Behavioral tests for enrichment digest freshness assessment."""

from __future__ import annotations

from maid_runner.core.outcomes import OutcomeIndex, OutcomeIndexRecord
from maid_runner.core.types import (
    OutcomeLesson,
    OutcomeReviewNote,
    OutcomeValidationEvidence,
)


def test_check_digest_freshness_reports_missing_digest(tmp_path) -> None:
    from maid_runner.core.outcome_enrichment import (
        DigestFreshness,
        check_digest_freshness,
    )

    digest_path = tmp_path / "outcomes-digest.json"
    index = _index(_record("alpha"), generated_from="current-fingerprint")

    freshness = check_digest_freshness(index, digest_path)

    assert isinstance(freshness, DigestFreshness)
    assert freshness.status == "missing"
    assert freshness.digest_path == str(digest_path)
    assert "not found" in freshness.detail


def test_check_digest_freshness_reports_fresh_digest(tmp_path) -> None:
    from maid_runner.core.outcome_enrichment import (
        check_digest_freshness,
        write_enrichment_digest,
    )

    digest_path = tmp_path / "outcomes-digest.json"
    index = _index(_record("alpha"), generated_from="current-fingerprint")
    write_enrichment_digest(
        _digest(source_generated_from="current-fingerprint"),
        digest_path,
    )

    freshness = check_digest_freshness(index, digest_path)

    assert freshness.status == "fresh"
    assert freshness.digest_path == str(digest_path)
    assert "matches" in freshness.detail


def test_check_digest_freshness_reports_stale_digest(tmp_path) -> None:
    from maid_runner.core.outcome_enrichment import (
        check_digest_freshness,
        write_enrichment_digest,
    )

    digest_path = tmp_path / "outcomes-digest.json"
    index = _index(_record("alpha"), generated_from="current-fingerprint")
    write_enrichment_digest(
        _digest(source_generated_from="old-fingerprint"),
        digest_path,
    )

    freshness = check_digest_freshness(index, digest_path)

    assert freshness.status == "stale"
    assert freshness.digest_path == str(digest_path)
    assert "old-fingerprint" in freshness.detail
    assert "current-fingerprint" in freshness.detail


def test_check_digest_freshness_reports_malformed_digest_without_raising(
    tmp_path,
) -> None:
    from maid_runner.core.outcome_enrichment import check_digest_freshness

    digest_path = tmp_path / "outcomes-digest.json"
    digest_path.write_text("{not json", encoding="utf-8")
    index = _index(_record("alpha"), generated_from="current-fingerprint")

    freshness = check_digest_freshness(index, digest_path)

    assert freshness.status == "malformed"
    assert freshness.digest_path == str(digest_path)
    assert "Malformed enrichment digest" in freshness.detail


def test_check_digest_freshness_never_raises_on_unreadable_input(tmp_path) -> None:
    from maid_runner.core.outcome_enrichment import check_digest_freshness

    digest_path = tmp_path / "outcomes-digest.json"
    digest_path.mkdir()
    index = _index(_record("alpha"), generated_from="current-fingerprint")

    freshness = check_digest_freshness(index, digest_path)

    assert freshness.status == "malformed"
    assert freshness.digest_path == str(digest_path)
    assert freshness.detail


def _digest(
    *,
    source_generated_from: str = "fingerprint",
):
    from maid_runner.core.outcome_enrichment import EnrichmentDigest

    return EnrichmentDigest(
        schema_version="1",
        source_generated_from=source_generated_from,
        advisory=True,
        themes=(),
        digest_entries=(),
    )


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
    lifecycle_status: str = "active",
    superseded_by: str | None = None,
    source_fingerprint: str | None = None,
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
                summary="passed evidence.",
            ),
        ),
        lessons=(
            OutcomeLesson(
                lesson_type="testing",
                summary="testing lesson.",
                tags=("testing",),
                paths=("src/outcome.py",),
            ),
        ),
        review_notes=(
            OutcomeReviewNote(
                source="implementation-review",
                severity="info",
                summary="info review.",
            ),
        ),
        source_fingerprint=source_fingerprint or f"{slug}-fingerprint",
    )
