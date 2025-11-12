# maid_runner/validators/file_tracker.py
"""File tracking validation for MAID manifests.

This module provides validation to detect:
- UNDECLARED: Files not in any manifest (high priority)
- REGISTERED: Files in manifest but incomplete compliance (medium priority)
- TRACKED: Files with full MAID compliance (clean)
"""

from pathlib import Path
from typing import Dict, List, Optional, Set
from typing_extensions import TypedDict


# File status constants
FILE_STATUS_UNDECLARED = "UNDECLARED"
FILE_STATUS_REGISTERED = "REGISTERED"
FILE_STATUS_TRACKED = "TRACKED"


# Type definitions
class FileInfo(TypedDict):
    """Information about a tracked file."""

    file: str
    status: str
    issues: List[str]
    manifests: List[str]


class FileTrackingAnalysis(TypedDict):
    """Results of file tracking analysis."""

    undeclared: List[FileInfo]
    registered: List[FileInfo]
    tracked: List[str]


def find_source_files(root_dir: str, exclude_patterns: List[str]) -> Set[str]:
    """Find all Python source files in a directory.

    Args:
        root_dir: Root directory to search
        exclude_patterns: List of glob patterns to exclude

    Returns:
        Set of relative file paths
    """
    root_path = Path(root_dir)
    source_files = set()

    # Find all .py files
    for py_file in root_path.rglob("*.py"):
        relative_path = py_file.relative_to(root_path).as_posix()

        # Check if file matches any exclude pattern
        excluded = False
        for pattern in exclude_patterns:
            # Simple pattern matching (supports basic wildcards)
            if _matches_pattern(relative_path, pattern):
                excluded = True
                break

        if not excluded:
            source_files.add(relative_path)

    return source_files


def _matches_pattern(file_path: str, pattern: str) -> bool:
    """Check if a file path matches an exclude pattern.

    Args:
        file_path: Relative file path
        pattern: Glob-like pattern (e.g., "**/__pycache__/**", ".venv/**")

    Returns:
        True if file matches pattern
    """
    # Handle common patterns
    if pattern.startswith("**"):
        # Pattern like "**/__pycache__/**"
        inner = pattern.strip("*").strip("/")
        return inner in file_path

    if pattern.endswith("/**"):
        # Pattern like ".venv/**"
        prefix = pattern.rstrip("/**")
        return file_path.startswith(prefix + "/") or file_path == prefix

    # Exact match
    return file_path == pattern


def collect_tracked_files(manifest_chain: List[dict]) -> Dict[str, dict]:
    """Collect all tracked files from manifest chain.

    Args:
        manifest_chain: List of manifests

    Returns:
        Dictionary mapping file paths to tracking information
    """
    tracked_files = {}

    for manifest in manifest_chain:
        manifest_goal = manifest.get("goal", "unknown")

        # Collect from creatableFiles
        for file_path in manifest.get("creatableFiles", []):
            if file_path not in tracked_files:
                tracked_files[file_path] = {
                    "created": False,
                    "edited": False,
                    "readonly": False,
                    "has_artifacts": False,
                    "has_tests": False,
                    "manifests": [],
                }
            tracked_files[file_path]["created"] = True
            tracked_files[file_path]["manifests"].append(manifest_goal)

        # Collect from editableFiles
        for file_path in manifest.get("editableFiles", []):
            if file_path not in tracked_files:
                tracked_files[file_path] = {
                    "created": False,
                    "edited": False,
                    "readonly": False,
                    "has_artifacts": False,
                    "has_tests": False,
                    "manifests": [],
                }
            tracked_files[file_path]["edited"] = True
            tracked_files[file_path]["manifests"].append(manifest_goal)

        # Collect from readonlyFiles
        for file_path in manifest.get("readonlyFiles", []):
            if file_path not in tracked_files:
                tracked_files[file_path] = {
                    "created": False,
                    "edited": False,
                    "readonly": False,
                    "has_artifacts": False,
                    "has_tests": False,
                    "manifests": [],
                }
            tracked_files[file_path]["readonly"] = True
            tracked_files[file_path]["manifests"].append(manifest_goal)

        # Check if this manifest has expectedArtifacts
        expected_artifacts = manifest.get("expectedArtifacts", {})
        if expected_artifacts:
            artifact_file = expected_artifacts.get("file")
            if artifact_file and artifact_file in tracked_files:
                tracked_files[artifact_file]["has_artifacts"] = True

        # Check if this manifest has validationCommand (implies tests)
        if manifest.get("validationCommand") or manifest.get("validationCommands"):
            # Mark files in creatableFiles/editableFiles as having tests
            for file_path in manifest.get("creatableFiles", []) + manifest.get(
                "editableFiles", []
            ):
                if file_path in tracked_files:
                    tracked_files[file_path]["has_tests"] = True

    return tracked_files


def classify_file_status(file_path: str, tracked_info: Optional[dict]) -> tuple:
    """Classify file status as UNDECLARED, REGISTERED, or TRACKED.

    Args:
        file_path: Path to the file
        tracked_info: Tracking information from collect_tracked_files

    Returns:
        Tuple of (status, issues_list)
    """
    # UNDECLARED: Not in any manifest
    if tracked_info is None:
        return (FILE_STATUS_UNDECLARED, ["Not found in any manifest"])

    # Check compliance issues
    issues = []

    # Issue: Only in readonlyFiles (no creation/edit record)
    if (
        tracked_info["readonly"]
        and not tracked_info["created"]
        and not tracked_info["edited"]
    ):
        issues.append("Only in readonlyFiles (no creation/edit record)")

    # Issue: No artifact declarations
    if (tracked_info["created"] or tracked_info["edited"]) and not tracked_info[
        "has_artifacts"
    ]:
        issues.append("In creatableFiles/editableFiles but no expectedArtifacts")

    # Issue: No behavioral tests
    if tracked_info["has_artifacts"] and not tracked_info["has_tests"]:
        issues.append("Has artifact declarations but no behavioral tests")

    # TRACKED: Full compliance (no issues)
    if len(issues) == 0:
        return (FILE_STATUS_TRACKED, [])

    # REGISTERED: Some tracking but incomplete
    return (FILE_STATUS_REGISTERED, issues)


def analyze_file_tracking(
    manifest_chain: List[dict], source_root: str
) -> FileTrackingAnalysis:
    """Analyze file tracking across manifest chain.

    Args:
        manifest_chain: List of manifests in chronological order
        source_root: Root directory containing source files

    Returns:
        FileTrackingAnalysis with categorized files
    """
    # Default exclude patterns
    default_excludes = [
        "**/__pycache__/**",
        "**/*.pyc",
        ".venv/**",
        "venv/**",
        ".git/**",
        ".pytest_cache/**",
        "**/.mypy_cache/**",
        "**/.ruff_cache/**",
    ]

    # Find all source files
    all_files = find_source_files(source_root, default_excludes)

    # Collect tracked files from manifests
    tracked_files = collect_tracked_files(manifest_chain)

    # Classify each file
    undeclared = []
    registered = []
    tracked = []

    for file_path in sorted(all_files):
        tracked_info = tracked_files.get(file_path)
        status, issues = classify_file_status(file_path, tracked_info)

        if status == FILE_STATUS_UNDECLARED:
            undeclared.append(
                {"file": file_path, "status": status, "issues": issues, "manifests": []}
            )
        elif status == FILE_STATUS_REGISTERED:
            registered.append(
                {
                    "file": file_path,
                    "status": status,
                    "issues": issues,
                    "manifests": tracked_info["manifests"],
                }
            )
        elif status == FILE_STATUS_TRACKED:
            tracked.append(file_path)

    return {"undeclared": undeclared, "registered": registered, "tracked": tracked}
