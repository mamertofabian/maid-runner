"""CLI command handler for maid bootstrap."""

from __future__ import annotations

import argparse

from maid_runner.cli.commands._format import format_bootstrap_report, print_error
from maid_runner.core.bootstrap import bootstrap_project


def cmd_bootstrap(args: argparse.Namespace) -> int:
    """Bootstrap MAID for an existing project."""
    json_mode = getattr(args, "json", False)
    quiet = getattr(args, "quiet", False)
    verbose = getattr(args, "verbose", False)

    exclude = set(args.exclude) if args.exclude else None
    respect_gitignore = not getattr(args, "no_gitignore", False)

    try:
        report = bootstrap_project(
            args.directory,
            manifest_dir=args.output_dir,
            exclude_patterns=exclude,
            respect_gitignore=respect_gitignore,
            include_private=getattr(args, "include_private", False),
            dry_run=getattr(args, "dry_run", False),
        )
    except Exception as e:
        print_error(str(e), json_mode=json_mode)
        return 2

    output = format_bootstrap_report(
        report,
        json_mode=json_mode,
        quiet=quiet,
        verbose=verbose,
    )
    if output:
        print(output)

    return 0
