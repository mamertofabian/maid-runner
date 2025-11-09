#!/usr/bin/env python3
"""
MAID Runner CLI - Implementation Loop Controller

Orchestrates Phase 3 of MAID workflow by loading manifests, preparing agent
context, executing validation commands, and supporting iteration until tests pass.
"""

import argparse
import json
import subprocess
import sys
from pathlib import Path


def main():
    """CLI entry point for MAID runner."""
    parser = argparse.ArgumentParser(
        description="MAID Runner - Implementation Loop Controller",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Run implementation loop for a manifest
  %(prog)s run manifests/task-011.manifest.json

  # Run with custom iteration limit
  %(prog)s run manifests/task-011.manifest.json --max-iterations 5
        """,
    )

    subparsers = parser.add_subparsers(dest="command", help="Command to execute")

    # Run command
    run_parser = subparsers.add_parser(
        "run", help="Run implementation loop for a manifest"
    )
    run_parser.add_argument("manifest_path", help="Path to the manifest JSON file")
    run_parser.add_argument(
        "--max-iterations",
        type=int,
        default=10,
        help="Maximum number of validation iterations (default: 10)",
    )

    args = parser.parse_args()

    if args.command == "run":
        success = run_implementation_loop(args.manifest_path, args.max_iterations)
        sys.exit(0 if success else 1)
    else:
        parser.print_help()


def run_implementation_loop(manifest_path: str, max_iterations: int) -> bool:
    """
    Run the implementation loop for a given manifest.

    Args:
        manifest_path: Path to the manifest JSON file
        max_iterations: Maximum number of validation iterations

    Returns:
        bool: True if validation passed, False otherwise
    """
    # Load manifest
    manifest_file = Path(manifest_path)
    if not manifest_file.exists():
        print(f"✗ Error: Manifest file not found: {manifest_path}")
        return False

    with open(manifest_file, "r") as f:
        try:
            manifest_data = json.load(f)
        except json.JSONDecodeError as e:
            print(f"✗ Error: Invalid JSON in manifest: {e}")
            return False

    # Load context
    context = load_manifest_context(manifest_data)

    # Display context for agent
    print("\n" + "=" * 80)
    print("MAID IMPLEMENTATION LOOP")
    print("=" * 80)
    display_agent_context(context)

    # Get validation command
    validation_command = manifest_data.get("validationCommand", [])
    if not validation_command:
        print("\n✗ Error: No validationCommand specified in manifest")
        return False

    # Run validation loop
    iteration = 0
    while iteration < max_iterations:
        iteration += 1

        print(f"\n{'─' * 80}")
        print(f"ITERATION {iteration}/{max_iterations}")
        print(f"{'─' * 80}")

        # Execute validation
        print(f"\nRunning: {' '.join(validation_command)}\n")
        result = execute_validation(validation_command)

        # Display results
        display_validation_results(result)

        if result["success"]:
            print("\n" + "=" * 80)
            print("✅ VALIDATION PASSED - Implementation complete!")
            print("=" * 80)
            return True

        if iteration < max_iterations:
            print(
                f"\n⚠ Validation failed. Iteration {iteration}/{max_iterations} complete."
            )
            print("Please review the errors above and make necessary changes.")
            print("Retrying validation...")

    print("\n" + "=" * 80)
    print(f"✗ Maximum iterations ({max_iterations}) reached without success")
    print("=" * 80)
    return False


def load_manifest_context(manifest_data: dict) -> dict:
    """
    Load and prepare context from manifest for AI agent.

    Args:
        manifest_data: Dictionary containing the manifest

    Returns:
        dict: Context information including goal and files
    """
    return {
        "goal": manifest_data.get("goal", "No goal specified"),
        "taskType": manifest_data.get("taskType", "unknown"),
        "files": {
            "creatable": manifest_data.get("creatableFiles", []),
            "editable": manifest_data.get("editableFiles", []),
            "readonly": manifest_data.get("readonlyFiles", []),
        },
        "expectedArtifacts": manifest_data.get("expectedArtifacts", {}),
    }


def execute_validation(validation_command: list) -> dict:
    """
    Execute validation command and capture results.

    Args:
        validation_command: List of command components to execute

    Returns:
        dict: Validation results including success status and output
    """
    try:
        result = subprocess.run(
            validation_command,
            capture_output=True,
            text=True,
            timeout=300,  # 5 minute timeout
        )

        return {
            "success": result.returncode == 0,
            "returncode": result.returncode,
            "stdout": result.stdout,
            "stderr": result.stderr,
            "output": result.stdout + result.stderr,
        }
    except subprocess.TimeoutExpired:
        return {
            "success": False,
            "returncode": -1,
            "stdout": "",
            "stderr": "Command timed out after 5 minutes",
            "output": "Command timed out after 5 minutes",
        }
    except Exception as e:
        return {
            "success": False,
            "returncode": -1,
            "stdout": "",
            "stderr": str(e),
            "output": str(e),
        }


def display_agent_context(context: dict):
    """
    Display agent context information.

    Args:
        context: Context dictionary to display
    """
    print("\n📋 GOAL:")
    print(f"   {context['goal']}")

    task_type = context.get('taskType', 'unknown')
    print(f"\n📂 FILES ({task_type}):")

    creatable = context["files"].get("creatable", [])
    if creatable:
        print(f"\n   Creatable files (new):")
        for f in creatable:
            print(f"   • {f}")

    editable = context["files"].get("editable", [])
    if editable:
        print(f"\n   Editable files (modify):")
        for f in editable:
            print(f"   • {f}")

    readonly = context["files"].get("readonly", [])
    if readonly:
        print(f"\n   Readonly files (reference):")
        for f in readonly:
            print(f"   • {f}")

    artifacts = context.get("expectedArtifacts", {})
    if artifacts and artifacts.get("contains"):
        print(f"\n🎯 EXPECTED ARTIFACTS:")
        print(f"   File: {artifacts.get('file')}")
        print(f"   Artifacts: {len(artifacts.get('contains', []))} items")


def display_validation_results(result: dict):
    """
    Display validation results.

    Args:
        result: Result dictionary to display
    """
    if result["success"]:
        print("✅ VALIDATION PASSED")
        if result.get("stdout"):
            print("\nOutput:")
            print(result["stdout"])
    else:
        print("❌ VALIDATION FAILED")
        print(f"\nExit code: {result.get('returncode', 'unknown')}")

        if result.get("stdout"):
            print("\n--- STDOUT ---")
            print(result["stdout"])

        if result.get("stderr"):
            print("\n--- STDERR ---")
            print(result["stderr"])


if __name__ == "__main__":
    main()
