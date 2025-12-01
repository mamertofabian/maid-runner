"""Behavioral tests for Task 063: Multi-manifest watch mode

Tests the multi-manifest watch mode functionality that watches all active manifests
and intelligently runs only affected validation commands when files change.

Artifacts under test:
- build_file_to_manifests_map(): Maps files to their manifests
- _MultiManifestFileChangeHandler: Handles file changes across multiple manifests
- watch_all_manifests(): Main watch function for all manifests
- run_test() with watch=True and manifest_path=None: Triggers multi-manifest watch
"""

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest


def test_build_file_to_manifests_map_is_importable():
    """Test that build_file_to_manifests_map() is importable."""
    from maid_runner.cli.test import build_file_to_manifests_map

    assert callable(build_file_to_manifests_map)


def test_multi_manifest_file_change_handler_is_importable():
    """Test that _MultiManifestFileChangeHandler class is importable."""
    from maid_runner.cli.test import _MultiManifestFileChangeHandler

    assert _MultiManifestFileChangeHandler is not None


def test_watch_all_manifests_is_importable():
    """Test that watch_all_manifests() is importable."""
    from maid_runner.cli.test import watch_all_manifests

    assert callable(watch_all_manifests)


def test_build_file_to_manifests_map_with_multiple_manifests_referencing_same_file(
    tmp_path: Path,
):
    """Test build_file_to_manifests_map() with multiple manifests referencing the same file."""
    from maid_runner.cli.test import build_file_to_manifests_map

    manifests_dir = tmp_path / "manifests"
    manifests_dir.mkdir()

    # Create first manifest that edits shared_file.py
    manifest1_data = {
        "version": "1",
        "goal": "task 1",
        "taskType": "edit",
        "editableFiles": ["src/shared_file.py", "src/file1.py"],
        "validationCommand": ["echo", "test1"],
    }
    manifest1 = manifests_dir / "task-001.manifest.json"
    manifest1.write_text(json.dumps(manifest1_data))

    # Create second manifest that also edits shared_file.py
    manifest2_data = {
        "version": "1",
        "goal": "task 2",
        "taskType": "edit",
        "editableFiles": ["src/shared_file.py", "src/file2.py"],
        "validationCommand": ["echo", "test2"],
    }
    manifest2 = manifests_dir / "task-002.manifest.json"
    manifest2.write_text(json.dumps(manifest2_data))

    active_manifests = [manifest1, manifest2]

    # Build the map
    file_to_manifests = build_file_to_manifests_map(manifests_dir, active_manifests)

    # Should return a dict
    assert isinstance(file_to_manifests, dict)

    # Get absolute paths for comparison
    project_root = tmp_path
    shared_file_abs = (project_root / "src" / "shared_file.py").resolve()
    file1_abs = (project_root / "src" / "file1.py").resolve()
    file2_abs = (project_root / "src" / "file2.py").resolve()

    # shared_file.py should map to both manifests
    assert shared_file_abs in file_to_manifests
    assert len(file_to_manifests[shared_file_abs]) == 2
    assert manifest1 in file_to_manifests[shared_file_abs]
    assert manifest2 in file_to_manifests[shared_file_abs]

    # file1.py should only map to manifest1
    assert file1_abs in file_to_manifests
    assert len(file_to_manifests[file1_abs]) == 1
    assert manifest1 in file_to_manifests[file1_abs]

    # file2.py should only map to manifest2
    assert file2_abs in file_to_manifests
    assert len(file_to_manifests[file2_abs]) == 1
    assert manifest2 in file_to_manifests[file2_abs]


def test_build_file_to_manifests_map_with_unique_files_per_manifest(tmp_path: Path):
    """Test build_file_to_manifests_map() with unique files per manifest (no overlap)."""
    from maid_runner.cli.test import build_file_to_manifests_map

    manifests_dir = tmp_path / "manifests"
    manifests_dir.mkdir()

    # Create first manifest with unique files
    manifest1_data = {
        "version": "1",
        "goal": "task 1",
        "taskType": "edit",
        "editableFiles": ["src/unique1.py"],
        "validationCommand": ["echo", "test1"],
    }
    manifest1 = manifests_dir / "task-001.manifest.json"
    manifest1.write_text(json.dumps(manifest1_data))

    # Create second manifest with different unique files
    manifest2_data = {
        "version": "1",
        "goal": "task 2",
        "taskType": "edit",
        "editableFiles": ["src/unique2.py"],
        "validationCommand": ["echo", "test2"],
    }
    manifest2 = manifests_dir / "task-002.manifest.json"
    manifest2.write_text(json.dumps(manifest2_data))

    active_manifests = [manifest1, manifest2]

    # Build the map
    file_to_manifests = build_file_to_manifests_map(manifests_dir, active_manifests)

    # Get absolute paths for comparison
    project_root = tmp_path
    unique1_abs = (project_root / "src" / "unique1.py").resolve()
    unique2_abs = (project_root / "src" / "unique2.py").resolve()

    # Each file should map to only one manifest
    assert len(file_to_manifests[unique1_abs]) == 1
    assert manifest1 in file_to_manifests[unique1_abs]

    assert len(file_to_manifests[unique2_abs]) == 1
    assert manifest2 in file_to_manifests[unique2_abs]


def test_build_file_to_manifests_map_excludes_superseded_manifests(tmp_path: Path):
    """Test that build_file_to_manifests_map() only processes active manifests (superseded excluded)."""
    from maid_runner.cli.test import build_file_to_manifests_map

    manifests_dir = tmp_path / "manifests"
    manifests_dir.mkdir()

    # Create original manifest
    manifest1_data = {
        "version": "1",
        "goal": "original task",
        "taskType": "edit",
        "editableFiles": ["src/file.py"],
        "validationCommand": ["echo", "test1"],
    }
    manifest1 = manifests_dir / "task-001.manifest.json"
    manifest1.write_text(json.dumps(manifest1_data))

    # Create superseding manifest
    manifest2_data = {
        "version": "1",
        "goal": "updated task",
        "taskType": "edit",
        "editableFiles": ["src/file.py", "src/new_file.py"],
        "supersedes": ["manifests/task-001.manifest.json"],
        "validationCommand": ["echo", "test2"],
    }
    manifest2 = manifests_dir / "task-002.manifest.json"
    manifest2.write_text(json.dumps(manifest2_data))

    # Active manifests list should only include manifest2 (manifest1 is superseded)
    active_manifests = [manifest2]  # manifest1 excluded by caller

    # Build the map
    file_to_manifests = build_file_to_manifests_map(manifests_dir, active_manifests)

    # Get absolute paths for comparison
    project_root = tmp_path
    file_abs = (project_root / "src" / "file.py").resolve()

    # src/file.py should only map to manifest2, not manifest1
    assert file_abs in file_to_manifests
    assert len(file_to_manifests[file_abs]) == 1
    assert manifest2 in file_to_manifests[file_abs]
    assert manifest1 not in file_to_manifests[file_abs]


def test_build_file_to_manifests_map_with_empty_manifest_list(tmp_path: Path):
    """Test build_file_to_manifests_map() with empty active_manifests list."""
    from maid_runner.cli.test import build_file_to_manifests_map

    manifests_dir = tmp_path / "manifests"
    manifests_dir.mkdir()

    active_manifests = []

    # Build the map
    file_to_manifests = build_file_to_manifests_map(manifests_dir, active_manifests)

    # Should return empty dict
    assert isinstance(file_to_manifests, dict)
    assert len(file_to_manifests) == 0


def test_build_file_to_manifests_map_includes_creatable_files(tmp_path: Path):
    """Test that build_file_to_manifests_map() includes creatableFiles."""
    from maid_runner.cli.test import build_file_to_manifests_map

    manifests_dir = tmp_path / "manifests"
    manifests_dir.mkdir()

    manifest_data = {
        "version": "1",
        "goal": "create new files",
        "taskType": "create",
        "creatableFiles": ["src/new_file.py", "src/another_new.py"],
        "editableFiles": ["src/existing.py"],
        "validationCommand": ["echo", "test"],
    }
    manifest = manifests_dir / "task-001.manifest.json"
    manifest.write_text(json.dumps(manifest_data))

    active_manifests = [manifest]

    # Build the map
    file_to_manifests = build_file_to_manifests_map(manifests_dir, active_manifests)

    # Get absolute paths for comparison
    project_root = tmp_path
    new_file_abs = (project_root / "src" / "new_file.py").resolve()
    another_new_abs = (project_root / "src" / "another_new.py").resolve()
    existing_abs = (project_root / "src" / "existing.py").resolve()

    # Should include both creatable and editable files
    assert new_file_abs in file_to_manifests
    assert another_new_abs in file_to_manifests
    assert existing_abs in file_to_manifests


def test_build_file_to_manifests_map_includes_test_files(tmp_path: Path):
    """Test that build_file_to_manifests_map() includes test files from validationCommand."""
    from maid_runner.cli.test import build_file_to_manifests_map

    manifests_dir = tmp_path / "manifests"
    manifests_dir.mkdir()

    manifest_data = {
        "version": "1",
        "goal": "test task",
        "taskType": "edit",
        "editableFiles": ["src/code.py"],
        "validationCommand": ["pytest", "tests/test_code.py", "-v"],
    }
    manifest = manifests_dir / "task-001.manifest.json"
    manifest.write_text(json.dumps(manifest_data))

    active_manifests = [manifest]

    # Build the map
    file_to_manifests = build_file_to_manifests_map(manifests_dir, active_manifests)

    # Get absolute paths for comparison
    project_root = tmp_path
    test_file_abs = (project_root / "tests" / "test_code.py").resolve()

    # Should include test files
    assert test_file_abs in file_to_manifests
    assert manifest in file_to_manifests[test_file_abs]


def test_multi_manifest_file_change_handler_instantiation(tmp_path: Path):
    """Test that _MultiManifestFileChangeHandler can be instantiated."""
    from maid_runner.cli.test import _MultiManifestFileChangeHandler

    manifests_dir = tmp_path / "manifests"
    manifests_dir.mkdir()

    manifest = manifests_dir / "task-001.manifest.json"
    manifest_data = {
        "version": "1",
        "goal": "test",
        "taskType": "edit",
        "editableFiles": ["src/file.py"],
        "validationCommand": ["echo", "test"],
    }
    manifest.write_text(json.dumps(manifest_data))

    file_to_manifests = {"src/file.py": [manifest]}

    # Create handler
    handler = _MultiManifestFileChangeHandler(
        file_to_manifests=file_to_manifests,
        timeout=300,
        verbose=False,
        quiet=False,
        project_root=tmp_path,
    )

    # Should be instantiated
    assert handler is not None
    assert hasattr(handler, "on_modified")


def test_multi_manifest_file_change_handler_on_modified_method(tmp_path: Path):
    """Test that _MultiManifestFileChangeHandler.on_modified() method exists and is callable."""
    from maid_runner.cli.test import _MultiManifestFileChangeHandler

    manifests_dir = tmp_path / "manifests"
    manifests_dir.mkdir()

    manifest = manifests_dir / "task-001.manifest.json"
    manifest_data = {
        "version": "1",
        "goal": "test",
        "taskType": "edit",
        "editableFiles": ["src/file.py"],
        "validationCommand": ["echo", "test"],
    }
    manifest.write_text(json.dumps(manifest_data))

    file_to_manifests = {"src/file.py": [manifest]}

    handler = _MultiManifestFileChangeHandler(
        file_to_manifests=file_to_manifests,
        timeout=300,
        verbose=False,
        quiet=False,
        project_root=tmp_path,
    )

    # on_modified should be callable
    assert callable(handler.on_modified)


def test_multi_manifest_file_change_handler_runs_affected_manifests(tmp_path: Path):
    """Test that _MultiManifestFileChangeHandler only runs validation for affected manifests."""
    from maid_runner.cli.test import _MultiManifestFileChangeHandler

    manifests_dir = tmp_path / "manifests"
    manifests_dir.mkdir()

    # Create two manifests
    manifest1_data = {
        "version": "1",
        "goal": "task 1",
        "taskType": "edit",
        "editableFiles": ["src/file1.py"],
        "validationCommand": ["echo", "test1"],
    }
    manifest1 = manifests_dir / "task-001.manifest.json"
    manifest1.write_text(json.dumps(manifest1_data))

    manifest2_data = {
        "version": "1",
        "goal": "task 2",
        "taskType": "edit",
        "editableFiles": ["src/file2.py"],
        "validationCommand": ["echo", "test2"],
    }
    manifest2 = manifests_dir / "task-002.manifest.json"
    manifest2.write_text(json.dumps(manifest2_data))

    # Use absolute paths as keys (matching new implementation)
    project_root = tmp_path
    file1_abs = (project_root / "src" / "file1.py").resolve()
    file2_abs = (project_root / "src" / "file2.py").resolve()

    file_to_manifests = {
        file1_abs: [manifest1],
        file2_abs: [manifest2],
    }

    # Mock execute_validation_commands
    with patch("maid_runner.cli.test.execute_validation_commands") as mock_execute:
        mock_execute.return_value = (1, 0, 1)

        handler = _MultiManifestFileChangeHandler(
            file_to_manifests=file_to_manifests,
            timeout=300,
            verbose=False,
            quiet=False,
            project_root=tmp_path,
        )

        # Create a mock file change event for file1.py
        mock_event = MagicMock()
        mock_event.is_directory = False
        mock_event.src_path = str(tmp_path / "src" / "file1.py")

        # Trigger the handler
        handler.on_modified(mock_event)

        # Should have called execute_validation_commands for manifest1 only
        assert mock_execute.called
        # Get the manifest_path argument from the call
        call_args = mock_execute.call_args
        manifest_path_arg = (
            call_args.args[0]
            if call_args.args
            else call_args.kwargs.get("manifest_path")
        )
        assert manifest_path_arg == manifest1


def test_multi_manifest_file_change_handler_debouncing(tmp_path: Path):
    """Test that _MultiManifestFileChangeHandler implements debouncing to avoid rapid re-runs."""
    from maid_runner.cli.test import _MultiManifestFileChangeHandler

    manifests_dir = tmp_path / "manifests"
    manifests_dir.mkdir()

    manifest = manifests_dir / "task-001.manifest.json"
    manifest_data = {
        "version": "1",
        "goal": "test",
        "taskType": "edit",
        "editableFiles": ["src/file.py"],
        "validationCommand": ["echo", "test"],
    }
    manifest.write_text(json.dumps(manifest_data))

    file_to_manifests = {"src/file.py": [manifest]}

    with patch("maid_runner.cli.test.execute_validation_commands") as mock_execute:
        mock_execute.return_value = (1, 0, 1)

        handler = _MultiManifestFileChangeHandler(
            file_to_manifests=file_to_manifests,
            timeout=300,
            verbose=False,
            quiet=False,
            project_root=tmp_path,
        )

        # Simulate rapid file changes
        mock_event = MagicMock()
        mock_event.is_directory = False
        mock_event.src_path = str(tmp_path / "src" / "file.py")

        # First change - should trigger
        handler.on_modified(mock_event)
        first_call_count = mock_execute.call_count

        # Immediate second change - should be debounced (not trigger)
        handler.on_modified(mock_event)
        second_call_count = mock_execute.call_count

        # Should only have been called once (debounced)
        assert second_call_count == first_call_count


def test_watch_all_manifests_function_signature():
    """Test that watch_all_manifests() has the correct function signature."""
    from maid_runner.cli.test import watch_all_manifests
    import inspect

    sig = inspect.signature(watch_all_manifests)

    # Verify all expected parameters exist
    expected_params = [
        "manifests_dir",
        "active_manifests",
        "timeout",
        "verbose",
        "quiet",
        "project_root",
        "debounce_seconds",
    ]

    for param in expected_params:
        assert (
            param in sig.parameters
        ), f"Parameter '{param}' missing from watch_all_manifests()"

    # Verify type annotations
    assert sig.parameters["manifests_dir"].annotation == Path
    # Check for List[Path] annotation (handle both typing.List and list)
    assert "List" in str(
        sig.parameters["active_manifests"].annotation
    ) and "Path" in str(sig.parameters["active_manifests"].annotation)
    assert sig.parameters["timeout"].annotation is int
    assert sig.parameters["verbose"].annotation is bool
    assert sig.parameters["quiet"].annotation is bool
    assert sig.parameters["project_root"].annotation == Path
    assert sig.parameters["debounce_seconds"].annotation is float

    # Verify return type
    assert sig.return_annotation is None


def test_watch_all_manifests_setup_and_initial_validation(tmp_path: Path):
    """Test that watch_all_manifests() sets up watching and runs initial validation."""
    from maid_runner.cli.test import watch_all_manifests

    manifests_dir = tmp_path / "manifests"
    manifests_dir.mkdir()

    # Create test manifests
    manifest1_data = {
        "version": "1",
        "goal": "task 1",
        "taskType": "edit",
        "editableFiles": ["src/file1.py"],
        "validationCommand": ["echo", "test1"],
    }
    manifest1 = manifests_dir / "task-001.manifest.json"
    manifest1.write_text(json.dumps(manifest1_data))

    manifest2_data = {
        "version": "1",
        "goal": "task 2",
        "taskType": "edit",
        "editableFiles": ["src/file2.py"],
        "validationCommand": ["echo", "test2"],
    }
    manifest2 = manifests_dir / "task-002.manifest.json"
    manifest2.write_text(json.dumps(manifest2_data))

    active_manifests = [manifest1, manifest2]

    # Mock execute_validation_commands and Observer
    with patch("maid_runner.cli.test.execute_validation_commands") as mock_execute:
        mock_execute.return_value = (1, 0, 1)

        with patch("maid_runner.cli.test.Observer") as mock_observer_class:
            mock_observer = MagicMock()
            mock_observer_class.return_value = mock_observer
            mock_observer.start.side_effect = KeyboardInterrupt()

            watch_all_manifests(
                manifests_dir=manifests_dir,
                active_manifests=active_manifests,
                timeout=300,
                verbose=False,
                quiet=False,
                project_root=tmp_path,
                debounce_seconds=2.0,
            )

            # Should have run initial validation for all active manifests
            assert mock_execute.call_count == 2  # Once for each manifest

            # Should have created an observer
            mock_observer_class.assert_called_once()

            # Should have started the observer
            mock_observer.start.assert_called_once()


def test_watch_all_manifests_file_watching_setup(tmp_path: Path):
    """Test that watch_all_manifests() sets up file watching for all watchable files."""
    from maid_runner.cli.test import watch_all_manifests

    manifests_dir = tmp_path / "manifests"
    manifests_dir.mkdir()

    manifest_data = {
        "version": "1",
        "goal": "test",
        "taskType": "edit",
        "editableFiles": ["src/file1.py", "src/subdir/file2.py"],
        "validationCommand": ["echo", "test"],
    }
    manifest = manifests_dir / "task-001.manifest.json"
    manifest.write_text(json.dumps(manifest_data))

    active_manifests = [manifest]

    with patch("maid_runner.cli.test.execute_validation_commands") as mock_execute:
        mock_execute.return_value = (1, 0, 1)

        with patch("maid_runner.cli.test.Observer") as mock_observer_class:
            mock_observer = MagicMock()
            mock_observer_class.return_value = mock_observer
            mock_observer.start.side_effect = KeyboardInterrupt()

            watch_all_manifests(
                manifests_dir=manifests_dir,
                active_manifests=active_manifests,
                timeout=300,
                verbose=False,
                quiet=False,
                project_root=tmp_path,
                debounce_seconds=2.0,
            )

            # Should have scheduled observers for parent directories
            assert mock_observer.schedule.called


def test_watch_all_manifests_handles_keyboard_interrupt(tmp_path: Path):
    """Test that watch_all_manifests() handles Ctrl+C (KeyboardInterrupt) gracefully."""
    from maid_runner.cli.test import watch_all_manifests

    manifests_dir = tmp_path / "manifests"
    manifests_dir.mkdir()

    manifest_data = {
        "version": "1",
        "goal": "test",
        "taskType": "edit",
        "editableFiles": ["src/file.py"],
        "validationCommand": ["echo", "test"],
    }
    manifest = manifests_dir / "task-001.manifest.json"
    manifest.write_text(json.dumps(manifest_data))

    active_manifests = [manifest]

    with patch("maid_runner.cli.test.execute_validation_commands") as mock_execute:
        mock_execute.return_value = (1, 0, 1)

        with patch("maid_runner.cli.test.Observer") as mock_observer_class:
            mock_observer = MagicMock()
            mock_observer_class.return_value = mock_observer
            mock_observer.start.side_effect = KeyboardInterrupt()

            # Should not raise - should handle gracefully
            watch_all_manifests(
                manifests_dir=manifests_dir,
                active_manifests=active_manifests,
                timeout=300,
                verbose=False,
                quiet=False,
                project_root=tmp_path,
                debounce_seconds=2.0,
            )

            # Should have stopped the observer
            mock_observer.stop.assert_called_once()


def test_watch_all_manifests_passes_debounce_seconds(tmp_path: Path):
    """Test that watch_all_manifests() passes debounce_seconds to the handler."""
    from maid_runner.cli.test import watch_all_manifests

    manifests_dir = tmp_path / "manifests"
    manifests_dir.mkdir()

    manifest_data = {
        "version": "1",
        "goal": "test",
        "taskType": "edit",
        "editableFiles": ["src/file.py"],
        "validationCommand": ["echo", "test"],
    }
    manifest = manifests_dir / "task-001.manifest.json"
    manifest.write_text(json.dumps(manifest_data))

    active_manifests = [manifest]
    custom_debounce = 5.0

    with patch("maid_runner.cli.test.execute_validation_commands") as mock_execute:
        mock_execute.return_value = (1, 0, 1)

        with patch("maid_runner.cli.test.Observer") as mock_observer_class:
            mock_observer = MagicMock()
            mock_observer_class.return_value = mock_observer
            mock_observer.start.side_effect = KeyboardInterrupt()

            with patch(
                "maid_runner.cli.test._MultiManifestFileChangeHandler"
            ) as mock_handler_class:
                mock_handler = MagicMock()
                mock_handler_class.return_value = mock_handler

                watch_all_manifests(
                    manifests_dir=manifests_dir,
                    active_manifests=active_manifests,
                    timeout=300,
                    verbose=False,
                    quiet=False,
                    project_root=tmp_path,
                    debounce_seconds=custom_debounce,
                )

                # Handler should have debounce_seconds set
                assert mock_handler.debounce_seconds == custom_debounce


def test_run_test_with_watch_and_no_manifest_path_calls_watch_all_manifests(
    tmp_path: Path,
):
    """Test that run_test() with watch_all=True calls watch_all_manifests()."""
    from maid_runner.cli.test import run_test

    manifests_dir = tmp_path / "manifests"
    manifests_dir.mkdir()

    # Create test manifests
    manifest1_data = {
        "version": "1",
        "goal": "task 1",
        "taskType": "edit",
        "editableFiles": ["src/file1.py"],
        "validationCommand": ["echo", "test1"],
    }
    manifest1 = manifests_dir / "task-001.manifest.json"
    manifest1.write_text(json.dumps(manifest1_data))

    manifest2_data = {
        "version": "1",
        "goal": "task 2",
        "taskType": "edit",
        "editableFiles": ["src/file2.py"],
        "validationCommand": ["echo", "test2"],
    }
    manifest2 = manifests_dir / "task-002.manifest.json"
    manifest2.write_text(json.dumps(manifest2_data))

    # Mock watch_all_manifests
    with patch("maid_runner.cli.test.watch_all_manifests") as mock_watch_all:
        # Should exit normally after watch_all_manifests returns
        with pytest.raises(SystemExit):
            run_test(
                manifest_dir=str(manifests_dir),
                fail_fast=False,
                verbose=False,
                quiet=False,
                timeout=300,
                manifest_path=None,  # No specific manifest
                watch=False,  # Single-manifest watch disabled
                watch_all=True,  # Multi-manifest watch enabled
            )

        # Should have called watch_all_manifests
        assert mock_watch_all.called

        # Get the call arguments
        call_args = mock_watch_all.call_args

        # Should have passed manifests_dir
        assert "manifests_dir" in call_args.kwargs or len(call_args.args) >= 1

        # Should have passed active_manifests
        assert "active_manifests" in call_args.kwargs or len(call_args.args) >= 2

        # Should have passed debounce_seconds
        assert "debounce_seconds" in call_args.kwargs or len(call_args.args) >= 7


def test_run_test_single_manifest_watch_still_works(tmp_path: Path):
    """Test that existing single-manifest watch mode still works with watch=True and manifest_path specified."""
    from maid_runner.cli.test import run_test

    manifests_dir = tmp_path / "manifests"
    manifests_dir.mkdir()

    manifest_data = {
        "version": "1",
        "goal": "test",
        "taskType": "edit",
        "editableFiles": ["src/file.py"],
        "validationCommand": ["echo", "test"],
    }
    manifest = manifests_dir / "task-001.manifest.json"
    manifest.write_text(json.dumps(manifest_data))

    # Mock watch_manifest (single-manifest watch)
    with patch("maid_runner.cli.test.watch_manifest") as mock_watch_single:
        # Should exit normally after watch_manifest returns
        with pytest.raises(SystemExit):
            run_test(
                manifest_dir=str(manifests_dir),
                fail_fast=False,
                verbose=False,
                quiet=False,
                timeout=300,
                manifest_path="task-001.manifest.json",  # Specific manifest
                watch=True,  # Watch mode enabled
            )

        # Should have called watch_manifest (not watch_all_manifests)
        assert mock_watch_single.called


def test_watch_all_manifests_with_no_watchable_files(tmp_path: Path):
    """Test that watch_all_manifests() handles manifests with no watchable files."""
    from maid_runner.cli.test import watch_all_manifests

    manifests_dir = tmp_path / "manifests"
    manifests_dir.mkdir()

    # Manifest with only readonly files
    manifest_data = {
        "version": "1",
        "goal": "test",
        "taskType": "edit",
        "readonlyFiles": ["README.md"],
        "validationCommand": ["echo", "test"],
    }
    manifest = manifests_dir / "task-001.manifest.json"
    manifest.write_text(json.dumps(manifest_data))

    active_manifests = [manifest]

    with patch("maid_runner.cli.test.execute_validation_commands") as mock_execute:
        mock_execute.return_value = (1, 0, 1)

        with patch("maid_runner.cli.test.Observer") as mock_observer_class:
            mock_observer = MagicMock()
            mock_observer_class.return_value = mock_observer
            mock_observer.start.side_effect = KeyboardInterrupt()

            # Should handle gracefully
            watch_all_manifests(
                manifests_dir=manifests_dir,
                active_manifests=active_manifests,
                timeout=300,
                verbose=False,
                quiet=False,
                project_root=tmp_path,
                debounce_seconds=2.0,
            )

            # Should still run initial validation
            assert mock_execute.called


def test_watch_all_manifests_with_shared_and_unique_files(tmp_path: Path):
    """Test watch_all_manifests() with a mix of shared files and unique files across manifests."""
    from maid_runner.cli.test import watch_all_manifests

    manifests_dir = tmp_path / "manifests"
    manifests_dir.mkdir()

    # Manifest 1: edits shared.py and unique1.py
    manifest1_data = {
        "version": "1",
        "goal": "task 1",
        "taskType": "edit",
        "editableFiles": ["src/shared.py", "src/unique1.py"],
        "validationCommand": ["echo", "test1"],
    }
    manifest1 = manifests_dir / "task-001.manifest.json"
    manifest1.write_text(json.dumps(manifest1_data))

    # Manifest 2: edits shared.py and unique2.py
    manifest2_data = {
        "version": "1",
        "goal": "task 2",
        "taskType": "edit",
        "editableFiles": ["src/shared.py", "src/unique2.py"],
        "validationCommand": ["echo", "test2"],
    }
    manifest2 = manifests_dir / "task-002.manifest.json"
    manifest2.write_text(json.dumps(manifest2_data))

    active_manifests = [manifest1, manifest2]

    with patch("maid_runner.cli.test.execute_validation_commands") as mock_execute:
        mock_execute.return_value = (1, 0, 1)

        with patch("maid_runner.cli.test.Observer") as mock_observer_class:
            mock_observer = MagicMock()
            mock_observer_class.return_value = mock_observer
            mock_observer.start.side_effect = KeyboardInterrupt()

            watch_all_manifests(
                manifests_dir=manifests_dir,
                active_manifests=active_manifests,
                timeout=300,
                verbose=False,
                quiet=False,
                project_root=tmp_path,
                debounce_seconds=2.0,
            )

            # Should set up file watching
            assert mock_observer.schedule.called
            # Should run initial validation for both manifests
            assert mock_execute.call_count == 2


def test_multi_manifest_handler_runs_multiple_manifests_for_shared_file(tmp_path: Path):
    """Test that changing a shared file triggers validation for all manifests that reference it."""
    from maid_runner.cli.test import _MultiManifestFileChangeHandler

    manifests_dir = tmp_path / "manifests"
    manifests_dir.mkdir()

    # Create two manifests that both edit shared.py
    manifest1_data = {
        "version": "1",
        "goal": "task 1",
        "taskType": "edit",
        "editableFiles": ["src/shared.py"],
        "validationCommand": ["echo", "test1"],
    }
    manifest1 = manifests_dir / "task-001.manifest.json"
    manifest1.write_text(json.dumps(manifest1_data))

    manifest2_data = {
        "version": "1",
        "goal": "task 2",
        "taskType": "edit",
        "editableFiles": ["src/shared.py"],
        "validationCommand": ["echo", "test2"],
    }
    manifest2 = manifests_dir / "task-002.manifest.json"
    manifest2.write_text(json.dumps(manifest2_data))

    # Use absolute paths as keys (matching new implementation)
    project_root = tmp_path
    shared_file_abs = (project_root / "src" / "shared.py").resolve()

    file_to_manifests = {shared_file_abs: [manifest1, manifest2]}

    with patch("maid_runner.cli.test.execute_validation_commands") as mock_execute:
        mock_execute.return_value = (1, 0, 1)

        handler = _MultiManifestFileChangeHandler(
            file_to_manifests=file_to_manifests,
            timeout=300,
            verbose=False,
            quiet=False,
            project_root=tmp_path,
        )

        # Create a mock file change event for shared.py
        mock_event = MagicMock()
        mock_event.is_directory = False
        mock_event.src_path = str(tmp_path / "src" / "shared.py")

        # Trigger the handler
        handler.on_modified(mock_event)

        # Should have called execute_validation_commands for BOTH manifests
        assert mock_execute.call_count == 2

        # Check that both manifests were called
        call_args_list = mock_execute.call_args_list
        manifests_called = []
        for call_args in call_args_list:
            manifest_path = (
                call_args.args[0]
                if call_args.args
                else call_args.kwargs.get("manifest_path")
            )
            manifests_called.append(manifest_path)

        assert manifest1 in manifests_called
        assert manifest2 in manifests_called


def test_build_file_to_manifests_map_function_signature():
    """Test that build_file_to_manifests_map() has the correct function signature."""
    from maid_runner.cli.test import build_file_to_manifests_map
    import inspect

    sig = inspect.signature(build_file_to_manifests_map)

    # Verify parameters
    assert "manifests_dir" in sig.parameters
    assert "active_manifests" in sig.parameters

    # Verify type annotations
    assert sig.parameters["manifests_dir"].annotation == Path
    # Check for List[Path] annotation (handle both typing.List and list)
    assert "List" in str(
        sig.parameters["active_manifests"].annotation
    ) and "Path" in str(sig.parameters["active_manifests"].annotation)

    # Verify return type
    assert sig.return_annotation is dict


def test_run_test_function_signature_includes_watch_all():
    """Test that run_test() function signature includes watch_all parameter."""
    from maid_runner.cli.test import run_test
    import inspect

    sig = inspect.signature(run_test)

    # Verify watch_all parameter exists
    assert "watch_all" in sig.parameters, "Parameter watch_all missing from run_test()"

    # Verify type annotation
    assert sig.parameters["watch_all"].annotation is bool
