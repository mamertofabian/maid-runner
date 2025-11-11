#!/usr/bin/env python3
"""
Test Runner Stop Hook
Runs tests for modified manifests and test files only.
"""
import json
import sys
import os
import subprocess
import shlex
from pathlib import Path


def get_modified_files_from_transcript(transcript_path):
    """Parse transcript to find files that were modified during the session."""
    try:
        modified_manifests = set()
        modified_test_files = set()

        with open(transcript_path, "r") as f:
            for line in f:
                try:
                    entry = json.loads(line.strip())

                    # Look for assistant messages with tool use content
                    if entry.get("type") == "assistant":
                        # Check if content is in 'message.content' or directly in 'content'
                        content = entry.get("message", {}).get("content") or entry.get(
                            "content"
                        )

                        if content:
                            for content_block in content:
                                # Check for Edit or Write tool uses
                                if (
                                    isinstance(content_block, dict)
                                    and content_block.get("type") == "tool_use"
                                ):
                                    tool_name = content_block.get("name", "")

                                    if tool_name in ["Edit", "Write"]:
                                        tool_input = content_block.get("input", {})
                                        file_path = tool_input.get("file_path")

                                        if file_path:
                                            # Check if this is a manifest file
                                            if file_path.startswith(
                                                "manifests/"
                                            ) and file_path.endswith(".json"):
                                                modified_manifests.add(Path(file_path))
                                            elif (
                                                "/manifests/" in file_path
                                                and file_path.endswith(".json")
                                            ):
                                                rel_path = file_path.split(
                                                    "/manifests/"
                                                )[-1]
                                                modified_manifests.add(
                                                    Path("manifests") / rel_path
                                                )

                                            # Check if this is a test file
                                            elif file_path.startswith(
                                                "tests/"
                                            ) and file_path.endswith(".py"):
                                                modified_test_files.add(Path(file_path))
                                            elif (
                                                "/tests/" in file_path
                                                and file_path.endswith(".py")
                                            ):
                                                rel_path = file_path.split("/tests/")[
                                                    -1
                                                ]
                                                modified_test_files.add(
                                                    Path("tests") / rel_path
                                                )

                except json.JSONDecodeError:
                    continue

        return list(modified_manifests), list(modified_test_files)

    except Exception as e:
        print(f"⚠️  Unable to parse transcript: {e}")
        return None, None


def run_tests():
    """Run tests for modified manifests and test files."""
    try:
        # Read hook input from stdin
        input_data = json.load(sys.stdin)
        project_dir = os.environ.get("CLAUDE_PROJECT_DIR", ".")

        # Change to project directory
        os.chdir(project_dir)

        # Skip if stop hook is already active to prevent infinite loops
        if input_data.get("stop_hook_active", False):
            return

        # Get transcript path from hook input
        transcript_path = input_data.get("transcript_path")
        if not transcript_path:
            print("⚠️  No transcript path provided - skipping tests")
            return

        # Get modified files from transcript
        modified_manifests, modified_test_files = get_modified_files_from_transcript(
            transcript_path
        )

        if modified_manifests is None:
            print("⚠️  Failed to parse transcript - skipping tests")
            return

        # Check if there are any changes to test
        if not modified_manifests and not modified_test_files:
            print("✨ No manifest or test file changes detected - skipping tests")
            return

        print("🧪 Running tests for modified files...")
        test_results = []

        # 1. Run tests from modified manifests
        if modified_manifests:
            print(
                f"\n📋 Running tests for {len(modified_manifests)} modified manifest(s)..."
            )

            for manifest_path in sorted(modified_manifests):
                if not manifest_path.exists():
                    print(f"⚠️  {manifest_path}: File does not exist")
                    continue

                try:
                    with open(manifest_path, "r") as f:
                        manifest_data = json.load(f)

                    # Get validation command (supports both formats)
                    validation_cmd = manifest_data.get(
                        "validationCommand"
                    ) or manifest_data.get("validationCommands", [{}])[0].get("command")

                    if validation_cmd:
                        # Convert string to list if needed (safely)
                        if isinstance(validation_cmd, str):
                            validation_cmd = shlex.split(validation_cmd)

                        print(f"🧪 Running tests for {manifest_path.name}")

                        result = subprocess.run(
                            validation_cmd,
                            shell=False,
                            capture_output=True,
                            text=True,
                            timeout=120,  # 2 minute timeout
                        )

                        if result.returncode == 0:
                            print(f"✅ {manifest_path.name}: Tests passed")
                            test_results.append((manifest_path.name, True, None))
                        else:
                            print(f"❌ {manifest_path.name}: Tests failed")
                            error_output = (
                                result.stderr.strip() or result.stdout.strip()
                            )
                            if error_output:
                                # Only show last 10 lines to avoid clutter
                                error_lines = error_output.split("\n")[-10:]
                                print(f"   {chr(10).join(error_lines)}")
                            test_results.append(
                                (manifest_path.name, False, error_output)
                            )
                    else:
                        print(
                            f"📋 {manifest_path.name}: No validation command specified"
                        )

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

        # 2. Run modified test files
        if modified_test_files:
            print(f"\n🧪 Running {len(modified_test_files)} modified test file(s)...")

            for test_file in sorted(modified_test_files):
                if not test_file.exists():
                    print(f"⚠️  {test_file}: File does not exist")
                    continue

                print(f"🧪 Running {test_file.name}")

                try:
                    result = subprocess.run(
                        ["uv", "run", "pytest", str(test_file), "-v"],
                        capture_output=True,
                        text=True,
                        timeout=120,
                    )

                    if result.returncode == 0:
                        print(f"✅ {test_file.name}: Tests passed")
                        test_results.append((test_file.name, True, None))
                    else:
                        print(f"❌ {test_file.name}: Tests failed")
                        error_output = result.stderr.strip() or result.stdout.strip()
                        # Only show last 10 lines
                        error_lines = error_output.split("\n")[-10:]
                        print(f"   {chr(10).join(error_lines)}")
                        test_results.append((test_file.name, False, error_output))

                except subprocess.TimeoutExpired:
                    print(f"⏰ {test_file.name}: Tests timed out")
                    test_results.append((test_file.name, False, "Test timeout"))
                except Exception as e:
                    print(f"❌ {test_file.name}: Test error - {e}")
                    test_results.append((test_file.name, False, str(e)))

        # Summary
        if test_results:
            total = len(test_results)
            passed = sum(1 for _, success, _ in test_results if success)
            failed = total - passed

            print(f"\n📊 Test Summary: {passed}/{total} test file(s) passed")

            if failed > 0:
                print("❌ Failed tests:")
                for name, success, error in test_results:
                    if not success:
                        error_preview = (
                            error[:100] + "..." if error and len(error) > 100 else error
                        )
                        print(f"   • {name}: {error_preview}")

                # Block Claude from stopping if tests fail
                output = {
                    "decision": "block",
                    "reason": f"Tests failed for {failed} file(s). Please fix the failing tests before proceeding.",
                }
                print(json.dumps(output))
            else:
                print("✨ All tests passed!")
        else:
            print("📋 No tests to run")

    except Exception as e:
        print(f"🔧 Test Runner Hook Error: {e}", file=sys.stderr)
        # Don't block on hook errors
        sys.exit(0)


if __name__ == "__main__":
    run_tests()
