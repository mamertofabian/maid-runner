"""List manifests CLI command for MAID Runner.

Provides a command to list all manifests that reference a given file,
categorized by how they reference it (created, edited, or read).
"""

import json
import sys
from pathlib import Path
from typing import Optional

from maid_runner.utils import (
    print_maid_not_enabled_message,
    print_no_manifests_found_message,
)


def _normalize_path(path: str) -> str:
    """Normalize file path by stripping ./ prefix.

    Args:
        path: File path to normalize

    Returns:
        Normalized path without ./ prefix
    """
    if path.startswith("./"):
        return path[2:]
    return path


def _categorize_manifest_by_file(manifest_data: dict, file_path: str) -> Optional[str]:
    """Categorize how a manifest references a file.

    Args:
        manifest_data: Dictionary containing the manifest data
        file_path: Path to the file to check

    Returns:
        "created" if file is in creatableFiles
        "edited" if file is in editableFiles
        "read" if file is in readonlyFiles
        None if file is not referenced

    Note:
        Priority order: created > edited > read
        If a file appears in multiple lists, the highest priority category is returned.
    """
    # Normalize the input file path
    normalized_file_path = _normalize_path(file_path)

    # Check in priority order (normalize manifest paths too)
    creatable_files = [
        _normalize_path(f) for f in manifest_data.get("creatableFiles", [])
    ]
    editable_files = [
        _normalize_path(f) for f in manifest_data.get("editableFiles", [])
    ]
    readonly_files = [
        _normalize_path(f) for f in manifest_data.get("readonlyFiles", [])
    ]

    if normalized_file_path in creatable_files:
        return "created"
    if normalized_file_path in editable_files:
        return "edited"
    if normalized_file_path in readonly_files:
        return "read"

    return None


def _format_manifest_list_output(
    categorized_manifests: dict, file_path: str, quiet: bool
) -> None:
    """Format and print the categorized manifest list.

    Args:
        categorized_manifests: Dictionary with categories as keys and manifest lists as values
        file_path: The file path being searched
        quiet: If True, show minimal output (just manifest names)
    """
    # Count total manifests
    total_count = sum(len(manifests) for manifests in categorized_manifests.values())

    if total_count == 0:
        print(f"No manifests found referencing: {file_path}")
        return

    # Print header (unless quiet)
    if not quiet:
        print(f"\nManifests referencing: {file_path}")
        print(f"Total: {total_count} manifest(s)\n")
        print("=" * 80)

    # Print each category
    categories = ["created", "edited", "read"]
    category_labels = {
        "created": "📝 CREATED BY",
        "edited": "✏️  EDITED BY",
        "read": "👀 READ BY",
    }

    for category in categories:
        manifests = categorized_manifests.get(category, [])
        if not manifests:
            continue

        if quiet:
            # Quiet mode: just list manifest names
            for manifest_name in manifests:
                print(f"{category}: {manifest_name}")
        else:
            # Verbose mode: formatted output with labels
            label = category_labels.get(category, category.upper())
            print(f"\n{label} ({len(manifests)} manifest(s)):")
            for manifest_name in manifests:
                print(f"  - {manifest_name}")

    if not quiet:
        print("\n" + "=" * 80)


def run_list_manifests(file_path: str, manifest_dir: str, quiet: bool) -> None:
    """List all manifests that reference a given file.

    Scans all manifests in the specified directory and categorizes them by
    how they reference the target file (created, edited, or read).

    Args:
        file_path: Path to the file to search for in manifests
        manifest_dir: Directory containing manifest files
        quiet: If True, show minimal output

    Raises:
        SystemExit: Exits with code 1 if manifest_dir doesn't exist
    """
    manifest_dir_path = Path(manifest_dir)

    # Validate manifest directory exists
    if not manifest_dir_path.exists():
        print_maid_not_enabled_message(manifest_dir, use_stderr=True)
        sys.exit(1)

    # Find all manifest files
    manifest_files = sorted(manifest_dir_path.glob("task-*.manifest.json"))

    if not manifest_files:
        print_no_manifests_found_message(manifest_dir)
        return

    # Categorize manifests
    categorized = {
        "created": [],
        "edited": [],
        "read": [],
    }

    for manifest_file in manifest_files:
        try:
            with open(manifest_file, "r") as f:
                manifest_data = json.load(f)

            # Categorize this manifest
            category = _categorize_manifest_by_file(manifest_data, file_path)

            if category:
                categorized[category].append(manifest_file.name)

        except (json.JSONDecodeError, IOError) as e:
            # Skip invalid manifests with a warning
            if not quiet:
                print(
                    f"Warning: Skipping invalid manifest {manifest_file.name}: {e}",
                    file=sys.stderr,
                )
            continue

    # Format and display results
    _format_manifest_list_output(categorized, file_path, quiet)


def _main() -> None:
    """CLI entry point for standalone testing (private)."""
    import argparse

    parser = argparse.ArgumentParser(
        description="List all manifests that reference a given file"
    )
    parser.add_argument("file_path", help="Path to the file to search for")
    parser.add_argument(
        "--manifest-dir",
        default="manifests",
        help="Directory containing manifests (default: manifests)",
    )
    parser.add_argument(
        "--quiet",
        "-q",
        action="store_true",
        help="Show minimal output (just manifest names)",
    )

    args = parser.parse_args()
    run_list_manifests(args.file_path, args.manifest_dir, args.quiet)


if __name__ == "__main__":
    _main()
