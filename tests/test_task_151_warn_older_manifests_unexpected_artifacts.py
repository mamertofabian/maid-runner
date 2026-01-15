"""Behavioral tests for warning older manifests on unexpected artifacts."""

import json
from pathlib import Path


from maid_runner.cli.validate import (
    _build_new_manifest_hint,
    _get_latest_manifest_name,
    _is_latest_manifest_for_file,
)


class TestIsLatestManifestForFile:
    """Test the _is_latest_manifest_for_file function."""

    def test_returns_true_for_latest_manifest(self, tmp_path):
        """Test that _is_latest_manifest_for_file returns True for the latest manifest."""
        # Create a temporary manifests directory
        manifests_dir = tmp_path / "manifests"
        manifests_dir.mkdir()

        # Create multiple manifests for the same file
        target_file = "test_file.py"

        # Create task-001
        manifest_1 = manifests_dir / "task-001.manifest.json"
        manifest_1.write_text(
            json.dumps(
                {
                    "goal": "First manifest",
                    "editableFiles": [target_file],
                    "expectedArtifacts": {"file": target_file, "contains": []},
                }
            )
        )

        # Create task-002 (latest)
        manifest_2 = manifests_dir / "task-002.manifest.json"
        manifest_2.write_text(
            json.dumps(
                {
                    "goal": "Second manifest",
                    "editableFiles": [target_file],
                    "expectedArtifacts": {"file": target_file, "contains": []},
                }
            )
        )

        # Change to the temp directory for relative path resolution
        original_cwd = Path.cwd()
        try:
            import os

            os.chdir(tmp_path)

            # USE the function - should return True for latest manifest
            result = _is_latest_manifest_for_file(
                manifest_2, target_file, use_cache=False
            )
            assert result is True
        finally:
            os.chdir(original_cwd)

    def test_returns_false_for_older_manifest(self, tmp_path):
        """Test that _is_latest_manifest_for_file returns False for older manifests."""
        # Create a temporary manifests directory
        manifests_dir = tmp_path / "manifests"
        manifests_dir.mkdir()

        # Create multiple manifests for the same file
        target_file = "test_file.py"

        # Create task-001 (older)
        manifest_1 = manifests_dir / "task-001.manifest.json"
        manifest_1.write_text(
            json.dumps(
                {
                    "goal": "First manifest",
                    "editableFiles": [target_file],
                    "expectedArtifacts": {"file": target_file, "contains": []},
                }
            )
        )

        # Create task-002 (latest)
        manifest_2 = manifests_dir / "task-002.manifest.json"
        manifest_2.write_text(
            json.dumps(
                {
                    "goal": "Second manifest",
                    "editableFiles": [target_file],
                    "expectedArtifacts": {"file": target_file, "contains": []},
                }
            )
        )

        # Change to the temp directory for relative path resolution
        original_cwd = Path.cwd()
        try:
            import os

            os.chdir(tmp_path)

            # USE the function - should return False for older manifest
            result = _is_latest_manifest_for_file(
                manifest_1, target_file, use_cache=False
            )
            assert result is False
        finally:
            os.chdir(original_cwd)

    def test_returns_true_for_only_manifest(self, tmp_path):
        """Test that _is_latest_manifest_for_file returns True when it's the only manifest."""
        # Create a temporary manifests directory
        manifests_dir = tmp_path / "manifests"
        manifests_dir.mkdir()

        target_file = "test_file.py"

        # Create single manifest
        manifest = manifests_dir / "task-001.manifest.json"
        manifest.write_text(
            json.dumps(
                {
                    "goal": "Only manifest",
                    "editableFiles": [target_file],
                    "expectedArtifacts": {"file": target_file, "contains": []},
                }
            )
        )

        # Change to the temp directory for relative path resolution
        original_cwd = Path.cwd()
        try:
            import os

            os.chdir(tmp_path)

            # USE the function - should return True for only manifest
            result = _is_latest_manifest_for_file(
                manifest, target_file, use_cache=False
            )
            assert result is True
        finally:
            os.chdir(original_cwd)


class TestBuildNewManifestHint:
    """Test the _build_new_manifest_hint function."""

    def test_returns_hint_for_unexpected_public_function(self):
        """Test that _build_new_manifest_hint returns hint for unexpected public function."""
        error_message = "Unexpected public function(s) found: undeclared_method"

        # USE the function - should return a hint string
        result = _build_new_manifest_hint(error_message)

        assert result is not None
        assert isinstance(result, str)
        assert "Create a new manifest" in result
        assert "new public function" in result or "behavioral test" in result

    def test_returns_hint_for_unexpected_public_class(self):
        """Test that _build_new_manifest_hint returns hint for unexpected public class."""
        error_message = "Unexpected public class(es) found: UndeclaredClass"

        # USE the function - should return a hint string
        result = _build_new_manifest_hint(error_message)

        assert result is not None
        assert isinstance(result, str)
        assert "Create a new manifest" in result

    def test_returns_none_for_non_unexpected_public_error(self):
        """Test that _build_new_manifest_hint returns None for other error types."""
        error_message = "Expected artifact not found: missing_function"

        # USE the function - should return None for non-unexpected-public errors
        result = _build_new_manifest_hint(error_message)

        assert result is None

    def test_returns_none_for_empty_string(self):
        """Test that _build_new_manifest_hint returns None for empty string."""
        # USE the function - should return None for empty string
        result = _build_new_manifest_hint("")

        assert result is None


class TestGetLatestManifestName:
    """Test the _get_latest_manifest_name function."""

    def test_returns_latest_manifest_name(self, tmp_path):
        """Test that _get_latest_manifest_name returns the name of the latest manifest."""
        # Create a temporary manifests directory
        manifests_dir = tmp_path / "manifests"
        manifests_dir.mkdir()

        target_file = "test_file.py"

        # Create multiple manifests
        manifest_1 = manifests_dir / "task-001.manifest.json"
        manifest_1.write_text(
            json.dumps(
                {
                    "goal": "First manifest",
                    "editableFiles": [target_file],
                    "expectedArtifacts": {"file": target_file, "contains": []},
                }
            )
        )

        manifest_2 = manifests_dir / "task-002.manifest.json"
        manifest_2.write_text(
            json.dumps(
                {
                    "goal": "Second manifest",
                    "editableFiles": [target_file],
                    "expectedArtifacts": {"file": target_file, "contains": []},
                }
            )
        )

        # Change to the temp directory for relative path resolution
        original_cwd = Path.cwd()
        try:
            import os

            os.chdir(tmp_path)

            # USE the function - should return the latest manifest name
            result = _get_latest_manifest_name(target_file, use_cache=False)

            assert result == "task-002.manifest.json"
        finally:
            os.chdir(original_cwd)

    def test_returns_unknown_when_no_manifests_exist(self, tmp_path):
        """Test that _get_latest_manifest_name returns 'unknown' when no manifests exist."""
        # Create a temporary manifests directory (empty)
        manifests_dir = tmp_path / "manifests"
        manifests_dir.mkdir()

        target_file = "test_file.py"

        # Change to the temp directory for relative path resolution
        original_cwd = Path.cwd()
        try:
            import os

            os.chdir(tmp_path)

            # USE the function - should return 'unknown' when no manifests exist
            result = _get_latest_manifest_name(target_file, use_cache=False)

            assert result == "unknown"
        finally:
            os.chdir(original_cwd)

    def test_returns_single_manifest_name(self, tmp_path):
        """Test that _get_latest_manifest_name returns the name when only one manifest exists."""
        # Create a temporary manifests directory
        manifests_dir = tmp_path / "manifests"
        manifests_dir.mkdir()

        target_file = "test_file.py"

        # Create single manifest
        manifest = manifests_dir / "task-001.manifest.json"
        manifest.write_text(
            json.dumps(
                {
                    "goal": "Only manifest",
                    "editableFiles": [target_file],
                    "expectedArtifacts": {"file": target_file, "contains": []},
                }
            )
        )

        # Change to the temp directory for relative path resolution
        original_cwd = Path.cwd()
        try:
            import os

            os.chdir(tmp_path)

            # USE the function - should return the manifest name
            result = _get_latest_manifest_name(target_file, use_cache=False)

            assert result == "task-001.manifest.json"
        finally:
            os.chdir(original_cwd)
