"""CLI handler for 'maid manifest' command."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import re

from maid_runner.cli.commands._format import print_error

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
    return 2


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

        import yaml

        output_path.write_text(
            yaml.dump(data, default_flow_style=False, sort_keys=False)
        )
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
    import yaml

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

    output_dir = Path(getattr(args, "output_dir", "manifests/"))
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

    data["created"] = _current_utc_timestamp()
    _clear_inactive_metadata_status(data)
    output_dir.mkdir(parents=True, exist_ok=True)
    output_path.write_text(yaml.dump(data, default_flow_style=False, sort_keys=False))
    manifest_path.unlink()

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


def _artifact_to_manifest_dict(artifact) -> dict:
    data = {"kind": artifact.kind.value, "name": artifact.name}
    if artifact.of:
        data["of"] = artifact.of
    return data


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
