#!/usr/bin/env python3
"""Unified script to validate all active manifests (structural + behavioral).

This script combines structural validation and validation command execution
in a single pass to avoid redundant manifest parsing and superseded manifest checks.
"""
import json
import subprocess
import sys
from pathlib import Path


def get_superseded_manifests(manifests_dir: Path):
    """Find all manifests that are superseded by snapshots."""
    import importlib.util

    # Import the function from the other script
    script_path = Path(__file__).parent / "get_superseded_manifests.py"
    spec = importlib.util.spec_from_file_location(
        "get_superseded_manifests", script_path
    )
    module = importlib.util.module_from_spec(spec)
    sys.modules["get_superseded_manifests"] = module
    spec.loader.exec_module(module)

    return module.get_superseded_manifests(manifests_dir)


def run_structural_validation(manifest_path: Path) -> bool:
    """Run structural validation for a single manifest.

    Args:
        manifest_path: Path to the manifest file

    Returns:
        True if validation passed, False otherwise
    """
    try:
        result = subprocess.run(
            ["maid", "validate", str(manifest_path), "--quiet", "--use-manifest-chain"],
            capture_output=True,
            text=True,
            timeout=30,
        )
        return result.returncode == 0
    except subprocess.TimeoutExpired:
        print(f"⚠️  Timeout validating {manifest_path.name}", file=sys.stderr)
        return False
    except Exception as e:
        print(f"⚠️  Error validating {manifest_path.name}: {e}", file=sys.stderr)
        return False


def extract_validation_commands(manifest_path: Path):
    """Extract validation commands from a manifest file."""
    try:
        with open(manifest_path, "r") as f:
            manifest_data = json.load(f)

        from maid_runner.utils import normalize_validation_commands

        return normalize_validation_commands(manifest_data)
    except json.JSONDecodeError as e:
        print(f"⚠️  Warning: Invalid JSON in {manifest_path.name}: {e}", file=sys.stderr)
        return []
    except KeyError as e:
        print(f"⚠️  Warning: Missing key in {manifest_path.name}: {e}", file=sys.stderr)
        return []


def run_validation_command(cmd: list, manifest_name: str) -> bool:
    """Run a single validation command.

    Args:
        cmd: Command array to execute
        manifest_name: Name of manifest for error messages

    Returns:
        True if command succeeded, False otherwise
    """
    if not cmd:
        return True

    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=300,
            cwd=Path.cwd(),
        )

        if result.returncode == 0:
            return True
        else:
            print(f"❌ Command failed for {manifest_name}:", file=sys.stderr)
            print(f"   Command: {' '.join(cmd)}", file=sys.stderr)
            if result.stdout:
                print(result.stdout, file=sys.stderr)
            if result.stderr:
                print(result.stderr, file=sys.stderr)
            return False
    except subprocess.TimeoutExpired:
        print(
            f"⚠️  Timeout running command for {manifest_name}: {' '.join(cmd)}",
            file=sys.stderr,
        )
        return False
    except Exception as e:
        print(
            f"⚠️  Error running command for {manifest_name}: {e}",
            file=sys.stderr,
        )
        return False


def validate_all_manifests(
    run_structural: bool = True, run_behavioral: bool = True
) -> int:
    """Validate all active manifests (structural and/or behavioral).

    Args:
        run_structural: If True, run structural validation
        run_behavioral: If True, run behavioral validation commands

    Returns:
        Exit code (0 for success, 1 for failure)
    """
    manifests_dir = Path("manifests")
    if not manifests_dir.exists():
        print("⚠️  No manifests directory found", file=sys.stderr)
        return 1

    manifest_files = sorted(manifests_dir.glob("task-*.manifest.json"))
    if not manifest_files:
        print("⚠️  No manifest files found", file=sys.stderr)
        return 1

    # Get superseded manifests once (cached for both operations)
    superseded = get_superseded_manifests(manifests_dir)
    active_manifests = [m for m in manifest_files if m not in superseded]

    if not active_manifests:
        print("⚠️  No active manifest files found", file=sys.stderr)
        return 1

    if superseded:
        print(f"⏭️  Skipping {len(superseded)} superseded manifest(s)")

    all_passed = True

    # Structural validation
    if run_structural:
        print("\n🔍 Running structural validation for active manifests...")
        structural_failed = []
        for manifest_path in active_manifests:
            print(f"Validating {manifest_path.name}...")
            if not run_structural_validation(manifest_path):
                structural_failed.append(manifest_path.name)
                all_passed = False

        if structural_failed:
            print(
                f"\n❌ Structural validation failed for: {', '.join(structural_failed)}"
            )
        else:
            print("✅ All active manifests structurally valid")

    # Behavioral validation (validation commands)
    if run_behavioral:
        print("\n🧪 Running validation commands from active manifests...")
        behavioral_failed = []
        total_commands = 0
        passed_commands = 0

        for manifest_path in active_manifests:
            commands = extract_validation_commands(manifest_path)
            if not commands:
                continue

            for cmd in commands:
                total_commands += 1
                if run_validation_command(cmd, manifest_path.name):
                    passed_commands += 1
                else:
                    behavioral_failed.append(f"{manifest_path.name}: {' '.join(cmd)}")
                    all_passed = False

        if behavioral_failed:
            print(
                f"\n❌ Behavioral validation failed for {len(behavioral_failed)} command(s):"
            )
            for failure in behavioral_failed:
                print(f"   - {failure}")
        else:
            print(
                f"✅ All validation commands passed ({passed_commands}/{total_commands})"
            )

    return 0 if all_passed else 1


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(
        description="Validate all active manifests (structural and/or behavioral)"
    )
    parser.add_argument(
        "--structural-only",
        action="store_true",
        help="Only run structural validation",
    )
    parser.add_argument(
        "--behavioral-only",
        action="store_true",
        help="Only run behavioral validation commands",
    )

    args = parser.parse_args()

    run_structural = not args.behavioral_only
    run_behavioral = not args.structural_only

    sys.exit(validate_all_manifests(run_structural, run_behavioral))
