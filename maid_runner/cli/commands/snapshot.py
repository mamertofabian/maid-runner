"""CLI handler for 'maid snapshot' and 'maid snapshot-system' commands."""

from __future__ import annotations

import argparse
import json

from maid_runner.cli.commands._format import print_error


def cmd_snapshot(args: argparse.Namespace) -> int:
    try:
        from maid_runner.core.snapshot import generate_snapshot, save_snapshot
    except ImportError:
        print_error("Snapshot module not available.")
        return 2

    try:
        manifest = generate_snapshot(args.file_path)
        if args.dry_run:
            from maid_runner.core.manifest import _manifest_to_dict

            data = _manifest_to_dict(manifest)
            if args.json:
                print(json.dumps(data, indent=2))
            else:
                import yaml

                print(yaml.dump(data, default_flow_style=False, sort_keys=False))
            return 0
        path = save_snapshot(manifest, output_dir=args.output_dir, output=args.output)
        print(f"Snapshot saved to {path}")
        return 0
    except Exception as e:
        print_error(str(e))
        return 2


def cmd_snapshot_system(args: argparse.Namespace) -> int:
    try:
        from maid_runner.core.snapshot import generate_system_snapshot, save_snapshot
    except ImportError:
        print_error("Snapshot module not available.")
        return 2

    try:
        manifest = generate_system_snapshot(manifest_dir=args.manifest_dir)
        if args.output:
            path = save_snapshot(manifest, output=args.output)
            if not args.quiet:
                print(f"System snapshot saved to {path}")
        else:
            if not args.quiet:
                from maid_runner.core.manifest import _manifest_to_dict

                data = _manifest_to_dict(manifest)
                if getattr(args, "json", False):
                    print(json.dumps(data, indent=2))
                else:
                    import yaml

                    print(yaml.dump(data, default_flow_style=False, sort_keys=False))
        return 0
    except Exception as e:
        print_error(str(e))
        return 2
