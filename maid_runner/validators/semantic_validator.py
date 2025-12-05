"""
Semantic validation for MAID manifests.

This module provides validation beyond JSON schema compliance, checking
for violations of MAID methodology principles like extreme isolation
(one manifest per file for new public artifacts).
"""

from typing import List, Optional
from maid_runner.validators.manifest_validator import (
    _validate_file_status_semantic_rules,
    AlignmentError,
)


class ManifestSemanticError(Exception):
    """Raised when a manifest violates MAID semantic rules."""

    pass


def validate_manifest_semantics(manifest_data: dict) -> None:
    """
    Validate that manifest follows MAID methodology principles.

    This function checks for semantic issues beyond schema validation,
    particularly attempts to modify multiple files with new public artifacts
    which violates MAID's extreme isolation principle.

    Args:
        manifest_data: The manifest dictionary to validate

    Raises:
        ManifestSemanticError: If manifest violates MAID principles
        TypeError: If manifest_data is not a dict
        AttributeError: If manifest_data is None
    """
    if manifest_data is None:
        raise AttributeError("manifest_data cannot be None")

    if not isinstance(manifest_data, dict):
        raise TypeError(f"manifest_data must be dict, got {type(manifest_data)}")

    # Validate file status semantic rules (e.g., status: "absent" constraints)
    try:
        _validate_file_status_semantic_rules(manifest_data)
    except AlignmentError as e:
        raise ManifestSemanticError(str(e))

    # Detect attempts to specify multiple files with artifacts
    multi_file_indicators = _detect_multi_file_intent(manifest_data)

    if multi_file_indicators:
        # Extract the invalid property names from the error message
        # The indicators string contains property names
        invalid_props = []
        for key in manifest_data.keys():
            if "additional" in key.lower() and key not in [
                "creatableFiles",
                "editableFiles",
                "readonlyFiles",
                "expectedArtifacts",
                "validationCommand",
                "validationCommands",
                "goal",
                "taskType",
                "metadata",
                "version",
                "supersedes",
            ]:
                invalid_props.append(key)

        suggestion = _build_multi_file_suggestion(invalid_props)
        error_msg = f"{multi_file_indicators}\n\n{suggestion}"
        raise ManifestSemanticError(error_msg)


def _detect_multi_file_intent(manifest_data: dict) -> Optional[str]:
    """
    Detect if manifest attempts to modify multiple files inappropriately.

    Looks for common patterns where users try to work around MAID's
    single-file constraint by using invalid property names.

    Args:
        manifest_data: The manifest dictionary to check

    Returns:
        Error message string if multi-file intent detected, None otherwise
    """
    # Common invalid properties that suggest multi-file intent
    suspicious_properties = []

    # Check for properties that don't match the schema
    valid_properties = {
        "goal",
        "taskType",
        "creatableFiles",
        "editableFiles",
        "readonlyFiles",
        "expectedArtifacts",
        "validationCommand",
        "validationCommands",
        "metadata",
        "version",
        "supersedes",
    }

    for key in manifest_data.keys():
        if key not in valid_properties:
            # Check if it looks like an attempt to add more files/artifacts
            if "additional" in key.lower() or "extra" in key.lower():
                suspicious_properties.append(key)

    if suspicious_properties:
        props_str = ", ".join(f"'{prop}'" for prop in suspicious_properties)
        return f"Detected invalid properties suggesting multi-file intent: {props_str}"

    return None


def _build_multi_file_suggestion(invalid_properties: List[str]) -> str:
    """
    Build a helpful error message suggesting how to fix multi-file attempts.

    Args:
        invalid_properties: List of invalid property names detected

    Returns:
        Formatted suggestion message for the user
    """
    props_list = ", ".join(f"'{prop}'" for prop in invalid_properties)

    suggestion = f"""💡 Suggestion: MAID Methodology Violation Detected

You're attempting to use: {props_list}

MAID (Manifest-driven AI Development) requires EXTREME ISOLATION:
- One manifest per file when adding new public methods/classes/functions
- Each manifest should have ONE primary file in expectedArtifacts

Your options:
1. Create separate manifests for each file:
   - task-XXX.manifest.json for the first file
   - task-XXY.manifest.json for the second file

2. Use the proper MAID fields:
   - creatableFiles: New files you're creating (strict validation)
   - editableFiles: Existing files you're modifying (permissive validation)
   - readonlyFiles: Dependencies and test files (no artifact validation)

Example of proper multi-file workflow:
  Manifest 1 (task-033): Adds public method to file1.py
  Manifest 2 (task-034): Adds public method to file2.py

Both manifests can reference each other's files in readonlyFiles or editableFiles.

See CLAUDE.md for full MAID workflow documentation."""

    return suggestion
