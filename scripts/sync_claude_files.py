#!/usr/bin/env python3
"""Sync Claude Code integration files for package distribution.

This script copies manifest-declared Claude agents, commands, and skills to
maid_runner/claude/ for inclusion in the PyPI package.
The source .claude/ directory is used for active development,
while maid_runner/claude/ is generated for distribution.

Usage:
    python scripts/sync_claude_files.py
    OR
    make sync-claude
"""

import json
import shutil
from pathlib import Path


def _project_root() -> Path:
    return Path.cwd()


def _dest_root() -> Path:
    return _project_root() / "maid_runner" / "claude"


def _load_manifest() -> dict:
    source_manifest = _project_root() / ".claude" / "manifest.json"
    if not source_manifest.exists():
        return {}
    return json.loads(source_manifest.read_text())


def _declared_items(section: str, fallback: list[str]) -> list[str]:
    manifest = _load_manifest()
    section_data = manifest.get(section, {})
    if "distributable" not in section_data:
        return fallback
    return [str(value) for value in section_data["distributable"]]


def _replace_directory(path: Path) -> None:
    if path.exists():
        shutil.rmtree(path)
    path.mkdir(parents=True, exist_ok=True)


def _remove_directory(path: Path) -> None:
    if path.exists():
        shutil.rmtree(path)


def sync_agents() -> None:
    """Copy .claude/agents/*.md to maid_runner/claude/agents/."""
    project_root = _project_root()
    source_agents = project_root / ".claude" / "agents"
    dest_agents = _dest_root() / "agents"

    agent_names = _declared_items(
        "agents",
        (
            sorted(agent_file.name for agent_file in source_agents.glob("*.md"))
            if source_agents.exists()
            else []
        ),
    )
    if not agent_names:
        _remove_directory(dest_agents)
        print(f"✓ Synced 0 agent files to {dest_agents}")
        return

    if not source_agents.exists():
        print(
            f"⚠️  Warning: Source directory not found: {source_agents}. Skipping agent sync."
        )
        return

    _replace_directory(dest_agents)
    copied = 0
    for agent_name in agent_names:
        source_file = source_agents / agent_name
        if source_file.exists():
            shutil.copy2(source_file, dest_agents / agent_name)
            copied += 1

    print(f"✓ Synced {copied} agent files to {dest_agents}")


def sync_commands() -> None:
    """Copy .claude/commands/*.md to maid_runner/claude/commands/."""
    project_root = _project_root()
    source_commands = project_root / ".claude" / "commands"
    dest_commands = _dest_root() / "commands"

    command_names = _declared_items(
        "commands",
        (
            sorted(command_file.name for command_file in source_commands.glob("*.md"))
            if source_commands.exists()
            else []
        ),
    )
    if not command_names:
        _remove_directory(dest_commands)
        print(f"✓ Synced 0 command files to {dest_commands}")
        return

    if not source_commands.exists():
        print(
            f"⚠️  Warning: Source directory not found: {source_commands}. Skipping command sync."
        )
        return

    _replace_directory(dest_commands)
    copied = 0
    for command_name in command_names:
        source_file = source_commands / command_name
        if source_file.exists():
            shutil.copy2(source_file, dest_commands / command_name)
            copied += 1

    print(f"✓ Synced {copied} command files to {dest_commands}")


def sync_skills() -> None:
    """Copy manifest-declared .claude/skills/* directories to maid_runner/claude/skills/."""
    project_root = _project_root()
    source_skills = project_root / ".claude" / "skills"
    dest_skills = _dest_root() / "skills"

    skill_names = _declared_items(
        "skills",
        (
            sorted(
                skill_dir.name
                for skill_dir in source_skills.iterdir()
                if skill_dir.is_dir()
            )
            if source_skills.exists()
            else []
        ),
    )
    if not skill_names:
        _remove_directory(dest_skills)
        print(f"✓ Synced 0 skill directories to {dest_skills}")
        return

    if not source_skills.exists():
        print(
            f"⚠️  Warning: Source directory not found: {source_skills}. Skipping skill sync."
        )
        return

    _replace_directory(dest_skills)
    copied = 0
    for skill_name in skill_names:
        source_dir = source_skills / skill_name
        if source_dir.exists():
            shutil.copytree(source_dir, dest_skills / skill_name)
            copied += 1

    print(f"✓ Synced {copied} skill directories to {dest_skills}")


def _sync_manifest() -> None:
    """Copy .claude/manifest.json to maid_runner/claude/manifest.json."""
    project_root = _project_root()
    source_manifest = project_root / ".claude" / "manifest.json"
    dest_manifest = _dest_root() / "manifest.json"

    if not source_manifest.exists():
        print(
            f"⚠️  Warning: Source manifest not found: {source_manifest}. Skipping manifest sync."
        )
        return

    dest_manifest.parent.mkdir(parents=True, exist_ok=True)

    shutil.copy2(source_manifest, dest_manifest)
    print(f"✓ Synced manifest.json to {dest_manifest}")


def main() -> None:
    """Main entry point - orchestrate the full sync process."""
    print("=" * 60)
    print("Syncing Claude Code integration files for package distribution")
    print("=" * 60)
    print()

    _sync_manifest()
    sync_agents()
    sync_commands()
    sync_skills()

    print()
    print("=" * 60)
    print("✓ Sync complete!")
    print("=" * 60)


if __name__ == "__main__":
    main()
