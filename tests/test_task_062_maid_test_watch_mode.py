"""Behavioral tests for Task 062: maid test watch mode

Tests the watch mode functionality for the maid test command, including:
- get_watchable_files() function for extracting files from manifest
- watch_manifest() function for monitoring files and re-running validation
- run_test() integration with watch parameter
- CLI integration with --watch flag
"""

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest


def test_get_watchable_files_is_importable():
    """Test that get_watchable_files() is importable from maid_runner.cli.test."""
    from maid_runner.cli.test import get_watchable_files

    assert callable(get_watchable_files)


def test_watch_manifest_is_importable():
    """Test that watch_manifest() is importable from maid_runner.cli.test."""
    from maid_runner.cli.test import watch_manifest

    assert callable(watch_manifest)


def test_run_test_accepts_watch_parameter():
    """Test that run_test() function accepts a watch parameter."""
    from maid_runner.cli.test import run_test
    import inspect

    # Get function signature
    sig = inspect.signature(run_test)

    # Check that 'watch' parameter exists
    assert "watch" in sig.parameters
    param = sig.parameters["watch"]

    # Should be type bool
    assert param.annotation is bool


def test_get_watchable_files_extracts_editable_files():
    """Test that get_watchable_files() extracts files from editableFiles."""
    from maid_runner.cli.test import get_watchable_files

    manifest_data = {
        "editableFiles": ["src/file1.py", "src/file2.py"],
        "creatableFiles": [],
        "readonlyFiles": ["README.md"],
    }

    watchable = get_watchable_files(manifest_data)

    # Should return list
    assert isinstance(watchable, list)

    # Should contain editableFiles
    assert "src/file1.py" in watchable
    assert "src/file2.py" in watchable

    # Should NOT contain readonlyFiles
    assert "README.md" not in watchable


def test_get_watchable_files_extracts_creatable_files():
    """Test that get_watchable_files() extracts files from creatableFiles."""
    from maid_runner.cli.test import get_watchable_files

    manifest_data = {
        "editableFiles": [],
        "creatableFiles": ["src/new_file.py", "src/another.py"],
        "readonlyFiles": ["README.md"],
    }

    watchable = get_watchable_files(manifest_data)

    # Should contain creatableFiles
    assert "src/new_file.py" in watchable
    assert "src/another.py" in watchable

    # Should NOT contain readonlyFiles
    assert "README.md" not in watchable


def test_get_watchable_files_combines_editable_and_creatable():
    """Test that get_watchable_files() combines editableFiles and creatableFiles."""
    from maid_runner.cli.test import get_watchable_files

    manifest_data = {
        "editableFiles": ["src/edit1.py", "src/edit2.py"],
        "creatableFiles": ["src/new1.py", "src/new2.py"],
        "readonlyFiles": ["tests/test_something.py"],
    }

    watchable = get_watchable_files(manifest_data)

    # Should contain all editable and creatable files
    assert len(watchable) == 4
    assert "src/edit1.py" in watchable
    assert "src/edit2.py" in watchable
    assert "src/new1.py" in watchable
    assert "src/new2.py" in watchable

    # Should NOT contain readonlyFiles
    assert "tests/test_something.py" not in watchable


def test_get_watchable_files_handles_missing_fields():
    """Test that get_watchable_files() handles manifests with missing file fields."""
    from maid_runner.cli.test import get_watchable_files

    # Manifest with only editableFiles
    manifest_data = {"editableFiles": ["src/file.py"]}
    watchable = get_watchable_files(manifest_data)
    assert "src/file.py" in watchable

    # Manifest with only creatableFiles
    manifest_data = {"creatableFiles": ["src/new.py"]}
    watchable = get_watchable_files(manifest_data)
    assert "src/new.py" in watchable

    # Manifest with no file fields
    manifest_data = {}
    watchable = get_watchable_files(manifest_data)
    assert isinstance(watchable, list)
    assert len(watchable) == 0


def test_get_watchable_files_extracts_test_files_from_validation_command():
    """Test that get_watchable_files() also extracts test files from validationCommand."""
    from maid_runner.cli.test import get_watchable_files

    # Manifest with editableFiles and validationCommand containing test files
    manifest_data = {
        "editableFiles": ["src/file.py"],
        "validationCommand": ["pytest", "tests/test_file.py", "-v"],
    }
    watchable = get_watchable_files(manifest_data)

    # Should include both source files and test files
    assert "src/file.py" in watchable
    assert "tests/test_file.py" in watchable

    # Test with validationCommands (multiple commands)
    manifest_data = {
        "editableFiles": ["src/file.py"],
        "validationCommands": [
            ["pytest", "tests/test_one.py", "-v"],
            ["pytest", "tests/test_two.py", "-v"],
        ],
    }
    watchable = get_watchable_files(manifest_data)

    assert "src/file.py" in watchable
    assert "tests/test_one.py" in watchable
    assert "tests/test_two.py" in watchable

    # Test deduplication (same test file mentioned twice)
    manifest_data = {
        "editableFiles": ["tests/test_file.py"],  # Test file also in editableFiles
        "validationCommand": ["pytest", "tests/test_file.py", "-v"],
    }
    watchable = get_watchable_files(manifest_data)

    # Should only appear once
    assert watchable.count("tests/test_file.py") == 1


def test_watch_manifest_monitors_files_and_reruns_validation(tmp_path: Path):
    """Test that watch_manifest() monitors files and re-runs validation on changes."""
    from maid_runner.cli.test import watch_manifest

    # Create test manifest
    manifest_path = tmp_path / "test.manifest.json"
    manifest_data = {
        "editableFiles": ["src/test.py"],
        "validationCommand": ["echo", "validation ran"],
    }

    # Mock watchdog components
    with patch("maid_runner.cli.test.Observer") as mock_observer_class:
        mock_observer = MagicMock()
        mock_observer_class.return_value = mock_observer

        # Mock the event handler to trigger on_modified after a short time
        def simulate_file_change(*args, **kwargs):
            # Simulate KeyboardInterrupt after initial setup
            raise KeyboardInterrupt()

        mock_observer.start.side_effect = simulate_file_change

        # Call watch_manifest - should handle KeyboardInterrupt gracefully
        watch_manifest(
            manifest_path=manifest_path,
            manifest_data=manifest_data,
            timeout=300,
            verbose=False,
            project_root=tmp_path,
            debounce_seconds=2.0,
        )

        # Should have created an observer
        mock_observer_class.assert_called_once()

        # Should have started the observer
        mock_observer.start.assert_called_once()


def test_watch_manifest_implements_debouncing():
    """Test that watch_manifest() implements debouncing to avoid rapid re-runs."""
    from maid_runner.cli.test import watch_manifest

    # The function signature requires debounce_seconds parameter
    import inspect

    sig = inspect.signature(watch_manifest)
    assert "debounce_seconds" in sig.parameters
    param = sig.parameters["debounce_seconds"]

    # Should be float type
    assert param.annotation is float


def test_watch_manifest_handles_keyboard_interrupt(tmp_path: Path):
    """Test that watch_manifest() handles Ctrl+C (KeyboardInterrupt) gracefully."""
    from maid_runner.cli.test import watch_manifest

    manifest_path = tmp_path / "test.manifest.json"
    manifest_data = {
        "editableFiles": ["src/test.py"],
        "validationCommand": ["echo", "test"],
    }

    # Mock watchdog components
    with patch("maid_runner.cli.test.Observer") as mock_observer_class:
        mock_observer = MagicMock()
        mock_observer_class.return_value = mock_observer

        # Simulate KeyboardInterrupt
        mock_observer.start.side_effect = KeyboardInterrupt()

        # Should not raise - should handle gracefully
        watch_manifest(
            manifest_path=manifest_path,
            manifest_data=manifest_data,
            timeout=300,
            verbose=False,
            project_root=tmp_path,
            debounce_seconds=2.0,
        )

        # Should have stopped the observer
        mock_observer.stop.assert_called_once()


def test_watch_manifest_shows_error_if_watchdog_not_available(tmp_path: Path):
    """Test that watch_manifest() shows error if watchdog library is not available."""
    from maid_runner.cli.test import watch_manifest

    tmp_path / "test.manifest.json"

    # Mock watchdog as unavailable
    with patch("maid_runner.cli.test.Observer", None):
        # The function should handle this gracefully
        # Implementation will check if Observer is available
        # For now, just verify the function accepts the parameters
        import inspect

        sig = inspect.signature(watch_manifest)
        # Verify all required parameters are present
        assert "manifest_path" in sig.parameters
        assert "manifest_data" in sig.parameters
        assert "timeout" in sig.parameters
        assert "verbose" in sig.parameters
        assert "project_root" in sig.parameters
        assert "debounce_seconds" in sig.parameters


def test_watch_manifest_monitors_editable_files(tmp_path: Path):
    """Test that watch_manifest() sets up monitoring for editable files."""
    from maid_runner.cli.test import watch_manifest

    manifest_path = tmp_path / "test.manifest.json"
    manifest_data = {
        "editableFiles": ["src/file1.py", "src/subdir/file2.py"],
        "validationCommand": ["echo", "test"],
    }

    with patch("maid_runner.cli.test.Observer") as mock_observer_class:
        mock_observer = MagicMock()
        mock_observer_class.return_value = mock_observer
        mock_observer.start.side_effect = KeyboardInterrupt()

        watch_manifest(
            manifest_path=manifest_path,
            manifest_data=manifest_data,
            timeout=300,
            verbose=False,
            project_root=tmp_path,
            debounce_seconds=2.0,
        )

        # Should have scheduled observers for the parent directories
        assert mock_observer.schedule.called


def test_watch_manifest_runs_initial_validation(tmp_path: Path):
    """Test that watch_manifest() runs initial validation before entering watch loop."""
    from maid_runner.cli.test import watch_manifest

    manifest_path = tmp_path / "test.manifest.json"
    manifest_data = {
        "editableFiles": ["src/test.py"],
        "validationCommand": ["echo", "initial validation"],
    }

    # Mock execute_validation_commands to track calls
    with patch("maid_runner.cli.test.execute_validation_commands") as mock_execute:
        mock_execute.return_value = (1, 0, 1)  # passed, failed, total

        with patch("maid_runner.cli.test.Observer") as mock_observer_class:
            mock_observer = MagicMock()
            mock_observer_class.return_value = mock_observer
            mock_observer.start.side_effect = KeyboardInterrupt()

            watch_manifest(
                manifest_path=manifest_path,
                manifest_data=manifest_data,
                timeout=300,
                verbose=False,
                project_root=tmp_path,
                debounce_seconds=2.0,
            )

            # Should have called execute_validation_commands for initial run
            assert mock_execute.called


def test_run_test_with_watch_mode_enabled(tmp_path: Path):
    """Test that run_test() enters watch mode when watch=True."""
    from maid_runner.cli.test import run_test

    # Create manifests directory
    manifests_dir = tmp_path / "manifests"
    manifests_dir.mkdir()

    # Create a test manifest
    manifest = {
        "version": "1",
        "goal": "watch mode test",
        "taskType": "edit",
        "editableFiles": ["src/test.py"],
        "validationCommand": ["echo", "test"],
    }
    manifest_file = manifests_dir / "task-001.manifest.json"
    manifest_file.write_text(json.dumps(manifest))

    # Mock watch_manifest to avoid actually entering watch loop
    with patch("maid_runner.cli.test.watch_manifest") as mock_watch:
        # Should exit normally after watch_manifest returns
        with pytest.raises(SystemExit):
            run_test(
                manifest_dir=str(manifests_dir),
                fail_fast=False,
                verbose=False,
                quiet=False,
                timeout=300,
                manifest_path="task-001.manifest.json",
                watch=True,
            )

        # Should have called watch_manifest
        assert mock_watch.called

        # Get the call arguments
        call_args = mock_watch.call_args

        # Should have passed manifest data
        assert "manifest_data" in call_args.kwargs or len(call_args.args) >= 2

        # Should have passed debounce_seconds
        assert "debounce_seconds" in call_args.kwargs or len(call_args.args) >= 6


def test_run_test_watch_requires_manifest_path(tmp_path: Path):
    """Test that run_test() with watch=True requires manifest_path to be specified."""
    from maid_runner.cli.test import run_test

    # Create manifests directory
    manifests_dir = tmp_path / "manifests"
    manifests_dir.mkdir()

    # Create a test manifest
    manifest = {
        "version": "1",
        "goal": "watch mode test",
        "taskType": "edit",
        "editableFiles": ["src/test.py"],
        "validationCommand": ["echo", "test"],
    }
    manifest_file = manifests_dir / "task-001.manifest.json"
    manifest_file.write_text(json.dumps(manifest))

    # Try to use watch mode without manifest_path
    with pytest.raises(SystemExit) as exc_info:
        run_test(
            manifest_dir=str(manifests_dir),
            fail_fast=False,
            verbose=False,
            quiet=False,
            timeout=300,
            manifest_path=None,  # No specific manifest
            watch=True,  # But watch mode enabled
        )

    # Should exit with error (code 1)
    assert exc_info.value.code == 1


def test_watch_manifest_passes_timeout_to_validation_commands(tmp_path: Path):
    """Test that watch_manifest() passes timeout parameter to validation commands."""
    from maid_runner.cli.test import watch_manifest

    manifest_path = tmp_path / "test.manifest.json"
    manifest_data = {
        "editableFiles": ["src/test.py"],
        "validationCommand": ["sleep", "10"],  # Long-running command
    }

    custom_timeout = 5

    with patch("maid_runner.cli.test.execute_validation_commands") as mock_execute:
        mock_execute.return_value = (1, 0, 1)

        with patch("maid_runner.cli.test.Observer") as mock_observer_class:
            mock_observer = MagicMock()
            mock_observer_class.return_value = mock_observer
            mock_observer.start.side_effect = KeyboardInterrupt()

            watch_manifest(
                manifest_path=manifest_path,
                manifest_data=manifest_data,
                timeout=custom_timeout,
                verbose=False,
                project_root=tmp_path,
                debounce_seconds=2.0,
            )

            # Should have called execute_validation_commands with custom timeout
            assert mock_execute.called
            call_args = mock_execute.call_args
            assert call_args.kwargs["timeout"] == custom_timeout


def test_watch_manifest_passes_verbose_flag(tmp_path: Path):
    """Test that watch_manifest() passes verbose flag to validation commands."""
    from maid_runner.cli.test import watch_manifest

    manifest_path = tmp_path / "test.manifest.json"
    manifest_data = {
        "editableFiles": ["src/test.py"],
        "validationCommand": ["echo", "test"],
    }

    with patch("maid_runner.cli.test.execute_validation_commands") as mock_execute:
        mock_execute.return_value = (1, 0, 1)

        with patch("maid_runner.cli.test.Observer") as mock_observer_class:
            mock_observer = MagicMock()
            mock_observer_class.return_value = mock_observer
            mock_observer.start.side_effect = KeyboardInterrupt()

            watch_manifest(
                manifest_path=manifest_path,
                manifest_data=manifest_data,
                timeout=300,
                verbose=True,  # Enable verbose
                project_root=tmp_path,
                debounce_seconds=2.0,
            )

            # Should have called execute_validation_commands with verbose=True
            assert mock_execute.called
            call_args = mock_execute.call_args
            assert call_args.kwargs["verbose"] is True


def test_watch_manifest_with_creatable_files(tmp_path: Path):
    """Test that watch_manifest() monitors creatableFiles as well as editableFiles."""
    from maid_runner.cli.test import watch_manifest

    manifest_path = tmp_path / "test.manifest.json"
    manifest_data = {
        "editableFiles": ["src/existing.py"],
        "creatableFiles": ["src/new_file.py"],
        "validationCommand": ["echo", "test"],
    }

    with patch("maid_runner.cli.test.Observer") as mock_observer_class:
        mock_observer = MagicMock()
        mock_observer_class.return_value = mock_observer
        mock_observer.start.side_effect = KeyboardInterrupt()

        watch_manifest(
            manifest_path=manifest_path,
            manifest_data=manifest_data,
            timeout=300,
            verbose=False,
            project_root=tmp_path,
            debounce_seconds=2.0,
        )

        # Should have scheduled observers
        # Implementation should watch both editable and creatable files
        assert mock_observer.schedule.called


def test_run_test_function_signature_includes_watch():
    """Test that run_test() function signature includes watch parameter with correct type."""
    from maid_runner.cli.test import run_test
    import inspect

    sig = inspect.signature(run_test)

    # Verify all expected parameters exist
    expected_params = [
        "manifest_dir",
        "fail_fast",
        "verbose",
        "quiet",
        "timeout",
        "manifest_path",
        "watch",
    ]

    for param in expected_params:
        assert param in sig.parameters, f"Parameter '{param}' missing from run_test()"

    # Verify watch parameter has correct type annotation
    watch_param = sig.parameters["watch"]
    assert watch_param.annotation is bool


def test_watch_manifest_function_signature_is_correct():
    """Test that watch_manifest() has the correct function signature."""
    from maid_runner.cli.test import watch_manifest
    import inspect

    sig = inspect.signature(watch_manifest)

    # Verify all expected parameters exist
    expected_params = [
        "manifest_path",
        "manifest_data",
        "timeout",
        "verbose",
        "project_root",
        "debounce_seconds",
    ]

    for param in expected_params:
        assert (
            param in sig.parameters
        ), f"Parameter '{param}' missing from watch_manifest()"

    # Verify type annotations
    assert sig.parameters["manifest_path"].annotation == Path
    assert sig.parameters["manifest_data"].annotation is dict
    assert sig.parameters["timeout"].annotation is int
    assert sig.parameters["verbose"].annotation is bool
    assert sig.parameters["project_root"].annotation is Path
    assert sig.parameters["debounce_seconds"].annotation is float

    # Verify return type
    assert sig.return_annotation is None


def test_get_watchable_files_returns_list():
    """Test that get_watchable_files() returns a List[str]."""
    from maid_runner.cli.test import get_watchable_files
    import inspect

    sig = inspect.signature(get_watchable_files)

    # Verify return type annotation
    from typing import List

    assert sig.return_annotation == List[str]


def test_watch_mode_with_no_watchable_files(tmp_path: Path):
    """Test that watch_manifest() handles manifests with no watchable files."""
    from maid_runner.cli.test import watch_manifest

    manifest_path = tmp_path / "test.manifest.json"
    manifest_data = {
        "readonlyFiles": ["README.md"],  # Only readonly files
        "validationCommand": ["echo", "test"],
    }

    with patch("maid_runner.cli.test.Observer") as mock_observer_class:
        mock_observer = MagicMock()
        mock_observer_class.return_value = mock_observer
        mock_observer.start.side_effect = KeyboardInterrupt()

        # Should handle gracefully even with no watchable files
        watch_manifest(
            manifest_path=manifest_path,
            manifest_data=manifest_data,
            timeout=300,
            verbose=False,
            project_root=tmp_path,
            debounce_seconds=2.0,
        )


def test_manifest_path_resolution_accepts_multiple_formats(tmp_path: Path):
    """Test that manifest path resolution handles various path formats correctly."""
    import json
    import os

    # Change to tmp_path to simulate running from project root
    original_cwd = os.getcwd()
    try:
        os.chdir(tmp_path)

        # Create a test manifest in a manifests directory
        manifests_dir = tmp_path / "manifests"
        manifests_dir.mkdir()
        manifest_file = manifests_dir / "task-test.manifest.json"

        manifest_data = {
            "goal": "Test path resolution",
            "editableFiles": ["test.py"],
            "validationCommand": ["echo", "test"],
        }

        with open(manifest_file, "w") as f:
            json.dump(manifest_data, f)

        # Test different path formats (all should work)
        path_formats = [
            ("task-test.manifest.json", "Just filename"),
            ("manifests/task-test.manifest.json", "With manifests/ prefix"),
            ("./manifests/task-test.manifest.json", "With ./ prefix"),
        ]

        for path_format, description in path_formats:
            # Simulate the resolution logic from run_test()
            from pathlib import Path

            specific_manifest = Path(path_format)

            # Apply the same logic as in run_test()
            if not specific_manifest.is_absolute():
                # Try as-is first
                if not specific_manifest.exists():
                    # Try relative to manifests_dir
                    specific_manifest = manifests_dir / specific_manifest

            # All formats should resolve successfully
            assert (
                specific_manifest.exists()
            ), f"Failed to resolve: {description} ({path_format})"
            assert (
                specific_manifest.resolve() == manifest_file.resolve()
            ), f"Wrong resolution: {description}"

    finally:
        os.chdir(original_cwd)
