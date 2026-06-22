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
    "root": "",
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
    install_cursor = args.tool == "cursor"

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
        if install_cursor:
            _print_agent_dry_run("cursor", ".cursor", None)
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
    if install_cursor:
        _install_agent_payload(Path.cwd(), "cursor", ".cursor", None)

    print(f"Initialized MAID in {Path.cwd()}")
    print(f"  Created: {manifest_dir}/")
    print(f"  Created: {config_file}")
    if install_claude:
        print("  Updated: .claude/")
        print("  Updated: CLAUDE.md")
    if install_codex:
        print("  Updated: .codex/")
        print("  Updated: AGENTS.md")
    if install_cursor:
        print("  Updated: .cursor/")
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


def _distributable_skill_names(manifest: dict) -> set[str]:
    return set(manifest.get("skills", {}).get("distributable", []))


def _installable_payload_files(tool: str, manifest: dict):
    """Yield payload files, restricting the skills subtree to distributable skills.

    Non-skill payload files (manifest.json, settings.json, agents) always
    install. A file under ``skills/<name>/`` installs only when ``<name>`` is in
    the manifest's ``skills.distributable`` list, so packaged-but-undistributed
    skills are never written into the target repository.
    """
    allowed_skills = _distributable_skill_names(manifest)
    for source_file, relative_path in _payload_files(tool):
        parts = relative_path.parts
        if parts and parts[0] == "skills":
            if len(parts) >= 2 and parts[1] not in allowed_skills:
                continue
        yield source_file, relative_path


def _print_agent_dry_run(tool: str, target_dir: str, guidance_file: str | None) -> None:
    manifest = _agent_manifest(tool)
    for _, relative_path in _installable_payload_files(tool, manifest):
        print(f"Would create: {target_dir}/{relative_path.as_posix()}")
    if guidance_file is not None:
        print(f"Would update: {guidance_file}")


def _install_agent_payload(
    project_root: Path, tool: str, target_dir_name: str, guidance_file_name: str | None
) -> None:
    target_dir = project_root / target_dir_name
    manifest = _agent_manifest(tool)
    payload_files = list(_installable_payload_files(tool, manifest))
    _prune_agent_payload(
        target_dir, _read_existing_agent_manifest(target_dir), manifest
    )
    for source_file, relative_path in payload_files:
        destination = target_dir / relative_path
        destination.parent.mkdir(parents=True, exist_ok=True)
        if tool == "claude" and relative_path == Path("settings.json"):
            _merge_claude_settings(destination, json.loads(source_file.read_text()))
        else:
            destination.write_bytes(source_file.read_bytes())

    if guidance_file_name is None:
        return

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
            paths.add(f"{prefix}/{name}" if prefix else str(name))
    return paths


def _merge_claude_settings(destination: Path, packaged_settings: dict) -> None:
    if destination.exists():
        existing_settings = json.loads(destination.read_text())
        if not isinstance(existing_settings, dict):
            raise ValueError(
                f"Existing Claude settings must be a JSON object: {destination}"
            )
    else:
        existing_settings = {}

    merged = dict(existing_settings)
    merged_hooks = dict(merged.get("hooks", {}))
    packaged_hooks = packaged_settings.get("hooks", {})
    for hook_name, packaged_entries in packaged_hooks.items():
        existing_entries = list(merged_hooks.get(hook_name, []))
        for packaged_entry in packaged_entries:
            if packaged_entry not in existing_entries:
                existing_entries.append(packaged_entry)
        merged_hooks[hook_name] = existing_entries
    merged["hooks"] = merged_hooks
    destination.write_text(json.dumps(merged, indent=2) + "\n")


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
        "`maid-implementation-review` before handoff.\n\n"
        f"{_render_draft_outcome_guidance()}"
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
        "Use the installed MAID Codex skills for manifest-driven development: "
        f"{skills}.\n\n"
        "For new features, bug fixes, and refactors, plan with `maid-planner`, "
        "review with `maid-plan-review`, implement with `maid-implementer`, and "
        "review the result with `maid-implementation-review` before handoff.\n\n"
        "Before editing a file during an active MAID task, run "
        "`maid hook scope-check --path <file>` and treat exit code 2 as "
        "out-of-scope. This pre-edit hook check is advisory and does not "
        "replace `maid verify` changed-scope validation.\n\n"
        f"{_render_draft_outcome_guidance()}"
        f"{agent_text}\n"
        f"{_MAID_SECTION_END}\n"
    )


def _render_draft_outcome_guidance() -> str:
    return (
        "Draft manifests under `manifests/drafts/` are planning inventory, not "
        "active contracts. Promote one implementation-sized draft into "
        "`manifests/`, implement and review the promoted manifest, then remove "
        "only the matching draft path.\n\n"
        "Always capture an Outcome record after implementation validation and "
        "implementation review, before final handoff. Outcome capture is "
        "required for completed, partial, failed, superseded, archived, or "
        "abandoned MAID work. The Outcome must cite "
        "concrete validation evidence and review notes; it does not replace "
        "behavioral tests, declared artifacts, validation commands, or "
        "implementation review. After Outcome capture, run `uv run maid learn` "
        "to refresh the local `.maid/outcomes.json` advisory index for "
        "subsequent recall. `.maid/outcomes.json` is generated and ignored; "
        "do not commit it. If `maid learn` fails, report the refresh failure "
        "as advisory unless recall or insights are required for the current "
        "task. See `docs/draft-manifest-workflow.md` and "
        "`docs/manifest-outcome-records.md`."
    )
