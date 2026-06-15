import json
from pathlib import Path

import pytest
import yaml

from maid_runner.cli.commands._main import build_parser, main
from maid_runner.cli.commands.incident import cmd_incident


def _record(*, created: str, rejected_diff: str, chosen_diff: str | None) -> dict:
    return {
        "incident_version": 1,
        "created": created,
        "manifest": "manifests/example.manifest.yaml",
        "gates": ["E701"],
        "packet": {"diagnostics": [{"code": "E701", "message": "lock missing"}]},
        "rejected_diff": rejected_diff,
        "chosen_diff": chosen_diff,
        "pattern_tags": ["false-done"],
        "notes": None,
    }


def _write_record(path: Path, record: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(yaml.safe_dump(record, sort_keys=False), encoding="utf-8")


def test_build_parser_registers_incident_export_options():
    parser = build_parser()

    args = parser.parse_args(
        ["incident", "export", "--format", "dpo", "--output", "pairs.jsonl"]
    )

    assert callable(cmd_incident)
    assert args.command == "incident"
    assert args.incident_command == "export"
    assert args.format == "dpo"
    assert args.output == "pairs.jsonl"


def test_incident_export_writes_dpo_jsonl_and_reports_counts(
    tmp_path, monkeypatch, capsys
):
    monkeypatch.chdir(tmp_path)
    incidents_dir = tmp_path / ".maid" / "incidents"
    _write_record(
        incidents_dir / "20260615-010203-complete.incident.yaml",
        _record(
            created="2026-06-15T01:02:03Z",
            rejected_diff="rejected",
            chosen_diff="chosen",
        ),
    )
    _write_record(
        incidents_dir / "20260615-010204-incomplete.incident.yaml",
        _record(
            created="2026-06-15T01:02:04Z",
            rejected_diff="missing chosen",
            chosen_diff=None,
        ),
    )

    exit_code = main(
        ["incident", "export", "--format", "dpo", "--output", "pairs.jsonl"]
    )

    assert exit_code == 0
    assert capsys.readouterr().out == "Exported 1 DPO pair(s), skipped 1\n"
    assert [
        json.loads(line)
        for line in (tmp_path / "pairs.jsonl").read_text(encoding="utf-8").splitlines()
    ] == [
        {
            "chosen": "chosen",
            "context": [{"code": "E701", "message": "lock missing"}],
            "rejected": "rejected",
        }
    ]


def test_incident_export_empty_store_reports_zero_counts(tmp_path, monkeypatch, capsys):
    monkeypatch.chdir(tmp_path)

    assert (
        main(["incident", "export", "--format", "dpo", "--output", "pairs.jsonl"]) == 0
    )

    assert capsys.readouterr().out == "Exported 0 DPO pair(s), skipped 0\n"
    assert (tmp_path / "pairs.jsonl").read_text(encoding="utf-8") == ""


def test_incident_export_malformed_record_returns_error_with_path(
    tmp_path, monkeypatch, capsys
):
    monkeypatch.chdir(tmp_path)
    bad = tmp_path / ".maid" / "incidents" / "20260615-010203-bad.incident.yaml"
    bad.parent.mkdir(parents=True)
    bad.write_text("[unclosed", encoding="utf-8")

    assert (
        main(["incident", "export", "--format", "dpo", "--output", "pairs.jsonl"]) == 2
    )

    assert str(bad) in capsys.readouterr().err


def test_incident_export_rejects_unknown_format_and_missing_output(capsys):
    parser = build_parser()

    with pytest.raises(SystemExit):
        parser.parse_args(
            ["incident", "export", "--format", "sft", "--output", "pairs.jsonl"]
        )
    assert "dpo" in capsys.readouterr().err

    with pytest.raises(SystemExit):
        parser.parse_args(["incident", "export", "--format", "dpo"])
    assert "--output" in capsys.readouterr().err
