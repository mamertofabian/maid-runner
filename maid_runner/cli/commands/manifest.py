"""CLI handler for 'maid manifest' command."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import re

from maid_runner.cli.commands._format import print_error


def cmd_manifest(args: argparse.Namespace) -> int:
    if not hasattr(args, "manifest_command") or not args.manifest_command:
        print_error("Usage: maid manifest create FILE --goal GOAL")
        return 2
    if args.manifest_command == "create":
        return _cmd_create(args)
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

    file_spec = FileSpec(
        path=args.file_path, mode=FileMode.CREATE, artifacts=tuple(artifacts)
    )

    data = {
        "schema": "2",
        "goal": args.goal,
        "type": args.task_type,
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


def _artifact_to_manifest_dict(artifact) -> dict:
    data = {"kind": artifact.kind.value, "name": artifact.name}
    if artifact.of:
        data["of"] = artifact.of
    return data


def _default_validation_command(file_path: str) -> str:
    stem = Path(file_path).stem
    return f"pytest tests/test_{stem}.py -v"


def _slugify(value: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")
    return slug or "manifest"
