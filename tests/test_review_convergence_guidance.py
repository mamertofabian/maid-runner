"""Behavioral contract for convergent MAID review and iteration guidance."""

from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path

from maid_runner.instruction_payload import INSTRUCTION_PAYLOAD_VERSION


PROJECT_ROOT = Path(__file__).resolve().parents[1]
TOOLS = ("claude", "codex")
SKILLS = (
    "maid-implementation-review",
    "maid-implementer",
    "maid-planner",
    "maid-runner-draft-implement",
)
PACKAGED_SKILLS = {
    "claude": SKILLS[:-1],
    "codex": SKILLS,
}


def _read(relative_path: str, root: Path = PROJECT_ROOT) -> str:
    return (root / relative_path).read_text()


def _source_skill(tool: str, skill: str) -> str:
    return _read(f".{tool}/skills/{skill}/SKILL.md")


def _sync_distribution(tmp_path: Path) -> Path:
    workspace = tmp_path / "workspace"
    shutil.copytree(PROJECT_ROOT / ".claude", workspace / ".claude")
    shutil.copytree(PROJECT_ROOT / ".codex", workspace / ".codex")
    shutil.copytree(PROJECT_ROOT / "docs", workspace / "docs")
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


def _version_tuple(value: str) -> tuple[int, ...]:
    return tuple(int(part) for part in value.split("."))


def test_implementation_review_skill_carries_convergence_protocol() -> None:
    required = (
        "every finding",
        "single pass",
        "blocking",
        "advisory",
        "MUST NOT trigger manifest or locked-test revision",
        "two full review rounds",
        "why it was not visible in round 1",
        "maid verify --profile handoff --since <baseline>",
        "maid verify --profile deep --since <baseline>",
    )

    for tool in TOOLS:
        text = _source_skill(tool, "maid-implementation-review")
        assert all(phrase in text for phrase in required)


def test_implementer_skills_carry_iteration_recipe() -> None:
    required = (
        "maid verify --summary --plan-lock-scope task --since <baseline>",
        "ALL blocking fixes",
        "one revise",
        "one re-validation",
        "--test-only-green",
        "--stash-implementation",
        "--allow-sibling-dirty",
        "maid verify --profile handoff --since <baseline>",
    )

    for tool in TOOLS:
        for skill in ("maid-implementer", "maid-runner-draft-implement"):
            text = _source_skill(tool, skill)
            assert all(phrase in text for phrase in required)


def test_planner_skill_carries_dedicated_test_file_rule() -> None:
    required = (
        "dedicated behavioral test file per manifest",
        "shared test files",
        "E701",
    )

    for tool in TOOLS:
        text = _source_skill(tool, "maid-planner")
        assert all(phrase in text for phrase in required)


def test_workflow_doc_and_packaged_copies_stay_in_sync(tmp_path: Path) -> None:
    workflow = _read("docs/draft-manifest-workflow.md")
    for phrase in (
        "Review-fix iteration cost",
        "single pass",
        "blocking",
        "advisory",
        "two full review rounds",
        "--plan-lock-scope task",
        "record them in the review packet for possible future draft manifests",
        "maid verify --summary --require-plan-lock --require-red-evidence --since <baseline>",
    ):
        assert phrase in workflow

    workspace = _sync_distribution(tmp_path)
    for tool in TOOLS:
        for skill in PACKAGED_SKILLS[tool]:
            source = f".{tool}/skills/{skill}/SKILL.md"
            packaged = f"maid_runner/{tool}/skills/{skill}/SKILL.md"
            assert _read(source, root=workspace) == _read(packaged, root=workspace)

    assert _read("docs/draft-manifest-workflow.md", root=workspace) == _read(
        "maid_runner/docs/draft-manifest-workflow.md", root=workspace
    )


def test_instruction_payload_version_marks_guidance_update() -> None:
    assert _version_tuple(INSTRUCTION_PAYLOAD_VERSION) > _version_tuple("2026.07.11.1")
