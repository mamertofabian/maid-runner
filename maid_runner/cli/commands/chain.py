"""CLI handler for 'maid chain' command."""

from __future__ import annotations

import argparse

from maid_runner.cli.commands._format import format_chain_log, print_error


def cmd_chain(args: argparse.Namespace) -> int:
    if args.chain_command != "log":
        print_error(
            f"Unknown chain subcommand: {args.chain_command}",
            json_mode=getattr(args, "json", False),
        )
        return 2

    from maid_runner.core.chain import ManifestChain

    manifest_dir = args.manifest_dir
    try:
        chain = ManifestChain(manifest_dir)
    except FileNotFoundError:
        print_error(
            f"Manifest directory not found: {manifest_dir}",
            json_mode=args.json,
        )
        return 2

    log = chain.event_log()
    output = format_chain_log(
        log,
        str(manifest_dir),
        json_mode=args.json,
        active_only=args.active,
    )
    print(output)
    return 0
