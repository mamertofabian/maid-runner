"""Private module for artifact validation logic."""

from typing import List, Optional, Any


# AlignmentError will be imported lazily to avoid circular imports
def _get_alignment_error():
    from maid_runner.validators.manifest_validator import AlignmentError

    return AlignmentError


# Artifact kind constants - determines validation behavior
_ARTIFACT_KIND_TYPE = "type"  # Compile-time only artifacts
_ARTIFACT_KIND_RUNTIME = "runtime"  # Runtime behavioral artifacts
_TYPEDDICT_INDICATOR = "TypedDict"  # Marker for TypedDict classes

# Artifact type constants - categorization of code elements
_ARTIFACT_TYPE_CLASS = "class"
_ARTIFACT_TYPE_FUNCTION = "function"
_ARTIFACT_TYPE_ATTRIBUTE = "attribute"
_ARTIFACT_TYPE_INTERFACE = "interface"
_ARTIFACT_TYPE_TYPE = "type"
_ARTIFACT_TYPE_ENUM = "enum"
_ARTIFACT_TYPE_NAMESPACE = "namespace"

# Validation mode constants - how validation is performed
_VALIDATION_MODE_BEHAVIORAL = "behavioral"  # Test usage validation
_VALIDATION_MODE_IMPLEMENTATION = "implementation"  # Code definition validation


def _validate_all_artifacts(
    expected_items: List[dict], collector: Any, validation_mode: str
) -> None:
    """Validate all expected artifacts exist in the code.

    Args:
        expected_items: List of expected artifacts
        collector: Artifact collector with discovered artifacts
        validation_mode: Validation mode

    Raises:
        AlignmentError: If any expected artifact is not found
    """
    # Import should_skip_behavioral_validation - circular import is safe
    from maid_runner.validators.manifest_validator import (
        should_skip_behavioral_validation,
    )

    for artifact in expected_items:
        # Skip type-only artifacts in behavioral validation
        if (
            validation_mode == _VALIDATION_MODE_BEHAVIORAL
            and should_skip_behavioral_validation(artifact)
        ):
            continue

        _validate_single_artifact(artifact, collector, validation_mode)


def _is_test_file_path(file_path: str) -> bool:
    """Check if file path indicates a test file.

    A file is considered a test file if:
    - It's in a 'tests/' directory, OR
    - Its filename starts with 'test_'

    This uses path-based detection instead of function-name-based detection
    to prevent production code from bypassing validation by including
    functions with test_ prefix.

    Args:
        file_path: Path to the file being validated

    Returns:
        True if this is a test file path
    """
    if not file_path:
        return False
    # Normalize path separators (Windows backslashes to forward slashes)
    normalized = file_path.replace("\\", "/")
    # Strip leading ./ for relative paths
    if normalized.startswith("./"):
        normalized = normalized[2:]
    # Check if in tests directory (handles relative, absolute, and various formats)
    # - "tests/..." (relative)
    # - "/path/to/tests/..." (absolute)
    # - "./tests/..." (explicit relative, after stripping)
    if normalized.startswith("tests/") or "/tests/" in normalized:
        return True
    # Check if filename starts with test_
    filename = normalized.split("/")[-1]
    return filename.startswith("test_")


def _check_unexpected_artifacts(expected_items: List[dict], collector: Any) -> None:
    """Check for unexpected public artifacts in strict mode.

    Args:
        expected_items: List of expected artifacts
        collector: Artifact collector with discovered artifacts

    Raises:
        AlignmentError: If unexpected public artifacts are found
    """
    # Skip strict validation for test files (path-based detection)
    # Uses collector.file_path for security - prevents bypass via test_ prefixed functions
    file_path = getattr(collector, "file_path", "")
    is_test_file = _is_test_file_path(file_path)

    if expected_items and not is_test_file:
        _validate_no_unexpected_artifacts(
            expected_items,
            collector.found_classes,
            collector.found_functions,
            collector.found_methods,
        )


def _validate_single_artifact(
    artifact: dict, collector: Any, validation_mode: str
) -> None:
    """Validate a single artifact.

    Args:
        artifact: Artifact definition
        collector: Artifact collector
        validation_mode: Validation mode

    Raises:
        AlignmentError: If artifact is not found or invalid
    """
    artifact_type = artifact.get("type")
    artifact_name = artifact.get("name")

    if artifact_type in (
        _ARTIFACT_TYPE_CLASS,
        _ARTIFACT_TYPE_INTERFACE,
        _ARTIFACT_TYPE_TYPE,
        _ARTIFACT_TYPE_ENUM,
        _ARTIFACT_TYPE_NAMESPACE,
    ):
        # Treat TypeScript structural types as equivalent to class for validation
        # They all define named types in the found_classes set
        expected_bases = artifact.get("bases", [])
        if validation_mode == _VALIDATION_MODE_BEHAVIORAL:
            # In behavioral mode, check if class was used
            if artifact_name not in collector.used_classes:
                AlignmentError = _get_alignment_error()
                raise AlignmentError(
                    f"Class '{artifact_name}' not used in behavioral test"
                )
        else:
            # In implementation mode, check definitions
            _validate_class(
                artifact_name,
                expected_bases,
                collector.found_classes,
                collector.found_class_bases,
            )

    elif artifact_type == _ARTIFACT_TYPE_ATTRIBUTE:
        parent_class = artifact.get("class")
        _validate_attribute(artifact_name, parent_class, collector.found_attributes)

    elif artifact_type == _ARTIFACT_TYPE_FUNCTION:
        _validate_function_artifact(artifact, collector, validation_mode)


def _validate_function_artifact(
    artifact: dict, collector: Any, validation_mode: str
) -> None:
    """Validate a function or method artifact.

    Args:
        artifact: Function/method artifact definition
        collector: Artifact collector
        validation_mode: Validation mode

    Raises:
        AlignmentError: If function/method is not found or invalid
    """
    artifact_name = artifact.get("name")
    # Support both args (enhanced) and parameters (legacy)
    parameters = artifact.get("args") or artifact.get("parameters", [])
    parent_class = artifact.get("class")

    # Reject manifests that explicitly declare 'self' as a parameter
    # In Python, 'self' is implicit for instance methods and not included in artifact declarations
    if parameters:
        for param in parameters:
            param_name = param.get("name")
            if param_name == "self":
                AlignmentError = _get_alignment_error()
                raise AlignmentError(
                    f"Manifest error: Parameter 'self' should not be explicitly declared "
                    f"in method '{artifact_name}'. In Python, 'self' is implicit for instance methods "
                    f"and is not included in artifact declarations. Remove 'self' from the parameters list."
                )

    if validation_mode == _VALIDATION_MODE_BEHAVIORAL:
        _validate_function_behavioral(
            artifact_name, parameters, parent_class, artifact, collector
        )
    else:
        _validate_function_implementation(
            artifact_name, parameters, parent_class, collector
        )


def _validate_function_behavioral(
    artifact_name: str,
    parameters: List[dict],
    parent_class: Optional[str],
    artifact: dict,
    collector: Any,
) -> None:
    """Validate function/method in behavioral mode."""
    if parent_class:
        # It's a method
        if parent_class not in collector.used_methods:
            AlignmentError = _get_alignment_error()
            raise AlignmentError(
                f"Class '{parent_class}' not used or method '{artifact_name}' not called"
            )
        if artifact_name not in collector.used_methods[parent_class]:
            AlignmentError = _get_alignment_error()
            raise AlignmentError(
                f"Method '{artifact_name}' not called on class '{parent_class}'"
            )
    else:
        # It's a standalone function
        if artifact_name not in collector.used_functions:
            AlignmentError = _get_alignment_error()
            raise AlignmentError(
                f"Function '{artifact_name}' not called in behavioral test"
            )

    # Validate parameters were used
    _validate_parameters_used(parameters, artifact_name, collector)

    # Validate return type if specified
    returns = artifact.get("returns")
    if returns and returns not in collector.used_classes:
        AlignmentError = _get_alignment_error()
        raise AlignmentError(
            f"Return type '{returns}' not validated for '{artifact_name}'"
        )


def _validate_parameters_used(
    parameters: List[dict], artifact_name: str, collector: Any
) -> None:
    """Validate parameters were used in function calls."""
    if not parameters:
        return

    # If we have positional arguments, we can't reliably check parameter names
    # Only check keyword arguments
    for param in parameters:
        param_name = param.get("name")
        if param_name:
            # Skip checking if positional args were used
            if "__positional__" not in collector.used_arguments:
                if param_name not in collector.used_arguments:
                    AlignmentError = _get_alignment_error()
                    raise AlignmentError(
                        f"Parameter '{param_name}' not used in call to '{artifact_name}'"
                    )


def _validate_function_implementation(
    artifact_name: str,
    parameters: List[dict],
    parent_class: Optional[str],
    collector: Any,
) -> None:
    """Validate function/method in implementation mode."""
    if parent_class:
        # It's a method
        if parent_class not in collector.found_methods:
            AlignmentError = _get_alignment_error()
            raise AlignmentError(
                f"Class '{parent_class}' not found for method '{artifact_name}'"
            )
        if artifact_name not in collector.found_methods[parent_class]:
            AlignmentError = _get_alignment_error()
            raise AlignmentError(
                f"Method '{artifact_name}' not found in class '{parent_class}'"
            )

        # Validate method parameters
        if parameters:
            _validate_method_parameters(
                artifact_name, parameters, parent_class, collector
            )
    else:
        # It's a standalone function
        _validate_function(artifact_name, parameters, collector.found_functions)


def _validate_method_parameters(
    method_name: str,
    parameters: List[dict],
    class_name: str,
    collector: Any,
) -> None:
    """Validate method parameters match expectations."""
    actual_parameters = collector.found_methods[class_name][method_name]

    # Handle both old format (list of strings) and new format (list of dicts)
    # After Task-077, parameters are dicts with {"name": "...", "type": "..."}
    if actual_parameters and isinstance(actual_parameters[0], dict):
        # New format: extract parameter names, filtering out 'self' and 'cls'
        actual_param_names = [
            p["name"] for p in actual_parameters if p.get("name") not in ("self", "cls")
        ]
    else:
        # Legacy format: list of strings, filter out 'self' and 'cls'
        actual_param_names = [p for p in actual_parameters if p not in ("self", "cls")]

    expected_param_names = [p["name"] for p in parameters]

    # Check all expected parameters are present
    for param_name in expected_param_names:
        if param_name not in actual_param_names:
            AlignmentError = _get_alignment_error()
            raise AlignmentError(
                f"Parameter '{param_name}' not found in method '{method_name}'"
            )


def _validate_class(class_name, expected_bases, found_classes, found_class_bases):
    """Validate that a class is referenced in the code with the expected base classes."""
    if class_name not in found_classes:
        AlignmentError = _get_alignment_error()
        raise AlignmentError(f"Artifact '{class_name}' not found")

    # Check base classes if specified
    if expected_bases:
        actual_bases = found_class_bases.get(class_name, [])
        for expected_base in expected_bases:
            # Check if expected base matches either the full name or just the class name part
            found = False
            for actual_base in actual_bases:
                # Match exact name or match the last component (for qualified names)
                if (
                    actual_base == expected_base
                    or actual_base.split(".")[-1] == expected_base
                ):
                    found = True
                    break
            if not found:
                AlignmentError = _get_alignment_error()
                raise AlignmentError(
                    f"Class '{class_name}' does not inherit from '{expected_base}'"
                )


def _validate_attribute(attribute_name, parent_class, found_attributes):
    """Validate that an attribute is referenced for a specific class."""
    class_attributes = found_attributes.get(parent_class, set())

    if attribute_name not in class_attributes:
        AlignmentError = _get_alignment_error()
        raise AlignmentError(f"Artifact '{attribute_name}' not found")


def _validate_function(function_name, expected_parameters, found_functions):
    """Validate that a function exists with the expected parameters."""
    if function_name not in found_functions:
        AlignmentError = _get_alignment_error()
        raise AlignmentError(f"Artifact '{function_name}' not found")

    # Check parameters if specified
    if expected_parameters:
        actual_parameters = found_functions[function_name]

        expected_param_names = [p["name"] for p in expected_parameters]

        # Handle both old format (list of strings) and new format (list of dicts)
        # After Task-077, parameters are dicts with {"name": "...", "type": "..."}
        if actual_parameters and isinstance(actual_parameters[0], dict):
            actual_param_names = [p["name"] for p in actual_parameters]
        else:
            # Legacy format: list of strings
            actual_param_names = actual_parameters

        # Check all expected parameters are present
        for param_name in expected_param_names:
            if param_name not in actual_param_names:
                AlignmentError = _get_alignment_error()
                raise AlignmentError(
                    f"Parameter '{param_name}' not found in function '{function_name}'"
                )

        # Check for unexpected parameters (strict validation)
        unexpected_params = set(actual_param_names) - set(expected_param_names)
        if unexpected_params:
            AlignmentError = _get_alignment_error()
            raise AlignmentError(
                f"Unexpected parameter(s) in function '{function_name}': {', '.join(sorted(unexpected_params))}"
            )


def _validate_no_unexpected_artifacts(
    expected_items, found_classes, found_functions, found_methods
):
    """Validate that no unexpected public artifacts exist in the code."""
    # Build sets of expected names
    expected_classes = {
        item["name"]
        for item in expected_items
        if item.get("type")
        in (
            "class",
            "interface",
            "type",
            "enum",
            "namespace",
        )
    }
    expected_functions = {
        item["name"]
        for item in expected_items
        if item.get("type") == "function" and "class" not in item
    }
    # Build expected methods: class_name -> set of method names
    expected_methods = {}
    for item in expected_items:
        if item.get("type") == "function" and "class" in item:
            class_name = item["class"]
            method_name = item["name"]
            if class_name not in expected_methods:
                expected_methods[class_name] = set()
            expected_methods[class_name].add(method_name)

    # Check for unexpected public classes (exclude private ones starting with _)
    public_classes = {cls for cls in found_classes if not cls.startswith("_")}
    unexpected_classes = public_classes - expected_classes
    if unexpected_classes:
        AlignmentError = _get_alignment_error()
        raise AlignmentError(
            f"Unexpected public class(es) found: {', '.join(sorted(unexpected_classes))}"
        )

    # Check for unexpected public functions (exclude private ones starting with _)
    public_functions = {func for func in found_functions if not func.startswith("_")}
    unexpected_functions = public_functions - expected_functions
    if unexpected_functions:
        AlignmentError = _get_alignment_error()
        raise AlignmentError(
            f"Unexpected public function(s) found: {', '.join(sorted(unexpected_functions))}"
        )

    # Check for unexpected public methods in each class
    for class_name, methods in found_methods.items():
        # Skip private classes (starting with _)
        if class_name.startswith("_"):
            continue
        # Get public methods (exclude private ones starting with _)
        public_methods = {m for m in methods.keys() if not m.startswith("_")}
        # Get expected methods for this class
        expected_for_class = expected_methods.get(class_name, set())
        # Find unexpected methods
        unexpected = public_methods - expected_for_class
        if unexpected:
            AlignmentError = _get_alignment_error()
            raise AlignmentError(
                f"Unexpected public method(s) in class '{class_name}': {', '.join(sorted(unexpected))}"
            )


def _is_typeddict_class(artifact: dict) -> bool:
    """
    Check if an artifact represents a TypedDict class.

    TypedDict classes are special type-only constructs that don't
    have runtime behavior and should be skipped during behavioral
    validation.

    Args:
        artifact: Dictionary containing artifact metadata

    Returns:
        True if artifact is a TypedDict class, False otherwise
    """
    if artifact.get("type") != _ARTIFACT_TYPE_CLASS:
        return False

    bases = artifact.get("bases")
    if not bases:
        return False

    # Check if any base class indicates TypedDict
    return any(_is_typeddict_base(base) for base in bases if base)


def _is_typeddict_base(base_name: str) -> bool:
    """Check if a base class name indicates TypedDict.

    Args:
        base_name: Name of the base class

    Returns:
        True if base class is TypedDict
    """
    return base_name and _TYPEDDICT_INDICATOR in base_name


def _should_skip_by_artifact_kind(artifact: dict) -> Optional[bool]:
    """Check if artifact kind explicitly indicates skip behavior.

    Args:
        artifact: Artifact metadata dictionary

    Returns:
        True to skip, False to validate, None if not explicitly specified
    """
    artifact_kind = artifact.get("artifactKind")

    if artifact_kind == _ARTIFACT_KIND_TYPE:
        return True
    elif artifact_kind == _ARTIFACT_KIND_RUNTIME:
        return False
    elif artifact_kind is not None:
        # Invalid values default to runtime (validate)
        return False

    return None  # No explicit specification
