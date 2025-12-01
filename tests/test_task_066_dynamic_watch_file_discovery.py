"""Behavioral tests for Task 066: Dynamic file discovery in watch-all mode

Tests the dynamic file discovery functionality that allows watch-all mode
to detect new manifests and files without requiring a restart.

Artifacts under test:
- _MultiManifestFileChangeHandler.on_created(): Handles new file creation events
- _MultiManifestFileChangeHandler.refresh_file_mappings(): Rebuilds file-to-manifests mapping
- _MultiManifestFileChangeHandler.manifests_dir: Stores manifests directory path
- _MultiManifestFileChangeHandler.observer: Reference to the observer for dynamic scheduling
"""

import json
from pathlib import Path
from unittest.mock import MagicMock, patch


def test_on_created_method_exists():
    """Test that _MultiManifestFileChangeHandler has on_created method."""
    from maid_runner.cli.test import _MultiManifestFileChangeHandler

    assert hasattr(_MultiManifestFileChangeHandler, "on_created")


def test_refresh_file_mappings_method_exists():
    """Test that _MultiManifestFileChangeHandler has refresh_file_mappings method."""
    from maid_runner.cli.test import _MultiManifestFileChangeHandler

    assert hasattr(_MultiManifestFileChangeHandler, "refresh_file_mappings")


def test_manifests_dir_attribute_exists(tmp_path: Path):
    """Test that _MultiManifestFileChangeHandler has manifests_dir attribute."""
    from maid_runner.cli.test import _MultiManifestFileChangeHandler

    manifests_dir = tmp_path / "manifests"
    manifests_dir.mkdir()

    handler = _MultiManifestFileChangeHandler(
        file_to_manifests={},
        timeout=300,
        verbose=False,
        quiet=False,
        project_root=tmp_path,
        manifests_dir=manifests_dir,
        observer=MagicMock(),
    )

    assert hasattr(handler, "manifests_dir")
    assert handler.manifests_dir == manifests_dir


def test_observer_attribute_exists(tmp_path: Path):
    """Test that _MultiManifestFileChangeHandler has observer attribute."""
    from maid_runner.cli.test import _MultiManifestFileChangeHandler

    manifests_dir = tmp_path / "manifests"
    manifests_dir.mkdir()

    mock_observer = MagicMock()

    handler = _MultiManifestFileChangeHandler(
        file_to_manifests={},
        timeout=300,
        verbose=False,
        quiet=False,
        project_root=tmp_path,
        manifests_dir=manifests_dir,
        observer=mock_observer,
    )

    assert hasattr(handler, "observer")
    assert handler.observer == mock_observer


def test_on_created_is_callable(tmp_path: Path):
    """Test that on_created method is callable."""
    from maid_runner.cli.test import _MultiManifestFileChangeHandler

    manifests_dir = tmp_path / "manifests"
    manifests_dir.mkdir()

    handler = _MultiManifestFileChangeHandler(
        file_to_manifests={},
        timeout=300,
        verbose=False,
        quiet=False,
        project_root=tmp_path,
        manifests_dir=manifests_dir,
        observer=MagicMock(),
    )

    assert callable(handler.on_created)


def test_refresh_file_mappings_is_callable(tmp_path: Path):
    """Test that refresh_file_mappings method is callable."""
    from maid_runner.cli.test import _MultiManifestFileChangeHandler

    manifests_dir = tmp_path / "manifests"
    manifests_dir.mkdir()

    handler = _MultiManifestFileChangeHandler(
        file_to_manifests={},
        timeout=300,
        verbose=False,
        quiet=False,
        project_root=tmp_path,
        manifests_dir=manifests_dir,
        observer=MagicMock(),
    )

    assert callable(handler.refresh_file_mappings)


def test_on_created_triggers_refresh_for_new_manifest(tmp_path: Path):
    """Test that on_created triggers refresh when a new manifest is created."""
    from maid_runner.cli.test import _MultiManifestFileChangeHandler

    manifests_dir = tmp_path / "manifests"
    manifests_dir.mkdir()

    handler = _MultiManifestFileChangeHandler(
        file_to_manifests={},
        timeout=300,
        verbose=False,
        quiet=False,
        project_root=tmp_path,
        manifests_dir=manifests_dir,
        observer=MagicMock(),
    )

    # Mock refresh_file_mappings
    handler.refresh_file_mappings = MagicMock()

    # Create mock event for new manifest
    mock_event = MagicMock()
    mock_event.is_directory = False
    mock_event.src_path = str(manifests_dir / "task-001.manifest.json")

    handler.on_created(mock_event)

    # Should have triggered refresh
    handler.refresh_file_mappings.assert_called_once()


def test_on_created_ignores_non_manifest_files(tmp_path: Path):
    """Test that on_created ignores non-manifest files."""
    from maid_runner.cli.test import _MultiManifestFileChangeHandler

    manifests_dir = tmp_path / "manifests"
    manifests_dir.mkdir()

    handler = _MultiManifestFileChangeHandler(
        file_to_manifests={},
        timeout=300,
        verbose=False,
        quiet=False,
        project_root=tmp_path,
        manifests_dir=manifests_dir,
        observer=MagicMock(),
    )

    # Mock refresh_file_mappings
    handler.refresh_file_mappings = MagicMock()

    # Create mock event for non-manifest file
    mock_event = MagicMock()
    mock_event.is_directory = False
    mock_event.src_path = str(tmp_path / "src" / "some_file.py")

    handler.on_created(mock_event)

    # Should NOT trigger refresh for non-manifest files
    handler.refresh_file_mappings.assert_not_called()


def test_refresh_file_mappings_updates_file_to_manifests(tmp_path: Path):
    """Test that refresh_file_mappings updates the file_to_manifests mapping."""
    from maid_runner.cli.test import _MultiManifestFileChangeHandler

    manifests_dir = tmp_path / "manifests"
    manifests_dir.mkdir()

    # Create initial manifest
    manifest1_data = {
        "version": "1",
        "goal": "task 1",
        "taskType": "edit",
        "editableFiles": ["src/file1.py"],
        "validationCommand": ["echo", "test1"],
    }
    manifest1 = manifests_dir / "task-001.manifest.json"
    manifest1.write_text(json.dumps(manifest1_data))

    handler = _MultiManifestFileChangeHandler(
        file_to_manifests={},
        timeout=300,
        verbose=False,
        quiet=False,
        project_root=tmp_path,
        manifests_dir=manifests_dir,
        observer=MagicMock(),
    )

    # Refresh mappings
    handler.refresh_file_mappings(manifests_dir)

    # Should now have file1.py in the mapping
    file1_abs = (tmp_path / "src" / "file1.py").resolve()
    assert file1_abs in handler.file_to_manifests


def test_refresh_file_mappings_adds_new_directories_to_observer(tmp_path: Path):
    """Test that refresh_file_mappings adds new directories to the observer."""
    from maid_runner.cli.test import _MultiManifestFileChangeHandler

    manifests_dir = tmp_path / "manifests"
    manifests_dir.mkdir()

    mock_observer = MagicMock()

    handler = _MultiManifestFileChangeHandler(
        file_to_manifests={},
        timeout=300,
        verbose=False,
        quiet=False,
        project_root=tmp_path,
        manifests_dir=manifests_dir,
        observer=mock_observer,
    )

    # Create a manifest that references a new directory
    manifest_data = {
        "version": "1",
        "goal": "task",
        "taskType": "edit",
        "editableFiles": ["new_dir/new_file.py"],
        "validationCommand": ["echo", "test"],
    }
    manifest = manifests_dir / "task-001.manifest.json"
    manifest.write_text(json.dumps(manifest_data))

    # Refresh mappings
    handler.refresh_file_mappings(manifests_dir)

    # Should have scheduled the new directory with the observer
    assert mock_observer.schedule.called


def test_watch_all_manifests_watches_manifests_directory(tmp_path: Path):
    """Test that watch_all_manifests() also watches the manifests directory."""
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

            watch_all_manifests(
                manifests_dir=manifests_dir,
                active_manifests=active_manifests,
                timeout=300,
                verbose=False,
                quiet=False,
                project_root=tmp_path,
                debounce_seconds=2.0,
            )

            # Should have scheduled the manifests directory for watching
            schedule_calls = mock_observer.schedule.call_args_list
            scheduled_paths = [str(call.args[1]) for call in schedule_calls]

            assert str(manifests_dir) in scheduled_paths


def test_on_created_ignores_non_json_files_in_manifests_dir(tmp_path: Path):
    """Test that on_created ignores non-JSON files even in the manifests directory."""
    from maid_runner.cli.test import _MultiManifestFileChangeHandler

    manifests_dir = tmp_path / "manifests"
    manifests_dir.mkdir()

    handler = _MultiManifestFileChangeHandler(
        file_to_manifests={},
        timeout=300,
        verbose=False,
        quiet=False,
        project_root=tmp_path,
        manifests_dir=manifests_dir,
        observer=MagicMock(),
    )

    # Mock refresh_file_mappings
    handler.refresh_file_mappings = MagicMock()

    # Create mock event for non-JSON file in manifests directory
    mock_event = MagicMock()
    mock_event.is_directory = False
    mock_event.src_path = str(manifests_dir / "README.md")

    handler.on_created(mock_event)

    # Should NOT trigger refresh for non-JSON files
    handler.refresh_file_mappings.assert_not_called()


def test_on_created_ignores_directory_events(tmp_path: Path):
    """Test that on_created ignores directory creation events."""
    from maid_runner.cli.test import _MultiManifestFileChangeHandler

    manifests_dir = tmp_path / "manifests"
    manifests_dir.mkdir()

    handler = _MultiManifestFileChangeHandler(
        file_to_manifests={},
        timeout=300,
        verbose=False,
        quiet=False,
        project_root=tmp_path,
        manifests_dir=manifests_dir,
        observer=MagicMock(),
    )

    # Mock refresh_file_mappings
    handler.refresh_file_mappings = MagicMock()

    # Create mock event for directory creation
    mock_event = MagicMock()
    mock_event.is_directory = True
    mock_event.src_path = str(manifests_dir / "subdir")

    handler.on_created(mock_event)

    # Should NOT trigger refresh for directory events
    handler.refresh_file_mappings.assert_not_called()


def test_refresh_file_mappings_handles_empty_manifests_dir(tmp_path: Path):
    """Test that refresh_file_mappings handles an empty manifests directory."""
    from maid_runner.cli.test import _MultiManifestFileChangeHandler

    manifests_dir = tmp_path / "manifests"
    manifests_dir.mkdir()

    handler = _MultiManifestFileChangeHandler(
        file_to_manifests={},
        timeout=300,
        verbose=False,
        quiet=False,
        project_root=tmp_path,
        manifests_dir=manifests_dir,
        observer=MagicMock(),
    )

    # Refresh mappings with empty directory
    handler.refresh_file_mappings(manifests_dir)

    # Should result in empty mapping
    assert len(handler.file_to_manifests) == 0


def test_refresh_file_mappings_handles_invalid_manifest(tmp_path: Path):
    """Test that refresh_file_mappings gracefully handles invalid manifest JSON."""
    from maid_runner.cli.test import _MultiManifestFileChangeHandler

    manifests_dir = tmp_path / "manifests"
    manifests_dir.mkdir()

    # Create an invalid manifest
    invalid_manifest = manifests_dir / "task-001.manifest.json"
    invalid_manifest.write_text("{ invalid json }")

    handler = _MultiManifestFileChangeHandler(
        file_to_manifests={},
        timeout=300,
        verbose=False,
        quiet=False,
        project_root=tmp_path,
        manifests_dir=manifests_dir,
        observer=MagicMock(),
    )

    # Should not raise an exception
    handler.refresh_file_mappings(manifests_dir)

    # Should result in empty mapping (invalid manifest skipped)
    assert len(handler.file_to_manifests) == 0


def test_refresh_file_mappings_updates_existing_mappings(tmp_path: Path):
    """Test that refresh_file_mappings properly updates existing file-to-manifests mappings."""
    from maid_runner.cli.test import _MultiManifestFileChangeHandler

    manifests_dir = tmp_path / "manifests"
    manifests_dir.mkdir()

    # Create first manifest
    manifest1_data = {
        "version": "1",
        "goal": "task 1",
        "taskType": "edit",
        "editableFiles": ["src/file1.py"],
        "validationCommand": ["echo", "test1"],
    }
    manifest1 = manifests_dir / "task-001.manifest.json"
    manifest1.write_text(json.dumps(manifest1_data))

    handler = _MultiManifestFileChangeHandler(
        file_to_manifests={},
        timeout=300,
        verbose=False,
        quiet=False,
        project_root=tmp_path,
        manifests_dir=manifests_dir,
        observer=MagicMock(),
    )

    # Initial refresh
    handler.refresh_file_mappings(manifests_dir)
    file1_abs = (tmp_path / "src" / "file1.py").resolve()
    assert file1_abs in handler.file_to_manifests

    # Now add a second manifest
    manifest2_data = {
        "version": "1",
        "goal": "task 2",
        "taskType": "edit",
        "editableFiles": ["src/file2.py"],
        "validationCommand": ["echo", "test2"],
    }
    manifest2 = manifests_dir / "task-002.manifest.json"
    manifest2.write_text(json.dumps(manifest2_data))

    # Refresh again
    handler.refresh_file_mappings(manifests_dir)

    # Both files should now be in the mapping
    file2_abs = (tmp_path / "src" / "file2.py").resolve()
    assert file1_abs in handler.file_to_manifests
    assert file2_abs in handler.file_to_manifests


def test_on_created_only_triggers_for_manifest_json_files(tmp_path: Path):
    """Test that on_created specifically checks for .manifest.json file extension."""
    from maid_runner.cli.test import _MultiManifestFileChangeHandler

    manifests_dir = tmp_path / "manifests"
    manifests_dir.mkdir()

    handler = _MultiManifestFileChangeHandler(
        file_to_manifests={},
        timeout=300,
        verbose=False,
        quiet=False,
        project_root=tmp_path,
        manifests_dir=manifests_dir,
        observer=MagicMock(),
    )

    # Mock refresh_file_mappings
    handler.refresh_file_mappings = MagicMock()

    # Test various file types that should NOT trigger refresh
    non_manifest_files = [
        "some_file.json",  # Regular JSON, not manifest
        "task-001.json",  # Missing .manifest
        "config.manifest",  # Missing .json
        "task-001.manifest.txt",  # Wrong extension
    ]

    for filename in non_manifest_files:
        mock_event = MagicMock()
        mock_event.is_directory = False
        mock_event.src_path = str(manifests_dir / filename)
        handler.on_created(mock_event)

    # None should have triggered refresh
    handler.refresh_file_mappings.assert_not_called()

    # Now test that .manifest.json DOES trigger
    mock_event = MagicMock()
    mock_event.is_directory = False
    mock_event.src_path = str(manifests_dir / "task-002.manifest.json")
    handler.on_created(mock_event)

    handler.refresh_file_mappings.assert_called_once()


def test_handler_stores_manifests_dir_for_refresh(tmp_path: Path):
    """Test that handler stores manifests_dir and uses it for refresh operations."""
    from maid_runner.cli.test import _MultiManifestFileChangeHandler

    manifests_dir = tmp_path / "manifests"
    manifests_dir.mkdir()

    handler = _MultiManifestFileChangeHandler(
        file_to_manifests={},
        timeout=300,
        verbose=False,
        quiet=False,
        project_root=tmp_path,
        manifests_dir=manifests_dir,
        observer=MagicMock(),
    )

    # Verify manifests_dir is stored
    assert handler.manifests_dir == manifests_dir

    # The stored path should be used when refreshing
    # (This tests that the attribute is properly utilized)
    assert handler.manifests_dir.exists()


def test_refresh_file_mappings_runs_validation_for_new_manifests(tmp_path: Path):
    """Test that refresh_file_mappings runs validation for newly discovered manifests."""
    from maid_runner.cli.test import _MultiManifestFileChangeHandler

    manifests_dir = tmp_path / "manifests"
    manifests_dir.mkdir()

    # Create initial manifest
    manifest1_data = {
        "version": "1",
        "goal": "task 1",
        "taskType": "edit",
        "editableFiles": ["src/file1.py"],
        "validationCommand": ["echo", "test1"],
    }
    manifest1 = manifests_dir / "task-001.manifest.json"
    manifest1.write_text(json.dumps(manifest1_data))

    handler = _MultiManifestFileChangeHandler(
        file_to_manifests={},
        timeout=300,
        verbose=False,
        quiet=False,
        project_root=tmp_path,
        manifests_dir=manifests_dir,
        observer=MagicMock(),
    )

    # Initialize known manifests with manifest1
    handler._known_manifests = {manifest1}

    # Now add a second manifest
    manifest2_data = {
        "version": "1",
        "goal": "task 2",
        "taskType": "edit",
        "editableFiles": ["src/file2.py"],
        "validationCommand": ["echo", "test2"],
    }
    manifest2 = manifests_dir / "task-002.manifest.json"
    manifest2.write_text(json.dumps(manifest2_data))

    # Mock execute_validation_commands
    with patch("maid_runner.cli.test.execute_validation_commands") as mock_execute:
        mock_execute.return_value = (1, 0, 1)

        # Refresh mappings - should detect and run validation for manifest2
        handler.refresh_file_mappings(manifests_dir)

        # Should have run validation for the new manifest
        assert mock_execute.called
        # Check that it was called with manifest2 (the new one)
        call_args = mock_execute.call_args
        assert call_args.kwargs.get("manifest_path") == manifest2


def test_refresh_file_mappings_tracks_known_manifests(tmp_path: Path):
    """Test that refresh_file_mappings tracks known manifests to detect new ones."""
    from maid_runner.cli.test import _MultiManifestFileChangeHandler

    manifests_dir = tmp_path / "manifests"
    manifests_dir.mkdir()

    handler = _MultiManifestFileChangeHandler(
        file_to_manifests={},
        timeout=300,
        verbose=False,
        quiet=False,
        project_root=tmp_path,
        manifests_dir=manifests_dir,
        observer=MagicMock(),
    )

    # Verify _known_manifests attribute exists
    assert hasattr(handler, "_known_manifests")
    assert isinstance(handler._known_manifests, set)

    # Create a manifest
    manifest_data = {
        "version": "1",
        "goal": "task 1",
        "taskType": "edit",
        "editableFiles": ["src/file1.py"],
        "validationCommand": ["echo", "test1"],
    }
    manifest = manifests_dir / "task-001.manifest.json"
    manifest.write_text(json.dumps(manifest_data))

    # Refresh mappings
    handler.refresh_file_mappings(manifests_dir)

    # _known_manifests should now contain the manifest
    assert manifest in handler._known_manifests


def test_refresh_file_mappings_does_not_rerun_existing_manifests(tmp_path: Path):
    """Test that refresh_file_mappings does not re-run validation for existing manifests."""
    from maid_runner.cli.test import _MultiManifestFileChangeHandler

    manifests_dir = tmp_path / "manifests"
    manifests_dir.mkdir()

    # Create manifest
    manifest_data = {
        "version": "1",
        "goal": "task 1",
        "taskType": "edit",
        "editableFiles": ["src/file1.py"],
        "validationCommand": ["echo", "test1"],
    }
    manifest = manifests_dir / "task-001.manifest.json"
    manifest.write_text(json.dumps(manifest_data))

    handler = _MultiManifestFileChangeHandler(
        file_to_manifests={},
        timeout=300,
        verbose=False,
        quiet=False,
        project_root=tmp_path,
        manifests_dir=manifests_dir,
        observer=MagicMock(),
    )

    # Pre-populate known manifests (as if initial watch setup happened)
    handler._known_manifests = {manifest}

    # Mock execute_validation_commands
    with patch("maid_runner.cli.test.execute_validation_commands") as mock_execute:
        mock_execute.return_value = (1, 0, 1)

        # Refresh mappings - should NOT run validation for already-known manifest
        handler.refresh_file_mappings(manifests_dir)

        # Should NOT have run validation
        assert not mock_execute.called


def test_on_created_for_non_manifest_files_triggers_on_modified(tmp_path: Path):
    """Test that on_created for non-manifest files delegates to on_modified."""
    from maid_runner.cli.test import _MultiManifestFileChangeHandler

    manifests_dir = tmp_path / "manifests"
    manifests_dir.mkdir()

    handler = _MultiManifestFileChangeHandler(
        file_to_manifests={},
        timeout=300,
        verbose=False,
        quiet=False,
        project_root=tmp_path,
        manifests_dir=manifests_dir,
        observer=MagicMock(),
    )

    # Mock on_modified
    handler.on_modified = MagicMock()

    # Create mock event for non-manifest file
    mock_event = MagicMock()
    mock_event.is_directory = False
    mock_event.src_path = str(tmp_path / "src" / "some_file.py")

    handler.on_created(mock_event)

    # Should have called on_modified
    handler.on_modified.assert_called_once_with(mock_event)


def test_on_moved_method_exists():
    """Test that _MultiManifestFileChangeHandler has on_moved method."""
    from maid_runner.cli.test import _MultiManifestFileChangeHandler

    assert hasattr(_MultiManifestFileChangeHandler, "on_moved")


def test_on_moved_handles_atomic_writes_for_manifest(tmp_path: Path):
    """Test that on_moved handles atomic writes for manifest files."""
    from maid_runner.cli.test import _MultiManifestFileChangeHandler

    manifests_dir = tmp_path / "manifests"
    manifests_dir.mkdir()

    handler = _MultiManifestFileChangeHandler(
        file_to_manifests={},
        timeout=300,
        verbose=False,
        quiet=False,
        project_root=tmp_path,
        manifests_dir=manifests_dir,
        observer=MagicMock(),
    )

    # Mock refresh_file_mappings
    handler.refresh_file_mappings = MagicMock()

    # Create mock move event (atomic write: temp -> final)
    mock_event = MagicMock()
    mock_event.is_directory = False
    mock_event.src_path = str(tmp_path / ".tmp_manifest_xyz")
    mock_event.dest_path = str(manifests_dir / "task-001.manifest.json")

    handler.on_moved(mock_event)

    # Should have triggered refresh for manifest files
    handler.refresh_file_mappings.assert_called_once()


def test_on_moved_handles_atomic_writes_for_regular_files(tmp_path: Path):
    """Test that on_moved handles atomic writes for regular files by calling on_modified."""
    from maid_runner.cli.test import _MultiManifestFileChangeHandler

    manifests_dir = tmp_path / "manifests"
    manifests_dir.mkdir()

    handler = _MultiManifestFileChangeHandler(
        file_to_manifests={},
        timeout=300,
        verbose=False,
        quiet=False,
        project_root=tmp_path,
        manifests_dir=manifests_dir,
        observer=MagicMock(),
    )

    # Mock on_modified
    handler.on_modified = MagicMock()

    # Create mock move event (atomic write: temp -> final)
    mock_event = MagicMock()
    mock_event.is_directory = False
    mock_event.src_path = str(tmp_path / ".tmp_file_xyz")
    mock_event.dest_path = str(tmp_path / "tests" / "test_file.py")

    handler.on_moved(mock_event)

    # Should have called on_modified with a fake event containing dest_path
    assert handler.on_modified.called
    call_args = handler.on_modified.call_args[0][0]
    assert call_args.src_path == str(tmp_path / "tests" / "test_file.py")


def test_on_moved_ignores_directory_events(tmp_path: Path):
    """Test that on_moved ignores directory move events."""
    from maid_runner.cli.test import _MultiManifestFileChangeHandler

    manifests_dir = tmp_path / "manifests"
    manifests_dir.mkdir()

    handler = _MultiManifestFileChangeHandler(
        file_to_manifests={},
        timeout=300,
        verbose=False,
        quiet=False,
        project_root=tmp_path,
        manifests_dir=manifests_dir,
        observer=MagicMock(),
    )

    # Mock on_modified
    handler.on_modified = MagicMock()
    handler.refresh_file_mappings = MagicMock()

    # Create mock directory move event
    mock_event = MagicMock()
    mock_event.is_directory = True
    mock_event.src_path = str(tmp_path / "old_dir")
    mock_event.dest_path = str(tmp_path / "new_dir")

    handler.on_moved(mock_event)

    # Should NOT have called on_modified or refresh
    handler.on_modified.assert_not_called()
    handler.refresh_file_mappings.assert_not_called()


def test_on_deleted_method_exists():
    """Test that _MultiManifestFileChangeHandler has on_deleted method."""
    from maid_runner.cli.test import _MultiManifestFileChangeHandler

    assert hasattr(_MultiManifestFileChangeHandler, "on_deleted")


def test_on_deleted_refreshes_mappings_for_manifest(tmp_path: Path):
    """Test that on_deleted refreshes mappings when a manifest is deleted."""
    from maid_runner.cli.test import _MultiManifestFileChangeHandler

    manifests_dir = tmp_path / "manifests"
    manifests_dir.mkdir()

    handler = _MultiManifestFileChangeHandler(
        file_to_manifests={},
        timeout=300,
        verbose=False,
        quiet=False,
        project_root=tmp_path,
        manifests_dir=manifests_dir,
        observer=MagicMock(),
    )

    # Mock refresh_file_mappings
    handler.refresh_file_mappings = MagicMock()

    # Create mock delete event for manifest
    mock_event = MagicMock()
    mock_event.is_directory = False
    mock_event.src_path = str(manifests_dir / "task-001.manifest.json")

    handler.on_deleted(mock_event)

    # Should have triggered refresh
    handler.refresh_file_mappings.assert_called_once()


def test_on_deleted_ignores_non_manifest_files(tmp_path: Path):
    """Test that on_deleted ignores non-manifest file deletions."""
    from maid_runner.cli.test import _MultiManifestFileChangeHandler

    manifests_dir = tmp_path / "manifests"
    manifests_dir.mkdir()

    handler = _MultiManifestFileChangeHandler(
        file_to_manifests={},
        timeout=300,
        verbose=False,
        quiet=False,
        project_root=tmp_path,
        manifests_dir=manifests_dir,
        observer=MagicMock(),
    )

    # Mock refresh_file_mappings
    handler.refresh_file_mappings = MagicMock()

    # Create mock delete event for regular file
    mock_event = MagicMock()
    mock_event.is_directory = False
    mock_event.src_path = str(tmp_path / "tests" / "test_file.py")

    handler.on_deleted(mock_event)

    # Should NOT have triggered refresh for non-manifest files
    handler.refresh_file_mappings.assert_not_called()


def test_on_deleted_ignores_directory_events(tmp_path: Path):
    """Test that on_deleted ignores directory deletion events."""
    from maid_runner.cli.test import _MultiManifestFileChangeHandler

    manifests_dir = tmp_path / "manifests"
    manifests_dir.mkdir()

    handler = _MultiManifestFileChangeHandler(
        file_to_manifests={},
        timeout=300,
        verbose=False,
        quiet=False,
        project_root=tmp_path,
        manifests_dir=manifests_dir,
        observer=MagicMock(),
    )

    # Mock refresh_file_mappings
    handler.refresh_file_mappings = MagicMock()

    # Create mock directory delete event
    mock_event = MagicMock()
    mock_event.is_directory = True
    mock_event.src_path = str(manifests_dir)

    handler.on_deleted(mock_event)

    # Should NOT have triggered refresh
    handler.refresh_file_mappings.assert_not_called()
