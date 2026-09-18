"""Installed lifecycle policy for shared branches and committed task code."""

from pathlib import Path

import pytest

from maid_runner.cli.commands._main import main
from maid_runner.instruction_payload import INSTRUCTION_PAYLOAD_VERSION


@pytest.mark.parametrize(
    "tool,instructions", [("codex", "AGENTS.md"), ("claude", "CLAUDE.md")]
)
def test_installed_policy_uses_shared_acceptance_instead_of_branch_name(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, tool: str, instructions: str
) -> None:
    monkeypatch.chdir(tmp_path)

    assert main(["init", "--tool", tool]) == 0

    guidance = (tmp_path / instructions).read_text()
    assert "accepted into shared project history" in guidance
    assert "integration or release branches regardless of name" in guidance
    assert "a local task commit alone is not acceptance" in guidance
    assert "clarify uncertain acceptance before rewriting" in guidance
    for skill in ("maid-planner", "maid-evolver"):
        installed = " ".join(
            (tmp_path / f".{tool}/skills/{skill}/SKILL.md").read_text().split()
        )
        assert "main/master" not in installed
        assert "shared project history" in installed
        assert "local task commit alone" in installed


@pytest.mark.parametrize(
    "tool,instructions", [("codex", "AGENTS.md"), ("claude", "CLAUDE.md")]
)
def test_installed_policy_routes_committed_implementation_evidence(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, tool: str, instructions: str
) -> None:
    monkeypatch.chdir(tmp_path)

    assert main(["init", "--tool", tool]) == 0

    guidance = (tmp_path / instructions).read_text()
    assert "cannot hide committed implementation" in guidance
    assert (
        "plain `maid plan revise` can capture fresh red evidence before the fix"
        in guidance
    )
    assert "already pass and valid evidence cannot be preserved" in guidance
    assert "report the evidence blocker" in guidance
    workflow = " ".join(
        (tmp_path / "docs/draft-manifest-workflow.md").read_text().split()
    )
    assert "Revision Evidence After Implementation" in workflow
    assert "only hides dirty implementation paths, not commits" in workflow
    assert "pre-implementation commit needed for recovery" in workflow
    assert (
        "A diagnostic baseline test run alone is not a valid replacement plan lock"
        in workflow
    )
    for skill in ("maid-planner", "maid-evolver"):
        installed = (tmp_path / f".{tool}/skills/{skill}/SKILL.md").read_text()
        assert "Revision Evidence After Implementation" in installed


def test_codex_evolver_prompt_retains_portable_lifecycle_decisions(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(tmp_path)

    assert main(["init", "--tool", "codex"]) == 0

    prompt = (tmp_path / ".codex/skills/maid-evolver/agents/openai.yaml").read_text()
    assert "shared project history on any branch" in prompt
    assert "committed implementation when choosing revision evidence" in prompt
    assert "main/master" not in prompt


def test_portable_lifecycle_payload_advances_the_prior_instruction_version() -> None:
    assert tuple(map(int, INSTRUCTION_PAYLOAD_VERSION.split("."))) > (2026, 9, 14, 1)
