import shutil
import subprocess
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]

LOCAL_ROLE_SKILLS = {
    "planner": (
        ".claude/skills/maid-planner/SKILL.md",
        ".codex/skills/maid-planner/SKILL.md",
    ),
    "implementer": (
        ".claude/skills/maid-implementer/SKILL.md",
        ".codex/skills/maid-implementer/SKILL.md",
    ),
    "implementation_review": (
        ".claude/skills/maid-implementation-review/SKILL.md",
        ".codex/skills/maid-implementation-review/SKILL.md",
    ),
}

CLAUDE_DISTRIBUTED_SKILLS = {
    "planner": "maid_runner/claude/skills/maid-planner/SKILL.md",
    "implementer": "maid_runner/claude/skills/maid-implementer/SKILL.md",
    "implementation_review": (
        "maid_runner/claude/skills/maid-implementation-review/SKILL.md"
    ),
}

ROLE_ANCHORS = {
    "planner": "Manifest-Derived Outcome Recall",
    "implementer": "Manifest-Derived Outcome Recall",
    "implementation_review": "Manifest Outcome Record Check",
}

ROLE_TERMS = {
    "planner": (
        "before drafting",
        "related completed Outcome records",
        "unimplemented draft",
    ),
    "implementer": (
        "choosing focused tests and code patterns",
        "approved manifest scope",
        "related completed Outcome records",
    ),
    "implementation_review": (
        "new or updated Outcome record",
        "after the review verdict is ready",
        "related completed Outcome records",
    ),
}

EXACT_COMMANDS = (
    "maid recall --for-manifest <path>",
    "maid recall --for-manifest <path> --plan-packet",
)

ADVISORY_TERMS = (
    "planning evidence only",
    "behavioral tests",
    "declared artifacts",
    "validation commands",
    "implementation review",
)


def _read(relative_path: str, root: Path = PROJECT_ROOT) -> str:
    return (root / relative_path).read_text()


def _normalized(text: str) -> str:
    return " ".join(text.split())


def _command_line_count(text: str, command: str) -> int:
    return sum(1 for line in text.splitlines() if line.strip() == command)


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


def test_manifest_recall_guidance_role_matrix_is_specific():
    for role, skill_paths in LOCAL_ROLE_SKILLS.items():
        for skill_path in skill_paths:
            skill_text = _read(skill_path)

            assert ROLE_ANCHORS[role] in skill_text
            normalized_text = _normalized(skill_text).lower()
            for role_term in ROLE_TERMS[role]:
                assert role_term.lower() in normalized_text

            for advisory_term in ADVISORY_TERMS:
                assert advisory_term.lower() in normalized_text


def test_manifest_recall_guidance_keeps_exact_command_surface():
    forbidden_command_forms = (
        "maid recall --manifest",
        "maid recall manifest",
        "maid recall --for-manifest <path> --json --plan-packet",
    )

    for skill_paths in LOCAL_ROLE_SKILLS.values():
        for skill_path in skill_paths:
            skill_text = _read(skill_path)

            for command in EXACT_COMMANDS:
                assert command in skill_text

            assert "maid learn" in skill_text
            assert "--allow-stale-index" in skill_text
            assert "stale index fails by default" in skill_text
            assert "run `maid learn`" in skill_text

            for forbidden_command in forbidden_command_forms:
                assert forbidden_command not in skill_text


def test_manifest_recall_guidance_is_synced_across_local_and_distributed_skills(
    tmp_path: Path,
):
    synced_workspace = _sync_distribution(tmp_path)

    for role, skill_paths in LOCAL_ROLE_SKILLS.items():
        claude_source_path, codex_path = skill_paths
        distributed_path = CLAUDE_DISTRIBUTED_SKILLS[role]
        source_text = _read(claude_source_path)
        codex_text = _read(codex_path)
        distributed_text = _read(distributed_path, root=synced_workspace)

        anchor = ROLE_ANCHORS[role]
        assert anchor in source_text
        assert anchor in codex_text
        assert anchor in distributed_text

        for command in EXACT_COMMANDS:
            assert _command_line_count(source_text, command) == 1
            assert _command_line_count(codex_text, command) == 1
            assert _command_line_count(distributed_text, command) == 1

        assert distributed_text == source_text
