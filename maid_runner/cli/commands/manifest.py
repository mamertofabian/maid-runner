"""CLI handler for 'maid manifest' command."""

from __future__ import annotations

import argparse
import json

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
        except (json.JSONDecodeError, KeyError) as e:
            print_error(f"Invalid artifacts JSON: {e}")
            return 2

    file_spec = FileSpec(
        path=args.file_path, mode=FileMode.CREATE, artifacts=tuple(artifacts)
    )

    if not args.dry_run:
        print_error("Non-dry-run manifest creation not yet implemented.")
        return 2

    data = {
        "schema": "2",
        "goal": args.goal,
        "type": args.task_type,
        "files": {
            "create": [
                {
                    "path": file_spec.path,
                    "artifacts": [
                        {"kind": a.kind.value, "name": a.name}
                        for a in file_spec.artifacts
                    ],
                }
            ]
        },
        "validate": [],
    }
    if args.json:
        print(json.dumps(data, indent=2))
    else:
        import yaml

        print(yaml.dump(data, default_flow_style=False))
    return 0
