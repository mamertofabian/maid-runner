"""CLI handler for 'maid chain' command."""

from __future__ import annotations

import argparse

from maid_runner.cli.commands._format import (
    format_chain_log,
    format_replay_result,
    print_error,
)


def cmd_chain(args: argparse.Namespace) -> int:
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

    if args.chain_command == "log":
        return _cmd_chain_log(chain, args)

    if args.chain_command == "replay":
        return _cmd_chain_replay(chain, args)

    print_error(
        f"Unknown chain subcommand: {args.chain_command}",
        json_mode=getattr(args, "json", False),
    )
    return 2


def _cmd_chain_log(chain, args: argparse.Namespace) -> int:
    until_seq = getattr(args, "until_seq", None)
    version_tag = getattr(args, "version_tag", None)

    try:
        log = chain.event_log_until(sequence_number=until_seq, version_tag=version_tag)
    except ValueError as e:
        print_error(str(e), json_mode=args.json)
        return 2

    output = format_chain_log(
        log,
        str(args.manifest_dir),
        json_mode=args.json,
        active_only=args.active,
    )
    print(output)
    return 0


def _cmd_chain_replay(chain, args: argparse.Namespace) -> int:
    until_seq = getattr(args, "until_seq", None)
    version_tag = getattr(args, "version_tag", None)

    try:
        result = chain.replay_until(sequence_number=until_seq, version_tag=version_tag)
    except ValueError as e:
        print_error(str(e), json_mode=args.json)
        return 2

    output = format_replay_result(result, json_mode=args.json)
    print(output)
    return 0
