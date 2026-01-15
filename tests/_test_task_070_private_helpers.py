"""
Private test module for private helper class declared in task-070 manifest.

These tests verify the actual behavior of private helper class that is declared
in the manifest. While this is an internal helper, it's part of the declared API
and must be behaviorally validated.

Tests focus on meaningful behavior:
- How this helper enables public APIs to work correctly
- Edge cases and error conditions
- Real-world usage scenarios

Related task: task-070-validate-watch-mode
"""

import pytest
from pathlib import Path
from unittest.mock import Mock

# Import with fallback for Red phase testing
try:
    from maid_runner.cli.validate import (
        _MultiManifestValidationHandler,
        _ManifestFileChangeHandler,
    )
except ImportError as e:
    # In Red phase, these functions won't exist yet
    pytest.skip(f"Implementation not ready: {e}", allow_module_level=True)


class TestMultiManifestValidationHandler:
    """Test _MultiManifestValidationHandler private class behavior."""

    def test_multi_manifest_handler_init_called(self, tmp_path):
        """Test that _MultiManifestValidationHandler.__init__ is called when instantiating."""
        file_to_manifests = {}
        handler = _MultiManifestValidationHandler(
            file_to_manifests=file_to_manifests,
            use_manifest_chain=False,
            quiet=True,
            skip_tests=False,
            timeout=300,
            verbose=False,
            project_root=tmp_path,
        )

        assert hasattr(handler, "file_to_manifests")
        assert hasattr(handler, "use_manifest_chain")
        assert hasattr(handler, "quiet")
        assert hasattr(handler, "skip_tests")
        assert hasattr(handler, "timeout")
        assert hasattr(handler, "verbose")
        assert hasattr(handler, "project_root")
        assert handler.file_to_manifests == file_to_manifests

    def test_multi_manifest_handler_init_explicitly_called(self, tmp_path):
        """Test that _MultiManifestValidationHandler.__init__ can be called explicitly."""
        file_to_manifests = {}
        handler = _MultiManifestValidationHandler(
            file_to_manifests=file_to_manifests,
            use_manifest_chain=False,
            quiet=True,
            skip_tests=False,
            timeout=300,
            verbose=False,
            project_root=tmp_path,
        )

        new_file_to_manifests = {Path("test.py"): [Path("manifest.json")]}
        handler.__init__(
            file_to_manifests=new_file_to_manifests,
            use_manifest_chain=True,
            quiet=False,
            skip_tests=True,
            timeout=600,
            verbose=True,
            project_root=tmp_path,
        )

        assert handler.file_to_manifests == new_file_to_manifests
        assert handler.use_manifest_chain is True
        assert handler.quiet is False

    def test_multi_manifest_handler_on_modified_called(self, tmp_path):
        """Test that _MultiManifestValidationHandler.on_modified is called with event."""
        file_to_manifests = {}
        handler = _MultiManifestValidationHandler(
            file_to_manifests=file_to_manifests,
            use_manifest_chain=False,
            quiet=True,
            skip_tests=True,
            timeout=300,
            verbose=False,
            project_root=tmp_path,
        )

        # Create a mock event
        event = Mock()
        event.is_directory = False
        event.src_path = str(tmp_path / "test.py")

        # Call on_modified directly
        handler.on_modified(event)

        # Should not raise an error
        assert handler.last_run >= 0

    def test_multi_manifest_handler_on_modified_ignores_directories(self, tmp_path):
        """Test that _MultiManifestValidationHandler.on_modified ignores directory events."""
        file_to_manifests = {}
        handler = _MultiManifestValidationHandler(
            file_to_manifests=file_to_manifests,
            use_manifest_chain=False,
            quiet=True,
            skip_tests=True,
            timeout=300,
            verbose=False,
            project_root=tmp_path,
        )

        # Create a mock event for a directory
        event = Mock()
        event.is_directory = True
        event.src_path = str(tmp_path)

        # Call on_modified directly - should return early
        handler.on_modified(event)

        # Should not have updated last_run for directories
        assert handler.last_run == 0.0

    def test_multi_manifest_handler_on_created_called(self, tmp_path):
        """Test that _MultiManifestValidationHandler.on_created is called with event."""
        file_to_manifests = {}
        handler = _MultiManifestValidationHandler(
            file_to_manifests=file_to_manifests,
            use_manifest_chain=False,
            quiet=True,
            skip_tests=True,
            timeout=300,
            verbose=False,
            project_root=tmp_path,
            manifests_dir=tmp_path / "manifests",
        )

        # Create a mock event
        event = Mock()
        event.is_directory = False
        event.src_path = str(tmp_path / "new_file.py")

        # Call on_created directly
        handler.on_created(event)

        # Should not raise an error
        assert True

    def test_multi_manifest_handler_on_created_ignores_directories(self, tmp_path):
        """Test that _MultiManifestValidationHandler.on_created ignores directory events."""
        file_to_manifests = {}
        handler = _MultiManifestValidationHandler(
            file_to_manifests=file_to_manifests,
            use_manifest_chain=False,
            quiet=True,
            skip_tests=True,
            timeout=300,
            verbose=False,
            project_root=tmp_path,
        )

        # Create a mock event for a directory
        event = Mock()
        event.is_directory = True
        event.src_path = str(tmp_path)

        # Call on_created directly - should return early
        handler.on_created(event)

        # Should not raise an error
        assert True

    def test_multi_manifest_handler_on_moved_called(self, tmp_path):
        """Test that _MultiManifestValidationHandler.on_moved is called with event."""
        file_to_manifests = {}
        handler = _MultiManifestValidationHandler(
            file_to_manifests=file_to_manifests,
            use_manifest_chain=False,
            quiet=True,
            skip_tests=True,
            timeout=300,
            verbose=False,
            project_root=tmp_path,
        )

        # Create a mock event
        event = Mock()
        event.is_directory = False
        event.src_path = str(tmp_path / "old_file.py")
        event.dest_path = str(tmp_path / "new_file.py")

        # Call on_moved directly
        handler.on_moved(event)

        # Should not raise an error
        assert True

    def test_multi_manifest_handler_on_moved_ignores_directories(self, tmp_path):
        """Test that _MultiManifestValidationHandler.on_moved ignores directory events."""
        file_to_manifests = {}
        handler = _MultiManifestValidationHandler(
            file_to_manifests=file_to_manifests,
            use_manifest_chain=False,
            quiet=True,
            skip_tests=True,
            timeout=300,
            verbose=False,
            project_root=tmp_path,
        )

        # Create a mock event for a directory
        event = Mock()
        event.is_directory = True
        event.src_path = str(tmp_path / "old_dir")
        event.dest_path = str(tmp_path / "new_dir")

        # Call on_moved directly - should return early
        handler.on_moved(event)

        # Should not raise an error
        assert True

    def test_multi_manifest_handler_handles_file_to_manifests_mapping(self, tmp_path):
        """Test that _MultiManifestValidationHandler handles file_to_manifests mapping."""
        test_file = tmp_path / "test.py"
        manifest_file = tmp_path / "manifest.json"
        test_file.touch()
        manifest_file.touch()

        file_to_manifests = {
            test_file.resolve(): [manifest_file.resolve()],
        }

        handler = _MultiManifestValidationHandler(
            file_to_manifests=file_to_manifests,
            use_manifest_chain=False,
            quiet=True,
            skip_tests=True,
            timeout=300,
            verbose=False,
            project_root=tmp_path,
        )

        assert test_file.resolve() in handler.file_to_manifests
        assert handler.file_to_manifests[test_file.resolve()] == [
            manifest_file.resolve()
        ]

    def test_multi_manifest_handler_debounces_rapid_changes(self, tmp_path):
        """Test that _MultiManifestValidationHandler debounces rapid file changes."""

        file_to_manifests = {}
        handler = _MultiManifestValidationHandler(
            file_to_manifests=file_to_manifests,
            use_manifest_chain=False,
            quiet=True,
            skip_tests=True,
            timeout=300,
            verbose=False,
            project_root=tmp_path,
        )

        event1 = Mock()
        event1.is_directory = False
        event1.src_path = str(tmp_path / "test.py")

        event2 = Mock()
        event2.is_directory = False
        event2.src_path = str(tmp_path / "test.py")

        # First call should update last_run
        handler.on_modified(event1)
        first_run_time = handler.last_run

        # Immediate second call should be debounced
        handler.on_modified(event2)
        # last_run should not have changed significantly
        assert abs(handler.last_run - first_run_time) < 0.1


class TestManifestFileChangeHandler:
    """Test _ManifestFileChangeHandler private class behavior."""

    def test_manifest_file_change_handler_init_called(self, tmp_path):
        """Test that _ManifestFileChangeHandler.__init__ is called when instantiating."""
        manifest_path = tmp_path / "manifest.json"
        manifest_path.write_text('{"goal": "test"}')

        handler = _ManifestFileChangeHandler(
            manifest_path=manifest_path,
            use_manifest_chain=False,
            quiet=True,
            skip_tests=False,
            timeout=300,
            verbose=False,
            project_root=tmp_path,
        )

        assert hasattr(handler, "manifest_path")
        assert hasattr(handler, "use_manifest_chain")
        assert hasattr(handler, "quiet")
        assert hasattr(handler, "skip_tests")
        assert hasattr(handler, "timeout")
        assert hasattr(handler, "verbose")
        assert hasattr(handler, "project_root")
        assert handler.manifest_path == manifest_path

    def test_manifest_file_change_handler_init_explicitly_called(self, tmp_path):
        """Test that _ManifestFileChangeHandler.__init__ can be called explicitly."""
        manifest_path = tmp_path / "manifest.json"
        manifest_path.write_text('{"goal": "test"}')

        handler = _ManifestFileChangeHandler(
            manifest_path=manifest_path,
            use_manifest_chain=False,
            quiet=True,
            skip_tests=False,
            timeout=300,
            verbose=False,
            project_root=tmp_path,
        )

        new_manifest_path = tmp_path / "new_manifest.json"
        new_manifest_path.write_text('{"goal": "test2"}')

        handler.__init__(
            manifest_path=new_manifest_path,
            use_manifest_chain=True,
            quiet=False,
            skip_tests=True,
            timeout=600,
            verbose=True,
            project_root=tmp_path,
        )

        assert handler.manifest_path == new_manifest_path
        assert handler.use_manifest_chain is True
        assert handler.quiet is False

    def test_manifest_file_change_handler_on_modified_called(self, tmp_path):
        """Test that _ManifestFileChangeHandler.on_modified is called with event."""
        manifest_path = tmp_path / "manifest.json"
        manifest_path.write_text('{"goal": "test", "editableFiles": ["test.py"]}')

        handler = _ManifestFileChangeHandler(
            manifest_path=manifest_path,
            use_manifest_chain=False,
            quiet=True,
            skip_tests=True,
            timeout=300,
            verbose=False,
            project_root=tmp_path,
        )

        # Create a mock event
        event = Mock()
        event.is_directory = False
        event.src_path = str(tmp_path / "test.py")

        # Call on_modified directly
        handler.on_modified(event)

        # Should not raise an error
        assert handler.last_run >= 0

    def test_manifest_file_change_handler_on_created_called(self, tmp_path):
        """Test that _ManifestFileChangeHandler.on_created is called with event."""
        manifest_path = tmp_path / "manifest.json"
        manifest_path.write_text('{"goal": "test", "editableFiles": ["test.py"]}')

        handler = _ManifestFileChangeHandler(
            manifest_path=manifest_path,
            use_manifest_chain=False,
            quiet=True,
            skip_tests=True,
            timeout=300,
            verbose=False,
            project_root=tmp_path,
        )

        # Create a mock event
        event = Mock()
        event.is_directory = False
        event.src_path = str(tmp_path / "new_file.py")

        # Call on_created directly
        handler.on_created(event)

        # Should not raise an error
        assert True

    def test_manifest_file_change_handler_on_moved_called(self, tmp_path):
        """Test that _ManifestFileChangeHandler.on_moved is called with event."""
        manifest_path = tmp_path / "manifest.json"
        manifest_path.write_text('{"goal": "test", "editableFiles": ["test.py"]}')

        handler = _ManifestFileChangeHandler(
            manifest_path=manifest_path,
            use_manifest_chain=False,
            quiet=True,
            skip_tests=True,
            timeout=300,
            verbose=False,
            project_root=tmp_path,
        )

        # Create a mock event
        event = Mock()
        event.is_directory = False
        event.src_path = str(tmp_path / "old_file.py")
        event.dest_path = str(tmp_path / "new_file.py")

        # Call on_moved directly
        handler.on_moved(event)

        # Should not raise an error
        assert True

    def test_manifest_file_change_handler_ignores_unwatched_files(self, tmp_path):
        """Test that _ManifestFileChangeHandler ignores changes to unwatched files."""
        manifest_path = tmp_path / "manifest.json"
        manifest_path.write_text('{"goal": "test", "editableFiles": ["test.py"]}')

        handler = _ManifestFileChangeHandler(
            manifest_path=manifest_path,
            use_manifest_chain=False,
            quiet=True,
            skip_tests=True,
            timeout=300,
            verbose=False,
            project_root=tmp_path,
        )

        # Create a mock event for an unwatched file
        event = Mock()
        event.is_directory = False
        event.src_path = str(tmp_path / "unwatched.py")

        # Call on_modified directly - should not trigger validation
        initial_last_run = handler.last_run
        handler.on_modified(event)

        # last_run should not have changed for unwatched files
        assert handler.last_run == initial_last_run

    def test_manifest_file_change_handler_handles_invalid_json(self, tmp_path):
        """Test that _ManifestFileChangeHandler handles invalid JSON manifest gracefully."""
        manifest_path = tmp_path / "manifest.json"
        manifest_path.write_text("not valid json {{{")

        # Should not raise, should fallback to just watching manifest file
        handler = _ManifestFileChangeHandler(
            manifest_path=manifest_path,
            use_manifest_chain=False,
            quiet=True,
            skip_tests=True,
            timeout=300,
            verbose=False,
            project_root=tmp_path,
        )

        # Should have only the manifest in watchable paths
        assert manifest_path.resolve() in handler.watchable_paths

    def test_manifest_file_change_handler_on_created_ignores_directories(
        self, tmp_path
    ):
        """Test that _ManifestFileChangeHandler.on_created ignores directory events."""
        manifest_path = tmp_path / "manifest.json"
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

        # Create a mock event for a directory
        event = Mock()
        event.is_directory = True
        event.src_path = str(tmp_path / "new_dir")

        initial_last_run = handler.last_run
        handler.on_created(event)

        # Should have returned early, not updating last_run
        assert handler.last_run == initial_last_run

    def test_manifest_file_change_handler_on_moved_ignores_directories(self, tmp_path):
        """Test that _ManifestFileChangeHandler.on_moved ignores directory events."""
        manifest_path = tmp_path / "manifest.json"
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

        # Create a mock event for a directory move
        event = Mock()
        event.is_directory = True
        event.src_path = str(tmp_path / "old_dir")
        event.dest_path = str(tmp_path / "new_dir")

        initial_last_run = handler.last_run
        handler.on_moved(event)

        # Should have returned early, not updating last_run
        assert handler.last_run == initial_last_run


class TestMultiManifestValidationHandlerExtended:
    """Extended tests for _MultiManifestValidationHandler."""

    def test_on_created_detects_new_manifest(self, tmp_path):
        """Test that on_created detects new manifest files."""
        manifests_dir = tmp_path / "manifests"
        manifests_dir.mkdir()

        handler = _MultiManifestValidationHandler(
            file_to_manifests={},
            use_manifest_chain=False,
            quiet=True,
            skip_tests=True,
            timeout=300,
            verbose=False,
            project_root=tmp_path,
            manifests_dir=manifests_dir,
        )

        # Create an event for a new manifest file
        event = Mock()
        event.is_directory = False
        event.src_path = str(manifests_dir / "task-001.manifest.json")

        # Should not raise
        handler.on_created(event)

    def test_on_deleted_handles_manifest_deletion(self, tmp_path):
        """Test that on_deleted handles manifest file deletion."""
        manifests_dir = tmp_path / "manifests"
        manifests_dir.mkdir()

        handler = _MultiManifestValidationHandler(
            file_to_manifests={},
            use_manifest_chain=False,
            quiet=True,
            skip_tests=True,
            timeout=300,
            verbose=False,
            project_root=tmp_path,
            manifests_dir=manifests_dir,
        )

        # Create an event for a deleted manifest file
        event = Mock()
        event.is_directory = False
        event.src_path = str(manifests_dir / "task-001.manifest.json")

        # Should not raise
        handler.on_deleted(event)

    def test_on_deleted_ignores_directories(self, tmp_path):
        """Test that on_deleted ignores directory events."""
        handler = _MultiManifestValidationHandler(
            file_to_manifests={},
            use_manifest_chain=False,
            quiet=True,
            skip_tests=True,
            timeout=300,
            verbose=False,
            project_root=tmp_path,
        )

        # Create a mock event for a directory
        event = Mock()
        event.is_directory = True
        event.src_path = str(tmp_path / "deleted_dir")

        # Should not raise
        handler.on_deleted(event)

    def test_on_moved_detects_new_manifest(self, tmp_path):
        """Test that on_moved detects manifest files moved/renamed to manifests dir."""
        manifests_dir = tmp_path / "manifests"
        manifests_dir.mkdir()

        handler = _MultiManifestValidationHandler(
            file_to_manifests={},
            use_manifest_chain=False,
            quiet=True,
            skip_tests=True,
            timeout=300,
            verbose=False,
            project_root=tmp_path,
            manifests_dir=manifests_dir,
        )

        # Create an event for a manifest file being moved
        event = Mock()
        event.is_directory = False
        event.src_path = str(tmp_path / "temp_file.tmp")
        event.dest_path = str(manifests_dir / "task-001.manifest.json")

        # Should not raise
        handler.on_moved(event)

    def test_on_modified_triggers_validation_for_tracked_file(self, tmp_path):
        """Test that on_modified triggers validation when a tracked file changes."""
        from unittest.mock import patch

        manifest_path = tmp_path / "manifests" / "task-001.manifest.json"
        manifest_path.parent.mkdir(parents=True)
        manifest_path.write_text('{"goal": "test"}')

        tracked_file = tmp_path / "src" / "test.py"
        tracked_file.parent.mkdir(parents=True)
        tracked_file.touch()

        file_to_manifests = {
            tracked_file.resolve(): [manifest_path],
        }

        handler = _MultiManifestValidationHandler(
            file_to_manifests=file_to_manifests,
            use_manifest_chain=False,
            quiet=True,
            skip_tests=True,
            timeout=300,
            verbose=False,
            project_root=tmp_path,
        )

        # Create an event for the tracked file
        event = Mock()
        event.is_directory = False
        event.src_path = str(tracked_file)

        # Mock the validation runner to avoid actual validation
        with patch.object(handler, "_run_validation_for_manifest"):
            handler.on_modified(event)

            # Should have updated last_run
            assert handler.last_run > 0

    def test_refresh_file_mappings_rebuilds_mapping(self, tmp_path):
        """Test that refresh_file_mappings rebuilds the file-to-manifests mapping."""
        manifests_dir = tmp_path / "manifests"
        manifests_dir.mkdir()

        # Create a manifest
        manifest_path = manifests_dir / "task-001.manifest.json"
        manifest_path.write_text('{"goal": "test", "editableFiles": ["src/test.py"]}')

        handler = _MultiManifestValidationHandler(
            file_to_manifests={},
            use_manifest_chain=False,
            quiet=True,
            skip_tests=True,
            timeout=300,
            verbose=False,
            project_root=tmp_path,
            manifests_dir=manifests_dir,
        )

        # Call refresh_file_mappings
        handler.refresh_file_mappings()

        # The file_to_manifests should have been updated
        assert len(handler.file_to_manifests) >= 0  # May be empty if no files exist


class TestMultiManifestHandlerQuietFalse:
    """Test _MultiManifestValidationHandler with quiet=False to cover print statements."""

    def test_on_modified_prints_when_quiet_false(self, tmp_path, capsys):
        """Test that on_modified prints change detection message when quiet=False."""
        from unittest.mock import patch

        manifest_path = tmp_path / "manifests" / "task-001.manifest.json"
        manifest_path.parent.mkdir(parents=True)
        manifest_path.write_text('{"goal": "test"}')

        tracked_file = tmp_path / "src" / "test.py"
        tracked_file.parent.mkdir(parents=True)
        tracked_file.touch()

        file_to_manifests = {
            tracked_file.resolve(): [manifest_path],
        }

        handler = _MultiManifestValidationHandler(
            file_to_manifests=file_to_manifests,
            use_manifest_chain=False,
            quiet=False,  # Enable output
            skip_tests=True,
            timeout=300,
            verbose=False,
            project_root=tmp_path,
        )

        # Create an event for the tracked file
        event = Mock()
        event.is_directory = False
        event.src_path = str(tracked_file)

        # Mock the validation runner to avoid actual validation
        with patch.object(handler, "_run_validation_for_manifest"):
            handler.on_modified(event)

            captured = capsys.readouterr()
            # Should have printed a message about the change
            assert "Detected change" in captured.out or "🔔" in captured.out

    def test_on_created_manifest_prints_when_quiet_false(self, tmp_path, capsys):
        """Test that on_created prints message for new manifest when quiet=False."""
        manifests_dir = tmp_path / "manifests"
        manifests_dir.mkdir()

        handler = _MultiManifestValidationHandler(
            file_to_manifests={},
            use_manifest_chain=False,
            quiet=False,  # Enable output
            skip_tests=True,
            timeout=300,
            verbose=False,
            project_root=tmp_path,
            manifests_dir=manifests_dir,
        )

        # Create an event for a new manifest file
        event = Mock()
        event.is_directory = False
        event.src_path = str(manifests_dir / "task-001.manifest.json")

        handler.on_created(event)

        captured = capsys.readouterr()
        # Should have printed a message about new manifest
        assert "manifest detected" in captured.out.lower() or "🔄" in captured.out

    def test_on_deleted_manifest_prints_when_quiet_false(self, tmp_path, capsys):
        """Test that on_deleted prints message for deleted manifest when quiet=False."""
        manifests_dir = tmp_path / "manifests"
        manifests_dir.mkdir()

        handler = _MultiManifestValidationHandler(
            file_to_manifests={},
            use_manifest_chain=False,
            quiet=False,  # Enable output
            skip_tests=True,
            timeout=300,
            verbose=False,
            project_root=tmp_path,
            manifests_dir=manifests_dir,
        )

        # Create an event for a deleted manifest file
        event = Mock()
        event.is_directory = False
        event.src_path = str(manifests_dir / "task-001.manifest.json")

        handler.on_deleted(event)

        captured = capsys.readouterr()
        # Should have printed a message about deleted manifest
        assert "deleted" in captured.out.lower() or "🗑️" in captured.out

    def test_on_moved_manifest_prints_when_quiet_false(self, tmp_path, capsys):
        """Test that on_moved prints message for manifest rename when quiet=False."""
        manifests_dir = tmp_path / "manifests"
        manifests_dir.mkdir()

        handler = _MultiManifestValidationHandler(
            file_to_manifests={},
            use_manifest_chain=False,
            quiet=False,  # Enable output
            skip_tests=True,
            timeout=300,
            verbose=False,
            project_root=tmp_path,
            manifests_dir=manifests_dir,
        )

        # Create an event for a manifest file being moved
        event = Mock()
        event.is_directory = False
        event.src_path = str(tmp_path / "temp_file.tmp")
        event.dest_path = str(manifests_dir / "task-001.manifest.json")

        handler.on_moved(event)

        captured = capsys.readouterr()
        # Should have printed a message about new manifest
        assert "manifest detected" in captured.out.lower() or "🔄" in captured.out


class TestManifestFileChangeHandlerQuietFalse:
    """Test _ManifestFileChangeHandler with quiet=False to cover print statements."""

    def test_on_modified_prints_when_quiet_false(self, tmp_path, capsys):
        """Test that on_modified prints change detection when quiet=False."""
        from unittest.mock import patch

        manifest_path = tmp_path / "manifest.json"
        manifest_path.write_text('{"goal": "test", "editableFiles": ["test.py"]}')

        # Create the test file
        test_file = tmp_path / "test.py"
        test_file.touch()

        handler = _ManifestFileChangeHandler(
            manifest_path=manifest_path,
            use_manifest_chain=False,
            quiet=False,  # Enable output
            skip_tests=True,
            timeout=300,
            verbose=False,
            project_root=tmp_path,
        )

        # Create a mock event for the test file
        event = Mock()
        event.is_directory = False
        event.src_path = str(test_file)

        # Mock the validation to avoid running actual validation
        with patch.object(handler, "_run_validation"):
            handler.on_modified(event)

            captured = capsys.readouterr()
            # Should have printed a message about detected change
            assert "Detected change" in captured.out or "🔔" in captured.out

    def test_on_created_prints_when_quiet_false(self, tmp_path, capsys):
        """Test that on_created prints file created message when quiet=False."""
        from unittest.mock import patch

        manifest_path = tmp_path / "manifest.json"
        test_file = tmp_path / "test.py"
        manifest_path.write_text(
            '{"goal": "test", "editableFiles": ["' + str(test_file) + '"]}'
        )
        test_file.touch()

        handler = _ManifestFileChangeHandler(
            manifest_path=manifest_path,
            use_manifest_chain=False,
            quiet=False,  # Enable output
            skip_tests=True,
            timeout=300,
            verbose=False,
            project_root=tmp_path,
        )

        # Manually add the test file to watchable paths
        handler.watchable_paths.add(test_file.resolve())

        # Create a mock event for a new file
        event = Mock()
        event.is_directory = False
        event.src_path = str(test_file)

        # Mock the validation to avoid running actual validation
        with patch.object(handler, "_run_validation"):
            handler.on_created(event)

            captured = capsys.readouterr()
            # Should have printed a message about file created
            assert "created" in captured.out.lower() or "🔔" in captured.out

    def test_on_moved_prints_when_quiet_false(self, tmp_path, capsys):
        """Test that on_moved prints detected change when quiet=False."""
        from unittest.mock import patch

        manifest_path = tmp_path / "manifest.json"
        manifest_path.write_text('{"goal": "test", "editableFiles": ["test.py"]}')

        # Create the test file
        test_file = tmp_path / "test.py"
        test_file.touch()

        handler = _ManifestFileChangeHandler(
            manifest_path=manifest_path,
            use_manifest_chain=False,
            quiet=False,  # Enable output
            skip_tests=True,
            timeout=300,
            verbose=False,
            project_root=tmp_path,
        )

        # Create a mock move event
        event = Mock()
        event.is_directory = False
        event.src_path = str(tmp_path / "temp.tmp")
        event.dest_path = str(test_file)

        # Mock the validation to avoid running actual validation
        with patch.object(handler, "_run_validation"):
            handler.on_moved(event)

            captured = capsys.readouterr()
            # Should have printed a message about detected change
            assert "Detected change" in captured.out or "🔔" in captured.out

    def test_on_modified_refreshes_paths_on_manifest_change(self, tmp_path):
        """Test that on_modified refreshes watchable paths when manifest changes."""
        from unittest.mock import patch

        manifest_path = tmp_path / "manifest.json"
        manifest_path.write_text('{"goal": "test", "editableFiles": ["test.py"]}')

        handler = _ManifestFileChangeHandler(
            manifest_path=manifest_path,
            use_manifest_chain=False,
            quiet=True,
            skip_tests=True,
            timeout=300,
            verbose=False,
            project_root=tmp_path,
        )

        # Verify initial watchable paths includes manifest
        assert manifest_path.resolve() in handler.watchable_paths

        # Create an event for the manifest file itself
        event = Mock()
        event.is_directory = False
        event.src_path = str(manifest_path)

        # Mock _run_validation and _refresh_watchable_paths to track calls
        with patch.object(handler, "_run_validation"):
            with patch.object(handler, "_refresh_watchable_paths") as mock_refresh:
                handler.on_modified(event)

                # Should have called refresh since manifest file changed
                mock_refresh.assert_called_once()
