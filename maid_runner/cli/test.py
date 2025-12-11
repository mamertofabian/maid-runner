#!/usr/bin/env python3
"""Command-line interface for running MAID validation commands.

This script discovers all manifests, filters out superseded ones, and executes
their validation commands, providing aggregate results.
"""

import argparse
import json
import subprocess
import sys
import time
from pathlib import Path
from typing import List, Optional

from maid_runner.cli._batch_test_runner import (
    collect_test_files_by_runner,
    run_batch_tests,
)
from maid_runner.utils import (
    find_project_root,
    get_superseded_manifests,
    normalize_validation_commands,
    print_maid_not_enabled_message,
    print_no_manifests_found_message,
    validate_manifest_version,
)
from maid_runner.validators.typescript_test_runner import (
    is_typescript_command,
    normalize_typescript_command,
)

# Try to import watchdog for watch mode
try:
    from watchdog.observers import Observer
    from watchdog.events import FileSystemEventHandler

    WATCHDOG_AVAILABLE = True
except ImportError:
    WATCHDOG_AVAILABLE = False
    # Provide a dummy base class to avoid NameError during module import
    # This allows the module to be imported even when watchdog is not installed
    FileSystemEventHandler = object  # type: ignore
    Observer = None  # type: ignore


def get_watchable_files(manifest_data: dict) -> List[str]:
    """Extract and combine editableFiles, creatableFiles, and test files from a manifest.

    This function extracts files that should be monitored in watch mode:
    - editableFiles: Files being modified
    - creatableFiles: New files being created
    - Test files: Extracted from validationCommand/validationCommands

    Including test files enables real-world TDD workflows where tests themselves
    need corrections during implementation (typos, wrong assertions, edge cases).

    Args:
        manifest_data: Dictionary containing manifest data

    Returns:
        List of file paths that should be watched for changes
    """
    from maid_runner.cli.validate import extract_test_files_from_command
    from maid_runner.utils import normalize_validation_commands

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
    seen = set()
    unique_files = []
    for f in watchable_files:
        if f not in seen:
            seen.add(f)
            unique_files.append(f)

    return unique_files


def build_file_to_manifests_map(
    manifests_dir: Path, active_manifests: List[Path]
) -> dict:
    """Build a mapping from file paths to lists of manifests that reference them.

    Args:
        manifests_dir: Path to the manifests directory
        active_manifests: List of paths to active (non-superseded) manifests

    Returns:
        Dictionary mapping absolute file paths to lists of manifest paths that reference them
    """
    file_to_manifests = {}
    project_root = find_project_root(manifests_dir)

    for manifest_path in active_manifests:
        try:
            with open(manifest_path, "r") as f:
                manifest_data = json.load(f)

            # Get all watchable files from this manifest
            watchable_files = get_watchable_files(manifest_data)

            # Add this manifest to the mapping for each watchable file
            # Use resolved absolute paths as keys for reliable matching
            for file_path in watchable_files:
                absolute_path = (project_root / file_path).resolve()
                if absolute_path not in file_to_manifests:
                    file_to_manifests[absolute_path] = []
                file_to_manifests[absolute_path].append(manifest_path)

        except (json.JSONDecodeError, IOError):
            # Skip invalid manifests
            continue

    return file_to_manifests


class _FileChangeHandler(FileSystemEventHandler):
    """Handle file change events for watch mode."""

    def __init__(
        self,
        manifest_path: Path,
        manifest_data: dict,
        timeout: int,
        verbose: bool,
        project_root: Path,
    ):
        """Initialize file change handler for single-manifest watch mode.

        Args:
            manifest_path: Path to the manifest file
            manifest_data: Parsed manifest dictionary
            timeout: Command timeout in seconds
            verbose: Enable detailed output
            project_root: Root directory for executing commands
        """
        self.manifest_path = manifest_path
        self.manifest_data = manifest_data
        self.timeout = timeout
        self.verbose = verbose
        self.project_root = project_root
        self.last_run = 0
        self.debounce_seconds = 2

        # Cache watchable files as absolute paths for efficient comparison
        watchable_files = get_watchable_files(manifest_data)
        self.watchable_paths = {(project_root / f).resolve() for f in watchable_files}

    def on_modified(self, event):
        """Run validation commands when watched files change."""
        if event.is_directory:
            return

        # Check if the modified file is in our watchable files using absolute path comparison
        modified_path = Path(event.src_path).resolve()

        if modified_path in self.watchable_paths:
            # Debounce to avoid multiple rapid triggers
            current_time = time.time()
            if current_time - self.last_run > self.debounce_seconds:
                self.last_run = current_time

                # Get relative path for display
                try:
                    display_path = modified_path.relative_to(self.project_root)
                except ValueError:
                    display_path = modified_path

                print(f"\n🔔 Detected change in {display_path}", flush=True)
                execute_validation_commands(
                    manifest_path=self.manifest_path,
                    manifest_data=self.manifest_data,
                    timeout=self.timeout,
                    verbose=self.verbose,
                    project_root=self.project_root,
                )


class _MultiManifestFileChangeHandler(FileSystemEventHandler):
    """Handle file change events for multi-manifest watch mode."""

    def __init__(
        self,
        file_to_manifests: dict,
        timeout: int,
        verbose: bool,
        quiet: bool,
        project_root: Path,
        manifests_dir: Optional[Path] = None,
        observer: Optional["Observer"] = None,
    ):
        """Initialize file change handler for multi-manifest watch mode.

        Args:
            file_to_manifests: Mapping from absolute file paths to lists of manifest paths
            timeout: Command timeout in seconds
            verbose: Enable detailed output
            quiet: Suppress non-essential output
            project_root: Root directory for executing commands
            manifests_dir: Path to manifests directory for dynamic discovery
            observer: Reference to the observer for dynamic scheduling
        """
        self.file_to_manifests = file_to_manifests
        self.timeout = timeout
        self.verbose = verbose
        self.quiet = quiet
        self.project_root = project_root
        self.manifests_dir = manifests_dir
        self.observer = observer
        self.last_run = 0
        self.debounce_seconds = 2
        # Track watched directories to avoid duplicates
        self._watched_dirs: set = set()
        # Track known manifests to detect new ones
        self._known_manifests: set = set()

    def on_modified(self, event):
        """Run validation commands for affected manifests when watched files change."""
        if event.is_directory:
            return

        # Debounce to avoid multiple rapid triggers
        current_time = time.time()
        if current_time - self.last_run <= self.debounce_seconds:
            return

        # Check if the modified file is in our file-to-manifests mapping using absolute path
        modified_path = Path(event.src_path).resolve()

        # Find which manifests reference this file
        affected_manifests = self.file_to_manifests.get(modified_path)

        if affected_manifests:
            self.last_run = current_time
            # Get the relative path for display
            try:
                display_path = modified_path.relative_to(self.project_root)
            except ValueError:
                display_path = modified_path

            print(f"\n🔔 Detected change in {display_path}", flush=True)

            # Run validation for each affected manifest
            for manifest_path in affected_manifests:
                try:
                    with open(manifest_path, "r") as f:
                        manifest_data = json.load(f)

                    if not self.quiet:
                        print(
                            f"\n📋 Running validation for {manifest_path.name}",
                            flush=True,
                        )

                    execute_validation_commands(
                        manifest_path=manifest_path,
                        manifest_data=manifest_data,
                        timeout=self.timeout,
                        verbose=self.verbose,
                        project_root=self.project_root,
                    )

                except (json.JSONDecodeError, IOError) as e:
                    if not self.quiet:
                        print(f"⚠️  Error loading {manifest_path.name}: {e}", flush=True)

    def on_created(self, event) -> None:
        """Handle file creation events for dynamic manifest discovery.

        Triggers refresh_file_mappings when a new manifest file is created,
        or treats new implementation/test files like modifications.

        Args:
            event: Filesystem event containing information about the created file
        """
        # Ignore directory events
        if event.is_directory:
            return

        src_path = str(event.src_path)

        # For manifest files, refresh mappings and run validation
        if src_path.endswith(".manifest.json"):
            if self.manifests_dir is not None:
                if not self.quiet:
                    print(
                        f"\n🔄 New manifest detected: {Path(src_path).name}", flush=True
                    )
                self.refresh_file_mappings(self.manifests_dir)
            return

        # For non-manifest files, treat as modified (editors often create new files)
        # This handles the case where a new test/implementation file is created
        # and we want to run validation if it's now tracked by a manifest
        self.on_modified(event)

    def on_deleted(self, event) -> None:
        """Handle file deletion events.

        When a manifest file is deleted, refresh mappings to remove it.
        For regular files, no action needed (validation will fail naturally
        if test tries to run on deleted file).

        Args:
            event: Filesystem event containing information about the deleted file
        """
        # Ignore directory events
        if event.is_directory:
            return

        src_path = str(event.src_path)

        # For manifest files, refresh mappings to remove the deleted manifest
        if src_path.endswith(".manifest.json"):
            if self.manifests_dir is not None:
                if not self.quiet:
                    print(f"\n🗑️  Manifest deleted: {Path(src_path).name}", flush=True)
                self.refresh_file_mappings(self.manifests_dir)

    def on_moved(self, event) -> None:
        """Handle file move/rename events for atomic write detection.

        Many editors and tools (including Claude Code) use atomic writes:
        write to temp file, then rename to final location. This triggers
        on_moved instead of on_modified/on_created.

        Args:
            event: Filesystem event with src_path (old) and dest_path (new)
        """
        # Ignore directory events
        if event.is_directory:
            return

        # Use the destination path (the final file location)
        dest_path = str(event.dest_path)

        # For manifest files, refresh mappings and run validation
        if dest_path.endswith(".manifest.json"):
            if self.manifests_dir is not None:
                if not self.quiet:
                    print(
                        f"\n🔄 New manifest detected: {Path(dest_path).name}",
                        flush=True,
                    )
                self.refresh_file_mappings(self.manifests_dir)
            return

        # For non-manifest files, create a fake event for on_modified
        # We need to handle this because atomic writes don't trigger on_modified
        class _FakeEvent:
            def __init__(self, path, is_dir=False):
                self.src_path = path
                self.is_directory = is_dir

        self.on_modified(_FakeEvent(dest_path))

    def refresh_file_mappings(self, manifests_dir: Path) -> None:
        """Rebuild file-to-manifests mapping from manifests directory.

        Discovers all manifest files, rebuilds the mapping, schedules
        new directories with the observer, and runs validation for
        newly discovered manifests.

        Args:
            manifests_dir: Path to the manifests directory
        """
        # Get all manifest files
        manifest_files = sorted(manifests_dir.glob("task-*.manifest.json"))

        # Get superseded manifests and filter them out
        superseded = get_superseded_manifests(manifests_dir)
        active_manifests = [m for m in manifest_files if m not in superseded]

        # Detect newly added manifests
        current_manifest_set = set(active_manifests)
        new_manifests = current_manifest_set - self._known_manifests
        self._known_manifests = current_manifest_set

        # Rebuild file-to-manifests mapping
        new_mapping = build_file_to_manifests_map(manifests_dir, active_manifests)
        self.file_to_manifests.clear()
        self.file_to_manifests.update(new_mapping)

        # Schedule new directories with the observer
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
                        # Directory might already be watched or inaccessible
                        pass

        # Run validation for newly discovered manifests
        for manifest_path in sorted(new_manifests):
            try:
                with open(manifest_path, "r") as f:
                    manifest_data = json.load(f)

                if not self.quiet:
                    print(
                        f"\n📋 Running validation for new manifest: {manifest_path.name}",
                        flush=True,
                    )

                execute_validation_commands(
                    manifest_path=manifest_path,
                    manifest_data=manifest_data,
                    timeout=self.timeout,
                    verbose=self.verbose,
                    project_root=self.project_root,
                )

            except (json.JSONDecodeError, IOError) as e:
                if not self.quiet:
                    print(f"⚠️  Error loading {manifest_path.name}: {e}", flush=True)


def watch_manifest(
    manifest_path: Path,
    manifest_data: dict,
    timeout: int,
    verbose: bool,
    project_root: Path,
    debounce_seconds: float,
) -> None:
    """Watch manifest files and re-run validation commands on changes.

    Args:
        manifest_path: Path to the manifest file
        manifest_data: Dictionary containing manifest data
        timeout: Command timeout in seconds
        verbose: If True, show detailed output
        project_root: Project root directory where commands should be executed
        debounce_seconds: Number of seconds to wait before re-running after a change
    """
    if not WATCHDOG_AVAILABLE:
        print(
            "❌ Watchdog not available. Install with: pip install watchdog", flush=True
        )
        sys.exit(1)

    watchable_files = get_watchable_files(manifest_data)

    print("\n👁️  Watch mode enabled. Press Ctrl+C to stop.", flush=True)
    if watchable_files:
        print(f"👀 Watching files: {', '.join(watchable_files)}", flush=True)
    else:
        print(
            "⚠️  No watchable files found in manifest (editableFiles or creatableFiles)",
            flush=True,
        )
        print("   Watch mode will only run initial validation", flush=True)

    # Initial run
    print("\n📋 Running initial validation:", flush=True)
    execute_validation_commands(
        manifest_path=manifest_path,
        manifest_data=manifest_data,
        timeout=timeout,
        verbose=verbose,
        project_root=project_root,
    )

    # Set up file watching
    event_handler = _FileChangeHandler(
        manifest_path, manifest_data, timeout, verbose, project_root
    )
    # Update debounce seconds from parameter
    event_handler.debounce_seconds = debounce_seconds

    observer = Observer()

    # Watch the parent directories of watchable files
    if watchable_files:
        watched_dirs = set()
        for file_path in watchable_files:
            parent_dir = Path(file_path).parent
            if parent_dir not in watched_dirs:
                observer.schedule(event_handler, str(parent_dir), recursive=False)
                watched_dirs.add(parent_dir)

    try:
        observer.start()
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        observer.stop()
        print("\n👋 Stopping watch mode", flush=True)
    observer.join()


def watch_all_manifests(
    manifests_dir: Path,
    active_manifests: List[Path],
    timeout: int,
    verbose: bool,
    quiet: bool,
    project_root: Path,
    debounce_seconds: float,
) -> None:
    """Watch all active manifests and run validation commands when files change.

    Args:
        manifests_dir: Path to the manifests directory
        active_manifests: List of paths to active (non-superseded) manifests
        timeout: Command timeout in seconds
        verbose: If True, show detailed output
        quiet: If True, only show summary
        project_root: Project root directory where commands should be executed
        debounce_seconds: Number of seconds to wait before re-running after a change
    """
    if not WATCHDOG_AVAILABLE:
        print(
            "❌ Watchdog not available. Install with: pip install watchdog", flush=True
        )
        sys.exit(1)

    # Build file-to-manifests mapping
    file_to_manifests = build_file_to_manifests_map(manifests_dir, active_manifests)

    # Get all unique watchable files
    all_watchable_files = set(file_to_manifests.keys())

    print("\n👁️  Multi-manifest watch mode enabled. Press Ctrl+C to stop.", flush=True)
    if all_watchable_files:
        print(
            f"👀 Watching {len(all_watchable_files)} file(s) across {len(active_manifests)} manifest(s)",
            flush=True,
        )
    else:
        print("⚠️  No watchable files found in any manifest", flush=True)
        print("   Watch mode will only run initial validation", flush=True)

    # Run initial validation for all manifests
    print("\n📋 Running initial validation for all manifests:", flush=True)
    for manifest_path in active_manifests:
        try:
            with open(manifest_path, "r") as f:
                manifest_data = json.load(f)

            if not quiet:
                print(f"\n📋 {manifest_path.name}", flush=True)

            execute_validation_commands(
                manifest_path=manifest_path,
                manifest_data=manifest_data,
                timeout=timeout,
                verbose=verbose,
                project_root=project_root,
            )

        except (json.JSONDecodeError, IOError) as e:
            if not quiet:
                print(f"⚠️  Error loading {manifest_path.name}: {e}", flush=True)

    observer = Observer()

    # Set up file watching with dynamic discovery support
    event_handler = _MultiManifestFileChangeHandler(
        file_to_manifests=file_to_manifests,
        timeout=timeout,
        verbose=verbose,
        quiet=quiet,
        project_root=project_root,
        manifests_dir=manifests_dir,
        observer=observer,
    )
    # Update debounce seconds from parameter
    event_handler.debounce_seconds = debounce_seconds

    # Watch the parent directories of all watchable files
    watched_dirs = set()
    if all_watchable_files:
        for file_path in all_watchable_files:
            parent_dir = Path(file_path).parent
            if parent_dir not in watched_dirs:
                observer.schedule(event_handler, str(parent_dir), recursive=False)
                watched_dirs.add(parent_dir)

    # Watch the manifests directory for dynamic manifest discovery
    if manifests_dir not in watched_dirs:
        observer.schedule(event_handler, str(manifests_dir), recursive=False)
        watched_dirs.add(manifests_dir)

    # Initialize handler's watched_dirs set and known manifests
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


def execute_validation_commands(
    manifest_path: Path,
    manifest_data: dict,
    timeout: int,
    verbose: bool,
    project_root: Path,
) -> tuple:
    """Execute validation commands for a single manifest.

    Args:
        manifest_path: Path to the manifest file
        manifest_data: Dictionary containing manifest data
        timeout: Command timeout in seconds
        verbose: If True, show detailed command output
        project_root: Project root directory (parent of manifests dir) where commands should be executed

    Returns:
        tuple: (passed_count, failed_count, total_count)
    """
    validation_commands = normalize_validation_commands(manifest_data)

    if not validation_commands:
        return (0, 0, 0)

    passed = 0
    failed = 0
    total = len(validation_commands)

    # Get project directory name for path normalization
    project_name = project_root.name

    # Set up environment
    import os

    env_additions = os.environ.copy()

    # Add current project root to PYTHONPATH to ensure local imports work
    current_pythonpath = env_additions.get("PYTHONPATH", "")
    pythonpath_additions = [str(project_root)]
    if current_pythonpath:
        pythonpath_additions.append(current_pythonpath)
    env_additions["PYTHONPATH"] = ":".join(pythonpath_additions)

    # Check if we should auto-prefix pytest commands with 'uv run'
    # Only do this if project has pyproject.toml (uv project)
    pyproject_path = project_root / "pyproject.toml"
    auto_prefix_uv_run = pyproject_path.exists()

    for i, cmd in enumerate(validation_commands):
        if not cmd:
            continue

        # Normalize command paths: strip redundant project directory prefix if needed
        # This handles cases where paths might have redundant directory prefixes
        normalized_cmd = []
        for arg in cmd:
            # Only normalize if the path doesn't exist as-is and starts with project name
            if "/" in arg and arg.startswith(f"{project_name}/"):
                # Check if removing the prefix would make the path exist
                normalized_arg = arg[len(project_name) + 1 :]
                # Use normalized path if original doesn't exist but normalized does
                if not Path(arg).exists() and Path(normalized_arg).exists():
                    normalized_cmd.append(normalized_arg)
                else:
                    normalized_cmd.append(arg)
            else:
                normalized_cmd.append(arg)

        # Auto-prefix pytest commands with 'uv run' if appropriate
        # This ensures tests run in the correct environment for maid-runner itself
        # but avoids dependency resolution issues for projects with local deps
        if auto_prefix_uv_run and normalized_cmd and normalized_cmd[0] == "pytest":
            normalized_cmd = ["uv", "run"] + normalized_cmd

        # Normalize TypeScript/JavaScript commands
        if is_typescript_command(normalized_cmd):
            normalized_cmd = normalize_typescript_command(normalized_cmd, project_root)

        cmd_str = " ".join(normalized_cmd)
        print(f"  [{i+1}/{total}] {cmd_str}")

        try:
            result = subprocess.run(
                normalized_cmd,
                capture_output=True,
                text=True,
                timeout=timeout,
                cwd=project_root,
                env=env_additions,
            )

            if result.returncode == 0:
                passed += 1
                print("    ✅ PASSED")
                if verbose and result.stdout:
                    for line in result.stdout.strip().split("\n"):
                        print(f"      {line}")
            else:
                failed += 1
                print(f"    ❌ FAILED (exit code: {result.returncode})")
                if result.stderr:
                    # Print first few lines of stderr
                    stderr_lines = result.stderr.strip().split("\n")[:10]
                    for line in stderr_lines:
                        print(f"      {line}")

        except subprocess.TimeoutExpired:
            failed += 1
            print(f"    ⏰ TIMEOUT (>{timeout}s)")
        except FileNotFoundError:
            failed += 1
            print(f"    ❌ Command not found: {cmd[0]}")
        except Exception as e:
            failed += 1
            print(f"    ❌ Error: {e}")

    return (passed, failed, total)


def run_test(
    manifest_dir: str,
    fail_fast: bool,
    verbose: bool,
    quiet: bool,
    timeout: int,
    manifest_path: Optional[str] = None,
    watch: bool = False,
    watch_all: bool = False,
) -> None:
    """Run all validation commands from active manifests.

    Args:
        manifest_dir: Path to the manifests directory
        fail_fast: If True, stop on first failure
        verbose: If True, show detailed output
        quiet: If True, only show summary
        timeout: Command timeout in seconds
        manifest_path: Optional path to a single manifest to test (relative to manifest_dir or absolute)
        watch: If True, enable single-manifest watch mode (requires manifest_path)
        watch_all: If True, enable multi-manifest watch mode (watches all active manifests)

    Raises:
        SystemExit: Exits with code 0 on success, 1 on failure
    """
    # Validate watch mode requirements
    if watch and not manifest_path:
        print("❌ Watch mode requires --manifest to be specified")
        print("   Use --watch-all to watch all manifests")
        sys.exit(1)

    if watch_all and watch:
        print("❌ Cannot use both --watch and --watch-all")
        sys.exit(1)

    manifests_dir = Path(manifest_dir).resolve()
    project_root = find_project_root(manifests_dir)

    if not manifests_dir.exists():
        print_maid_not_enabled_message(str(manifest_dir))
        sys.exit(0)

    # If a specific manifest is requested, use only that one
    if manifest_path:
        specific_manifest = Path(manifest_path)
        # If path is relative, try to find it
        if not specific_manifest.is_absolute():
            # Try as-is first (handles cases like "manifests/task-XXX.manifest.json")
            if not specific_manifest.exists():
                # Try relative to manifests_dir (handles cases like "task-XXX.manifest.json")
                specific_manifest = manifests_dir / specific_manifest

        if not specific_manifest.exists():
            print(f"⚠️  Manifest file not found: {manifest_path}")
            sys.exit(1)

        active_manifests = [specific_manifest.resolve()]

        # If watch mode is enabled, load manifest and start watching
        if watch:
            try:
                with open(specific_manifest, "r") as f:
                    manifest_data = json.load(f)

                # Start watch mode with 2-second debounce
                watch_manifest(
                    specific_manifest,
                    manifest_data,
                    timeout,
                    verbose,
                    project_root,
                    debounce_seconds=2.0,
                )
            except json.JSONDecodeError as e:
                print(f"\n⚠️  {specific_manifest.name}: Invalid JSON - {e}")
                sys.exit(1)
            except Exception as e:
                print(f"\n⚠️  {specific_manifest.name}: Error - {e}")
                sys.exit(1)
            # watch_manifest will handle the loop and exit
            # If we reach here, watch was interrupted and we should exit cleanly
            sys.exit(0)
    else:
        # Default behavior: process all non-superseded manifests
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
            print(f"⏭️  Skipping {len(superseded)} superseded manifest(s)")

        # If watch_all mode is enabled, watch all manifests
        if watch_all:
            watch_all_manifests(
                manifests_dir=manifests_dir,
                active_manifests=active_manifests,
                timeout=timeout,
                verbose=verbose,
                quiet=quiet,
                project_root=project_root,
                debounce_seconds=2.0,
            )
            # watch_all_manifests will handle the loop and exit
            # If we reach here, watch was interrupted and we should exit cleanly
            sys.exit(0)

        # Try batch mode for multiple manifests
        # Group tests by runner type and batch execute
        # Skip batch mode for watch modes (already handled above)
        if len(active_manifests) > 1:
            # Collect test files grouped by runner type
            test_files_by_runner = collect_test_files_by_runner(
                manifests_dir, active_manifests
            )

            if test_files_by_runner:
                # We have test files that can be batched
                total_runners = len(test_files_by_runner)
                total_test_files = sum(
                    len(files) for files in test_files_by_runner.values()
                )

                if not quiet:
                    print(
                        f"\n🚀 Using batch mode for {len(active_manifests)} manifest(s)"
                    )
                    if total_runners > 1:
                        print(f"   📊 Found {total_runners} test runner type(s)")

                # Run batch tests for each runner type
                total_passed = 0
                total_failed = 0
                total_batches = 0

                for runner, test_files in sorted(test_files_by_runner.items()):
                    passed, failed, count = run_batch_tests(
                        runner, test_files, project_root, verbose, timeout
                    )
                    total_passed += passed
                    total_failed += failed
                    total_batches += count

                # Print summary
                if total_batches > 0:
                    print(
                        f"\n📊 Summary: {'All tests passed' if total_failed == 0 else 'Some tests failed'}"
                    )
                    print(
                        f"   🧪 Ran {total_test_files} test file(s) across {total_runners} runner(s)"
                    )
                else:
                    print("\n⚠️  No tests executed")

                # Exit with appropriate code
                if total_failed > 0:
                    sys.exit(1)
                else:
                    sys.exit(0)

            # If no test files collected, fall through to sequential mode
            elif not quiet:
                print("\n⚠️  No batchable test commands found, using sequential mode")

    total_passed = 0
    total_failed = 0
    total_commands = 0
    manifests_with_failures = 0
    manifests_fully_passed = 0

    for manifest_file in active_manifests:
        try:
            with open(manifest_file, "r") as f:
                manifest_data = json.load(f)

            # Validate version
            try:
                validate_manifest_version(manifest_data, manifest_file.name)
            except ValueError as e:
                if not quiet:
                    print(f"\n⚠️  {manifest_file.name}: {e}")
                continue

            validation_commands = normalize_validation_commands(manifest_data)
            if not validation_commands:
                continue

            if not quiet:
                print(
                    f"\n📋 {manifest_file.name}: Running {len(validation_commands)} validation command(s)"
                )

            passed, failed, total = execute_validation_commands(
                manifest_file, manifest_data, timeout, verbose, project_root
            )

            total_passed += passed
            total_failed += failed
            total_commands += total

            if failed > 0:
                manifests_with_failures += 1
                if fail_fast:
                    print("\n❌ Stopping due to failure (--fail-fast)")
                    sys.exit(1)
            else:
                manifests_fully_passed += 1

        except json.JSONDecodeError as e:
            if not quiet:
                print(f"\n⚠️  {manifest_file.name}: Invalid JSON - {e}")
            continue
        except Exception as e:
            if not quiet:
                print(f"\n⚠️  {manifest_file.name}: Error - {e}")
            continue

    # Print summary
    if total_commands > 0:
        percentage = (total_passed / total_commands * 100) if total_commands > 0 else 0
        print(
            f"\n📊 Summary: {total_passed}/{total_commands} validation commands passed ({percentage:.1f}%)"
        )
        if not quiet:
            print(f"   ✅ {manifests_fully_passed} manifest(s) fully passed")
            if manifests_with_failures > 0:
                print(f"   ❌ {manifests_with_failures} manifest(s) had failures")
    else:
        print("\n⚠️  No validation commands found in manifests")

    # Exit with appropriate code
    if total_failed > 0:
        sys.exit(1)
    else:
        sys.exit(0)


def main() -> None:
    """Main CLI entry point for maid test command."""
    parser = argparse.ArgumentParser(
        description="""Run validation commands from all non-superseded manifests.

When running multiple manifests, automatically uses batch mode to run all pytest
tests in a single invocation (10-20x faster). Falls back to sequential mode for
mixed test runners (pytest + vitest, etc.).""",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Run all validation commands (uses batch mode for speed)
  %(prog)s

  # Run validation commands for a single manifest
  %(prog)s --manifest task-021-maid-test-command.manifest.json

  # Use custom manifest directory
  %(prog)s --manifest-dir my-manifests

  # Stop on first failure
  %(prog)s --fail-fast

  # Show detailed output
  %(prog)s --verbose

  # Only show summary
  %(prog)s --quiet

Batch Mode:
  When all validation commands are pytest-compatible, batch mode automatically
  collects test files from all manifests and runs them in a single pytest
  invocation, eliminating the overhead of running N separate pytest processes.

  For projects with mixed test runners (pytest + vitest/jest), falls back to
  sequential mode. Single-manifest mode (--manifest) and watch modes skip
  batch optimization.
        """,
    )

    parser.add_argument(
        "--manifest",
        "-m",
        help="Run validation commands for a single manifest (filename relative to manifest-dir or absolute path)",
    )

    parser.add_argument(
        "--manifest-dir",
        default="manifests",
        help="Directory containing manifests (default: manifests)",
    )

    parser.add_argument(
        "--fail-fast",
        action="store_true",
        help="Stop execution on first failure",
    )

    parser.add_argument(
        "--verbose",
        "-v",
        action="store_true",
        help="Show detailed command output",
    )

    parser.add_argument(
        "--quiet",
        "-q",
        action="store_true",
        help="Only show summary (suppress per-manifest output)",
    )

    parser.add_argument(
        "--timeout",
        type=int,
        default=300,
        help="Command timeout in seconds (default: 300)",
    )

    args = parser.parse_args()

    run_test(
        manifest_dir=args.manifest_dir,
        fail_fast=args.fail_fast,
        verbose=args.verbose,
        quiet=args.quiet,
        timeout=args.timeout,
        manifest_path=args.manifest,
    )


if __name__ == "__main__":
    main()
