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

from maid_runner.utils import get_superseded_manifests, normalize_validation_commands


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


def aggregate_validation_commands(manifest_paths: List[Path]) -> List[List[str]]:
    """Aggregate and deduplicate validation commands from multiple manifests.

    Loads each manifest, extracts its validation commands (both legacy
    validationCommand and enhanced validationCommands formats), normalizes
    them to a consistent format, and deduplicates identical commands.

    Args:
        manifest_paths: List of paths to manifest files to aggregate

    Returns:
        List of validation commands in enhanced format (List[List[str]]),
        where each command is represented as a list of strings.
        Duplicate commands are removed.

        Example return value:
        [
            ["pytest", "tests/", "-v"],
            ["make", "lint"],
            ["make", "type-check"]
        ]

    Note:
        - Uses normalize_validation_commands() to handle different formats
        - Deduplication is case-sensitive and order-preserving
        - Manifests without validation commands are skipped
        - Invalid JSON files are skipped with a warning
    """
    all_commands = []

    for manifest_path in manifest_paths:
        try:
            # Load manifest JSON
            with open(manifest_path, "r") as f:
                manifest_data = json.load(f)

            # Normalize and extract validation commands
            commands = normalize_validation_commands(manifest_data)

            # Add all commands from this manifest
            all_commands.extend(commands)

        except (json.JSONDecodeError, IOError):
            # Skip invalid or malformed manifests
            # In production, might want to log this
            continue

    # Deduplicate commands while preserving order
    # Convert to tuples for hashability, use dict to preserve order
    seen = {}
    deduplicated = []

    for command in all_commands:
        # Convert command list to tuple for use as dict key
        command_tuple = tuple(command)

        if command_tuple not in seen:
            seen[command_tuple] = True
            deduplicated.append(command)

    return deduplicated


def run_snapshot_system(output_path: str, manifest_dir: str, quiet: bool) -> None:
    """Orchestrate system-wide manifest snapshot generation.

    Main entry point for the snapshot-system CLI command. Discovers active
    manifests, aggregates artifacts and validation commands, creates a
    system manifest, and writes it to the specified output file.

    Args:
        output_path: Path where the system manifest should be written
        manifest_dir: Directory containing manifest files to aggregate
        quiet: If True, suppress informational output (errors still shown)

    Raises:
        FileNotFoundError: If manifest_dir doesn't exist
        OSError: If unable to write to output_path

    Example:
        >>> run_snapshot_system("system.manifest.json", "manifests", quiet=False)
        Discovering active manifests...
        Found 42 active manifests
        Aggregating artifacts...
        Aggregating validation commands...
        Creating system manifest...
        Writing to system.manifest.json...
        ✓ System snapshot created successfully
    """
    from maid_runner.cli.snapshot_system import (
        discover_active_manifests,
        aggregate_system_artifacts,
        aggregate_validation_commands,
        create_system_manifest,
    )

    manifest_dir_path = Path(manifest_dir)

    # Ensure manifest directory exists
    if not manifest_dir_path.exists():
        raise FileNotFoundError(f"Manifest directory not found: {manifest_dir}")

    if not quiet:
        print("Discovering active manifests...")

    # Discover active manifests
    active_manifests = discover_active_manifests(manifest_dir_path)

    if not quiet:
        print(f"Found {len(active_manifests)} active manifests")
        print("Aggregating artifacts...")

    # Aggregate artifacts
    artifact_blocks = aggregate_system_artifacts(active_manifests)

    if not quiet:
        total_files = len(artifact_blocks)
        total_artifacts = sum(len(block["contains"]) for block in artifact_blocks)
        print(f"  {total_files} files, {total_artifacts} artifacts")
        print("Aggregating validation commands...")

    # Aggregate validation commands
    validation_commands = aggregate_validation_commands(active_manifests)

    if not quiet:
        print(f"  {len(validation_commands)} unique commands")
        print("Creating system manifest...")

    # Create system manifest
    system_manifest = create_system_manifest(artifact_blocks, validation_commands)

    if not quiet:
        print(f"Writing to {output_path}...")

    # Ensure output directory exists
    output_path_obj = Path(output_path)
    output_path_obj.parent.mkdir(parents=True, exist_ok=True)

    # Write to file
    with open(output_path_obj, "w") as f:
        json.dump(system_manifest, f, indent=2)
        f.write("\n")  # Add trailing newline

    if not quiet:
        print("✓ System snapshot created successfully")
        print(f"  Output: {output_path}")


def create_system_manifest(
    artifact_blocks: List[Dict[str, Any]], validation_commands: List[List[str]]
) -> Dict[str, Any]:
    """Create a complete system manifest structure following the extended schema.

    Constructs a manifest dictionary with all required fields for a system-wide
    snapshot. Uses systemArtifacts for aggregated artifact blocks and
    validationCommands for deduplicated commands.

    Args:
        artifact_blocks: List of artifact blocks from aggregate_system_artifacts(),
                        where each block has 'file' and 'contains' fields
        validation_commands: List of validation commands from
                            aggregate_validation_commands()

    Returns:
        Dictionary representing a complete system manifest that follows the
        extended manifest schema and can be validated with `maid validate`.

        Example return value:
        {
            "version": "1",
            "goal": "System-wide manifest snapshot...",
            "taskType": "system-snapshot",
            "readonlyFiles": [],
            "systemArtifacts": [
                {"file": "file1.py", "contains": [...]},
                {"file": "file2.py", "contains": [...]}
            ],
            "validationCommands": [
                ["pytest", "tests/"],
                ["make", "lint"]
            ]
        }

    Note:
        - Uses taskType: "system-snapshot"
        - Uses systemArtifacts instead of expectedArtifacts
        - Uses validationCommands (enhanced format)
        - Includes all required schema fields
        - Generated manifest validates against manifest.schema.json
    """
    # Count total number of files and artifacts for descriptive goal
    num_files = len(artifact_blocks)
    num_artifacts = sum(len(block.get("contains", [])) for block in artifact_blocks)

    manifest = {
        "version": "1",
        "goal": f"System-wide manifest snapshot aggregated from all active manifests ({num_files} files, {num_artifacts} artifacts)",
        "taskType": "system-snapshot",
        "readonlyFiles": [],
        "systemArtifacts": artifact_blocks,
        "validationCommands": validation_commands,
    }

    return manifest
