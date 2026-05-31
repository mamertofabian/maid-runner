"""CLI handler for 'maid init' command."""

from __future__ import annotations

import argparse
import json
import shutil
import sys
from importlib import resources
from pathlib import Path


_MAID_SECTION_START = "<!-- BEGIN MAID RUNNER -->"
_MAID_SECTION_END = "<!-- END MAID RUNNER -->"
_PAYLOAD_PATH_PREFIXES = {
    "agents": "agents",
    "commands": "commands",
    "skills": "skills",
    "skill_agents": "skills",
}


def cmd_init(args: argparse.Namespace) -> int:
    manifest_dir = Path("manifests")
    config_file = Path(".maidrc.yaml")
    install_claude = args.tool in {"auto", "claude"}
    install_codex = args.tool == "codex"

    if not args.force:
        if manifest_dir.exists() and config_file.exists():
            print(
                "MAID already initialized. Use --force to reinitialize.",
                file=sys.stderr,
            )
            return 2

    if args.dry_run:
        print(f"Would create: {manifest_dir}/")
        print(f"Would create: {config_file}")
        if install_claude:
            _print_agent_dry_run("claude", ".claude", "CLAUDE.md")
        if install_codex:
            _print_agent_dry_run("codex", ".codex", "AGENTS.md")
        return 0

    manifest_dir.mkdir(exist_ok=True)

    config_content = (
        "# MAID Runner configuration\n"
        "manifest_dir: manifests/\n"
        "schema_version: 2\n"
        "default_validation_mode: implementation\n"
    )

    config_file.write_text(config_content)

    if install_claude:
        _install_agent_payload(Path.cwd(), "claude", ".claude", "CLAUDE.md")
    if install_codex:
        _install_agent_payload(Path.cwd(), "codex", ".codex", "AGENTS.md")

    print(f"Initialized MAID in {Path.cwd()}")
    print(f"  Created: {manifest_dir}/")
    print(f"  Created: {config_file}")
    if install_claude:
        print("  Updated: .claude/")
        print("  Updated: CLAUDE.md")
    if install_codex:
        print("  Updated: .codex/")
        print("  Updated: AGENTS.md")
    return 0


def _agent_payload_root(tool: str):
    return resources.files("maid_runner").joinpath(tool)


def _agent_manifest(tool: str) -> dict:
    manifest = _agent_payload_root(tool).joinpath("manifest.json")
    return json.loads(manifest.read_text())


def _payload_files(tool: str):
    root = _agent_payload_root(tool)
    for child in root.iterdir():
        if child.is_file():
            yield child, Path(child.name)
            continue
        if child.is_dir():
            yield from _walk_resource_files(child, Path(child.name))


def _walk_resource_files(root, prefix: Path):
    for child in root.iterdir():
        child_path = prefix / child.name
        if child.is_file():
            yield child, child_path
        elif child.is_dir():
            yield from _walk_resource_files(child, child_path)


def _print_agent_dry_run(tool: str, target_dir: str, guidance_file: str) -> None:
    for _, relative_path in _payload_files(tool):
        print(f"Would create: {target_dir}/{relative_path.as_posix()}")
    print(f"Would update: {guidance_file}")


def _install_agent_payload(
    project_root: Path, tool: str, target_dir_name: str, guidance_file_name: str
) -> None:
    target_dir = project_root / target_dir_name
    payload_files = list(_payload_files(tool))
    manifest = _agent_manifest(tool)
    _prune_agent_payload(
        target_dir, _read_existing_agent_manifest(target_dir), manifest
    )
    for source_file, relative_path in payload_files:
        destination = target_dir / relative_path
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(source_file.read_bytes())

    if tool == "claude":
        section = _render_claude_md_section(manifest)
    else:
        section = _render_agents_md_section(manifest)
    _update_marked_guidance(project_root / guidance_file_name, section)


def _read_existing_agent_manifest(target_dir: Path) -> dict:
    manifest_path = target_dir / "manifest.json"
    if not manifest_path.exists():
        return {}
    try:
        return json.loads(manifest_path.read_text())
    except (OSError, json.JSONDecodeError):
        return {}


def _prune_agent_payload(
    target_dir: Path, previous_manifest: dict, current_manifest: dict
) -> None:
    if not target_dir.exists():
        return

    stale_paths = _manifest_payload_paths(previous_manifest) - _manifest_payload_paths(
        current_manifest
    )
    for relative_path in sorted(stale_paths, reverse=True):
        path = target_dir / relative_path
        if path.is_dir():
            shutil.rmtree(path)
            _prune_empty_agent_parents(path.parent, target_dir)
        elif path.exists():
            path.unlink()
            _prune_empty_agent_parents(path.parent, target_dir)


def _manifest_payload_paths(manifest: dict) -> set[str]:
    paths: set[str] = set()
    for section, prefix in _PAYLOAD_PATH_PREFIXES.items():
        for name in manifest.get(section, {}).get("distributable", []):
            paths.add(f"{prefix}/{name}")
    return paths


def _prune_empty_agent_parents(path: Path, target_dir: Path) -> None:
    while path != target_dir and path.parent != path:
        if not path.exists() or any(path.iterdir()):
            return
        path.rmdir()
        path = path.parent


def _update_marked_guidance(path: Path, section: str) -> None:
    if not path.exists():
        path.write_text(section)
        return

    content = path.read_text()
    if _MAID_SECTION_START in content and _MAID_SECTION_END in content:
        before, rest = content.split(_MAID_SECTION_START, 1)
        _, after = rest.split(_MAID_SECTION_END, 1)
        path.write_text(before.rstrip() + "\n\n" + section + after)
        return

    separator = "\n\n" if content.strip() else ""
    path.write_text(content.rstrip() + separator + section)


def _render_claude_md_section(manifest: dict) -> str:
    skills = ", ".join(f"`{name}`" for name in manifest["skills"]["distributable"])
    agents = ", ".join(
        f"`{name.removesuffix('.md')}`" for name in manifest["agents"]["distributable"]
    )
    agent_text = f"\n\nAvailable MAID agents: {agents}." if agents else ""
    return (
        f"{_MAID_SECTION_START}\n"
        "## MAID Runner\n\n"
        "### MAID Skills Workflow\n"
        "Use the installed MAID skills for manifest-driven development: "
        f"{skills}.\n\n"
        "For new features, bug fixes, and refactors, plan with "
        "`maid-planner`, review with `maid-plan-review`, implement with "
        "`maid-implementer`, and review the result with "
        "`maid-implementation-review` before handoff."
        f"{agent_text}\n"
        f"{_MAID_SECTION_END}\n"
    )


def _render_agents_md_section(manifest: dict) -> str:
    skills = ", ".join(f"`{name}`" for name in manifest["skills"]["distributable"])
    agent_count = len(manifest.get("skill_agents", {}).get("distributable", []))
    agent_text = (
        f"\n\nInstalled Codex skill-local agent metadata files: {agent_count}."
        if agent_count
        else ""
    )
    return (
        f"{_MAID_SECTION_START}\n"
        "## MAID Runner\n\n"
        "### MAID Codex Skills Workflow\n"
        "Use the installed MAID Codex skills for repository-specific "
        f"manifest-driven development: {skills}.\n\n"
        "For maid-runner work, plan or audit with the specialized "
        "`maid-runner-*` skills, implement approved drafts with "
        "`maid-runner-draft-implement`, and keep validation-hardening work "
        "inside `maid-validate-hardening`."
        f"{agent_text}\n"
        f"{_MAID_SECTION_END}\n"
    )
