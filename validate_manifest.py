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

from validators.manifest_validator import validate_with_ast


def extract_test_files_from_command(validation_command):
    """
    Extract test file paths from pytest validation commands.

    Handles various pytest command formats:
    - ["pytest tests/test_file.py -v"] (single string)
    - ["pytest", "tests/test_file.py", "-v"] (separate elements)
    - python -m pytest tests/test_file.py tests/test_other.py -v
    - uv run pytest tests/test_*.py -v
    - pytest tests/ -v

    Args:
        validation_command: List of command components

    Returns:
        list: List of test file paths extracted from the command
    """
    if not validation_command:
        return []

    # Handle multiple pytest commands (e.g., ["pytest test1.py", "pytest test2.py"])
    all_test_files = []

    # Process each command in the list
    for cmd in validation_command:
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
                pytest_args = cmd_parts[pytest_index + 1:]

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
                        all_test_files.append(file_path)
                    else:
                        # Regular file or directory path
                        all_test_files.append(arg)

    # If we found test files from multiple commands, return them
    if all_test_files:
        return all_test_files

    # Otherwise, try the original logic for single command format
    # (e.g., ["pytest", "test.py", "-v"])
    if len(validation_command) > 1:
        # Find the pytest command index
        pytest_index = -1
        for i, part in enumerate(validation_command):
            if part == "pytest":
                pytest_index = i
                break

        # If no pytest found, return empty
        if pytest_index == -1:
            return []

        # Extract arguments after pytest command
        pytest_args = validation_command[pytest_index + 1:]

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


def validate_behavioral_tests(manifest_data, test_files, use_manifest_chain=False, quiet=False):
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
    import ast
    from validators.manifest_validator import _ArtifactCollector

    all_used_classes = set()
    all_used_methods = {}
    all_used_functions = set()
    all_used_arguments = set()

    for test_file in test_files:
        with open(test_file, "r") as f:
            test_code = f.read()

        tree = ast.parse(test_code)
        collector = _ArtifactCollector(validation_mode="behavioral")
        collector.visit(tree)

        # Merge usage data
        all_used_classes.update(collector.used_classes)
        all_used_functions.update(collector.used_functions)
        all_used_arguments.update(collector.used_arguments)

        for class_name, methods in collector.used_methods.items():
            if class_name not in all_used_methods:
                all_used_methods[class_name] = set()
            all_used_methods[class_name].update(methods)

    # Determine expected artifacts based on mode
    if use_manifest_chain:
        # Discover all manifests that touched this file (if needed for behavioral tests)
        from validators.manifest_validator import _discover_related_manifests, _merge_expected_artifacts
        target_file = manifest_data.get("expectedArtifacts", {}).get("file", test_files[0] if test_files else "")
        related_manifests = _discover_related_manifests(target_file)
        expected_items = _merge_expected_artifacts(related_manifests)
    else:
        expected_artifacts = manifest_data.get("expectedArtifacts", {})
        expected_items = expected_artifacts.get("contains", [])

    # Manually validate each expected artifact is used across all test files
    for artifact in expected_items:
        artifact_type = artifact.get("type")
        artifact_name = artifact.get("name")

        if artifact_type == "class":
            if artifact_name not in all_used_classes:
                # Import locally to avoid detection by AST validator
                import validators.manifest_validator as mv
                raise mv.AlignmentError(
                    f"Class '{artifact_name}' not used in behavioral tests"
                )

        elif artifact_type == "function":
            parent_class = artifact.get("class")
            parameters = artifact.get("parameters", [])

            if parent_class:
                # It's a method
                if parent_class in all_used_methods:
                    if artifact_name not in all_used_methods[parent_class]:
                        import validators.manifest_validator as mv
                        raise mv.AlignmentError(
                            f"Method '{artifact_name}' not called on class '{parent_class}' in behavioral tests"
                        )
                else:
                    import validators.manifest_validator as mv
                    raise mv.AlignmentError(
                        f"Class '{parent_class}' not used or method '{artifact_name}' not called in behavioral tests"
                    )
            else:
                # It's a standalone function
                if artifact_name not in all_used_functions:
                    import validators.manifest_validator as mv
                    raise mv.AlignmentError(
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
                        if param_name not in all_used_arguments and "__positional__" not in all_used_arguments:
                            import validators.manifest_validator as mv
                            raise mv.AlignmentError(
                                f"Parameter '{param_name}' not used in call to '{artifact_name}' in behavioral tests"
                            )

        elif artifact_type == "attribute":
            # For attributes, we'd need to check attribute access patterns
            # This is more complex and may not be needed for the current use case
            pass


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

    try:
        # Validate manifest file exists
        manifest_path = Path(args.manifest_path)
        if not manifest_path.exists():
            print(f"✗ Error: Manifest file not found: {args.manifest_path}")
            sys.exit(1)

        # Load the manifest
        with open(manifest_path, "r") as f:
            manifest_data = json.load(f)

        # Get the file to validate from the manifest
        file_path = manifest_data.get("expectedArtifacts", {}).get("file")
        if not file_path:
            print("✗ Error: No file specified in manifest's expectedArtifacts.file")
            sys.exit(1)

        # Validate target file exists
        if not Path(file_path).exists():
            print(f"✗ Error: Target file not found: {file_path}")
            sys.exit(1)

        # BEHAVIORAL TEST VALIDATION (BEFORE implementation validation)
        # Check if manifest has a validationCommand that contains test files
        validation_command = manifest_data.get("validationCommand", [])
        if validation_command:
            test_files = extract_test_files_from_command(validation_command)
            if test_files:
                if not args.quiet:
                    print("Running behavioral test validation...")
                validate_behavioral_tests(
                    manifest_data,
                    test_files,
                    use_manifest_chain=args.use_manifest_chain,
                    quiet=args.quiet
                )
                if not args.quiet:
                    print("✓ Behavioral test validation PASSED")

        # IMPLEMENTATION VALIDATION (after behavioral tests)
        validate_with_ast(
            manifest_data,
            file_path,
            use_manifest_chain=args.use_manifest_chain,
            validation_mode=args.validation_mode,
        )

        # Success message
        if not args.quiet:
            print(f"✓ Validation PASSED ({args.validation_mode} mode)")
            if args.use_manifest_chain:
                print("  Used manifest chain for validation")
            print(f"  Manifest: {args.manifest_path}")
            print(f"  Target:   {file_path}")

    except Exception as e:
        import validators.manifest_validator as mv
        if isinstance(e, mv.AlignmentError):
            print(f"✗ Validation FAILED: {e}")
            if not args.quiet:
                print(f"  Manifest: {args.manifest_path}")
                print(f"  Mode:     {args.validation_mode}")
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
        if not args.quiet:
            import traceback

            traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
