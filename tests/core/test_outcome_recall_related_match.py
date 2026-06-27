"""Behavioral tests for narrow related-match Outcome recall scoring."""

from __future__ import annotations

from maid_runner.core.outcomes import OutcomeIndex, OutcomeIndexRecord
from maid_runner.core.types import (
    OutcomeLesson,
    OutcomeReviewNote,
    OutcomeValidationEvidence,
)


def test_recall_partial_match_same_directory_surfaces_related_record() -> None:
    from maid_runner.core.outcome_recall import OutcomeRecallQuery, recall_outcomes

    record = _record(
        "same-directory",
        declared_paths=("maid_runner/core/chain.py",),
    )

    matches = recall_outcomes(
        _index(record),
        OutcomeRecallQuery(paths=("maid_runner/core/manifest.py",)),
    )

    assert [match.record.manifest_slug for match in matches] == ["same-directory"]
    assert matches[0].score == 20
    assert matches[0].reasons == ("path~dir:maid_runner/core (+20)",)


def test_recall_exact_path_outranks_partial_path() -> None:
    from maid_runner.core.outcome_recall import OutcomeRecallQuery, recall_outcomes

    exact = _record(
        "exact",
        declared_paths=("maid_runner/core/manifest.py",),
    )
    partial = _record(
        "partial",
        declared_paths=("maid_runner/core/chain.py",),
    )

    matches = recall_outcomes(
        _index(partial, exact),
        OutcomeRecallQuery(paths=("maid_runner/core/manifest.py",)),
    )

    assert [match.record.manifest_slug for match in matches] == ["exact", "partial"]
    assert matches[0].score == 80
    assert matches[0].reasons == ("path:maid_runner/core/manifest.py (+80)",)
    assert matches[1].score == 20
    assert matches[1].reasons == ("path~dir:maid_runner/core (+20)",)


def test_recall_related_tag_substring_surfaces_but_unrelated_excluded() -> None:
    from maid_runner.core.outcome_recall import OutcomeRecallQuery, recall_outcomes

    related = _record("related", tags=("validator-hardening",))
    unrelated = _record("unrelated", tags=("anti-gaming",))

    matches = recall_outcomes(
        _index(unrelated, related),
        OutcomeRecallQuery(tags=("hardening",)),
    )

    assert [match.record.manifest_slug for match in matches] == ["related"]
    assert matches[0].score == 10
    assert matches[0].reasons == ("tag~related:hardening (+10)",)


def test_recall_partial_match_still_requires_every_supplied_dimension() -> None:
    from maid_runner.core.outcome_recall import OutcomeRecallQuery, recall_outcomes

    path_only = _record(
        "path-only",
        tags=("planning",),
        declared_paths=("maid_runner/core/chain.py",),
    )

    matches = recall_outcomes(
        _index(path_only),
        OutcomeRecallQuery(
            paths=("maid_runner/core/manifest.py",),
            tags=("hardening",),
        ),
    )

    assert matches == []


def test_recall_unrelated_record_still_excluded() -> None:
    from maid_runner.core.outcome_recall import OutcomeRecallQuery, recall_outcomes

    unrelated = _record(
        "unrelated",
        tags=("anti-gaming",),
        declared_paths=("maid_runner/validators/javascript.py",),
    )

    matches = recall_outcomes(
        _index(unrelated),
        OutcomeRecallQuery(
            paths=("maid_runner/core/manifest.py",),
            tags=("hardening",),
        ),
    )

    assert matches == []


def test_recall_partial_does_not_inflate_above_exact_combination() -> None:
    from maid_runner.core.outcome_recall import OutcomeRecallQuery, recall_outcomes

    exact_combination = _record(
        "exact-combination",
        tags=("recall",),
        declared_paths=("maid_runner/core/manifest.py",),
    )
    partial_combination = _record(
        "partial-combination",
        tags=("outcome-recall", "recall-planning", "learning-loop"),
        declared_paths=(
            "maid_runner/core/chain.py",
            "maid_runner/core/outcomes.py",
        ),
    )

    matches = recall_outcomes(
        _index(partial_combination, exact_combination),
        OutcomeRecallQuery(
            paths=(
                "maid_runner/core/manifest.py",
                "maid_runner/core/validate.py",
                "maid_runner/core/result.py",
                "maid_runner/core/types.py",
                "maid_runner/core/graph.py",
                "maid_runner/core/index.py",
            ),
            tags=("recall", "outcome", "planning", "learning", "loop"),
        ),
    )

    assert [match.record.manifest_slug for match in matches] == [
        "exact-combination",
        "partial-combination",
    ]
    assert matches[0].score == 120
    assert matches[0].reasons == (
        "path:maid_runner/core/manifest.py (+80)",
        "tag:recall (+40)",
    )
    assert matches[1].score == 30
    assert matches[1].reasons == (
        "path~dir:maid_runner/core (+20)",
        "tag~related:recall (+10)",
    )


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
