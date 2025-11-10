#!/usr/bin/env python3
"""
AST Validator Stop Hook
Validates manifest alignment with implementation using AST analysis.
"""
import json
import sys
import os
from pathlib import Path


def validate_manifest_implementation():
    """Run AST validation for all manifests with existing implementations."""
    try:
        # Read hook input from stdin
        input_data = json.load(sys.stdin)
        project_dir = os.environ.get("CLAUDE_PROJECT_DIR", ".")

        # Change to project directory
        os.chdir(project_dir)

        # Skip if stop hook is already active to prevent infinite loops
        if input_data.get("stop_hook_active", False):
            return

        print("🔍 Running MAID AST Validation...")

        # Find all manifests
        manifests_dir = Path("manifests")
        if not manifests_dir.exists():
            print("📋 No manifests directory found - skipping AST validation")
            return

        manifest_files = list(manifests_dir.glob("*.json"))
        if not manifest_files:
            print("📋 No manifest files found - skipping AST validation")
            return

        # Check if validator exists
        if not Path("maid_runner/validators/manifest_validator.py").exists():
            print("❌ AST validator not found - skipping validation")
            return

        validation_results = []

        for manifest_path in sorted(manifest_files):
            try:
                # Load manifest
                with open(manifest_path, "r") as f:
                    manifest_data = json.load(f)

                # Get implementation file
                impl_file = manifest_data.get("expectedArtifacts", {}).get("file")
                if not impl_file:
                    print(f"📋 {manifest_path.name}: No implementation file specified")
                    continue

                if not Path(impl_file).exists():
                    print(
                        f"📋 {manifest_path.name}: Implementation file {impl_file} not found"
                    )
                    continue

                # Run AST validation
                print(f"🔍 Validating {manifest_path.name} against {impl_file}")

                # Import and run validation
                sys.path.insert(0, ".")
                from maid_runner.validators.manifest_validator import validate_with_ast

                try:
                    validate_with_ast(manifest_data, impl_file, use_manifest_chain=True)
                    print(f"✅ {manifest_path.name}: AST validation passed")
                    validation_results.append((manifest_path.name, True, None))
                except Exception as e:
                    print(f"❌ {manifest_path.name}: AST validation failed - {e}")
                    validation_results.append((manifest_path.name, False, str(e)))

            except json.JSONDecodeError as e:
                print(f"❌ {manifest_path.name}: Invalid JSON - {e}")
                validation_results.append(
                    (manifest_path.name, False, f"Invalid JSON: {e}")
                )
            except Exception as e:
                print(f"❌ {manifest_path.name}: Validation error - {e}")
                validation_results.append((manifest_path.name, False, str(e)))

        # Summary
        total = len(validation_results)
        passed = sum(1 for _, success, _ in validation_results if success)
        failed = total - passed

        print(f"\n📊 AST Validation Summary: {passed}/{total} passed")

        if failed > 0:
            print("❌ Failed validations:")
            for name, success, error in validation_results:
                if not success:
                    print(f"   • {name}: {error}")

            # Block Claude from stopping if there are validation failures
            output = {
                "decision": "block",
                "reason": f"AST validation failed for {failed} manifest(s). Please fix the implementation-manifest alignment issues before proceeding.",
            }
            print(json.dumps(output))
        else:
            print("✨ All manifests are properly aligned with their implementations!")

    except Exception as e:
        print(f"🔧 AST Validator Hook Error: {e}", file=sys.stderr)
        # Don't block on hook errors
        sys.exit(0)


if __name__ == "__main__":
    validate_manifest_implementation()
