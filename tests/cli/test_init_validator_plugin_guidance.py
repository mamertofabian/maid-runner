from __future__ import annotations

from pathlib import Path

from maid_runner.cli.commands._main import main
from maid_runner.instruction_payload import INSTRUCTION_PAYLOAD_VERSION


def _assert_plugin_guidance(content: str) -> None:
    assert "maid validators" in content
    assert "validator plugin" in content.lower()
    assert "skipping MAID" in content


def test_init_injects_validator_plugin_guidance_for_claude(
    tmp_path: Path, monkeypatch
) -> None:
    monkeypatch.chdir(tmp_path)

    assert main(["init", "--tool", "claude"]) == 0

    _assert_plugin_guidance((tmp_path / "CLAUDE.md").read_text(encoding="utf-8"))


def test_init_injects_validator_plugin_guidance_for_codex(
    tmp_path: Path, monkeypatch
) -> None:
    monkeypatch.chdir(tmp_path)

    assert main(["init", "--tool", "codex"]) == 0

    _assert_plugin_guidance((tmp_path / "AGENTS.md").read_text(encoding="utf-8"))


def test_validator_plugin_guidance_bumps_instruction_payload_version() -> None:
    assert INSTRUCTION_PAYLOAD_VERSION > "2026.07.18.1"
