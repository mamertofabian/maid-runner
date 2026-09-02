"""Behavioral tests for the distributed maid-implement-draft skill."""

from __future__ import annotations

from pathlib import Path

from maid_runner.instruction_payload import INSTRUCTION_PAYLOAD_VERSION
from scripts.sync_claude_files import CODEX_DISTRIBUTABLE_SKILLS
from tests.cli.test_init_codex_distributable_scope import GENERIC_CODEX_SKILLS
from tests.test_agent_payload_distribution import (
    CODEX_DISTRIBUTABLE_SKILLS as PAYLOAD_DISTRIBUTABLE_SKILLS,
)
from tests.test_cross_tool_skill_parity import DISTRIBUTABLE_SKILLS
from tests.test_insights_skill_guidance import (
    CODEX_DISTRIBUTABLE_SKILLS as INSIGHTS_DISTRIBUTABLE_SKILLS,
)
from tests.test_learning_loop_init_payload import (
    GENERIC_CODEX_SKILLS as LEARNING_GENERIC_CODEX_SKILLS,
)

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SKILL_NAME = "maid-implement-draft"
SOURCE_SKILLS = (
    Path(".claude/skills") / SKILL_NAME / "SKILL.md",
    Path(".codex/skills") / SKILL_NAME / "SKILL.md",
)
GENERATED_SKILLS = (
    Path("maid_runner/claude/skills") / SKILL_NAME / "SKILL.md",
    Path("maid_runner/codex/skills") / SKILL_NAME / "SKILL.md",
)
CODEX_AGENT = Path(".codex/skills") / SKILL_NAME / "agents" / "openai.yaml"
GENERATED_CODEX_AGENT = (
    Path("maid_runner/codex/skills") / SKILL_NAME / "agents" / "openai.yaml"
)
BASELINE_PAYLOAD_VERSION = "2026.08.25.1"
PLANNER_SKILLS = (
    Path(".claude/skills/maid-planner/SKILL.md"),
    Path(".codex/skills/maid-planner/SKILL.md"),
)
IMPLEMENTER_SKILLS = (
    Path(".claude/skills/maid-implementer/SKILL.md"),
    Path(".codex/skills/maid-implementer/SKILL.md"),
)
ONBOARD_SKILLS = (
    Path(".claude/skills/maid-onboard/SKILL.md"),
    Path(".codex/skills/maid-onboard/SKILL.md"),
)


def _read(relative_path: Path | str) -> str:
    return (PROJECT_ROOT / relative_path).read_text()


def _skill_texts() -> list[str]:
    for path in SOURCE_SKILLS:
        assert (PROJECT_ROOT / path).exists(), f"missing source skill: {path}"
    return [_read(path) for path in SOURCE_SKILLS]


def _version_tuple(version: str) -> tuple[int, ...]:
    return tuple(int(part) for part in version.split("."))


def test_both_source_skills_exist_and_match() -> None:
    claude, codex = _skill_texts()
    assert claude == codex
    assert "name: maid-implement-draft" in claude


def test_skill_is_a_coordinator_not_an_implementer_replacement() -> None:
    for text in _skill_texts():
        assert "This skill coordinates existing phase skills" in text
        assert "it does not replace them" in text
        assert "Use `maid-plan-review`" in text
        assert "Use `maid-implementer`" in text
        assert "Use `maid-implementation-review`" in text
        assert "If the contract is already promoted" in text
        assert "use `maid-implementer` instead" in text
        assert "AUTOMATION_STATUS" not in text
        assert "maid-runner-draft-implement" not in text


def test_skill_pins_lock_then_promote_and_current_handoff_verify() -> None:
    for text in _skill_texts():
        lock_index = text.index("maid plan lock manifests/drafts/<slug>.manifest.yaml")
        promote_index = text.index(
            "maid manifest promote manifests/drafts/<slug>.manifest.yaml"
        )
        assert lock_index < promote_index
        assert "Do not create after-the-fact red evidence" in text
        assert "Never manually move or copy draft manifests" in text
        assert "maid task start manifests/<slug>.manifest.yaml" in text
        assert "maid assess --since <baseline>" in text
        assert "maid verify --profile handoff --since <baseline>" in text
        assert "maid learn" in text
        assert "maid task stop" in text


def test_planner_handoff_names_implement_draft_as_receiving_skill() -> None:
    for path in PLANNER_SKILLS:
        text = _read(path)
        handoff = text.split("## Planning Handoff Mode", 1)[1]
        assert "`maid-implement-draft`" in handoff
        assert "receiving agent" in handoff.lower()


def test_implementer_routes_unpromoted_drafts_to_implement_draft() -> None:
    for path in IMPLEMENTER_SKILLS:
        text = _read(path)
        assert "manifests/drafts/" in text
        assert "`maid-implement-draft`" in text


def test_agent_skills_and_draft_docs_list_implement_draft() -> None:
    agent_skills = _read("docs/agent-skills.md")
    draft_docs = _read("docs/draft-manifest-workflow.md")
    claude_md = _read("CLAUDE.md")
    agents_md = _read("AGENTS.md")

    assert "`maid-implement-draft`" in agent_skills
    assert "Claude" in agent_skills
    assert "Codex" in agent_skills
    assert "`maid-implement-draft`" in draft_docs
    assert "`maid-implement-draft`" in claude_md
    assert "`maid-implement-draft`" in agents_md


def test_onboard_guidance_counts_ten_generic_skills() -> None:
    expected = (
        "only the 10 generic skills, including maid-auditor, "
        "maid-outcome-enrich, maid-run-review, and maid-implement-draft"
    )
    for path in ONBOARD_SKILLS:
        assert expected in _read(path)


def test_init_guidance_names_implement_draft_for_draft_resume(
    tmp_path, monkeypatch
) -> None:
    from maid_runner.cli.commands._main import main

    monkeypatch.chdir(tmp_path)
    assert main(["init", "--tool", "codex"]) == 0
    assert main(["init", "--tool", "claude", "--force"]) == 0

    resume = (
        "When continuing from `manifests/drafts/*.manifest.yaml`, use "
        "`maid-implement-draft`"
    )
    assert resume in (tmp_path / "AGENTS.md").read_text()
    assert resume in (tmp_path / "CLAUDE.md").read_text()
    assert (tmp_path / ".codex" / "skills" / SKILL_NAME / "SKILL.md").exists()
    assert (tmp_path / ".claude" / "skills" / SKILL_NAME / "SKILL.md").exists()


def test_distributable_skill_lists_include_implement_draft() -> None:
    assert "maid-implement-draft" in CODEX_DISTRIBUTABLE_SKILLS
    assert "maid-implement-draft" in PAYLOAD_DISTRIBUTABLE_SKILLS
    assert "maid-implement-draft" in INSIGHTS_DISTRIBUTABLE_SKILLS
    assert "maid-implement-draft" in DISTRIBUTABLE_SKILLS
    assert "maid-implement-draft" in GENERIC_CODEX_SKILLS
    assert "maid-implement-draft" in LEARNING_GENERIC_CODEX_SKILLS


def test_generated_payload_copies_match_sources() -> None:
    for source, generated in zip(SOURCE_SKILLS, GENERATED_SKILLS, strict=True):
        assert _read(generated) == _read(source)
    assert _read(GENERATED_CODEX_AGENT) == _read(CODEX_AGENT)
    assert "$maid-implement-draft" in _read(CODEX_AGENT)


def test_instruction_payload_version_bumped_for_implement_draft_skill() -> None:
    assert _version_tuple(INSTRUCTION_PAYLOAD_VERSION) > _version_tuple(
        BASELINE_PAYLOAD_VERSION
    )
