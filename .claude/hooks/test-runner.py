#!/usr/bin/env python3
"""
Test Runner Stop Hook
Runs tests specified in manifests and integration tests.
"""
import json
import sys
import os
import subprocess
from pathlib import Path


def run_tests():
    """Run all tests from manifests and integration tests."""
    try:
        # Read hook input from stdin
        input_data = json.load(sys.stdin)
        project_dir = os.environ.get("CLAUDE_PROJECT_DIR", ".")

        # Change to project directory
        os.chdir(project_dir)

        # Skip if stop hook is already active to prevent infinite loops
        if input_data.get("stop_hook_active", False):
            return

        print("🧪 Running MAID Test Suite...")

        test_results = []

        # 1. Run tests from manifests
        manifests_dir = Path("manifests")
        if manifests_dir.exists():
            manifest_files = sorted(manifests_dir.glob("*.json"))

            for manifest_path in manifest_files:
                try:
                    with open(manifest_path, "r") as f:
                        manifest_data = json.load(f)

                    # Get validation command (supports both formats)
                    validation_cmd = manifest_data.get("validationCommand") or manifest_data.get("validationCommands", [{}])[0].get("command")

                    if validation_cmd:
                        # Convert list to string if needed
                        if isinstance(validation_cmd, list):
                            validation_cmd = " ".join(validation_cmd)

                        print(f"🧪 Running tests for {manifest_path.name}")

                        result = subprocess.run(
                            validation_cmd,
                            shell=True,
                            capture_output=True,
                            text=True,
                            timeout=120,  # 2 minute timeout
                        )

                        if result.returncode == 0:
                            print(f"✅ {manifest_path.name}: Tests passed")
                            test_results.append((manifest_path.name, True, None))
                        else:
                            print(f"❌ {manifest_path.name}: Tests failed")
                            error_output = result.stderr.strip() or result.stdout.strip()
                            if error_output:
                                # Only show last 10 lines to avoid clutter
                                error_lines = error_output.split('\n')[-10:]
                                print(f"   {chr(10).join(error_lines)}")
                            test_results.append(
                                (manifest_path.name, False, error_output)
                            )
                    else:
                        print(f"📋 {manifest_path.name}: No validation command specified")

                except json.JSONDecodeError as e:
                    print(f"❌ {manifest_path.name}: Invalid JSON - {e}")
                    test_results.append(
                        (manifest_path.name, False, f"Invalid JSON: {e}")
                    )
                except subprocess.TimeoutExpired:
                    print(f"⏰ {manifest_path.name}: Tests timed out")
                    test_results.append((manifest_path.name, False, "Test timeout"))
                except Exception as e:
                    print(f"❌ {manifest_path.name}: Test error - {e}")
                    test_results.append((manifest_path.name, False, str(e)))

        # 2. Run integration tests
        integration_tests = list(Path("tests").glob("test_*_integration.py")) if Path("tests").exists() else []
        if integration_tests:
            print(f"\n🔗 Running {len(integration_tests)} integration test file(s)")

            for test_file in sorted(integration_tests):
                print(f"🧪 Running {test_file.name}")

                try:
                    result = subprocess.run(
                        ["uv", "run", "pytest", str(test_file), "-v"],
                        capture_output=True,
                        text=True,
                        timeout=120,
                    )

                    if result.returncode == 0:
                        print(f"✅ {test_file.name}: Integration tests passed")
                        test_results.append(
                            (f"integration:{test_file.name}", True, None)
                        )
                    else:
                        print(f"❌ {test_file.name}: Integration tests failed")
                        error_output = result.stderr.strip() or result.stdout.strip()
                        test_results.append(
                            (f"integration:{test_file.name}", False, error_output)
                        )

                except subprocess.TimeoutExpired:
                    print(f"⏰ {test_file.name}: Integration tests timed out")
                    test_results.append(
                        (f"integration:{test_file.name}", False, "Test timeout")
                    )
                except Exception as e:
                    print(f"❌ {test_file.name}: Integration test error - {e}")
                    test_results.append(
                        (f"integration:{test_file.name}", False, str(e))
                    )

        # 3. Run comprehensive test suite
        if Path("tests").exists():
            print("\n🧪 Running comprehensive test suite")

            try:
                result = subprocess.run(
                    ["uv", "run", "pytest", "tests/", "-q"],
                    capture_output=True,
                    text=True,
                    timeout=180,  # 3 minute timeout for all tests
                )

                if result.returncode == 0:
                    print("✅ Comprehensive test suite: All tests passed")
                    test_results.append(("comprehensive", True, None))
                else:
                    print("❌ Comprehensive test suite: Some tests failed")
                    error_output = result.stderr.strip() or result.stdout.strip()
                    test_results.append(("comprehensive", False, error_output))

            except subprocess.TimeoutExpired:
                print("⏰ Comprehensive test suite: Timed out")
                test_results.append(("comprehensive", False, "Test timeout"))
            except Exception as e:
                print(f"❌ Comprehensive test suite error: {e}")
                test_results.append(("comprehensive", False, str(e)))

        # Summary
        if test_results:
            total = len(test_results)
            passed = sum(1 for _, success, _ in test_results if success)
            failed = total - passed

            print(f"\n📊 Test Summary: {passed}/{total} test suites passed")

            if failed > 0:
                print("❌ Failed test suites:")
                for name, success, error in test_results:
                    if not success:
                        error_preview = error[:100] + "..." if error and len(error) > 100 else error
                        print(f"   • {name}: {error_preview}")

                # Block Claude from stopping if tests fail
                output = {
                    "decision": "block",
                    "reason": f"Tests failed for {failed} test suite(s). Please fix the failing tests before proceeding.",
                }
                print(json.dumps(output))
            else:
                print("✨ All tests passed! MAID validation complete.")
        else:
            print("📋 No tests found to run")

    except Exception as e:
        print(f"🔧 Test Runner Hook Error: {e}", file=sys.stderr)
        # Don't block on hook errors
        sys.exit(0)


if __name__ == "__main__":
    run_tests()
