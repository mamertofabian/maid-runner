"""CLI handler for 'maid files' and 'maid manifests' commands."""

from __future__ import annotations

import argparse

from maid_runner.cli.commands._format import (
    format_file_tracking,
    format_manifests_list,
    print_error,
)


def cmd_files(args: argparse.Namespace) -> int:
    from maid_runner.core.chain import ManifestChain
    from maid_runner.core.validate import ValidationEngine

    try:
        engine = ValidationEngine(project_root=".")
        chain = ManifestChain(args.manifest_dir, ".")
        report = engine.run_file_tracking(chain)
        print(
            format_file_tracking(
                report, json_mode=args.json, hide_private=args.hide_private
            )
        )
        return 0
    except Exception as e:
        print_error(str(e), json_mode=args.json)
        return 2


def cmd_manifests(args: argparse.Namespace) -> int:
    from maid_runner.core.chain import ManifestChain

    try:
        chain = ManifestChain(args.manifest_dir, ".")
        manifests = chain.manifests_for_file(args.file_path)
        print(
            format_manifests_list(
                manifests, args.file_path, json_mode=args.json, quiet=args.quiet
            )
        )
        return 0
    except Exception as e:
        print_error(str(e), json_mode=args.json)
        return 2
