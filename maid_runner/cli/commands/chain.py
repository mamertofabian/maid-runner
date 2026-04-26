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

    until_seq = getattr(args, "until_seq", None)
    version_tag = getattr(args, "version_tag", None)

    try:
        log = chain.event_log_until(sequence_number=until_seq, version_tag=version_tag)
    except ValueError as e:
        print_error(str(e), json_mode=args.json)
        return 2

    # --active applies after the query filter: remove superseded from the
    # event-log prefix so the result is the active chain at that point.
    output = format_chain_log(
        log,
        str(manifest_dir),
        json_mode=args.json,
        active_only=args.active,
    )
    print(output)
    return 0
