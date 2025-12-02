"""Utility functions for MAID Runner."""

import json
import shlex
import sys
from pathlib import Path
from typing import List, Tuple

# Tuple of file/directory names that indicate a project root
# These are common markers for various project types
PROJECT_ROOT_MARKERS: Tuple[str, ...] = (
    ".git",
    "pyproject.toml",
    "package.json",
    ".maid",
    "setup.py",
    "Cargo.toml",
    "go.mod",
)


def find_project_root(
    start_path: Path,
    markers: Tuple[str, ...] = PROJECT_ROOT_MARKERS,
) -> Path:
    """Find the project root by walking up from start_path looking for marker files/directories.

    Args:
        start_path: The path to start searching from (can be a file or directory)
        markers: Tuple of marker file/directory names to look for.
                 Defaults to PROJECT_ROOT_MARKERS.

    Returns:
        The directory containing a marker, or start_path's parent if no marker found.
    """

    # Resolve the start path to get an absolute path
    current = start_path.resolve()

    # If start_path is a file, start from its parent directory
    if current.is_file():
        current = current.parent

    # Save original directory for fallback
    original_dir = current

    # Walk up the directory tree looking for markers
    while True:
        # Check if any marker exists in the current directory
        for marker in markers:
            if (current / marker).exists():
                return current

        # Move to parent directory
        parent = current.parent

        # If we've reached the root (parent is same as current), stop
        if parent == current:
            break

        current = parent

    # No marker found, fall back to start_path's parent (original behavior)
    return original_dir.parent


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
    project_root = find_project_root(manifests_dir)

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
                    # If path includes "manifests/", resolve from project root
                    if str(superseded_path).startswith("manifests/"):
                        superseded_path = project_root / superseded_path
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


def print_maid_not_enabled_message(manifest_dir: str, use_stderr: bool = False) -> None:
    """Print a friendly message when MAID manifests directory is not found.

    Args:
        manifest_dir: Path to the manifests directory that was not found
        use_stderr: If True, print to stderr instead of stdout
    """
    output_stream = sys.stderr if use_stderr else sys.stdout
    print(file=output_stream)
    print("⚠️  This repository does not appear to be MAID-enabled.", file=output_stream)
    print(file=output_stream)
    print(
        f"   The manifests directory was not found: {manifest_dir}", file=output_stream
    )
    print(file=output_stream)
    print(
        "   MAID (Manifest-driven AI Development) requires a 'manifests' directory",
        file=output_stream,
    )
    print(
        "   containing task manifest files (task-*.manifest.json).", file=output_stream
    )
    print(file=output_stream)
    print("   To get started with MAID:", file=output_stream)
    print(
        "   - Create a 'manifests' directory in your project root", file=output_stream
    )
    print("   - Generate manifests using: maid snapshot <file.py>", file=output_stream)
    print(
        "   - Or create manifests manually following the MAID specification",
        file=output_stream,
    )
    print(file=output_stream)


def print_no_manifests_found_message(
    manifest_dir: str, use_stderr: bool = False
) -> None:
    """Print a friendly message when no manifest files are found in the directory.

    Args:
        manifest_dir: Path to the manifests directory
        use_stderr: If True, print to stderr instead of stdout
    """
    output_stream = sys.stderr if use_stderr else sys.stdout
    print(file=output_stream)
    print("⚠️  No manifest files found in this repository.", file=output_stream)
    print(file=output_stream)
    print(f"   The manifests directory exists: {manifest_dir}", file=output_stream)
    print(
        "   but it does not contain any task manifest files (task-*.manifest.json).",
        file=output_stream,
    )
    print(file=output_stream)
    print("   To create manifest files:", file=output_stream)
    print("   - Generate manifests using: maid snapshot <file.py>", file=output_stream)
    print(
        "   - Or create manifests manually following the MAID specification",
        file=output_stream,
    )
    print(file=output_stream)
