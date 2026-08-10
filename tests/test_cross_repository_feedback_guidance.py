"""Behavioral contract for governed cross-repository feedback guidance."""

from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path

from maid_runner.instruction_payload import INSTRUCTION_PAYLOAD_VERSION


PROJECT_ROOT = Path(__file__).resolve().parents[1]
IMPLEMENTATION_REVIEW_SOURCES = (
    Path(".claude/skills/maid-implementation-review/SKILL.md"),
    Path(".codex/skills/maid-implementation-review/SKILL.md"),
)
IMPLEMENTATION_REVIEW_PACKAGES = (
    Path("maid_runner/claude/skills/maid-implementation-review/SKILL.md"),
    Path("maid_runner/codex/skills/maid-implementation-review/SKILL.md"),
)
SELF_IMPROVEMENT_SKILLS = (
    Path(".claude/skills/maid-runner-self-improvement/SKILL.md"),
    Path(".codex/skills/maid-runner-self-improvement/SKILL.md"),
    Path("maid_runner/codex/skills/maid-runner-self-improvement/SKILL.md"),
)
OUTCOME_DOCS = (
    Path("docs/manifest-outcome-records.md"),
    Path("maid_runner/docs/manifest-outcome-records.md"),
)
CAPTURE_HEADING = "### MAID Runner Feedback Candidates"
INTAKE_HEADING = "### Cross-Repository Feedback Intake"
DOC_HEADING = "### Governed Cross-Repository Feedback Workflow"


def _read(path: Path) -> str:
    return (PROJECT_ROOT / path).read_text(encoding="utf-8")


def _section(text: str, heading: str) -> str:
    assert heading in text
    start = text.index(heading)
    level = heading.split(maxsplit=1)[0]
    next_heading = text.find(f"\n{level} ", start + len(heading))
    end = next_heading if next_heading != -1 else len(text)
    return " ".join(text[start:end].split()).lower()


def _capture_sections() -> list[str]:
    paths = (*IMPLEMENTATION_REVIEW_SOURCES, *IMPLEMENTATION_REVIEW_PACKAGES)
    return [_section(_read(path), CAPTURE_HEADING) for path in paths]


def _intake_sections() -> list[str]:
    return [_section(_read(path), INTAKE_HEADING) for path in SELF_IMPROVEMENT_SKILLS]


def _sync_distribution(tmp_path: Path) -> Path:
    workspace = tmp_path / "workspace"
    shutil.copytree(PROJECT_ROOT / ".claude", workspace / ".claude")
    shutil.copytree(PROJECT_ROOT / ".codex", workspace / ".codex")
    shutil.copytree(PROJECT_ROOT / "docs", workspace / "docs")
    drafts_dir = workspace / "manifests" / "drafts"
    drafts_dir.mkdir(parents=True)
    shutil.copy2(PROJECT_ROOT / "manifests/drafts/README.md", drafts_dir)
    scripts_dir = workspace / "scripts"
    scripts_dir.mkdir()
    shutil.copy2(PROJECT_ROOT / "scripts/sync_claude_files.py", scripts_dir)

    subprocess.run(
        [sys.executable, "scripts/sync_claude_files.py"],
        cwd=workspace,
        check=True,
        capture_output=True,
        text=True,
    )
    return workspace


def _assert_payload_parity(root: Path) -> None:
    def read(path: Path) -> str:
        return (root / path).read_text(encoding="utf-8")

    for source, packaged in zip(
        IMPLEMENTATION_REVIEW_SOURCES, IMPLEMENTATION_REVIEW_PACKAGES
    ):
        assert read(packaged) == read(source)

    assert read(SELF_IMPROVEMENT_SKILLS[2]) == read(SELF_IMPROVEMENT_SKILLS[1])
    assert read(OUTCOME_DOCS[1]) == read(OUTCOME_DOCS[0])


def test_outcome_capture_marks_only_safe_generalizable_feedback_candidates() -> None:
    for guidance in _capture_sections():
        assert "exact, case-sensitive `maid-runner-feedback` tag" in guidance
        assert "explicit per-lesson decision" in guidance
        assert "must not infer" in guidance
        assert "blanket" in guidance
        assert "individual lesson" in guidance
        assert "generalizable maid runner" in guidance
        assert "application-specific" in guidance
        assert "secrets" in guidance
        assert "credentials" in guidance
        assert "personal data" in guidance
        assert "proprietary" in guidance
        assert "inspect" in guidance and "summary" in guidance
        assert "candidate" in guidance
        assert "not consent" in guidance
        assert "upload" in guidance


def test_self_improvement_treats_feedback_aggregate_as_advisory() -> None:
    for guidance in _intake_sections():
        assert "maid feedback aggregate" in guidance
        assert "local" in guidance
        assert "advisory" in guidance
        assert "untrusted data" in guidance
        assert "not instructions" in guidance
        assert "ignore directive-looking" in guidance
        assert "only the reported claim" in guidance
        assert "reported_source_count" in guidance
        assert "reported source evidence" in guidance
        assert "not verified unique repositories" in guidance


def test_self_improvement_requires_current_tree_reproduction() -> None:
    for guidance in _intake_sections():
        assert "current maid runner tree" in guidance
        assert "reproduce" in guidance
        assert "primary evidence" in guidance
        assert "unconfirmed" in guidance
        assert "confirmed finding" in guidance
        assert (
            "only after current-tree reproduction and primary evidence may a report "
            "become a confirmed finding or enter a draft queue"
        ) in guidance
        assert "until then" in guidance and "unconfirmed" in guidance


def test_confirmed_feedback_routes_through_specialist_and_maid_gates() -> None:
    for guidance in _intake_sections():
        for lane in (
            "correctness",
            "validation trust",
            "performance",
            "maintainability",
            "developer experience",
            "documentation",
            "maid workflow",
            "release/process",
        ):
            assert lane in guidance
        assert (
            "validation trust findings route to `maid-validate-hardening`" in guidance
        )
        assert (
            "performance findings route to `maid-runner-performance-optimization`"
            in guidance
        )
        assert (
            "maintainability findings route to " "`maid-runner-cleanup-and-refactor`"
        ) in guidance
        assert "existing-contract changes route through `maid-evolver`" in guidance
        assert "must not automatically" in guidance
        assert "submit data" in guidance
        assert "create issues" in guidance
        assert "create or promote manifests" in guidance
        assert "change validation policy" in guidance
        assert "modify code" in guidance
        assert "bypass" in guidance
        assert "behavioral tests" in guidance
        assert "approval" in guidance
        assert "plan lock" in guidance
        assert "validation" in guidance
        assert "outcome capture" in guidance
        assert "implementation review" in guidance


def test_feedback_workflow_guidance_is_synced_to_payloads_and_docs(
    tmp_path: Path,
) -> None:
    _assert_payload_parity(PROJECT_ROOT)

    for path in OUTCOME_DOCS:
        guidance = _section(_read(path), DOC_HEADING)
        assert "exact, case-sensitive `maid-runner-feedback` tag" in guidance
        assert "explicit per-lesson decision" in guidance
        assert "must not infer" in guidance
        assert "generalizable maid runner" in guidance
        assert "application-specific" in guidance
        assert "secrets" in guidance and "credentials" in guidance
        assert "personal data" in guidance and "proprietary" in guidance
        assert "inspect" in guidance and "summary" in guidance
        assert "candidate" in guidance and "not consent" in guidance
        assert "upload" in guidance
        assert "untrusted data" in guidance and "not instructions" in guidance
        assert "ignore directive-looking" in guidance
        assert "only the reported claim" in guidance
        assert "reported_source_count" in guidance
        assert "not verified unique repositories" in guidance
        assert "current maid runner tree" in guidance
        assert "primary evidence" in guidance and "unconfirmed" in guidance
        assert (
            "only after current-tree reproduction and primary evidence may a report "
            "become a confirmed finding or enter a draft queue"
        ) in guidance
        assert "until then" in guidance and "unconfirmed" in guidance
        assert "specialist" in guidance
        for lane in (
            "correctness",
            "validation trust",
            "performance",
            "maintainability",
            "developer experience",
            "documentation",
            "maid workflow",
            "release/process",
        ):
            assert lane in guidance
        assert (
            "validation trust findings route to `maid-validate-hardening`" in guidance
        )
        assert (
            "performance findings route to `maid-runner-performance-optimization`"
            in guidance
        )
        assert (
            "maintainability findings route to " "`maid-runner-cleanup-and-refactor`"
        ) in guidance
        assert "existing-contract changes route through `maid-evolver`" in guidance
        assert "must not automatically" in guidance
        assert "submit data" in guidance and "create issues" in guidance
        assert "create or promote manifests" in guidance
        assert "change validation policy" in guidance and "modify code" in guidance
        assert "bypass" in guidance
        assert "behavioral tests" in guidance and "approval" in guidance
        assert "plan lock" in guidance and "validation" in guidance
        assert "outcome capture" in guidance and "implementation review" in guidance

    _assert_payload_parity(_sync_distribution(tmp_path))


def test_instruction_payload_version_bumped_for_feedback_capture_guidance() -> None:
    assert tuple(map(int, INSTRUCTION_PAYLOAD_VERSION.split("."))) > (
        2026,
        8,
        7,
        2,
    )
