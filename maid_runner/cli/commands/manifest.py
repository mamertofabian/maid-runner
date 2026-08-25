"""CLI handler for 'maid manifest' command."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
from io import StringIO
import json
from pathlib import Path
import re
import shlex
import sys

from maid_runner.cli.commands._format import print_error
from maid_runner.core.manifest import backfill_manifest_header, prepend_manifest_header

_INACTIVE_METADATA_STATUSES = frozenset(
    {"archive", "archived", "draft", "epic", "legacy", "planning"}
)


def cmd_manifest(args: argparse.Namespace) -> int:
    if not hasattr(args, "manifest_command") or not args.manifest_command:
        print_error("Usage: maid manifest create FILE --goal GOAL")
        return 2
    if args.manifest_command == "create":
        return _cmd_create(args)
    if args.manifest_command == "promote":
        return _cmd_promote(args)
    if args.manifest_command == "from-diff":
        return _cmd_from_diff(args)
    return 2


def _dump_manifest_yaml(data: dict, *, leading_marker: str | None = None) -> str:
    """Render manifest YAML with human-reviewable string styles.

    Multiline strings (descriptions, summaries) render as literal block
    scalars instead of escaped double-quoted scalars, unicode characters
    stay literal, and the wide emitter width keeps long single-line
    strings from being wrapped with backslash continuations. PyYAML falls
    back to a quoted scalar when literal style cannot represent a string
    exactly (for example trailing whitespace on a line), so content is
    never altered for the sake of formatting.
    """
    import yaml

    class _ManifestYamlDumper(yaml.SafeDumper):
        pass

    def _represent_str(dumper: yaml.SafeDumper, value: str):
        if "\n" in value:
            return dumper.represent_scalar("tag:yaml.org,2002:str", value, style="|")
        return dumper.represent_scalar("tag:yaml.org,2002:str", value)

    _ManifestYamlDumper.add_representer(str, _represent_str)
    rendered = yaml.dump(
        data,
        Dumper=_ManifestYamlDumper,
        default_flow_style=False,
        sort_keys=False,
        allow_unicode=True,
        width=4096,
    )
    if leading_marker is not None:
        rendered = f"{leading_marker}\n{rendered}"
    return prepend_manifest_header(rendered)


def _cmd_create(args: argparse.Namespace) -> int:
    from maid_runner.core.types import (
        ArtifactKind,
        ArtifactSpec,
        FileMode,
        FileSpec,
    )

    artifacts = []
    if args.artifacts:
        try:
            for item in json.loads(args.artifacts):
                artifacts.append(
                    ArtifactSpec(
                        kind=ArtifactKind(item["kind"]),
                        name=item["name"],
                        of=item.get("of"),
                    )
                )
        except (json.JSONDecodeError, KeyError, ValueError) as e:
            print_error(f"Invalid artifacts JSON: {e}")
            return 2

    if not artifacts:
        print_error("Manifest create requires at least one artifact.")
        return 2

    temptations = []
    try:
        raw_temptations = getattr(args, "temptations", None) or []
        if len(raw_temptations) > 5:
            raise ValueError("Manifest create accepts at most five temptations.")
        for item in raw_temptations:
            risk, instead = _parse_temptation_arg(item)
            temptations.append({"risk": risk, "instead": instead})
    except ValueError as e:
        print_error(str(e))
        return 2

    file_spec = FileSpec(
        path=args.file_path, mode=FileMode.CREATE, artifacts=tuple(artifacts)
    )

    data = {
        "schema": "2",
        "goal": args.goal,
        "type": args.task_type,
        "created": _current_utc_timestamp(),
        "files": {
            "create": [
                {
                    "path": file_spec.path,
                    "artifacts": [
                        _artifact_to_manifest_dict(a) for a in file_spec.artifacts
                    ],
                }
            ]
        },
        "validate": [_default_validation_command(file_spec.path)],
    }
    if temptations:
        data["temptations"] = temptations

    if not args.dry_run:
        output_dir = Path(getattr(args, "output_dir", "manifests/"))
        output_dir.mkdir(parents=True, exist_ok=True)
        output_path = output_dir / f"{_slugify(args.goal)}.manifest.yaml"
        if output_path.exists():
            print_error(f"Manifest already exists: {output_path}")
            return 2

        leading_marker = (
            "# draft-kind: implementation" if "drafts" in output_dir.parts else None
        )
        output_path.write_text(_dump_manifest_yaml(data, leading_marker=leading_marker))
        if args.json:
            print(json.dumps({"path": str(output_path)}, indent=2))
        else:
            print(f"Created {output_path}")
        return 0

    if args.json:
        print(json.dumps(data, indent=2))
    else:
        import yaml

        print(yaml.dump(data, default_flow_style=False))
    return 0


def _cmd_promote(args: argparse.Namespace) -> int:
    from maid_runner.core.manifest import (
        ManifestLoadError,
        load_manifest_raw,
        validate_manifest_schema,
    )

    manifest_path = Path(args.manifest_path)
    if not manifest_path.exists():
        print_error(f"Manifest not found: {manifest_path}")
        return 2
    if not manifest_path.name.endswith((".manifest.yaml", ".manifest.yml")):
        print_error(
            "Manifest promote only supports *.manifest.yaml and *.manifest.yml files."
        )
        return 2

    output_dir_arg = getattr(args, "output_dir", None)
    if output_dir_arg is None:
        if manifest_path.parent.name != "drafts":
            print_error(
                "Cannot infer the promotion destination because the source "
                "manifest is not directly inside a drafts directory. Pass "
                "--output-dir explicitly."
            )
            return 2
        output_dir = manifest_path.parent.parent
    else:
        output_dir = Path(output_dir_arg)
    output_path = output_dir / manifest_path.name
    if output_path.exists():
        print_error(f"Manifest already exists: {output_path}")
        return 2

    try:
        data = load_manifest_raw(manifest_path)
    except ManifestLoadError as exc:
        print_error(str(exc))
        return 2

    if not isinstance(data, dict):
        print_error("Manifest YAML must be a mapping.")
        return 2
    schema_errors = validate_manifest_schema(data)
    if schema_errors:
        print_error(f"Manifest schema validation failed: {schema_errors[0]}")
        return 2

    project_root = Path(getattr(args, "project_root", "."))
    old_rel = _project_relative(manifest_path, project_root)
    new_rel = _project_relative(output_path, project_root)

    lock_state = _load_promotion_lock(project_root, manifest_path, old_rel)
    if isinstance(lock_state, str):
        print_error(lock_state)
        return 2

    created = _current_utc_timestamp()
    _apply_promotion_mutations(data, old_rel, new_rel, created)
    try:
        promoted_text = _render_promoted_yaml(manifest_path, old_rel, new_rel, created)
    except (OSError, ValueError) as exc:
        print_error(f"Manifest YAML round-trip failed: {exc}")
        return 2
    output_dir.mkdir(parents=True, exist_ok=True)
    output_path.write_text(promoted_text)

    if lock_state is not None:
        lock, lock_path = lock_state
        migration_error = _migrate_promotion_lock(
            lock,
            lock_path,
            output_path,
            project_root,
            old_rel,
            new_rel,
            no_run=bool(getattr(args, "no_run", False)),
        )
        if migration_error is not None:
            output_path.unlink(missing_ok=True)
            print_error(
                f"Plan lock migration failed; promotion rolled back: {migration_error}"
            )
            return 2

    _advisory_backfill_manifest_header(output_path)
    manifest_path.unlink()
    _warn_about_draft_references(output_dir, output_path, old_rel)

    if args.json:
        print(
            json.dumps(
                {"path": str(output_path), "removed": str(manifest_path)},
                indent=2,
            )
        )
    else:
        print(f"Promoted {manifest_path} -> {output_path}")
    return 0


def _advisory_backfill_manifest_header(manifest_path: Path) -> None:
    try:
        backfill_manifest_header(manifest_path)
    except OSError as exc:
        print(
            f"Advisory: could not backfill manifest header for {manifest_path}: {exc}",
            file=sys.stderr,
        )


def _project_relative(path: Path, project_root: Path) -> str:
    try:
        return path.resolve().relative_to(project_root.resolve()).as_posix()
    except ValueError:
        return path.as_posix()


def _load_promotion_lock(project_root: Path, draft_path: Path, old_rel: str):
    """Load the draft's plan lock; a string return is a fail-closed error."""
    from maid_runner.core.manifest import slug_from_path
    from maid_runner.core.plan_lock import (
        PlanLock,
        default_plan_lock_path,
        _PlanLockLoadError,
    )

    lock_path = default_plan_lock_path(project_root, slug_from_path(draft_path))
    if not lock_path.exists():
        return None
    try:
        lock = PlanLock.load(lock_path)
    except _PlanLockLoadError as exc:
        return (
            f"Plan lock at {lock_path} cannot be loaded ({exc.detail}); "
            "refusing to promote a draft with a broken lock."
        )
    if lock.manifest_path != old_rel:
        return (
            f"Plan lock at {lock_path} records manifest_path "
            f"'{lock.manifest_path}', not the draft being promoted "
            f"('{old_rel}'); refusing to promote."
        )
    return lock, lock_path


def _migrate_promotion_lock(
    lock,
    lock_path: Path,
    output_path: Path,
    project_root: Path,
    old_rel: str,
    new_rel: str,
    *,
    no_run: bool,
) -> str | None:
    """Re-lock the promoted manifest; a string return is the failure detail."""
    from dataclasses import replace

    from maid_runner.core.manifest import ManifestLoadError, ManifestSchemaError
    from maid_runner.core.plan_lock import (
        capture_red_phase_evidence,
        revision_preserves_red_evidence,
        revise_plan_lock,
        _load_locked_contract,
    )

    reason = f"Migrated by maid manifest promote: {old_rel} -> {new_rel}"
    try:
        prior_contract = _load_locked_contract(lock_path)
        preserve_red_evidence = (
            lock.red_evidence is not None
            and revision_preserves_red_evidence(
                lock,
                output_path,
                project_root,
                prior_contract,
            )
        )
        migrated = revise_plan_lock(
            lock,
            output_path,
            project_root,
            reason,
            prior_contract=prior_contract,
            preserve_legacy_baseline=no_run,
        )
        if preserve_red_evidence:
            migrated = replace(migrated, red_evidence=lock.red_evidence)
        elif not no_run:
            migrated = replace(
                migrated,
                red_evidence=capture_red_phase_evidence(
                    output_path, project_root
                ).to_payload(),
            )
        migrated.save(lock_path)
    except (ManifestLoadError, ManifestSchemaError, OSError, ValueError) as exc:
        return str(exc)
    return None


def _rewrite_self_validate_paths(data: dict, old_rel: str, new_rel: str) -> None:
    commands = data.get("validate")
    if not isinstance(commands, list):
        return
    for command_index, command in enumerate(commands):
        if isinstance(command, str):
            commands[command_index] = command.replace(old_rel, new_rel)
        elif isinstance(command, list):
            for part_index, part in enumerate(command):
                if part == old_rel:
                    command[part_index] = new_rel


def _apply_promotion_mutations(
    data: dict, old_rel: str, new_rel: str, created: str
) -> None:
    _rewrite_self_validate_paths(data, old_rel, new_rel)
    data["created"] = created
    _clear_inactive_metadata_status(data)


def _render_promoted_yaml(
    manifest_path: Path, old_rel: str, new_rel: str, created: str
) -> str:
    """Render bounded promotion changes while preserving draft presentation."""
    from ruamel.yaml import YAML
    from ruamel.yaml.error import YAMLError
    from ruamel.yaml.scalarstring import FoldedScalarString, LiteralScalarString
    from ruamel.yaml.util import load_yaml_guess_indent

    yaml = YAML()
    yaml.preserve_quotes = True
    yaml.width = 4096
    source_text = manifest_path.read_text()
    try:
        data, sequence_indent, sequence_offset = load_yaml_guess_indent(
            source_text, yaml=yaml
        )
    except YAMLError as exc:
        raise ValueError(str(exc)) from exc
    if not isinstance(data, dict):
        raise ValueError("Manifest YAML must be a mapping.")

    _apply_promotion_mutations(data, old_rel, new_rel, created)
    _render_multiline_strings_as_literal_blocks(
        data,
        LiteralScalarString,
        (LiteralScalarString, FoldedScalarString),
    )
    if sequence_indent is not None:
        yaml.indent(
            mapping=_guess_mapping_indent(source_text),
            sequence=sequence_indent,
            offset=sequence_offset or 0,
        )
    output = StringIO()
    try:
        yaml.dump(data, output)
    except YAMLError as exc:
        raise ValueError(str(exc)) from exc
    return output.getvalue()


def _guess_mapping_indent(source_text: str) -> int:
    candidates = []
    for line in source_text.splitlines():
        stripped = line.lstrip(" ")
        indent = len(line) - len(stripped)
        if indent and not stripped.startswith(("-", "#")) and ":" in stripped:
            candidates.append(indent)
    return min(candidates, default=2)


def _render_multiline_strings_as_literal_blocks(
    value, literal_type, preserved_block_types
) -> None:
    if isinstance(value, dict):
        for key, item in value.items():
            if (
                isinstance(item, str)
                and "\n" in item
                and not isinstance(item, preserved_block_types)
            ):
                value[key] = literal_type(item)
            else:
                _render_multiline_strings_as_literal_blocks(
                    item, literal_type, preserved_block_types
                )
    elif isinstance(value, list):
        for index, item in enumerate(value):
            if (
                isinstance(item, str)
                and "\n" in item
                and not isinstance(item, preserved_block_types)
            ):
                value[index] = literal_type(item)
            else:
                _render_multiline_strings_as_literal_blocks(
                    item, literal_type, preserved_block_types
                )


def _warn_about_draft_references(
    output_dir: Path, output_path: Path, old_rel: str
) -> None:
    import sys

    for candidate in sorted(output_dir.glob("*.manifest.yaml")):
        if candidate == output_path:
            continue
        try:
            text = candidate.read_text()
        except OSError:
            continue
        if old_rel in text:
            print(
                f"Warning: {candidate.name} references the promoted draft path "
                f"{old_rel}; update the reference and run `maid plan revise` "
                "for its lock.",
                file=sys.stderr,
            )


def _cmd_from_diff(args: argparse.Namespace) -> int:
    from maid_runner.core.diff_scope import (
        DiffScopeError,
        collect_diff_scope,
    )
    from maid_runner.core.manifest_from_diff import (
        FromDiffRenderError,
        build_from_diff_manifest,
        default_from_diff_slug,
        validate_from_diff_output_suffix,
        write_from_diff_manifest,
    )

    baseline = _baseline_from_args(args)
    if baseline is None:
        print_error(
            "Changed-scope baseline required: pass the task baseline explicitly; "
            "MAID will not guess main, dev, or a remote branch."
        )
        return 2

    try:
        slug = args.slug or default_from_diff_slug(Path.cwd(), baseline)
        diff = collect_diff_scope(Path.cwd(), baseline)
        output_path = Path(args.output or f"manifests/drafts/{slug}.manifest.yaml")
        if not _is_manifest_draft_path(output_path):
            raise FromDiffRenderError(
                f"Manifest from-diff output must be under manifests/drafts/: {output_path}"
            )
        # Checked here as well as in write_from_diff_manifest because --dry-run
        # returns below without ever reaching the writer, and must not hand back
        # a manifest whose own validate command names a file MAID cannot load.
        validate_from_diff_output_suffix(output_path)
        data = build_from_diff_manifest(diff, Path.cwd(), slug)
        _set_validate_path(data, output_path)

        if args.dry_run:
            if args.json:
                print(json.dumps(data, indent=2))
            else:
                import yaml

                print(yaml.safe_dump(data, default_flow_style=False, sort_keys=False))
            return 0

        path = write_from_diff_manifest(data, output_path, force=args.force)
    except (DiffScopeError, FromDiffRenderError) as exc:
        print_error(str(exc))
        return 2

    if args.json:
        print(json.dumps({"path": str(path)}, indent=2))
    else:
        print(f"Wrote {path}")
    return 0


def _set_validate_path(data: dict, output_path: Path) -> None:
    schema_command = (
        f"maid validate {shlex.quote(_display_output_path(output_path))} "
        "--mode schema --quiet"
    )
    existing = data.get("validate") or []
    suggestions = [
        command for command in existing if not _is_schema_validate_command(command)
    ]
    data["validate"] = suggestions + [schema_command]


def _is_schema_validate_command(command: str) -> bool:
    try:
        parts = shlex.split(command)
    except ValueError:
        return False
    return (
        len(parts) == 6
        and parts[0] == "maid"
        and parts[1] == "validate"
        and parts[3:] == ["--mode", "schema", "--quiet"]
    )


def _display_output_path(output_path: Path) -> str:
    try:
        return output_path.resolve(strict=False).relative_to(Path.cwd()).as_posix()
    except ValueError:
        return output_path.as_posix()


def _is_manifest_draft_path(path: Path) -> bool:
    root = Path.cwd().resolve(strict=False)
    draft_root = (root / "manifests" / "drafts").resolve(strict=False)
    candidate = path if path.is_absolute() else root / path
    try:
        candidate.resolve(strict=False).relative_to(draft_root)
    except ValueError:
        return False
    return True


def _artifact_to_manifest_dict(artifact) -> dict:
    data = {"kind": artifact.kind.value, "name": artifact.name}
    if artifact.of:
        data["of"] = artifact.of
    return data


def _baseline_from_args(args: argparse.Namespace):
    selected = [
        args.since is not None,
        args.base_ref is not None,
        bool(args.worktree),
    ]
    if sum(selected) != 1:
        return None
    from maid_runner.core.diff_scope import DiffScopeBaseline

    if args.worktree:
        return DiffScopeBaseline(source="worktree", commitish=None)
    if args.since is not None:
        return DiffScopeBaseline(source="since", commitish=args.since)
    return DiffScopeBaseline(source="base-ref", commitish=args.base_ref)


def _parse_temptation_arg(value: str) -> tuple[str, str]:
    if "::" not in value:
        raise ValueError("Temptations must use risk::instead format.")
    risk, instead = (part.strip() for part in value.split("::", 1))
    if not risk or not instead:
        raise ValueError("Temptations must include both risk and instead text.")
    return risk, instead


def _default_validation_command(file_path: str) -> str:
    stem = Path(file_path).stem
    return f"pytest tests/test_{stem}.py -v"


def _slugify(value: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")
    return slug or "manifest"


def _clear_inactive_metadata_status(data: dict) -> None:
    metadata = data.get("metadata")
    if not isinstance(metadata, dict):
        return
    status = str(metadata.get("status", "")).strip().lower()
    if status not in _INACTIVE_METADATA_STATUSES:
        return
    merge_sources = getattr(metadata, "merge", None)
    if merge_sources:
        from ruamel.yaml.comments import CommentedMap

        for index, source in enumerate(merge_sources):
            source_status = str(source.get("status", "")).strip().lower()
            if source_status not in _INACTIVE_METADATA_STATUSES:
                continue
            replacement = CommentedMap(
                (key, value) for key, value in source.items() if key != "status"
            )
            if source.fa.flow_style():
                replacement.fa.set_flow_style()
            merge_sources[index] = replacement
            serialized_sources = getattr(merge_sources, "sequence", None)
            if serialized_sources is not None:
                serialized_sources[index] = replacement
    metadata.pop("status", None)
    if not metadata:
        data.pop("metadata", None)


def _current_utc_timestamp() -> str:
    return (
        datetime.now(timezone.utc)
        .replace(microsecond=0)
        .isoformat()
        .replace("+00:00", "Z")
    )
