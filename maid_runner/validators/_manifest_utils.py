"""Private module for manifest discovery and merging utilities."""

import ast
import json
from pathlib import Path
from typing import List


# discover_related_manifests will be imported lazily to avoid circular imports
def _get_discover_related_manifests():
    from maid_runner.validators.manifest_validator import discover_related_manifests

    return discover_related_manifests


def _get_task_number(path: Path) -> int:
    """Extract task number from filename like task-XXX-description.json.

    Args:
        path: Path object to the manifest file

    Returns:
        Task number as integer, or float('inf') for non-task files
    """
    stem = path.stem
    # Handle .manifest.json files by removing .manifest suffix
    if stem.endswith(".manifest"):
        stem = stem[:-9]  # Remove '.manifest' suffix

    if stem.startswith("task-"):
        try:
            # Split by '-' and get the number part (second element)
            parts = stem.split("-")
            if len(parts) >= 2:
                return int(parts[1])
        except (ValueError, IndexError):
            pass
    return float("inf")  # Put non-task files at the end


def _get_artifact_key(artifact: dict) -> tuple:
    """Generate unique key for an artifact.

    For methods and class attributes, the key includes the class name to distinguish
    between artifacts with the same name in different classes.

    Args:
        artifact: Artifact dictionary with type, name, and optional class fields

    Returns:
        Tuple of (type, class_or_none, name) that uniquely identifies the artifact

    Examples:
        >>> _get_artifact_key({"type": "class", "name": "MyClass"})
        ('class', None, 'MyClass')

        >>> _get_artifact_key({"type": "function", "name": "get", "class": "LRUCache"})
        ('function', 'LRUCache', 'get')

        >>> _get_artifact_key({"type": "function", "name": "helper"})
        ('function', None, 'helper')
    """
    artifact_type = artifact.get("type")
    artifact_name = artifact.get("name")
    artifact_class = artifact.get("class")  # None for module-level artifacts

    # Key format: (type, class_or_none, name)
    # This allows methods/attributes with same name in different classes to coexist
    return (artifact_type, artifact_class, artifact_name)


def _merge_expected_artifacts(
    manifest_paths: List[str], target_file: str
) -> List[dict]:
    """
    Merge expected artifacts from multiple manifests, filtering by target file.

    Args:
        manifest_paths: List of paths to manifest files
        target_file: Only include artifacts where expectedArtifacts.file matches this path

    Returns:
        Merged list of expected artifacts
    """
    merged_artifacts = []
    seen_artifacts = {}  # Track (type, class, name) -> artifact

    for path in manifest_paths:
        with open(path, "r") as f:
            data = json.load(f)

        # Only include artifacts if expectedArtifacts.file matches target_file
        expected_artifacts = data.get("expectedArtifacts", {})
        artifacts_file = expected_artifacts.get("file")

        # Skip this manifest if its artifacts are for a different file
        if artifacts_file != target_file:
            continue

        artifacts = expected_artifacts.get("contains", [])

        for artifact in artifacts:
            # Use (type, class, name) as unique key
            # This prevents methods with same name in different classes from overwriting each other
            key = _get_artifact_key(artifact)

            # Add if not seen, or always update (later manifests override earlier ones)
            # This ensures that modifications in later tasks override earlier definitions
            seen_artifacts[key] = artifact

    # Return artifacts in a consistent order
    merged_artifacts = list(seen_artifacts.values())
    return merged_artifacts


def _get_expected_artifacts(
    manifest_data: dict, test_file_path: str, use_manifest_chain: bool
) -> List[dict]:
    """Get expected artifacts from manifest(s).

    Args:
        manifest_data: Manifest data dictionary
        test_file_path: Path to file being validated
        use_manifest_chain: Whether to use manifest chain

    Returns:
        List of expected artifact definitions
    """
    # Check if this is a snapshot manifest
    is_snapshot = manifest_data.get("taskType") == "snapshot"

    # Snapshots are already consolidated, so skip manifest chain even if requested
    if use_manifest_chain and not is_snapshot:
        target_file = manifest_data.get("expectedArtifacts", {}).get(
            "file", test_file_path
        )
        discover_related_manifests = _get_discover_related_manifests()
        related_manifests = discover_related_manifests(target_file)
        return _merge_expected_artifacts(related_manifests, target_file)
    else:
        expected_artifacts = manifest_data.get("expectedArtifacts", {})
        return expected_artifacts.get("contains", [])


def _get_validator_for_file(file_path: str):
    """Get the appropriate validator for a file based on its extension.

    Args:
        file_path: Path to the file

    Returns:
        Validator instance (PythonValidator or TypeScriptValidator)

    Raises:
        ValueError: If file extension is not supported
    """
    from maid_runner.validators.python_validator import PythonValidator
    from maid_runner.validators.typescript_validator import TypeScriptValidator
    from maid_runner.validators.svelte_validator import SvelteValidator

    # Try each validator
    validators = [PythonValidator(), TypeScriptValidator(), SvelteValidator()]

    for validator in validators:
        if validator.supports_file(file_path):
            return validator

    # Fallback to Python validator for backward compatibility
    return PythonValidator()


def _parse_file(file_path: str) -> ast.AST:
    """Parse a Python file into an AST.

    Args:
        file_path: Path to the Python file

    Returns:
        Parsed AST tree
    """
    with open(file_path, "r") as f:
        code = f.read()
    return ast.parse(code)


def _collect_artifacts_from_ast(
    tree: ast.AST, validation_mode: str
):  # type: ignore[no-any-return]
    """Collect artifacts from an AST tree.

    Args:
        tree: Parsed AST tree
        validation_mode: Mode for validation

    Returns:
        Collector with discovered artifacts
    """
    # Import _ArtifactCollector - circular import is safe since it's defined in manifest_validator
    from maid_runner.validators.manifest_validator import _ArtifactCollector

    collector = _ArtifactCollector(validation_mode=validation_mode)
    collector.visit(tree)
    return collector
