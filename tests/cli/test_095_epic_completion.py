"""Behavioral contract for closing the 095 onboarding epic."""

from __future__ import annotations

from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[2]
AGENT_RETRY_COMMAND = "maid verify --profile agent-retry --since <baseline>"
HANDOFF_COMMAND = "maid verify --profile handoff --since <baseline>"
OBSOLETE_HANDOFF_COMMAND = (
    "maid verify --summary --require-plan-lock --require-red-evidence "
    "--since <baseline>"
)
PRE_COMPLETION_PAYLOAD_VERSION = "2026.08.07.1"


def _read(relative: str, *, root: Path = ROOT) -> str:
    return (root / relative).read_text(encoding="utf-8")


def _version_tuple(value: str) -> tuple[int, ...]:
    return tuple(int(part) for part in value.split("."))


def test_howto_actionable_verify_commands_use_named_profiles(capsys) -> None:
    from maid_runner.cli.commands._main import main

    for topic in ("validate", "commands"):
        assert main(["howto", topic]) == 0
        output = capsys.readouterr().out
        assert AGENT_RETRY_COMMAND in output
        assert "\n  maid verify --packet\n" not in output

    for topic in ("workflow", "commands"):
        assert main(["howto", topic]) == 0
        output = capsys.readouterr().out
        assert "maid verify --profile handoff" in output
        assert "expands to" in output.lower()
        assert (
            "\n  maid verify --require-plan-lock --require-red-evidence\n" not in output
        )


def test_init_distributed_workflow_uses_handoff_profile(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from maid_runner.cli.commands._main import main

    source = _read("docs/draft-manifest-workflow.md")
    packaged = _read("maid_runner/docs/draft-manifest-workflow.md")

    assert packaged == source
    assert HANDOFF_COMMAND in source
    assert OBSOLETE_HANDOFF_COMMAND not in source

    monkeypatch.chdir(tmp_path)
    assert main(["init", "--tool", "generic"]) == 0
    assert _read("docs/draft-manifest-workflow.md", root=tmp_path) == source


def test_instruction_payload_version_advances_for_completed_guidance() -> None:
    from maid_runner.instruction_payload import INSTRUCTION_PAYLOAD_VERSION

    assert _version_tuple(INSTRUCTION_PAYLOAD_VERSION) > _version_tuple(
        PRE_COMPLETION_PAYLOAD_VERSION
    )
