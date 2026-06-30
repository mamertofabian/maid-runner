import argparse
import json
import shutil
import subprocess
import sys
from pathlib import Path

try:
    import tomllib
except ModuleNotFoundError:  # pragma: no cover - Python 3.10 fallback
    import tomli as tomllib

from maid_runner.cli.commands._main import build_parser


PROJECT_ROOT = Path(__file__).resolve().parents[1]
CODEX_DISTRIBUTABLE_SKILLS = [
    "maid-planner",
    "maid-plan-review",
    "maid-implementer",
    "maid-implementation-review",
    "maid-auditor",
    "maid-outcome-enrich",
]


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


def _top_level_commands(parser: argparse.ArgumentParser) -> list[str]:
    for action in parser._actions:
        if isinstance(action, argparse._SubParsersAction):
            return sorted(action.choices)
    raise AssertionError("parser has no subcommands")


def _command_options(parser: argparse.ArgumentParser, command: str) -> set[str]:
    for action in parser._actions:
        if isinstance(action, argparse._SubParsersAction):
            subparser = action.choices[command]
            return {
                option
                for subparser_action in subparser._actions
                for option in subparser_action.option_strings
            }
    raise AssertionError("parser has no subcommands")


def test_codex_payload_manifest_matches_source_skills(tmp_path: Path):
    from scripts.sync_claude_files import main as sync_main

    assert callable(sync_main)
    synced_workspace = _sync_distribution(tmp_path)
    manifest = json.loads(
        _read("maid_runner/codex/manifest.json", root=synced_workspace)
    )

    assert manifest["skills"]["distributable"] == CODEX_DISTRIBUTABLE_SKILLS

    for skill_name in CODEX_DISTRIBUTABLE_SKILLS:
        source_skill = f".codex/skills/{skill_name}/SKILL.md"
        distributed_skill = f"maid_runner/codex/skills/{skill_name}/SKILL.md"
        assert _read(distributed_skill, root=synced_workspace) == _read(source_skill)

    for relative_agent in manifest["skill_agents"]["distributable"]:
        source_agent = f".codex/skills/{relative_agent}"
        distributed_agent = f"maid_runner/codex/skills/{relative_agent}"
        assert _read(distributed_agent, root=synced_workspace) == _read(source_agent)


def test_agent_payload_package_data_includes_claude_and_codex_assets():
    pyproject = tomllib.loads(_read("pyproject.toml"))
    package_data = pyproject["tool"]["setuptools"]["package-data"]["maid_runner"]

    for pattern in (
        "claude/manifest.json",
        "claude/agents/*.md",
        "claude/skills/*/SKILL.md",
        "codex/manifest.json",
        "codex/skills/*/SKILL.md",
        "codex/skills/*/agents/*.yaml",
        "docs/draft-manifest-workflow.md",
        "docs/manifest-outcome-records.md",
        "manifests/drafts/README.md",
    ):
        assert pattern in package_data


def test_command_docs_match_registered_parser_commands():
    commands = _top_level_commands(build_parser())
    docs_text = _read("README.md") + "\n" + _read("docs/ROADMAP.md")

    for command in commands:
        assert f"`maid {command}" in docs_text

    assert "`maid learn`" in docs_text
    assert "`maid recall`" in docs_text
    assert "`maid insights`" in docs_text
    assert "`maid test`" in docs_text and "`--jobs" in docs_text
    assert "`maid verify`" in docs_text and "`--test-jobs" in docs_text
    assert "codex" in docs_text.lower()


def test_codex_skill_probe_commands_use_registered_cli_options():
    parser = build_parser()
    test_options = _command_options(parser, "test")
    verify_options = _command_options(parser, "verify")
    source_self_improvement = _read(
        ".codex/skills/maid-runner-self-improvement/SKILL.md"
    )
    source_performance = _read(
        ".codex/skills/maid-runner-performance-optimization/SKILL.md"
    )
    distributed_self_improvement = _read(
        "maid_runner/codex/skills/maid-runner-self-improvement/SKILL.md"
    )
    distributed_performance = _read(
        "maid_runner/codex/skills/maid-runner-performance-optimization/SKILL.md"
    )
    skill_text = "\n".join(
        [
            source_self_improvement,
            source_performance,
            distributed_self_improvement,
            distributed_performance,
        ]
    )

    assert "--quiet" not in test_options
    assert "--quiet" not in verify_options
    assert "--json" in test_options
    assert "--json" in verify_options
    assert distributed_self_improvement == source_self_improvement
    assert distributed_performance == source_performance
    assert "maid test --quiet" not in skill_text
    assert "maid verify --keep-going --quiet" not in skill_text
    assert "maid test --json" in skill_text
    assert "maid verify --keep-going --json" in skill_text
