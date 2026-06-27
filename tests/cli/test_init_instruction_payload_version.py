from __future__ import annotations

import json
from pathlib import Path

import pytest

from maid_runner.__version__ import __version__
from maid_runner.cli.commands._main import main


def _manifest(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _json_output(capsys: pytest.CaptureFixture[str]) -> dict:
    return json.loads(capsys.readouterr().out)


def _write_agent_manifest(root: Path, tool: str, payload_version: str) -> Path:
    manifest_path = root / f".{tool}" / "manifest.json"
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    manifest_path.write_text(
        json.dumps(
            {
                "metadata": {
                    "maid_runner_version": __version__,
                    "instruction_payload_version": payload_version,
                },
                "skills": {"distributable": []},
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    return manifest_path


def _instruction_payload_contract() -> tuple[str, dict[str, str]]:
    try:
        from maid_runner.instruction_payload import (
            INSTRUCTION_PAYLOAD_VERSION,
            instruction_payload_metadata,
        )
    except ModuleNotFoundError as exc:
        pytest.fail(f"missing instruction payload module: {exc}")

    return INSTRUCTION_PAYLOAD_VERSION, instruction_payload_metadata()


def test_init_stamps_instruction_payload_version_into_codex_payload(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(tmp_path)

    assert main(["init", "--tool", "codex"]) == 0

    manifest = _manifest(tmp_path / ".codex" / "manifest.json")
    guidance = (tmp_path / "AGENTS.md").read_text(encoding="utf-8")
    payload_version, metadata = _instruction_payload_contract()

    assert manifest["metadata"] == metadata
    assert manifest["metadata"]["instruction_payload_version"] == payload_version
    assert f"Instruction payload version: {payload_version}" in guidance


def test_init_stamps_instruction_payload_version_into_claude_payload(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(tmp_path)

    assert main(["init", "--tool", "claude"]) == 0

    manifest = _manifest(tmp_path / ".claude" / "manifest.json")
    guidance = (tmp_path / "CLAUDE.md").read_text(encoding="utf-8")
    payload_version, metadata = _instruction_payload_contract()

    assert manifest["metadata"] == metadata
    assert manifest["metadata"]["instruction_payload_version"] == payload_version
    assert f"Instruction payload version: {payload_version}" in guidance


def test_init_check_reports_current_installed_payload(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.chdir(tmp_path)
    payload_version, _ = _instruction_payload_contract()
    assert main(["init", "--tool", "codex"]) == 0
    capsys.readouterr()

    assert main(["init", "--check", "--json"]) == 0

    payload = _json_output(capsys)
    assert payload == {
        "status": "current",
        "maid_runner_version": __version__,
        "instruction_payload_version": payload_version,
        "installed": {
            "claude": {
                "manifest_path": ".claude/manifest.json",
                "present": False,
                "instruction_payload_version": None,
                "status": "absent",
            },
            "codex": {
                "manifest_path": ".codex/manifest.json",
                "present": True,
                "instruction_payload_version": payload_version,
                "status": "current",
            },
        },
    }


def test_init_check_reports_missing_payload(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.chdir(tmp_path)
    before = sorted(tmp_path.rglob("*"))

    assert main(["init", "--check", "--json"]) == 1

    payload = _json_output(capsys)
    assert payload["status"] == "missing"
    assert payload["installed"]["claude"]["status"] == "absent"
    assert payload["installed"]["codex"]["status"] == "absent"
    assert sorted(tmp_path.rglob("*")) == before


def test_init_check_reports_stale_payload(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.chdir(tmp_path)
    manifest_path = _write_agent_manifest(tmp_path, "codex", "1900.01.01")
    before = manifest_path.read_text(encoding="utf-8")

    assert main(["init", "--check", "--json"]) == 1

    payload = _json_output(capsys)
    assert payload["status"] == "stale"
    assert payload["installed"]["codex"]["present"] is True
    assert payload["installed"]["codex"]["instruction_payload_version"] == (
        "1900.01.01"
    )
    assert payload["installed"]["codex"]["status"] == "stale"
    assert manifest_path.read_text(encoding="utf-8") == before


def test_init_check_reports_stale_when_any_installed_payload_is_stale(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.chdir(tmp_path)
    payload_version, _ = _instruction_payload_contract()
    _write_agent_manifest(tmp_path, "claude", payload_version)
    _write_agent_manifest(tmp_path, "codex", "1900.01.01")

    assert main(["init", "--check", "--json"]) == 1

    payload = _json_output(capsys)
    assert payload["status"] == "stale"
    assert payload["installed"]["claude"]["status"] == "current"
    assert payload["installed"]["codex"]["status"] == "stale"


def test_init_check_prints_human_readable_status(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.chdir(tmp_path)
    payload_version, _ = _instruction_payload_contract()
    assert main(["init", "--tool", "claude"]) == 0
    capsys.readouterr()

    assert main(["init", "--check"]) == 0

    output = capsys.readouterr().out
    assert "MAID instruction payload status: current" in output
    assert f"Current instruction payload version: {payload_version}" in output
    assert "claude: current" in output
    assert "codex: absent" in output
