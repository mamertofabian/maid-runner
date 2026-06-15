import json
from pathlib import Path
from typing import TYPE_CHECKING

import pytest
import yaml

from maid_runner.cli.commands._main import build_parser, main

if TYPE_CHECKING:
    from maid_runner.cli.commands.incident import cmd_incident


def _write_inputs(tmp_path: Path) -> tuple[Path, Path, Path]:
    manifest = tmp_path / "manifests" / "example.manifest.yaml"
    manifest.parent.mkdir()
    manifest.write_text("schema: '2'\n", encoding="utf-8")
    packet = tmp_path / "packet.json"
    packet.write_text(
        json.dumps({"packet_version": 1, "diagnostics": [{"code": "E701"}]}),
        encoding="utf-8",
    )
    rejected = tmp_path / "rejected.diff"
    rejected.write_text("--- a/test.py\n+++ b/test.py\n", encoding="utf-8")
    return manifest, packet, rejected


def _incident_command_module():
    try:
        import maid_runner.cli.commands.incident as incident_command
    except ModuleNotFoundError:
        pytest.fail("maid_runner.cli.commands.incident module is missing")
    return incident_command


def test_build_parser_registers_incident_subcommands():
    if TYPE_CHECKING:
        assert cmd_incident
    assert callable(_incident_command_module().cmd_incident)
    parser = build_parser()

    capture = parser.parse_args(
        [
            "incident",
            "capture",
            "--manifest",
            "manifest.yaml",
            "--packet",
            "packet.json",
            "--rejected-diff",
            "rejected.diff",
            "--tags",
            "test-weakening,false-done",
            "--notes",
            "caught",
        ]
    )
    assert capture.command == "incident"
    assert capture.incident_command == "capture"
    assert capture.tags == "test-weakening,false-done"

    update = parser.parse_args(
        ["incident", "update", "record.incident.yaml", "--chosen-diff", "fix.diff"]
    )
    assert update.incident_command == "update"
    assert update.incident_path == "record.incident.yaml"

    list_args = parser.parse_args(["incident", "list", "--tag", "false-done", "--json"])
    assert list_args.incident_command == "list"
    assert list_args.json is True


def test_main_incident_capture_update_and_list_json(tmp_path, monkeypatch, capsys):
    monkeypatch.chdir(tmp_path)
    manifest, packet, rejected = _write_inputs(tmp_path)

    exit_code = main(
        [
            "incident",
            "capture",
            "--manifest",
            str(manifest),
            "--packet",
            str(packet),
            "--rejected-diff",
            str(rejected),
            "--tags",
            "test-weakening,false-done",
            "--notes",
            "caught",
        ]
    )
    assert exit_code == 0
    capture_out = capsys.readouterr().out
    incident_path = Path(capture_out.strip())
    assert incident_path.exists()

    chosen = tmp_path / "chosen.diff"
    chosen.write_text("chosen diff", encoding="utf-8")
    assert (
        main(
            [
                "incident",
                "update",
                str(incident_path),
                "--chosen-diff",
                str(chosen),
            ]
        )
        == 0
    )
    capsys.readouterr()

    assert main(["incident", "list", "--tag", "test-weakening", "--json"]) == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload == [
        {
            "path": str(incident_path),
            "incident_version": 1,
            "created": payload[0]["created"],
            "manifest": "manifests/example.manifest.yaml",
            "gates": ["E701"],
            "packet": {"packet_version": 1, "diagnostics": [{"code": "E701"}]},
            "rejected_diff": "--- a/test.py\n+++ b/test.py\n",
            "chosen_diff": "chosen diff",
            "pattern_tags": ["test-weakening", "false-done"],
            "notes": "caught",
        }
    ]


def test_incident_capture_rejects_malformed_packet(tmp_path, monkeypatch, capsys):
    monkeypatch.chdir(tmp_path)
    manifest, packet, rejected = _write_inputs(tmp_path)
    packet.write_text("{not json", encoding="utf-8")

    exit_code = main(
        [
            "incident",
            "capture",
            "--manifest",
            str(manifest),
            "--packet",
            str(packet),
            "--rejected-diff",
            str(rejected),
            "--tags",
            "false-done",
        ]
    )

    assert exit_code == 2
    assert str(packet) in capsys.readouterr().err


def test_incident_capture_rejects_unknown_tag_with_vocabulary(
    tmp_path, monkeypatch, capsys
):
    monkeypatch.chdir(tmp_path)
    manifest, packet, rejected = _write_inputs(tmp_path)

    exit_code = main(
        [
            "incident",
            "capture",
            "--manifest",
            str(manifest),
            "--packet",
            str(packet),
            "--rejected-diff",
            str(rejected),
            "--tags",
            "not-a-tag",
        ]
    )

    captured = capsys.readouterr()
    assert exit_code == 2
    assert "not-a-tag" in captured.err
    assert "test-weakening" in captured.err


def test_incident_list_text_is_ordered_by_timestamp(tmp_path, monkeypatch, capsys):
    monkeypatch.chdir(tmp_path)
    incidents_dir = tmp_path / ".maid" / "incidents"
    incidents_dir.mkdir(parents=True)
    first = incidents_dir / "20260615-010203-first.incident.yaml"
    second = incidents_dir / "20260615-010204-second.incident.yaml"
    base = {
        "incident_version": 1,
        "created": "2026-06-15T01:02:03Z",
        "manifest": "manifest.yaml",
        "gates": ["E701"],
        "packet": {"diagnostics": [{"code": "E701"}]},
        "rejected_diff": "rejected",
        "chosen_diff": None,
        "pattern_tags": ["false-done"],
        "notes": None,
    }
    second.write_text(yaml.safe_dump(base | {"created": "2026-06-15T01:02:04Z"}))
    first.write_text(yaml.safe_dump(base))

    assert main(["incident", "list"]) == 0

    lines = capsys.readouterr().out.splitlines()
    assert lines == [
        ".maid/incidents/20260615-010203-first.incident.yaml",
        ".maid/incidents/20260615-010204-second.incident.yaml",
    ]


def test_incident_update_missing_path_returns_usage_error(tmp_path, capsys):
    chosen = tmp_path / "chosen.diff"
    chosen.write_text("chosen", encoding="utf-8")
    missing = tmp_path / ".maid" / "incidents" / "missing.incident.yaml"

    assert main(["incident", "update", str(missing), "--chosen-diff", str(chosen)]) == 2
    assert str(missing) in capsys.readouterr().err
