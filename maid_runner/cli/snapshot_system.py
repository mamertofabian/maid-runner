"""
System-wide manifest snapshot generation for MAID Runner.

This module provides functionality for generating system-wide manifest snapshots
that aggregate artifacts from all active manifests in the project.
"""

from pathlib import Path
from typing import List
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
