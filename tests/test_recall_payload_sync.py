import fnmatch
import json
import shutil
import subprocess
import sys
from pathlib import Path

try:
    import tomllib
except ModuleNotFoundError:  # pragma: no cover - Python 3.10 fallback
    import tomli as tomllib


PROJECT_ROOT = Path(__file__).resolve().parents[1]

WORKFLOW_SKILLS = (
    "maid-planner",
    "maid-implementer",
    "maid-implementation-review",
)

EXACT_RECALL_COMMANDS = (
    "maid recall --for-manifest <path>",
    "maid recall --for-manifest <path> --plan-packet",
)

RECALL_GUIDANCE_ANCHORS = (
    "Manifest-Derived Outcome Recall",
    "Manifest Outcome Record Check",
)


def _read(relative_path: str, root: Path = PROJECT_ROOT) -> str:
    return (root / relative_path).read_text()


def _sync_distribution(tmp_path: Path) -> Path:
    workspace = tmp_path / "workspace"
    shutil.copytree(PROJECT_ROOT / ".claude", workspace / ".claude")
    shutil.copytree(PROJECT_ROOT / ".codex", workspace / ".codex")
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


def _assert_recall_guidance(text: str) -> None:
    assert any(anchor in text for anchor in RECALL_GUIDANCE_ANCHORS)
    for command in EXACT_RECALL_COMMANDS:
        assert command in text
    for term in (
        "planning evidence only",
        "behavioral tests",
        "declared artifacts",
        "validation commands",
        "implementation review",
    ):
        assert term in text


def test_recall_guidance_payload_sync_matches_sources(tmp_path: Path):
    synced_workspace = _sync_distribution(tmp_path)

    for skill_name in WORKFLOW_SKILLS:
        source_claude = f".claude/skills/{skill_name}/SKILL.md"
        distributed_claude = f"maid_runner/claude/skills/{skill_name}/SKILL.md"
        source_codex = f".codex/skills/{skill_name}/SKILL.md"
        distributed_codex = f"maid_runner/codex/skills/{skill_name}/SKILL.md"

        assert _read(distributed_claude, root=synced_workspace) == _read(source_claude)
        assert _read(distributed_codex, root=synced_workspace) == _read(source_codex)
        _assert_recall_guidance(_read(distributed_claude, root=synced_workspace))
        _assert_recall_guidance(_read(distributed_codex, root=synced_workspace))


def test_codex_payload_manifest_lists_recall_workflow_skills_and_agents(
    tmp_path: Path,
):
    synced_workspace = _sync_distribution(tmp_path)
    manifest = json.loads(
        _read("maid_runner/codex/manifest.json", root=synced_workspace)
    )

    distributable_skills = manifest["skills"]["distributable"]
    distributable_agents = manifest["skill_agents"]["distributable"]

    for skill_name in WORKFLOW_SKILLS:
        assert skill_name in distributable_skills
        assert f"{skill_name}/agents/openai.yaml" in distributable_agents
        assert _read(
            f"maid_runner/codex/skills/{skill_name}/agents/openai.yaml",
            root=synced_workspace,
        ) == _read(f".codex/skills/{skill_name}/agents/openai.yaml")


def test_codex_recall_payload_package_data_covers_generated_files():
    pyproject = tomllib.loads(_read("pyproject.toml"))
    package_data = pyproject["tool"]["setuptools"]["package-data"]["maid_runner"]
    generated_files = [
        f"codex/skills/{skill_name}/SKILL.md" for skill_name in WORKFLOW_SKILLS
    ] + [
        f"codex/skills/{skill_name}/agents/openai.yaml"
        for skill_name in WORKFLOW_SKILLS
    ]

    for generated_file in generated_files:
        assert any(fnmatch.fnmatch(generated_file, pattern) for pattern in package_data)
