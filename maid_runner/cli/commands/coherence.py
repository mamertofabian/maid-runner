"""CLI handler for 'maid coherence' command."""

from __future__ import annotations

import argparse

from maid_runner.cli.commands._format import format_coherence_result, print_error


def cmd_coherence(args: argparse.Namespace) -> int:
    from maid_runner.coherence.engine import CoherenceEngine
    from maid_runner.coherence.checks.base import get_checks
    from maid_runner.core.chain import ManifestChain

    try:
        chain = ManifestChain(args.manifest_dir)
    except FileNotFoundError:
        print_error(
            f"Manifest directory not found: {args.manifest_dir}",
            json_mode=args.json,
        )
        return 2

    checks = get_checks()

    # Filter checks if --checks or --exclude specified
    if args.checks:
        include = {c.strip() for c in args.checks.split(",")}
        checks = [c for c in checks if c.name in include]
    if args.exclude:
        exclude = {c.strip() for c in args.exclude.split(",")}
        checks = [c for c in checks if c.name not in exclude]

    engine = CoherenceEngine(checks=checks)
    result = engine.validate(chain)
    print(format_coherence_result(result, json_mode=args.json))
    return 0 if result.success else 1
