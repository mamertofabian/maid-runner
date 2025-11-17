"""
System-wide manifest snapshot generation for MAID Runner.

This module provides functionality for generating system-wide manifest snapshots
that aggregate artifacts from all active manifests in the project.
"""

from pathlib import Path
from typing import List, Dict, Any
from collections import defaultdict
import re
import json

from maid_runner.utils import get_superseded_manifests


def discover_active_manifests(manifest_dir: Path) -> List[Path]:
    """Discover all active (non-superseded) manifests in chronological order.

    Scans the manifest directory for all task manifests, filters out those that
    have been superseded by other manifests, and returns the active ones sorted
    by task number (chronological order). Invalid JSON files are skipped.

    Args:
        manifest_dir: Path to the manifests directory

    Returns:
        List of Path objects for active manifests, sorted chronologically by
        task number (e.g., task-001, task-002, etc.)

    Example:
        >>> manifest_dir = Path("manifests")
        >>> active = discover_active_manifests(manifest_dir)
        >>> len(active)
        42
        >>> active[0].name
        'task-001-init.manifest.json'
    """
    # Get all manifest files matching the pattern task-*.manifest.json
    all_manifests = list(manifest_dir.glob("task-*.manifest.json"))

    # Filter out manifests with invalid JSON
    valid_manifests = []
    for manifest_path in all_manifests:
        try:
            with open(manifest_path, "r") as f:
                json.load(f)  # Verify it's valid JSON
            valid_manifests.append(manifest_path)
        except (json.JSONDecodeError, IOError):
            # Skip manifests with invalid JSON or read errors
            continue

    # Get the set of superseded manifests
    superseded = get_superseded_manifests(manifest_dir)

    # Filter out superseded manifests
    active_manifests = [m for m in valid_manifests if m not in superseded]

    # Sort chronologically by extracting task number from filename
    # Pattern: task-XXX-description.manifest.json
    def _extract_task_number(manifest_path: Path) -> int:
        """Extract task number from manifest filename."""
        match = re.match(r"task-(\d+)", manifest_path.name)
        if match:
            return int(match.group(1))
        # Fallback to 0 if pattern doesn't match (shouldn't happen with glob)
        return 0

    active_manifests.sort(key=_extract_task_number)

    return active_manifests


def aggregate_system_artifacts(manifest_paths: List[Path]) -> List[Dict[str, Any]]:
    """Aggregate artifacts from multiple manifests into system-wide artifact blocks.

    Loads each manifest, extracts its expectedArtifacts, and groups all artifacts
    by their source file. Returns a list of artifact blocks suitable for the
    systemArtifacts field in system-wide snapshot manifests.

    Args:
        manifest_paths: List of paths to manifest files to aggregate

    Returns:
        List of artifact blocks, where each block is a dict with:
        - 'file': Path to the source file (str)
        - 'contains': List of artifact definitions (list of dicts)

        Example return value:
        [
            {
                "file": "module/file1.py",
                "contains": [
                    {"type": "function", "name": "func1", "args": [...]},
                    {"type": "class", "name": "Class1"}
                ]
            },
            {
                "file": "module/file2.py",
                "contains": [
                    {"type": "function", "name": "func2"}
                ]
            }
        ]

    Note:
        - Manifests without expectedArtifacts (e.g., system snapshots) are skipped
        - Invalid JSON files are skipped with a warning
        - Artifacts from the same file across multiple manifests are combined
        - Duplicate artifacts are preserved (no deduplication at this level)
    """
    # Group artifacts by file path
    artifacts_by_file: Dict[str, List[Dict[str, Any]]] = defaultdict(list)

    for manifest_path in manifest_paths:
        try:
            # Load manifest JSON
            with open(manifest_path, "r") as f:
                manifest_data = json.load(f)

            # Skip manifests without expectedArtifacts
            # (e.g., system snapshots with systemArtifacts instead)
            if "expectedArtifacts" not in manifest_data:
                continue

            expected_artifacts = manifest_data["expectedArtifacts"]

            # Extract file path and artifacts
            file_path = expected_artifacts.get("file")
            contains = expected_artifacts.get("contains", [])

            if file_path:
                # Add all artifacts from this manifest to the file's list
                artifacts_by_file[file_path].extend(contains)

        except (json.JSONDecodeError, IOError, KeyError):
            # Skip invalid or malformed manifests
            # In production, might want to log this
            continue

    # Convert grouped artifacts to list of artifact blocks
    artifact_blocks = []
    for file_path in sorted(artifacts_by_file.keys()):
        artifact_blocks.append(
            {"file": file_path, "contains": artifacts_by_file[file_path]}
        )

    return artifact_blocks
