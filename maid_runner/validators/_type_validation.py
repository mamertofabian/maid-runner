"""Private module for type hint validation."""

from typing import Any, Optional

from maid_runner.validators._artifact_validation import _ARTIFACT_TYPE_FUNCTION


# AlignmentError and compare_types will be imported lazily to avoid circular imports
def _get_alignment_error():
    from maid_runner.validators.manifest_validator import AlignmentError

    return AlignmentError


def _get_compare_types():
    from maid_runner.validators.manifest_validator import compare_types

    return compare_types


def _are_valid_type_validation_inputs(
    manifest_artifacts: Any, implementation_artifacts: Any
) -> bool:
    """Check if inputs are valid for type validation.

    Args:
        manifest_artifacts: Potentially a dict with manifest data
        implementation_artifacts: Potentially a dict with implementation data

    Returns:
        True if both inputs are valid dictionaries
    """
    return (
        manifest_artifacts is not None
        and isinstance(manifest_artifacts, dict)
        and implementation_artifacts is not None
        and isinstance(implementation_artifacts, dict)
    )


def _should_validate_artifact_types(artifact: Any) -> bool:
    """Check if an artifact should have its types validated.

    Args:
        artifact: Artifact definition from manifest

    Returns:
        True if artifact is a function/method that should be validated
    """
    return (
        isinstance(artifact, dict) and artifact.get("type") == _ARTIFACT_TYPE_FUNCTION
    )


def _validate_function_types(artifact: dict, implementation_artifacts: dict) -> list:
    """Validate type hints for a single function or method artifact.

    Args:
        artifact: Manifest artifact definition
        implementation_artifacts: Collected implementation type information

    Returns:
        List of validation error messages
    """
    # Early return for invalid inputs
    if not isinstance(artifact, dict):
        return []

    artifact_name = artifact.get("name")
    if not artifact_name:
        return []

    parent_class = artifact.get("class")

    # Get implementation info
    impl_info = _get_implementation_info(
        artifact_name, parent_class, implementation_artifacts
    )

    if not impl_info:
        return []  # No implementation to validate against

    # Collect all validation errors
    errors = []

    # Validate parameters
    errors.extend(
        _validate_parameter_types(artifact, impl_info, artifact_name, parent_class)
    )

    # Validate return type
    return_error = _validate_return_type(
        artifact, impl_info, artifact_name, parent_class
    )
    if return_error:
        errors.append(return_error)

    return errors


def _get_implementation_info(
    artifact_name: str, parent_class: Optional[str], implementation_artifacts: dict
) -> Optional[dict]:
    """Get implementation info for a function or method.

    Args:
        artifact_name: Name of the function or method
        parent_class: Parent class name if method, None if function
        implementation_artifacts: Collected implementation information

    Returns:
        Dictionary with type information, or None if not found
    """
    if not isinstance(implementation_artifacts, dict):
        return None

    if parent_class:
        return _get_method_info(artifact_name, parent_class, implementation_artifacts)
    else:
        return _get_function_info(artifact_name, implementation_artifacts)


def _get_method_info(
    method_name: str, class_name: str, implementation_artifacts: dict
) -> Optional[dict]:
    """Get implementation info for a method.

    Args:
        method_name: Name of the method
        class_name: Name of the parent class
        implementation_artifacts: Collected implementation information

    Returns:
        Dictionary with method type information, or None if not found
    """
    methods = implementation_artifacts.get("methods", {})
    if not isinstance(methods, dict):
        return None

    class_methods = methods.get(class_name)
    if not isinstance(class_methods, dict):
        return None

    return class_methods.get(method_name, {})


def _get_function_info(
    function_name: str, implementation_artifacts: dict
) -> Optional[dict]:
    """Get implementation info for a standalone function.

    Args:
        function_name: Name of the function
        implementation_artifacts: Collected implementation information

    Returns:
        Dictionary with function type information, or None if not found
    """
    functions = implementation_artifacts.get("functions", {})
    if not isinstance(functions, dict):
        return None

    func_info = functions.get(function_name, {})
    if not isinstance(func_info, dict):
        return None

    return func_info


def _validate_parameter_types(
    artifact: dict, impl_info: dict, artifact_name: str, parent_class: str
) -> list:
    """Validate parameter types match between manifest and implementation.

    Args:
        artifact: Manifest artifact definition
        impl_info: Implementation type information
        artifact_name: Name of the function/method
        parent_class: Parent class name if method, None if function

    Returns:
        List of validation error messages
    """
    errors = []
    # Support both args (enhanced) and parameters (legacy)
    manifest_params = artifact.get("args") or artifact.get("parameters", [])
    impl_params = impl_info.get("parameters", [])

    # Create lookup for implementation parameters
    impl_params_dict = {p.get("name"): p for p in impl_params}

    for manifest_param in manifest_params:
        param_name = manifest_param.get("name")
        manifest_type = manifest_param.get("type")

        if not manifest_type:
            continue  # No type to validate

        error = _validate_single_parameter(
            param_name, manifest_type, impl_params_dict, artifact_name, parent_class
        )
        if error:
            errors.append(error)

    return errors


def _validate_single_parameter(
    param_name: str,
    manifest_type: str,
    impl_params_dict: dict,
    artifact_name: str,
    parent_class: Optional[str],
) -> Optional[str]:
    """Validate a single parameter's type annotation.

    Args:
        param_name: Parameter name
        manifest_type: Expected type from manifest
        impl_params_dict: Implementation parameters by name
        artifact_name: Function/method name
        parent_class: Parent class or None

    Returns:
        Error message if validation fails, None otherwise
    """
    entity_type = "method" if parent_class else "function"

    impl_param = impl_params_dict.get(param_name)
    if not impl_param:
        return (
            f"Missing type annotation for parameter '{param_name}' "
            f"in {entity_type} '{artifact_name}'"
        )

    impl_type = impl_param.get("type")
    compare_types = _get_compare_types()
    if not compare_types(manifest_type, impl_type):
        return (
            f"Type mismatch for parameter '{param_name}' in {entity_type} "
            f"'{artifact_name}': expected '{manifest_type}', got '{impl_type}'"
        )

    return None


def _validate_return_type(
    artifact: dict, impl_info: dict, artifact_name: str, parent_class: Optional[str]
) -> Optional[str]:
    """Validate return type matches between manifest and implementation.

    Supports both string format ("Optional[dict]") and object format ({"type": "Optional[dict]"}).

    Args:
        artifact: Manifest artifact definition
        impl_info: Implementation type information
        artifact_name: Name of the function/method
        parent_class: Parent class name if method, None if function

    Returns:
        Error message if validation fails, None otherwise
    """
    manifest_return = artifact.get("returns")
    if not manifest_return:
        return None

    # Handle both string and object formats for returns
    if isinstance(manifest_return, dict):
        manifest_return_type = manifest_return.get("type")
        if not manifest_return_type:
            return None
        manifest_return = manifest_return_type
    elif not isinstance(manifest_return, str):
        # Invalid format, skip validation
        return None

    impl_return = impl_info.get("returns")
    if not impl_return:
        # Manifest specifies return type but implementation doesn't have one
        entity_type = "method" if parent_class else "function"
        return (
            f"Missing return type annotation in {entity_type} '{artifact_name}': "
            f"manifest expects '{manifest_return}' but implementation has no return type"
        )

    compare_types = _get_compare_types()
    if not compare_types(manifest_return, impl_return):
        entity_type = "method" if parent_class else "function"
        return (
            f"Type mismatch for return type in {entity_type} '{artifact_name}': "
            f"expected '{manifest_return}', got '{impl_return}'"
        )

    return None
