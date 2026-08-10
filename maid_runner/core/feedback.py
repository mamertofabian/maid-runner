"""Deterministic, privacy-bounded exports of explicit Outcome feedback."""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
from pathlib import Path
from typing import Union

from maid_runner.core.outcomes import OutcomeIndex


@dataclass(frozen=True)
class FeedbackRecord:
    """One exact lesson aggregate without repository source identity."""

    feedback_id: str
    lesson_type: str
    summary: str
    source_count: int
    outcome_statuses: tuple[str, ...]
    validation_statuses: tuple[str, ...]
    review_severities: tuple[str, ...]


@dataclass(frozen=True)
class FeedbackBundle:
    """Versioned local export of explicitly marked Outcome lessons."""

    schema_version: str
    exported_with_version: str
    records: tuple[FeedbackRecord, ...]


def build_feedback_bundle(index: OutcomeIndex, runner_version: str) -> FeedbackBundle:
    """Build a source-anonymous bundle from explicitly marked Outcome lessons."""

    aggregates: dict[tuple[str, str], dict[str, set[str]]] = {}
    for source in index.records:
        for lesson in source.lessons:
            if _FEEDBACK_TAG not in lesson.tags:
                continue
            key = (lesson.lesson_type, lesson.summary)
            aggregate = aggregates.setdefault(
                key,
                {
                    "sources": set(),
                    "outcomes": set(),
                    "validations": set(),
                    "reviews": set(),
                },
            )
            aggregate["sources"].add(source.manifest_slug)
            aggregate["outcomes"].add(source.status)
            aggregate["validations"].update(
                evidence.status for evidence in source.validation_evidence
            )
            aggregate["reviews"].update(note.severity for note in source.review_notes)

    records = tuple(
        FeedbackRecord(
            feedback_id=_feedback_id(lesson_type, summary),
            lesson_type=lesson_type,
            summary=summary,
            source_count=len(aggregate["sources"]),
            outcome_statuses=tuple(sorted(aggregate["outcomes"])),
            validation_statuses=_bounded_values(
                aggregate["validations"], _VALIDATION_STATUSES
            ),
            review_severities=_bounded_values(aggregate["reviews"], _REVIEW_SEVERITIES),
        )
        for (lesson_type, summary), aggregate in sorted(aggregates.items())
    )
    return FeedbackBundle(
        schema_version=_SCHEMA_VERSION,
        exported_with_version=runner_version,
        records=records,
    )


def write_feedback_bundle(
    bundle: FeedbackBundle,
    output_path: Union[str, Path],
    overwrite: bool = False,
) -> None:
    """Write stable bundle JSON, preserving existing output by default."""

    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    mode = "w" if overwrite else "x"
    with path.open(mode, encoding="utf-8") as output:
        json.dump(
            _bundle_to_dict(bundle),
            output,
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
        )
        output.write("\n")


_SCHEMA_VERSION = "1"
_FEEDBACK_TAG = "maid-runner-feedback"
_VALIDATION_STATUSES = frozenset(
    {
        "blocked",
        "failed",
        "failed-unrelated",
        "not-run",
        "partial",
        "passed",
        "skipped",
        "warning",
    }
)
_REVIEW_SEVERITIES = frozenset(
    {
        "P0",
        "P1",
        "P2",
        "P3",
        "advisory",
        "blocker",
        "blocking",
        "error",
        "info",
        "needs-changes",
        "needs-discussion",
        "ready",
        "warning",
    }
)


def _bounded_values(values: set[str], allowed: frozenset[str]) -> tuple[str, ...]:
    bounded = {value if value in allowed else "other" for value in values}
    return tuple(sorted(bounded))


def _feedback_id(lesson_type: str, summary: str) -> str:
    canonical = json.dumps(
        {"lesson_type": lesson_type, "summary": summary},
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")
    return hashlib.sha256(canonical).hexdigest()


def _bundle_to_dict(bundle: FeedbackBundle) -> dict:
    return {
        "exported_with_version": bundle.exported_with_version,
        "records": [
            {
                "feedback_id": record.feedback_id,
                "lesson_type": record.lesson_type,
                "outcome_statuses": list(record.outcome_statuses),
                "review_severities": list(record.review_severities),
                "source_count": record.source_count,
                "summary": record.summary,
                "validation_statuses": list(record.validation_statuses),
            }
            for record in bundle.records
        ],
        "schema_version": bundle.schema_version,
    }
