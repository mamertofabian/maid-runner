#!/usr/bin/env python3
"""
MAID Runner CLI - Example Implementation Helper

This is a sample/example implementation demonstrating how external tools
can build automation on top of MAID Runner's validation tools.

Provides optional interactive helpers for manual MAID workflow:
- Planning loop: Interactive manifest creation
- Implementation loop: Manual validation iteration

**Note:** This is an EXAMPLE implementation showing how to use MAID Runner.
The core validation tools are `validate_manifest.py` and `generate_snapshot.py`.
External automation tools should use those validation tools directly.

This demonstrates how an external tool can:
- Load manifests and prepare context for AI agents
- Execute validation commands
- Display context information
- Orchestrate iteration loops
"""

import argparse
import json
import re
import shlex
import subprocess
import sys
from pathlib import Path
from typing import Dict, List, Any, Optional


def main() -> None:
    """CLI entry point for MAID runner."""
    parser = argparse.ArgumentParser(
        description="MAID Runner - Phase 2 & 3 Orchestrator",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Plan a new task (Phase 2)
  %(prog)s plan --goal "Add user authentication"

  # Run implementation loop (Phase 3)
  %(prog)s run manifests/task-011.manifest.json
        """,
    )

    subparsers = parser.add_subparsers(dest="command", help="Command to execute")

    # Plan command (Phase 2)
    plan_parser = subparsers.add_parser(
        "plan", help="Run planning loop to create a new task manifest"
    )
    plan_parser.add_argument(
        "--goal", required=True, help="The goal/description of the task"
    )
    plan_parser.add_argument(
        "--task-number",
        type=int,
        default=None,
        help="Task number (auto-detected if not specified)",
    )

    # Run command (Phase 3)
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
    run_parser.add_argument(
        "--timeout",
        type=int,
        default=300,
        help="Validation command timeout in seconds (default: 300)",
    )
    run_parser.add_argument(
        "--auto",
        action="store_true",
        help="Run iterations automatically without pausing (not recommended)",
    )

    args = parser.parse_args()

    if args.command == "plan":
        success = run_planning_loop(args.goal, args.task_number)
        sys.exit(0 if success else 1)
    elif args.command == "run":
        success = run_implementation_loop(
            args.manifest_path, args.max_iterations, args.timeout, args.auto
        )
        sys.exit(0 if success else 1)
    else:
        parser.print_help()


def run_implementation_loop(
    manifest_path: str, max_iterations: int, timeout: int = 300, auto: bool = False
) -> bool:
    """
    Run the implementation loop for a given manifest.

    This is a MANUAL loop - it pauses between iterations to allow the developer
    to review failures and make code changes. It does NOT automatically generate
    or modify code.

    Args:
        manifest_path: Path to the manifest JSON file
        max_iterations: Maximum number of validation iterations
        timeout: Validation command timeout in seconds (default: 300)
        auto: If True, run without pausing between iterations (default: False)

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

    # Validate command structure
    if not isinstance(validation_command, list):
        print("\n✗ Error: validationCommand must be a list")
        return False

    if not all(isinstance(arg, str) for arg in validation_command):
        print("\n✗ Error: All items in validationCommand must be strings")
        return False

    # Validate command is allowed (security)
    ALLOWED_COMMANDS = {"pytest", "python", "uv", "make"}
    if validation_command and validation_command[0] not in ALLOWED_COMMANDS:
        print(
            f"\n✗ Error: Command '{validation_command[0]}' not allowed. "
            f"Allowed commands: {', '.join(sorted(ALLOWED_COMMANDS))}"
        )
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
        result = execute_validation(validation_command, timeout)

        # Display results
        display_validation_results(result)

        if result["success"]:
            print("\n" + "=" * 80)
            print("✅ VALIDATION PASSED - Implementation complete!")
            print("=" * 80)
            return True

        # Validation failed
        print(
            f"\n⚠ Validation failed. Iteration {iteration}/{max_iterations} complete."
        )

        if iteration < max_iterations:
            print("Please review the errors above and make necessary changes.")

            if not auto:
                # Pause for user intervention (manual implementation loop)
                try:
                    input("\nPress Enter to retry validation (or Ctrl+C to abort): ")
                except KeyboardInterrupt:
                    print("\n\n✗ Aborted by user")
                    return False
            else:
                print("Retrying validation automatically...")

    print("\n" + "=" * 80)
    print(f"✗ Maximum iterations ({max_iterations}) reached without success")
    print("=" * 80)
    return False


def load_manifest_context(manifest_data: Dict[str, Any]) -> Dict[str, Any]:
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


def execute_validation(
    validation_command: List[str], timeout: int = 300
) -> Dict[str, Any]:
    """
    Execute validation command and capture results.

    Args:
        validation_command: List of command components to execute
        timeout: Command timeout in seconds (default: 300)

    Returns:
        dict: Validation results including success status and output
    """
    try:
        result = subprocess.run(
            validation_command,
            capture_output=True,
            text=True,
            timeout=timeout,
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
            "stderr": f"Command timed out after {timeout} seconds",
            "output": f"Command timed out after {timeout} seconds",
        }
    except Exception as e:
        return {
            "success": False,
            "returncode": -1,
            "stdout": "",
            "stderr": str(e),
            "output": str(e),
        }


def display_agent_context(context: Dict[str, Any]) -> None:
    """
    Display agent context information.

    Args:
        context: Context dictionary to display
    """
    print("\n📋 GOAL:")
    print(f"   {context['goal']}")

    task_type = context.get("taskType", "unknown")
    print(f"\n📂 FILES ({task_type}):")

    creatable = context["files"].get("creatable", [])
    if creatable:
        print("\n   Creatable files (new):")
        for f in creatable:
            print(f"   • {f}")

    editable = context["files"].get("editable", [])
    if editable:
        print("\n   Editable files (modify):")
        for f in editable:
            print(f"   • {f}")

    readonly = context["files"].get("readonly", [])
    if readonly:
        print("\n   Readonly files (reference):")
        for f in readonly:
            print(f"   • {f}")

    artifacts = context.get("expectedArtifacts", {})
    if artifacts and artifacts.get("contains"):
        print("\n🎯 EXPECTED ARTIFACTS:")
        print(f"   File: {artifacts.get('file')}")
        print(f"   Artifacts: {len(artifacts.get('contains', []))} items")


def display_validation_results(result: Dict[str, Any]) -> None:
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


# ============================================================================
# Phase 2: Planning Loop Orchestrator
# ============================================================================


def run_planning_loop(
    goal: str, task_number: Optional[int] = None, max_iterations: int = 10
) -> bool:
    """
    Run the planning loop for creating a new task manifest.

    Args:
        goal: The goal/description of the task
        task_number: Optional task number (auto-detected if None)
        max_iterations: Maximum validation iterations (default: 10)

    Returns:
        bool: True if planning completed successfully, False otherwise
    """
    print("\n" + "=" * 80)
    print("MAID PLANNING LOOP")
    print("=" * 80)
    print(f"\n📋 Goal: {goal}\n")

    # Get task number
    if task_number is None:
        manifest_dir = Path("manifests")
        task_number = get_next_task_number(manifest_dir)
        print(f"Auto-detected task number: {task_number:03d}")

    # Prompt for manifest details
    try:
        manifest_details = prompt_for_manifest_details(goal)
    except (EOFError, KeyboardInterrupt):
        print("\n\n⚠ Planning cancelled by user")
        return False

    # Create draft manifest
    manifest_path = create_draft_manifest(task_number, manifest_details)
    print(f"\n✓ Created draft manifest: {manifest_path}")

    # Guide user to create tests
    print("\n" + "=" * 80)
    print("NEXT STEPS")
    print("=" * 80)
    print("\n1. Create behavioral tests for this task")
    print(f"   Suggested filename: tests/test_task_{task_number:03d}_*.py")
    print("\n2. Add test file to manifest's readonlyFiles")
    print("\n3. Define expectedArtifacts in the manifest")
    print("\n4. Run structural validation")

    try:
        input("\nPress Enter when ready to validate (or Ctrl+C to exit)...")
    except (EOFError, OSError):
        # Non-interactive mode - skip prompt
        pass

    # Validation loop
    iteration = 0

    while iteration < max_iterations:
        iteration += 1

        print(f"\n{'─' * 80}")
        print(f"VALIDATION ITERATION {iteration}/{max_iterations}")
        print(f"{'─' * 80}\n")

        result = run_structural_validation(manifest_path)

        if result["success"]:
            print("✅ STRUCTURAL VALIDATION PASSED")
            print("\n" + "=" * 80)
            print("PLANNING COMPLETE!")
            print("=" * 80)
            print(f"\n✓ Manifest: {manifest_path}")
            print("✓ All structural validations passed")
            print("\nYou can now commit the manifest and tests.")
            return True
        else:
            print("❌ STRUCTURAL VALIDATION FAILED")
            print("\n" + result["output"])

            if iteration < max_iterations:
                print(f"\nIteration {iteration}/{max_iterations}")
                print("\nPlease fix the validation errors and update:")
                print(f"  - Manifest: {manifest_path}")
                print("  - Tests")
                print("  - Implementation (if needed)")

                try:
                    input("\nPress Enter to retry validation (or Ctrl+C to exit)...")
                except (EOFError, KeyboardInterrupt, OSError):
                    print("\n\n⚠ Planning cancelled")
                    return False

    print(f"\n✗ Maximum iterations ({max_iterations}) reached")
    return False


def get_next_task_number(manifest_dir: Path) -> int:
    """
    Get the next available task number by scanning manifest directory.

    Args:
        manifest_dir: Path to the manifests directory

    Returns:
        int: Next task number to use
    """
    manifest_dir = Path(manifest_dir)
    if not manifest_dir.exists():
        return 1

    max_number = 0
    for manifest_file in manifest_dir.glob("task-*.manifest.json"):
        # Extract task number from filename like "task-001-description.manifest.json"
        stem = manifest_file.stem  # Remove .manifest.json
        parts = stem.split("-")

        if len(parts) >= 2 and parts[0] == "task":
            try:
                number = int(parts[1])
                max_number = max(max_number, number)
            except ValueError:
                continue

    return max_number + 1


def prompt_for_manifest_details(goal: str) -> Dict[str, Any]:
    """
    Interactively prompt user for manifest details.

    Args:
        goal: The task goal

    Returns:
        dict: Manifest details including files, task type, etc.
    """
    # Default values for non-interactive mode (testing)
    task_type = "edit"
    creatable_files = []
    editable_files = []
    readonly_files = []
    impl_file = "test.py"
    validation_command = ["true"]

    try:
        print("\n" + "=" * 80)
        print("MANIFEST CONFIGURATION")
        print("=" * 80)

        # Task type
        print("\nTask type:")
        print("  1. create  - Creating new files")
        print("  2. edit    - Modifying existing files")
        print("  3. refactor - Refactoring code")
        print("  4. snapshot - Creating a snapshot")

        task_type_input = input("Select task type [1-4] (default: 2): ").strip()
        task_type_map = {"1": "create", "2": "edit", "3": "refactor", "4": "snapshot"}
        task_type = task_type_map.get(task_type_input, "edit")

        # Files
        print("\nFile configuration:")

        if task_type == "create":
            creatable_input = input("Creatable files (comma-separated): ").strip()
            if creatable_input:
                creatable_files = [f.strip() for f in creatable_input.split(",")]
        elif task_type == "edit":
            editable_input = input("Editable files (comma-separated): ").strip()
            if editable_input:
                editable_files = [f.strip() for f in editable_input.split(",")]

        readonly_input = input("Readonly files (comma-separated, optional): ").strip()
        if readonly_input:
            readonly_files = [f.strip() for f in readonly_input.split(",")]

        # Implementation file
        if creatable_files:
            impl_file = creatable_files[0]
        elif editable_files:
            impl_file = editable_files[0]
        else:
            impl_file = input("Implementation file path: ").strip()

        # Validation command
        print("\nValidation command (e.g., pytest tests/test_xxx.py -v)")
        val_cmd_input = input("Command: ").strip()

        if val_cmd_input:
            # Split command into parts (handles quoted arguments correctly)
            validation_command = shlex.split(val_cmd_input)
        else:
            validation_command = ["true"]  # Default no-op

    except (EOFError, OSError):
        # Non-interactive mode - use defaults
        pass

    return {
        "goal": goal,
        "taskType": task_type,
        "supersedes": [],
        "creatableFiles": creatable_files,
        "editableFiles": editable_files,
        "readonlyFiles": readonly_files,
        "expectedArtifacts": {"file": impl_file, "contains": []},
        "validationCommand": validation_command,
    }


def create_draft_manifest(task_number: int, manifest_details: Dict[str, Any]) -> str:
    """
    Create a draft manifest file.

    Args:
        task_number: The task number
        manifest_details: Dictionary with manifest details

    Returns:
        str: Path to the created manifest file
    """
    # Sanitize goal for filename
    goal = manifest_details.get("goal", "task")
    # Create a simple filename from goal (lowercase, replace spaces with hyphens)
    goal_slug = goal.lower().replace(" ", "-")[:50]
    # Remove special characters and collapse multiple hyphens
    goal_slug = re.sub(r"[^a-z0-9-]", "", goal_slug)
    goal_slug = re.sub(r"-+", "-", goal_slug).strip("-")
    # Fallback if empty
    if not goal_slug:
        goal_slug = "task"

    # Create manifest filename
    filename = f"task-{task_number:03d}-{goal_slug}.manifest.json"
    manifest_path = Path("manifests") / filename

    # Ensure manifests directory exists
    manifest_path.parent.mkdir(parents=True, exist_ok=True)

    # Write manifest
    with open(manifest_path, "w") as f:
        json.dump(manifest_details, f, indent=2)
        f.write("\n")  # Add trailing newline

    return str(manifest_path)


def run_structural_validation(manifest_path: str, timeout: int = 60) -> Dict[str, Any]:
    """
    Run structural validation on a manifest.

    Args:
        manifest_path: Path to the manifest file
        timeout: Validation timeout in seconds (default: 60)

    Returns:
        dict: Validation result with success status and errors
    """
    try:
        result = subprocess.run(
            [
                sys.executable,
                "validate_manifest.py",
                manifest_path,
                "--use-manifest-chain",
            ],
            capture_output=True,
            text=True,
            timeout=timeout,
        )

        return {
            "success": result.returncode == 0,
            "returncode": result.returncode,
            "output": result.stdout + result.stderr,
            "stdout": result.stdout,
            "stderr": result.stderr,
            "errors": [] if result.returncode == 0 else [result.stderr],
            "message": (
                "Validation passed" if result.returncode == 0 else "Validation failed"
            ),
        }
    except subprocess.TimeoutExpired:
        return {
            "success": False,
            "returncode": -1,
            "output": "Validation timed out",
            "errors": [f"Validation timed out after {timeout} seconds"],
            "message": "Validation timed out",
        }
    except Exception as e:
        return {
            "success": False,
            "returncode": -1,
            "output": str(e),
            "errors": [str(e)],
            "message": f"Validation error: {e}",
        }


if __name__ == "__main__":
    main()
