"""Documentation contract for exact client-grounded agent provenance."""

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_outcome_docs_document_reasoning_effort_and_exact_model_rule() -> None:
    source = (ROOT / "docs/manifest-outcome-records.md").read_text()
    packaged = (ROOT / "maid_runner/docs/manifest-outcome-records.md").read_text()
    assert source == packaged
    for phrase in (
        "reasoning_effort",
        "MAID_AGENT_REASONING_EFFORT",
        "client-provided",
        "ground truth",
        "gpt-5.6-luna",
    ):
        assert phrase in source


def test_review_skill_instructs_env_sourced_outcome_agent() -> None:
    source = (ROOT / ".claude/skills/maid-implementation-review/SKILL.md").read_text()
    claude = (
        ROOT / "maid_runner/claude/skills/maid-implementation-review/SKILL.md"
    ).read_text()
    codex = (
        ROOT / "maid_runner/codex/skills/maid-implementation-review/SKILL.md"
    ).read_text()
    for content in (source, claude, codex):
        assert "MAID_AGENT_MODEL" in content
        assert "MAID_AGENT_REASONING_EFFORT" in content
        assert "client-invoked model slug" in content
