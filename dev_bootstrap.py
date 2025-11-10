#!/usr/bin/env python3
"""
Bootstrap Development Script for MAID Workflow
Temporary solution for development until full MAID Runner is complete.

Usage:
    python dev_bootstrap.py manifests/task-005-type-validation.manifest.json --watch
    python dev_bootstrap.py manifests/task-005-type-validation.manifest.json --once
"""

import json
import subprocess
import sys
import time
from pathlib import Path
from typing import Dict
import argparse

try:
    from watchdog.observers import Observer
    from watchdog.events import FileSystemEventHandler

    WATCHDOG_AVAILABLE = True
except ImportError:
    WATCHDOG_AVAILABLE = False

    # Define dummy class to avoid NameError
    class FileSystemEventHandler:
        pass


class MAIDDevRunner:
    """Minimal MAID runner for bootstrapping development."""

    def __init__(self, manifest_path: str):
        self.manifest_path = Path(manifest_path)
        self.manifest_data = self._load_manifest()
        self.editable_files = self.manifest_data.get("editableFiles", [])
        # Support both validationCommand (legacy) and validationCommands (enhanced)
        self.validation_commands = self.manifest_data.get("validationCommands", [])
        self.validation_command = self.manifest_data.get("validationCommand", [])

    def _load_manifest(self) -> Dict:
        """Load and parse manifest JSON."""
        with open(self.manifest_path, "r") as f:
            manifest_data = json.load(f)

        # Validate version field
        from maid_runner.utils import validate_manifest_version

        try:
            validate_manifest_version(manifest_data, self.manifest_path.name)
        except ValueError as e:
            print(f"✗ Error: {e}", file=sys.stderr)
            sys.exit(1)

        return manifest_data

    def run_validation(self) -> bool:
        """Run the validation command(s) and return success status.

        Supports multiple validation command formats:
        - Enhanced: validationCommands (array of command arrays)
        - Legacy: validationCommand (single array or multiple string commands)

        Timeout: 300 seconds (5 minutes) per command to allow for comprehensive test suites.
        """
        from maid_runner.utils import normalize_validation_commands

        commands_to_run = normalize_validation_commands(self.manifest_data)
        if not commands_to_run:
            print("❌ No validation command in manifest")
            return False

        all_passed = True
        for i, cmd in enumerate(commands_to_run):
            if i > 0:
                print()  # Add spacing between commands

            print(f"\n{'='*60}")
            print(
                f"🔄 Running validation command {i+1}/{len(commands_to_run)}: {' '.join(cmd)}"
            )
            print(f"{'='*60}")

            try:
                # Timeout: 300 seconds (5 minutes) to allow for comprehensive test suites
                result = subprocess.run(
                    cmd, capture_output=True, text=True, timeout=300
                )

                # Print output
                if result.stdout:
                    print(result.stdout)
                if result.stderr:
                    print(result.stderr, file=sys.stderr)

                if result.returncode == 0:
                    print(f"✅ Command {i+1} PASSED!")
                else:
                    print(f"❌ Command {i+1} FAILED (exit code: {result.returncode})")
                    all_passed = False

            except subprocess.TimeoutExpired:
                print(f"❌ Command {i+1} TIMEOUT (300s)")
                all_passed = False
            except Exception as e:
                print(f"❌ Error running command {i+1}: {e}")
                all_passed = False

        if all_passed:
            print(f"\n✅ All {len(commands_to_run)} validation command(s) PASSED!")
        else:
            print("\n❌ Some validation command(s) FAILED")

        return all_passed

    def run_structural_validation(self) -> bool:
        """Run manifest structural validation."""
        print("\n🔍 Running structural validation...")
        try:
            result = subprocess.run(
                [
                    "maid",
                    "validate",
                    str(self.manifest_path),
                    "--quiet",
                    "--use-manifest-chain",
                ],
                capture_output=True,
                text=True,
                timeout=10,
            )

            if result.returncode == 0:
                print("✅ Structural validation passed")
                return True
            else:
                print(
                    f"❌ Structural validation failed:\n{result.stdout}{result.stderr}"
                )
                return False
        except Exception as e:
            print(f"⚠️  Could not run structural validation: {e}")
            return True  # Don't block development

    def display_status(self):
        """Display current manifest information."""
        print(f"\n📋 Manifest: {self.manifest_path.name}")
        print(f"📝 Goal: {self.manifest_data.get('goal', 'No goal specified')[:80]}...")
        print(f"📁 Editable files: {', '.join(self.editable_files)}")
        if self.validation_commands:
            print(f"🧪 Validation commands: {len(self.validation_commands)} command(s)")
        elif self.validation_command:
            print(f"🧪 Validation: {' '.join(self.validation_command[:3])}...")


class FileChangeHandler(FileSystemEventHandler):
    """Handle file change events for watch mode."""

    def __init__(self, runner: MAIDDevRunner):
        self.runner = runner
        self.last_run = 0
        self.debounce_seconds = 2

    def on_modified(self, event):
        """Run tests when editable files change."""
        if event.is_directory:
            return

        # Check if the modified file is in our editable files
        modified_path = Path(event.src_path)
        for editable_file in self.runner.editable_files:
            if str(modified_path).endswith(editable_file):
                # Debounce to avoid multiple rapid triggers
                current_time = time.time()
                if current_time - self.last_run > self.debounce_seconds:
                    self.last_run = current_time
                    print(f"\n🔔 Detected change in {editable_file}")
                    self.runner.run_structural_validation()
                    self.runner.run_validation()
                break


def watch_mode(runner: MAIDDevRunner):
    """Run in watch mode - automatically run tests on file changes."""
    if not WATCHDOG_AVAILABLE:
        print("❌ Watchdog not available. Install with: pip install watchdog")
        return

    print("\n👁️  Watch mode enabled. Press Ctrl+C to stop.")
    print(f"👀 Watching files: {', '.join(runner.editable_files)}")

    # Initial run
    runner.run_structural_validation()
    runner.run_validation()

    # Set up file watching
    event_handler = FileChangeHandler(runner)
    observer = Observer()

    # Watch the parent directories of editable files
    watched_dirs = set()
    for file_path in runner.editable_files:
        parent_dir = Path(file_path).parent
        if parent_dir not in watched_dirs:
            observer.schedule(event_handler, str(parent_dir), recursive=False)
            watched_dirs.add(parent_dir)

    observer.start()

    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        observer.stop()
        print("\n👋 Stopping watch mode")
    observer.join()


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="Bootstrap MAID development runner",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )

    parser.add_argument("manifest", help="Path to manifest file")

    parser.add_argument(
        "--watch", action="store_true", help="Watch files and run tests on changes"
    )

    parser.add_argument(
        "--once", action="store_true", help="Run validation once and exit (default)"
    )

    args = parser.parse_args()

    # Create runner
    try:
        runner = MAIDDevRunner(args.manifest)
    except Exception as e:
        print(f"❌ Failed to load manifest: {e}")
        sys.exit(1)

    # Display status
    runner.display_status()

    # Run in appropriate mode
    if args.watch:
        watch_mode(runner)
    else:
        # Run once
        structural_valid = runner.run_structural_validation()
        behavioral_valid = runner.run_validation()
        success = structural_valid and behavioral_valid
        sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
