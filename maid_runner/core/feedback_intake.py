"""Fail-closed validation and deterministic aggregation of feedback bundles."""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
from pathlib import Path
from typing import Sequence, Union

from maid_runner.core.feedback import FeedbackBundle, FeedbackRecord


@dataclass(frozen=True)
class FeedbackIntakeRecord:
    """One exact feedback aggregate across distinct logical bundles."""

    feedback_id: str
    lesson_type: str
    summary: str
    bundle_count: int
    reported_source_count: int
    outcome_statuses: tuple[str, ...]
    validation_statuses: tuple[str, ...]
    review_severities: tuple[str, ...]


@dataclass(frozen=True)
class FeedbackIntakeReport:
    """Versioned deterministic report over validated feedback bundles."""

    schema_version: str
    bundles_received: int
    unique_bundles: int
    records: tuple[FeedbackIntakeRecord, ...]


def read_feedback_bundle(path: Union[str, Path]) -> FeedbackBundle:
    """Read one exact version-1 bundle, rejecting ambiguous input."""

    source = Path(path)
    try:
        payload = json.loads(
            source.read_text(encoding="utf-8"),
            object_pairs_hook=_unique_object,
        )
        return _parse_bundle(payload)
    except (OSError, UnicodeError, json.JSONDecodeError, TypeError, ValueError) as exc:
        raise ValueError(f"Invalid feedback bundle {source}: {exc}") from exc


def aggregate_feedback_bundles(
    bundles: Sequence[FeedbackBundle],
) -> FeedbackIntakeReport:
    """Validate, deduplicate, and aggregate exact feedback evidence."""

    received = tuple(_parse_bundle(_bundle_to_dict(bundle)) for bundle in bundles)
    unique = {_bundle_fingerprint(bundle): bundle for bundle in received}
    aggregates: dict[str, dict[str, object]] = {}

    for fingerprint in sorted(unique):
        bundle = unique[fingerprint]
        for record in bundle.records:
            aggregate = aggregates.setdefault(
                record.feedback_id,
                {
                    "lesson_type": record.lesson_type,
                    "summary": record.summary,
                    "bundle_count": 0,
                    "reported_source_count": 0,
                    "outcome_statuses": set(),
                    "validation_statuses": set(),
                    "review_severities": set(),
                },
            )
            if (
                aggregate["lesson_type"] != record.lesson_type
                or aggregate["summary"] != record.summary
            ):
                raise ValueError(
                    f"Conflicting content for feedback_id {record.feedback_id}"
                )
            aggregate["bundle_count"] += 1
            aggregate["reported_source_count"] += record.source_count
            aggregate["outcome_statuses"].update(record.outcome_statuses)
            aggregate["validation_statuses"].update(record.validation_statuses)
            aggregate["review_severities"].update(record.review_severities)

    records = tuple(
        FeedbackIntakeRecord(
            feedback_id=feedback_id,
            lesson_type=str(aggregate["lesson_type"]),
            summary=str(aggregate["summary"]),
            bundle_count=int(aggregate["bundle_count"]),
            reported_source_count=int(aggregate["reported_source_count"]),
            outcome_statuses=tuple(sorted(aggregate["outcome_statuses"])),
            validation_statuses=tuple(sorted(aggregate["validation_statuses"])),
            review_severities=tuple(sorted(aggregate["review_severities"])),
        )
        for feedback_id, aggregate in sorted(
            aggregates.items(),
            key=lambda item: (item[1]["lesson_type"], item[1]["summary"]),
        )
    )
    return FeedbackIntakeReport(
        schema_version=_REPORT_SCHEMA_VERSION,
        bundles_received=len(received),
        unique_bundles=len(unique),
        records=records,
    )


def write_feedback_intake_report(
    report: FeedbackIntakeReport,
    output_path: Union[str, Path],
    overwrite: bool = False,
) -> None:
    """Write stable minimized JSON, preserving existing output by default."""

    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    mode = "w" if overwrite else "x"
    with path.open(mode, encoding="utf-8") as output:
        json.dump(
            _report_to_dict(report),
            output,
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
        )
        output.write("\n")


_BUNDLE_SCHEMA_VERSION = "1"
_REPORT_SCHEMA_VERSION = "1"
_BUNDLE_KEYS = {"exported_with_version", "records", "schema_version"}
_RECORD_KEYS = {
    "feedback_id",
    "lesson_type",
    "outcome_statuses",
    "review_severities",
    "source_count",
    "summary",
    "validation_statuses",
}
_OUTCOME_STATUSES = {
    "abandoned",
    "archived",
    "completed",
    "failed",
    "partial",
    "superseded",
}
_VALIDATION_STATUSES = {
    "blocked",
    "failed",
    "failed-unrelated",
    "not-run",
    "other",
    "partial",
    "passed",
    "skipped",
    "warning",
}
_REVIEW_SEVERITIES = {
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
    "other",
    "ready",
    "warning",
}


def _unique_object(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"duplicate JSON key {key!r}")
        result[key] = value
    return result


def _parse_bundle(payload: object) -> FeedbackBundle:
    root = _exact_dict(payload, _BUNDLE_KEYS, "bundle")
    if root["schema_version"] != _BUNDLE_SCHEMA_VERSION:
        raise ValueError(
            f"unsupported schema_version {root['schema_version']!r}; expected '1'"
        )
    version = _nonempty_string(root["exported_with_version"], "exported_with_version")
    raw_records = root["records"]
    if not isinstance(raw_records, list):
        raise ValueError("records must be an array")
    records = tuple(
        _parse_record(record, position) for position, record in enumerate(raw_records)
    )
    order = [(record.lesson_type, record.summary) for record in records]
    if order != sorted(order):
        raise ValueError("records must be sorted by lesson_type and summary")
    identifiers = [record.feedback_id for record in records]
    if len(identifiers) != len(set(identifiers)):
        raise ValueError("feedback_id values must be unique within a bundle")
    return FeedbackBundle(_BUNDLE_SCHEMA_VERSION, version, records)


def _parse_record(payload: object, position: int) -> FeedbackRecord:
    label = f"records[{position}]"
    record = _exact_dict(payload, _RECORD_KEYS, label)
    lesson_type = _nonempty_string(record["lesson_type"], f"{label}.lesson_type")
    summary = _nonempty_string(record["summary"], f"{label}.summary")
    feedback_id = _nonempty_string(record["feedback_id"], f"{label}.feedback_id")
    expected_id = _feedback_id(lesson_type, summary)
    if feedback_id != expected_id:
        raise ValueError(f"{label}.feedback_id does not match lesson content")
    source_count = record["source_count"]
    if isinstance(source_count, bool) or not isinstance(source_count, int):
        raise ValueError(f"{label}.source_count must be an integer")
    if source_count < 1:
        raise ValueError(f"{label}.source_count must be positive")
    return FeedbackRecord(
        feedback_id=feedback_id,
        lesson_type=lesson_type,
        summary=summary,
        source_count=source_count,
        outcome_statuses=_status_array(
            record["outcome_statuses"], _OUTCOME_STATUSES, f"{label}.outcome_statuses"
        ),
        validation_statuses=_status_array(
            record["validation_statuses"],
            _VALIDATION_STATUSES,
            f"{label}.validation_statuses",
        ),
        review_severities=_status_array(
            record["review_severities"],
            _REVIEW_SEVERITIES,
            f"{label}.review_severities",
        ),
    )


def _exact_dict(
    value: object,
    expected_keys: set[str],
    label: str,
) -> dict[str, object]:
    if not isinstance(value, dict):
        raise ValueError(f"{label} must be an object")
    keys = set(value)
    if keys != expected_keys:
        missing = sorted(expected_keys - keys)
        extra = sorted(keys - expected_keys)
        raise ValueError(f"{label} keys mismatch; missing={missing}, extra={extra}")
    return value


def _nonempty_string(value: object, label: str) -> str:
    if not isinstance(value, str) or not value:
        raise ValueError(f"{label} must be a non-empty string")
    return value


def _status_array(value: object, allowed: set[str], label: str) -> tuple[str, ...]:
    if not isinstance(value, list) or any(not isinstance(item, str) for item in value):
        raise ValueError(f"{label} must be an array of strings")
    if value != sorted(set(value)):
        raise ValueError(f"{label} must be sorted and unique")
    unknown = sorted(set(value) - allowed)
    if unknown:
        raise ValueError(f"{label} contains unsupported values: {unknown}")
    return tuple(value)


def _feedback_id(lesson_type: str, summary: str) -> str:
    canonical = json.dumps(
        {"lesson_type": lesson_type, "summary": summary},
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")
    return hashlib.sha256(canonical).hexdigest()


def _bundle_to_dict(bundle: FeedbackBundle) -> dict[str, object]:
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


def _bundle_fingerprint(bundle: FeedbackBundle) -> str:
    canonical = json.dumps(
        _bundle_to_dict(bundle),
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")
    return hashlib.sha256(canonical).hexdigest()


def _report_to_dict(report: FeedbackIntakeReport) -> dict[str, object]:
    return {
        "bundles_received": report.bundles_received,
        "records": [
            {
                "bundle_count": record.bundle_count,
                "feedback_id": record.feedback_id,
                "lesson_type": record.lesson_type,
                "outcome_statuses": list(record.outcome_statuses),
                "reported_source_count": record.reported_source_count,
                "review_severities": list(record.review_severities),
                "summary": record.summary,
                "validation_statuses": list(record.validation_statuses),
            }
            for record in report.records
        ],
        "schema_version": report.schema_version,
        "unique_bundles": report.unique_bundles,
    }
