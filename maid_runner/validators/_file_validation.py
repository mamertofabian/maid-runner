"""Private module for file status and editable files validation."""

from pathlib import Path

from maid_runner.validators._artifact_validation import (
    _VALIDATION_MODE_IMPLEMENTATION,
)
from maid_runner.validators._manifest_utils import (
    _collect_artifacts_from_ast,
    _merge_expected_artifacts,
    _parse_file,
)


# AlignmentError and discover_related_manifests will be imported lazily to avoid circular imports
def _get_alignment_error():
    from maid_runner.validators.manifest_validator import AlignmentError

    return AlignmentError


def _get_discover_related_manifests():
    from maid_runner.validators.manifest_validator import discover_related_manifests

    return discover_related_manifests


def _validate_absent_file(manifest_data: dict, file_path: str) -> None:
    """Validates that a file with status 'absent' does not exist.

    This function checks the expectedArtifacts.status field in the manifest.
    If status is "absent", it verifies the file does NOT exist in the codebase.
    If status is "present" or missing, the function returns early (no-op).

    Args:
        manifest_data: Dictionary containing the manifest data
        file_path: Path to the file being validated

    Raises:
        AlignmentError: If file has status 'absent' but still exists in the codebase

    Example:
        >>> manifest = {
        ...     "expectedArtifacts": {
        ...         "file": "deleted.py",
        ...         "status": "absent",
        ...         "contains": []
        ...     }
        ... }
        >>> _validate_absent_file(manifest, "deleted.py")  # Passes if deleted.py doesn't exist
        >>> # Raises AlignmentError if deleted.py exists
    """
    # Skip if no expectedArtifacts
    expected_artifacts = manifest_data.get("expectedArtifacts")
    if not expected_artifacts or not isinstance(expected_artifacts, dict):
        return

    # Get the status field - default to "present" if not specified
    status = expected_artifacts.get("status", "present")

    # Only validate absence if status is explicitly "absent"
    if status != "absent":
        return

    # Check if the file exists
    file_path_obj = Path(file_path)
    if file_path_obj.exists():
        AlignmentError = _get_alignment_error()
        raise AlignmentError(
            f"File {file_path} has status 'absent' but still exists in the codebase"
        )


def _validate_file_status_semantic_rules(manifest_data: dict) -> None:
    """Validates semantic rules for file status field usage.

    This function enforces semantic constraints on the status field:
    - Files in creatableFiles cannot have status: "absent" (contradiction)
    - Files with status: "absent" must have empty contains array
    - Files with status: "absent" must have taskType: "refactor"
    - Files with status: "absent" must have non-empty supersedes array
    - Files in editableFiles CAN have status: "absent" (deletion scenario)
    - Files in readonlyFiles are not affected by status

    Args:
        manifest_data: Dictionary containing the manifest data

    Raises:
        AlignmentError: If semantic rules are violated

    Example:
        >>> # This is invalid - creating a file that should be absent
        >>> manifest = {
        ...     "creatableFiles": ["new.py"],
        ...     "expectedArtifacts": {
        ...         "file": "new.py",
        ...         "status": "absent"
        ...     }
        ... }
        >>> _validate_file_status_semantic_rules(manifest)  # Raises AlignmentError

        >>> # This is valid - refactoring to delete a file
        >>> manifest = {
        ...     "taskType": "refactor",
        ...     "supersedes": ["manifests/task-001.manifest.json"],
        ...     "editableFiles": ["old.py"],
        ...     "expectedArtifacts": {
        ...         "file": "old.py",
        ...         "status": "absent",
        ...         "contains": []
        ...     }
        ... }
        >>> _validate_file_status_semantic_rules(manifest)  # Passes
    """
    # Skip if no expectedArtifacts
    expected_artifacts = manifest_data.get("expectedArtifacts")
    if not expected_artifacts or not isinstance(expected_artifacts, dict):
        return

    # Get the file path and status
    file_path = expected_artifacts.get("file")
    status = expected_artifacts.get("status")

    # Only validate if status is "absent"
    if status != "absent":
        return

    # Rule 1: Files in creatableFiles cannot have status: "absent"
    creatable_files = manifest_data.get("creatableFiles", [])
    if file_path in creatable_files:
        AlignmentError = _get_alignment_error()
        raise AlignmentError("Files in 'creatableFiles' cannot have status 'absent'")

    # Rule 2: contains must be empty when status is "absent"
    contains = expected_artifacts.get("contains", [])
    if contains:
        AlignmentError = _get_alignment_error()
        raise AlignmentError(
            "Files with status 'absent' must have empty 'contains' array "
            "(no artifacts to declare for deleted files)"
        )

    # Rule 3: taskType must be "refactor" when status is "absent"
    task_type = manifest_data.get("taskType")
    if task_type != "refactor":
        AlignmentError = _get_alignment_error()
        raise AlignmentError(
            f"Files with status 'absent' require taskType 'refactor', got '{task_type}'"
        )

    # Rule 4: supersedes must be non-empty when status is "absent"
    supersedes = manifest_data.get("supersedes", [])
    if not supersedes:
        AlignmentError = _get_alignment_error()
        raise AlignmentError(
            "Files with status 'absent' must have non-empty 'supersedes' array "
            "(must reference the manifest that created the file being deleted)"
        )


def _has_undeclared_public_artifacts(file_path: str) -> bool:
    """Check if a file has any undeclared public artifacts.

    Args:
        file_path: Path to the Python file to check

    Returns:
        True if file contains public (non-private) classes or functions
    """
    try:
        tree = _parse_file(file_path)
        collector = _collect_artifacts_from_ast(tree, _VALIDATION_MODE_IMPLEMENTATION)

        # Check for public artifacts (not starting with _)
        has_public_classes = any(
            not cls.startswith("_") for cls in collector.found_classes
        )
        has_public_functions = any(
            not func.startswith("_") for func in collector.found_functions
        )

        return has_public_classes or has_public_functions

    except (FileNotFoundError, SyntaxError):
        # If file doesn't exist or has syntax errors, skip validation
        # (other validation will catch these issues)
        return False


def _validate_editable_files(manifest_data: dict, validation_mode: str) -> None:
    """Validate that files in editableFiles don't have undeclared public artifacts.

    This closes the loophole where you could add multiple files to editableFiles
    but only the expectedArtifacts.file would be checked for unexpected artifacts.

    This validation checks files against the manifest chain to allow incremental
    development - artifacts declared in previous manifests are considered valid.

    Args:
        manifest_data: The manifest dictionary
        validation_mode: The validation mode (implementation or behavioral)

    Raises:
        AlignmentError: If any editableFile has undeclared public artifacts
    """
    # Import _VALIDATION_MODE_IMPLEMENTATION from artifact_validation
    from maid_runner.validators._artifact_validation import (
        _VALIDATION_MODE_IMPLEMENTATION,
    )

    # Only validate in implementation mode
    if validation_mode != _VALIDATION_MODE_IMPLEMENTATION:
        return

    editable_files = manifest_data.get("editableFiles", [])
    if not editable_files:
        return

    expected_file = manifest_data.get("expectedArtifacts", {}).get("file")

    # Check each editableFile that's NOT the expectedArtifacts file
    for file_path in editable_files:
        # Skip the file that's being explicitly validated
        if file_path == expected_file:
            continue

        # Check if this file has any public artifacts
        if not _has_undeclared_public_artifacts(file_path):
            continue  # No public artifacts, skip

        # File has public artifacts - check if they're declared in manifest chain
        try:
            # Discover manifests that touch this file
            discover_related_manifests = _get_discover_related_manifests()
            manifests_for_file = discover_related_manifests(file_path)

            if not manifests_for_file:
                # No manifests declare this file - it has undeclared artifacts
                AlignmentError = _get_alignment_error()
                raise AlignmentError(
                    f"File '{file_path}' in editableFiles has undeclared public artifacts. "
                    f"MAID requires one manifest per file for new public APIs. "
                    f"Either: (1) Create a separate manifest for '{file_path}', or "
                    f"(2) Make the artifacts private (prefix with _), or "
                    f"(3) Move '{file_path}' to readonlyFiles if you're only using existing APIs."
                )

            # Get merged artifacts from all manifests for this file
            merged_artifacts = _merge_expected_artifacts(manifests_for_file, file_path)

            # If no artifacts declared but file has public artifacts, it's undeclared
            if not merged_artifacts:
                AlignmentError = _get_alignment_error()
                raise AlignmentError(
                    f"File '{file_path}' in editableFiles has undeclared public artifacts. "
                    f"This file appears in manifests but has no expectedArtifacts declared. "
                    f"MAID requires one manifest per file for new public APIs. "
                    f"Either: (1) Add expectedArtifacts for '{file_path}' in a manifest, or "
                    f"(2) Make the artifacts private (prefix with _), or "
                    f"(3) Move '{file_path}' to readonlyFiles if you're only using existing APIs."
                )

        except FileNotFoundError:
            # Manifest directory doesn't exist - skip validation
            # (This can happen in test scenarios or before MAID is initialized)
            pass
