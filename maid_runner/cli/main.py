#!/usr/bin/env python3
"""Main CLI entry point for MAID Runner.

Provides a unified command-line interface with subcommands:
- maid --version
- maid validate ...
- maid snapshot ...
"""

import argparse
import sys

from maid_runner import __version__


def main():
    """Main CLI entry point with subcommands."""
    parser = argparse.ArgumentParser(
        prog="maid",
        description="MAID Runner - Manifest-driven AI Development validation tool",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )

    parser.add_argument(
        "--version",
        action="version",
        version=f"maid-runner {__version__}",
        help="Show version and exit",
    )

    subparsers = parser.add_subparsers(dest="command", help="Available commands")

    # Validate subcommand
    validate_parser = subparsers.add_parser(
        "validate",
        help="Validate manifest against implementation or behavioral test files",
        description="Validate manifest against implementation or behavioral test files",
    )
    validate_parser.add_argument("manifest_path", help="Path to the manifest JSON file")
    validate_parser.add_argument(
        "--validation-mode",
        choices=["implementation", "behavioral"],
        default="implementation",
        help="Validation mode: 'implementation' (default) checks definitions, 'behavioral' checks usage",
    )
    validate_parser.add_argument(
        "--use-manifest-chain",
        action="store_true",
        help="Use manifest chain to merge all related manifests",
    )
    validate_parser.add_argument(
        "--quiet",
        "-q",
        action="store_true",
        help="Only output errors (suppress success messages)",
    )

    # Snapshot subcommand
    snapshot_parser = subparsers.add_parser(
        "snapshot",
        help="Generate MAID snapshot manifests from existing Python files",
        description="Generate MAID snapshot manifests from existing Python files",
    )
    snapshot_parser.add_argument(
        "file_path", help="Path to the Python file to snapshot"
    )
    snapshot_parser.add_argument(
        "--output-dir",
        default="manifests",
        help="Directory to write the manifest (default: manifests)",
    )
    snapshot_parser.add_argument(
        "--force",
        action="store_true",
        help="Overwrite existing manifests without prompting",
    )

    # Test subcommand
    test_parser = subparsers.add_parser(
        "test",
        help="Run validation commands from all non-superseded manifests",
        description="Run validation commands from all non-superseded manifests",
    )
    test_parser.add_argument(
        "--manifest",
        "-m",
        help="Run validation commands for a single manifest (filename relative to manifest-dir or absolute path)",
    )
    test_parser.add_argument(
        "--manifest-dir",
        default="manifests",
        help="Directory containing manifests (default: manifests)",
    )
    test_parser.add_argument(
        "--fail-fast",
        action="store_true",
        help="Stop execution on first failure",
    )
    test_parser.add_argument(
        "--verbose",
        "-v",
        action="store_true",
        help="Show detailed command output",
    )
    test_parser.add_argument(
        "--quiet",
        "-q",
        action="store_true",
        help="Only show summary (suppress per-manifest output)",
    )
    test_parser.add_argument(
        "--timeout",
        type=int,
        default=300,
        help="Command timeout in seconds (default: 300)",
    )

    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        sys.exit(1)

    if args.command == "validate":
        from maid_runner.cli.validate import run_validation

        run_validation(
            args.manifest_path,
            args.validation_mode,
            args.use_manifest_chain,
            args.quiet,
        )
    elif args.command == "snapshot":
        from maid_runner.cli.snapshot import run_snapshot

        run_snapshot(args.file_path, args.output_dir, args.force)
    elif args.command == "test":
        from maid_runner.cli.test import run_test

        run_test(
            args.manifest_dir,
            args.fail_fast,
            args.verbose,
            args.quiet,
            args.timeout,
            args.manifest,
        )
    else:
        parser.print_help()
        sys.exit(1)


if __name__ == "__main__":
    main()
