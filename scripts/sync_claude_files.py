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
    "maid-implement-draft",
    "maid-implementer",
    "maid-implementation-review",
    "maid-evolver",
    "maid-auditor",
    "maid-incident-logger",
    "maid-outcome-enrich",
    "maid-run-review",
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

_ANTIGRAVITY_SCOPE_CHECK_HOOK_NAME = "maid-scope-check"
_ANTIGRAVITY_SCOPE_CHECK_MATCHER = (
    "write_file|edit_file|write_to_file|replace_file_content|"
    "multi_replace_file_content"
)
_ANTIGRAVITY_SCOPE_CHECK_COMMAND = "maid hook scope-check --stdin --format antigravity"
_CLAUDE_REVIEWER_SUBAGENT_BLOCK = (
    '- use `subagent_type: "maid-implementation-reviewer"`\n'
    "- use a fresh agent; never fork the full session context into an independent\n"
    "  reviewer\n"
    "- leave the model unset unless the user or local project instructions require a\n"
    "  specific model\n"
    "- pass the review packet explicitly\n"
    "- instruct the subagent not to edit files and not to spawn further subagents\n"
    "- wait for the subagent verdict before final handoff\n"
    "- close the subagent thread after consuming the verdict"
)
_ANTIGRAVITY_REVIEWER_SUBAGENT_BLOCK = (
    '- use `invoke_subagent` with `TypeName: "research"` (fresh read-only subagent;\n'
    "  never inherit or pass the implementation transcript)\n"
    '- pass `Model: "inherit"` unless the user or local project instructions require a\n'
    "  specific model\n"
    "- pass the complete verdict-neutral review packet explicitly (including factual\n"
    "  validation outputs, since `research` is read-only)\n"
    "- instruct the subagent not to edit files and not to spawn further subagents\n"
    "- wait for the subagent verdict before final handoff\n"
    '- close the subagent with `manage_subagents` (`Action: "kill"`) after consuming\n'
    "  the verdict"
)


def _project_root() -> Path:
    return Path.cwd()


def _claude_dest_root() -> Path:
    return _project_root() / "maid_runner" / "claude"


def _codex_dest_root() -> Path:
    return _project_root() / "maid_runner" / "codex"


def _cursor_dest_root() -> Path:
    return _project_root() / "maid_runner" / "cursor"


def _antigravity_dest_root() -> Path:
    return _project_root() / "maid_runner" / "antigravity"


def _copy_file(source: Path, destination: Path) -> bool:
    if not source.exists():
        print(f"⚠️  Warning: Source file not found: {source}. Skipping.")
        return False
    destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source, destination)
    return True


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
                "maid-implement-draft": (
                    "Harden, lock, promote, and implement a MAID draft manifest"
                ),
                "maid-implementer": (
                    "Implement approved MAID manifests with Outcome recall context"
                ),
                "maid-implementation-review": (
                    "Review MAID implementations and Outcome record needs"
                ),
                "maid-evolver": (
                    "Intentionally evolve existing MAID manifest contracts"
                ),
                "maid-auditor": (
                    "Audit MAID contracts with advisory Outcome insights cadence"
                ),
                "maid-incident-logger": (
                    "Record curated MAID workflow drift or gaming incidents"
                ),
                "maid-outcome-enrich": (
                    "Generate advisory Outcome enrichment outside maid-runner"
                ),
                "maid-run-review": (
                    "Generate advisory MAID run reviews outside maid-runner"
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


def _antigravity_hooks() -> dict:
    return {
        _ANTIGRAVITY_SCOPE_CHECK_HOOK_NAME: {
            "PreToolUse": [
                {
                    "matcher": _ANTIGRAVITY_SCOPE_CHECK_MATCHER,
                    "hooks": [
                        {
                            "type": "command",
                            "command": _ANTIGRAVITY_SCOPE_CHECK_COMMAND,
                        }
                    ],
                }
            ]
        }
    }


def _apply_antigravity_review_overlay(skill_text: str) -> str:
    if _CLAUDE_REVIEWER_SUBAGENT_BLOCK not in skill_text:
        raise ValueError(
            "Cannot generate Antigravity maid-implementation-review skill: "
            "expected Claude reviewer subagent block was not found in source SKILL.md."
        )
    return skill_text.replace(
        _CLAUDE_REVIEWER_SUBAGENT_BLOCK,
        _ANTIGRAVITY_REVIEWER_SUBAGENT_BLOCK,
        1,
    )


def _antigravity_manifest(skill_names: list[str]) -> dict:
    claude_descriptions = (
        _load_claude_manifest().get("skills", {}).get("descriptions", {})
    )
    descriptions = {
        name: str(claude_descriptions[name])
        for name in skill_names
        if name in claude_descriptions
    }
    return {
        "root": {
            "distributable": ["hooks.json"],
            "descriptions": {
                "hooks.json": (
                    "Antigravity hooks configuration that runs MAID scope checks "
                    "before write/edit tool events"
                )
            },
        },
        "skills": {
            "distributable": skill_names,
            "descriptions": descriptions,
        },
    }


def sync_antigravity_payload() -> None:
    """Generate maid_runner/antigravity/ from canonical .claude/skills/ + overlay."""
    project_root = _project_root()
    source_skills = project_root / ".claude" / "skills"
    dest_root = _antigravity_dest_root()
    dest_skills = dest_root / "skills"

    if not source_skills.exists():
        print(
            f"⚠️  Warning: Source directory not found: {source_skills}. "
            "Skipping Antigravity sync."
        )
        return

    skill_names = _declared_claude_items("skills", list(CODEX_DISTRIBUTABLE_SKILLS))
    overlaid_review_text: str | None = None
    if "maid-implementation-review" in skill_names:
        review_source_dir = source_skills / "maid-implementation-review"
        if review_source_dir.exists():
            review_skill_md = review_source_dir / "SKILL.md"
            if not review_skill_md.is_file():
                raise ValueError(
                    "Cannot generate Antigravity maid-implementation-review skill: "
                    f"missing source SKILL.md at {review_skill_md}."
                )
            overlaid_review_text = _apply_antigravity_review_overlay(
                review_skill_md.read_text(encoding="utf-8")
            )

    _replace_directory(dest_root)
    dest_skills.mkdir(parents=True, exist_ok=True)

    installed_skill_names: list[str] = []
    for skill_name in skill_names:
        source_dir = source_skills / skill_name
        if not source_dir.exists():
            continue
        target_dir = dest_skills / skill_name
        shutil.copytree(source_dir, target_dir)
        if (
            skill_name == "maid-implementation-review"
            and overlaid_review_text is not None
        ):
            (target_dir / "SKILL.md").write_text(overlaid_review_text, encoding="utf-8")
        installed_skill_names.append(skill_name)

    (dest_root / "hooks.json").write_text(
        json.dumps(_antigravity_hooks(), indent=2) + "\n", encoding="utf-8"
    )
    manifest = _antigravity_manifest(installed_skill_names)
    (dest_root / "manifest.json").write_text(
        json.dumps(manifest, indent=2) + "\n", encoding="utf-8"
    )

    print(
        f"✓ Synced {len(installed_skill_names)} Antigravity skill directories to {dest_skills}"
    )
    print(f"✓ Synced Antigravity hooks.json to {dest_root / 'hooks.json'}")
    print(f"✓ Synced Antigravity manifest.json to {dest_root / 'manifest.json'}")


def sync_user_skills() -> None:
    """Copy the repo maid-onboard skill sources into maid_runner/user_skills/.

    The maid-onboard skill is a user-level bootstrapper: it is packaged so
    `maid skills install` can deliver it to ~/.claude and ~/.codex, but it is
    kept out of the per-repo init payloads (maid_runner/<tool>/skills) and the
    distributable manifests so `maid init` never installs it into a project.
    """
    project_root = _project_root()
    dest_root = project_root / "maid_runner" / "user_skills"
    _remove_directory(dest_root)

    copied = 0
    for tool in ("claude", "codex"):
        source = project_root / f".{tool}" / "skills" / "maid-onboard"
        if not source.exists():
            continue
        shutil.copytree(source, dest_root / tool / "maid-onboard")
        copied += 1

    print(f"✓ Synced {copied} user skill directories to {dest_root}")


def sync_init_workflow_payloads() -> None:
    """Copy workflow docs installed by `maid init` into package resources."""
    project_root = _project_root()
    payloads = (
        (
            "docs/draft-manifest-workflow.md",
            "maid_runner/docs/draft-manifest-workflow.md",
        ),
        (
            "docs/manifest-outcome-records.md",
            "maid_runner/docs/manifest-outcome-records.md",
        ),
        ("manifests/drafts/README.md", "maid_runner/manifests/drafts/README.md"),
    )

    copied = 0
    for source_path, destination_path in payloads:
        if _copy_file(project_root / source_path, project_root / destination_path):
            copied += 1

    print(f"✓ Synced {copied} init workflow payload files")


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
    sync_antigravity_payload()
    sync_user_skills()
    sync_init_workflow_payloads()

    print()
    print("=" * 60)
    print("✓ Sync complete!")
    print("=" * 60)


if __name__ == "__main__":
    main()
