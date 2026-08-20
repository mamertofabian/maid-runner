"""CLI handler for 'maid test' command."""

from __future__ import annotations

import argparse

from maid_runner.cli.commands._format import format_test_result, print_error


def cmd_test(args: argparse.Namespace) -> int:
    from maid_runner.core.test_runner import run_manifest_tests, run_tests

    try:
        from maid_runner.core.config import load_config

        batch = getattr(args, "batch", None)
        config = load_config(".").test_execution
        jobs_explicit = getattr(args, "jobs_explicit", None)
        jobs = (
            config.command_jobs if jobs_explicit is False else getattr(args, "jobs", 1)
        )
        workers_explicit = getattr(args, "pytest_workers_explicit", None)
        pytest_workers = (
            None if workers_explicit is False else getattr(args, "pytest_workers", None)
        )
        if args.manifest:
            result = run_manifest_tests(
                args.manifest,
                fail_fast=args.fail_fast,
                pytest_workers=pytest_workers,
            )
        else:
            result = run_tests(
                manifest_dir=args.manifest_dir,
                fail_fast=args.fail_fast,
                batch=batch,
                jobs=jobs,
                pytest_workers=pytest_workers,
            )
        print(format_test_result(result, verbose=args.verbose, json_mode=args.json))
        return 0 if result.success else 1
    except Exception as e:
        print_error(str(e), json_mode=args.json)
        return 2
