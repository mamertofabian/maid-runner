"""CLI command handler for maid bootstrap."""

from __future__ import annotations

import argparse
import json

from maid_runner.cli.commands._format import format_bootstrap_report, print_error
from maid_runner.core.bootstrap import (
    BootstrapRankReport,
    bootstrap_project,
    rank_bootstrap_candidates,
)


def cmd_bootstrap(args: argparse.Namespace) -> int:
    """Bootstrap MAID for an existing project."""
    json_mode = getattr(args, "json", False)
    quiet = getattr(args, "quiet", False)
    verbose = getattr(args, "verbose", False)

    exclude = set(args.exclude) if args.exclude else None
    respect_gitignore = not getattr(args, "no_gitignore", False)

    try:
        if getattr(args, "rank", False):
            report = rank_bootstrap_candidates(
                args.directory,
                manifest_dir=args.output_dir,
                limit=getattr(args, "limit", 20),
                exclude_patterns=exclude,
                respect_gitignore=respect_gitignore,
            )
            output = _format_rank_report(report, json_mode=json_mode)
            if output:
                print(output)
            return 0

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


def _format_rank_report(
    report: BootstrapRankReport,
    *,
    json_mode: bool = False,
) -> str:
    if json_mode:
        return json.dumps(
            {
                "total_candidates": report.total_candidates,
                "limit": report.limit,
                "candidates": [
                    {
                        "rank": index,
                        "path": candidate.path,
                        "churn": candidate.churn,
                        "inbound_refs": candidate.inbound_refs,
                        "public_artifacts": candidate.public_artifacts,
                    }
                    for index, candidate in enumerate(report.candidates, start=1)
                ],
            },
            indent=2,
        )

    lines = [
        "Ranked bootstrap candidates: "
        f"{len(report.candidates)} of {report.total_candidates}"
    ]
    for index, candidate in enumerate(report.candidates, start=1):
        lines.append(
            f"{index}. {candidate.path} "
            f"(churn={candidate.churn}, "
            f"inbound_refs={candidate.inbound_refs}, "
            f"public_artifacts={candidate.public_artifacts})"
        )
    return "\n".join(lines)
