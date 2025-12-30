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
    delete: bool = False,
    rename_to: Optional[str] = None,
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
        delete: If True, create a deletion manifest with status: absent
        rename_to: New file path for rename/move operations

    Returns:
        Exit code: 0 on success, non-zero on failure
    """
    try:
        return _run_create_manifest_impl(
            file_path=file_path,
            goal=goal,
            artifacts=artifacts,
            task_type=task_type,
            force_supersede=force_supersede,
            test_file=test_file,
            readonly_files=readonly_files,
            output_dir=output_dir,
            task_number=task_number,
            json_output=json_output,
            quiet=quiet,
            dry_run=dry_run,
            delete=delete,
            rename_to=rename_to,
        )
    except Exception as e:
        if json_output:
            error_output = {
                "success": False,
                "error": str(e),
            }
            print(json.dumps(error_output, indent=2))
            return 1
        else:
            # Re-raise to show normal traceback
            raise


def _run_create_manifest_impl(
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
    delete: bool = False,
    rename_to: Optional[str] = None,
) -> int:
    """Implementation of manifest creation logic.

    This is the internal implementation, wrapped by run_create_manifest
    which handles errors and JSON output formatting.
    """
    from maid_runner.cli._manifest_helpers import parse_artifacts_json

    # Convert inputs to proper types (handle both CLI strings and direct Python objects)
    output_dir_path = Path(output_dir) if isinstance(output_dir, str) else output_dir

    # Handle rename_to validation early
    if rename_to is not None:
        # Validate rename_to != file_path (normalize paths for comparison)
        # This catches equivalents like "./src/file.py" vs "src/file.py"
        normalized_rename = str(Path(rename_to))
        normalized_source = str(Path(file_path))
        if normalized_rename == normalized_source:
            raise ValueError(
                "Cannot rename to the same path. "
                "--rename-to must be different from the source file."
            )
        # Validate not used with delete flag (mutually exclusive)
        if delete:
            raise ValueError(
                "Cannot use --delete and --rename-to together. "
                "These flags are mutually exclusive."
            )

    # Handle delete flag validation early
    if delete:
        # Validate that artifacts is empty/None when delete=True
        if artifacts is not None:
            # Check if it's a non-empty list or non-empty string
            if isinstance(artifacts, str) and artifacts.strip():
                raise ValueError(
                    "Cannot specify artifacts when delete=True. "
                    "Deletion manifests must have empty artifacts."
                )
            elif isinstance(artifacts, list) and len(artifacts) > 0:
                raise ValueError(
                    "Cannot specify artifacts when delete=True. "
                    "Deletion manifests must have empty artifacts."
                )
        # Force artifacts to empty list for delete manifests
        artifacts_list = []
        # Force task_type to "refactor" for delete manifests
        task_type = "refactor"
    elif rename_to is not None:
        # For rename operations, force task_type to "refactor"
        task_type = "refactor"
        # Handle artifacts: if not provided, copy from existing manifests
        if artifacts is None:
            artifacts_list = _get_artifacts_from_manifests(file_path, output_dir_path)
        elif isinstance(artifacts, str):
            artifacts_list = parse_artifacts_json(artifacts)
        else:
            artifacts_list = artifacts
    else:
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
    active_snapshot = None  # Initialize for later reference in output

    if delete:
        # For delete manifests, auto-supersede ALL active manifests for the file
        active_manifests = _find_active_manifests_to_supersede(
            file_path, output_dir_path
        )
        supersedes.extend(active_manifests)
        if active_manifests and not quiet and not json_output:
            print(
                f"Auto-superseding {len(active_manifests)} active manifest(s): "
                f"{', '.join(active_manifests)}",
                file=sys.stderr,
            )
    elif rename_to is not None:
        # For rename manifests, auto-supersede ALL active manifests for the OLD file
        active_manifests = _find_active_manifests_to_supersede(
            file_path, output_dir_path
        )
        supersedes.extend(active_manifests)
        if active_manifests and not quiet and not json_output:
            print(
                f"Auto-superseding {len(active_manifests)} active manifest(s): "
                f"{', '.join(active_manifests)}",
                file=sys.stderr,
            )
    else:
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
        delete=delete,
        rename_to=rename_to,
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


def _find_active_manifests_to_supersede(
    file_path: str, manifests_dir: Path
) -> List[str]:
    """Find all active manifests that reference a file.

    Unlike _find_active_snapshot_to_supersede which only finds snapshots,
    this finds ALL manifest types (snapshot, edit, create, refactor) that
    reference the given file in expectedArtifacts.

    Args:
        file_path: Path to the target file (as declared in expectedArtifacts)
        manifests_dir: Path to the manifests directory

    Returns:
        List of manifest filenames that reference this file and are not superseded
    """
    if not manifests_dir.exists():
        return []

    # Get set of superseded manifests
    superseded = get_superseded_manifests(manifests_dir)

    result = []
    for manifest_path in manifests_dir.glob("task-*.manifest.json"):
        # Skip already-superseded manifests
        if manifest_path in superseded:
            continue

        try:
            with open(manifest_path, "r") as f:
                manifest_data = json.load(f)
        except (json.JSONDecodeError, IOError):
            continue

        # Check if this manifest references our file in expectedArtifacts
        expected_artifacts = manifest_data.get("expectedArtifacts", {})
        if not isinstance(expected_artifacts, dict):
            continue

        manifest_file = expected_artifacts.get("file")
        if manifest_file == file_path:
            result.append(manifest_path.name)

    return result


def _get_artifacts_from_manifests(file_path: str, manifests_dir: Path) -> List[dict]:
    """Get combined artifacts from all active manifests for a file.

    Used during rename operations to copy existing artifact declarations
    to the new file location.

    Args:
        file_path: Path to the file (as declared in expectedArtifacts)
        manifests_dir: Path to the manifests directory

    Returns:
        List of artifact dictionaries merged from all active manifests
    """
    if not manifests_dir.exists():
        return []

    # Get set of superseded manifests
    superseded = get_superseded_manifests(manifests_dir)

    # Collect artifacts from all active manifests for this file
    all_artifacts = []
    seen_artifact_keys = set()

    for manifest_path in manifests_dir.glob("task-*.manifest.json"):
        # Skip already-superseded manifests
        if manifest_path in superseded:
            continue

        try:
            with open(manifest_path, "r") as f:
                manifest_data = json.load(f)
        except (json.JSONDecodeError, IOError):
            continue

        # Check if this manifest references our file in expectedArtifacts
        expected_artifacts = manifest_data.get("expectedArtifacts", {})
        if not isinstance(expected_artifacts, dict):
            continue

        manifest_file = expected_artifacts.get("file")
        if manifest_file != file_path:
            continue

        # Extract artifacts from contains array
        contains = expected_artifacts.get("contains", [])
        if not isinstance(contains, list):
            continue

        for artifact in contains:
            if not isinstance(artifact, dict):
                continue

            # Create a deduplication key based on type, name, class, args, and returns
            # Include args and returns for functions to handle overloaded signatures
            args_key = ""
            if artifact.get("type") == "function" and "args" in artifact:
                # Serialize args as a tuple of (name, type) pairs for deduplication
                args = artifact.get("args", [])
                if isinstance(args, list):
                    args_key = str(
                        tuple(
                            (a.get("name", ""), a.get("type", ""))
                            for a in args
                            if isinstance(a, dict)
                        )
                    )
            artifact_key = (
                artifact.get("type", ""),
                artifact.get("name", ""),
                artifact.get("class", ""),
                args_key,
                artifact.get("returns", ""),
            )

            if artifact_key not in seen_artifact_keys:
                seen_artifact_keys.add(artifact_key)
                all_artifacts.append(artifact)

    return all_artifacts


def _generate_manifest(
    goal: str,
    file_path: str,
    task_type: str,
    artifacts: List[dict],
    supersedes: List[str],
    readonly_files: List[str],
    validation_command: List[str],
    delete: bool = False,
    rename_to: Optional[str] = None,
) -> dict:
    """Build manifest dictionary from provided parameters.

    Args:
        goal: Task goal description
        file_path: Target file path (source file for rename operations)
        task_type: One of "create", "edit", "refactor"
        artifacts: List of artifact dictionaries
        supersedes: List of manifest filenames to supersede
        readonly_files: List of readonly dependency paths
        validation_command: Command array for validation
        delete: If True, create deletion manifest with status: absent
        rename_to: New file path for rename/move operations. Rename and move
            are semantically equivalent - both relocate a file to a new path.
            Use rename for same-directory changes (e.g., old.py -> new.py)
            and move for cross-directory changes (e.g., src/old.py -> lib/old.py),
            though the manifest structure is identical for both.

    Returns:
        Complete manifest dictionary
    """
    # For delete manifests, always use editableFiles (file exists to be deleted)
    if delete:
        creatable_files = []
        editable_files = [file_path]
    elif rename_to is not None:
        # For rename operations: new file in creatableFiles, old file not in any list
        creatable_files = [rename_to]
        editable_files = []
    elif task_type == "create":
        creatable_files = [file_path]
        editable_files = []
    else:
        # edit, refactor, etc. use editableFiles
        creatable_files = []
        editable_files = [file_path]

    # Determine the file path for expectedArtifacts
    # For rename: use the new path; otherwise use the original path
    artifacts_file = rename_to if rename_to is not None else file_path

    # Build expectedArtifacts
    expected_artifacts = {
        "file": artifacts_file,
        "contains": artifacts,
    }

    # For delete manifests, add status: absent
    if delete:
        expected_artifacts["status"] = "absent"

    return {
        "goal": goal,
        "taskType": task_type,
        "supersedes": supersedes,
        "creatableFiles": creatable_files,
        "editableFiles": editable_files,
        "readonlyFiles": readonly_files,
        "expectedArtifacts": expected_artifacts,
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
