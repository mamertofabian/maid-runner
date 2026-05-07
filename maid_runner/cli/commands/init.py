"""CLI handler for 'maid init' command."""

from __future__ import annotations

import argparse
import json
import sys
from importlib import resources
from pathlib import Path


_MAID_SECTION_START = "<!-- BEGIN MAID RUNNER -->"
_MAID_SECTION_END = "<!-- END MAID RUNNER -->"


def cmd_init(args: argparse.Namespace) -> int:
    manifest_dir = Path("manifests")
    config_file = Path(".maidrc.yaml")
    install_claude = args.tool in {"auto", "claude"}

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
            _print_claude_dry_run()
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
        _install_claude_payload(Path.cwd())

    print(f"Initialized MAID in {Path.cwd()}")
    print(f"  Created: {manifest_dir}/")
    print(f"  Created: {config_file}")
    if install_claude:
        print("  Updated: .claude/")
        print("  Updated: CLAUDE.md")
    return 0


def _claude_payload_root():
    return resources.files("maid_runner").joinpath("claude")


def _claude_manifest() -> dict:
    manifest = _claude_payload_root().joinpath("manifest.json")
    return json.loads(manifest.read_text())


def _payload_files():
    root = _claude_payload_root()
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


def _print_claude_dry_run() -> None:
    for _, relative_path in _payload_files():
        print(f"Would create: .claude/{relative_path.as_posix()}")
    print("Would update: CLAUDE.md")


def _install_claude_payload(project_root: Path) -> None:
    claude_dir = project_root / ".claude"
    for source_file, relative_path in _payload_files():
        destination = claude_dir / relative_path
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(source_file.read_bytes())

    _update_claude_md(project_root / "CLAUDE.md", _claude_manifest())


def _update_claude_md(path: Path, manifest: dict) -> None:
    section = _render_claude_md_section(manifest)
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
    commands = ", ".join(
        f"`/{name.removesuffix('.md')}`"
        for name in manifest["commands"]["distributable"]
    )
    return (
        f"{_MAID_SECTION_START}\n"
        "## MAID Runner\n\n"
        "### MAID Skills Workflow\n"
        "Use the installed MAID skills for manifest-driven development: "
        f"{skills}.\n\n"
        "For new features, bug fixes, and refactors, plan with "
        "`maid-planner`, review with `maid-plan-review`, implement with "
        "`maid-implementer`, and review the result with "
        "`maid-implementation-review` before handoff.\n\n"
        "Available MAID agents: "
        f"{agents}.\n\n"
        "Available MAID slash commands: "
        f"{commands}.\n"
        f"{_MAID_SECTION_END}\n"
    )
