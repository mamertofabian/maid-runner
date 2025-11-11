"""Utility functions for MAID Runner."""

import json
import shlex
from pathlib import Path
from typing import List


def validate_manifest_version(
    manifest_data: dict, manifest_name: str = "manifest"
) -> None:
    """Validate manifest version field.

    Args:
        manifest_data: Dictionary containing manifest data
        manifest_name: Name of the manifest file for error messages

    Raises:
        ValueError: If version is invalid (not "1")
    """
    # Default to "1" if version is missing or None (per schema default)
    version = manifest_data.get("version", "1")
    if version != "1":
        raise ValueError(
            f"Invalid schema version '{version}'. "
            f"Only version '1' is currently supported. "
            f"Manifest: {manifest_name}"
        )


def normalize_validation_commands(manifest_data: dict) -> List[List[str]]:
    """Normalize validation commands from manifest to a consistent format.

    Converts various validation command formats to a standard format:
    List[List[str]] where each inner list is a command array.

    Supported formats:
    - Enhanced: validationCommands = [["pytest", "test1.py"], ["pytest", "test2.py"]]
    - Legacy single: validationCommand = ["pytest", "test.py", "-v"]
    - Legacy multiple strings: validationCommand = ["pytest test1.py", "pytest test2.py"]
    - Legacy single string: validationCommand = "pytest test.py"

    Args:
        manifest_data: Dictionary containing manifest data

    Returns:
        List of command arrays, where each command is a list of strings.
        Returns empty list if no validation commands found.
    """
    # Support both validationCommand (legacy) and validationCommands (enhanced)
    validation_commands = manifest_data.get("validationCommands", [])
    if validation_commands:
        # Enhanced format: array of command arrays
        return validation_commands

    validation_command = manifest_data.get("validationCommand", [])
    if not validation_command:
        return []

    # Handle different legacy formats
    if isinstance(validation_command, str):
        # Single string command: "pytest tests/test.py"
        # Use shlex.split() to handle quoted arguments correctly
        return [shlex.split(validation_command)]

    if isinstance(validation_command, list):
        # Check for multiple string commands format: ["pytest test1.py", "pytest test2.py"]
        # This format requires ALL elements to be strings with spaces (command strings)
        if len(validation_command) > 1 and all(
            isinstance(cmd, str) and " " in cmd for cmd in validation_command
        ):
            # Multiple string commands: ["pytest test1.py", "pytest test2.py"]
            # Convert each string to a command array using shlex.split() for quoted args
            return [shlex.split(cmd) for cmd in validation_command]
        elif len(validation_command) > 0 and isinstance(validation_command[0], str):
            # Check if first element is a string with spaces (single string command)
            if " " in validation_command[0]:
                # Single string command in array: ["pytest tests/test.py"]
                # Use shlex.split() to handle quoted arguments correctly
                return [shlex.split(validation_command[0])]
            else:
                # Single command array: ["pytest", "test.py", "-v"]
                return [validation_command]
        else:
            # Single command array: ["pytest", "test.py", "-v"]
            return [validation_command]

    return []


def get_superseded_manifests(manifests_dir: Path) -> set:
    """Find all manifests that are superseded by any other manifests.

    Args:
        manifests_dir: Path to the manifests directory

    Returns:
        set: Set of manifest paths (as Path objects) that are superseded
    """
    superseded = set()

    # Check ALL manifests for supersedes declarations (not just snapshots)
    all_manifests = manifests_dir.glob("task-*.manifest.json")

    for manifest_path in all_manifests:
        try:
            with open(manifest_path, "r") as f:
                manifest_data = json.load(f)

            # Get the supersedes list
            supersedes_list = manifest_data.get("supersedes", [])
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
