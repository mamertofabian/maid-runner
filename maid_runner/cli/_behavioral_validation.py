"""Private helpers for behavioral validation of test files.

These helpers validate that test files use the expected artifacts declared
in manifests, ensuring behavioral test alignment.
"""

from pathlib import Path
from typing import Dict, Any, List, Set


def _collect_artifact_usage_from_tests(test_files: List[str]) -> Dict[str, Any]:
    """Collect artifact usage data from all test files.

    Also checks imported test files (e.g., _test_*.py files imported by main test file)
    to support split test file patterns.

    Args:
        test_files: List of test file paths to analyze

    Returns:
        Dictionary with usage data for classes, methods, functions, and arguments
    """
    from maid_runner.validators.manifest_validator import collect_behavioral_artifacts
    from maid_runner.cli._test_file_extraction import _find_imported_test_files

    all_used_classes = set()
    all_used_methods = {}
    all_used_functions = set()
    all_used_arguments = set()

    # Track which files we've already processed to avoid duplicates
    processed_files = set()

    # First, collect all files to process (original + imported)
    files_to_process = []
    for test_file in test_files:
        normalized_path = str(Path(test_file).resolve())
        if normalized_path not in processed_files:
            files_to_process.append(test_file)
            processed_files.add(normalized_path)

            # Find imported test files
            imported_files = _find_imported_test_files(test_file)
            for imported_file in imported_files:
                imported_normalized = str(Path(imported_file).resolve())
                if imported_normalized not in processed_files:
                    files_to_process.append(imported_file)
                    processed_files.add(imported_normalized)

    # Now collect artifacts from all files
    for test_file in files_to_process:
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
