#!/usr/bin/env python3
"""Helper script to identify superseded manifests."""
import json
import sys
from pathlib import Path


def get_superseded_manifests(manifests_dir: Path) -> set:
    """Find all manifests that are superseded by snapshots.

    Args:
        manifests_dir: Path to the manifests directory

    Returns:
        set: Set of manifest paths (as Path objects) that are superseded
    """
    superseded = set()

    # Find all snapshot manifests
    snapshot_manifests = manifests_dir.glob("task-*-snapshot-*.manifest.json")

    for snapshot_path in snapshot_manifests:
        try:
            with open(snapshot_path, "r") as f:
                snapshot_data = json.load(f)

            # Get the supersedes list from the snapshot
            supersedes_list = snapshot_data.get("supersedes", [])
            for superseded_path_str in supersedes_list:
                # Convert to Path and resolve relative to manifests_dir
                superseded_path = Path(superseded_path_str)
                if not superseded_path.is_absolute():
                    # If path includes "manifests/", resolve from manifests_dir's parent
                    if str(superseded_path).startswith("manifests/"):
                        superseded_path = manifests_dir.parent / superseded_path
                    else:
                        # Resolve relative to manifests_dir
                        superseded_path = manifests_dir / superseded_path

                # Normalize to relative path from manifests_dir for comparison
                try:
                    resolved = superseded_path.resolve()
                    # Get relative path from manifests_dir
                    try:
                        relative_path = resolved.relative_to(manifests_dir.resolve())
                        superseded.add(manifests_dir / relative_path)
                    except ValueError:
                        # Path is outside manifests_dir, skip
                        pass
                except (OSError, ValueError):
                    # Invalid path, skip
                    pass
        except (json.JSONDecodeError, IOError):
            # Skip invalid manifests
            continue

    return superseded


if __name__ == "__main__":
    """Print superseded manifest paths, one per line."""
    manifests_dir = Path("manifests")
    if not manifests_dir.exists():
        sys.exit(0)

    superseded = get_superseded_manifests(manifests_dir)
    for manifest_path in sorted(superseded):
        print(str(manifest_path))
