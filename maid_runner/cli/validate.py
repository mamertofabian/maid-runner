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
from typing import Optional, List, Dict, Set, Any

import jsonschema

from maid_runner.validators.manifest_validator import validate_with_ast, validate_schema
from maid_runner.validators.semantic_validator import (
    validate_manifest_semantics,
    ManifestSemanticError,
)
from maid_runner.validators.file_tracker import analyze_file_tracking


def _format_file_tracking_output(
    analysis: dict,
    quiet: bool = False,
    validation_summary: Optional[str] = None,
) -> None:
    """Format and print file tracking analysis warnings (internal helper).

    Args:
        analysis: FileTrackingAnalysis dictionary with undeclared, registered, tracked
        quiet: If True, only show summary
        validation_summary: Optional validation summary to display at the top
    """
    undeclared = analysis.get("undeclared", [])
    registered = analysis.get("registered", [])
    tracked = analysis.get("tracked", [])
    untracked_tests = analysis.get("untracked_tests", [])

    total_files = (
        len(undeclared) + len(registered) + len(tracked) + len(untracked_tests)
    )

    if total_files == 0:
        return  # No files to report

    # Only show if there are warnings
    if undeclared or registered or untracked_tests:
        print()
        print("━" * 80)
        print("FILE TRACKING ANALYSIS")
        print("━" * 80)
        print()

    # UNDECLARED files (high priority)
    if undeclared:
        print(f"🔴 UNDECLARED FILES ({len(undeclared)} files)")
        print("  Files exist in codebase but are not tracked in any manifest")
        print()

        if not quiet:
            for file_info in undeclared[:10]:  # Limit to 10 for readability
                print(f"  - {file_info['file']}")
                for issue in file_info["issues"]:
                    print(f"    → {issue}")

            if len(undeclared) > 10:
                print(f"  ... and {len(undeclared) - 10} more")

        print()
        print(
            "  Action: Add these files to creatableFiles or editableFiles in a manifest"
        )
        print()

    # REGISTERED files (medium priority)
    if registered:
        print(f"🟡 REGISTERED FILES ({len(registered)} files)")
        print("  Files are tracked but not fully MAID-compliant")
        print()

        if not quiet:
            for file_info in registered[:10]:  # Limit to 10 for readability
                print(f"  - {file_info['file']}")
                for issue in file_info["issues"]:
                    print(f"    ⚠️  {issue}")
                print(f"    Manifests: {', '.join(file_info['manifests'][:3])}")

            if len(registered) > 10:
                print(f"  ... and {len(registered) - 10} more")

        print()
        print(
            "  Action: Add expectedArtifacts and validationCommand for full compliance"
        )
        print()

    # UNTRACKED TEST FILES (informational)
    if untracked_tests:
        print(f"🔵 UNTRACKED TEST FILES ({len(untracked_tests)} files)")
        print("  Test files not referenced in any manifest")
        print()

        if not quiet:
            for test_file in untracked_tests[:10]:  # Limit to 10 for readability
                print(f"  - {test_file}")

            if len(untracked_tests) > 10:
                print(f"  ... and {len(untracked_tests) - 10} more")

        print()
        print("  Note: Consider adding to readonlyFiles for reference tracking")
        print()

    # Summary
    if undeclared or registered or untracked_tests:
        print(f"✓ TRACKED ({len(tracked)} files)")
        print("  All other source files are fully MAID-compliant")
        print()

        # Build summary string
        summary_parts = []
        if undeclared:
            summary_parts.append(f"{len(undeclared)} UNDECLARED")
        if registered:
            summary_parts.append(f"{len(registered)} REGISTERED")
        if untracked_tests:
            summary_parts.append(f"{len(untracked_tests)} UNTRACKED TESTS")
        summary_parts.append(f"{len(tracked)} TRACKED")

        # Show validation summary if provided
        if validation_summary:
            print(validation_summary)
        print(f"Summary: {', '.join(summary_parts)}")
        print()


def extract_test_files_from_command(validation_command: List[Any]) -> list:
    """Extract test file paths from pytest validation commands.

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
        List of test file paths extracted from the command(s)
    """
    if not validation_command:
        return []

    # Check if this is the enhanced format (array of arrays)
    if _is_enhanced_command_format(validation_command):
        return _extract_from_multiple_commands(validation_command)
    else:
        # Legacy format: validationCommand = ["pytest", "test.py", "-v"]
        return _extract_from_single_command(validation_command)


def _is_enhanced_command_format(validation_command: List[Any]) -> bool:
    """Check if validation command uses enhanced format (array of arrays).

    Args:
        validation_command: Command to check

    Returns:
        True if enhanced format, False otherwise
    """
    return bool(validation_command and isinstance(validation_command[0], list))


def _extract_from_multiple_commands(commands: List[List[str]]) -> List[str]:
    """Extract test files from multiple command arrays (enhanced format).

    Args:
        commands: List of command arrays

    Returns:
        Combined list of test file paths from all commands
    """
    all_test_files = []
    for cmd_array in commands:
        test_files = _extract_from_single_command(cmd_array)
        all_test_files.extend(test_files)
    return all_test_files


def _extract_from_single_command(command: List[str]) -> list:
    """Extract test files from a single command array.

    Args:
        command: List of command components (e.g., ["pytest", "test.py", "-v"])

    Returns:
        List of test file paths
    """
    if not command:
        return []

    # Handle multiple pytest commands as strings
    test_files = _extract_from_string_commands(command)
    if test_files:
        return test_files

    # Otherwise, try the standard list format
    return _extract_from_list_command(command)


def _extract_from_string_commands(command: List[str]) -> List[str]:
    """Extract test files from string-based pytest commands.

    Handles formats like: ["pytest test1.py", "pytest test2.py"]

    Args:
        command: List of command strings

    Returns:
        List of test file paths
    """
    test_files = []

    for cmd in command:
        if not isinstance(cmd, str) or "pytest" not in cmd:
            continue

        cmd_parts = cmd.split() if " " in cmd else [cmd]
        pytest_index = _find_pytest_index(cmd_parts)

        if pytest_index != -1:
            pytest_args = cmd_parts[pytest_index + 1 :]
            test_files.extend(_filter_test_paths_from_args(pytest_args))

    return test_files


def _extract_from_list_command(command: List[str]) -> List[str]:
    """Extract test files from list-based pytest command.

    Handles formats like: ["pytest", "test.py", "-v"]

    Args:
        command: List of command parts

    Returns:
        List of test file paths
    """
    if len(command) <= 1:
        return []

    pytest_index = _find_pytest_index(command)
    if pytest_index == -1:
        return []

    pytest_args = command[pytest_index + 1 :]
    return _filter_test_paths_from_args(pytest_args)


def _find_pytest_index(command_parts: List[str]) -> int:
    """Find the index of 'pytest' in command parts.

    Args:
        command_parts: List of command components

    Returns:
        Index of 'pytest' or -1 if not found
    """
    for i, part in enumerate(command_parts):
        if part == "pytest":
            return i
    return -1


def _filter_test_paths_from_args(pytest_args: List[str]) -> List[str]:
    """Filter test file/directory paths from pytest arguments.

    Args:
        pytest_args: List of pytest arguments

    Returns:
        List of test file/directory paths
    """
    PYTEST_OPTIONS_WITH_VALUES = {"--tb", "--cov", "--maxfail", "--timeout"}
    test_files = []

    for arg in pytest_args:
        # Skip pytest flags
        if arg.startswith("-"):
            continue

        # Skip common pytest options that take values
        if arg in PYTEST_OPTIONS_WITH_VALUES:
            continue

        # Extract file path from node IDs (file::class::method)
        if "::" in arg:
            file_path = arg.split("::")[0]
            test_files.append(file_path)
        else:
            # Regular file or directory path
            test_files.append(arg)

    return test_files


def _normalize_test_file_paths(test_files: List[str]) -> List[str]:
    """Normalize test file paths by removing redundant directory prefixes.

    Args:
        test_files: List of test file paths to normalize

    Returns:
        List of normalized test file paths
    """
    normalized_test_files = []
    project_name = Path.cwd().name

    for test_file in test_files:
        # Only normalize if the file doesn't exist as-is
        if "/" in test_file and not Path(test_file).exists():
            if test_file.startswith(f"{project_name}/"):
                potential_normalized = test_file[len(project_name) + 1 :]
                if Path(potential_normalized).exists():
                    test_file = potential_normalized
        normalized_test_files.append(test_file)

    return normalized_test_files


def _validate_test_files_exist(test_files: List[str]) -> None:
    """Validate that all test files exist on disk.

    Args:
        test_files: List of test file paths to check

    Raises:
        FileNotFoundError: If any test file doesn't exist
    """
    for test_file in test_files:
        if not Path(test_file).exists():
            raise FileNotFoundError(f"Test file not found: {test_file}")


def _collect_artifact_usage_from_tests(test_files: List[str]) -> Dict[str, Any]:
    """Collect artifact usage data from all test files.

    Args:
        test_files: List of test file paths to analyze

    Returns:
        Dictionary with usage data for classes, methods, functions, and arguments
    """
    from maid_runner.validators.manifest_validator import collect_behavioral_artifacts

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

    return {
        "used_classes": all_used_classes,
        "used_methods": all_used_methods,
        "used_functions": all_used_functions,
        "used_arguments": all_used_arguments,
    }


def _get_expected_artifacts(manifest_data: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Extract expected artifacts from manifest data.

    Args:
        manifest_data: Dictionary containing the manifest

    Returns:
        List of expected artifact definitions
    """
    expected_artifacts = manifest_data.get("expectedArtifacts", {})
    return expected_artifacts.get("contains", [])


def _validate_artifacts_usage(
    expected_items: List[Dict[str, Any]],
    usage_data: Dict[str, Any],
    should_skip_behavioral_validation,
) -> None:
    """Validate that all expected artifacts are used in tests.

    Args:
        expected_items: List of expected artifact definitions
        usage_data: Dictionary with usage data from tests
        should_skip_behavioral_validation: Function to check if artifact should be skipped

    Raises:
        AlignmentError: If any expected artifact is not used in tests
    """
    all_used_classes = usage_data["used_classes"]
    all_used_methods = usage_data["used_methods"]
    all_used_functions = usage_data["used_functions"]
    all_used_arguments = usage_data["used_arguments"]

    for artifact in expected_items:
        _validate_no_self_parameter(artifact)

        # Skip type-only artifacts in behavioral validation
        if should_skip_behavioral_validation(artifact):
            continue

        artifact_type = artifact.get("type")
        artifact_name = artifact.get("name")

        if artifact_type == "class":
            _validate_class_usage(artifact_name, all_used_classes)
        elif artifact_type == "function":
            _validate_function_usage(
                artifact,
                artifact_name,
                all_used_methods,
                all_used_functions,
                all_used_arguments,
            )


def _validate_no_self_parameter(artifact: Dict[str, Any]) -> None:
    """Validate that 'self' parameter is not explicitly declared in methods.

    Args:
        artifact: Artifact definition to check

    Raises:
        AlignmentError: If 'self' is explicitly declared
    """
    from maid_runner.validators.manifest_validator import AlignmentError

    if artifact.get("type") != "function":
        return

    parameters = artifact.get("args") or artifact.get("parameters", [])
    if not parameters:
        return

    for param in parameters:
        if param.get("name") == "self":
            raise AlignmentError(
                f"Manifest error: Parameter 'self' should not be explicitly declared "
                f"in method '{artifact.get('name')}'. In Python, 'self' is implicit for instance methods "
                f"and is not included in artifact declarations. Remove 'self' from the parameters list."
            )


def _validate_class_usage(artifact_name: str, all_used_classes: Set[str]) -> None:
    """Validate that a class artifact is used in tests.

    Args:
        artifact_name: Name of the class artifact
        all_used_classes: Set of classes used in tests

    Raises:
        AlignmentError: If class is not used in tests
    """
    from maid_runner.validators.manifest_validator import AlignmentError

    if artifact_name not in all_used_classes:
        raise AlignmentError(f"Class '{artifact_name}' not used in behavioral tests")


def _validate_function_usage(
    artifact: Dict[str, Any],
    artifact_name: str,
    all_used_methods: Dict[str, Set[str]],
    all_used_functions: Set[str],
    all_used_arguments: Set[str],
) -> None:
    """Validate that a function/method artifact is used in tests.

    Args:
        artifact: Artifact definition
        artifact_name: Name of the function/method
        all_used_methods: Dictionary of methods used per class
        all_used_functions: Set of standalone functions used
        all_used_arguments: Set of arguments used in calls

    Raises:
        AlignmentError: If function/method is not used correctly in tests
    """
    parent_class = artifact.get("class")
    parameters = artifact.get("args") or artifact.get("parameters", [])

    if parent_class:
        _validate_method_usage(artifact_name, parent_class, all_used_methods)
    else:
        _validate_standalone_function_usage(artifact_name, all_used_functions)

    # Validate parameters were used (if specified)
    if parameters:
        _validate_parameters_usage(parameters, artifact_name, all_used_arguments)


def _validate_method_usage(
    artifact_name: str, parent_class: str, all_used_methods: Dict[str, Set[str]]
) -> None:
    """Validate that a method is called on its class in tests.

    Args:
        artifact_name: Name of the method
        parent_class: Name of the parent class
        all_used_methods: Dictionary of methods used per class

    Raises:
        AlignmentError: If method is not called on class in tests
    """
    from maid_runner.validators.manifest_validator import AlignmentError

    if parent_class in all_used_methods:
        if artifact_name not in all_used_methods[parent_class]:
            raise AlignmentError(
                f"Method '{artifact_name}' not called on class '{parent_class}' in behavioral tests"
            )
    else:
        raise AlignmentError(
            f"Class '{parent_class}' not used or method '{artifact_name}' not called in behavioral tests"
        )


def _validate_standalone_function_usage(
    artifact_name: str, all_used_functions: Set[str]
) -> None:
    """Validate that a standalone function is called in tests.

    Args:
        artifact_name: Name of the function
        all_used_functions: Set of standalone functions used

    Raises:
        AlignmentError: If function is not called in tests
    """
    from maid_runner.validators.manifest_validator import AlignmentError

    if artifact_name not in all_used_functions:
        raise AlignmentError(
            f"Function '{artifact_name}' not called in behavioral tests"
        )


def _validate_parameters_usage(
    parameters: List[Dict[str, Any]], artifact_name: str, all_used_arguments: Set[str]
) -> None:
    """Validate that function parameters are used in test calls.

    Args:
        parameters: List of parameter definitions
        artifact_name: Name of the function/method
        all_used_arguments: Set of arguments used in calls

    Raises:
        AlignmentError: If parameter is not used in test calls
    """
    from maid_runner.validators.manifest_validator import AlignmentError

    for param in parameters:
        param_name = param.get("name")
        if not param_name:
            continue

        # Check if parameter was used as keyword argument or positionally
        if (
            param_name not in all_used_arguments
            and "__positional__" not in all_used_arguments
        ):
            raise AlignmentError(
                f"Parameter '{param_name}' not used in call to '{artifact_name}' in behavioral tests"
            )


def validate_behavioral_tests(
    manifest_data: Dict[str, Any],
    test_files: List[str],
    use_manifest_chain: bool = False,
    quiet: bool = False,
) -> None:
    """Validate that behavioral test files use the expected artifacts from the manifest.

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
        return

    test_files = _normalize_test_file_paths(test_files)
    _validate_test_files_exist(test_files)

    from maid_runner.validators.manifest_validator import (
        should_skip_behavioral_validation,
    )

    usage_data = _collect_artifact_usage_from_tests(test_files)

    expected_items = _get_expected_artifacts(manifest_data)
    _validate_artifacts_usage(
        expected_items, usage_data, should_skip_behavioral_validation
    )


def _run_directory_validation(
    manifest_dir: str,
    validation_mode: str,
    use_manifest_chain: bool,
    quiet: bool,
) -> None:
    """Validate all manifests in a directory.

    Args:
        manifest_dir: Path to directory containing manifests
        validation_mode: Validation mode ('implementation' or 'behavioral')
        use_manifest_chain: If True, use manifest chain to merge related manifests
        quiet: If True, suppress success messages

    Raises:
        SystemExit: Exits with code 0 on success, 1 on failure
    """
    import os
    from maid_runner.utils import (
        get_superseded_manifests,
        print_maid_not_enabled_message,
        print_no_manifests_found_message,
    )

    manifests_dir = Path(manifest_dir).resolve()

    if not manifests_dir.exists():
        print_maid_not_enabled_message(str(manifest_dir))
        sys.exit(0)

    manifest_files = sorted(manifests_dir.glob("task-*.manifest.json"))
    if not manifest_files:
        print_no_manifests_found_message(str(manifest_dir))
        sys.exit(0)

    # Get superseded manifests and filter them out
    superseded = get_superseded_manifests(manifests_dir)
    active_manifests = [m for m in manifest_files if m not in superseded]

    if not active_manifests:
        print("⚠️  No active manifest files found")
        sys.exit(0)

    if superseded and not quiet:
        print(f"⏭️  Skipping {len(superseded)} superseded manifest(s)\n")

    # Change to project root directory for validation
    # This ensures relative paths in manifests are resolved correctly
    project_root = manifests_dir.parent
    original_cwd = os.getcwd()
    os.chdir(project_root)

    total_passed = 0
    total_failed = 0
    manifests_with_failures = []

    try:
        for manifest_path in active_manifests:
            if not quiet:
                print(f"📋 Validating {manifest_path.name}...")

            # Validate this manifest using the single-manifest validation logic
            # We'll capture the exit by catching SystemExit
            try:
                run_validation(
                    manifest_path=str(manifest_path),
                    validation_mode=validation_mode,
                    use_manifest_chain=use_manifest_chain,
                    quiet=True,  # Suppress individual success messages
                    manifest_dir=None,  # Prevent recursion
                    skip_file_tracking=True,  # Skip per-manifest tracking
                )
                total_passed += 1
                if not quiet:
                    print("  ✅ PASSED\n")
            except SystemExit as e:
                if e.code == 0:
                    total_passed += 1
                    if not quiet:
                        print("  ✅ PASSED\n")
                else:
                    total_failed += 1
                    manifests_with_failures.append(manifest_path.name)
                    if not quiet:
                        print("  ❌ FAILED\n")
    finally:
        # Restore original working directory
        os.chdir(original_cwd)

    # Print summary
    total_manifests = total_passed + total_failed
    percentage = (total_passed / total_manifests * 100) if total_manifests > 0 else 0
    print(
        f"📊 Summary: {total_passed}/{total_manifests} manifest(s) passed ({percentage:.1f}%)"
    )

    if manifests_with_failures:
        print(f"   ❌ Failed manifests: {', '.join(manifests_with_failures)}")

    # FILE TRACKING ANALYSIS (once for all manifests)
    # Run only if using manifest chain and in implementation mode
    if use_manifest_chain and validation_mode == "implementation":
        try:
            # Load all manifests
            manifest_chain = []
            for manifest_file in sorted(manifests_dir.glob("task-*.manifest.json")):
                with open(manifest_file, "r") as f:
                    manifest_data = json.load(f)
                    # Add filename to manifest data for tracking purposes
                    manifest_data["_filename"] = manifest_file.name
                    manifest_chain.append(manifest_data)

            # Analyze file tracking
            source_root = str(project_root)
            analysis = analyze_file_tracking(manifest_chain, source_root)

            # Build validation summary
            validation_summary = (
                f"📊 Validation: {total_passed}/{total_manifests} manifest(s) passed "
                f"({percentage:.1f}%)"
            )

            # Display warnings
            _format_file_tracking_output(
                analysis, quiet=quiet, validation_summary=validation_summary
            )

        except Exception as e:
            # Don't fail validation if file tracking has issues
            if not quiet:
                print(f"\n⚠️  File tracking analysis failed: {e}")

    # Exit with appropriate code
    if total_failed > 0:
        sys.exit(1)
    else:
        sys.exit(0)


def run_validation(
    manifest_path: Optional[str] = None,
    validation_mode: str = "implementation",
    use_manifest_chain: bool = False,
    quiet: bool = False,
    manifest_dir: Optional[str] = None,
    skip_file_tracking: bool = False,
) -> None:
    """Core validation logic accepting parsed arguments.

    Args:
        manifest_path: Path to the manifest JSON file (mutually exclusive with manifest_dir)
        validation_mode: Validation mode ('implementation' or 'behavioral')
        use_manifest_chain: If True, use manifest chain to merge related manifests
        quiet: If True, suppress success messages
        manifest_dir: Path to directory containing manifests to validate all at once
        skip_file_tracking: If True, skip file tracking analysis (used in batch mode)

    Raises:
        SystemExit: Exits with code 0 on success, 1 on failure
    """
    # Handle --manifest-dir mode
    if manifest_dir:
        _run_directory_validation(
            manifest_dir, validation_mode, use_manifest_chain, quiet
        )
        return

    try:
        # Validate manifest file exists
        manifest_path_obj = Path(manifest_path)
        if not manifest_path_obj.exists():
            print(f"✗ Error: Manifest file not found: {manifest_path}")
            sys.exit(1)

        # Load the manifest
        with open(manifest_path_obj, "r") as f:
            manifest_data = json.load(f)

        # Validate against JSON schema
        schema_path = (
            Path(__file__).parent.parent
            / "validators"
            / "schemas"
            / "manifest.schema.json"
        )
        try:
            validate_schema(manifest_data, str(schema_path))
        except jsonschema.ValidationError as e:
            print("✗ Error: Manifest validation failed", file=sys.stderr)
            print(f"  {e.message}", file=sys.stderr)
            if e.path:
                path_str = ".".join(str(p) for p in e.path)
                print(f"  Location: {path_str}", file=sys.stderr)
            sys.exit(1)
        except FileNotFoundError:
            print(f"✗ Error: Schema file not found at {schema_path}", file=sys.stderr)
            sys.exit(1)

        # Validate MAID semantics (methodology compliance)
        try:
            validate_manifest_semantics(manifest_data)
        except ManifestSemanticError as e:
            print("✗ Error: Manifest semantic validation failed", file=sys.stderr)
            print(f"\n{e}", file=sys.stderr)
            sys.exit(1)

        # Validate version field
        from maid_runner.utils import validate_manifest_version

        try:
            validate_manifest_version(manifest_data, manifest_path_obj.name)
        except ValueError as e:
            print(f"✗ Error: {e}", file=sys.stderr)
            sys.exit(1)

        # Check if this is a system manifest - they skip behavioral/implementation validation
        from maid_runner.validators.manifest_validator import (
            _should_skip_behavioral_validation,
            _should_skip_implementation_validation,
        )

        skip_behavioral = _should_skip_behavioral_validation(manifest_data)
        skip_implementation = _should_skip_implementation_validation(manifest_data)

        # System manifests only undergo schema validation
        if skip_behavioral and skip_implementation:
            if not quiet:
                print("✓ System manifest validation PASSED (schema validation only)")
                print(
                    "  System manifests aggregate multiple files; no single implementation to validate"
                )
            return

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

        # Normalize file path: strip redundant project directory prefix if it exists
        # This handles cases where paths might have redundant directory prefixes
        # Check if the file exists as-is first, then try without the first directory component
        if "/" in file_path and not Path(file_path).exists():
            # Try removing the first directory component if it matches the current directory name
            project_name = Path.cwd().name
            if file_path.startswith(f"{project_name}/"):
                potential_normalized = file_path[len(project_name) + 1 :]
                if Path(potential_normalized).exists():
                    file_path = potential_normalized

        # BEHAVIORAL TEST VALIDATION
        # In behavioral mode, we validate test structure, not implementation
        # Support both legacy (validationCommand) and enhanced (validationCommands) formats
        validation_commands = manifest_data.get("validationCommands", [])
        if not validation_commands:
            validation_commands = manifest_data.get("validationCommand", [])

        # Initialize test_files to empty list for use in both behavioral and implementation modes
        test_files = []

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
            # Only run AST validation for Python files
            # Validate using appropriate language validator (Python, TypeScript, etc.)
            # The validator factory in manifest_validator.py routes to the correct validator
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

        # FILE TRACKING ANALYSIS
        # Run file tracking analysis when using manifest chain in implementation mode
        # Skip if in batch mode (will be shown once at the end)
        if (
            use_manifest_chain
            and validation_mode == "implementation"
            and not skip_file_tracking
        ):
            try:
                # Load all manifests from manifests directory
                manifests_dir = Path("manifests")
                if manifests_dir.exists():
                    manifest_chain = []
                    for manifest_file in sorted(
                        manifests_dir.glob("task-*.manifest.json")
                    ):
                        with open(manifest_file, "r") as f:
                            manifest_data = json.load(f)
                            # Add filename to manifest data for tracking purposes
                            manifest_data["_filename"] = manifest_file.name
                            manifest_chain.append(manifest_data)

                    # Analyze file tracking
                    source_root = str(Path.cwd())
                    analysis = analyze_file_tracking(manifest_chain, source_root)

                    # Display warnings
                    _format_file_tracking_output(analysis, quiet=quiet)

            except Exception as e:
                # Don't fail validation if file tracking has issues
                if not quiet:
                    print(f"\n⚠️  File tracking analysis failed: {e}")

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


def main() -> None:
    """Main CLI entry point."""
    parser = argparse.ArgumentParser(
        description="Validate manifest against implementation or behavioral test files",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Validate single manifest (implementation mode)
  %(prog)s manifests/task-001.manifest.json

  # Validate all manifests in directory
  %(prog)s --manifest-dir manifests

  # Validate behavioral test usage
  %(prog)s manifests/task-001.manifest.json --validation-mode behavioral

  # Use manifest chain for complex validation
  %(prog)s manifests/task-001.manifest.json --use-manifest-chain

  # Validate all manifests with behavioral mode
  %(prog)s --manifest-dir manifests --validation-mode behavioral

Validation Modes:
  implementation  - Validates that code DEFINES the expected artifacts (default)
  behavioral      - Validates that tests USE/CALL the expected artifacts

File Tracking Analysis:
  When using --use-manifest-chain in implementation mode, MAID Runner automatically
  analyzes file tracking compliance across the codebase:

  🔴 UNDECLARED - Files not in any manifest (high priority)
  🟡 REGISTERED - Files tracked but incomplete compliance (medium priority)
  ✓ TRACKED     - Files with full MAID compliance

  This helps identify accountability gaps and ensures all source files are properly
  documented in manifests.

This enables MAID Phase 2 validation: manifest ↔ behavioral test alignment!
        """,
    )

    parser.add_argument(
        "manifest_path",
        nargs="?",
        help="Path to the manifest JSON file (mutually exclusive with --manifest-dir)",
    )

    parser.add_argument(
        "--validation-mode",
        choices=["implementation", "behavioral"],
        default="implementation",
        help="Validation mode: 'implementation' (default) checks definitions, 'behavioral' checks usage",
    )

    parser.add_argument(
        "--use-manifest-chain",
        action="store_true",
        help="Use manifest chain to merge all related manifests (enables file tracking analysis)",
    )

    parser.add_argument(
        "--quiet",
        "-q",
        action="store_true",
        help="Only output errors (suppress success messages)",
    )

    parser.add_argument(
        "--manifest-dir",
        help="Directory containing manifests to validate (mutually exclusive with manifest_path)",
    )

    args = parser.parse_args()

    # Check for mutual exclusivity
    if args.manifest_path and args.manifest_dir:
        parser.error(
            "Cannot specify both manifest_path and --manifest-dir. Use one or the other."
        )

    if not args.manifest_path and not args.manifest_dir:
        parser.error("Must specify either manifest_path or --manifest-dir")

    run_validation(
        args.manifest_path,
        args.validation_mode,
        args.use_manifest_chain,
        args.quiet,
        args.manifest_dir,
    )


if __name__ == "__main__":
    main()
