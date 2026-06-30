import argparse
import json
import re
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

from maid_runner.cli.commands._main import build_parser


PROJECT_ROOT = Path(__file__).resolve().parents[1]
AUDITOR_SKILLS = {
    "claude": ".claude/skills/maid-auditor/SKILL.md",
    "codex": ".codex/skills/maid-auditor/SKILL.md",
}
AUDITOR_ANCHOR = "Outcome Insights Cadence"
CODEX_DISTRIBUTABLE_SKILLS = [
    "maid-planner",
    "maid-plan-review",
    "maid-implementer",
    "maid-implementation-review",
    "maid-auditor",
    "maid-outcome-enrich",
]
REPO_INTERNAL_CODEX_SKILLS = [
    "maid-runner-cleanup-and-refactor",
    "maid-runner-draft-implement",
    "maid-runner-performance-optimization",
    "maid-runner-self-improvement",
    "maid-validate-hardening",
]


def _read(relative_path: str, root: Path = PROJECT_ROOT) -> str:
    return (root / relative_path).read_text()


def _normalized(text: str) -> str:
    return " ".join(text.split()).lower()


def _insights_section(skill_text: str) -> str:
    marker = f"### {AUDITOR_ANCHOR}"
    assert marker in skill_text
    start = skill_text.index(marker)
    next_heading = skill_text.find("\n### ", start + len(marker))
    next_rule = skill_text.find("\n---", start + len(marker))
    candidates = [index for index in (next_heading, next_rule) if index != -1]
    end = min(candidates) if candidates else len(skill_text)
    return skill_text[start:end]


def _top_level_command_options(command: str) -> set[str]:
    parser = build_parser()
    for action in parser._actions:
        if isinstance(action, argparse._SubParsersAction):
            subparser = action.choices[command]
            return {
                option
                for subparser_action in subparser._actions
                for option in subparser_action.option_strings
            }
    raise AssertionError("parser has no subcommands")


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


def test_auditor_insights_cadence_is_present_and_specific():
    for skill_path in AUDITOR_SKILLS.values():
        section = _insights_section(_read(skill_path))
        normalized_section = _normalized(section)

        assert "maid insights" in section
        assert "release" in normalized_section
        assert "periodic health" in normalized_section
        assert "advisory aggregate evidence" in normalized_section
        assert "read-only" in normalized_section
        assert "verdict-neutral" in normalized_section
        assert "recommended-actions" in normalized_section


def test_auditor_insights_guidance_uses_only_registered_options():
    registered_options = _top_level_command_options("insights") - {"-h", "--help"}
    assert registered_options == {
        "--index",
        "--manifest-dir",
        "--project-root",
        "--allow-stale-index",
        "--theme-map",
        "--limit",
        "--json",
    }

    forbidden_options = {"--tag", "--include-status"}
    for skill_path in AUDITOR_SKILLS.values():
        section = _insights_section(_read(skill_path))
        used_options = set(re.findall(r"(?<![\w-])--[a-z][a-z-]*", section))

        assert used_options <= registered_options
        assert used_options & forbidden_options == set()
        assert "maid insights --tag" not in section
        assert "maid insights --include-status" not in section


def test_auditor_insights_guidance_handles_stale_index_explicitly():
    for skill_path in AUDITOR_SKILLS.values():
        section = _insights_section(_read(skill_path))
        normalized_section = _normalized(section)

        assert "stale index fails by default" in normalized_section
        assert "run `maid learn`" in section
        assert "--allow-stale-index" in section
        assert "stale advisory read is acceptable" in normalized_section


def test_auditor_insights_guidance_synced_to_agent_payloads(tmp_path: Path):
    synced_workspace = _sync_distribution(tmp_path)

    for tool, source_path in AUDITOR_SKILLS.items():
        distributed_path = f"maid_runner/{tool}/skills/maid-auditor/SKILL.md"
        source_text = _read(source_path)
        distributed_text = _read(distributed_path, root=synced_workspace)

        assert _insights_section(source_text)
        assert _insights_section(distributed_text)
        assert distributed_text == source_text


def test_auditor_insights_guidance_is_distributed_to_codex(tmp_path: Path):
    synced_workspace = _sync_distribution(tmp_path)
    manifest = json.loads(
        _read("maid_runner/codex/manifest.json", root=synced_workspace)
    )

    assert manifest["skills"]["distributable"] == CODEX_DISTRIBUTABLE_SKILLS
    assert "maid-auditor" in manifest["skills"]["descriptions"]
    assert (
        "maid-auditor/agents/openai.yaml" in manifest["skill_agents"]["distributable"]
    )
    assert _read(
        "maid_runner/codex/skills/maid-auditor/SKILL.md",
        root=synced_workspace,
    ) == _read(".codex/skills/maid-auditor/SKILL.md")
    assert _read(
        "maid_runner/codex/skills/maid-auditor/agents/openai.yaml",
        root=synced_workspace,
    ) == _read(".codex/skills/maid-auditor/agents/openai.yaml")


def test_codex_init_installs_auditor_insights_skill(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    from maid_runner.cli.commands._main import main
    from maid_runner.cli.commands.init import cmd_init

    monkeypatch.chdir(tmp_path)
    assert callable(cmd_init)

    exit_code = main(["init", "--tool", "codex"])

    assert exit_code == 0
    skills_dir = tmp_path / ".codex" / "skills"
    installed = sorted(path.name for path in skills_dir.iterdir())
    assert installed == sorted(CODEX_DISTRIBUTABLE_SKILLS)
    assert AUDITOR_ANCHOR in (skills_dir / "maid-auditor" / "SKILL.md").read_text()
    assert (skills_dir / "maid-auditor" / "agents" / "openai.yaml").exists()
    for internal in REPO_INTERNAL_CODEX_SKILLS:
        assert not (skills_dir / internal).exists()
