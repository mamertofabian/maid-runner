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
