"""Behavioral contract for verdict-neutral MAID implementation reviews."""

from __future__ import annotations

from pathlib import Path

from maid_runner.instruction_payload import INSTRUCTION_PAYLOAD_VERSION


PROJECT_ROOT = Path(__file__).resolve().parents[1]
TOOLS = ("claude", "codex")


def _read(relative_path: str) -> str:
    return (PROJECT_ROOT / relative_path).read_text()


def _version_tuple(value: str) -> tuple[int, ...]:
    return tuple(int(part) for part in value.split("."))


def _between(text: str, start: str, end: str) -> str:
    return text.split(start, 1)[1].split(end, 1)[0]


def test_reviewer_prompts_are_verdict_neutral_in_every_round() -> None:
    required = (
        "verdict-neutral in every review round",
        "complete baseline-to-current implementation delta",
        "all manifest-declared artifacts",
        "manifest-declared artifact definitions: <complete declarations and parent relationships>",
        "prior findings, fixes, verdicts, or review-round state",
        "Continue fresh review rounds",
        "current-scope actionable findings",
    )
    forbidden = (
        "After two full review rounds, issue a final verdict",
        "After two full review rounds, the reviewer issues a final verdict",
    )

    for tool in TOOLS:
        skill = _read(f".{tool}/skills/maid-implementation-review/SKILL.md")
        assert all(phrase in skill for phrase in required)
        assert all(phrase not in skill for phrase in forbidden)

        prompt = _between(skill, "Use this prompt shape:\n\n```text\n", "\n```")
        assert all(
            phrase in prompt
            for phrase in (
                "baseline: <task baseline>",
                "complete baseline-to-current diff: <diff reference>",
                "manifest-declared artifact definitions: <complete declarations and parent relationships>",
                "manifest-declared files: <complete implementation and behavioral-test file list>",
                "Report every finding you can identify in this pass.",
                "Classify every finding as blocking or advisory.",
                "Blocking findings are contract violations, behavioral bugs, scope drift, or validation failures.",
                "Advisory findings are non-actionable style preferences, optional hardening, or future-work notes.",
                "residual advisories",
            )
        )
        assert "Return only actionable review output" not in prompt
        assert all(
            phrase not in prompt.lower()
            for phrase in (
                "final",
                "approval",
                "merge-readiness",
                "blocker-closure",
                "convergence",
                "prior finding",
                "previous finding",
                "confirm the fix",
                "fixes work",
            )
        )

        convergence = _between(
            skill,
            "## Review Convergence Protocol",
            "## Phase 1 — Identify the Active Manifest",
        )
        assert "the coordinator compares" in convergence
        assert "never passes" in convergence
        assert "review lineage into a later reviewer prompt" in convergence
        assert (
            "Do not record them in the review packet for possible future draft manifests"
            in convergence
        )
        assert "coordinator-owned follow-up log" in convergence
        assert (
            "in the current session; record them in the review packet"
            not in convergence
        )


def test_workflow_docs_keep_convergence_with_the_coordinator() -> None:
    required = (
        "verdict-neutral in every review round",
        "complete baseline-to-current implementation delta",
        "prior findings, fixes, verdicts, or review-round state",
        "current-scope actionable findings",
    )

    for relative_path in (
        "docs/draft-manifest-workflow.md",
        "maid_runner/docs/draft-manifest-workflow.md",
    ):
        workflow = _read(relative_path)
        assert all(phrase in workflow for phrase in required)
        convergence = _between(
            workflow,
            "### Review-fix iteration cost",
            "## Evolution During Implementation",
        )
        assert "the coordinator compares findings" in convergence
        assert "without passing that comparison" in convergence
        assert "The coordinator decides convergence" in convergence
        assert (
            "Do not record them in the review packet for possible future draft manifests"
            in convergence
        )
        assert "coordinator-owned follow-up log" in convergence
        assert (
            "in the current session; record them in the review packet"
            not in convergence
        )


def test_packaged_reviewer_skills_match_their_sources() -> None:
    for tool in TOOLS:
        source = _read(f".{tool}/skills/maid-implementation-review/SKILL.md")
        packaged = _read(
            f"maid_runner/{tool}/skills/maid-implementation-review/SKILL.md"
        )
        assert packaged == source


def test_instruction_payload_version_advances_for_review_guidance() -> None:
    assert _version_tuple(INSTRUCTION_PAYLOAD_VERSION) > _version_tuple("2026.08.10.1")


def test_all_review_coordinators_require_neutral_complete_packets() -> None:
    coordinator_paths = (
        ".claude/skills/maid-implementer/SKILL.md",
        ".codex/skills/maid-implementer/SKILL.md",
        ".claude/skills/maid-runner-draft-implement/SKILL.md",
        ".codex/skills/maid-runner-draft-implement/SKILL.md",
        "AGENTS.md",
        ".claude/AGENTS.md",
        "tools/claude_maid_loop.py",
        "tools/codex_maid_loop.py",
    )
    required = (
        "verdict-neutral",
        "task baseline",
        "complete baseline-to-current diff",
        "complete changed-file list",
        "complete manifest-declared artifact definitions",
        "factual validation outcomes",
        "environment limits",
        "plan-revision signal",
        "prior review lineage",
        "coordinator-owned follow-up state",
    )

    for relative_path in coordinator_paths:
        coordinator = _read(relative_path)
        assert all(phrase in coordinator for phrase in required), relative_path
