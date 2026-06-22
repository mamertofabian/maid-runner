#!/usr/bin/env python3
"""Sync Claude, Codex, and Cursor integration files for package distribution.

This script copies manifest-declared Claude agents, commands, skills, and
settings plus repo-owned Codex skills and Cursor hooks to maid_runner/ for
inclusion in the PyPI package. The source .claude/, .codex/, and .cursor/
directories are used for active development, while maid_runner/claude/,
maid_runner/codex/, and maid_runner/cursor/ are generated for distribution.

Usage:
    python scripts/sync_claude_files.py
    OR
    make sync-agent-payloads
"""

import json
import shutil
from pathlib import Path


# Skills declared distributable in the generated Codex payload manifest. These
# are the generic, tool-agnostic MAID skills that `maid init --tool codex`
# installs into any repository. Repo-internal maid-runner-* and
# maid-validate-hardening skills are deliberately excluded so they are never
# installed into other repositories.
CODEX_DISTRIBUTABLE_SKILLS = [
    "maid-planner",
    "maid-plan-review",
    "maid-implementer",
    "maid-implementation-review",
]

# Skills copied into the packaged Codex payload. The repo-internal skills stay
# packaged so this repository's own Codex tooling and the generated-payload
# artifacts declared by prior manifests keep working, but they remain inert for
# other repositories because they are not in CODEX_DISTRIBUTABLE_SKILLS and the
# installer honors the distributable list.
CODEX_PACKAGED_SKILLS = [
    *CODEX_DISTRIBUTABLE_SKILLS,
    "maid-runner-cleanup-and-refactor",
    "maid-runner-draft-implement",
    "maid-runner-performance-optimization",
    "maid-runner-self-improvement",
    "maid-validate-hardening",
]


def _project_root() -> Path:
    return Path.cwd()


def _claude_dest_root() -> Path:
    return _project_root() / "maid_runner" / "claude"


def _codex_dest_root() -> Path:
    return _project_root() / "maid_runner" / "codex"


def _cursor_dest_root() -> Path:
    return _project_root() / "maid_runner" / "cursor"


def _load_claude_manifest() -> dict:
    source_manifest = _project_root() / ".claude" / "manifest.json"
    if not source_manifest.exists():
        return {}
    return json.loads(source_manifest.read_text())


def _declared_claude_items(section: str, fallback: list[str]) -> list[str]:
    manifest = _load_claude_manifest()
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
    dest_agents = _claude_dest_root() / "agents"

    agent_names = _declared_claude_items(
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
    dest_commands = _claude_dest_root() / "commands"

    command_names = _declared_claude_items(
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
    dest_skills = _claude_dest_root() / "skills"

    skill_names = _declared_claude_items(
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
    dest_manifest = _claude_dest_root() / "manifest.json"

    if not source_manifest.exists():
        print(
            f"⚠️  Warning: Source manifest not found: {source_manifest}. Skipping manifest sync."
        )
        return

    dest_manifest.parent.mkdir(parents=True, exist_ok=True)

    shutil.copy2(source_manifest, dest_manifest)
    print(f"✓ Synced manifest.json to {dest_manifest}")


def _sync_claude_settings() -> None:
    """Copy .claude/settings.json to maid_runner/claude/settings.json."""
    project_root = _project_root()
    source_settings = project_root / ".claude" / "settings.json"
    dest_settings = _claude_dest_root() / "settings.json"

    if not source_settings.exists():
        print(
            f"⚠️  Warning: Source settings not found: {source_settings}. Skipping Claude settings sync."
        )
        return

    dest_settings.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source_settings, dest_settings)
    print(f"✓ Synced settings.json to {dest_settings}")


def _codex_skill_agent_paths(source_skills: Path, skill_names: list[str]) -> list[str]:
    agent_paths: list[str] = []
    for skill_name in skill_names:
        agents_dir = source_skills / skill_name / "agents"
        if not agents_dir.exists():
            continue
        for agent_file in sorted(agents_dir.rglob("*")):
            if agent_file.is_file():
                agent_paths.append(
                    (
                        Path(skill_name)
                        / agent_file.relative_to(source_skills / skill_name)
                    ).as_posix()
                )
    return agent_paths


def _codex_manifest(source_skills: Path, skill_names: list[str]) -> dict:
    return {
        "skills": {
            "distributable": skill_names,
            "descriptions": {
                "maid-planner": (
                    "Plan MAID changes with manifest-derived Outcome recall"
                ),
                "maid-plan-review": (
                    "Review a MAID manifest and behavioral tests before implementation"
                ),
                "maid-implementer": (
                    "Implement approved MAID manifests with Outcome recall context"
                ),
                "maid-implementation-review": (
                    "Review MAID implementations and Outcome record needs"
                ),
            },
        },
        "skill_agents": {
            "distributable": _codex_skill_agent_paths(source_skills, skill_names),
            "descriptions": {},
        },
    }


def sync_codex_payload() -> None:
    """Copy repo-owned .codex/skills/* directories to maid_runner/codex/."""
    project_root = _project_root()
    source_skills = project_root / ".codex" / "skills"
    dest_root = _codex_dest_root()
    dest_skills = dest_root / "skills"

    if not source_skills.exists():
        print(
            f"⚠️  Warning: Source directory not found: {source_skills}. Skipping Codex sync."
        )
        return

    _replace_directory(dest_skills)
    copied = 0
    for skill_name in CODEX_PACKAGED_SKILLS:
        source_dir = source_skills / skill_name
        if source_dir.exists():
            shutil.copytree(source_dir, dest_skills / skill_name)
            copied += 1

    dest_root.mkdir(parents=True, exist_ok=True)
    manifest = _codex_manifest(source_skills, CODEX_DISTRIBUTABLE_SKILLS)
    (dest_root / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")

    print(f"✓ Synced {copied} Codex skill directories to {dest_skills}")
    print(f"✓ Synced Codex manifest.json to {dest_root / 'manifest.json'}")


def sync_cursor_payload() -> None:
    """Copy repo-owned .cursor/hooks.json to maid_runner/cursor/."""
    project_root = _project_root()
    source_hooks = project_root / ".cursor" / "hooks.json"
    dest_root = _cursor_dest_root()

    if not source_hooks.exists():
        print(
            f"⚠️  Warning: Source Cursor hooks not found: {source_hooks}. Skipping Cursor sync."
        )
        return

    _replace_directory(dest_root)
    shutil.copy2(source_hooks, dest_root / "hooks.json")
    manifest = {
        "root": {
            "distributable": ["hooks.json"],
            "descriptions": {
                "hooks.json": (
                    "Cursor hook configuration that runs MAID scope checks "
                    "before write/edit tool events"
                )
            },
        }
    }
    (dest_root / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")

    print(f"✓ Synced Cursor hooks.json to {dest_root / 'hooks.json'}")
    print(f"✓ Synced Cursor manifest.json to {dest_root / 'manifest.json'}")


def main() -> None:
    """Main entry point - orchestrate the full sync process."""
    print("=" * 60)
    print(
        "Syncing Claude, Codex, and Cursor integration files for package distribution"
    )
    print("=" * 60)
    print()

    _sync_manifest()
    _sync_claude_settings()
    sync_agents()
    sync_commands()
    sync_skills()
    sync_codex_payload()
    sync_cursor_payload()

    print()
    print("=" * 60)
    print("✓ Sync complete!")
    print("=" * 60)


if __name__ == "__main__":
    main()
