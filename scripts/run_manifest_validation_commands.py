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

        from maid_runner.utils import normalize_validation_commands

        return normalize_validation_commands(manifest_data)
    except json.JSONDecodeError as e:
        print(f"⚠️  Warning: Invalid JSON in {manifest_path.name}: {e}")
        return []
    except KeyError as e:
        print(f"⚠️  Warning: Missing key in {manifest_path.name}: {e}")
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
