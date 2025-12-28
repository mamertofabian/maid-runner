"""Core logic for the `maid manifest create` command.

This module provides programmatic manifest creation with:
- Auto-numbering of task manifests
- Auto-detection of task type (create vs edit)
- Auto-supersession of active snapshot manifests
- JSON output support for agent consumption
"""

import json
import re
import sys
from pathlib import Path
from typing import List, Optional

from maid_runner.cli._manifest_helpers import (
    generate_validation_command,
    sanitize_goal_for_filename,
)
from maid_runner.utils import get_superseded_manifests


def run_create_manifest(
    file_path: str,
    goal: str,
    artifacts: Optional[str | List[dict]],
    task_type: Optional[str],
    force_supersede: Optional[str],
    test_file: Optional[str],
    readonly_files: Optional[str | List[str]],
    output_dir: str | Path,
    task_number: Optional[int],
    json_output: bool,
    quiet: bool,
    dry_run: bool,
) -> int:
    """Main entry point for manifest creation, called from main.py CLI.

    Args:
        file_path: Path to the file this manifest describes
        goal: Concise goal description for the manifest
        artifacts: JSON string or list of artifact definitions, or None
        task_type: Task type (create/edit/refactor) or None for auto-detect
        force_supersede: Specific manifest to supersede (for non-snapshots)
        test_file: Path to test file for validationCommand, or None for auto
        readonly_files: Comma-separated string or list of readonly dependencies
        output_dir: Directory to write manifest (string or Path)
        task_number: Explicit task number, or None for auto-number
        json_output: If True, output created manifest as JSON
        quiet: If True, suppress informational messages
        dry_run: If True, print manifest without writing

    Returns:
        Exit code: 0 on success, non-zero on failure
    """
    from maid_runner.cli._manifest_helpers import parse_artifacts_json

    # Convert inputs to proper types (handle both CLI strings and direct Python objects)
    output_dir_path = Path(output_dir) if isinstance(output_dir, str) else output_dir

    # Handle artifacts: string (from CLI) or list (from tests/programmatic)
    if artifacts is None:
        artifacts_list = []
    elif isinstance(artifacts, str):
        artifacts_list = parse_artifacts_json(artifacts)
    else:
        artifacts_list = artifacts

    # Handle readonly_files: string (from CLI) or list (from tests/programmatic)
    if readonly_files is None:
        readonly_list = []
    elif isinstance(readonly_files, str):
        readonly_list = [f.strip() for f in readonly_files.split(",") if f.strip()]
    else:
        readonly_list = readonly_files

    # Get task number (auto or explicit)
    if task_number is None:
        task_number = _get_next_task_number(output_dir_path)

    # Build supersedes list (do this before task type detection)
    supersedes = []

    # Auto-supersede active snapshots
    active_snapshot = _find_active_snapshot_to_supersede(file_path, output_dir_path)
    if active_snapshot:
        supersedes.append(active_snapshot)
        if not quiet and not json_output:
            print(
                f"Auto-superseding active snapshot: {active_snapshot}",
                file=sys.stderr,
            )

    # Detect or use explicit task type
    # If superseding a snapshot, the file must exist per MAID methodology
    # (snapshots are only for existing code), so default to "edit"
    if task_type is None:
        if active_snapshot:
            # Superseding a snapshot implies the file exists
            task_type = "edit"
        else:
            task_type = _detect_task_type(Path(file_path))

    # Add force_supersede if provided
    if force_supersede:
        if force_supersede not in supersedes:
            supersedes.append(force_supersede)

    # Generate validation command
    if test_file:
        validation_command = ["pytest", test_file, "-v"]
    else:
        validation_command = generate_validation_command(file_path, task_number)

    # Generate manifest
    manifest_data = _generate_manifest(
        goal=goal,
        file_path=file_path,
        task_type=task_type,
        artifacts=artifacts_list,
        supersedes=supersedes,
        readonly_files=readonly_list,
        validation_command=validation_command,
    )

    # Generate filename
    sanitized_goal = sanitize_goal_for_filename(goal)
    manifest_filename = f"task-{task_number:03d}-{sanitized_goal}.manifest.json"
    output_path = output_dir_path / manifest_filename

    # Handle dry-run
    if dry_run:
        if json_output:
            output = {
                "success": True,
                "dry_run": True,
                "manifest_path": str(output_path),
                "task_number": task_number,
                "manifest": manifest_data,
            }
            if active_snapshot:
                output["superseded_snapshot"] = active_snapshot
            print(json.dumps(output, indent=2))
        else:
            if not quiet:
                print(f"[DRY RUN] Would create: {output_path}", file=sys.stderr)
                print(json.dumps(manifest_data, indent=2))
        return 0

    # Write manifest
    _write_manifest(manifest_data, output_path)

    # Output result
    if json_output:
        output = {
            "success": True,
            "manifest_path": str(output_path),
            "task_number": task_number,
            "manifest": manifest_data,
        }
        if active_snapshot:
            output["superseded_snapshot"] = active_snapshot
        print(json.dumps(output, indent=2))
    elif not quiet:
        print(f"Created manifest: {output_path}", file=sys.stderr)

    return 0


def _get_next_task_number(manifests_dir: Path) -> int:
    """Find next available task number by scanning manifest directory.

    Scans for task-*.manifest.json files and returns max+1.

    Args:
        manifests_dir: Path to the manifests directory

    Returns:
        Next available task number (1 if no manifests exist)
    """
    if not manifests_dir.exists():
        return 1

    max_number = 0
    task_pattern = re.compile(r"^task-(\d+)-.*\.manifest\.json$")

    for manifest_file in manifests_dir.glob("task-*.manifest.json"):
        match = task_pattern.match(manifest_file.name)
        if match:
            try:
                number = int(match.group(1))
                max_number = max(max_number, number)
            except ValueError:
                pass

    return max_number + 1


def _detect_task_type(file_path: Path) -> str:
    """Auto-detect create/edit based on file existence.

    Args:
        file_path: Path to the target file

    Returns:
        "create" if file doesn't exist, "edit" if it does
    """
    if file_path.exists():
        return "edit"
    return "create"


def _find_active_snapshot_to_supersede(
    file_path: str, manifests_dir: Path
) -> Optional[str]:
    """Find active snapshot manifest that must be superseded to edit file.

    Per MAID methodology:
    - Snapshots "freeze" a file
    - To edit a snapshotted file, you MUST supersede the snapshot
    - This is automatic, not optional

    Args:
        file_path: Path to the target file (as declared in expectedArtifacts)
        manifests_dir: Path to the manifests directory

    Returns:
        Manifest filename (e.g., "task-012-snapshot.manifest.json") if active
        snapshot exists, None otherwise
    """
    if not manifests_dir.exists():
        return None

    # Get set of superseded manifests
    superseded = get_superseded_manifests(manifests_dir)

    for manifest_path in manifests_dir.glob("task-*.manifest.json"):
        # Skip already-superseded manifests
        if manifest_path in superseded:
            continue

        try:
            with open(manifest_path, "r") as f:
                manifest_data = json.load(f)
        except (json.JSONDecodeError, IOError):
            continue

        # Check if this is a snapshot manifest
        if manifest_data.get("taskType") != "snapshot":
            continue

        # Check if this manifest references our file
        expected_artifacts = manifest_data.get("expectedArtifacts", {})
        if not isinstance(expected_artifacts, dict):
            continue

        manifest_file = expected_artifacts.get("file")
        if manifest_file == file_path:
            return manifest_path.name

    return None


def _generate_manifest(
    goal: str,
    file_path: str,
    task_type: str,
    artifacts: List[dict],
    supersedes: List[str],
    readonly_files: List[str],
    validation_command: List[str],
) -> dict:
    """Build manifest dictionary from provided parameters.

    Args:
        goal: Task goal description
        file_path: Target file path
        task_type: One of "create", "edit", "refactor"
        artifacts: List of artifact dictionaries
        supersedes: List of manifest filenames to supersede
        readonly_files: List of readonly dependency paths
        validation_command: Command array for validation

    Returns:
        Complete manifest dictionary
    """
    # Determine file placement based on task type
    if task_type == "create":
        creatable_files = [file_path]
        editable_files = []
    else:
        # edit, refactor, etc. use editableFiles
        creatable_files = []
        editable_files = [file_path]

    return {
        "goal": goal,
        "taskType": task_type,
        "supersedes": supersedes,
        "creatableFiles": creatable_files,
        "editableFiles": editable_files,
        "readonlyFiles": readonly_files,
        "expectedArtifacts": {
            "file": file_path,
            "contains": artifacts,
        },
        "validationCommand": validation_command,
    }


def _write_manifest(manifest_data: dict, output_path: Path) -> None:
    """Write manifest dictionary to JSON file.

    Creates parent directories if needed.

    Args:
        manifest_data: The manifest dictionary to write
        output_path: Path where to write the manifest file
    """
    # Ensure parent directory exists
    output_path.parent.mkdir(parents=True, exist_ok=True)

    # Write with indent for readability
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(manifest_data, f, indent=2)
