#!/usr/bin/env python3
"""Sync Claude Code integration files for package distribution.

This script copies .claude/agents/ and .claude/commands/ to maid_runner/claude/
for inclusion in the PyPI package. The source .claude/ directory is used for
active development, while maid_runner/claude/ is generated for distribution.

Usage:
    python scripts/sync_claude_files.py
    OR
    make sync-claude
"""

import shutil
from pathlib import Path


def sync_agents() -> None:
    """Copy .claude/agents/*.md to maid_runner/claude/agents/."""
    # Get project root (where this script is located)
    project_root = Path.cwd()
    source_agents = project_root / ".claude" / "agents"
    dest_root = project_root / "maid_runner" / "claude"
    dest_agents = dest_root / "agents"

    # Check if source exists
    if not source_agents.exists():
        print(
            f"⚠️  Warning: Source directory not found: {source_agents}. Skipping agent sync."
        )
        return

    # Remove old destination directory if it exists
    if dest_agents.exists():
        shutil.rmtree(dest_agents)

    # Create destination directory
    dest_agents.mkdir(parents=True, exist_ok=True)

    # Copy all .md files
    agent_files = list(source_agents.glob("*.md"))
    for agent_file in agent_files:
        shutil.copy2(agent_file, dest_agents / agent_file.name)

    print(f"✓ Synced {len(agent_files)} agent files to {dest_agents}")


def sync_commands() -> None:
    """Copy .claude/commands/*.md to maid_runner/claude/commands/."""
    # Get project root (where this script is located)
    project_root = Path.cwd()
    source_commands = project_root / ".claude" / "commands"
    dest_root = project_root / "maid_runner" / "claude"
    dest_commands = dest_root / "commands"

    # Check if source exists
    if not source_commands.exists():
        print(
            f"⚠️  Warning: Source directory not found: {source_commands}. Skipping command sync."
        )
        return

    # Remove old destination directory if it exists
    if dest_commands.exists():
        shutil.rmtree(dest_commands)

    # Create destination directory
    dest_commands.mkdir(parents=True, exist_ok=True)

    # Copy all .md files
    command_files = list(source_commands.glob("*.md"))
    for command_file in command_files:
        shutil.copy2(command_file, dest_commands / command_file.name)

    print(f"✓ Synced {len(command_files)} command files to {dest_commands}")


def _sync_manifest() -> None:
    """Copy .claude/manifest.json to maid_runner/claude/manifest.json."""
    project_root = Path.cwd()
    source_manifest = project_root / ".claude" / "manifest.json"
    dest_root = project_root / "maid_runner" / "claude"
    dest_manifest = dest_root / "manifest.json"

    if not source_manifest.exists():
        print(
            f"⚠️  Warning: Source manifest not found: {source_manifest}. Skipping manifest sync."
        )
        return

    # Ensure destination directory exists
    dest_root.mkdir(parents=True, exist_ok=True)

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

    print()
    print("=" * 60)
    print("✓ Sync complete!")
    print("=" * 60)


if __name__ == "__main__":
    main()
