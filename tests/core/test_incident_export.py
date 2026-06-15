import json
from pathlib import Path
from typing import TYPE_CHECKING

import pytest
import yaml

if TYPE_CHECKING:
    from maid_runner.core.incidents import DpoExportReport, export_incidents_dpo


def _record(
    *,
    created: str,
    rejected_diff: str,
    chosen_diff: str | None,
    diagnostics: list[dict] | None = None,
) -> dict:
    return {
        "incident_version": 1,
        "created": created,
        "manifest": "manifests/example.manifest.yaml",
        "gates": ["E701"],
        "packet": {"diagnostics": diagnostics or [{"code": "E701"}]},
        "rejected_diff": rejected_diff,
        "chosen_diff": chosen_diff,
        "pattern_tags": ["false-done"],
        "notes": None,
    }


def _write_record(path: Path, record: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(yaml.safe_dump(record, sort_keys=False), encoding="utf-8")


def _incident_api():
    try:
        import maid_runner.core.incidents as incidents
    except ModuleNotFoundError:
        pytest.fail("maid_runner.core.incidents module is missing")
    return incidents


def test_export_incidents_dpo_writes_jsonl_context_rejected_and_chosen(tmp_path):
    if TYPE_CHECKING:
        assert DpoExportReport
        assert export_incidents_dpo
    incidents = _incident_api()
    incidents_dir = tmp_path / ".maid" / "incidents"
    _write_record(
        incidents_dir / "20260615-010203-complete.incident.yaml",
        _record(
            created="2026-06-15T01:02:03Z",
            rejected_diff="rejected diff",
            chosen_diff="chosen diff",
            diagnostics=[
                {"code": "E701", "message": "lock missing"},
                {"code": "E711", "message": "weak evidence"},
            ],
        ),
    )
    output = tmp_path / "pairs.jsonl"

    report = incidents.export_incidents_dpo(incidents_dir, output)

    assert isinstance(report, incidents.DpoExportReport)
    assert report.exported_count == 1
    assert report.skipped_count == 0
    assert report.output_path == str(output)
    lines = output.read_text(encoding="utf-8").splitlines()
    assert lines == [
        json.dumps(
            {
                "context": [
                    {"code": "E701", "message": "lock missing"},
                    {"code": "E711", "message": "weak evidence"},
                ],
                "rejected": "rejected diff",
                "chosen": "chosen diff",
            },
            sort_keys=True,
        )
    ]


def test_export_incidents_dpo_skips_valid_records_without_chosen_diff(tmp_path):
    incidents = _incident_api()
    incidents_dir = tmp_path / ".maid" / "incidents"
    _write_record(
        incidents_dir / "20260615-010203-incomplete.incident.yaml",
        _record(
            created="2026-06-15T01:02:03Z",
            rejected_diff="rejected only",
            chosen_diff=None,
        ),
    )
    _write_record(
        incidents_dir / "20260615-010204-complete.incident.yaml",
        _record(
            created="2026-06-15T01:02:04Z",
            rejected_diff="rejected complete",
            chosen_diff="chosen complete",
        ),
    )

    report = incidents.export_incidents_dpo(incidents_dir, tmp_path / "pairs.jsonl")

    assert report.exported_count == 1
    assert report.skipped_count == 1
    assert (tmp_path / "pairs.jsonl").read_text(encoding="utf-8").splitlines() == [
        json.dumps(
            {
                "context": [{"code": "E701"}],
                "rejected": "rejected complete",
                "chosen": "chosen complete",
            },
            sort_keys=True,
        )
    ]


def test_export_incidents_dpo_orders_lines_like_incident_listing(tmp_path):
    incidents = _incident_api()
    incidents_dir = tmp_path / ".maid" / "incidents"
    _write_record(
        incidents_dir / "20260615-010204-second.incident.yaml",
        _record(
            created="2026-06-15T01:02:04Z",
            rejected_diff="second rejected",
            chosen_diff="second chosen",
        ),
    )
    _write_record(
        incidents_dir / "20260615-010203-first.incident.yaml",
        _record(
            created="2026-06-15T01:02:03Z",
            rejected_diff="first rejected",
            chosen_diff="first chosen",
        ),
    )

    incidents.export_incidents_dpo(incidents_dir, tmp_path / "pairs.jsonl")

    payloads = [
        json.loads(line)
        for line in (tmp_path / "pairs.jsonl").read_text(encoding="utf-8").splitlines()
    ]
    assert [payload["rejected"] for payload in payloads] == [
        "first rejected",
        "second rejected",
    ]


def test_export_incidents_dpo_empty_or_absent_store_writes_zero_lines(tmp_path):
    incidents = _incident_api()
    output = tmp_path / "nested" / "pairs.jsonl"

    report = incidents.export_incidents_dpo(tmp_path / "absent", output)

    assert report.exported_count == 0
    assert report.skipped_count == 0
    assert output.read_text(encoding="utf-8") == ""


def test_export_incidents_dpo_names_malformed_record_path(tmp_path):
    incidents = _incident_api()
    incidents_dir = tmp_path / ".maid" / "incidents"
    bad = incidents_dir / "20260615-010203-bad.incident.yaml"
    bad.parent.mkdir(parents=True)
    bad.write_text("[unclosed", encoding="utf-8")

    with pytest.raises(ValueError) as excinfo:
        incidents.export_incidents_dpo(incidents_dir, tmp_path / "pairs.jsonl")

    assert str(bad) in str(excinfo.value)
