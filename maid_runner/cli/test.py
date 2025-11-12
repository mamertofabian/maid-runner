#!/usr/bin/env python3
"""Command-line interface for running MAID validation commands.

This script discovers all manifests, filters out superseded ones, and executes
their validation commands, providing aggregate results.
"""

import argparse
import json
import subprocess
import sys
from pathlib import Path
from typing import Optional

from maid_runner.utils import (
    get_superseded_manifests,
    normalize_validation_commands,
    print_maid_not_enabled_message,
    print_no_manifests_found_message,
    validate_manifest_version,
)


def execute_validation_commands(
    manifest_path: Path,
    manifest_data: dict,
    timeout: int,
    verbose: bool,
    project_root: Path,
) -> tuple:
    """Execute validation commands for a single manifest.

    Args:
        manifest_path: Path to the manifest file
        manifest_data: Dictionary containing manifest data
        timeout: Command timeout in seconds
        verbose: If True, show detailed command output
        project_root: Project root directory (parent of manifests dir) where commands should be executed

    Returns:
        tuple: (passed_count, failed_count, total_count)
    """
    validation_commands = normalize_validation_commands(manifest_data)

    if not validation_commands:
        return (0, 0, 0)

    passed = 0
    failed = 0
    total = len(validation_commands)

    # Get project directory name for path normalization
    project_name = project_root.name

    # Set up environment
    import os

    env_additions = os.environ.copy()

    # Add current project root to PYTHONPATH to ensure local imports work
    current_pythonpath = env_additions.get("PYTHONPATH", "")
    pythonpath_additions = [str(project_root)]
    if current_pythonpath:
        pythonpath_additions.append(current_pythonpath)
    env_additions["PYTHONPATH"] = ":".join(pythonpath_additions)

    # Check if we should auto-prefix pytest commands with 'uv run'
    # Only do this if project has pyproject.toml (uv project)
    pyproject_path = project_root / "pyproject.toml"
    auto_prefix_uv_run = pyproject_path.exists()

    for i, cmd in enumerate(validation_commands):
        if not cmd:
            continue

        # Normalize command paths: strip redundant project directory prefix if needed
        # This handles cases where paths might have redundant directory prefixes
        normalized_cmd = []
        for arg in cmd:
            # Only normalize if the path doesn't exist as-is and starts with project name
            if "/" in arg and arg.startswith(f"{project_name}/"):
                # Check if removing the prefix would make the path exist
                normalized_arg = arg[len(project_name) + 1 :]
                # Use normalized path if original doesn't exist but normalized does
                if not Path(arg).exists() and Path(normalized_arg).exists():
                    normalized_cmd.append(normalized_arg)
                else:
                    normalized_cmd.append(arg)
            else:
                normalized_cmd.append(arg)

        # Auto-prefix pytest commands with 'uv run' if appropriate
        # This ensures tests run in the correct environment for maid-runner itself
        # but avoids dependency resolution issues for projects with local deps
        if auto_prefix_uv_run and normalized_cmd and normalized_cmd[0] == "pytest":
            normalized_cmd = ["uv", "run"] + normalized_cmd

        cmd_str = " ".join(normalized_cmd)
        print(f"  [{i+1}/{total}] {cmd_str}")

        try:
            result = subprocess.run(
                normalized_cmd,
                capture_output=True,
                text=True,
                timeout=timeout,
                cwd=project_root,
                env=env_additions,
            )

            if result.returncode == 0:
                passed += 1
                print("    ✅ PASSED")
                if verbose and result.stdout:
                    for line in result.stdout.strip().split("\n"):
                        print(f"      {line}")
            else:
                failed += 1
                print(f"    ❌ FAILED (exit code: {result.returncode})")
                if result.stderr:
                    # Print first few lines of stderr
                    stderr_lines = result.stderr.strip().split("\n")[:10]
                    for line in stderr_lines:
                        print(f"      {line}")

        except subprocess.TimeoutExpired:
            failed += 1
            print(f"    ⏰ TIMEOUT (>{timeout}s)")
        except FileNotFoundError:
            failed += 1
            print(f"    ❌ Command not found: {cmd[0]}")
        except Exception as e:
            failed += 1
            print(f"    ❌ Error: {e}")

    return (passed, failed, total)


def run_test(
    manifest_dir: str,
    fail_fast: bool,
    verbose: bool,
    quiet: bool,
    timeout: int,
    manifest_path: Optional[str] = None,
) -> None:
    """Run all validation commands from active manifests.

    Args:
        manifest_dir: Path to the manifests directory
        fail_fast: If True, stop on first failure
        verbose: If True, show detailed output
        quiet: If True, only show summary
        timeout: Command timeout in seconds
        manifest_path: Optional path to a single manifest to test (relative to manifest_dir or absolute)

    Raises:
        SystemExit: Exits with code 0 on success, 1 on failure
    """
    manifests_dir = Path(manifest_dir).resolve()
    project_root = manifests_dir.parent

    if not manifests_dir.exists():
        print_maid_not_enabled_message(str(manifest_dir))
        sys.exit(0)

    # If a specific manifest is requested, use only that one
    if manifest_path:
        specific_manifest = Path(manifest_path)
        # If path is relative, resolve it relative to manifests_dir
        if not specific_manifest.is_absolute():
            specific_manifest = manifests_dir / specific_manifest

        if not specific_manifest.exists():
            print(f"⚠️  Manifest file not found: {manifest_path}")
            sys.exit(1)

        active_manifests = [specific_manifest.resolve()]
    else:
        # Default behavior: process all non-superseded manifests
        manifest_files = sorted(manifests_dir.glob("task-*.manifest.json"))
        if not manifest_files:
            print_no_manifests_found_message(str(manifest_dir))
            sys.exit(0)

        # Get superseded manifests and filter them out
        superseded = get_superseded_manifests(manifests_dir)
        active_manifests = [m for m in manifest_files if m not in superseded]

        if not active_manifests:
            print("⚠️  No active manifest files found")
            sys.exit(0)

        if superseded and not quiet:
            print(f"⏭️  Skipping {len(superseded)} superseded manifest(s)")

    total_passed = 0
    total_failed = 0
    total_commands = 0
    manifests_with_failures = 0
    manifests_fully_passed = 0

    for manifest_file in active_manifests:
        try:
            with open(manifest_file, "r") as f:
                manifest_data = json.load(f)

            # Validate version
            try:
                validate_manifest_version(manifest_data, manifest_file.name)
            except ValueError as e:
                if not quiet:
                    print(f"\n⚠️  {manifest_file.name}: {e}")
                continue

            validation_commands = normalize_validation_commands(manifest_data)
            if not validation_commands:
                continue

            if not quiet:
                print(
                    f"\n📋 {manifest_file.name}: Running {len(validation_commands)} validation command(s)"
                )

            passed, failed, total = execute_validation_commands(
                manifest_file, manifest_data, timeout, verbose, project_root
            )

            total_passed += passed
            total_failed += failed
            total_commands += total

            if failed > 0:
                manifests_with_failures += 1
                if fail_fast:
                    print("\n❌ Stopping due to failure (--fail-fast)")
                    sys.exit(1)
            else:
                manifests_fully_passed += 1

        except json.JSONDecodeError as e:
            if not quiet:
                print(f"\n⚠️  {manifest_file.name}: Invalid JSON - {e}")
            continue
        except Exception as e:
            if not quiet:
                print(f"\n⚠️  {manifest_file.name}: Error - {e}")
            continue

    # Print summary
    if total_commands > 0:
        percentage = (total_passed / total_commands * 100) if total_commands > 0 else 0
        print(
            f"\n📊 Summary: {total_passed}/{total_commands} validation commands passed ({percentage:.1f}%)"
        )
        if not quiet:
            print(f"   ✅ {manifests_fully_passed} manifest(s) fully passed")
            if manifests_with_failures > 0:
                print(f"   ❌ {manifests_with_failures} manifest(s) had failures")
    else:
        print("\n⚠️  No validation commands found in manifests")

    # Exit with appropriate code
    if total_failed > 0:
        sys.exit(1)
    else:
        sys.exit(0)


def main() -> None:
    """Main CLI entry point for maid test command."""
    parser = argparse.ArgumentParser(
        description="Run validation commands from all non-superseded manifests",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Run all validation commands
  %(prog)s

  # Run validation commands for a single manifest
  %(prog)s --manifest task-021-maid-test-command.manifest.json

  # Use custom manifest directory
  %(prog)s --manifest-dir my-manifests

  # Stop on first failure
  %(prog)s --fail-fast

  # Show detailed output
  %(prog)s --verbose

  # Only show summary
  %(prog)s --quiet
        """,
    )

    parser.add_argument(
        "--manifest",
        "-m",
        help="Run validation commands for a single manifest (filename relative to manifest-dir or absolute path)",
    )

    parser.add_argument(
        "--manifest-dir",
        default="manifests",
        help="Directory containing manifests (default: manifests)",
    )

    parser.add_argument(
        "--fail-fast",
        action="store_true",
        help="Stop execution on first failure",
    )

    parser.add_argument(
        "--verbose",
        "-v",
        action="store_true",
        help="Show detailed command output",
    )

    parser.add_argument(
        "--quiet",
        "-q",
        action="store_true",
        help="Only show summary (suppress per-manifest output)",
    )

    parser.add_argument(
        "--timeout",
        type=int,
        default=300,
        help="Command timeout in seconds (default: 300)",
    )

    args = parser.parse_args()

    run_test(
        manifest_dir=args.manifest_dir,
        fail_fast=args.fail_fast,
        verbose=args.verbose,
        quiet=args.quiet,
        timeout=args.timeout,
        manifest_path=args.manifest,
    )


if __name__ == "__main__":
    main()
