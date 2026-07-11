"""CLI handler for 'maid init' command."""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import stat
import sys
import tempfile
from importlib import resources
from pathlib import Path

import yaml
from yaml.nodes import MappingNode, SequenceNode

from maid_runner.instruction_payload import (
    INSTRUCTION_PAYLOAD_VERSION,
    instruction_payload_metadata,
)


_MAID_SECTION_START = "<!-- BEGIN MAID RUNNER -->"
_MAID_SECTION_END = "<!-- END MAID RUNNER -->"
_PRE_COMMIT_CONFIG = Path(".pre-commit-config.yaml")
_PRE_COMMIT_SECTION_START = "# BEGIN MAID RUNNER PRE-COMMIT"
_PRE_COMMIT_SECTION_END = "# END MAID RUNNER PRE-COMMIT"
_PRE_COMMIT_HOOK_ID = "maid-verify"
_PRE_COMMIT_VERIFY_ENTRY = (
    "maid verify --summary --advisory --require-plan-lock --require-red-evidence "
    "--fail-fast --no-changed-scope --file-tracking-scope task "
    "--plan-lock-scope task --since HEAD"
)
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

    try:
        pre_commit_action, pre_commit_content = _prepare_pre_commit_config(
            _PRE_COMMIT_CONFIG
        )
    except ValueError as exc:
        print(f"Pre-commit configuration conflict: {exc}", file=sys.stderr)
        return 1

    if args.dry_run:
        print(f"Would create: {manifest_dir}/")
        print(f"Would create: {drafts_dir}/")
        print(f"Would create: {config_file}")
        for _, destination in _INIT_WORKFLOW_PAYLOADS:
            print(f"Would create: {destination.as_posix()}")
        if pre_commit_action == "create":
            print(f"Would create: {_PRE_COMMIT_CONFIG}")
        elif pre_commit_action == "update":
            print(f"Would update: {_PRE_COMMIT_CONFIG}")
        else:
            print(f"Already current: {_PRE_COMMIT_CONFIG}")
        if install_claude:
            _print_agent_dry_run("claude", ".claude", "CLAUDE.md")
        if install_codex:
            _print_agent_dry_run("codex", ".codex", "AGENTS.md")
        if install_cursor:
            _print_agent_dry_run("cursor", ".cursor", None)
        return 0

    if pre_commit_action != "current":
        try:
            _write_pre_commit_config_atomically(_PRE_COMMIT_CONFIG, pre_commit_content)
        except OSError as exc:
            print(f"Failed to update {_PRE_COMMIT_CONFIG}: {exc}", file=sys.stderr)
            return 1

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
    pre_commit_label = {
        "create": "Created",
        "update": "Updated",
        "current": "Current",
    }[pre_commit_action]
    print(f"  {pre_commit_label}: {_PRE_COMMIT_CONFIG}")
    if install_claude:
        print("  Updated: .claude/")
        print("  Updated: CLAUDE.md")
    if install_codex:
        print("  Updated: .codex/")
        print("  Updated: AGENTS.md")
    if install_cursor:
        print("  Updated: .cursor/")
    print(
        "  Ensure your Git hook runner invokes .pre-commit-config.yaml "
        "(standard setup: pre-commit install)."
    )
    print(
        "  If core.hooksPath is configured, keep its dispatcher and have it "
        "run the project pre-commit configuration."
    )
    return 0


def _prepare_pre_commit_config(path: Path) -> tuple[str, bytes]:
    """Return the write action and complete managed pre-commit config text."""
    if path.is_symlink():
        raise ValueError(f"{path} must not be a symbolic link")
    if not path.exists():
        return "create", ("repos:\n" + _pre_commit_managed_block("\n")).encode()

    try:
        original = path.read_bytes()
        text = original.decode("utf-8")
    except (OSError, UnicodeDecodeError) as exc:
        raise ValueError(f"cannot read {path}: {exc}") from exc

    newline = _pre_commit_newline(text)
    start_matches = _standalone_marker_matches(text, _PRE_COMMIT_SECTION_START)
    end_matches = _standalone_marker_matches(text, _PRE_COMMIT_SECTION_END)
    if (len(start_matches), len(end_matches)) not in {(0, 0), (1, 1)}:
        raise ValueError(
            f"{path} has malformed MAID managed markers; reconcile them manually"
        )

    managed = len(start_matches) == len(end_matches) == 1
    if managed and start_matches[0].start() > end_matches[0].start():
        raise ValueError(
            f"{path} has reversed MAID managed markers; reconcile them manually"
        )

    data, root = _parse_pre_commit_config(text, path)
    hook_count = _maid_verify_hook_count(data)
    if managed:
        start, end = _managed_marker_span(text, start_matches[0], end_matches[0])
        block_data, _ = _parse_pre_commit_config(
            "repos:" + newline + text[start:end], path
        )
        if _maid_verify_hook_count(block_data) != 1 or hook_count != 1:
            raise ValueError(
                f"{path} managed block must contain exactly one {_PRE_COMMIT_HOOK_ID} hook"
            )
        updated_text = _replace_managed_pre_commit_block(text, start, end, newline)
        _validate_prepared_pre_commit_config(updated_text, path)
        updated = updated_text.encode("utf-8")
        return ("current", original) if updated == original else ("update", updated)

    if hook_count:
        raise ValueError(
            f"{path} contains an unmanaged {_PRE_COMMIT_HOOK_ID} hook; "
            "remove it or adopt the MAID managed markers"
        )

    updated_text = _insert_managed_pre_commit_block(text, root, path, newline)
    _validate_prepared_pre_commit_config(updated_text, path)
    return "update", updated_text.encode("utf-8")


def _parse_pre_commit_config(text: str, path: Path) -> tuple[dict, MappingNode]:
    try:
        data = yaml.safe_load(text)
        root = yaml.compose(text)
    except yaml.YAMLError as exc:
        raise ValueError(f"{path} is invalid YAML: {exc}") from exc
    if not isinstance(data, dict) or not isinstance(root, MappingNode):
        raise ValueError(f"{path} must contain a top-level YAML mapping")
    if root.flow_style:
        raise ValueError(
            f"{path} uses a flow-style top-level mapping; convert it to block "
            "style before MAID manages a hook"
        )
    top_level_keys = [key_node.value for key_node, _ in root.value]
    if top_level_keys.count("repos") > 1:
        raise ValueError(f"{path} contains duplicate top-level repos keys")
    if "<<" in top_level_keys:
        raise ValueError(f"{path} cannot supply repos through a YAML merge key")
    for key_node, value_node in root.value:
        if (
            key_node.value == "repos"
            and value_node.start_mark.index < key_node.end_mark.index
        ):
            raise ValueError(f"{path} cannot supply repos through a YAML alias")
    if "repos" in data and not isinstance(data["repos"], list):
        raise ValueError(f"{path} top-level repos value must be a sequence")
    return data, root


def _maid_verify_hook_count(data: dict) -> int:
    count = 0
    for repo in data.get("repos", []):
        if not isinstance(repo, dict):
            continue
        hooks = repo.get("hooks", [])
        if not isinstance(hooks, list):
            continue
        count += sum(
            isinstance(hook, dict) and hook.get("id") == _PRE_COMMIT_HOOK_ID
            for hook in hooks
        )
    return count


def _validate_prepared_pre_commit_config(text: str, path: Path) -> None:
    data, _ = _parse_pre_commit_config(text, path)
    if _maid_verify_hook_count(data) != 1:
        raise ValueError(
            f"generated {path} must contain exactly one {_PRE_COMMIT_HOOK_ID} hook"
        )
    start_count = len(_standalone_marker_matches(text, _PRE_COMMIT_SECTION_START))
    end_count = len(_standalone_marker_matches(text, _PRE_COMMIT_SECTION_END))
    if (start_count, end_count) != (1, 1):
        raise ValueError(f"generated {path} must contain one MAID managed block")


def _pre_commit_managed_block(newline: str) -> str:
    lines = (
        _PRE_COMMIT_SECTION_START,
        "  - repo: local",
        "    hooks:",
        f"      - id: {_PRE_COMMIT_HOOK_ID}",
        "        name: MAID verification (fail-fast handoff gates)",
        f"        entry: {_PRE_COMMIT_VERIFY_ENTRY}",
        "        language: system",
        "        pass_filenames: false",
        "        always_run: true",
        "        stages: [pre-commit]",
        _PRE_COMMIT_SECTION_END,
    )
    return newline.join(lines) + newline


def _pre_commit_newline(text: str) -> str:
    without_crlf = text.replace("\r\n", "")
    return "\r\n" if "\r\n" in text and "\n" not in without_crlf else "\n"


def _standalone_marker_matches(text: str, marker: str) -> list[re.Match[str]]:
    return list(re.finditer(rf"(?m)^{re.escape(marker)}\r?$", text))


def _managed_marker_span(
    text: str, start_match: re.Match[str], end_match: re.Match[str]
) -> tuple[int, int]:
    start = start_match.start()
    end = end_match.end()
    if end < len(text) and text[end : end + 2] == "\r\n":
        end += 2
    elif end < len(text) and text[end] == "\n":
        end += 1
    return start, end


def _replace_managed_pre_commit_block(
    text: str, start: int, end: int, newline: str
) -> str:
    return text[:start] + _pre_commit_managed_block(newline) + text[end:]


def _insert_managed_pre_commit_block(
    text: str, root: MappingNode, path: Path, newline: str
) -> str:
    repos_node = None
    for key_node, value_node in root.value:
        if key_node.value == "repos":
            repos_node = value_node
            break

    block = _pre_commit_managed_block(newline)
    if repos_node is None:
        position = root.end_mark.index
        separator = "" if position == 0 or text[position - 1] == "\n" else newline
        addition = separator + "repos:" + newline + block
        return text[:position] + addition + text[position:]
    if not isinstance(repos_node, SequenceNode):
        raise ValueError(f"{path} top-level repos value must be a sequence")
    if repos_node.flow_style:
        raise ValueError(
            f"{path} uses a flow-style repos sequence; convert it to block "
            "style before MAID manages a hook"
        )

    position = repos_node.end_mark.index
    separator = "" if position == 0 or text[position - 1] == "\n" else newline
    return text[:position] + separator + block + text[position:]


def _write_pre_commit_config_atomically(path: Path, content: bytes) -> None:
    destination = path.absolute()
    if destination.is_symlink():
        raise OSError(f"refusing to replace symbolic link: {path}")
    mode = stat.S_IMODE(destination.stat().st_mode) if destination.exists() else 0o644
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{destination.name}.", suffix=".tmp", dir=destination.parent
    )
    temporary_path = Path(temporary_name)
    try:
        os.fchmod(descriptor, mode)
        with os.fdopen(descriptor, "wb") as temporary:
            descriptor = -1
            temporary.write(content)
            temporary.flush()
            os.fsync(temporary.fileno())
        os.replace(temporary_path, destination)
    finally:
        if descriptor >= 0:
            os.close(descriptor)
        temporary_path.unlink(missing_ok=True)


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
