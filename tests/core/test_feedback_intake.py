"""Behavioral contract for validated local feedback intake reports."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from maid_runner.core.feedback import FeedbackBundle, FeedbackRecord


def test_read_feedback_bundle_accepts_exact_version_one_shape(tmp_path: Path) -> None:
    intake = _intake_api()
    path = tmp_path / "bundle.json"
    path.write_text(json.dumps(_bundle_payload(_record_payload("runner-gap", "Gap."))))

    bundle = intake.read_feedback_bundle(path)

    assert isinstance(bundle, FeedbackBundle)
    assert bundle.schema_version == "1"
    assert bundle.exported_with_version == "2.25.0"
    assert bundle.records == (
        FeedbackRecord(
            feedback_id=_feedback_id("runner-gap", "Gap."),
            lesson_type="runner-gap",
            summary="Gap.",
            source_count=1,
            outcome_statuses=("completed",),
            validation_statuses=("passed",),
            review_severities=("ready",),
        ),
    )


def test_read_feedback_bundle_rejects_unsupported_ambiguous_or_unbounded_content(
    tmp_path: Path,
) -> None:
    intake = _intake_api()
    valid = _bundle_payload(_record_payload("runner-gap", "Gap."))
    cases = []

    unsupported = _copy(valid)
    unsupported["schema_version"] = "2"
    cases.append(unsupported)

    extra_top_level = _copy(valid)
    extra_top_level["project_root"] = "/private/customer"
    cases.append(extra_top_level)

    wrong_id = _copy(valid)
    wrong_id["records"][0]["feedback_id"] = "0" * 64
    cases.append(wrong_id)

    extra_record_field = _copy(valid)
    extra_record_field["records"][0]["manifest_slug"] = "private-customer"
    cases.append(extra_record_field)

    unknown_status = _copy(valid)
    unknown_status["records"][0]["validation_statuses"] = ["customer-secret"]
    cases.append(unknown_status)

    unsorted_statuses = _copy(valid)
    unsorted_statuses["records"][0]["outcome_statuses"] = ["partial", "completed"]
    cases.append(unsorted_statuses)

    boolean_count = _copy(valid)
    boolean_count["records"][0]["source_count"] = True
    cases.append(boolean_count)

    unsorted_records = _bundle_payload(
        _record_payload("zeta", "Last."),
        _record_payload("alpha", "First."),
    )
    cases.append(unsorted_records)

    for position, payload in enumerate(cases):
        path = tmp_path / f"invalid-{position}.json"
        path.write_text(json.dumps(payload), encoding="utf-8")
        with pytest.raises(ValueError):
            intake.read_feedback_bundle(path)

    duplicate_key = tmp_path / "duplicate-key.json"
    duplicate_key.write_text(
        '{"schema_version":"1","schema_version":"1",'
        '"exported_with_version":"2.25.0","records":[]}',
        encoding="utf-8",
    )
    with pytest.raises(ValueError):
        intake.read_feedback_bundle(duplicate_key)


def test_aggregate_feedback_bundles_deduplicates_bundles_and_unions_exact_evidence() -> (
    None
):
    intake = _intake_api()
    shared_id = _feedback_id("runner-gap", "Gap.")
    first = FeedbackBundle(
        "1",
        "2.25.0",
        (
            FeedbackRecord(
                shared_id,
                "runner-gap",
                "Gap.",
                2,
                ("completed",),
                ("passed",),
                ("P1",),
            ),
        ),
    )
    second = FeedbackBundle(
        "1",
        "2.26.0",
        (
            FeedbackRecord(
                shared_id,
                "runner-gap",
                "Gap.",
                3,
                ("partial",),
                ("failed",),
                ("ready",),
            ),
        ),
    )

    report = intake.aggregate_feedback_bundles((first, first, second))

    assert isinstance(report, intake.FeedbackIntakeReport)
    assert report.schema_version == "1"
    assert report.bundles_received == 3
    assert report.unique_bundles == 2
    assert len(report.records) == 1
    record = report.records[0]
    assert isinstance(record, intake.FeedbackIntakeRecord)
    assert record.feedback_id == shared_id
    assert record.lesson_type == "runner-gap"
    assert record.summary == "Gap."
    assert record.bundle_count == 2
    assert record.reported_source_count == 5
    assert record.outcome_statuses == ("completed", "partial")
    assert record.validation_statuses == ("failed", "passed")
    assert record.review_severities == ("P1", "ready")
    assert intake.aggregate_feedback_bundles((second, first, first)) == report

    unvalidated = FeedbackBundle(
        "1",
        "private-version-value",
        (
            FeedbackRecord(
                "0" * 64,
                "runner-gap",
                "Gap.",
                1,
                ("completed",),
                ("private-validation-status",),
                ("ready",),
            ),
        ),
    )
    with pytest.raises(ValueError):
        intake.aggregate_feedback_bundles((unvalidated,))


def test_write_feedback_intake_report_is_stable_minimized_and_overwrite_safe(
    tmp_path: Path,
) -> None:
    intake = _intake_api()
    report = intake.FeedbackIntakeReport(
        schema_version="1",
        bundles_received=1,
        unique_bundles=1,
        records=(
            intake.FeedbackIntakeRecord(
                feedback_id=_feedback_id("runner-gap", "Reviewed summary."),
                lesson_type="runner-gap",
                summary="Reviewed summary.",
                bundle_count=1,
                reported_source_count=2,
                outcome_statuses=("completed",),
                validation_statuses=("passed",),
                review_severities=("ready",),
            ),
        ),
    )
    first = tmp_path / "nested" / "first.json"
    second = tmp_path / "second.json"

    intake.write_feedback_intake_report(report, first)
    intake.write_feedback_intake_report(report, second)

    assert first.read_bytes() == second.read_bytes()
    rendered = first.read_text(encoding="utf-8")
    payload = json.loads(rendered)
    assert set(payload) == {
        "bundles_received",
        "records",
        "schema_version",
        "unique_bundles",
    }
    assert set(payload["records"][0]) == {
        "bundle_count",
        "feedback_id",
        "lesson_type",
        "outcome_statuses",
        "reported_source_count",
        "review_severities",
        "summary",
        "validation_statuses",
    }
    assert "/private/input.json" not in rendered
    with pytest.raises(FileExistsError):
        intake.write_feedback_intake_report(report, first)
    intake.write_feedback_intake_report(report, first, overwrite=True)


def _intake_api():
    try:
        from maid_runner.core.feedback_intake import (
            FeedbackIntakeRecord,
            FeedbackIntakeReport,
            aggregate_feedback_bundles,
            read_feedback_bundle,
            write_feedback_intake_report,
        )
        import maid_runner.core.feedback_intake as intake
    except ModuleNotFoundError:
        pytest.fail("maid_runner.core.feedback_intake is not implemented")
    assert FeedbackIntakeRecord is intake.FeedbackIntakeRecord
    assert FeedbackIntakeReport is intake.FeedbackIntakeReport
    assert aggregate_feedback_bundles is intake.aggregate_feedback_bundles
    assert read_feedback_bundle is intake.read_feedback_bundle
    assert write_feedback_intake_report is intake.write_feedback_intake_report
    return intake


def _feedback_id(lesson_type: str, summary: str) -> str:
    canonical = json.dumps(
        {"lesson_type": lesson_type, "summary": summary},
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")
    return hashlib.sha256(canonical).hexdigest()


def _record_payload(lesson_type: str, summary: str) -> dict:
    return {
        "feedback_id": _feedback_id(lesson_type, summary),
        "lesson_type": lesson_type,
        "summary": summary,
        "source_count": 1,
        "outcome_statuses": ["completed"],
        "validation_statuses": ["passed"],
        "review_severities": ["ready"],
    }


def _bundle_payload(*records: dict) -> dict:
    return {
        "schema_version": "1",
        "exported_with_version": "2.25.0",
        "records": list(records),
    }


def _copy(payload: dict) -> dict:
    return json.loads(json.dumps(payload))
