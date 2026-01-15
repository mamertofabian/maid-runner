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


class TestBuildFileToManifestsMapErrors:
    """Tests for error handling in build_file_to_manifests_map_for_validation."""

    def test_handles_invalid_json_in_manifest(self, tmp_path: Path):
        """Test that build_file_to_manifests_map_for_validation handles invalid JSON gracefully."""
        from maid_runner.cli.validate import build_file_to_manifests_map_for_validation

        manifests_dir = tmp_path / "manifests"
        manifests_dir.mkdir()

        # Create a manifest with invalid JSON
        bad_manifest = manifests_dir / "task-001.manifest.json"
        bad_manifest.write_text("not valid json {{{")

        # Should not raise, should skip the bad manifest
        result = build_file_to_manifests_map_for_validation(
            manifests_dir, [bad_manifest]
        )
        assert isinstance(result, dict)

    def test_handles_io_error_reading_manifest(self, tmp_path: Path):
        """Test that build_file_to_manifests_map_for_validation handles IO errors gracefully."""
        from maid_runner.cli.validate import build_file_to_manifests_map_for_validation

        manifests_dir = tmp_path / "manifests"
        manifests_dir.mkdir()

        # Create a reference to a non-existent manifest
        missing_manifest = manifests_dir / "task-001.manifest.json"

        # Should not raise, should skip the missing manifest
        result = build_file_to_manifests_map_for_validation(
            manifests_dir, [missing_manifest]
        )
        assert isinstance(result, dict)


class TestCheckIfSupersededErrors:
    """Tests for error handling in _check_if_superseded."""

    def test_handles_invalid_json_in_other_manifest(self, tmp_path: Path):
        """Test that _check_if_superseded handles invalid JSON in other manifests."""
        from maid_runner.cli.validate import _check_if_superseded

        manifests_dir = tmp_path / "manifests"
        manifests_dir.mkdir()

        # Create target manifest
        target_manifest = manifests_dir / "task-001.manifest.json"
        target_manifest.write_text('{"goal": "target"}')

        # Create a manifest with invalid JSON
        bad_manifest = manifests_dir / "task-002.manifest.json"
        bad_manifest.write_text("not valid json {{{")

        # Should not raise
        is_superseded, superseder = _check_if_superseded(target_manifest, manifests_dir)
        assert isinstance(is_superseded, bool)


class TestBuildSupersedeHint:
    """Tests for _build_supersede_hint function."""

    def test_returns_none_for_non_unexpected_error(self, tmp_path: Path):
        """Test that _build_supersede_hint returns None for non-'Unexpected public' errors."""
        from maid_runner.cli.validate import _build_supersede_hint

        manifest_path = tmp_path / "task-001.manifest.json"
        manifest_data = {"goal": "test"}

        result = _build_supersede_hint(
            manifest_path=manifest_path,
            manifest_data=manifest_data,
            target_file="src/test.py",
            error_message="Some other error",
        )
        assert result is None

    def test_returns_none_when_no_related_manifests(self, tmp_path: Path):
        """Test that _build_supersede_hint returns None when no related manifests found."""
        from maid_runner.cli.validate import _build_supersede_hint

        manifest_path = tmp_path / "task-001.manifest.json"
        manifest_data = {"goal": "test"}

        result = _build_supersede_hint(
            manifest_path=manifest_path,
            manifest_data=manifest_data,
            target_file="nonexistent/file.py",
            error_message="Unexpected public function 'foo' found",
        )
        # May return None if no related manifests
        assert result is None or isinstance(result, str)


class TestValidationHelpers:
    """Tests for validation helper functions."""

    def test_should_skip_debounce_is_importable(self):
        """Test that _should_skip_debounce is importable."""
        from maid_runner.cli.validate import _should_skip_debounce

        assert callable(_should_skip_debounce)

    def test_should_skip_debounce_returns_true_within_threshold(self):
        """Test that _should_skip_debounce returns True when within debounce window."""
        from maid_runner.cli.validate import _should_skip_debounce

        last_run = 100.0
        current_time = 100.5  # 0.5 seconds later
        debounce_seconds = 2.0

        result = _should_skip_debounce(last_run, current_time, debounce_seconds)
        assert result is True

    def test_should_skip_debounce_returns_false_outside_threshold(self):
        """Test that _should_skip_debounce returns False when outside debounce window."""
        from maid_runner.cli.validate import _should_skip_debounce

        last_run = 100.0
        current_time = 103.0  # 3 seconds later
        debounce_seconds = 2.0

        result = _should_skip_debounce(last_run, current_time, debounce_seconds)
        assert result is False

    def test_get_display_path_is_importable(self):
        """Test that _get_display_path is importable."""
        from maid_runner.cli.validate import _get_display_path

        assert callable(_get_display_path)

    def test_get_display_path_returns_relative_path(self, tmp_path: Path):
        """Test that _get_display_path returns a relative path when possible."""
        from maid_runner.cli.validate import _get_display_path

        file_path = tmp_path / "src" / "test.py"
        project_root = tmp_path

        result = _get_display_path(file_path, project_root)
        # Should return a Path object representing the relative path
        assert isinstance(result, Path)
        assert str(result) == "src/test.py"


class TestExecuteValidationCommandExtended:
    """Extended tests for execute_validation_command error handling."""

    def test_execute_validation_command_shows_stderr_on_failure(
        self, tmp_path: Path, capsys
    ):
        """Test that execute_validation_command shows stderr when command fails."""
        from maid_runner.cli.validate import execute_validation_command

        manifest_data = {
            # Command that fails and outputs to stderr
            "validationCommand": [
                "python",
                "-c",
                "import sys; print('error message', file=sys.stderr); sys.exit(1)",
            ],
        }

        result = execute_validation_command(
            manifest_data=manifest_data,
            project_root=tmp_path,
            timeout=30,
            verbose=False,
        )

        assert result is False
        captured = capsys.readouterr()
        assert "FAILED" in captured.out

    def test_execute_validation_command_shows_output_in_verbose_mode(
        self, tmp_path: Path, capsys
    ):
        """Test that execute_validation_command shows command output in verbose mode."""
        from maid_runner.cli.validate import execute_validation_command

        manifest_data = {
            "validationCommand": ["echo", "verbose output test"],
        }

        result = execute_validation_command(
            manifest_data=manifest_data,
            project_root=tmp_path,
            timeout=30,
            verbose=True,
        )

        assert result is True
        captured = capsys.readouterr()
        assert "PASSED" in captured.out
        assert "verbose output test" in captured.out

    def test_execute_validation_command_handles_command_not_found(
        self, tmp_path: Path, capsys
    ):
        """Test that execute_validation_command handles non-existent commands."""
        from maid_runner.cli.validate import execute_validation_command

        manifest_data = {
            "validationCommand": ["nonexistent_command_xyz123", "--help"],
        }

        result = execute_validation_command(
            manifest_data=manifest_data,
            project_root=tmp_path,
            timeout=30,
            verbose=False,
        )

        assert result is False
        captured = capsys.readouterr()
        # Should have printed an error about the command
        assert "❌" in captured.out or "not found" in captured.out.lower()

    def test_execute_validation_command_skips_empty_commands(
        self, tmp_path: Path, capsys
    ):
        """Test that execute_validation_command skips empty commands in the list."""
        from maid_runner.cli.validate import execute_validation_command

        manifest_data = {
            "validationCommands": [[], ["echo", "valid"]],  # First is empty
        }

        result = execute_validation_command(
            manifest_data=manifest_data,
            project_root=tmp_path,
            timeout=30,
            verbose=False,
        )

        assert result is True
        captured = capsys.readouterr()
        assert "PASSED" in captured.out


class TestRunDualModeValidationExtended:
    """Extended tests for run_dual_mode_validation error handling."""

    def test_run_dual_mode_validation_handles_file_not_found(self, tmp_path: Path):
        """Test that run_dual_mode_validation handles FileNotFoundError gracefully."""
        from maid_runner.cli.validate import run_dual_mode_validation
        from unittest.mock import patch

        manifest_path = tmp_path / "manifests" / "task-001.manifest.json"
        manifest_path.parent.mkdir(parents=True)

        manifest_data = {
            "version": "1",
            "goal": "Test file not found",
            "taskType": "edit",
            "editableFiles": ["nonexistent_file.py"],
            "expectedArtifacts": {
                "file": "nonexistent_file.py",
                "contains": [{"type": "function", "name": "func"}],
            },
        }
        manifest_path.write_text(json.dumps(manifest_data))

        with patch("maid_runner.cli.validate.run_validation") as mock_run:
            with patch("maid_runner.cli.validate.validate_schema"):
                # Simulate FileNotFoundError during validation
                mock_run.side_effect = FileNotFoundError("File not found")

                import os

                original_cwd = os.getcwd()
                try:
                    os.chdir(tmp_path)
                    result = run_dual_mode_validation(
                        manifest_path=manifest_path,
                        use_manifest_chain=False,
                        quiet=True,
                    )

                    # Should return dict with False values for the failing validation
                    assert isinstance(result, dict)
                    assert result["behavioral"] is False
                finally:
                    os.chdir(original_cwd)

    def test_run_dual_mode_validation_with_quiet_false(self, tmp_path: Path, capsys):
        """Test that run_dual_mode_validation prints output when quiet=False."""
        from maid_runner.cli.validate import run_dual_mode_validation
        from unittest.mock import patch

        manifest_path = tmp_path / "manifests" / "task-001.manifest.json"
        manifest_path.parent.mkdir(parents=True)

        manifest_data = {
            "version": "1",
            "goal": "Test quiet=False",
            "taskType": "edit",
            "editableFiles": ["src/example.py"],
            "expectedArtifacts": {
                "file": "src/example.py",
                "contains": [{"type": "function", "name": "example"}],
            },
        }
        manifest_path.write_text(json.dumps(manifest_data))

        with patch("maid_runner.cli.validate.run_validation"):
            with patch("maid_runner.cli.validate.validate_schema"):
                import os

                original_cwd = os.getcwd()
                try:
                    os.chdir(tmp_path)
                    result = run_dual_mode_validation(
                        manifest_path=manifest_path,
                        use_manifest_chain=False,
                        quiet=False,  # Output enabled
                    )

                    # Result should be a dict with validation status
                    assert isinstance(result, dict)

                    captured = capsys.readouterr()
                    # Should have printed validation messages
                    assert "validation" in captured.out.lower()
                finally:
                    os.chdir(original_cwd)

    def test_run_dual_mode_validation_handles_schema_failure(
        self, tmp_path: Path, capsys
    ):
        """Test that run_dual_mode_validation handles schema validation failure."""
        from maid_runner.cli.validate import run_dual_mode_validation
        from unittest.mock import patch
        import jsonschema

        manifest_path = tmp_path / "manifests" / "task-001.manifest.json"
        manifest_path.parent.mkdir(parents=True)

        # Write invalid manifest
        manifest_path.write_text('{"invalid": "manifest"}')

        with patch("maid_runner.cli.validate.validate_schema") as mock_validate:
            # Simulate schema validation failure
            mock_validate.side_effect = jsonschema.ValidationError("Invalid schema")

            import os

            original_cwd = os.getcwd()
            try:
                os.chdir(tmp_path)
                result = run_dual_mode_validation(
                    manifest_path=manifest_path,
                    use_manifest_chain=False,
                    quiet=False,
                )

                # Schema validation should have failed
                assert isinstance(result, dict)
                assert result["schema"] is False
            finally:
                os.chdir(original_cwd)

    def test_run_dual_mode_validation_handles_system_exit_with_zero(
        self, tmp_path: Path
    ):
        """Test that run_dual_mode_validation handles SystemExit(0) as success."""
        from maid_runner.cli.validate import run_dual_mode_validation
        from unittest.mock import patch

        manifest_path = tmp_path / "manifests" / "task-001.manifest.json"
        manifest_path.parent.mkdir(parents=True)

        manifest_data = {
            "version": "1",
            "goal": "Test SystemExit 0",
            "taskType": "edit",
            "editableFiles": ["src/example.py"],
            "expectedArtifacts": {
                "file": "src/example.py",
                "contains": [{"type": "function", "name": "example"}],
            },
        }
        manifest_path.write_text(json.dumps(manifest_data))

        with patch("maid_runner.cli.validate.run_validation") as mock_run:
            with patch("maid_runner.cli.validate.validate_schema"):
                # SystemExit(0) should be treated as success
                mock_run.side_effect = SystemExit(0)

                import os

                original_cwd = os.getcwd()
                try:
                    os.chdir(tmp_path)
                    result = run_dual_mode_validation(
                        manifest_path=manifest_path,
                        use_manifest_chain=False,
                        quiet=True,
                    )

                    # SystemExit(0) should result in True for that mode
                    assert isinstance(result, dict)
                    assert result["schema"] is True
                    assert result["behavioral"] is True
                finally:
                    os.chdir(original_cwd)


class TestRunValidationErrorPaths:
    """Tests for run_validation error handling paths."""

    def test_run_validation_watch_mode_manifest_not_found(self, tmp_path: Path):
        """Test that run_validation in watch mode exits if manifest not found."""
        from maid_runner.cli.validate import run_validation

        nonexistent_manifest = tmp_path / "nonexistent.manifest.json"

        with pytest.raises(SystemExit) as exc_info:
            run_validation(
                manifest_path=str(nonexistent_manifest),
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

        assert exc_info.value.code == 1

    def test_run_validation_watch_all_mode_dir_not_found(self, tmp_path: Path):
        """Test that run_validation in watch_all mode exits if dir not found."""
        from maid_runner.cli.validate import run_validation

        nonexistent_dir = tmp_path / "nonexistent_manifests"

        with pytest.raises(SystemExit) as exc_info:
            run_validation(
                manifest_path=None,
                validation_mode="implementation",
                use_manifest_chain=True,
                quiet=True,
                manifest_dir=str(nonexistent_dir),
                skip_file_tracking=False,
                watch=False,
                watch_all=True,
                timeout=300,
                verbose=False,
                skip_tests=True,
            )

        assert exc_info.value.code == 1


class TestRunTestsForManifest:
    """Tests for _run_tests_for_manifest function."""

    def test_run_tests_for_manifest_handles_invalid_json(self, tmp_path: Path):
        """Test that _run_tests_for_manifest handles invalid JSON manifest."""
        from maid_runner.cli.validate import _run_tests_for_manifest

        manifest_path = tmp_path / "test.manifest.json"
        manifest_path.write_text("not valid json {{{")

        result = _run_tests_for_manifest(
            manifest_path=manifest_path,
            project_root=tmp_path,
            timeout=300,
            verbose=False,
            quiet=True,
        )

        assert result is False

    def test_run_tests_for_manifest_handles_io_error(self, tmp_path: Path):
        """Test that _run_tests_for_manifest handles IO errors."""
        from maid_runner.cli.validate import _run_tests_for_manifest

        nonexistent_manifest = tmp_path / "nonexistent.manifest.json"

        result = _run_tests_for_manifest(
            manifest_path=nonexistent_manifest,
            project_root=tmp_path,
            timeout=300,
            verbose=False,
            quiet=True,
        )

        assert result is False


class TestValidationJsonOutput:
    """Tests for JSON output formatting."""

    def test_format_validation_json_returns_valid_json(self):
        """Test that format_validation_json returns valid JSON string."""
        from maid_runner.cli.validate import format_validation_json

        result = format_validation_json(
            success=True,
            errors=[],
            warnings=[],
            metadata={"manifest": "test.json"},
        )

        # Should be valid JSON
        import json

        parsed = json.loads(result)
        assert parsed["success"] is True
        assert parsed["errors"] == []
        assert parsed["warnings"] == []

    def test_format_validation_json_includes_errors(self):
        """Test that format_validation_json includes error details."""
        from maid_runner.cli.validate import format_validation_json
        from maid_runner.validation_result import (
            ValidationError,
            ErrorCode,
            ErrorSeverity,
        )

        error = ValidationError(
            code=ErrorCode.ARTIFACT_NOT_FOUND,
            message="Test error",
            file="test.py",
            severity=ErrorSeverity.ERROR,
        )

        result = format_validation_json(
            success=False,
            errors=[error],
            warnings=[],
            metadata={},
        )

        import json

        parsed = json.loads(result)
        assert parsed["success"] is False
        assert len(parsed["errors"]) == 1
        assert parsed["errors"][0]["message"] == "Test error"


# =============================================================================
# Tests for _validate_helpers.py
# =============================================================================


class TestValidateHelpers:
    """Tests for private validate helper functions."""

    def test_get_display_path_relative(self, tmp_path: Path):
        """Test _get_display_path returns relative path when possible."""
        from maid_runner.cli._validate_helpers import _get_display_path

        file_path = tmp_path / "src" / "test.py"
        project_root = tmp_path

        result = _get_display_path(file_path, project_root)
        assert result == Path("src/test.py")

    def test_get_display_path_outside_project(self, tmp_path: Path):
        """Test _get_display_path returns absolute path when file is outside project."""
        from maid_runner.cli._validate_helpers import _get_display_path

        # Create a path that's outside the project root
        file_path = Path("/tmp/some/external/file.py")
        project_root = tmp_path / "myproject"
        project_root.mkdir()

        result = _get_display_path(file_path, project_root)
        # Should return the original file path when it's not under project root
        assert result == file_path

    def test_are_validations_passed_all_true(self):
        """Test _are_validations_passed returns True when all validations pass."""
        from maid_runner.cli._validate_helpers import _are_validations_passed

        results = {
            "schema": True,
            "behavioral": True,
            "implementation": True,
            "tests": None,  # tests are excluded
        }
        assert _are_validations_passed(results) is True

    def test_are_validations_passed_with_failure(self):
        """Test _are_validations_passed returns False when any validation fails."""
        from maid_runner.cli._validate_helpers import _are_validations_passed

        results = {
            "schema": True,
            "behavioral": False,
            "implementation": True,
            "tests": None,
        }
        assert _are_validations_passed(results) is False

    def test_should_skip_debounce_within_interval(self):
        """Test _should_skip_debounce returns True within debounce interval."""
        from maid_runner.cli._validate_helpers import _should_skip_debounce

        last_run = 100.0
        current_time = 100.3
        debounce_seconds = 0.5

        result = _should_skip_debounce(last_run, current_time, debounce_seconds)
        assert result is True

    def test_should_skip_debounce_after_interval(self):
        """Test _should_skip_debounce returns False after debounce interval."""
        from maid_runner.cli._validate_helpers import _should_skip_debounce

        last_run = 100.0
        current_time = 101.0
        debounce_seconds = 0.5

        result = _should_skip_debounce(last_run, current_time, debounce_seconds)
        assert result is False
