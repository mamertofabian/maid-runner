"""
Semantic validation for MAID manifests.

This module provides validation beyond JSON schema compliance, checking
for violations of MAID methodology principles like extreme isolation
(one manifest per file for new public artifacts).
"""

import json
from pathlib import Path
from typing import List, Optional, Tuple

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


def validate_supersession(manifest_data: dict, manifests_dir: Path) -> None:
    """
    Validate that supersession is legitimate (delete, rename, or snapshot-edit only).

    This function validates the supersedes field of a manifest to ensure it follows
    valid supersession patterns:
    - Delete operations (status: absent) can supersede manifests for the same file
    - Rename operations can supersede manifests for the old file path
    - Edit manifests can supersede snapshot manifests for the same file

    Args:
        manifest_data: The manifest dictionary to validate
        manifests_dir: Path to the manifests directory

    Raises:
        ManifestSemanticError: If supersession is invalid/abusive
    """
    # Get superseded manifests - if none, nothing to validate
    superseded_manifests = _get_superseded_manifest_files(manifest_data, manifests_dir)
    if not superseded_manifests:
        return

    # Get expectedArtifacts info
    expected_artifacts = manifest_data.get("expectedArtifacts", {})
    target_file = expected_artifacts.get("file", "")
    status = expected_artifacts.get("status", "")

    # Check for delete operation (status: absent)
    if status == "absent":
        _validate_delete_supersession(manifest_data, superseded_manifests)
        return

    # Check for rename operation (file in creatableFiles, supersedes different file)
    creatable_files = manifest_data.get("creatableFiles", [])
    if target_file and target_file in creatable_files:
        # Check if superseded manifests are for DIFFERENT files (rename)
        # or SAME file (complete rewrite/snapshot transition)
        superseded_files = set()
        for _, content in superseded_manifests:
            superseded_artifacts = content.get("expectedArtifacts", {})
            superseded_file = superseded_artifacts.get("file", "")
            if superseded_file:
                superseded_files.add(superseded_file)

        # If all superseded are for the same target file, treat as snapshot transition
        if superseded_files == {target_file}:
            _validate_snapshot_edit_supersession(manifest_data, superseded_manifests)
            return
        # If superseded files exist and are different, it's a rename
        elif superseded_files:
            _validate_rename_supersession(manifest_data, superseded_manifests)
            return

    # Otherwise, check for valid snapshot-to-edit transition
    _validate_snapshot_edit_supersession(manifest_data, superseded_manifests)


def _get_superseded_manifest_files(
    manifest_data: dict, manifests_dir: Path
) -> List[Tuple[str, dict]]:
    """
    Load superseded manifest files and their contents.

    Args:
        manifest_data: The manifest dictionary containing supersedes field
        manifests_dir: Path to the manifests directory

    Returns:
        List of (filename, manifest_data) tuples for each superseded manifest
    """
    supersedes = manifest_data.get("supersedes", [])
    if not supersedes:
        return []

    result = []
    for filename in supersedes:
        manifest_path = manifests_dir / filename
        if manifest_path.exists():
            with open(manifest_path, "r") as f:
                content = json.load(f)
            result.append((str(manifest_path), content))

    return result


def _validate_delete_supersession(
    manifest_data: dict, superseded_manifests: List[Tuple[str, dict]]
) -> None:
    """
    Validate supersession for delete operations (status: absent).

    All superseded manifests must reference the same file being deleted.

    Args:
        manifest_data: The manifest dictionary (deleting manifest)
        superseded_manifests: List of (filename, content) tuples

    Raises:
        ManifestSemanticError: If superseded manifests don't reference the deleted file
    """
    expected_artifacts = manifest_data.get("expectedArtifacts", {})
    deleted_file = expected_artifacts.get("file", "")

    for filename, content in superseded_manifests:
        superseded_artifacts = content.get("expectedArtifacts", {})
        superseded_file = superseded_artifacts.get("file", "")

        # Check systemArtifacts for system manifests
        if not superseded_file:
            system_artifacts = content.get("systemArtifacts", [])
            if system_artifacts:
                # System manifest - check if any artifact references the deleted file
                system_files = [a.get("file", "") for a in system_artifacts]
                if deleted_file not in system_files:
                    raise ManifestSemanticError(
                        f"Delete operation supersedes manifest '{filename}' "
                        f"which does not reference the deleted file '{deleted_file}'"
                    )
                continue

        if superseded_file and superseded_file != deleted_file:
            raise ManifestSemanticError(
                f"Delete operation for '{deleted_file}' supersedes manifest "
                f"'{filename}' which references different file '{superseded_file}'"
            )


def _validate_rename_supersession(
    manifest_data: dict, superseded_manifests: List[Tuple[str, dict]]
) -> None:
    """
    Validate supersession for rename/move operations.

    Superseded manifests must reference the old file path (found in editableFiles),
    not the new file path.

    Args:
        manifest_data: The manifest dictionary (renaming manifest)
        superseded_manifests: List of (filename, content) tuples

    Raises:
        ManifestSemanticError: If superseded manifests don't reference the old path
    """
    editable_files = manifest_data.get("editableFiles", [])
    expected_artifacts = manifest_data.get("expectedArtifacts", {})
    new_file = expected_artifacts.get("file", "")

    # Old files are in editableFiles (files being renamed from)
    old_files = set(editable_files)

    for filename, content in superseded_manifests:
        superseded_artifacts = content.get("expectedArtifacts", {})
        superseded_file = superseded_artifacts.get("file", "")

        # Handle manifest without expectedArtifacts
        if not superseded_file:
            continue

        # Superseded must be for the old path, not the new one
        if superseded_file == new_file:
            raise ManifestSemanticError(
                f"Rename operation supersedes manifest '{filename}' which "
                f"references the NEW file path '{new_file}' instead of the old path"
            )

        if superseded_file not in old_files:
            raise ManifestSemanticError(
                f"Rename operation supersedes manifest '{filename}' which "
                f"references unrelated file '{superseded_file}'. "
                f"Expected old file from: {list(old_files)}"
            )


def _validate_snapshot_edit_supersession(
    manifest_data: dict, superseded_manifests: List[Tuple[str, dict]]
) -> None:
    """
    Validate that only snapshot manifests for the same file are superseded.

    Non-snapshot manifests cannot be superseded (would be consolidation abuse).
    Snapshots for different files also cannot be superseded.

    Args:
        manifest_data: The manifest dictionary (editing manifest)
        superseded_manifests: List of (filename, content) tuples

    Raises:
        ManifestSemanticError: If superseding non-snapshot or snapshot for different file
    """
    expected_artifacts = manifest_data.get("expectedArtifacts", {})
    target_file = expected_artifacts.get("file", "")

    for filename, content in superseded_manifests:
        task_type = content.get("taskType", "")
        superseded_artifacts = content.get("expectedArtifacts", {})
        superseded_file = superseded_artifacts.get("file", "")

        # Handle manifest without expectedArtifacts
        if not superseded_file:
            # System manifest or missing expectedArtifacts - skip or error
            if content.get("systemArtifacts"):
                continue
            # No file to compare - could be problematic but allow
            continue

        # Check if superseding a valid manifest type
        # Only snapshots can be superseded (they are "frozen" and need explicit unfreezing)
        # All other types (create, edit, refactor) should use manifest chain instead
        if task_type != "snapshot":
            raise ManifestSemanticError(
                f"Cannot supersede '{task_type}' manifest '{filename}'. "
                f"Only 'snapshot' manifests can be superseded by edit manifests. "
                f"Use --use-manifest-chain to merge artifacts from multiple manifests. "
                f"To delete a file, use status: 'absent'. To rename, put old file in editableFiles."
            )

        # Check if superseded manifest is for the same file
        if superseded_file != target_file:
            raise ManifestSemanticError(
                f"Cannot supersede manifest '{filename}' for file "
                f"'{superseded_file}' when editing file '{target_file}'. "
                f"Supersession must be for the same file."
            )
