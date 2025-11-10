#!/usr/bin/env python3
"""Script to extract and run validation commands from all manifests."""
import json
import subprocess
import sys
from pathlib import Path


def extract_validation_commands(manifest_path: Path):
    """Extract validation commands from a manifest file."""
    try:
        with open(manifest_path, "r") as f:
            manifest_data = json.load(f)

        # Support both validationCommand (legacy) and validationCommands (enhanced)
        validation_commands = manifest_data.get("validationCommands", [])
        if not validation_commands:
            validation_command = manifest_data.get("validationCommand", [])
            if validation_command:
                # Handle different formats
                if isinstance(validation_command, str):
                    # Single string command: "pytest tests/test.py"
                    validation_commands = [validation_command.split()]
                elif isinstance(validation_command, list):
                    if len(validation_command) > 1 and all(
                        isinstance(cmd, str) and " " in cmd
                        for cmd in validation_command
                    ):
                        # Multiple string commands: ["pytest test1.py", "pytest test2.py"]
                        validation_commands = [
                            cmd.split() for cmd in validation_command
                        ]
                    elif len(validation_command) > 0 and isinstance(
                        validation_command[0], str
                    ):
                        # Check if first element is a string with spaces (single string command)
                        if " " in validation_command[0]:
                            # Single string command in array: ["pytest tests/test.py"]
                            validation_commands = [validation_command[0].split()]
                        else:
                            # Single command array: ["pytest", "test.py", "-v"]
                            validation_commands = [validation_command]
                    else:
                        # Single command array: ["pytest", "test.py", "-v"]
                        validation_commands = [validation_command]

        return validation_commands
    except (json.JSONDecodeError, KeyError):
        return []


def run_validation_commands():
    """Run all validation commands from manifests."""
    manifests_dir = Path("manifests")
    if not manifests_dir.exists():
        print("⚠️  No manifests directory found")
        return 0

    manifest_files = sorted(manifests_dir.glob("task-*.manifest.json"))
    if not manifest_files:
        print("⚠️  No manifest files found")
        return 0

    all_passed = True
    total_commands = 0
    passed_commands = 0

    for manifest_path in manifest_files:
        validation_commands = extract_validation_commands(manifest_path)
        if not validation_commands:
            continue

        manifest_name = manifest_path.name
        print(
            f"\n📋 {manifest_name}: Running {len(validation_commands)} validation command(s)"
        )

        for i, cmd in enumerate(validation_commands):
            if not cmd:
                continue

            total_commands += 1
            cmd_str = " ".join(cmd)
            print(f"  [{i+1}/{len(validation_commands)}] {cmd_str}")

            try:
                result = subprocess.run(
                    cmd,
                    capture_output=True,
                    text=True,
                    timeout=300,
                    cwd=Path.cwd(),
                )

                if result.returncode == 0:
                    passed_commands += 1
                    print("    ✅ PASSED")
                else:
                    all_passed = False
                    print(f"    ❌ FAILED (exit code: {result.returncode})")
                    if result.stderr:
                        # Print first few lines of stderr
                        stderr_lines = result.stderr.strip().split("\n")[:5]
                        for line in stderr_lines:
                            print(f"      {line}")

            except subprocess.TimeoutExpired:
                all_passed = False
                print("    ⏰ TIMEOUT")
            except FileNotFoundError:
                all_passed = False
                print(f"    ❌ Command not found: {cmd[0]}")
            except Exception as e:
                all_passed = False
                print(f"    ❌ Error: {e}")

    print(
        f"\n📊 Summary: {passed_commands}/{total_commands} validation commands passed"
    )
    return 0 if all_passed else 1


if __name__ == "__main__":
    sys.exit(run_validation_commands())
