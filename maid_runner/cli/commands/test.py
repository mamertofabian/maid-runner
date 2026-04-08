"""CLI handler for 'maid test' command."""

from __future__ import annotations

import argparse

from maid_runner.cli.commands._format import format_test_result, print_error


def cmd_test(args: argparse.Namespace) -> int:
    from maid_runner.core.test_runner import run_manifest_tests, run_tests

    try:
        batch = getattr(args, "batch", None)
        if args.manifest:
            result = run_manifest_tests(args.manifest, fail_fast=args.fail_fast)
        else:
            result = run_tests(
                manifest_dir=args.manifest_dir,
                fail_fast=args.fail_fast,
                batch=False if batch is None else batch,
            )
        print(format_test_result(result, verbose=args.verbose, json_mode=args.json))
        return 0 if result.success else 1
    except Exception as e:
        print_error(str(e), json_mode=args.json)
        return 2
