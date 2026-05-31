"""Deterministic aggregations for learned Outcome index records."""

from __future__ import annotations

from dataclasses import dataclass
import re
from typing import Callable, Iterable

from maid_runner.core.outcomes import OutcomeIndex, OutcomeIndexRecord


@dataclass(frozen=True)
class OutcomeInsightGroup:
    key: str
    count: int
    source_manifests: tuple[str, ...]
    lesson_types: tuple[str, ...]
    review_severities: tuple[str, ...]


@dataclass(frozen=True)
class OutcomeInsightsReport:
    total_records: int
    by_tag: tuple[OutcomeInsightGroup, ...]
    by_path: tuple[OutcomeInsightGroup, ...]
    by_artifact: tuple[OutcomeInsightGroup, ...]
    by_change_type: tuple[OutcomeInsightGroup, ...]
    by_lesson_type: tuple[OutcomeInsightGroup, ...]
    by_review_severity: tuple[OutcomeInsightGroup, ...]
    by_validation_status: tuple[OutcomeInsightGroup, ...]
    by_completion_month: tuple[OutcomeInsightGroup, ...]


def aggregate_outcome_insights(
    index: OutcomeIndex,
    limit_per_group: int = 10,
) -> OutcomeInsightsReport:
    records = tuple(_active_unique_records(index.records))
    return OutcomeInsightsReport(
        total_records=len(records),
        by_tag=_aggregate(records, lambda record: record.tags, limit_per_group),
        by_path=_aggregate(
            records, lambda record: record.declared_paths, limit_per_group
        ),
        by_artifact=_aggregate(
            records, lambda record: record.artifacts, limit_per_group
        ),
        by_change_type=_aggregate(
            records,
            lambda record: (record.task_type or "unknown",),
            limit_per_group,
        ),
        by_lesson_type=_aggregate(
            records,
            lambda record: tuple(lesson.lesson_type for lesson in record.lessons),
            limit_per_group,
        ),
        by_review_severity=_aggregate(
            records,
            lambda record: tuple(note.severity for note in record.review_notes),
            limit_per_group,
        ),
        by_validation_status=_aggregate(
            records,
            lambda record: tuple(
                evidence.status for evidence in record.validation_evidence
            ),
            limit_per_group,
        ),
        by_completion_month=_aggregate(
            records,
            lambda record: (_completion_month(record.completed_at),),
            limit_per_group,
        ),
    )


_ACTIVE_LIFECYCLE_STATUSES = frozenset({"active"})
_MONTH_PATTERN = re.compile(r"^\d{4}-\d{2}")


def _active_unique_records(
    records: Iterable[OutcomeIndexRecord],
) -> list[OutcomeIndexRecord]:
    unique_by_source: dict[tuple[str, str], OutcomeIndexRecord] = {}
    for record in records:
        if record.status != "completed":
            continue
        if record.lifecycle_status not in _ACTIVE_LIFECYCLE_STATUSES:
            continue
        unique_by_source.setdefault(
            (record.manifest_slug, record.source_fingerprint),
            record,
        )

    active_slugs = {record.manifest_slug for record in unique_by_source.values()}
    filtered = [
        record
        for record in unique_by_source.values()
        if record.superseded_by is None or record.superseded_by not in active_slugs
    ]
    return sorted(
        filtered, key=lambda record: (record.manifest_slug, record.manifest_path)
    )


def _aggregate(
    records: Iterable[OutcomeIndexRecord],
    key_func: Callable[[OutcomeIndexRecord], Iterable[str]],
    limit: int,
) -> tuple[OutcomeInsightGroup, ...]:
    grouped: dict[str, dict[str, set[str]]] = {}
    for record in records:
        lesson_types = {lesson.lesson_type for lesson in record.lessons}
        review_severities = {note.severity for note in record.review_notes}
        for key in _unique_keys(key_func(record)):
            bucket = grouped.setdefault(
                key,
                {
                    "source_manifests": set(),
                    "lesson_types": set(),
                    "review_severities": set(),
                },
            )
            bucket["source_manifests"].add(record.manifest_slug)
            bucket["lesson_types"].update(lesson_types)
            bucket["review_severities"].update(review_severities)

    groups = [
        OutcomeInsightGroup(
            key=key,
            count=len(values["source_manifests"]),
            source_manifests=tuple(sorted(values["source_manifests"])),
            lesson_types=tuple(sorted(values["lesson_types"])),
            review_severities=tuple(sorted(values["review_severities"])),
        )
        for key, values in grouped.items()
    ]
    groups.sort(key=lambda group: (-group.count, group.key))
    return tuple(groups[: max(0, limit)])


def _unique_keys(keys: Iterable[str]) -> tuple[str, ...]:
    return tuple(sorted({str(key) for key in keys if str(key).strip()}))


def _completion_month(completed_at: str | None) -> str:
    if completed_at is None:
        return "unknown"
    match = _MONTH_PATTERN.match(completed_at)
    return match.group(0) if match else "unknown"
