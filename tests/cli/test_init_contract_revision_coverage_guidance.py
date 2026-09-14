"""Behavioral checks for distributed MAID contract-lifecycle guidance."""

from pathlib import Path

from maid_runner.cli.commands._main import main
from maid_runner.instruction_payload import INSTRUCTION_PAYLOAD_VERSION


def _assert_installed_guidance(
    guidance: str, evolver: str, workflow: str, planner: str
) -> None:
    assert "unmerged" in guidance
    assert "maid plan revise" in guidance
    assert "durable" in guidance
    assert "each touched source file" in guidance
    assert "public behavior" in guidance
    assert "behavioral tests" in guidance
    assert "files.scope" in guidance
    assert "even if the file was previously listed only in `files.scope`" in guidance
    assert "previously undeclared file" not in guidance

    assert "unmerged" in evolver
    assert "maid plan revise" in evolver
    assert "durable" in evolver
    assert "supersede" in evolver
    assert "maid-implement-draft" in evolver
    assert (
        "The manifest hasn't been implemented yet (use `maid-implementer`)"
        not in evolver
    )

    assert "unmerged" in workflow
    assert "maid plan revise" in workflow
    assert "durable" in workflow
    assert "chain merging" in workflow
    assert "superseding manifest" in workflow
    assert "Use the normal MAID evolution path instead" not in workflow
    assert "legacy contracted plans" in workflow
    assert "`files.read` does not authorize production edits" in workflow
    assert "`files.scope` for narrow no-artifact wiring" in workflow

    assert "current unmerged task" in planner
    assert "maid plan revise" in planner
    assert "durable" in planner
    assert "stop and create a new manifest" not in planner


def test_codex_init_guides_pre_durable_revision_and_touched_file_coverage(
    tmp_path: Path, monkeypatch
) -> None:
    monkeypatch.chdir(tmp_path)

    assert main(["init", "--tool", "codex"]) == 0

    _assert_installed_guidance(
        (tmp_path / "AGENTS.md").read_text(encoding="utf-8"),
        (tmp_path / ".codex/skills/maid-evolver/SKILL.md").read_text(encoding="utf-8"),
        (tmp_path / "docs/draft-manifest-workflow.md").read_text(encoding="utf-8"),
        (tmp_path / ".codex/skills/maid-planner/SKILL.md").read_text(encoding="utf-8"),
    )
    agent_prompt = (
        tmp_path / ".codex/skills/maid-evolver/agents/openai.yaml"
    ).read_text(encoding="utf-8")
    assert "unmerged" in agent_prompt
    assert "maid plan revise" in agent_prompt
    assert "durable" in agent_prompt
    assert "never edit an approved manifest in place" not in agent_prompt


def test_claude_init_matches_contract_revision_and_coverage_guidance(
    tmp_path: Path, monkeypatch
) -> None:
    monkeypatch.chdir(tmp_path)

    assert main(["init", "--tool", "claude"]) == 0

    _assert_installed_guidance(
        (tmp_path / "CLAUDE.md").read_text(encoding="utf-8"),
        (tmp_path / ".claude/skills/maid-evolver/SKILL.md").read_text(encoding="utf-8"),
        (tmp_path / "docs/draft-manifest-workflow.md").read_text(encoding="utf-8"),
        (tmp_path / ".claude/skills/maid-planner/SKILL.md").read_text(encoding="utf-8"),
    )


def test_instruction_payload_version_advances_for_guidance_change() -> None:
    assert tuple(map(int, INSTRUCTION_PAYLOAD_VERSION.split("."))) > (
        2026,
        9,
        2,
        1,
    )
