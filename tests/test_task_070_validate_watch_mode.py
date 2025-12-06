"""Behavioral tests for Task 070: maid validate watch mode

Tests the watch mode functionality for the maid validate command, including:
- _ManifestFileChangeHandler class for handling file system events
- run_dual_mode_validation() for running both behavioral and implementation validation
- execute_validation_command() for running manifest's validationCommand
- watch_manifest_validation() for single-manifest watch orchestration
- watch_all_validations() for multi-manifest watch orchestration
"""

import sys
from pathlib import Path

# Add parent directory to path to enable imports
sys.path.insert(0, str(Path(__file__).parent.parent))

import inspect
import json
from unittest.mock import MagicMock, patch

import pytest

# Import private test modules for task-070 private artifacts
from tests._test_task_070_private_helpers import (  # noqa: F401
    TestMultiManifestValidationHandler,
    TestManifestFileChangeHandler,
)


class TestManifestFileChangeHandlerClass:
    """Tests for the _ManifestFileChangeHandler class."""

    def test_manifest_file_change_handler_is_importable(self):
        """Test that _ManifestFileChangeHandler class is importable from maid_runner.cli.validate."""
        from maid_runner.cli.validate import _ManifestFileChangeHandler

        assert _ManifestFileChangeHandler is not None
        assert inspect.isclass(_ManifestFileChangeHandler)

    def test_manifest_file_change_handler_has_on_modified_method(self):
        """Test that _ManifestFileChangeHandler has on_modified method with correct signature."""
        from maid_runner.cli.validate import _ManifestFileChangeHandler

        assert hasattr(_ManifestFileChangeHandler, "on_modified")
        assert callable(getattr(_ManifestFileChangeHandler, "on_modified"))

        sig = inspect.signature(_ManifestFileChangeHandler.on_modified)
        params = list(sig.parameters.keys())
        assert "self" in params
        assert "event" in params

    def test_manifest_file_change_handler_has_on_created_method(self):
        """Test that _ManifestFileChangeHandler has on_created method with correct signature."""
        from maid_runner.cli.validate import _ManifestFileChangeHandler

        assert hasattr(_ManifestFileChangeHandler, "on_created")
        assert callable(getattr(_ManifestFileChangeHandler, "on_created"))

        sig = inspect.signature(_ManifestFileChangeHandler.on_created)
        params = list(sig.parameters.keys())
        assert "self" in params
        assert "event" in params

    def test_manifest_file_change_handler_has_on_moved_method(self):
        """Test that _ManifestFileChangeHandler has on_moved method with correct signature."""
        from maid_runner.cli.validate import _ManifestFileChangeHandler

        assert hasattr(_ManifestFileChangeHandler, "on_moved")
        assert callable(getattr(_ManifestFileChangeHandler, "on_moved"))

        sig = inspect.signature(_ManifestFileChangeHandler.on_moved)
        params = list(sig.parameters.keys())
        assert "self" in params
        assert "event" in params

    def test_on_modified_triggers_validation_on_manifest_change(self, tmp_path: Path):
        """Test that on_modified triggers validation when manifest file changes."""
        from maid_runner.cli.validate import _ManifestFileChangeHandler

        # Create a test manifest file
        manifest_path = tmp_path / "test.manifest.json"
        manifest_path.write_text('{"goal": "test"}')

        # Create handler instance
        handler = _ManifestFileChangeHandler(
            manifest_path=manifest_path,
            use_manifest_chain=False,
            quiet=True,
            skip_tests=True,
            timeout=300,
            verbose=False,
            project_root=tmp_path,
        )

        # Mock the validation function to track calls
        with patch(
            "maid_runner.cli.validate.run_dual_mode_validation"
        ) as mock_validate:
            mock_validate.return_value = {
                "schema": True,
                "behavioral": True,
                "implementation": True,
                "tests": None,
            }

            # Create a fake event for the manifest file
            fake_event = MagicMock()
            fake_event.is_directory = False
            fake_event.src_path = str(manifest_path)

            # Call on_modified
            handler.on_modified(fake_event)

            # Should have triggered validation
            assert mock_validate.called

    def test_on_modified_ignores_directory_events(self, tmp_path: Path):
        """Test that on_modified ignores directory events."""
        from maid_runner.cli.validate import _ManifestFileChangeHandler

        manifest_path = tmp_path / "test.manifest.json"
        manifest_path.write_text('{"goal": "test"}')

        handler = _ManifestFileChangeHandler(
            manifest_path=manifest_path,
            use_manifest_chain=False,
            quiet=True,
            skip_tests=True,
            timeout=300,
            verbose=False,
            project_root=tmp_path,
        )

        with patch(
            "maid_runner.cli.validate.run_dual_mode_validation"
        ) as mock_validate:
            fake_event = MagicMock()
            fake_event.is_directory = True
            fake_event.src_path = str(tmp_path)

            handler.on_modified(fake_event)

            # Should NOT have triggered validation for directory events
            assert not mock_validate.called

    def test_on_moved_handles_atomic_writes(self, tmp_path: Path):
        """Test that on_moved handles atomic file writes (temp file rename)."""
        from maid_runner.cli.validate import _ManifestFileChangeHandler

        manifest_path = tmp_path / "test.manifest.json"
        manifest_path.write_text('{"goal": "test"}')

        handler = _ManifestFileChangeHandler(
            manifest_path=manifest_path,
            use_manifest_chain=False,
            quiet=True,
            skip_tests=True,
            timeout=300,
            verbose=False,
            project_root=tmp_path,
        )

        with patch(
            "maid_runner.cli.validate.run_dual_mode_validation"
        ) as mock_validate:
            mock_validate.return_value = {
                "schema": True,
                "behavioral": True,
                "implementation": True,
                "tests": None,
            }

            # Create a fake move event (temp file -> manifest file)
            fake_event = MagicMock()
            fake_event.is_directory = False
            fake_event.src_path = str(tmp_path / "temp_file.tmp")
            fake_event.dest_path = str(manifest_path)

            handler.on_moved(fake_event)

            # Should have triggered validation for the destination file
            assert mock_validate.called


class TestGetWatchableFilesForManifest:
    """Tests for the get_watchable_files_for_manifest function."""

    def test_get_watchable_files_for_manifest_is_importable(self):
        """Test that get_watchable_files_for_manifest is importable."""
        from maid_runner.cli.validate import get_watchable_files_for_manifest

        assert callable(get_watchable_files_for_manifest)

    def test_get_watchable_files_for_manifest_has_correct_signature(self):
        """Test that get_watchable_files_for_manifest has correct signature."""
        from maid_runner.cli.validate import get_watchable_files_for_manifest

        sig = inspect.signature(get_watchable_files_for_manifest)
        params = list(sig.parameters.keys())
        assert "manifest_data" in params

    def test_get_watchable_files_for_manifest_returns_list(self):
        """Test that get_watchable_files_for_manifest returns a list."""
        from maid_runner.cli.validate import get_watchable_files_for_manifest

        result = get_watchable_files_for_manifest({})
        assert isinstance(result, list)

    def test_get_watchable_files_for_manifest_includes_editable_files(self):
        """Test that get_watchable_files_for_manifest includes editableFiles."""
        from maid_runner.cli.validate import get_watchable_files_for_manifest

        manifest_data = {"editableFiles": ["src/file1.py", "src/file2.py"]}
        result = get_watchable_files_for_manifest(manifest_data)
        assert "src/file1.py" in result
        assert "src/file2.py" in result

    def test_get_watchable_files_for_manifest_includes_creatable_files(self):
        """Test that get_watchable_files_for_manifest includes creatableFiles."""
        from maid_runner.cli.validate import get_watchable_files_for_manifest

        manifest_data = {"creatableFiles": ["src/new_file.py"]}
        result = get_watchable_files_for_manifest(manifest_data)
        assert "src/new_file.py" in result

    def test_get_watchable_files_for_manifest_includes_test_files(self):
        """Test that get_watchable_files_for_manifest includes test files from validationCommand."""
        from maid_runner.cli.validate import get_watchable_files_for_manifest

        manifest_data = {"validationCommand": ["pytest", "tests/test_file.py", "-v"]}
        result = get_watchable_files_for_manifest(manifest_data)
        assert "tests/test_file.py" in result

    def test_get_watchable_files_for_manifest_removes_duplicates(self):
        """Test that get_watchable_files_for_manifest removes duplicate files."""
        from maid_runner.cli.validate import get_watchable_files_for_manifest

        manifest_data = {
            "editableFiles": ["src/file.py"],
            "creatableFiles": ["src/file.py"],  # Duplicate
        }
        result = get_watchable_files_for_manifest(manifest_data)
        assert result.count("src/file.py") == 1


class TestBuildFileToManifestsMapForValidation:
    """Tests for the build_file_to_manifests_map_for_validation function."""

    def test_build_file_to_manifests_map_for_validation_is_importable(self):
        """Test that build_file_to_manifests_map_for_validation is importable."""
        from maid_runner.cli.validate import build_file_to_manifests_map_for_validation

        assert callable(build_file_to_manifests_map_for_validation)

    def test_build_file_to_manifests_map_for_validation_has_correct_signature(self):
        """Test that build_file_to_manifests_map_for_validation has correct signature."""
        from maid_runner.cli.validate import build_file_to_manifests_map_for_validation

        sig = inspect.signature(build_file_to_manifests_map_for_validation)
        params = list(sig.parameters.keys())
        assert "manifests_dir" in params
        assert "active_manifests" in params

    def test_build_file_to_manifests_map_for_validation_returns_dict(
        self, tmp_path: Path
    ):
        """Test that build_file_to_manifests_map_for_validation returns a dictionary."""
        from maid_runner.cli.validate import build_file_to_manifests_map_for_validation

        manifests_dir = tmp_path / "manifests"
        manifests_dir.mkdir()

        result = build_file_to_manifests_map_for_validation(manifests_dir, [])
        assert isinstance(result, dict)


class TestRunDualModeValidation:
    """Tests for the run_dual_mode_validation function."""

    def test_run_dual_mode_validation_is_importable(self):
        """Test that run_dual_mode_validation is importable from maid_runner.cli.validate."""
        from maid_runner.cli.validate import run_dual_mode_validation

        assert callable(run_dual_mode_validation)

    def test_run_dual_mode_validation_has_correct_signature(self):
        """Test that run_dual_mode_validation has the correct function signature."""
        from maid_runner.cli.validate import run_dual_mode_validation
        from typing import Dict, Optional

        sig = inspect.signature(run_dual_mode_validation)

        # Check required parameters
        assert "manifest_path" in sig.parameters
        assert "use_manifest_chain" in sig.parameters
        assert "quiet" in sig.parameters

        # Check types
        assert sig.parameters["manifest_path"].annotation == Path
        assert sig.parameters["use_manifest_chain"].annotation is bool
        assert sig.parameters["quiet"].annotation is bool

        # Check return type - now returns Dict[str, Optional[bool]]
        assert sig.return_annotation == Dict[str, Optional[bool]]

    def test_run_dual_mode_validation_returns_true_on_success(self, tmp_path: Path):
        """Test that run_dual_mode_validation returns dict with True values when validation succeeds."""
        from maid_runner.cli.validate import run_dual_mode_validation

        # Create a valid manifest
        manifest_path = tmp_path / "manifests" / "task-001.manifest.json"
        manifest_path.parent.mkdir(parents=True)

        # Create the target file that the manifest references
        target_file = tmp_path / "src" / "example.py"
        target_file.parent.mkdir(parents=True)
        target_file.write_text(
            """
def example_function():
    pass
"""
        )

        manifest_data = {
            "version": "1",
            "goal": "Test dual mode validation",
            "taskType": "edit",
            "editableFiles": ["src/example.py"],
            "expectedArtifacts": {
                "file": "src/example.py",
                "contains": [{"type": "function", "name": "example_function"}],
            },
        }
        manifest_path.write_text(json.dumps(manifest_data))

        # Mock run_validation and validate_schema to succeed
        with patch("maid_runner.cli.validate.run_validation") as mock_run:
            with patch("maid_runner.cli.validate.validate_schema"):
                # Don't raise SystemExit - just return normally
                mock_run.return_value = None

                import os

                original_cwd = os.getcwd()
                try:
                    os.chdir(tmp_path)
                    result = run_dual_mode_validation(
                        manifest_path=manifest_path,
                        use_manifest_chain=False,
                        quiet=True,
                    )

                    # Should return dict with all True values for schema, behavioral, implementation
                    assert isinstance(result, dict)
                    assert result["schema"] is True
                    assert result["behavioral"] is True
                    assert result["implementation"] is True
                    assert result["tests"] is None  # Tests not run by this function
                finally:
                    os.chdir(original_cwd)

    def test_run_dual_mode_validation_returns_false_on_failure(self, tmp_path: Path):
        """Test that run_dual_mode_validation returns dict with False values when validation fails."""
        from maid_runner.cli.validate import run_dual_mode_validation

        manifest_path = tmp_path / "manifests" / "task-001.manifest.json"
        manifest_path.parent.mkdir(parents=True)

        manifest_data = {
            "version": "1",
            "goal": "Test dual mode validation",
            "taskType": "edit",
            "editableFiles": ["src/example.py"],
            "expectedArtifacts": {
                "file": "src/example.py",
                "contains": [{"type": "function", "name": "missing_function"}],
            },
        }
        manifest_path.write_text(json.dumps(manifest_data))

        # Mock run_validation to fail with SystemExit, and validate_schema to succeed
        with patch("maid_runner.cli.validate.run_validation") as mock_run:
            with patch("maid_runner.cli.validate.validate_schema"):
                mock_run.side_effect = SystemExit(1)

                import os

                original_cwd = os.getcwd()
                try:
                    os.chdir(tmp_path)
                    result = run_dual_mode_validation(
                        manifest_path=manifest_path,
                        use_manifest_chain=False,
                        quiet=True,
                    )

                    # Should return dict with at least one False value on failure
                    assert isinstance(result, dict)
                    assert result["schema"] is True  # Schema passed
                    assert result["behavioral"] is False  # Behavioral failed
                finally:
                    os.chdir(original_cwd)

    def test_run_dual_mode_validation_runs_both_modes(self, tmp_path: Path):
        """Test that run_dual_mode_validation runs both behavioral and implementation validation."""
        from maid_runner.cli.validate import run_dual_mode_validation

        manifest_path = tmp_path / "manifests" / "task-001.manifest.json"
        manifest_path.parent.mkdir(parents=True)

        manifest_data = {
            "version": "1",
            "goal": "Test dual mode",
            "taskType": "edit",
            "editableFiles": ["src/example.py"],
            "expectedArtifacts": {
                "file": "src/example.py",
                "contains": [{"type": "function", "name": "example"}],
            },
        }
        manifest_path.write_text(json.dumps(manifest_data))

        validation_modes = []

        with patch("maid_runner.cli.validate.run_validation") as mock_run:
            with patch("maid_runner.cli.validate.validate_schema"):
                # Capture which modes are called
                def capture_mode(**kwargs):
                    mode = kwargs.get("validation_mode")
                    if mode:
                        validation_modes.append(mode)

                mock_run.side_effect = capture_mode

                import os

                original_cwd = os.getcwd()
                try:
                    os.chdir(tmp_path)
                    run_dual_mode_validation(
                        manifest_path=manifest_path,
                        use_manifest_chain=False,
                        quiet=True,
                    )

                    # Should have called validation twice (behavioral and implementation)
                    assert mock_run.call_count == 2
                    assert "behavioral" in validation_modes
                    assert "implementation" in validation_modes
                finally:
                    os.chdir(original_cwd)


class TestExecuteValidationCommand:
    """Tests for the execute_validation_command function."""

    def test_execute_validation_command_is_importable(self):
        """Test that execute_validation_command is importable from maid_runner.cli.validate."""
        from maid_runner.cli.validate import execute_validation_command

        assert callable(execute_validation_command)

    def test_execute_validation_command_has_correct_signature(self):
        """Test that execute_validation_command has the correct function signature."""
        from maid_runner.cli.validate import execute_validation_command

        sig = inspect.signature(execute_validation_command)

        # Check required parameters
        assert "manifest_data" in sig.parameters
        assert "project_root" in sig.parameters
        assert "timeout" in sig.parameters
        assert "verbose" in sig.parameters

        # Check types
        assert sig.parameters["manifest_data"].annotation is dict
        assert sig.parameters["project_root"].annotation == Path
        assert sig.parameters["timeout"].annotation is int
        assert sig.parameters["verbose"].annotation is bool

        # Check return type
        assert sig.return_annotation is bool

    def test_execute_validation_command_returns_true_on_success(self, tmp_path: Path):
        """Test that execute_validation_command returns True when command succeeds."""
        from maid_runner.cli.validate import execute_validation_command

        manifest_data = {
            "validationCommand": ["echo", "success"],
        }

        result = execute_validation_command(
            manifest_data=manifest_data,
            project_root=tmp_path,
            timeout=30,
            verbose=False,
        )

        assert result is True

    def test_execute_validation_command_returns_false_on_failure(self, tmp_path: Path):
        """Test that execute_validation_command returns False when command fails."""
        from maid_runner.cli.validate import execute_validation_command

        manifest_data = {
            "validationCommand": ["false"],  # Unix command that always fails
        }

        result = execute_validation_command(
            manifest_data=manifest_data,
            project_root=tmp_path,
            timeout=30,
            verbose=False,
        )

        assert result is False

    def test_execute_validation_command_handles_missing_command(self, tmp_path: Path):
        """Test that execute_validation_command handles manifests without validationCommand."""
        from maid_runner.cli.validate import execute_validation_command

        manifest_data = {
            "goal": "No validation command",
        }

        # Should return True (no command to run = success)
        result = execute_validation_command(
            manifest_data=manifest_data,
            project_root=tmp_path,
            timeout=30,
            verbose=False,
        )

        assert result is True

    def test_execute_validation_command_respects_timeout(self, tmp_path: Path):
        """Test that execute_validation_command respects timeout parameter."""
        from maid_runner.cli.validate import execute_validation_command

        manifest_data = {
            # Command that would take 10 seconds
            "validationCommand": ["sleep", "10"],
        }

        # Use a very short timeout
        result = execute_validation_command(
            manifest_data=manifest_data,
            project_root=tmp_path,
            timeout=1,  # 1 second timeout
            verbose=False,
        )

        # Should return False due to timeout
        assert result is False


class TestWatchManifestValidation:
    """Tests for the watch_manifest_validation function."""

    def test_watch_manifest_validation_is_importable(self):
        """Test that watch_manifest_validation is importable from maid_runner.cli.validate."""
        from maid_runner.cli.validate import watch_manifest_validation

        assert callable(watch_manifest_validation)

    def test_watch_manifest_validation_has_correct_signature(self):
        """Test that watch_manifest_validation has the correct function signature."""
        from maid_runner.cli.validate import watch_manifest_validation

        sig = inspect.signature(watch_manifest_validation)

        # Check required parameters
        expected_params = [
            "manifest_path",
            "use_manifest_chain",
            "quiet",
            "skip_tests",
            "timeout",
            "verbose",
        ]

        for param in expected_params:
            assert (
                param in sig.parameters
            ), f"Parameter '{param}' missing from watch_manifest_validation()"

        # Check types
        assert sig.parameters["manifest_path"].annotation == Path
        assert sig.parameters["use_manifest_chain"].annotation is bool
        assert sig.parameters["quiet"].annotation is bool
        assert sig.parameters["skip_tests"].annotation is bool
        assert sig.parameters["timeout"].annotation is int
        assert sig.parameters["verbose"].annotation is bool

        # Check return type
        assert sig.return_annotation is None

    def test_watch_manifest_validation_runs_initial_validation(self, tmp_path: Path):
        """Test that watch_manifest_validation runs initial validation before watching."""
        from maid_runner.cli.validate import watch_manifest_validation

        manifest_path = tmp_path / "test.manifest.json"
        manifest_path.write_text(json.dumps({"goal": "test"}))

        with patch(
            "maid_runner.cli.validate.run_dual_mode_validation"
        ) as mock_validate:
            mock_validate.return_value = {
                "schema": True,
                "behavioral": True,
                "implementation": True,
                "tests": None,
            }

            with patch("maid_runner.cli.validate.Observer") as mock_observer_class:
                mock_observer = MagicMock()
                mock_observer_class.return_value = mock_observer
                mock_observer.start.side_effect = KeyboardInterrupt()

                watch_manifest_validation(
                    manifest_path=manifest_path,
                    use_manifest_chain=False,
                    quiet=True,
                    skip_tests=True,
                    timeout=300,
                    verbose=False,
                )

                # Should have run initial validation
                assert mock_validate.called

    def test_watch_manifest_validation_handles_keyboard_interrupt(self, tmp_path: Path):
        """Test that watch_manifest_validation handles Ctrl+C gracefully."""
        from maid_runner.cli.validate import watch_manifest_validation

        manifest_path = tmp_path / "test.manifest.json"
        manifest_path.write_text(json.dumps({"goal": "test"}))

        with patch(
            "maid_runner.cli.validate.run_dual_mode_validation"
        ) as mock_validate:
            mock_validate.return_value = {
                "schema": True,
                "behavioral": True,
                "implementation": True,
                "tests": None,
            }

            with patch("maid_runner.cli.validate.Observer") as mock_observer_class:
                mock_observer = MagicMock()
                mock_observer_class.return_value = mock_observer
                mock_observer.start.side_effect = KeyboardInterrupt()

                # Should not raise - should handle gracefully
                watch_manifest_validation(
                    manifest_path=manifest_path,
                    use_manifest_chain=False,
                    quiet=True,
                    skip_tests=True,
                    timeout=300,
                    verbose=False,
                )

                # Should have stopped the observer
                mock_observer.stop.assert_called_once()

    def test_watch_manifest_validation_runs_tests_by_default(self, tmp_path: Path):
        """Test that watch_manifest_validation runs validationCommand by default."""
        from maid_runner.cli.validate import watch_manifest_validation

        manifest_path = tmp_path / "test.manifest.json"
        manifest_path.write_text(
            json.dumps({"goal": "test", "validationCommand": ["echo", "test"]})
        )

        with patch(
            "maid_runner.cli.validate.run_dual_mode_validation"
        ) as mock_validate:
            mock_validate.return_value = {
                "schema": True,
                "behavioral": True,
                "implementation": True,
                "tests": None,
            }

            with patch(
                "maid_runner.cli.validate.execute_validation_command"
            ) as mock_exec:
                mock_exec.return_value = True

                with patch("maid_runner.cli.validate.Observer") as mock_observer_class:
                    mock_observer = MagicMock()
                    mock_observer_class.return_value = mock_observer
                    mock_observer.start.side_effect = KeyboardInterrupt()

                    watch_manifest_validation(
                        manifest_path=manifest_path,
                        use_manifest_chain=False,
                        quiet=True,
                        skip_tests=False,  # Run tests
                        timeout=300,
                        verbose=False,
                    )

                    # Should have run validation command
                    assert mock_exec.called

    def test_watch_manifest_validation_skips_tests_when_requested(self, tmp_path: Path):
        """Test that watch_manifest_validation skips validationCommand when skip_tests=True."""
        from maid_runner.cli.validate import watch_manifest_validation

        manifest_path = tmp_path / "test.manifest.json"
        manifest_path.write_text(
            json.dumps({"goal": "test", "validationCommand": ["echo", "test"]})
        )

        with patch(
            "maid_runner.cli.validate.run_dual_mode_validation"
        ) as mock_validate:
            mock_validate.return_value = {
                "schema": True,
                "behavioral": True,
                "implementation": True,
                "tests": None,
            }

            with patch(
                "maid_runner.cli.validate.execute_validation_command"
            ) as mock_exec:
                mock_exec.return_value = True

                with patch("maid_runner.cli.validate.Observer") as mock_observer_class:
                    mock_observer = MagicMock()
                    mock_observer_class.return_value = mock_observer
                    mock_observer.start.side_effect = KeyboardInterrupt()

                    watch_manifest_validation(
                        manifest_path=manifest_path,
                        use_manifest_chain=False,
                        quiet=True,
                        skip_tests=True,  # Skip tests
                        timeout=300,
                        verbose=False,
                    )

                    # Should NOT have run validation command
                    assert not mock_exec.called


class TestWatchAllValidations:
    """Tests for the watch_all_validations function."""

    def test_watch_all_validations_is_importable(self):
        """Test that watch_all_validations is importable from maid_runner.cli.validate."""
        from maid_runner.cli.validate import watch_all_validations

        assert callable(watch_all_validations)

    def test_watch_all_validations_has_correct_signature(self):
        """Test that watch_all_validations has the correct function signature."""
        from maid_runner.cli.validate import watch_all_validations

        sig = inspect.signature(watch_all_validations)

        # Check required parameters
        expected_params = [
            "manifests_dir",
            "use_manifest_chain",
            "quiet",
            "skip_tests",
            "timeout",
            "verbose",
        ]

        for param in expected_params:
            assert (
                param in sig.parameters
            ), f"Parameter '{param}' missing from watch_all_validations()"

        # Check types
        assert sig.parameters["manifests_dir"].annotation == Path
        assert sig.parameters["use_manifest_chain"].annotation is bool
        assert sig.parameters["quiet"].annotation is bool
        assert sig.parameters["skip_tests"].annotation is bool
        assert sig.parameters["timeout"].annotation is int
        assert sig.parameters["verbose"].annotation is bool

        # Check return type
        assert sig.return_annotation is None

    def test_watch_all_validations_discovers_manifests(self, tmp_path: Path):
        """Test that watch_all_validations discovers all manifests in directory."""
        from maid_runner.cli.validate import watch_all_validations

        manifests_dir = tmp_path / "manifests"
        manifests_dir.mkdir()

        # Create multiple manifest files
        for i in range(3):
            manifest_path = manifests_dir / f"task-{i:03d}.manifest.json"
            manifest_path.write_text(json.dumps({"goal": f"test {i}"}))

        with patch(
            "maid_runner.cli.validate.run_dual_mode_validation"
        ) as mock_validate:
            mock_validate.return_value = {
                "schema": True,
                "behavioral": True,
                "implementation": True,
                "tests": None,
            }

            with patch("maid_runner.cli.validate.Observer") as mock_observer_class:
                mock_observer = MagicMock()
                mock_observer_class.return_value = mock_observer
                mock_observer.start.side_effect = KeyboardInterrupt()

                watch_all_validations(
                    manifests_dir=manifests_dir,
                    use_manifest_chain=True,
                    quiet=True,
                    skip_tests=True,
                    timeout=300,
                    verbose=False,
                )

                # Should have run initial validation for all manifests
                # At least one call to run_dual_mode_validation or observer setup
                assert mock_observer_class.called

    def test_watch_all_validations_handles_keyboard_interrupt(self, tmp_path: Path):
        """Test that watch_all_validations handles Ctrl+C gracefully."""
        from maid_runner.cli.validate import watch_all_validations

        manifests_dir = tmp_path / "manifests"
        manifests_dir.mkdir()

        manifest_path = manifests_dir / "task-001.manifest.json"
        manifest_path.write_text(json.dumps({"goal": "test"}))

        with patch("maid_runner.cli.validate.Observer") as mock_observer_class:
            mock_observer = MagicMock()
            mock_observer_class.return_value = mock_observer
            mock_observer.start.side_effect = KeyboardInterrupt()

            # Should not raise
            watch_all_validations(
                manifests_dir=manifests_dir,
                use_manifest_chain=True,
                quiet=True,
                skip_tests=True,
                timeout=300,
                verbose=False,
            )

            # Should have stopped the observer
            mock_observer.stop.assert_called_once()

    def test_watch_all_validations_schedules_manifest_directory(self, tmp_path: Path):
        """Test that watch_all_validations watches the manifests directory."""
        from maid_runner.cli.validate import watch_all_validations

        manifests_dir = tmp_path / "manifests"
        manifests_dir.mkdir()

        manifest_path = manifests_dir / "task-001.manifest.json"
        manifest_path.write_text(json.dumps({"goal": "test"}))

        with patch("maid_runner.cli.validate.Observer") as mock_observer_class:
            mock_observer = MagicMock()
            mock_observer_class.return_value = mock_observer
            mock_observer.start.side_effect = KeyboardInterrupt()

            watch_all_validations(
                manifests_dir=manifests_dir,
                use_manifest_chain=True,
                quiet=True,
                skip_tests=True,
                timeout=300,
                verbose=False,
            )

            # Should have scheduled the manifests directory for watching
            assert mock_observer.schedule.called


class TestDebouncing:
    """Tests for debouncing behavior in watch mode."""

    def test_handler_implements_debouncing(self, tmp_path: Path):
        """Test that _ManifestFileChangeHandler implements debouncing."""
        from maid_runner.cli.validate import _ManifestFileChangeHandler

        manifest_path = tmp_path / "test.manifest.json"
        manifest_path.write_text('{"goal": "test"}')

        handler = _ManifestFileChangeHandler(
            manifest_path=manifest_path,
            use_manifest_chain=False,
            quiet=True,
            skip_tests=True,
            timeout=300,
            verbose=False,
            project_root=tmp_path,
        )

        # Handler should have debounce-related attributes
        assert hasattr(handler, "last_run") or hasattr(handler, "debounce_seconds")

    def test_rapid_changes_are_debounced(self, tmp_path: Path):
        """Test that rapid file changes are debounced to avoid multiple validations."""
        from maid_runner.cli.validate import _ManifestFileChangeHandler

        manifest_path = tmp_path / "test.manifest.json"
        manifest_path.write_text('{"goal": "test"}')

        handler = _ManifestFileChangeHandler(
            manifest_path=manifest_path,
            use_manifest_chain=False,
            quiet=True,
            skip_tests=True,
            timeout=300,
            verbose=False,
            project_root=tmp_path,
        )

        validation_count = 0

        with patch(
            "maid_runner.cli.validate.run_dual_mode_validation"
        ) as mock_validate:

            def count_calls(*_args, **_kwargs):
                nonlocal validation_count
                validation_count += 1
                return {
                    "schema": True,
                    "behavioral": True,
                    "implementation": True,
                    "tests": None,
                }

            mock_validate.side_effect = count_calls

            # Create fake event
            fake_event = MagicMock()
            fake_event.is_directory = False
            fake_event.src_path = str(manifest_path)

            # Trigger multiple rapid changes
            handler.on_modified(fake_event)
            handler.on_modified(fake_event)
            handler.on_modified(fake_event)

            # Due to debouncing, should only have one or two calls, not three
            # The exact behavior depends on implementation, but rapid calls should be grouped
            assert validation_count <= 2


class TestWatchdogAvailability:
    """Tests for handling watchdog library availability."""

    def test_watch_mode_checks_watchdog_availability(self, tmp_path: Path):
        """Test that watch mode checks if watchdog library is available."""
        from maid_runner.cli.validate import watch_manifest_validation

        manifest_path = tmp_path / "test.manifest.json"
        manifest_path.write_text(json.dumps({"goal": "test"}))

        # Mock watchdog as unavailable
        with patch("maid_runner.cli.validate.WATCHDOG_AVAILABLE", False):
            with pytest.raises(SystemExit) as exc_info:
                watch_manifest_validation(
                    manifest_path=manifest_path,
                    use_manifest_chain=False,
                    quiet=True,
                    skip_tests=True,
                    timeout=300,
                    verbose=False,
                )

            # Should exit with error code 1
            assert exc_info.value.code == 1


class TestRunValidationWithWatchParameters:
    """Tests for run_validation function with watch mode parameters."""

    def test_run_validation_has_watch_parameters(self):
        """Test that run_validation accepts watch, watch_all, timeout, verbose, skip_tests parameters."""
        from maid_runner.cli.validate import run_validation

        sig = inspect.signature(run_validation)

        # Check new watch-related parameters exist
        expected_params = [
            "watch",
            "watch_all",
            "timeout",
            "verbose",
            "skip_tests",
        ]

        for param in expected_params:
            assert (
                param in sig.parameters
            ), f"Parameter '{param}' missing from run_validation()"

        # Check types
        assert sig.parameters["watch"].annotation is bool
        assert sig.parameters["watch_all"].annotation is bool
        assert sig.parameters["timeout"].annotation is int
        assert sig.parameters["verbose"].annotation is bool
        assert sig.parameters["skip_tests"].annotation is bool

    def test_run_validation_routes_to_watch_mode(self, tmp_path: Path):
        """Test that run_validation routes to watch_manifest_validation when watch=True."""
        from maid_runner.cli.validate import run_validation

        manifest_path = tmp_path / "test.manifest.json"
        manifest_path.write_text(json.dumps({"goal": "test"}))

        with patch("maid_runner.cli.validate.watch_manifest_validation") as mock_watch:
            run_validation(
                manifest_path=str(manifest_path),
                validation_mode="implementation",
                use_manifest_chain=False,
                quiet=True,
                manifest_dir=None,
                skip_file_tracking=False,
                watch=True,
                watch_all=False,
                timeout=300,
                verbose=False,
                skip_tests=True,
            )

            # Should have called watch_manifest_validation
            assert mock_watch.called

    def test_run_validation_routes_to_watch_all_mode(self, tmp_path: Path):
        """Test that run_validation routes to watch_all_validations when watch_all=True."""
        from maid_runner.cli.validate import run_validation

        manifests_dir = tmp_path / "manifests"
        manifests_dir.mkdir()

        manifest_path = manifests_dir / "task-001.manifest.json"
        manifest_path.write_text(json.dumps({"goal": "test"}))

        with patch("maid_runner.cli.validate.watch_all_validations") as mock_watch_all:
            run_validation(
                manifest_path=None,
                validation_mode="implementation",
                use_manifest_chain=True,
                quiet=True,
                manifest_dir=str(manifests_dir),
                skip_file_tracking=False,
                watch=False,
                watch_all=True,
                timeout=300,
                verbose=False,
                skip_tests=True,
            )

            # Should have called watch_all_validations
            assert mock_watch_all.called

    def test_run_validation_watch_requires_manifest_path(self):
        """Test that run_validation with watch=True requires manifest_path."""
        from maid_runner.cli.validate import run_validation

        with pytest.raises(SystemExit) as exc_info:
            run_validation(
                manifest_path=None,  # No manifest path
                validation_mode="implementation",
                use_manifest_chain=False,
                quiet=True,
                manifest_dir=None,
                skip_file_tracking=False,
                watch=True,  # Watch mode enabled
                watch_all=False,
                timeout=300,
                verbose=False,
                skip_tests=True,
            )

        # Should exit with error code 1
        assert exc_info.value.code == 1

    def test_run_validation_watch_all_uses_default_manifest_dir(self, tmp_path: Path):
        """Test that run_validation watch_all defaults to 'manifests' directory."""
        from maid_runner.cli.validate import run_validation

        import os

        original_cwd = os.getcwd()
        try:
            os.chdir(tmp_path)

            manifests_dir = tmp_path / "manifests"
            manifests_dir.mkdir()
            manifest_path = manifests_dir / "task-001.manifest.json"
            manifest_path.write_text(json.dumps({"goal": "test"}))

            with patch(
                "maid_runner.cli.validate.watch_all_validations"
            ) as mock_watch_all:
                run_validation(
                    manifest_path=None,
                    validation_mode="implementation",
                    use_manifest_chain=True,
                    quiet=True,
                    manifest_dir=None,  # No manifest_dir specified
                    skip_file_tracking=False,
                    watch=False,
                    watch_all=True,  # Watch all mode
                    timeout=300,
                    verbose=False,
                    skip_tests=True,
                )

                # Should have called watch_all_validations with default 'manifests' dir
                assert mock_watch_all.called
                call_args = mock_watch_all.call_args
                assert call_args.kwargs["manifests_dir"] == Path("manifests")
        finally:
            os.chdir(original_cwd)
