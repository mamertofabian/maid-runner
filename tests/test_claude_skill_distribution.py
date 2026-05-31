import shutil
import subprocess
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]

SOURCE_TO_DISTRIBUTED_SKILLS = {
    ".claude/skills/maid-planner/SKILL.md": (
        "maid_runner/claude/skills/maid-planner/SKILL.md"
    ),
    ".claude/skills/maid-plan-review/SKILL.md": (
        "maid_runner/claude/skills/maid-plan-review/SKILL.md"
    ),
    ".claude/skills/maid-implementer/SKILL.md": (
        "maid_runner/claude/skills/maid-implementer/SKILL.md"
    ),
    ".claude/skills/maid-implementation-review/SKILL.md": (
        "maid_runner/claude/skills/maid-implementation-review/SKILL.md"
    ),
}

OUTCOME_GUIDANCE_ANCHORS = ("## Outcome-Aware MAID Guidance",)

ROLE_GUIDANCE = {
    ".claude/skills/maid-planner/SKILL.md": {
        "commands": ("maid learn", "maid recall"),
        "role_terms": ("draft", "planning evidence"),
    },
    ".codex/skills/maid-planner/SKILL.md": {
        "commands": ("maid learn", "maid recall"),
        "role_terms": ("draft", "planning evidence"),
    },
    ".claude/skills/maid-plan-review/SKILL.md": {
        "commands": ("maid learn", "maid recall", "maid insights"),
        "role_terms": ("review question", "scope", "tests"),
    },
    ".codex/skills/maid-plan-review/SKILL.md": {
        "commands": ("maid learn", "maid recall", "maid insights"),
        "role_terms": ("review question", "scope", "tests"),
    },
    ".claude/skills/maid-implementer/SKILL.md": {
        "commands": ("maid learn", "maid recall", "maid insights"),
        "role_terms": ("focused tests", "code patterns", "manifest scope"),
    },
    ".codex/skills/maid-implementer/SKILL.md": {
        "commands": ("maid learn", "maid recall", "maid insights"),
        "role_terms": ("focused tests", "code patterns", "manifest scope"),
    },
    ".claude/skills/maid-implementation-review/SKILL.md": {
        "commands": ("maid learn", "maid recall", "maid insights"),
        "role_terms": ("outcome:", "after implementation review", "final handoff"),
    },
    ".codex/skills/maid-implementation-review/SKILL.md": {
        "commands": ("maid learn", "maid recall", "maid insights"),
        "role_terms": ("outcome:", "after implementation review", "final handoff"),
    },
    ".codex/skills/maid-runner-draft-implement/SKILL.md": {
        "commands": ("maid learn", "maid recall", "maid insights"),
        "role_terms": ("promoting a draft", "focused tests", "implementation scope"),
    },
    ".claude/skills/maid-runner-draft-implement/SKILL.md": {
        "commands": ("maid learn", "maid recall", "maid insights"),
        "role_terms": ("promoting a draft", "focused tests", "implementation scope"),
    },
    ".codex/skills/maid-runner-self-improvement/SKILL.md": {
        "commands": ("maid learn", "maid recall", "maid insights"),
        "role_terms": ("recurring lessons", "future draft queue", "current evidence"),
    },
    ".claude/skills/maid-runner-self-improvement/SKILL.md": {
        "commands": ("maid learn", "maid recall", "maid insights"),
        "role_terms": ("recurring lessons", "future draft queue", "current evidence"),
    },
}

CODEX_AGENT_PROMPTS = {
    ".codex/skills/maid-planner/agents/openai.yaml": "$maid-planner",
    ".codex/skills/maid-plan-review/agents/openai.yaml": "$maid-plan-review",
    ".codex/skills/maid-implementer/agents/openai.yaml": "$maid-implementer",
    ".codex/skills/maid-implementation-review/agents/openai.yaml": (
        "$maid-implementation-review"
    ),
}


def _read(relative_path: str, root: Path = PROJECT_ROOT) -> str:
    return (root / relative_path).read_text()


def _lowered(relative_path: str) -> str:
    return _read(relative_path).lower()


def _assert_contract_boundary(text: str) -> None:
    lowered = text.lower()
    for term in ("behavioral tests", "declared scope", "validation", "review"):
        assert term in lowered
    assert "replace" in lowered


def _sync_distribution(tmp_path: Path) -> Path:
    workspace = tmp_path / "workspace"
    shutil.copytree(PROJECT_ROOT / ".claude", workspace / ".claude")
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


def test_outcome_guidance_is_synced_to_distributed_claude_skills(tmp_path: Path):
    synced_workspace = _sync_distribution(tmp_path)

    for source_path, distributed_path in SOURCE_TO_DISTRIBUTED_SKILLS.items():
        source_text = _read(source_path)
        distributed_text = _read(distributed_path, root=synced_workspace)

        for anchor in OUTCOME_GUIDANCE_ANCHORS:
            assert anchor in source_text
            assert anchor in distributed_text


def test_claude_skill_distribution_matches_source_after_sync(tmp_path: Path):
    synced_workspace = _sync_distribution(tmp_path)

    for source_path, distributed_path in SOURCE_TO_DISTRIBUTED_SKILLS.items():
        assert _read(distributed_path, root=synced_workspace) == _read(source_path)


def test_outcome_guidance_role_matrix_is_specific():
    for skill_path, expectations in ROLE_GUIDANCE.items():
        skill_text = _lowered(skill_path)

        for command in expectations["commands"]:
            assert command in skill_text

        for role_term in expectations["role_terms"]:
            assert role_term in skill_text

        _assert_contract_boundary(skill_text)

    for prompt_path, skill_name in CODEX_AGENT_PROMPTS.items():
        prompt_text = _read(prompt_path)
        assert skill_name in prompt_text
        assert "default_prompt" in prompt_text


def test_outcome_guidance_is_future_facing_until_commands_exist():
    command_text = _read("maid_runner/cli/commands/_main.py")
    docs_text = _read("docs/agent-skills.md")

    for command_name in ("learn", "recall", "insights"):
        assert f'"{command_name}"' in command_text
        assert f"`maid {command_name}`" in docs_text

    assert (
        "future-facing until the deterministic commands are promoted" not in docs_text
    )
