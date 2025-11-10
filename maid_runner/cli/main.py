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
from maid_runner.cli import snapshot, validate


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

    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        sys.exit(1)

    if args.command == "validate":
        # Build arguments for validate command
        validate_argv = [args.manifest_path]
        if args.validation_mode != "implementation":
            validate_argv.extend(["--validation-mode", args.validation_mode])
        if args.use_manifest_chain:
            validate_argv.append("--use-manifest-chain")
        if args.quiet:
            validate_argv.append("--quiet")

        # Temporarily replace sys.argv for validate.main()
        old_argv = sys.argv
        sys.argv = ["validate"] + validate_argv
        try:
            validate.main()
        finally:
            sys.argv = old_argv
    elif args.command == "snapshot":
        # Build arguments for snapshot command
        snapshot_argv = [args.file_path]
        if args.output_dir != "manifests":
            snapshot_argv.extend(["--output-dir", args.output_dir])
        if args.force:
            snapshot_argv.append("--force")

        # Temporarily replace sys.argv for snapshot.main()
        old_argv = sys.argv
        sys.argv = ["snapshot"] + snapshot_argv
        try:
            snapshot.main()
        finally:
            sys.argv = old_argv
    else:
        parser.print_help()
        sys.exit(1)


if __name__ == "__main__":
    main()
