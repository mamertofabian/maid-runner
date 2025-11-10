#!/usr/bin/env python3
"""
AST Validator Stop Hook
Validates manifest alignment with implementation using MAID CLI.
"""
import json
import sys
import os
import subprocess
from pathlib import Path


def validate_manifest_implementation():
    """Run AST validation for all manifests using maid CLI."""
    try:
        # Read hook input from stdin
        input_data = json.load(sys.stdin)
        project_dir = os.environ.get("CLAUDE_PROJECT_DIR", ".")

        # Change to project directory
        os.chdir(project_dir)

        # Skip if stop hook is already active to prevent infinite loops
        if input_data.get("stop_hook_active", False):
            return

        print("🔍 Running MAID Validation using CLI...")

        # Find all manifests
        manifests_dir = Path("manifests")
        if not manifests_dir.exists():
            print("📋 No manifests directory found - skipping validation")
            return

        manifest_files = sorted(manifests_dir.glob("*.json"))
        if not manifest_files:
            print("📋 No manifest files found - skipping validation")
            return

        validation_results = []

        for manifest_path in manifest_files:
            try:
                # Run validation using maid CLI
                print(f"🔍 Validating {manifest_path.name}")

                result = subprocess.run(
                    ["uv", "run", "maid", "validate", str(manifest_path), "--use-manifest-chain", "--quiet"],
                    capture_output=True,
                    text=True,
                    timeout=30,
                )

                if result.returncode == 0:
                    print(f"✅ {manifest_path.name}: Validation passed")
                    validation_results.append((manifest_path.name, True, None))
                else:
                    error_msg = result.stderr.strip() or result.stdout.strip()
                    print(f"❌ {manifest_path.name}: Validation failed")
                    if error_msg:
                        print(f"   {error_msg}")
                    validation_results.append((manifest_path.name, False, error_msg))

            except subprocess.TimeoutExpired:
                print(f"⏰ {manifest_path.name}: Validation timed out")
                validation_results.append((manifest_path.name, False, "Validation timeout"))
            except Exception as e:
                print(f"❌ {manifest_path.name}: Validation error - {e}")
                validation_results.append((manifest_path.name, False, str(e)))

        # Summary
        total = len(validation_results)
        passed = sum(1 for _, success, _ in validation_results if success)
        failed = total - passed

        print(f"\n📊 Validation Summary: {passed}/{total} passed")

        if failed > 0:
            print("❌ Failed validations:")
            for name, success, error in validation_results:
                if not success:
                    print(f"   • {name}: {error}")

            # Block Claude from stopping if there are validation failures
            output = {
                "decision": "block",
                "reason": f"Validation failed for {failed} manifest(s). Please fix the implementation-manifest alignment issues before proceeding.",
            }
            print(json.dumps(output))
        else:
            print("✨ All manifests are properly aligned with their implementations!")

    except Exception as e:
        print(f"🔧 Validator Hook Error: {e}", file=sys.stderr)
        # Don't block on hook errors
        sys.exit(0)


if __name__ == "__main__":
    validate_manifest_implementation()
