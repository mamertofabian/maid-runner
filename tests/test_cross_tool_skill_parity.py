"""Behavioral contract for Claude/Codex MAID skill body parity."""

from __future__ import annotations

import re
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]

DISTRIBUTABLE_SKILLS = (
    "maid-planner",
    "maid-plan-review",
    "maid-implement-draft",
    "maid-implementer",
    "maid-evolver",
    "maid-auditor",
    "maid-incident-logger",
    "maid-outcome-enrich",
    "maid-run-review",
)

REPO_INTERNAL_SKILLS = (
    "maid-runner-cleanup-and-refactor",
    "maid-runner-draft-implement",
    "maid-runner-performance-optimization",
    "maid-runner-self-improvement",
    "maid-validate-hardening",
)

PACKET_RETRY_ANCHORS = (
    "## Packet-Driven Retry Gates",
    "maid validate --packet",
    "maid verify --profile agent-retry --since <baseline>",
    ".maid/last-failure-packet.json",
    "escalate-human",
)

IMPLEMENTATION_REVIEW_PHASE_3 = "## Phase 3 — Run the Reviewer Subagent"


def _read(tool: str, skill: str) -> str:
    return (PROJECT_ROOT / f".{tool}/skills/{skill}/SKILL.md").read_text()


def _normalize_user_guidance_paths(text: str) -> str:
    return text.replace("~/.claude/CLAUDE.md", "<USER_GUIDANCE>").replace(
        "~/.codex/AGENTS.md", "<USER_GUIDANCE>"
    )


def _normalize_maid_loop_reference(text: str) -> str:
    return text.replace("tools/claude_maid_loop.py", "tools/<maid_loop>.py").replace(
        "tools/codex_maid_loop.py", "tools/<maid_loop>.py"
    )


def _normalize_front_matter_description(text: str) -> str:
    return re.sub(
        r"(?m)^description:.*$",
        "description: <normalized>",
        text,
        count=1,
    )


def _normalize_skill_coordination_block(text: str) -> str:
    pattern = (
        r"(?ms)^- This skill has standing explicit user authorization.*?"
        r"(?=\n## Start\n)"
    )
    return re.sub(
        pattern,
        "- <normalized reviewer-subagent coordination>\n",
        text,
        count=1,
    )


def _normalize_review_loop_block(text: str) -> str:
    pattern = r"(?ms)^## Review Loop\n.*?" r"(?=\n## Outcome Capture\n)"
    return re.sub(
        pattern,
        "## Review Loop\n<normalized reviewer-subagent loop>\n\n",
        text,
        count=1,
    )


def _normalize_repo_internal_skill(text: str) -> str:
    normalized = _normalize_front_matter_description(text)
    normalized = _normalize_user_guidance_paths(normalized)
    normalized = _normalize_maid_loop_reference(normalized)
    normalized = _normalize_skill_coordination_block(normalized)
    normalized = _normalize_review_loop_block(normalized)
    return normalized


def _normalize_implementation_review_phase_3(text: str) -> str:
    if IMPLEMENTATION_REVIEW_PHASE_3 not in text:
        return text
    before, rest = text.split(IMPLEMENTATION_REVIEW_PHASE_3, 1)
    _, after = rest.split("## Phase 4", 1)
    return (
        f"{before}{IMPLEMENTATION_REVIEW_PHASE_3}\n"
        "<normalized reviewer-subagent mechanics>\n\n"
        f"## Phase 4{after}"
    )


def test_distributable_skill_bodies_match_across_tools() -> None:
    for skill in DISTRIBUTABLE_SKILLS:
        claude = _read("claude", skill)
        codex = _read("codex", skill)
        assert claude == codex, skill


def test_implementation_review_matches_after_phase_3_normalization() -> None:
    claude = _normalize_implementation_review_phase_3(
        _read("claude", "maid-implementation-review")
    )
    codex = _normalize_implementation_review_phase_3(
        _read("codex", "maid-implementation-review")
    )
    assert claude == codex


def test_repo_internal_skills_match_after_tool_specific_normalization() -> None:
    for skill in REPO_INTERNAL_SKILLS:
        claude = _normalize_repo_internal_skill(_read("claude", skill))
        codex = _normalize_repo_internal_skill(_read("codex", skill))
        assert claude == codex, skill


def test_packet_driven_retry_gates_present_in_draft_implement_both_tools() -> None:
    for tool in ("claude", "codex"):
        text = _read(tool, "maid-runner-draft-implement")
        for anchor in PACKET_RETRY_ANCHORS:
            assert anchor in text


def test_packet_driven_retry_gates_present_in_implementer_both_tools() -> None:
    for tool in ("claude", "codex"):
        text = _read(tool, "maid-implementer")
        for anchor in PACKET_RETRY_ANCHORS:
            assert anchor in text


def test_performance_and_self_improvement_profiling_commands_aligned() -> None:
    performance = _read("claude", "maid-runner-performance-optimization")
    assert "time uv run maid verify --keep-going --json" in performance
    assert "time uv run maid test --json" in performance
    assert performance == _read("codex", "maid-runner-performance-optimization")

    self_improvement = _read("claude", "maid-runner-self-improvement")
    assert "uv run maid test --json" in self_improvement
    assert self_improvement == _read("codex", "maid-runner-self-improvement")
