#!/usr/bin/env python3
"""
AST Validator Stop Hook
Validates manifest alignment with implementation using MAID CLI.
Parses the transcript to find manifests modified during the session.
"""
import json
import sys
import os
import subprocess
from pathlib import Path


def get_modified_manifests_from_transcript(transcript_path):
    """Parse transcript to find manifest files that were modified during the session."""
    try:
        modified_manifests = set()

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
                                                # Handle absolute paths
                                                rel_path = file_path.split(
                                                    "/manifests/"
                                                )[-1]
                                                modified_manifests.add(
                                                    Path("manifests") / rel_path
                                                )

                except json.JSONDecodeError:
                    continue

        return list(modified_manifests) if modified_manifests else []

    except Exception as e:
        print(f"⚠️  Unable to parse transcript for modified manifests: {e}")
        return None


def main():
    """Main entry point for Stop hook."""
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
            print("⚠️  No transcript path provided - skipping validation")
            return

        # Find all manifests directory
        manifests_dir = Path("manifests")
        if not manifests_dir.exists():
            print("📋 No manifests directory found - skipping validation")
            return

        # Get modified manifests from transcript
        modified_manifests = get_modified_manifests_from_transcript(transcript_path)

        if modified_manifests is None:
            # Fall back to validating all manifests if transcript parsing failed
            print("🔍 Running MAID Validation for all manifests...")
            manifest_files = sorted(manifests_dir.glob("*.json"))
        elif not modified_manifests:
            # No modified manifests - skip validation
            print(
                "✨ No manifest changes detected in this session - skipping validation"
            )
            return
        else:
            # Only validate modified manifests
            print(
                f"🔍 Running MAID Validation for {len(modified_manifests)} modified manifest(s)..."
            )
            manifest_files = sorted(modified_manifests)

        if not manifest_files:
            print("📋 No manifest files found - skipping validation")
            return

        validation_results = []

        for manifest_path in manifest_files:
            try:
                # Run validation using maid CLI
                print(f"🔍 Validating {manifest_path.name}")

                result = subprocess.run(
                    [
                        "uv",
                        "run",
                        "maid",
                        "validate",
                        str(manifest_path),
                        "--use-manifest-chain",
                        "--quiet",
                    ],
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
                validation_results.append(
                    (manifest_path.name, False, "Validation timeout")
                )
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
    main()
