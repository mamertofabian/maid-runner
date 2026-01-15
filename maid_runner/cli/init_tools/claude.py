"""Claude Code tool setup for MAID init.

This module handles setting up Claude Code integration by copying
agent and command files to .claude/agents/ and .claude/commands/ directories.
"""

import shutil
from pathlib import Path

from maid_runner.cli.init import get_distributable_files, load_claude_manifest


def setup_claude(target_dir: str, force: bool, dry_run: bool = False) -> None:
    """Set up Claude Code integration in target directory.

    Args:
        target_dir: Target directory to initialize MAID in
        force: If True, copy without prompting
        dry_run: If True, show what would be copied without making changes
    """
    copy_claude_agents(target_dir, force, dry_run)
    copy_claude_commands(target_dir, force, dry_run)


def copy_claude_agents(target_dir: str, force: bool, dry_run: bool = False) -> None:
    """Copy Claude Code agent files to .claude/agents/ directory.

    Args:
        target_dir: Target directory for .claude/agents/
        force: If True, copy without prompting
        dry_run: If True, show what would be copied without making changes
    """
    # Get source location from package
    current_file = Path(__file__)
    maid_runner_package = current_file.parent.parent.parent
    source_agents = maid_runner_package / "claude" / "agents"

    if not source_agents.exists():
        print(
            f"⚠️  Warning: Could not find claude/agents at {source_agents}. Skipping copy."
        )
        return

    # Prompt user if not forcing and not dry-run
    if not force and not dry_run:
        response = input("Copy Claude Code agent files (.claude/agents)? (Y/n): ")
        if response.lower() in ("n", "no"):
            print("⊘ Skipped Claude Code agent files")
            return

    # Create destination directory
    dest_agents = Path(target_dir) / ".claude" / "agents"
    if not dry_run:
        dest_agents.mkdir(parents=True, exist_ok=True)

    # Load manifest and get distributable files
    manifest = load_claude_manifest()
    distributable = get_distributable_files(manifest, "agents")

    # Copy only distributable agent files
    copied_count = 0
    for filename in distributable:
        source_file = source_agents / filename
        if source_file.exists():
            dest_file = dest_agents / filename
            if dry_run:
                action = "[UPDATE]" if dest_file.exists() else "[CREATE]"
                print(f"{action} {dest_file}")
            else:
                shutil.copy2(source_file, dest_file)
            copied_count += 1

    if not dry_run:
        print(f"✓ Copied {copied_count} Claude Code agent files to {dest_agents}")


def copy_claude_commands(target_dir: str, force: bool, dry_run: bool = False) -> None:
    """Copy Claude Code command files to .claude/commands/ directory.

    Args:
        target_dir: Target directory for .claude/commands/
        force: If True, copy without prompting
        dry_run: If True, show what would be copied without making changes
    """
    # Get source location from package
    current_file = Path(__file__)
    maid_runner_package = current_file.parent.parent.parent
    source_commands = maid_runner_package / "claude" / "commands"

    if not source_commands.exists():
        print(
            f"⚠️  Warning: Could not find claude/commands at {source_commands}. Skipping copy."
        )
        return

    # Prompt user if not forcing and not dry-run
    if not force and not dry_run:
        response = input("Copy Claude Code command files (.claude/commands)? (Y/n): ")
        if response.lower() in ("n", "no"):
            print("⊘ Skipped Claude Code command files")
            return

    # Create destination directory
    dest_commands = Path(target_dir) / ".claude" / "commands"
    if not dry_run:
        dest_commands.mkdir(parents=True, exist_ok=True)

    # Load manifest and get distributable files
    manifest = load_claude_manifest()
    distributable = get_distributable_files(manifest, "commands")

    # Copy only distributable command files
    copied_count = 0
    for filename in distributable:
        source_file = source_commands / filename
        if source_file.exists():
            dest_file = dest_commands / filename
            if dry_run:
                action = "[UPDATE]" if dest_file.exists() else "[CREATE]"
                print(f"{action} {dest_file}")
            else:
                shutil.copy2(source_file, dest_file)
            copied_count += 1

    if not dry_run:
        print(f"✓ Copied {copied_count} Claude Code command files to {dest_commands}")
