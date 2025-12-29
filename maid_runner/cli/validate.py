#!/usr/bin/env python3
"""
Command-line interface for MAID manifest validation.

This script provides a clean CLI for validating manifests against implementation
or behavioral test files using the enhanced AST validator.
"""

import argparse
import json
import re
import subprocess
import sys
import time
from pathlib import Path
from typing import Optional, List, Dict, Set, Any

import jsonschema

from maid_runner.utils import find_project_root, normalize_validation_commands

# Try to import watchdog for watch mode
try:
    from watchdog.observers import Observer
    from watchdog.events import FileSystemEventHandler

    WATCHDOG_AVAILABLE = True
except ImportError:
    WATCHDOG_AVAILABLE = False
    # Provide a dummy base class to avoid NameError during module import
    FileSystemEventHandler = object  # type: ignore
    Observer = None  # type: ignore

from maid_runner.validators.manifest_validator import validate_with_ast, validate_schema
from maid_runner.validators.semantic_validator import (
    validate_manifest_semantics,
    validate_supersession,
    ManifestSemanticError,
)
from maid_runner.validators.file_tracker import analyze_file_tracking

# Import private helpers
from . import _validate_helpers
from . import _test_file_extraction
from . import _behavioral_validation


def _format_file_tracking_output(
    analysis: dict,
    quiet: bool = False,
    validation_summary: Optional[str] = None,
) -> None:
    """Format and print file tracking analysis warnings (internal helper).

    Args:
        analysis: FileTrackingAnalysis dictionary with undeclared, registered, tracked
        quiet: If True, only show summary
        validation_summary: Optional validation summary to display at the top
    """
    undeclared = analysis.get("undeclared", [])
    registered = analysis.get("registered", [])
    tracked = analysis.get("tracked", [])
    untracked_tests = analysis.get("untracked_tests", [])

    total_files = (
        len(undeclared) + len(registered) + len(tracked) + len(untracked_tests)
    )

    if total_files == 0:
        return  # No files to report

    # Only show if there are warnings
    if undeclared or registered or untracked_tests:
        print()
        print("━" * 80)
        print("FILE TRACKING ANALYSIS")
        print("━" * 80)
        print()

    # UNDECLARED files (high priority)
    if undeclared:
        print(f"🔴 UNDECLARED FILES ({len(undeclared)} files)")
        print("  Files exist in codebase but are not tracked in any manifest")
        print()

        if not quiet:
            for file_info in undeclared[:10]:  # Limit to 10 for readability
                print(f"  - {file_info['file']}")
                for issue in file_info["issues"]:
                    print(f"    → {issue}")

            if len(undeclared) > 10:
                print(f"  ... and {len(undeclared) - 10} more")

        print()
        print(
            "  Action: Add these files to creatableFiles or editableFiles in a manifest"
        )
        print()

    # REGISTERED files (medium priority)
    if registered:
        print(f"🟡 REGISTERED FILES ({len(registered)} files)")
        print("  Files are tracked but not fully MAID-compliant")
        print()

        if not quiet:
            for file_info in registered[:10]:  # Limit to 10 for readability
                print(f"  - {file_info['file']}")
                for issue in file_info["issues"]:
                    print(f"    ⚠️  {issue}")
                print(f"    Manifests: {', '.join(file_info['manifests'][:3])}")

            if len(registered) > 10:
                print(f"  ... and {len(registered) - 10} more")

        print()
        print(
            "  Action: Add expectedArtifacts and validationCommand for full compliance"
        )
        print()

    # UNTRACKED TEST FILES (informational)
    if untracked_tests:
        print(f"🔵 UNTRACKED TEST FILES ({len(untracked_tests)} files)")
        print("  Test files not referenced in any manifest")
        print()

        if not quiet:
            for test_file in untracked_tests[:10]:  # Limit to 10 for readability
                print(f"  - {test_file}")

            if len(untracked_tests) > 10:
                print(f"  ... and {len(untracked_tests) - 10} more")

        print()
        print("  Note: Consider adding to readonlyFiles for reference tracking")
        print()

    # Summary
    if undeclared or registered or untracked_tests:
        print(f"✓ TRACKED ({len(tracked)} files)")
        print("  All other source files are fully MAID-compliant")
        print()

        # Build summary string
        summary_parts = []
        if undeclared:
            summary_parts.append(f"{len(undeclared)} UNDECLARED")
        if registered:
            summary_parts.append(f"{len(registered)} REGISTERED")
        if untracked_tests:
            summary_parts.append(f"{len(untracked_tests)} UNTRACKED TESTS")
        summary_parts.append(f"{len(tracked)} TRACKED")

        # Show validation summary if provided
        if validation_summary:
            print(validation_summary)
        print(f"Summary: {', '.join(summary_parts)}")
        print()


def extract_test_files_from_command(validation_command: List[Any]) -> list:
    """Extract test file paths from pytest validation commands.

    Handles various pytest command formats:
    - ["pytest tests/test_file.py -v"] (single string)
    - ["pytest", "tests/test_file.py", "-v"] (separate elements)
    - [["pytest", "test1.py"], ["pytest", "test2.py"]] (validationCommands format)
    - python -m pytest tests/test_file.py tests/test_other.py -v
    - uv run pytest tests/test_*.py -v
    - pytest tests/ -v

    Args:
        validation_command: List of command components (legacy format)
                          OR array of command arrays (enhanced format)

    Returns:
        List of test file paths extracted from the command(s)
    """
    if not validation_command:
        return []

    # Check if this is the enhanced format (array of arrays)
    if _test_file_extraction._is_enhanced_command_format(validation_command):
        return _test_file_extraction._extract_from_multiple_commands(validation_command)
    else:
        # Legacy format: validationCommand = ["pytest", "test.py", "-v"]
        return _test_file_extraction._extract_from_single_command(validation_command)


def validate_behavioral_tests(
    manifest_data: Dict[str, Any],
    test_files: List[str],
    use_manifest_chain: bool = False,
    quiet: bool = False,
) -> None:
    """Validate that behavioral test files use the expected artifacts from the manifest.

    This function validates that test files collectively use all expected artifacts,
    allowing different test files to exercise different parts of the API.

    Args:
        manifest_data: Dictionary containing the manifest with expectedArtifacts
        test_files: List of test file paths to validate
        use_manifest_chain: If True, use manifest chain for validation
        quiet: If True, suppress success messages

    Raises:
        AlignmentError: If test files don't exercise the expected artifacts
        FileNotFoundError: If test files don't exist
    """
    if not test_files:
        return

    test_files = _test_file_extraction._normalize_test_file_paths(test_files)
    _test_file_extraction._validate_test_files_exist(test_files)

    from maid_runner.validators.manifest_validator import (
        should_skip_behavioral_validation,
    )

    usage_data = _behavioral_validation._collect_artifact_usage_from_tests(test_files)

    expected_items = _behavioral_validation._get_expected_artifacts(manifest_data)
    _behavioral_validation._validate_artifacts_usage(
        expected_items, usage_data, should_skip_behavioral_validation
    )


def get_watchable_files_for_manifest(manifest_data: dict) -> List[str]:
    """Extract files that should be watched for a manifest.

    This includes:
    - editableFiles: Implementation files being modified
    - creatableFiles: New implementation files being created
    - Test files: Extracted from validationCommand/validationCommands

    Args:
        manifest_data: Dictionary containing manifest data

    Returns:
        List of file paths that should be watched for changes
    """
    watchable_files = []

    # Get editable files
    editable_files = manifest_data.get("editableFiles", [])
    if editable_files:
        watchable_files.extend(editable_files)

    # Get creatable files
    creatable_files = manifest_data.get("creatableFiles", [])
    if creatable_files:
        watchable_files.extend(creatable_files)

    # Get test files from validation commands
    validation_commands = normalize_validation_commands(manifest_data)
    for cmd in validation_commands:
        test_files = extract_test_files_from_command(cmd)
        watchable_files.extend(test_files)

    # Remove duplicates while preserving order
    seen: Set[str] = set()
    unique_files: List[str] = []
    for f in watchable_files:
        if f not in seen:
            seen.add(f)
            unique_files.append(f)

    return unique_files


def build_file_to_manifests_map_for_validation(
    manifests_dir: Path, active_manifests: List[Path]
) -> Dict[Path, List[Path]]:
    """Build a mapping from file paths to lists of manifests that reference them.

    Args:
        manifests_dir: Path to the manifests directory
        active_manifests: List of paths to active (non-superseded) manifests

    Returns:
        Dictionary mapping absolute file paths to lists of manifest paths
    """
    file_to_manifests: Dict[Path, List[Path]] = {}
    project_root = find_project_root(manifests_dir)

    for manifest_path in active_manifests:
        try:
            with open(manifest_path, "r") as f:
                manifest_data = json.load(f)

            # Get all watchable files from this manifest
            watchable_files = get_watchable_files_for_manifest(manifest_data)

            # Add this manifest to the mapping for each watchable file
            for file_path in watchable_files:
                absolute_path = (project_root / file_path).resolve()
                if absolute_path not in file_to_manifests:
                    file_to_manifests[absolute_path] = []
                file_to_manifests[absolute_path].append(manifest_path)

            # Also add the manifest file itself
            manifest_absolute = manifest_path.resolve()
            if manifest_absolute not in file_to_manifests:
                file_to_manifests[manifest_absolute] = []
            file_to_manifests[manifest_absolute].append(manifest_path)

        except (json.JSONDecodeError, IOError):
            continue

    return file_to_manifests


class _MultiManifestValidationHandler(FileSystemEventHandler):
    """Handle file change events for multi-manifest validation watch mode."""

    def __init__(
        self,
        file_to_manifests: Dict[Path, List[Path]],
        use_manifest_chain: bool,
        quiet: bool,
        skip_tests: bool,
        timeout: int,
        verbose: bool,
        project_root: Path,
        manifests_dir: Optional[Path] = None,
        observer: Optional["Observer"] = None,
    ):
        """Initialize handler for multi-manifest validation watch mode.

        Args:
            file_to_manifests: Mapping from absolute file paths to manifest lists
            use_manifest_chain: If True, use manifest chain for validation
            quiet: If True, suppress non-essential output
            skip_tests: If True, skip running validationCommand
            timeout: Command timeout in seconds
            verbose: If True, show detailed output
            project_root: Root directory for executing commands
            manifests_dir: Path to manifests directory for dynamic discovery
            observer: Reference to the observer for dynamic scheduling
        """
        self.file_to_manifests = file_to_manifests
        self.use_manifest_chain = use_manifest_chain
        self.quiet = quiet
        self.skip_tests = skip_tests
        self.timeout = timeout
        self.verbose = verbose
        self.project_root = project_root
        self.manifests_dir = manifests_dir
        self.observer = observer
        self.last_run = 0.0
        self.debounce_seconds = 2.0
        self._watched_dirs: Set[Path] = set()
        self._known_manifests: Set[Path] = set()

    def _run_validation_for_manifest(self, manifest_path: Path) -> None:
        """Run dual mode validation and optionally tests for a manifest."""
        _run_validation_with_tests(
            manifest_path=manifest_path,
            use_manifest_chain=self.use_manifest_chain,
            quiet=self.quiet,
            skip_tests=self.skip_tests,
            project_root=self.project_root,
            timeout=self.timeout,
            verbose=self.verbose,
        )

    def on_modified(self, event) -> None:
        """Run validation for affected manifests when watched files change."""
        if event.is_directory:
            return

        current_time = time.time()
        if _should_skip_debounce(self.last_run, current_time, self.debounce_seconds):
            return

        modified_path = Path(event.src_path).resolve()
        affected_manifests = self.file_to_manifests.get(modified_path)

        if affected_manifests:
            self.last_run = current_time

            display_path = _get_display_path(modified_path, self.project_root)
            if not self.quiet:
                print(f"\n🔔 Detected change in {display_path}", flush=True)

            for manifest_path in affected_manifests:
                if not self.quiet:
                    print(f"\n📋 Validating {manifest_path.name}", flush=True)
                self._run_validation_for_manifest(manifest_path)

    def on_created(self, event) -> None:
        """Handle file creation events for dynamic manifest discovery."""
        if event.is_directory:
            return

        src_path = str(event.src_path)

        if src_path.endswith(".manifest.json"):
            if self.manifests_dir is not None:
                if not self.quiet:
                    print(
                        f"\n🔄 New manifest detected: {Path(src_path).name}", flush=True
                    )
                self.refresh_file_mappings()
            return

        self.on_modified(event)

    def on_deleted(self, event) -> None:
        """Handle file deletion events."""
        if event.is_directory:
            return

        src_path = str(event.src_path)

        if src_path.endswith(".manifest.json"):
            if self.manifests_dir is not None:
                if not self.quiet:
                    print(f"\n🗑️  Manifest deleted: {Path(src_path).name}", flush=True)
                self.refresh_file_mappings()

    def on_moved(self, event) -> None:
        """Handle file move/rename events for atomic write detection."""
        if event.is_directory:
            return

        dest_path = str(event.dest_path)

        if dest_path.endswith(".manifest.json"):
            if self.manifests_dir is not None:
                if not self.quiet:
                    print(
                        f"\n🔄 New manifest detected: {Path(dest_path).name}",
                        flush=True,
                    )
                self.refresh_file_mappings()
            return

        class _FakeEvent:
            def __init__(self, path, is_dir=False):
                self.src_path = path
                self.is_directory = is_dir

        self.on_modified(_FakeEvent(dest_path))

    def refresh_file_mappings(self) -> None:
        """Rebuild file-to-manifests mapping from manifests directory."""
        if self.manifests_dir is None:
            return

        from maid_runner.utils import get_superseded_manifests

        manifest_files = sorted(self.manifests_dir.glob("task-*.manifest.json"))
        superseded = get_superseded_manifests(self.manifests_dir)
        active_manifests = [m for m in manifest_files if m not in superseded]

        current_manifest_set = set(active_manifests)
        new_manifests = current_manifest_set - self._known_manifests
        self._known_manifests = current_manifest_set

        new_mapping = build_file_to_manifests_map_for_validation(
            self.manifests_dir, active_manifests
        )
        self.file_to_manifests.clear()
        self.file_to_manifests.update(new_mapping)

        if self.observer is not None:
            for file_path in new_mapping.keys():
                parent_dir = file_path.parent
                if parent_dir not in self._watched_dirs:
                    try:
                        self.observer.schedule(self, str(parent_dir), recursive=False)
                        self._watched_dirs.add(parent_dir)
                        if not self.quiet:
                            print(f"   👁️  Now watching: {parent_dir}", flush=True)
                    except Exception:
                        pass

        for manifest_path in sorted(new_manifests):
            if not self.quiet:
                print(f"\n📋 Validating new manifest: {manifest_path.name}", flush=True)
            self._run_validation_for_manifest(manifest_path)


class _ManifestFileChangeHandler(FileSystemEventHandler):
    """Handle manifest and related file change events for watch mode."""

    def __init__(
        self,
        manifest_path: Path,
        use_manifest_chain: bool,
        quiet: bool,
        skip_tests: bool,
        timeout: int,
        verbose: bool,
        project_root: Path,
    ):
        """Initialize manifest file change handler.

        Args:
            manifest_path: Path to the manifest file to watch
            use_manifest_chain: If True, use manifest chain for validation
            quiet: If True, suppress non-essential output
            skip_tests: If True, skip running validationCommand
            timeout: Command timeout in seconds
            verbose: If True, show detailed output
            project_root: Root directory for executing commands
        """
        self.manifest_path = manifest_path
        self.use_manifest_chain = use_manifest_chain
        self.quiet = quiet
        self.skip_tests = skip_tests
        self.timeout = timeout
        self.verbose = verbose
        self.project_root = project_root
        self.last_run = 0.0
        self.debounce_seconds = 2.0

        # Cache watchable files as absolute paths for efficient comparison
        self._refresh_watchable_paths()

    def _refresh_watchable_paths(self) -> None:
        """Refresh the set of watchable paths from the manifest."""
        try:
            with open(self.manifest_path, "r") as f:
                manifest_data = json.load(f)
            watchable_files = get_watchable_files_for_manifest(manifest_data)
            self.watchable_paths: Set[Path] = {
                (self.project_root / f).resolve() for f in watchable_files
            }
            # Also include the manifest itself
            self.watchable_paths.add(self.manifest_path.resolve())
        except (json.JSONDecodeError, IOError):
            # If manifest can't be read, just watch the manifest itself
            self.watchable_paths = {self.manifest_path.resolve()}

    def _is_watched_file(self, file_path: Path) -> bool:
        """Check if a file is in our watchable paths.

        Args:
            file_path: Path to check

        Returns:
            True if file should trigger validation
        """
        resolved_path = file_path.resolve()
        return resolved_path in self.watchable_paths

    def on_modified(self, event) -> None:
        """Handle file modification events.

        Args:
            event: Filesystem event containing information about the modified file
        """
        if event.is_directory:
            return

        modified_path = Path(event.src_path)
        if not self._is_watched_file(modified_path):
            return

        current_time = time.time()
        if _should_skip_debounce(self.last_run, current_time, self.debounce_seconds):
            return
        self.last_run = current_time

        display_path = _get_display_path(modified_path, self.project_root)
        if not self.quiet:
            print(f"\n🔔 Detected change in {display_path}", flush=True)

        if modified_path.resolve() == self.manifest_path.resolve():
            self._refresh_watchable_paths()

        self._run_validation()

    def on_created(self, event) -> None:
        """Handle file creation events.

        Args:
            event: Filesystem event containing information about the created file
        """
        if event.is_directory:
            return

        created_path = Path(event.src_path)
        if not self._is_watched_file(created_path):
            return

        current_time = time.time()
        if _should_skip_debounce(self.last_run, current_time, self.debounce_seconds):
            return
        self.last_run = current_time

        display_path = _get_display_path(created_path, self.project_root)
        if not self.quiet:
            print(f"\n🔔 File created: {display_path}", flush=True)

        self._run_validation()

    def on_moved(self, event) -> None:
        """Handle file move/rename events for atomic write detection.

        Many editors use atomic writes: write to temp file, then rename.
        This triggers on_moved instead of on_modified.

        Args:
            event: Filesystem event with src_path (old) and dest_path (new)
        """
        if event.is_directory:
            return

        dest_path = Path(event.dest_path)
        if not self._is_watched_file(dest_path):
            return

        current_time = time.time()
        if _should_skip_debounce(self.last_run, current_time, self.debounce_seconds):
            return
        self.last_run = current_time

        display_path = _get_display_path(dest_path, self.project_root)
        if not self.quiet:
            print(f"\n🔔 Detected change in {display_path}", flush=True)

        if dest_path.resolve() == self.manifest_path.resolve():
            self._refresh_watchable_paths()

        self._run_validation()

    def _run_validation(self) -> None:
        """Run dual mode validation and optionally execute tests."""
        _run_validation_with_tests(
            manifest_path=self.manifest_path,
            use_manifest_chain=self.use_manifest_chain,
            quiet=self.quiet,
            skip_tests=self.skip_tests,
            project_root=self.project_root,
            timeout=self.timeout,
            verbose=self.verbose,
        )


def _extract_task_id(manifest_path: Path) -> str:
    """Extract task ID from manifest filename.

    Args:
        manifest_path: Path to the manifest file

    Returns:
        Task ID (e.g., "task-070") or empty string if not found
    """
    filename = manifest_path.name
    match = re.match(r"(task-\d+)", filename)
    return match.group(1) if match else ""


# Re-export helpers for backward compatibility
_are_validations_passed = _validate_helpers._are_validations_passed
_get_display_path = _validate_helpers._get_display_path
_should_skip_debounce = _validate_helpers._should_skip_debounce

# Re-export test file extraction helpers for backward compatibility
_is_enhanced_command_format = _test_file_extraction._is_enhanced_command_format
_extract_from_multiple_commands = _test_file_extraction._extract_from_multiple_commands
_extract_from_single_command = _test_file_extraction._extract_from_single_command
_extract_from_string_commands = _test_file_extraction._extract_from_string_commands
_extract_from_list_command = _test_file_extraction._extract_from_list_command
_find_pytest_index = _test_file_extraction._find_pytest_index
_filter_test_paths_from_args = _test_file_extraction._filter_test_paths_from_args
_normalize_test_file_paths = _test_file_extraction._normalize_test_file_paths
_validate_test_files_exist = _test_file_extraction._validate_test_files_exist
_find_imported_test_files = _test_file_extraction._find_imported_test_files

# Re-export behavioral validation helpers for backward compatibility
_collect_artifact_usage_from_tests = (
    _behavioral_validation._collect_artifact_usage_from_tests
)
_get_expected_artifacts = _behavioral_validation._get_expected_artifacts
_validate_artifacts_usage = _behavioral_validation._validate_artifacts_usage
_validate_no_self_parameter = _behavioral_validation._validate_no_self_parameter
_validate_class_usage = _behavioral_validation._validate_class_usage
_validate_function_usage = _behavioral_validation._validate_function_usage
_validate_method_usage = _behavioral_validation._validate_method_usage
_validate_standalone_function_usage = (
    _behavioral_validation._validate_standalone_function_usage
)
_validate_parameters_usage = _behavioral_validation._validate_parameters_usage


def _run_tests_for_manifest(
    manifest_path: Path,
    project_root: Path,
    timeout: int,
    verbose: bool,
    quiet: bool,
) -> bool:
    """Load manifest and run validation command.

    Args:
        manifest_path: Path to manifest file
        project_root: Project root directory
        timeout: Command timeout in seconds
        verbose: If True, show detailed output
        quiet: If True, suppress error messages

    Returns:
        True if tests passed, False otherwise
    """
    try:
        with open(manifest_path, "r") as f:
            manifest_data = json.load(f)
        return execute_validation_command(
            manifest_data=manifest_data,
            project_root=project_root,
            timeout=timeout,
            verbose=verbose,
        )
    except (json.JSONDecodeError, IOError) as e:
        if not quiet:
            print(f"⚠️  Error loading manifest: {e}", flush=True)
        return False


def _run_validation_with_tests(
    manifest_path: Path,
    use_manifest_chain: bool,
    quiet: bool,
    skip_tests: bool,
    project_root: Path,
    timeout: int,
    verbose: bool,
) -> Dict[str, Optional[bool]]:
    """Run dual mode validation and optionally execute tests.

    Args:
        manifest_path: Path to manifest file
        use_manifest_chain: If True, use manifest chain for validation
        quiet: If True, suppress non-essential output
        skip_tests: If True, skip running validationCommand
        project_root: Project root directory
        timeout: Command timeout in seconds
        verbose: If True, show detailed output

    Returns:
        Dict with validation results including tests
    """
    results = run_dual_mode_validation(
        manifest_path=manifest_path,
        use_manifest_chain=use_manifest_chain,
        quiet=quiet,
    )

    if _are_validations_passed(results) and not skip_tests:
        test_success = _run_tests_for_manifest(
            manifest_path, project_root, timeout, verbose, quiet
        )
        results["tests"] = test_success

    task_id = _extract_task_id(manifest_path)
    _print_validation_summary(task_id, results, quiet)
    return results


def _print_validation_summary(
    task_id: str,
    results: Dict[str, Optional[bool]],
    quiet: bool = False,
) -> None:
    """Print a summary of validation results.

    Args:
        task_id: Task identifier (e.g., "task-070")
        results: Dict with keys 'schema', 'behavioral', 'implementation', 'tests'
                 Values are True (passed), False (failed), or None (skipped)
        quiet: If True, suppress output
    """
    if quiet:
        return

    # Status icons mapping
    _icons = {True: "✅", False: "❌", None: "⏭️"}

    task_prefix = f"[{task_id}] " if task_id else ""

    # Count passed/total (only count non-None results)
    active_results = {k: v for k, v in results.items() if v is not None}
    passed = sum(1 for v in active_results.values() if v is True)
    total = len(active_results)

    # Build summary parts
    parts = []
    for key in ["schema", "behavioral", "implementation", "tests"]:
        result = results.get(key)
        icon = _icons.get(result, "⏭️")
        label = key.capitalize()
        parts.append(f"{icon} {label}")

    print()
    print("━" * 70, flush=True)
    print(f"📊 {task_prefix}{passed}/{total} passed ({' | '.join(parts)})", flush=True)
    print("━" * 70, flush=True)


def run_dual_mode_validation(
    manifest_path: Path,
    use_manifest_chain: bool,
    quiet: bool,
) -> Dict[str, Optional[bool]]:
    """Run schema, behavioral, and implementation validation on a manifest.

    Validates in three stages:
    1. Schema validation - manifest structure against JSON schema
    2. Behavioral validation - tests USE declared artifacts
    3. Implementation validation - code DEFINES declared artifacts

    Args:
        manifest_path: Path to the manifest file
        use_manifest_chain: If True, use manifest chain for validation
        quiet: If True, suppress success messages

    Returns:
        Dict with validation results: {'schema': bool, 'behavioral': bool,
        'implementation': bool, 'tests': None}. 'tests' is always None
        (to be filled by caller after running tests).
    """
    results: Dict[str, Optional[bool]] = {
        "schema": None,
        "behavioral": None,
        "implementation": None,
        "tests": None,
    }
    task_id = _extract_task_id(manifest_path)
    task_prefix = f"[{task_id}] " if task_id else ""

    # Stage 1: Schema validation
    if not quiet:
        print(f"\n📋 {task_prefix}Running schema validation...", flush=True)

    try:
        # Load and validate manifest against schema
        with open(manifest_path, "r") as f:
            manifest_data = json.load(f)

        schema_path = (
            Path(__file__).parent.parent
            / "validators"
            / "schemas"
            / "manifest.schema.json"
        )
        validate_schema(manifest_data, str(schema_path))

        results["schema"] = True
        if not quiet:
            print("  ✅ Schema validation PASSED", flush=True)
    except (json.JSONDecodeError, jsonschema.ValidationError, FileNotFoundError) as e:
        results["schema"] = False
        if not quiet:
            print(f"  ❌ Schema validation FAILED: {e}", flush=True)
        return results  # Can't continue without valid schema

    # Stage 2 & 3: Behavioral and Implementation validation
    validation_modes = ["behavioral", "implementation"]

    for mode in validation_modes:
        try:
            if not quiet:
                print(f"\n📋 {task_prefix}Running {mode} validation...", flush=True)

            run_validation(
                manifest_path=str(manifest_path),
                validation_mode=mode,
                use_manifest_chain=use_manifest_chain,
                quiet=True,  # Suppress individual messages
                manifest_dir=None,
                skip_file_tracking=True,
            )

            results[mode] = True
            if not quiet:
                print(f"  ✅ {mode.capitalize()} validation PASSED", flush=True)

        except SystemExit as e:
            if e.code == 0:
                results[mode] = True
                if not quiet:
                    print(f"  ✅ {mode.capitalize()} validation PASSED", flush=True)
            else:
                results[mode] = False
                if not quiet:
                    print(f"  ❌ {mode.capitalize()} validation FAILED", flush=True)
        except FileNotFoundError as e:
            # File not found - don't crash watch mode
            results[mode] = False
            if not quiet:
                print(f"  ⚠️  {e}", flush=True)

    return results


def execute_validation_command(
    manifest_data: dict,
    project_root: Path,
    timeout: int,
    verbose: bool,
) -> bool:
    """Execute the validation command from a manifest.

    Args:
        manifest_data: Dictionary containing manifest data
        project_root: Project root directory where commands should be executed
        timeout: Command timeout in seconds
        verbose: If True, show detailed command output

    Returns:
        True if all commands pass, False otherwise
    """
    import os

    validation_commands = normalize_validation_commands(manifest_data)

    if not validation_commands:
        return True  # No commands to run = success

    all_passed = True
    total = len(validation_commands)

    # Set up environment
    env = os.environ.copy()
    current_pythonpath = env.get("PYTHONPATH", "")
    pythonpath_additions = [str(project_root)]
    if current_pythonpath:
        pythonpath_additions.append(current_pythonpath)
    env["PYTHONPATH"] = ":".join(pythonpath_additions)

    print("\n🧪 Running validation command(s)...", flush=True)

    for i, cmd in enumerate(validation_commands):
        if not cmd:
            continue

        cmd_str = " ".join(cmd)
        print(f"  [{i+1}/{total}] {cmd_str}", flush=True)

        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=timeout,
                cwd=project_root,
                env=env,
            )

            if result.returncode == 0:
                print("    ✅ PASSED", flush=True)
                if verbose and result.stdout:
                    for line in result.stdout.strip().split("\n"):
                        print(f"      {line}", flush=True)
            else:
                all_passed = False
                print(f"    ❌ FAILED (exit code: {result.returncode})", flush=True)
                if result.stderr:
                    stderr_lines = result.stderr.strip().split("\n")[:10]
                    for line in stderr_lines:
                        print(f"      {line}", flush=True)

        except subprocess.TimeoutExpired:
            all_passed = False
            print(f"    ⏰ TIMEOUT (>{timeout}s)", flush=True)
        except FileNotFoundError:
            all_passed = False
            print(f"    ❌ Command not found: {cmd[0]}", flush=True)
        except Exception as e:
            all_passed = False
            print(f"    ❌ Error: {e}", flush=True)

    return all_passed


def watch_manifest_validation(
    manifest_path: Path,
    use_manifest_chain: bool,
    quiet: bool,
    skip_tests: bool,
    timeout: int,
    verbose: bool,
) -> None:
    """Watch a manifest and related files, run validation when they change.

    Watches:
    - The manifest file itself
    - Implementation files (editableFiles, creatableFiles)
    - Test files (from validationCommand)

    Args:
        manifest_path: Path to the manifest file to watch
        use_manifest_chain: If True, use manifest chain for validation
        quiet: If True, suppress non-essential output
        skip_tests: If True, skip running validationCommand
        timeout: Command timeout in seconds
        verbose: If True, show detailed output
    """
    if not WATCHDOG_AVAILABLE:
        print("❌ Watchdog not available. Install with: pip install watchdog")
        sys.exit(1)

    project_root = find_project_root(manifest_path.parent)

    # Load manifest to get watchable files
    try:
        with open(manifest_path, "r") as f:
            manifest_data = json.load(f)
        watchable_files = get_watchable_files_for_manifest(manifest_data)
    except (json.JSONDecodeError, IOError):
        watchable_files = []

    print(f"\n👁️  Watch mode enabled for: {manifest_path.name}", flush=True)
    if watchable_files:
        print(f"👀 Watching {len(watchable_files)} file(s) + manifest", flush=True)
    print("Press Ctrl+C to stop.", flush=True)

    # Run initial validation
    print("\n📋 Running initial validation:", flush=True)
    _run_validation_with_tests(
        manifest_path=manifest_path,
        use_manifest_chain=use_manifest_chain,
        quiet=quiet,
        skip_tests=skip_tests,
        project_root=project_root,
        timeout=timeout,
        verbose=verbose,
    )

    # Set up file watching
    event_handler = _ManifestFileChangeHandler(
        manifest_path=manifest_path,
        use_manifest_chain=use_manifest_chain,
        quiet=quiet,
        skip_tests=skip_tests,
        timeout=timeout,
        verbose=verbose,
        project_root=project_root,
    )

    observer = Observer()

    # Watch all directories containing watchable files
    watched_dirs: Set[Path] = set()

    # Always watch the manifest directory
    manifest_dir = manifest_path.parent.resolve()
    observer.schedule(event_handler, str(manifest_dir), recursive=False)
    watched_dirs.add(manifest_dir)

    # Watch directories of implementation and test files
    for file_path in watchable_files:
        parent_dir = (project_root / file_path).parent.resolve()
        if parent_dir not in watched_dirs:
            try:
                observer.schedule(event_handler, str(parent_dir), recursive=False)
                watched_dirs.add(parent_dir)
            except Exception:
                # Directory might not exist yet
                pass

    try:
        observer.start()
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        observer.stop()
        print("\n👋 Stopping watch mode", flush=True)
    observer.join()


def watch_all_validations(
    manifests_dir: Path,
    use_manifest_chain: bool,
    quiet: bool,
    skip_tests: bool,
    timeout: int,
    verbose: bool,
) -> None:
    """Watch all manifests and related files, run validation when they change.

    Uses a single handler with file-to-manifests mapping for efficient watching.
    Supports dynamic manifest discovery (new manifests are auto-detected).

    Watches:
    - All manifest files in the directory
    - All implementation files (editableFiles, creatableFiles) from each manifest
    - All test files (from validationCommand) from each manifest

    Args:
        manifests_dir: Path to the manifests directory
        use_manifest_chain: If True, use manifest chain for validation
        quiet: If True, suppress non-essential output
        skip_tests: If True, skip running validationCommand
        timeout: Command timeout in seconds
        verbose: If True, show detailed output
    """
    if not WATCHDOG_AVAILABLE:
        print("❌ Watchdog not available. Install with: pip install watchdog")
        sys.exit(1)

    from maid_runner.utils import get_superseded_manifests

    project_root = find_project_root(manifests_dir)

    # Get all active manifests
    manifest_files = sorted(manifests_dir.glob("task-*.manifest.json"))
    superseded = get_superseded_manifests(manifests_dir)
    active_manifests = [m for m in manifest_files if m not in superseded]

    if not active_manifests:
        print("⚠️  No active manifest files found")
        return

    # Build file-to-manifests mapping
    file_to_manifests = build_file_to_manifests_map_for_validation(
        manifests_dir, active_manifests
    )

    # Get all unique watchable files
    all_watchable_files = set(file_to_manifests.keys())

    print(
        f"\n👁️  Multi-manifest watch mode enabled for {len(active_manifests)} manifest(s)",
        flush=True,
    )
    if all_watchable_files:
        print(
            f"👀 Watching {len(all_watchable_files)} file(s)",
            flush=True,
        )
    print("Press Ctrl+C to stop.", flush=True)

    # Run initial validation for all manifests
    print("\n📋 Running initial validation for all manifests:", flush=True)
    for manifest_path in active_manifests:
        if not quiet:
            print(f"\n📋 {manifest_path.name}", flush=True)

        _run_validation_with_tests(
            manifest_path=manifest_path,
            use_manifest_chain=use_manifest_chain,
            quiet=quiet,
            skip_tests=skip_tests,
            project_root=project_root,
            timeout=timeout,
            verbose=verbose,
        )

    # Create single handler with file-to-manifests mapping
    observer = Observer()

    event_handler = _MultiManifestValidationHandler(
        file_to_manifests=file_to_manifests,
        use_manifest_chain=use_manifest_chain,
        quiet=quiet,
        skip_tests=skip_tests,
        timeout=timeout,
        verbose=verbose,
        project_root=project_root,
        manifests_dir=manifests_dir,
        observer=observer,
    )

    # Watch all directories containing watchable files
    watched_dirs: Set[Path] = set()
    for file_path in all_watchable_files:
        parent_dir = file_path.parent
        if parent_dir not in watched_dirs:
            try:
                observer.schedule(event_handler, str(parent_dir), recursive=False)
                watched_dirs.add(parent_dir)
            except Exception:
                pass

    # Always watch the manifests directory for dynamic discovery
    if manifests_dir.resolve() not in watched_dirs:
        observer.schedule(event_handler, str(manifests_dir), recursive=False)
        watched_dirs.add(manifests_dir.resolve())

    # Initialize handler state
    event_handler._watched_dirs = watched_dirs
    event_handler._known_manifests = set(active_manifests)

    try:
        observer.start()
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        observer.stop()
        print("\n👋 Stopping watch mode", flush=True)
    observer.join()


def _run_directory_validation(
    manifest_dir: str,
    validation_mode: str,
    use_manifest_chain: bool,
    quiet: bool,
) -> None:
    """Validate all manifests in a directory.

    Args:
        manifest_dir: Path to directory containing manifests
        validation_mode: Validation mode ('implementation' or 'behavioral')
        use_manifest_chain: If True, use manifest chain to merge related manifests
        quiet: If True, suppress success messages

    Raises:
        SystemExit: Exits with code 0 on success, 1 on failure
    """
    import os
    from maid_runner.utils import (
        get_superseded_manifests,
        print_maid_not_enabled_message,
        print_no_manifests_found_message,
    )

    manifests_dir = Path(manifest_dir).resolve()

    if not manifests_dir.exists():
        print_maid_not_enabled_message(str(manifest_dir))
        sys.exit(0)

    manifest_files = sorted(manifests_dir.glob("task-*.manifest.json"))
    if not manifest_files:
        print_no_manifests_found_message(str(manifest_dir))
        sys.exit(0)

    # Get superseded manifests and filter them out
    superseded = get_superseded_manifests(manifests_dir)
    active_manifests = [m for m in manifest_files if m not in superseded]

    if not active_manifests:
        print("⚠️  No active manifest files found")
        sys.exit(0)

    if superseded and not quiet:
        print(f"⏭️  Skipping {len(superseded)} superseded manifest(s)\n")

    # Change to project root directory for validation
    # This ensures relative paths in manifests are resolved correctly
    project_root = find_project_root(manifests_dir)
    original_cwd = os.getcwd()
    os.chdir(project_root)

    total_passed = 0
    total_failed = 0
    manifests_with_failures = []

    try:
        for manifest_path in active_manifests:
            if not quiet:
                print(f"📋 Validating {manifest_path.name}...")

            # Validate this manifest using the single-manifest validation logic
            # We'll capture the exit by catching SystemExit
            try:
                run_validation(
                    manifest_path=str(manifest_path),
                    validation_mode=validation_mode,
                    use_manifest_chain=use_manifest_chain,
                    quiet=True,  # Suppress individual success messages
                    manifest_dir=None,  # Prevent recursion
                    skip_file_tracking=True,  # Skip per-manifest tracking
                )
                total_passed += 1
                if not quiet:
                    print("  ✅ PASSED\n")
            except SystemExit as e:
                if e.code == 0:
                    total_passed += 1
                    if not quiet:
                        print("  ✅ PASSED\n")
                else:
                    total_failed += 1
                    manifests_with_failures.append(manifest_path.name)
                    if not quiet:
                        print("  ❌ FAILED\n")
            except FileNotFoundError as e:
                # File not found (test files, implementation files, etc.)
                total_failed += 1
                manifests_with_failures.append(manifest_path.name)
                if not quiet:
                    print(f"  ⚠️  {e}\n")
    finally:
        # Restore original working directory
        os.chdir(original_cwd)

    # Print summary
    total_manifests = total_passed + total_failed
    percentage = (total_passed / total_manifests * 100) if total_manifests > 0 else 0
    print(
        f"📊 Summary: {total_passed}/{total_manifests} manifest(s) passed ({percentage:.1f}%)"
    )

    if manifests_with_failures:
        print(f"   ❌ Failed manifests: {', '.join(manifests_with_failures)}")

    # FILE TRACKING ANALYSIS (once for all manifests)
    # Run only if using manifest chain and in implementation mode
    if use_manifest_chain and validation_mode == "implementation":
        try:
            # Load all manifests
            manifest_chain = []
            for manifest_file in sorted(manifests_dir.glob("task-*.manifest.json")):
                with open(manifest_file, "r") as f:
                    manifest_data = json.load(f)
                    # Add filename to manifest data for tracking purposes
                    manifest_data["_filename"] = manifest_file.name
                    manifest_chain.append(manifest_data)

            # Analyze file tracking
            source_root = str(project_root)
            analysis = analyze_file_tracking(manifest_chain, source_root)

            # Build validation summary
            validation_summary = (
                f"📊 Validation: {total_passed}/{total_manifests} manifest(s) passed "
                f"({percentage:.1f}%)"
            )

            # Display warnings
            _format_file_tracking_output(
                analysis, quiet=quiet, validation_summary=validation_summary
            )

        except Exception as e:
            # Don't fail validation if file tracking has issues
            if not quiet:
                print(f"\n⚠️  File tracking analysis failed: {e}")

    # Exit with appropriate code
    if total_failed > 0:
        sys.exit(1)
    else:
        sys.exit(0)


def run_validation(
    manifest_path: Optional[str] = None,
    validation_mode: str = "implementation",
    use_manifest_chain: bool = False,
    quiet: bool = False,
    manifest_dir: Optional[str] = None,
    skip_file_tracking: bool = False,
    watch: bool = False,
    watch_all: bool = False,
    timeout: int = 300,
    verbose: bool = False,
    skip_tests: bool = False,
) -> None:
    """Core validation logic accepting parsed arguments.

    Args:
        manifest_path: Path to the manifest JSON file (mutually exclusive with manifest_dir)
        validation_mode: Validation mode ('implementation' or 'behavioral')
        use_manifest_chain: If True, use manifest chain to merge related manifests
        quiet: If True, suppress success messages
        manifest_dir: Path to directory containing manifests to validate all at once
        skip_file_tracking: If True, skip file tracking analysis (used in batch mode)
        watch: If True, watch the manifest file for changes
        watch_all: If True, watch all manifests for changes
        timeout: Command timeout in seconds (default: 300)
        verbose: If True, show detailed output
        skip_tests: If True, skip running validationCommand

    Raises:
        SystemExit: Exits with code 0 on success, 1 on failure
    """
    # Handle --watch-all mode: watch all manifests in directory
    if watch_all:
        manifests_dir = Path(manifest_dir) if manifest_dir else Path("manifests")
        if not manifests_dir.exists():
            print(f"✗ Error: Manifests directory not found: {manifests_dir}")
            sys.exit(1)
        watch_all_validations(
            manifests_dir=manifests_dir,
            use_manifest_chain=use_manifest_chain,
            quiet=quiet,
            skip_tests=skip_tests,
            timeout=timeout,
            verbose=verbose,
        )
        return

    # Handle --watch mode: watch single manifest
    if watch:
        if not manifest_path:
            print("✗ Error: --watch requires a manifest path")
            sys.exit(1)
        manifest_path_obj = Path(manifest_path)
        if not manifest_path_obj.exists():
            print(f"✗ Error: Manifest file not found: {manifest_path}")
            sys.exit(1)
        watch_manifest_validation(
            manifest_path=manifest_path_obj,
            use_manifest_chain=use_manifest_chain,
            quiet=quiet,
            skip_tests=skip_tests,
            timeout=timeout,
            verbose=verbose,
        )
        return

    # Handle --manifest-dir mode
    if manifest_dir:
        _run_directory_validation(
            manifest_dir, validation_mode, use_manifest_chain, quiet
        )
        return

    try:
        # Validate manifest file exists
        manifest_path_obj = Path(manifest_path)
        if not manifest_path_obj.exists():
            print(f"✗ Error: Manifest file not found: {manifest_path}")
            sys.exit(1)

        # Load the manifest
        with open(manifest_path_obj, "r") as f:
            manifest_data = json.load(f)

        # Validate against JSON schema
        schema_path = (
            Path(__file__).parent.parent
            / "validators"
            / "schemas"
            / "manifest.schema.json"
        )
        try:
            validate_schema(manifest_data, str(schema_path))
        except jsonschema.ValidationError as e:
            print("✗ Error: Manifest validation failed", file=sys.stderr)
            print(f"  {e.message}", file=sys.stderr)
            if e.path:
                path_str = ".".join(str(p) for p in e.path)
                print(f"  Location: {path_str}", file=sys.stderr)
            sys.exit(1)
        except FileNotFoundError:
            print(f"✗ Error: Schema file not found at {schema_path}", file=sys.stderr)
            sys.exit(1)

        # Validate MAID semantics (methodology compliance)
        try:
            validate_manifest_semantics(manifest_data)
        except ManifestSemanticError as e:
            print("✗ Error: Manifest semantic validation failed", file=sys.stderr)
            print(f"\n{e}", file=sys.stderr)
            sys.exit(1)

        # Validate supersession legitimacy (prevent abuse)
        try:
            manifests_dir = manifest_path_obj.parent
            validate_supersession(manifest_data, manifests_dir, manifest_path_obj)
        except ManifestSemanticError as e:
            print("✗ Error: Supersession validation failed", file=sys.stderr)
            print(f"\n{e}", file=sys.stderr)
            sys.exit(1)

        # Validate version field
        from maid_runner.utils import validate_manifest_version

        try:
            validate_manifest_version(manifest_data, manifest_path_obj.name)
        except ValueError as e:
            print(f"✗ Error: {e}", file=sys.stderr)
            sys.exit(1)

        # Early exit for schema-only validation mode
        # Schema mode validates structure only, without checking files
        if validation_mode == "schema":
            if not quiet:
                print("✓ Manifest validation PASSED (schema-only mode)")
                print("  Schema, semantic, and version validation completed")
            return

        # Check if this is a system manifest - they skip behavioral/implementation validation
        from maid_runner.validators.manifest_validator import (
            _should_skip_behavioral_validation,
            _should_skip_implementation_validation,
        )

        skip_behavioral = _should_skip_behavioral_validation(manifest_data)
        skip_implementation = _should_skip_implementation_validation(manifest_data)

        # System manifests only undergo schema validation
        if skip_behavioral and skip_implementation:
            if not quiet:
                print("✓ System manifest validation PASSED (schema validation only)")
                print(
                    "  System manifests aggregate multiple files; no single implementation to validate"
                )
            return

        # Snapshot manifests must have comprehensive validationCommands
        # Check this early, before file validation
        # Support both legacy (validationCommand) and enhanced (validationCommands) formats
        validation_command = manifest_data.get("validationCommand", [])
        validation_commands = manifest_data.get("validationCommands", [])
        has_validation = bool(validation_command or validation_commands)

        if manifest_data.get("taskType") == "snapshot" and not has_validation:
            print(
                f"✗ Error: Snapshot manifest {manifest_path_obj.name} must have a comprehensive "
                f"validationCommand or validationCommands that tests all artifacts. Snapshot manifests document the "
                f"complete current state and must validate all artifacts."
            )
            sys.exit(1)

        # Get the file to validate from the manifest
        file_path = manifest_data.get("expectedArtifacts", {}).get("file")
        if not file_path:
            print("✗ Error: No file specified in manifest's expectedArtifacts.file")
            sys.exit(1)

        # Normalize file path: strip redundant project directory prefix if it exists
        # This handles cases where paths might have redundant directory prefixes
        # Check if the file exists as-is first, then try without the first directory component
        if "/" in file_path and not Path(file_path).exists():
            # Try removing the first directory component if it matches the current directory name
            project_name = Path.cwd().name
            if file_path.startswith(f"{project_name}/"):
                potential_normalized = file_path[len(project_name) + 1 :]
                if Path(potential_normalized).exists():
                    file_path = potential_normalized

        # BEHAVIORAL TEST VALIDATION
        # In behavioral mode, we validate test structure, not implementation
        # Support both legacy (validationCommand) and enhanced (validationCommands) formats
        validation_commands = manifest_data.get("validationCommands", [])
        if not validation_commands:
            validation_commands = manifest_data.get("validationCommand", [])

        # Initialize test_files to empty list for use in both behavioral and implementation modes
        test_files = []

        if validation_mode == "behavioral":
            # Behavioral mode: Check test files exist and USE artifacts
            if validation_commands:
                test_files = extract_test_files_from_command(validation_commands)
                if test_files:
                    # Validate test files exist
                    missing_test_files = []
                    for test_file in test_files:
                        if not Path(test_file).exists():
                            missing_test_files.append(test_file)

                    if missing_test_files:
                        print(
                            f"✗ Error: Test file(s) not found: {', '.join(missing_test_files)}"
                        )
                        sys.exit(1)

                    if not quiet:
                        print("Running behavioral test validation...")
                    validate_behavioral_tests(
                        manifest_data,
                        test_files,
                        use_manifest_chain=use_manifest_chain,
                        quiet=quiet,
                    )
                    if not quiet:
                        print("✓ Behavioral test validation PASSED")
                else:
                    if not quiet:
                        print("⚠ Warning: No test files found in validationCommand")
            else:
                if not quiet:
                    print(
                        "⚠ Warning: No validationCommand specified for behavioral validation"
                    )
        else:
            # Implementation mode: Check implementation file exists and DEFINES artifacts
            # Special case: If status is "absent", file should NOT exist - skip existence check
            expected_artifacts = manifest_data.get("expectedArtifacts", {})
            file_status = expected_artifacts.get("status", "present")

            if file_status != "absent" and not Path(file_path).exists():
                print(f"✗ Error: Target file not found: {file_path}")
                print()
                print(
                    "⚠️  Hint: If you're validating a manifest before implementing the code (MAID Phase 2),"
                )
                print(
                    "   you should use behavioral validation to check the test structure:"
                )
                print()
                print(
                    f"   uv run maid validate {manifest_path} --validation-mode behavioral"
                )
                print()
                print("   Implementation validation requires the target file to exist.")
                sys.exit(1)

            # Also run behavioral test validation if validation commands are present
            if validation_commands:
                test_files = extract_test_files_from_command(validation_commands)
                if test_files:
                    # Check if test files exist (TDD: tests may not exist yet)
                    missing_test_files = []
                    for test_file in test_files:
                        if not Path(test_file).exists():
                            missing_test_files.append(test_file)

                    if missing_test_files:
                        print(
                            f"✗ Error: Test file(s) not found: {', '.join(missing_test_files)}"
                        )
                        sys.exit(1)

                    if not quiet:
                        print("Running behavioral test validation...")
                    validate_behavioral_tests(
                        manifest_data,
                        test_files,
                        use_manifest_chain=use_manifest_chain,
                        quiet=quiet,
                    )
                    if not quiet:
                        print("✓ Behavioral test validation PASSED")

            # IMPLEMENTATION VALIDATION
            # Only run AST validation for Python files
            # Validate using appropriate language validator (Python, TypeScript, etc.)
            # The validator factory in manifest_validator.py routes to the correct validator
            validate_with_ast(
                manifest_data,
                file_path,
                use_manifest_chain=use_manifest_chain,
                validation_mode=validation_mode,
            )

        # Success message
        if not quiet:
            print(f"✓ Validation PASSED ({validation_mode} mode)")
            if use_manifest_chain:
                # Check if this is a snapshot (snapshots skip chain merging)
                is_snapshot = manifest_data.get("taskType") == "snapshot"
                if is_snapshot:
                    print("  Snapshot manifest (chain skipped)")
                else:
                    print("  Used manifest chain for validation")

            print(f"  Manifest: {manifest_path}")
            print(f"  Target:   {file_path}")

        # FILE TRACKING ANALYSIS
        # Run file tracking analysis when using manifest chain in implementation mode
        # Skip if in batch mode (will be shown once at the end)
        if (
            use_manifest_chain
            and validation_mode == "implementation"
            and not skip_file_tracking
        ):
            try:
                # Load all manifests from manifests directory
                manifests_dir = Path("manifests")
                if manifests_dir.exists():
                    manifest_chain = []
                    for manifest_file in sorted(
                        manifests_dir.glob("task-*.manifest.json")
                    ):
                        with open(manifest_file, "r") as f:
                            manifest_data = json.load(f)
                            # Add filename to manifest data for tracking purposes
                            manifest_data["_filename"] = manifest_file.name
                            manifest_chain.append(manifest_data)

                    # Analyze file tracking
                    source_root = str(Path.cwd())
                    analysis = analyze_file_tracking(manifest_chain, source_root)

                    # Display warnings
                    _format_file_tracking_output(analysis, quiet=quiet)

            except Exception as e:
                # Don't fail validation if file tracking has issues
                if not quiet:
                    print(f"\n⚠️  File tracking analysis failed: {e}")

        # Display metadata if present (outside conditional for consistent display)
        metadata = manifest_data.get("metadata")
        if metadata:
            if metadata.get("author"):
                print(f"  Author:   {metadata['author']}")
            if metadata.get("tags"):
                tags_str = ", ".join(metadata["tags"])
                print(f"  Tags:     {tags_str}")
            if metadata.get("priority"):
                print(f"  Priority: {metadata['priority']}")

    except Exception as e:
        from maid_runner.validators.manifest_validator import AlignmentError

        if isinstance(e, AlignmentError):
            print(f"✗ Validation FAILED: {e}")
            if not quiet:
                print(f"  Manifest: {manifest_path}")
                print(f"  Mode:     {validation_mode}")
            sys.exit(1)
        else:
            # Re-raise if it's not an AlignmentError
            raise

    except json.JSONDecodeError as e:
        print(f"✗ Error: Invalid JSON in manifest file: {e}")
        sys.exit(1)

    except FileNotFoundError as e:
        print(f"✗ Error: File not found: {e}")
        sys.exit(1)

    except Exception as e:
        print(f"✗ Unexpected error: {e}")
        if not quiet:
            import traceback

            traceback.print_exc()
        sys.exit(1)


def main() -> None:
    """Main CLI entry point."""
    parser = argparse.ArgumentParser(
        description="Validate manifest against implementation or behavioral test files",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Validate single manifest (implementation mode)
  %(prog)s manifests/task-001.manifest.json

  # Validate all manifests in directory
  %(prog)s --manifest-dir manifests

  # Validate behavioral test usage
  %(prog)s manifests/task-001.manifest.json --validation-mode behavioral

  # Use manifest chain for complex validation
  %(prog)s manifests/task-001.manifest.json --use-manifest-chain

  # Validate all manifests with behavioral mode
  %(prog)s --manifest-dir manifests --validation-mode behavioral

Validation Modes:
  implementation  - Validates that code DEFINES the expected artifacts (default)
  behavioral      - Validates that tests USE/CALL the expected artifacts

File Tracking Analysis:
  When using --use-manifest-chain in implementation mode, MAID Runner automatically
  analyzes file tracking compliance across the codebase:

  🔴 UNDECLARED - Files not in any manifest (high priority)
  🟡 REGISTERED - Files tracked but incomplete compliance (medium priority)
  ✓ TRACKED     - Files with full MAID compliance

  This helps identify accountability gaps and ensures all source files are properly
  documented in manifests.

This enables MAID Phase 2 validation: manifest ↔ behavioral test alignment!
        """,
    )

    parser.add_argument(
        "manifest_path",
        nargs="?",
        help="Path to the manifest JSON file (mutually exclusive with --manifest-dir)",
    )

    parser.add_argument(
        "--validation-mode",
        choices=["implementation", "behavioral"],
        default="implementation",
        help="Validation mode: 'implementation' (default) checks definitions, 'behavioral' checks usage",
    )

    parser.add_argument(
        "--use-manifest-chain",
        action="store_true",
        help="Use manifest chain to merge all related manifests (enables file tracking analysis)",
    )

    parser.add_argument(
        "--quiet",
        "-q",
        action="store_true",
        help="Only output errors (suppress success messages)",
    )

    parser.add_argument(
        "--manifest-dir",
        help="Directory containing manifests to validate (mutually exclusive with manifest_path)",
    )

    args = parser.parse_args()

    # Check for mutual exclusivity
    if args.manifest_path and args.manifest_dir:
        parser.error(
            "Cannot specify both manifest_path and --manifest-dir. Use one or the other."
        )

    if not args.manifest_path and not args.manifest_dir:
        parser.error("Must specify either manifest_path or --manifest-dir")

    run_validation(
        args.manifest_path,
        args.validation_mode,
        args.use_manifest_chain,
        args.quiet,
        args.manifest_dir,
    )


if __name__ == "__main__":
    main()
