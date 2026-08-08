"""CLI handler for 'maid init' command."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import secrets
import shutil
import stat
import sys
import tempfile
from dataclasses import dataclass
from importlib import resources
from pathlib import Path, PurePosixPath

import yaml
from yaml.nodes import MappingNode, SequenceNode

from maid_runner.instruction_payload import (
    INSTRUCTION_PAYLOAD_VERSION,
    instruction_payload_metadata,
)
from maid_runner.core.uninstall import UninstallReport


_MAID_SECTION_START = "<!-- BEGIN MAID RUNNER -->"
_MAID_SECTION_END = "<!-- END MAID RUNNER -->"
_PRE_COMMIT_CONFIG = Path(".pre-commit-config.yaml")
_PRE_COMMIT_SECTION_START = "# BEGIN MAID RUNNER PRE-COMMIT"
_PRE_COMMIT_SECTION_END = "# END MAID RUNNER PRE-COMMIT"
_PRE_COMMIT_HOOK_ID = "maid-verify"
_PRE_COMMIT_VERIFY_ARGS = "verify --profile pre-commit --since HEAD"
_GITIGNORE_PATH = Path(".gitignore")
_GITIGNORE_SECTION_START = "# BEGIN MAID RUNNER GENERATED FILES"
_GITIGNORE_SECTION_END = "# END MAID RUNNER GENERATED FILES"
_MAID_GENERATED_IGNORE_PATHS = (
    ".maid/outcomes.json",
    ".maid/outcomes-digest.json",
    ".maid/outcomes-digest.md",
    ".maid/outcomes-enrichment-prompt.json",
    ".maid/run-review-request.json",
    ".maid/run-review.json",
    ".maid/run-reviews/",
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
_INIT_CONFIG_CONTENT = (
    "# MAID Runner configuration\n"
    "manifest_dir: manifests/\n"
    "schema_version: 2\n"
    "default_validation_mode: implementation\n"
).encode()
_AGENT_TARGETS = {
    "claude": (Path(".claude"), Path("CLAUDE.md")),
    "codex": (Path(".codex"), Path("AGENTS.md")),
    "cursor": (Path(".cursor"), None),
}


@dataclass(frozen=True)
class _UninstallOperation:
    path: Path
    replacement: bytes | None = None
    expected_digest: str = ""
    expected_identity: tuple[int, int, int] = (0, 0, 0)
    expected_file_hash: str | None = None


def cmd_init(args: argparse.Namespace) -> int:
    if getattr(args, "uninstall", False):
        return _cmd_init_uninstall(args)
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
    try:
        gitignore_action, gitignore_content = _prepare_gitignore(_GITIGNORE_PATH)
    except ValueError as exc:
        print(f".gitignore configuration conflict: {exc}", file=sys.stderr)
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
        if gitignore_action == "create":
            print(f"Would create: {_GITIGNORE_PATH}")
        elif gitignore_action == "update":
            print(f"Would update: {_GITIGNORE_PATH}")
        else:
            print(f"Already current: {_GITIGNORE_PATH}")
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
    if gitignore_action != "current":
        try:
            _write_pre_commit_config_atomically(_GITIGNORE_PATH, gitignore_content)
        except OSError as exc:
            print(f"Failed to update {_GITIGNORE_PATH}: {exc}", file=sys.stderr)
            return 1

    drafts_dir.mkdir(parents=True, exist_ok=True)

    config_file.write_bytes(_INIT_CONFIG_CONTENT)
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
    gitignore_label = {
        "create": "Created",
        "update": "Updated",
        "current": "Current",
    }[gitignore_action]
    print(f"  {gitignore_label}: {_GITIGNORE_PATH}")
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
    print()
    print("Next steps:")
    print("  maid howto quickstart")
    return 0


def _cmd_init_uninstall(args: argparse.Namespace) -> int:
    tool = getattr(args, "tool", "auto")
    tools = ("claude", "codex", "cursor", "generic") if tool == "auto" else (tool,)
    try:
        report = uninstall_init_payload(Path.cwd(), tools, bool(args.dry_run))
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        print(f"MAID init uninstall failed: {exc}", file=sys.stderr)
        return 1

    if not report.removed and not report.preserved:
        print("No installed MAID init payload found")
        return 0
    verb = "Would remove" if args.dry_run else "Removed"
    for relative in report.removed:
        print(f"{verb}: {relative}")
    for relative in report.preserved:
        print(f"Preserved modified or redirected file: {relative}")
    return 0


def uninstall_init_payload(
    project_root: Path, tools: tuple[str, ...], dry_run: bool
) -> UninstallReport:
    """Remove only preflighted MAID-owned init payloads for selected tools."""
    project_root = Path(project_root).absolute()
    unknown = set(tools) - {*_AGENT_TARGETS, "generic", "windsurf"}
    if unknown:
        raise ValueError(f"unsupported MAID init tool(s): {', '.join(sorted(unknown))}")

    operations: list[_UninstallOperation] = []
    removed: list[str] = []
    preserved: list[str] = []
    missing: list[str] = []

    for tool in tools:
        if tool in _AGENT_TARGETS:
            _plan_agent_uninstall(
                project_root,
                tool,
                operations,
                removed,
                preserved,
                missing,
            )
    if "generic" in tools:
        _plan_generic_uninstall(project_root, operations, removed, preserved, missing)

    report = UninstallReport(
        removed=sorted(set(removed)),
        preserved=sorted(set(preserved)),
        missing=sorted(set(missing)),
    )
    if dry_run:
        return report

    planned = _deduplicate_operations(operations)
    for operation in planned:
        _revalidate_uninstall_operation(project_root, operation)
    for operation in planned:
        _apply_uninstall_operation(project_root, operation)
    return report


def _plan_agent_uninstall(
    project_root: Path,
    tool: str,
    operations: list[_UninstallOperation],
    removed: list[str],
    preserved: list[str],
    missing: list[str],
) -> None:
    target_relative, guidance_relative = _AGENT_TARGETS[tool]
    target_root = project_root / target_relative
    manifest_path = target_root / "manifest.json"
    manifest_label = manifest_path.relative_to(project_root).as_posix()
    if not os.path.lexists(manifest_path):
        missing.append(manifest_label)
    else:
        _assert_no_symlink_boundary(project_root, manifest_path, include_leaf=True)
        try:
            manifest_bytes = manifest_path.read_bytes()
            manifest = json.loads(manifest_bytes)
        except json.JSONDecodeError as exc:
            raise ValueError(f"{manifest_label} contains invalid JSON: {exc}") from exc
        owned_paths = _validated_manifest_payload_paths(manifest, manifest_label)
        for relative in _top_level_owned_paths(owned_paths):
            destination = target_root / relative
            label = destination.relative_to(project_root).as_posix()
            if tool == "claude" and relative == Path("settings.json"):
                _plan_claude_settings_cleanup(
                    destination, label, operations, removed, missing
                )
                continue
            if not os.path.lexists(destination):
                missing.append(label)
                continue
            _assert_no_symlink_boundary(target_root, destination, include_leaf=False)
            operations.append(_new_uninstall_operation(destination))
            removed.append(label)
        operations.append(
            _new_uninstall_operation(manifest_path, expected_source=manifest_bytes)
        )
        removed.append(manifest_label)

    if guidance_relative is not None:
        _plan_marker_cleanup(
            project_root,
            guidance_relative,
            _MAID_SECTION_START,
            _MAID_SECTION_END,
            operations,
            removed,
            missing,
        )


def _plan_generic_uninstall(
    project_root: Path,
    operations: list[_UninstallOperation],
    removed: list[str],
    preserved: list[str],
    missing: list[str],
) -> None:
    canonical_files = [(Path(".maidrc.yaml"), _INIT_CONFIG_CONTENT)]
    canonical_files.extend(
        (destination, _maid_runner_resource(source).read_bytes())
        for source, destination in _INIT_WORKFLOW_PAYLOADS
    )
    for relative, canonical in canonical_files:
        path = project_root / relative
        label = relative.as_posix()
        if not os.path.lexists(path):
            missing.append(label)
        elif path.is_symlink() or not path.is_file() or path.read_bytes() != canonical:
            preserved.append(label)
        else:
            operations.append(_new_uninstall_operation(path, expected_source=canonical))
            removed.append(label)

    _plan_marker_cleanup(
        project_root,
        _PRE_COMMIT_CONFIG,
        _PRE_COMMIT_SECTION_START,
        _PRE_COMMIT_SECTION_END,
        operations,
        removed,
        missing,
    )
    _plan_marker_cleanup(
        project_root,
        _GITIGNORE_PATH,
        _GITIGNORE_SECTION_START,
        _GITIGNORE_SECTION_END,
        operations,
        removed,
        missing,
    )


def _validated_manifest_payload_paths(manifest: object, label: str) -> set[Path]:
    if not isinstance(manifest, dict):
        raise ValueError(f"{label} must contain a JSON object")
    paths: set[Path] = set()
    for section, prefix in _PAYLOAD_PATH_PREFIXES.items():
        section_data = manifest.get(section, {})
        if not isinstance(section_data, dict):
            raise ValueError(f"{label} field {section!r} must be an object")
        distributable = section_data.get("distributable", [])
        if not isinstance(distributable, list) or not all(
            isinstance(item, str) for item in distributable
        ):
            raise ValueError(
                f"{label} field {section}.distributable must be a list of strings"
            )
        for item in distributable:
            relative_text = f"{prefix}/{item}" if prefix else item
            relative = PurePosixPath(relative_text)
            if (
                not item
                or "\\" in item
                or relative.is_absolute()
                or not relative.parts
                or relative == PurePosixPath(".")
                or ".." in relative.parts
                or relative.as_posix() != relative_text
            ):
                raise ValueError(
                    f"{label} contains unsafe or non-normalized path: {item!r}"
                )
            paths.add(Path(*relative.parts))
    return paths


def _top_level_owned_paths(paths: set[Path]) -> list[Path]:
    selected: list[Path] = []
    for path in sorted(paths, key=lambda item: (len(item.parts), item.as_posix())):
        if any(parent == path or parent in path.parents for parent in selected):
            continue
        selected.append(path)
    return selected


def _plan_claude_settings_cleanup(
    path: Path,
    label: str,
    operations: list[_UninstallOperation],
    removed: list[str],
    missing: list[str],
) -> None:
    if not os.path.lexists(path):
        missing.append(label)
        return
    _assert_no_symlink_boundary(path.parent, path, include_leaf=True)
    try:
        source_bytes = path.read_bytes()
        settings = json.loads(source_bytes)
    except json.JSONDecodeError as exc:
        raise ValueError(f"{label} contains invalid JSON: {exc}") from exc
    if not isinstance(settings, dict):
        raise ValueError(f"{label} must contain a JSON object")

    hooks = settings.get("hooks")
    if not isinstance(hooks, dict):
        missing.append(f"{label}#maid-scope-check")
        return
    cleaned_hooks: dict[str, object] = {}
    removed_any = False
    for hook_name, entries in hooks.items():
        if not isinstance(entries, list):
            cleaned_hooks[hook_name] = entries
            continue
        cleaned_entries: list[object] = []
        for entry in entries:
            cleaned, was_removed = _without_maid_scope_check_hooks(entry)
            removed_any = removed_any or was_removed
            if cleaned is not None:
                cleaned_entries.append(cleaned)
        if cleaned_entries or not entries:
            cleaned_hooks[hook_name] = cleaned_entries
    if not removed_any:
        missing.append(f"{label}#maid-scope-check")
        return
    cleaned_settings = dict(settings)
    if cleaned_hooks:
        cleaned_settings["hooks"] = cleaned_hooks
    else:
        cleaned_settings.pop("hooks", None)
    operations.append(
        _new_uninstall_operation(
            path,
            (json.dumps(cleaned_settings, indent=2) + "\n").encode(),
            expected_source=source_bytes,
        )
    )
    removed.append(f"{label}#maid-scope-check")


def _plan_marker_cleanup(
    project_root: Path,
    relative: Path,
    start_marker: str,
    end_marker: str,
    operations: list[_UninstallOperation],
    removed: list[str],
    missing: list[str],
) -> None:
    path = project_root / relative
    label = relative.as_posix()
    if not os.path.lexists(path):
        missing.append(f"{label}#maid-managed-block")
        return
    _assert_no_symlink_boundary(project_root, path, include_leaf=True)
    try:
        original = path.read_bytes()
        text = original.decode("utf-8")
    except (OSError, UnicodeDecodeError) as exc:
        raise ValueError(f"cannot read managed markers in {label}: {exc}") from exc
    starts = _standalone_marker_matches(text, start_marker)
    ends = _standalone_marker_matches(text, end_marker)
    if not starts and not ends:
        missing.append(f"{label}#maid-managed-block")
        return
    if len(starts) != 1 or len(ends) != 1 or starts[0].start() > ends[0].start():
        raise ValueError(f"{label} has malformed MAID managed markers")
    start, end = _managed_marker_span(text, starts[0], ends[0])
    updated = text[:start] + text[end:]
    operations.append(
        _new_uninstall_operation(
            path, updated.encode("utf-8"), expected_source=original
        )
    )
    removed.append(f"{label}#maid-managed-block")


def _assert_no_symlink_boundary(
    root: Path, target: Path, *, include_leaf: bool
) -> None:
    try:
        relative = target.relative_to(root)
    except ValueError as exc:
        raise ValueError(f"unsafe uninstall target outside {root}: {target}") from exc
    current = root
    components = relative.parts if include_leaf else relative.parts[:-1]
    if current.is_symlink():
        raise ValueError(f"refusing to cross symlink boundary: {current}")
    for component in components:
        current = current / component
        if current.is_symlink():
            raise ValueError(f"refusing to cross symlink boundary: {current}")


def _deduplicate_operations(
    operations: list[_UninstallOperation],
) -> list[_UninstallOperation]:
    by_path: dict[Path, _UninstallOperation] = {}
    for operation in operations:
        previous = by_path.get(operation.path)
        if previous is not None and previous != operation:
            raise ValueError(f"conflicting uninstall operations for {operation.path}")
        by_path[operation.path] = operation
    return sorted(
        by_path.values(),
        key=lambda operation: (-len(operation.path.parts), operation.path.as_posix()),
    )


def _new_uninstall_operation(
    path: Path,
    replacement: bytes | None = None,
    *,
    expected_source: bytes | None = None,
) -> _UninstallOperation:
    if expected_source is not None:
        before = path.lstat()
        current = path.read_bytes()
        after = path.lstat()
        before_state = (
            before.st_dev,
            before.st_ino,
            before.st_mode,
            before.st_size,
            before.st_mtime_ns,
        )
        after_state = (
            after.st_dev,
            after.st_ino,
            after.st_mode,
            after.st_size,
            after.st_mtime_ns,
        )
        if current != expected_source or before_state != after_state:
            raise ValueError(f"{path} changed while uninstall was planning")
        stat_result = after
        expected_digest = _single_file_digest(stat_result, expected_source)
        expected_file_hash = hashlib.sha256(expected_source).hexdigest()
    else:
        stat_result = path.lstat()
        expected_digest = _path_digest(path)
        expected_file_hash = (
            hashlib.sha256(path.read_bytes()).hexdigest()
            if path.is_file() and not path.is_symlink()
            else None
        )
    return _UninstallOperation(
        path=path,
        replacement=replacement,
        expected_digest=expected_digest,
        expected_identity=(stat_result.st_dev, stat_result.st_ino, stat_result.st_mode),
        expected_file_hash=expected_file_hash,
    )


def _single_file_digest(stat_result: os.stat_result, content: bytes) -> str:
    digest = hashlib.sha256()
    digest.update(b".")
    digest.update(str(stat.S_IFMT(stat_result.st_mode)).encode())
    digest.update(content)
    return digest.hexdigest()


def _path_digest(path: Path) -> str:
    digest = hashlib.sha256()

    def add_entry(entry: Path, relative: str) -> None:
        stat_result = entry.lstat()
        digest.update(relative.encode("utf-8", errors="surrogateescape"))
        digest.update(str(stat.S_IFMT(stat_result.st_mode)).encode())
        if entry.is_symlink():
            digest.update(os.readlink(entry).encode("utf-8", errors="surrogateescape"))
        elif entry.is_file():
            digest.update(entry.read_bytes())

    add_entry(path, ".")
    if path.is_dir() and not path.is_symlink():
        for current_root, directory_names, file_names in os.walk(
            path, followlinks=False
        ):
            directory_names.sort()
            file_names.sort()
            current = Path(current_root)
            for name in [*directory_names, *file_names]:
                entry = current / name
                add_entry(entry, entry.relative_to(path).as_posix())
    return digest.hexdigest()


def _revalidate_uninstall_operation(
    project_root: Path, operation: _UninstallOperation
) -> None:
    try:
        _assert_no_symlink_boundary(
            project_root,
            operation.path,
            include_leaf=operation.replacement is not None,
        )
        stat_result = operation.path.lstat()
        identity = (stat_result.st_dev, stat_result.st_ino, stat_result.st_mode)
        digest = _path_digest(operation.path)
    except (OSError, ValueError) as exc:
        raise ValueError(
            f"{operation.path} changed after uninstall planning: {exc}"
        ) from exc
    if identity != operation.expected_identity or digest != operation.expected_digest:
        raise ValueError(f"{operation.path} changed after uninstall planning")


def _apply_uninstall_operation(
    project_root: Path, operation: _UninstallOperation
) -> None:
    _revalidate_uninstall_operation(project_root, operation)
    if not _supports_descriptor_relative_mutation():
        raise OSError(
            "safe descriptor-relative uninstall is unavailable on this platform; "
            "refusing pathname-based mutation"
        )
    parent_fd, name = _open_parent_directory(project_root, operation.path)
    try:
        stat_result = os.stat(name, dir_fd=parent_fd, follow_symlinks=False)
        identity = (stat_result.st_dev, stat_result.st_ino, stat_result.st_mode)
        if identity != operation.expected_identity:
            raise ValueError(f"{operation.path} changed after uninstall planning")
        if operation.replacement is None:
            if stat.S_ISDIR(stat_result.st_mode):
                shutil.rmtree(name, dir_fd=parent_fd)
            else:
                os.unlink(name, dir_fd=parent_fd)
        else:
            _replace_file_at_descriptor(
                parent_fd,
                name,
                operation.path,
                operation.replacement,
                operation.expected_file_hash,
            )
    finally:
        os.close(parent_fd)


def _supports_descriptor_relative_mutation() -> bool:
    return (
        os.open in os.supports_dir_fd
        and os.stat in os.supports_dir_fd
        and os.unlink in os.supports_dir_fd
        and os.rename in os.supports_dir_fd
        and bool(getattr(shutil.rmtree, "avoids_symlink_attacks", False))
    )


def _open_parent_directory(project_root: Path, target: Path) -> tuple[int, str]:
    relative = target.relative_to(project_root)
    flags = os.O_RDONLY | getattr(os, "O_DIRECTORY", 0) | getattr(os, "O_NOFOLLOW", 0)
    descriptor = os.open(project_root, flags)
    try:
        for component in relative.parts[:-1]:
            child = os.open(component, flags, dir_fd=descriptor)
            os.close(descriptor)
            descriptor = child
        return descriptor, relative.name
    except BaseException:
        os.close(descriptor)
        raise


def _replace_file_at_descriptor(
    parent_fd: int,
    name: str,
    path: Path,
    content: bytes,
    expected_file_hash: str | None,
) -> None:
    source_fd = os.open(
        name,
        os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0),
        dir_fd=parent_fd,
    )
    try:
        current = b""
        initial_stat = os.fstat(source_fd)
        while chunk := os.read(source_fd, 65536):
            current += chunk
        after_read_stat = os.fstat(source_fd)
        if (
            after_read_stat.st_size != initial_stat.st_size
            or after_read_stat.st_mtime_ns != initial_stat.st_mtime_ns
        ):
            raise ValueError(f"{path} changed after uninstall planning")
        if (
            expected_file_hash is None
            or hashlib.sha256(current).hexdigest() != expected_file_hash
        ):
            raise ValueError(f"{path} changed after uninstall planning")
        mode = stat.S_IMODE(initial_stat.st_mode)
    finally:
        os.close(source_fd)

    temporary_name = f".{name}.{os.getpid()}.{secrets.token_hex(6)}.maid-uninstall.tmp"
    temporary_fd = os.open(
        temporary_name,
        os.O_WRONLY | os.O_CREAT | os.O_EXCL,
        mode,
        dir_fd=parent_fd,
    )
    try:
        os.fchmod(temporary_fd, mode)
        view = memoryview(content)
        while view:
            written = os.write(temporary_fd, view)
            view = view[written:]
        os.fsync(temporary_fd)
    finally:
        os.close(temporary_fd)
    try:
        current_stat = os.stat(name, dir_fd=parent_fd, follow_symlinks=False)
        current_identity = (
            current_stat.st_dev,
            current_stat.st_ino,
            current_stat.st_mode,
            current_stat.st_size,
            current_stat.st_mtime_ns,
        )
        initial_identity = (
            initial_stat.st_dev,
            initial_stat.st_ino,
            initial_stat.st_mode,
            initial_stat.st_size,
            initial_stat.st_mtime_ns,
        )
        if current_identity != initial_identity:
            raise ValueError(f"{path} changed after uninstall planning")
        os.rename(
            temporary_name,
            name,
            src_dir_fd=parent_fd,
            dst_dir_fd=parent_fd,
        )
    finally:
        try:
            os.unlink(temporary_name, dir_fd=parent_fd)
        except FileNotFoundError:
            pass


def _prepare_pre_commit_config(path: Path) -> tuple[str, bytes]:
    """Return the write action and complete managed pre-commit config text."""
    if path.is_symlink():
        raise ValueError(f"{path} must not be a symbolic link")
    if not path.exists():
        return (
            "create",
            (
                "repos:\n"
                + _pre_commit_managed_block("\n", _maid_verify_entry(path.parent))
            ).encode(),
        )

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
        updated_text = _replace_managed_pre_commit_block(
            text, start, end, newline, _maid_verify_entry(path.parent)
        )
        _validate_prepared_pre_commit_config(updated_text, path)
        updated = updated_text.encode("utf-8")
        return ("current", original) if updated == original else ("update", updated)

    if hook_count:
        raise ValueError(
            f"{path} contains an unmanaged {_PRE_COMMIT_HOOK_ID} hook; "
            "remove it or adopt the MAID managed markers"
        )

    updated_text = _insert_managed_pre_commit_block(
        text, root, path, newline, _maid_verify_entry(path.parent)
    )
    _validate_prepared_pre_commit_config(updated_text, path)
    return "update", updated_text.encode("utf-8")


def _prepare_gitignore(path: Path) -> tuple[str, bytes]:
    """Return an idempotent update containing MAID-generated advisory paths."""
    if path.is_symlink():
        raise ValueError(f"{path} must not be a symbolic link")
    if path.exists():
        try:
            original = path.read_bytes()
            text = original.decode("utf-8")
        except (OSError, UnicodeDecodeError) as exc:
            raise ValueError(f"cannot read {path}: {exc}") from exc
    else:
        original = b""
        text = ""

    start_matches = _standalone_marker_matches(text, _GITIGNORE_SECTION_START)
    end_matches = _standalone_marker_matches(text, _GITIGNORE_SECTION_END)
    if (len(start_matches), len(end_matches)) not in {(0, 0), (1, 1)}:
        raise ValueError(
            f"{path} has malformed MAID generated-file markers; reconcile them manually"
        )
    if start_matches and start_matches[0].start() > end_matches[0].start():
        raise ValueError(
            f"{path} has reversed MAID generated-file markers; reconcile them manually"
        )

    newline = _pre_commit_newline(text)
    block = newline.join(
        (
            _GITIGNORE_SECTION_START,
            *_MAID_GENERATED_IGNORE_PATHS,
            _GITIGNORE_SECTION_END,
            "",
        )
    )
    if start_matches:
        start, end = _managed_marker_span(text, start_matches[0], end_matches[0])
        updated = text[:start] + block + text[end:]
    else:
        separator = "" if not text or text.endswith(("\n", "\r")) else newline
        blank = newline if text else ""
        updated = text + separator + blank + block
    if updated.encode("utf-8") == original:
        return "current", original
    return ("update" if path.exists() else "create"), updated.encode("utf-8")


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


def _maid_verify_entry(project_root: Path) -> str:
    launcher = (
        "scripts/maid" if (project_root / "scripts" / "maid").is_file() else "maid"
    )
    return f"{launcher} {_PRE_COMMIT_VERIFY_ARGS}"


def _pre_commit_managed_block(newline: str, entry: str) -> str:
    lines = (
        _PRE_COMMIT_SECTION_START,
        "  - repo: local",
        "    hooks:",
        f"      - id: {_PRE_COMMIT_HOOK_ID}",
        "        name: MAID verification (fail-fast handoff gates)",
        f"        entry: {entry}",
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
    text: str, start: int, end: int, newline: str, entry: str
) -> str:
    return text[:start] + _pre_commit_managed_block(newline, entry) + text[end:]


def _insert_managed_pre_commit_block(
    text: str, root: MappingNode, path: Path, newline: str, entry: str
) -> str:
    repos_node = None
    for key_node, value_node in root.value:
        if key_node.value == "repos":
            repos_node = value_node
            break

    block = _pre_commit_managed_block(newline, entry)
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
            packaged_settings = json.loads(source_file.read_text())
            _merge_claude_settings(
                destination,
                _settings_for_project_launcher(packaged_settings, project_root),
            )
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
            if _contains_maid_scope_check_hook(packaged_entry):
                cleaned_entries = (
                    _without_maid_scope_check_hooks(entry) for entry in existing_entries
                )
                existing_entries = [
                    entry for entry, _removed in cleaned_entries if entry is not None
                ]
            if packaged_entry not in existing_entries:
                existing_entries.append(packaged_entry)
        merged_hooks[hook_name] = existing_entries
    merged["hooks"] = merged_hooks
    destination.write_text(json.dumps(merged, indent=2) + "\n")


def _contains_maid_scope_check_hook(value: object) -> bool:
    if isinstance(value, dict):
        command = value.get("command")
        if _is_maid_scope_check_command(command):
            return True
        return any(_contains_maid_scope_check_hook(child) for child in value.values())
    if isinstance(value, list):
        return any(_contains_maid_scope_check_hook(child) for child in value)
    return False


def _without_maid_scope_check_hooks(value: object) -> tuple[object | None, bool]:
    if isinstance(value, dict):
        if _is_maid_scope_check_command(value.get("command")):
            return None, True
        cleaned: dict = {}
        removed_from_hooks = False
        for key, child in value.items():
            cleaned_child, removed = _without_maid_scope_check_hooks(child)
            if cleaned_child is not None:
                cleaned[key] = cleaned_child
            if key == "hooks" and removed:
                removed_from_hooks = True
        if removed_from_hooks and not cleaned.get("hooks"):
            return None, True
        return cleaned, removed_from_hooks
    if isinstance(value, list):
        cleaned_items: list[object] = []
        removed_any = False
        for child in value:
            cleaned_child, removed = _without_maid_scope_check_hooks(child)
            removed_any = removed_any or removed
            if cleaned_child is not None:
                cleaned_items.append(cleaned_child)
        return cleaned_items, removed_any
    return value, False


def _is_maid_scope_check_command(value: object) -> bool:
    return value in {
        "maid hook scope-check --stdin",
        "./scripts/maid hook scope-check --stdin",
    }


def _settings_for_project_launcher(settings: dict, project_root: Path) -> dict:
    """Route packaged MAID hook commands through a repository launcher if present."""
    if not (project_root / "scripts" / "maid").is_file():
        return settings

    transformed = json.loads(json.dumps(settings))

    def rewrite(value: object) -> None:
        if isinstance(value, dict):
            if value.get("command") == "maid hook scope-check --stdin":
                value["command"] = "./scripts/maid hook scope-check --stdin"
            for child in value.values():
                rewrite(child)
        elif isinstance(value, list):
            for child in value:
                rewrite(child)

    rewrite(transformed)
    return transformed


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
        f"{_render_validator_plugin_guidance()}"
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
        f"{_render_validator_plugin_guidance()}"
        f"{_render_draft_outcome_guidance()}"
        f"{agent_text}\n"
        f"{_MAID_SECTION_END}\n"
    )


def _render_validator_plugin_guidance() -> str:
    return (
        "Before treating a file's language as unsupported, run "
        "`maid validators` and install a matching validator plugin when "
        "available instead of skipping MAID for that file.\n\n"
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
        f"Current instruction payload version: {status['instruction_payload_version']}"
    )
    for tool, info in status["installed"].items():
        version = info["instruction_payload_version"]
        suffix = f" ({version})" if version is not None else ""
        print(f"{tool}: {info['status']}{suffix}")
