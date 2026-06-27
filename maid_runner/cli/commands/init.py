"""CLI handler for 'maid init' command."""

from __future__ import annotations

import argparse
import json
import shutil
import sys
from importlib import resources
from pathlib import Path

from maid_runner.instruction_payload import (
    INSTRUCTION_PAYLOAD_VERSION,
    instruction_payload_metadata,
)


_MAID_SECTION_START = "<!-- BEGIN MAID RUNNER -->"
_MAID_SECTION_END = "<!-- END MAID RUNNER -->"
_CHECKED_AGENT_MANIFESTS = {
    "claude": Path(".claude/manifest.json"),
    "codex": Path(".codex/manifest.json"),
}
_PAYLOAD_PATH_PREFIXES = {
    "root": "",
    "agents": "agents",
    "commands": "commands",
    "skills": "skills",
    "skill_agents": "skills",
}
_INIT_WORKFLOW_PAYLOADS = (
    ("docs/draft-manifest-workflow.md", Path("docs/draft-manifest-workflow.md")),
    ("docs/manifest-outcome-records.md", Path("docs/manifest-outcome-records.md")),
    ("manifests/drafts/README.md", Path("manifests/drafts/README.md")),
)


def cmd_init(args: argparse.Namespace) -> int:
    if args.check:
        return _cmd_init_check(args)

    manifest_dir = Path("manifests")
    drafts_dir = manifest_dir / "drafts"
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
        print(f"Would create: {drafts_dir}/")
        print(f"Would create: {config_file}")
        for _, destination in _INIT_WORKFLOW_PAYLOADS:
            print(f"Would create: {destination.as_posix()}")
        if install_claude:
            _print_agent_dry_run("claude", ".claude", "CLAUDE.md")
        if install_codex:
            _print_agent_dry_run("codex", ".codex", "AGENTS.md")
        if install_cursor:
            _print_agent_dry_run("cursor", ".cursor", None)
        return 0

    drafts_dir.mkdir(parents=True, exist_ok=True)

    config_content = (
        "# MAID Runner configuration\n"
        "manifest_dir: manifests/\n"
        "schema_version: 2\n"
        "default_validation_mode: implementation\n"
    )

    config_file.write_text(config_content)
    _install_init_workflow_payloads(Path.cwd())

    if install_claude:
        _install_agent_payload(Path.cwd(), "claude", ".claude", "CLAUDE.md")
    if install_codex:
        _install_agent_payload(Path.cwd(), "codex", ".codex", "AGENTS.md")
    if install_cursor:
        _install_agent_payload(Path.cwd(), "cursor", ".cursor", None)

    print(f"Initialized MAID in {Path.cwd()}")
    print(f"  Created: {manifest_dir}/")
    print(f"  Created: {drafts_dir}/")
    print(f"  Created: {config_file}")
    for _, destination in _INIT_WORKFLOW_PAYLOADS:
        print(f"  Created: {destination.as_posix()}")
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


def _maid_runner_resource(relative_path: str):
    return resources.files("maid_runner").joinpath(*Path(relative_path).parts)


def _install_init_workflow_payloads(project_root: Path) -> None:
    for source_path, destination_path in _INIT_WORKFLOW_PAYLOADS:
        source = _maid_runner_resource(source_path)
        destination = project_root / destination_path
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(source.read_bytes())


def _agent_manifest(tool: str) -> dict:
    manifest = _agent_payload_root(tool).joinpath("manifest.json")
    return json.loads(manifest.read_text())


def _stamp_instruction_payload_metadata(manifest: dict) -> dict:
    stamped = dict(manifest)
    metadata = dict(stamped.get("metadata", {}))
    metadata.update(instruction_payload_metadata())
    stamped["metadata"] = metadata
    return stamped


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
    if tool in _CHECKED_AGENT_MANIFESTS:
        manifest = _stamp_instruction_payload_metadata(manifest)
    payload_files = list(_installable_payload_files(tool, manifest))
    _prune_agent_payload(
        target_dir, _read_existing_agent_manifest(target_dir), manifest
    )
    for source_file, relative_path in payload_files:
        destination = target_dir / relative_path
        destination.parent.mkdir(parents=True, exist_ok=True)
        if relative_path == Path("manifest.json"):
            destination.write_text(json.dumps(manifest, indent=2) + "\n")
        elif tool == "claude" and relative_path == Path("settings.json"):
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
        f"Instruction payload version: {INSTRUCTION_PAYLOAD_VERSION}\n\n"
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
        f"Instruction payload version: {INSTRUCTION_PAYLOAD_VERSION}\n\n"
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
        "active contracts. Child implementation drafts live at "
        "`manifests/drafts/*.manifest.yaml`; epic planning records live at "
        "`manifests/drafts/*.epic.yaml` and use split-before-promote before "
        "implementation; archived draft records are historical inventory. "
        "Before promoting the selected child draft, refresh the Outcome index "
        "when needed and run `uv run maid recall --for-manifest "
        "manifests/drafts/<slug>.manifest.yaml --plan-packet` when completed "
        "Outcome records exist. Recall is advisory planning context only: it "
        "can inform draft hardening and implementation risks, but it does not "
        "expand scope or replace red evidence, behavioral validation, plan "
        "lock, implementation validation, or review. "
        "Use `uv run maid insights` to review recurring Outcome lessons when "
        "an index is available. To intentionally include instructive failed "
        "or abandoned Outcome lessons, refresh the index with "
        "`uv run maid learn --include-status completed --include-status "
        "abandoned`, then recall from that index; the completed-only default "
        "is unchanged. When related Outcome evidence is retrieved, do not dump "
        "a raw recall or insights transcript into the task. Digest it visibly: "
        "name applicable lessons, reject stale or irrelevant lessons with a "
        "reason, and state what changed because of the evidence for the "
        "current planning, implementation, or review phase. Recalled, "
        "aggregated, and digested Outcomes remain advisory planning context "
        "only; they do not create an approval, promotion, done, or review gate. "
        "Promote one selected child draft with "
        "`uv run maid manifest promote manifests/drafts/<slug>.manifest.yaml`. "
        "Do not manually move or copy draft manifests. For metadata-only "
        "reference cleanup on locked active manifests, use "
        '`uv run maid plan revise <manifest> --reason "<text>" '
        "--preserve-red-evidence`. For review-driven behavioral contract "
        "changes after implementation exists, use "
        '`uv run maid plan revise <manifest> --reason "<text>" '
        "--stash-implementation` so MAID temporarily hides declared "
        "implementation changes while it captures fresh red evidence.\n\n"
        "Always capture an Outcome record after implementation validation and "
        "implementation review, before final handoff. Capture Outcome after "
        "implementation review so the result records the reviewed evidence. "
        "Outcome capture is "
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


def _cmd_init_check(args: argparse.Namespace) -> int:
    status = _instruction_payload_status(Path.cwd())
    if args.json:
        print(json.dumps(status))
    else:
        _print_instruction_payload_status(status)
    return 0 if status["status"] == "current" else 1


def _instruction_payload_status(project_root: Path) -> dict:
    installed = {
        tool: _installed_agent_payload_status(project_root, manifest_path)
        for tool, manifest_path in _CHECKED_AGENT_MANIFESTS.items()
    }
    present = [info for info in installed.values() if info["present"]]
    if not present:
        status = "missing"
    elif any(info["status"] != "current" for info in present):
        status = "stale"
    else:
        status = "current"

    metadata = instruction_payload_metadata()
    return {
        "status": status,
        "maid_runner_version": metadata["maid_runner_version"],
        "instruction_payload_version": metadata["instruction_payload_version"],
        "installed": installed,
    }


def _installed_agent_payload_status(project_root: Path, manifest_path: Path) -> dict:
    path = project_root / manifest_path
    if not path.exists():
        return {
            "manifest_path": manifest_path.as_posix(),
            "present": False,
            "instruction_payload_version": None,
            "status": "absent",
        }

    payload_version = _read_installed_payload_version(path)
    return {
        "manifest_path": manifest_path.as_posix(),
        "present": True,
        "instruction_payload_version": payload_version,
        "status": (
            "current" if payload_version == INSTRUCTION_PAYLOAD_VERSION else "stale"
        ),
    }


def _read_installed_payload_version(path: Path) -> str | None:
    try:
        manifest = json.loads(path.read_text())
    except (OSError, json.JSONDecodeError):
        return None
    metadata = manifest.get("metadata")
    if not isinstance(metadata, dict):
        return None
    version = metadata.get("instruction_payload_version")
    return version if isinstance(version, str) else None


def _print_instruction_payload_status(status: dict) -> None:
    print(f"MAID instruction payload status: {status['status']}")
    print(
        "Current instruction payload version: "
        f"{status['instruction_payload_version']}"
    )
    for tool, info in status["installed"].items():
        version = info["instruction_payload_version"]
        suffix = f" ({version})" if version is not None else ""
        print(f"{tool}: {info['status']}{suffix}")
