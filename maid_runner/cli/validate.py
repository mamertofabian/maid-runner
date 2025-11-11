#!/usr/bin/env python3
"""
Command-line interface for MAID manifest validation.

This script provides a clean CLI for validating manifests against implementation
or behavioral test files using the enhanced AST validator.
"""

import argparse
import json
import sys
from pathlib import Path

from maid_runner.validators.manifest_validator import validate_with_ast


def extract_test_files_from_command(validation_command) -> list:
    """
    Extract test file paths from pytest validation commands.

    Handles various pytest command formats:
    - ["pytest tests/test_file.py -v"] (single string)
    - ["pytest", "tests/test_file.py", "-v"] (separate elements)
    - [["pytest", "test1.py"], ["pytest", "test2.py"]] (validationCommands format)
    - python -m pytest tests/test_file.py tests/test_other.py -v
    - uv run pytest tests/test_*.py -v
    - pytest tests/ -v

    Args:
        validation_command: List of command components (legacy format)
                          OR array of command arrays (enhanced format)

    Returns:
        list: List of test file paths extracted from the command(s)
    """
    if not validation_command:
        return []

    all_test_files = []

    # Check if this is the enhanced format (array of arrays)
    if validation_command and isinstance(validation_command[0], list):
        # Enhanced format: validationCommands = [["pytest", "test1.py"], ["pytest", "test2.py"]]
        for cmd_array in validation_command:
            test_files = _extract_from_single_command(cmd_array)
            all_test_files.extend(test_files)
        return all_test_files
    else:
        # Legacy format: validationCommand = ["pytest", "test.py", "-v"]
        return _extract_from_single_command(validation_command)


def _extract_from_single_command(command) -> list:
    """
    Extract test files from a single command array.

    Args:
        command: List of command components (e.g., ["pytest", "test.py", "-v"])

    Returns:
        list: List of test file paths
    """
    if not command:
        return []

    test_files = []

    # Handle multiple pytest commands as strings (e.g., ["pytest test1.py", "pytest test2.py"])
    for cmd in command:
        if isinstance(cmd, str) and "pytest" in cmd:
            # Split if it's a single string command
            cmd_parts = cmd.split() if " " in cmd else [cmd]

            # Find pytest index in this command
            pytest_index = -1
            for i, part in enumerate(cmd_parts):
                if part == "pytest":
                    pytest_index = i
                    break

            if pytest_index != -1:
                # Extract arguments after pytest
                pytest_args = cmd_parts[pytest_index + 1 :]

                # Extract test files from this command's args
                for arg in pytest_args:
                    # Skip pytest flags (start with -)
                    if arg.startswith("-"):
                        continue

                    # Skip common pytest options that take values
                    if arg in ["--tb", "--cov", "--maxfail", "--timeout"]:
                        continue

                    # Extract file path from node IDs (file::class::method)
                    if "::" in arg:
                        file_path = arg.split("::")[0]
                        test_files.append(file_path)
                    else:
                        # Regular file or directory path
                        test_files.append(arg)

    # If we found test files from string commands, return them
    if test_files:
        return test_files

    # Otherwise, try the original logic for single command format
    # (e.g., ["pytest", "test.py", "-v"])
    if len(command) > 1:
        # Find the pytest command index
        pytest_index = -1
        for i, part in enumerate(command):
            if part == "pytest":
                pytest_index = i
                break

        # If no pytest found, return empty
        if pytest_index == -1:
            return []

        # Extract arguments after pytest command
        pytest_args = command[pytest_index + 1 :]

        # Filter out pytest flags and options, keep only file/directory paths
        test_files = []
        for arg in pytest_args:
            # Skip pytest flags (start with -)
            if arg.startswith("-"):
                continue

            # Skip common pytest options that take values
            if arg in ["--tb", "--cov", "--maxfail", "--timeout"]:
                continue

            # Extract file path from node IDs (file::class::method)
            if "::" in arg:
                file_path = arg.split("::")[0]
                test_files.append(file_path)
            else:
                # Regular file or directory path
                test_files.append(arg)

        return test_files

    return []


def validate_behavioral_tests(
    manifest_data, test_files, use_manifest_chain=False, quiet=False
):
    """
    Validate that behavioral test files use the expected artifacts from the manifest.

    This function validates that test files collectively use all expected artifacts,
    allowing different test files to exercise different parts of the API.

    Args:
        manifest_data: Dictionary containing the manifest with expectedArtifacts
        test_files: List of test file paths to validate
        use_manifest_chain: If True, use manifest chain for validation
        quiet: If True, suppress success messages

    Raises:
        AlignmentError: If test files don't exercise the expected artifacts
        FileNotFoundError: If test files don't exist
    """
    if not test_files:
        return  # No test files to validate

    # Validate each test file exists
    for test_file in test_files:
        if not Path(test_file).exists():
            raise FileNotFoundError(f"Test file not found: {test_file}")

    # Collect usage data from all test files
    from maid_runner.validators.manifest_validator import (
        collect_behavioral_artifacts,
        should_skip_behavioral_validation,
    )

    all_used_classes = set()
    all_used_methods = {}
    all_used_functions = set()
    all_used_arguments = set()

    for test_file in test_files:
        artifacts = collect_behavioral_artifacts(test_file)

        # Merge usage data
        all_used_classes.update(artifacts["used_classes"])
        all_used_functions.update(artifacts["used_functions"])
        all_used_arguments.update(artifacts["used_arguments"])

        for class_name, methods in artifacts["used_methods"].items():
            if class_name not in all_used_methods:
                all_used_methods[class_name] = set()
            all_used_methods[class_name].update(methods)

    # For behavioral validation, we only validate artifacts from the current manifest
    # NOT the merged artifacts from the manifest chain
    # The tests for each task should only use the artifacts that task declares
    # The use_manifest_chain parameter is ignored for behavioral validation
    expected_artifacts = manifest_data.get("expectedArtifacts", {})
    expected_items = expected_artifacts.get("contains", [])

    # Manually validate each expected artifact is used across all test files
    for artifact in expected_items:
        # Check for 'self' parameter before skipping artifacts
        # This validation must occur even for private methods like __init__
        if artifact.get("type") == "function":
            parameters = artifact.get("args") or artifact.get("parameters", [])
            if parameters:
                for param in parameters:
                    if param.get("name") == "self":
                        from maid_runner.validators.manifest_validator import (
                            AlignmentError,
                        )

                        raise AlignmentError(
                            f"Manifest error: Parameter 'self' should not be explicitly declared "
                            f"in method '{artifact.get('name')}'. In Python, 'self' is implicit for instance methods "
                            f"and is not included in artifact declarations. Remove 'self' from the parameters list."
                        )

        # Skip type-only artifacts in behavioral validation
        if should_skip_behavioral_validation(artifact):
            continue

        artifact_type = artifact.get("type")
        artifact_name = artifact.get("name")

        if artifact_type == "class":
            if artifact_name not in all_used_classes:
                from maid_runner.validators.manifest_validator import AlignmentError

                raise AlignmentError(
                    f"Class '{artifact_name}' not used in behavioral tests"
                )

        elif artifact_type == "function":
            parent_class = artifact.get("class")
            # Support both args (enhanced) and parameters (legacy)
            parameters = artifact.get("args") or artifact.get("parameters", [])

            if parent_class:
                # It's a method
                if parent_class in all_used_methods:
                    if artifact_name not in all_used_methods[parent_class]:
                        from maid_runner.validators.manifest_validator import (
                            AlignmentError,
                        )

                        raise AlignmentError(
                            f"Method '{artifact_name}' not called on class '{parent_class}' in behavioral tests"
                        )
                else:
                    from maid_runner.validators.manifest_validator import AlignmentError

                    raise AlignmentError(
                        f"Class '{parent_class}' not used or method '{artifact_name}' not called in behavioral tests"
                    )
            else:
                # It's a standalone function
                if artifact_name not in all_used_functions:
                    from maid_runner.validators.manifest_validator import AlignmentError

                    raise AlignmentError(
                        f"Function '{artifact_name}' not called in behavioral tests"
                    )

            # Validate parameters were used (if specified)
            if parameters:
                # Check if any of the expected parameters were used as keyword arguments
                for param in parameters:
                    param_name = param.get("name")
                    if param_name:
                        # Check if this specific parameter was used as a keyword argument
                        # Or if positional arguments were provided (which we can't verify individually)
                        if (
                            param_name not in all_used_arguments
                            and "__positional__" not in all_used_arguments
                        ):
                            from maid_runner.validators.manifest_validator import (
                                AlignmentError,
                            )

                            raise AlignmentError(
                                f"Parameter '{param_name}' not used in call to '{artifact_name}' in behavioral tests"
                            )

        elif artifact_type == "attribute":
            # For attributes, we'd need to check attribute access patterns
            # This is more complex and may not be needed for the current use case
            pass


def run_validation(
    manifest_path: str,
    validation_mode: str = "implementation",
    use_manifest_chain: bool = False,
    quiet: bool = False,
) -> None:
    """Core validation logic accepting parsed arguments.

    Args:
        manifest_path: Path to the manifest JSON file
        validation_mode: Validation mode ('implementation' or 'behavioral')
        use_manifest_chain: If True, use manifest chain to merge related manifests
        quiet: If True, suppress success messages

    Raises:
        SystemExit: Exits with code 0 on success, 1 on failure
    """

    try:
        # Validate manifest file exists
        manifest_path_obj = Path(manifest_path)
        if not manifest_path_obj.exists():
            print(f"✗ Error: Manifest file not found: {manifest_path}")
            sys.exit(1)

        # Load the manifest
        with open(manifest_path_obj, "r") as f:
            manifest_data = json.load(f)

        # Validate version field
        from maid_runner.utils import validate_manifest_version

        try:
            validate_manifest_version(manifest_data, manifest_path_obj.name)
        except ValueError as e:
            print(f"✗ Error: {e}", file=sys.stderr)
            sys.exit(1)

        # Snapshot manifests must have comprehensive validationCommands
        # Check this early, before file validation
        # Support both legacy (validationCommand) and enhanced (validationCommands) formats
        validation_command = manifest_data.get("validationCommand", [])
        validation_commands = manifest_data.get("validationCommands", [])
        has_validation = bool(validation_command or validation_commands)

        if manifest_data.get("taskType") == "snapshot" and not has_validation:
            print(
                f"✗ Error: Snapshot manifest {manifest_path_obj.name} must have a comprehensive "
                f"validationCommand or validationCommands that tests all artifacts. Snapshot manifests document the "
                f"complete current state and must validate all artifacts."
            )
            sys.exit(1)

        # Get the file to validate from the manifest
        file_path = manifest_data.get("expectedArtifacts", {}).get("file")
        if not file_path:
            print("✗ Error: No file specified in manifest's expectedArtifacts.file")
            sys.exit(1)

        # BEHAVIORAL TEST VALIDATION
        # In behavioral mode, we validate test structure, not implementation
        # Support both legacy (validationCommand) and enhanced (validationCommands) formats
        validation_commands = manifest_data.get("validationCommands", [])
        if not validation_commands:
            validation_commands = manifest_data.get("validationCommand", [])

        if validation_mode == "behavioral":
            # Behavioral mode: Check test files exist and USE artifacts
            if validation_commands:
                test_files = extract_test_files_from_command(validation_commands)
                if test_files:
                    # Validate test files exist
                    missing_test_files = []
                    for test_file in test_files:
                        if not Path(test_file).exists():
                            missing_test_files.append(test_file)

                    if missing_test_files:
                        print(
                            f"✗ Error: Test file(s) not found: {', '.join(missing_test_files)}"
                        )
                        sys.exit(1)

                    if not quiet:
                        print("Running behavioral test validation...")
                    validate_behavioral_tests(
                        manifest_data,
                        test_files,
                        use_manifest_chain=use_manifest_chain,
                        quiet=quiet,
                    )
                    if not quiet:
                        print("✓ Behavioral test validation PASSED")
                else:
                    if not quiet:
                        print("⚠ Warning: No test files found in validationCommand")
            else:
                if not quiet:
                    print(
                        "⚠ Warning: No validationCommand specified for behavioral validation"
                    )
        else:
            # Implementation mode: Check implementation file exists and DEFINES artifacts
            if not Path(file_path).exists():
                print(f"✗ Error: Target file not found: {file_path}")
                print()
                print(
                    "⚠️  Hint: If you're validating a manifest before implementing the code (MAID Phase 2),"
                )
                print(
                    "   you should use behavioral validation to check the test structure:"
                )
                print()
                print(
                    f"   uv run maid validate {manifest_path} --validation-mode behavioral"
                )
                print()
                print("   Implementation validation requires the target file to exist.")
                sys.exit(1)

            # Also run behavioral test validation if validation commands are present
            if validation_commands:
                test_files = extract_test_files_from_command(validation_commands)
                if test_files:
                    if not quiet:
                        print("Running behavioral test validation...")
                    validate_behavioral_tests(
                        manifest_data,
                        test_files,
                        use_manifest_chain=use_manifest_chain,
                        quiet=quiet,
                    )
                    if not quiet:
                        print("✓ Behavioral test validation PASSED")

            # IMPLEMENTATION VALIDATION
            validate_with_ast(
                manifest_data,
                file_path,
                use_manifest_chain=use_manifest_chain,
                validation_mode=validation_mode,
            )

        # Success message
        if not quiet:
            print(f"✓ Validation PASSED ({validation_mode} mode)")
            if use_manifest_chain:
                # Check if this is a snapshot (snapshots skip chain merging)
                is_snapshot = manifest_data.get("taskType") == "snapshot"
                if is_snapshot:
                    print("  Snapshot manifest (chain skipped)")
                else:
                    print("  Used manifest chain for validation")

            print(f"  Manifest: {manifest_path}")
            print(f"  Target:   {file_path}")

        # Display metadata if present (outside conditional for consistent display)
        metadata = manifest_data.get("metadata")
        if metadata:
            if metadata.get("author"):
                print(f"  Author:   {metadata['author']}")
            if metadata.get("tags"):
                tags_str = ", ".join(metadata["tags"])
                print(f"  Tags:     {tags_str}")
            if metadata.get("priority"):
                print(f"  Priority: {metadata['priority']}")

    except Exception as e:
        from maid_runner.validators.manifest_validator import AlignmentError

        if isinstance(e, AlignmentError):
            print(f"✗ Validation FAILED: {e}")
            if not quiet:
                print(f"  Manifest: {manifest_path}")
                print(f"  Mode:     {validation_mode}")
            sys.exit(1)
        else:
            # Re-raise if it's not an AlignmentError
            raise

    except json.JSONDecodeError as e:
        print(f"✗ Error: Invalid JSON in manifest file: {e}")
        sys.exit(1)

    except FileNotFoundError as e:
        print(f"✗ Error: File not found: {e}")
        sys.exit(1)

    except Exception as e:
        print(f"✗ Unexpected error: {e}")
        if not quiet:
            import traceback

            traceback.print_exc()
        sys.exit(1)


def main():
    """Main CLI entry point."""
    parser = argparse.ArgumentParser(
        description="Validate manifest against implementation or behavioral test files",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Validate implementation (default mode)
  %(prog)s manifests/task-001.manifest.json

  # Validate behavioral test usage
  %(prog)s manifests/task-001.manifest.json --validation-mode behavioral

  # Use manifest chain for complex validation
  %(prog)s manifests/task-001.manifest.json --use-manifest-chain

  # Combined behavioral + manifest chain
  %(prog)s manifests/task-001.manifest.json --validation-mode behavioral --use-manifest-chain

Validation Modes:
  implementation  - Validates that code DEFINES the expected artifacts (default)
  behavioral      - Validates that tests USE/CALL the expected artifacts

This enables MAID Phase 2 validation: manifest ↔ behavioral test alignment!
        """,
    )

    parser.add_argument("manifest_path", help="Path to the manifest JSON file")

    parser.add_argument(
        "--validation-mode",
        choices=["implementation", "behavioral"],
        default="implementation",
        help="Validation mode: 'implementation' (default) checks definitions, 'behavioral' checks usage",
    )

    parser.add_argument(
        "--use-manifest-chain",
        action="store_true",
        help="Use manifest chain to merge all related manifests",
    )

    parser.add_argument(
        "--quiet",
        "-q",
        action="store_true",
        help="Only output errors (suppress success messages)",
    )

    args = parser.parse_args()
    run_validation(
        args.manifest_path,
        args.validation_mode,
        args.use_manifest_chain,
        args.quiet,
    )


if __name__ == "__main__":
    main()
