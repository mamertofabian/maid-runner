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


def validate_supersession(
    manifest_data: dict,
    manifests_dir: Path,
    current_manifest_path: Optional[Path] = None,
) -> None:
    """
    Validate that supersession is legitimate (delete, rename, or snapshot-edit only).

    This function validates the supersedes field of a manifest to ensure it follows
    valid supersession patterns:
    - Delete operations (status: absent) can supersede manifests for the same file
    - Rename operations can supersede manifests for the old file path
    - Snapshot manifests can supersede any manifest for the same file (creating baseline)
    - Edit manifests can supersede only snapshot manifests for the same file

    For snapshot manifests, additional validation:
    - Legacy snapshot (no prior manifests): supersedes must be empty
    - Consolidation snapshot (prior manifests exist): supersedes must NOT be empty

    Args:
        manifest_data: The manifest dictionary to validate
        manifests_dir: Path to the manifests directory
        current_manifest_path: Optional path to current manifest (to exclude from prior check)

    Raises:
        ManifestSemanticError: If supersession is invalid/abusive
    """
    task_type = manifest_data.get("taskType", "")

    # For snapshot manifests, validate supersedes based on prior manifests
    if task_type == "snapshot":
        _validate_snapshot_supersedes(
            manifest_data, manifests_dir, current_manifest_path
        )

    # Get superseded manifests - if none, nothing more to validate
    superseded_manifests = _get_superseded_manifest_files(manifest_data, manifests_dir)
    if not superseded_manifests:
        return

    # Get expectedArtifacts info
    expected_artifacts = manifest_data.get("expectedArtifacts", {})
    target_file = expected_artifacts.get("file", "")
    status = expected_artifacts.get("status", "")
    task_type = manifest_data.get("taskType", "")

    # Snapshot manifests can supersede anything (they create a new baseline)
    # Only validate that superseded manifests are for the same file
    if task_type == "snapshot":
        _validate_same_file_supersession(manifest_data, superseded_manifests)
        return

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

    Raises:
        ManifestSemanticError: If a superseded manifest file doesn't exist or has invalid JSON
    """
    supersedes = manifest_data.get("supersedes", [])
    if not supersedes:
        return []

    result = []
    for filename in supersedes:
        # Handle both formats: "task-001.manifest.json" and "manifests/task-001.manifest.json"
        # Strip "manifests/" prefix if present to normalize the path
        normalized_filename = filename
        if filename.startswith("manifests/"):
            normalized_filename = filename[len("manifests/") :]

        manifest_path = manifests_dir / normalized_filename
        if not manifest_path.exists():
            raise ManifestSemanticError(
                f"Superseded manifest file not found: '{filename}'. "
                f"Check that the file exists in '{manifests_dir}' or remove it from supersedes array."
            )
        try:
            with open(manifest_path, "r") as f:
                content = json.load(f)
        except json.JSONDecodeError as e:
            raise ManifestSemanticError(
                f"Invalid JSON in superseded manifest '{filename}': {e}"
            )
        result.append((str(manifest_path), content))

    return result


def _validate_same_file_supersession(
    manifest_data: dict, superseded_manifests: List[Tuple[str, dict]]
) -> None:
    """
    Validate that all superseded manifests reference the same file.

    Used for snapshot manifests which can supersede any manifest type
    but must be for the same file.

    Args:
        manifest_data: The manifest dictionary (snapshot manifest)
        superseded_manifests: List of (filename, content) tuples

    Raises:
        ManifestSemanticError: If superseded manifests reference different files
    """
    expected_artifacts = manifest_data.get("expectedArtifacts", {})
    target_file = expected_artifacts.get("file", "")

    for filename, content in superseded_manifests:
        superseded_artifacts = content.get("expectedArtifacts", {})
        superseded_file = superseded_artifacts.get("file", "")

        # Handle system manifests
        if not superseded_file:
            system_artifacts = content.get("systemArtifacts", [])
            if system_artifacts:
                continue
            continue

        # Normalize paths for comparison (handle ./path vs path)
        normalized_target = target_file.lstrip("./")
        normalized_superseded = superseded_file.lstrip("./")

        if normalized_superseded != normalized_target:
            raise ManifestSemanticError(
                f"Snapshot supersedes manifest '{filename}' for file "
                f"'{superseded_file}' but declares artifacts for '{target_file}'. "
                f"Snapshots can only supersede manifests for the same file."
            )


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

        # Check if superseded file is in valid old_files list
        if superseded_file not in old_files:
            # If old_files is empty, give specific guidance
            if not old_files:
                raise ManifestSemanticError(
                    f"Rename operation supersedes manifest '{filename}' for file "
                    f"'{superseded_file}', but editableFiles is empty. "
                    f"The old file path must be specified in editableFiles."
                )
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
        # Normalize paths for comparison (handle ./path vs path)
        normalized_target = target_file.lstrip("./")
        normalized_superseded = superseded_file.lstrip("./")

        if normalized_superseded != normalized_target:
            raise ManifestSemanticError(
                f"Cannot supersede manifest '{filename}' for file "
                f"'{superseded_file}' when editing file '{target_file}'. "
                f"Supersession must be for the same file."
            )


def _validate_snapshot_supersedes(
    manifest_data: dict,
    manifests_dir: Path,
    current_manifest_path: Optional[Path] = None,
) -> None:
    """
    Validate snapshot supersedes based on whether prior manifests exist.

    - Legacy snapshot (no prior manifests for target file): supersedes must be empty
    - Consolidation snapshot (prior manifests exist for target file): supersedes must NOT be empty

    Args:
        manifest_data: The snapshot manifest dictionary
        manifests_dir: Path to the manifests directory
        current_manifest_path: Path to current manifest (to exclude from prior check)

    Raises:
        ManifestSemanticError: If supersedes doesn't match the expected pattern
    """
    expected_artifacts = manifest_data.get("expectedArtifacts", {})
    target_file = expected_artifacts.get("file", "")
    supersedes = manifest_data.get("supersedes", [])

    if not target_file:
        return  # Can't validate without a target file

    # Normalize target file path
    normalized_target = target_file.lstrip("./")

    # Find all prior manifests for the same file
    prior_manifests = _find_prior_manifests_for_file(
        normalized_target, manifests_dir, current_manifest_path
    )

    if prior_manifests and not supersedes:
        # Case 1: Consolidation snapshot - must supersede prior manifests
        prior_names = [p.name for p in prior_manifests]
        raise ManifestSemanticError(
            f"Snapshot manifest for '{target_file}' has empty supersedes, "
            f"but prior manifests exist for this file: {prior_names}. "
            f"Consolidation snapshots must supersede all prior manifests for the same file. "
            f"Add the prior manifests to the supersedes array."
        )

    if not prior_manifests and supersedes:
        # Case 2: Legacy snapshot - should not supersede anything
        raise ManifestSemanticError(
            f"Snapshot manifest for '{target_file}' has supersedes={supersedes}, "
            f"but no prior manifests exist for this file. "
            f"Legacy snapshots (for code not previously tracked by MAID) should have empty supersedes."
        )


def _find_prior_manifests_for_file(
    target_file: str,
    manifests_dir: Path,
    exclude_manifest: Optional[Path] = None,
) -> List[Path]:
    """
    Find all manifests that reference the given target file.

    Args:
        target_file: Normalized file path to search for
        manifests_dir: Path to the manifests directory
        exclude_manifest: Optional manifest path to exclude from results

    Returns:
        List of manifest paths that reference the target file
    """
    prior_manifests = []

    # Scan all manifest files in the directory
    for manifest_path in manifests_dir.glob("task-*.manifest.json"):
        # Skip the current manifest being validated
        if exclude_manifest and manifest_path.resolve() == exclude_manifest.resolve():
            continue

        try:
            with open(manifest_path, "r") as f:
                content = json.load(f)

            # Check if this manifest references the same file
            artifacts = content.get("expectedArtifacts", {})
            manifest_file = artifacts.get("file", "")

            if not manifest_file:
                continue

            # Normalize for comparison
            normalized_manifest_file = manifest_file.lstrip("./")

            if normalized_manifest_file == target_file:
                prior_manifests.append(manifest_path)

        except (json.JSONDecodeError, IOError):
            # Skip manifests that can't be read
            continue

    return prior_manifests
