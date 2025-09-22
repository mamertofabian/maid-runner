#!/usr/bin/env python3
"""
Behavioral test validator for MAID Phase 2 Planning Loop.

This module ensures that behavioral tests (specified in validationCommand)
actually USE the artifacts declared in the manifest's expectedArtifacts.
"""

import json
import os
from pathlib import Path
from typing import List, Dict, Optional, Any

from validators.manifest_validator import validate_with_ast, AlignmentError


class BehavioralTestValidationError(Exception):
    """Raised when behavioral tests don't properly exercise expected artifacts."""
    pass


def extract_test_files_from_command(command: List[str]) -> List[str]:
    """
    Extract test file paths from a pytest command.

    Args:
        command: List of command components (e.g., ["pytest", "tests/test_example.py", "-v"])
        or a single string that needs splitting (e.g., "pytest tests/test_example.py")

    Returns:
        List of test file paths found in the command
    """
    # Handle if command is a single string that needs splitting
    if isinstance(command, str):
        command = command.split()

    # Handle if the command is a single-element list with a string to split
    if len(command) == 1 and " " in command[0]:
        command = command[0].split()

    if not command or command[0] not in ["pytest", "python", "uv"]:
        # Also check if pytest might come later (e.g., ["python", "-m", "pytest"])
        if len(command) > 2 and command[2] == "pytest":
            pass  # Continue processing
        else:
            return []

    test_files = []

    # Skip the command itself and any flags
    i = 0
    while i < len(command):
        arg = command[i]

        # Skip the executable and module invocations
        if arg in ["pytest", "python", "uv", "run", "-m"]:
            i += 1
            continue

        # Skip flags and their arguments
        if arg.startswith("-"):
            # Some flags take an argument
            if arg in ["-c", "-o", "-W", "-p", "--cov", "--cov-report",
                      "--cov-config", "--basetemp", "--junit-xml", "--log-file"]:
                i += 2  # Skip flag and its argument
            else:
                i += 1
            continue

        # Check if this looks like a test file or directory
        if arg.endswith(".py"):
            test_files.append(arg)
        elif os.path.isdir(arg):
            # If it's a directory, find all test files in it
            test_files.extend(_discover_test_files_in_directory(arg))
        elif "test" in arg.lower() and not arg.startswith("-"):
            # Might be a test module or directory path without extension
            if os.path.isdir(arg):
                test_files.extend(_discover_test_files_in_directory(arg))
            elif os.path.exists(f"{arg}.py"):
                test_files.append(f"{arg}.py")
            elif os.path.exists(arg):  # Maybe it's already a valid path
                test_files.append(arg)

        i += 1

    return test_files


def _discover_test_files_in_directory(directory: str) -> List[str]:
    """
    Discover all test files in a directory.

    Args:
        directory: Path to directory to search

    Returns:
        List of test file paths
    """
    test_files = []
    path = Path(directory)

    if path.exists() and path.is_dir():
        # Find all test_*.py files
        for test_file in path.glob("**/test_*.py"):
            test_files.append(str(test_file))

        # Also find *_test.py files
        for test_file in path.glob("**/*_test.py"):
            if str(test_file) not in test_files:
                test_files.append(str(test_file))

    return sorted(test_files)


def validate_behavioral_tests(manifest: Dict[str, Any], use_manifest_chain: bool = False) -> Optional[Dict]:
    """
    Validate that behavioral tests exercise the expected artifacts.

    Args:
        manifest: Manifest dictionary containing expectedArtifacts and validationCommand
        use_manifest_chain: Whether to use manifest chain for validation

    Returns:
        Dictionary with validation results or None if no validationCommand

    Raises:
        BehavioralTestValidationError: If tests don't properly exercise expected artifacts
    """
    # Check if manifest has validationCommand
    validation_command = manifest.get("validationCommand")
    if not validation_command:
        return None

    # Extract test files from command
    test_files = []
    if isinstance(validation_command, list):
        # Check if this is a list of separate commands (task-002 format)
        # e.g., ["pytest tests/test1.py", "pytest tests/test2.py"]
        if all(isinstance(cmd, str) and cmd.startswith("pytest ") for cmd in validation_command):
            # Each element is a complete pytest command as a string
            for cmd in validation_command:
                test_files.extend(extract_test_files_from_command(cmd.split()))
        elif isinstance(validation_command[0], list):
            # Multiple commands as lists
            for cmd in validation_command:
                test_files.extend(extract_test_files_from_command(cmd))
        else:
            # Single command as list
            test_files.extend(extract_test_files_from_command(validation_command))

    if not test_files:
        raise BehavioralTestValidationError(
            f"No test files could be extracted from validationCommand: {validation_command}"
        )

    # Get expected artifacts
    expected_artifacts = manifest.get("expectedArtifacts", {})
    if not expected_artifacts:
        return {"validation_passed": True, "message": "No expectedArtifacts to validate"}

    # For behavioral validation, we need to check if the tests USE the artifacts
    # We'll track which artifacts are found across ALL test files
    errors = []
    validated_files = []
    artifacts_to_find = expected_artifacts.get("contains", [])
    artifacts_found = set()  # Track which artifacts have been found

    # First, check that all test files exist
    for test_file in test_files:
        if not os.path.exists(test_file):
            errors.append(f"Test file not found: {test_file}")

    if errors:
        raise BehavioralTestValidationError(
            f"Test file validation errors:\n" + "\n".join(errors)
        )

    # Check each test file and collect which artifacts it uses
    for test_file in test_files:
        # Create a manifest copy that points to the test file
        test_manifest = {
            "expectedArtifacts": {
                "file": test_file,  # Point to the test file instead
                "contains": artifacts_to_find  # Check all artifacts
            }
        }

        # Try to validate this test file, collecting which artifacts it has
        for artifact in artifacts_to_find:
            single_artifact_manifest = {
                "expectedArtifacts": {
                    "file": test_file,
                    "contains": [artifact]
                }
            }

            try:
                # Check if this specific artifact is used in this test file
                validate_with_ast(
                    single_artifact_manifest,
                    test_file,
                    use_manifest_chain=use_manifest_chain,
                    validation_mode="behavioral"
                )
                # Mark this artifact as found
                artifact_key = f"{artifact.get('type')}:{artifact.get('name')}"
                if artifact.get('class'):
                    artifact_key += f":{artifact.get('class')}"
                artifacts_found.add(artifact_key)
            except AlignmentError:
                # This artifact isn't in this file, that's okay - might be in another
                pass

        validated_files.append(test_file)

    # Check if all artifacts were found across all test files
    missing_artifacts = []
    for artifact in artifacts_to_find:
        artifact_key = f"{artifact.get('type')}:{artifact.get('name')}"
        if artifact.get('class'):
            artifact_key += f":{artifact.get('class')}"
        if artifact_key not in artifacts_found:
            missing_artifacts.append(
                f"{artifact.get('type')} '{artifact.get('name')}'" +
                (f" in class {artifact.get('class')}" if artifact.get('class') else "")
            )

    if missing_artifacts:
        raise BehavioralTestValidationError(
            f"Behavioral tests don't properly exercise expected artifacts:\n" +
            f"Missing artifacts not used in any test file:\n" +
            "\n".join(f"  - {artifact}" for artifact in missing_artifacts)
        )

    return {
        "validation_passed": True,
        "validated_files": validated_files,
        "message": f"All {len(validated_files)} test file(s) properly exercise expected artifacts"
    }


def validate_all_manifests(manifests_dir: str) -> Dict[str, Dict]:
    """
    Validate behavioral tests for all manifests in a directory.

    Args:
        manifests_dir: Path to directory containing manifest files

    Returns:
        Dictionary mapping manifest paths to validation results
    """
    results = {}
    manifest_dir = Path(manifests_dir)

    if not manifest_dir.exists():
        raise ValueError(f"Manifests directory not found: {manifests_dir}")

    # Find all task manifests
    for manifest_path in sorted(manifest_dir.glob("task-*.manifest.json")):
        with open(manifest_path, "r") as f:
            manifest = json.load(f)

        # Check if it has a validationCommand
        has_validation = "validationCommand" in manifest

        if has_validation:
            try:
                result = validate_behavioral_tests(manifest)
                results[str(manifest_path)] = {
                    "has_validation_command": True,
                    "validation_passed": True,
                    "result": result
                }
            except BehavioralTestValidationError as e:
                results[str(manifest_path)] = {
                    "has_validation_command": True,
                    "validation_passed": False,
                    "error": str(e)
                }
            except Exception as e:
                results[str(manifest_path)] = {
                    "has_validation_command": True,
                    "validation_passed": False,
                    "error": f"Unexpected error: {str(e)}"
                }
        else:
            results[str(manifest_path)] = {
                "has_validation_command": False,
                "validation_passed": None,
                "message": "No validationCommand in manifest"
            }

    return results


if __name__ == "__main__":
    # CLI interface for testing
    import sys

    if len(sys.argv) < 2:
        print("Usage: python validate_behavioral_tests.py <manifest_path>")
        sys.exit(1)

    manifest_path = sys.argv[1]

    try:
        with open(manifest_path, "r") as f:
            manifest = json.load(f)

        result = validate_behavioral_tests(manifest)
        if result:
            print(f"✓ Behavioral test validation passed: {result['message']}")
        else:
            print("No validationCommand in manifest")

    except BehavioralTestValidationError as e:
        print(f"✗ Behavioral test validation failed:\n{e}")
        sys.exit(1)
    except Exception as e:
        print(f"✗ Error: {e}")
        sys.exit(1)