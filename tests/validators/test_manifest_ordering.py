"""Tests for manifest file ordering with various naming patterns."""

import json
import tempfile
from pathlib import Path
from validators.manifest_validator import _discover_related_manifests


def test_four_digit_task_numbers():
    """Test that task-1000 comes after task-999."""
    with tempfile.TemporaryDirectory() as tmpdir:
        manifest_dir = Path(tmpdir) / "manifests"
        manifest_dir.mkdir()

        # Create manifests with 3 and 4 digit numbers
        manifests_to_create = [
            "task-998.json",
            "task-999.json",
            "task-1000.json",
            "task-1001.json",
        ]

        manifest_content = {
            "expectedArtifacts": {"file": "test.py", "contains": []},
            "creatableFiles": ["test.py"],
        }

        for filename in manifests_to_create:
            path = manifest_dir / filename
            with open(path, "w") as f:
                json.dump(manifest_content, f)

        # Mock the manifest directory
        import validators.manifest_validator as mv

        original_path = mv.Path
        mv.Path = lambda x: manifest_dir if x == "manifests" else original_path(x)

        try:
            manifests = _discover_related_manifests("test.py")
            # Verify correct ordering
            assert len(manifests) == 4
            assert "task-998" in manifests[0]
            assert "task-999" in manifests[1]
            assert "task-1000" in manifests[2]
            assert "task-1001" in manifests[3]
        finally:
            mv.Path = original_path


def test_mixed_digit_lengths():
    """Test sorting with various digit lengths (1, 2, 3, 4+ digits)."""
    with tempfile.TemporaryDirectory() as tmpdir:
        manifest_dir = Path(tmpdir) / "manifests"
        manifest_dir.mkdir()

        # Create manifests with different digit lengths
        manifests_to_create = [
            "task-1.json",
            "task-9.json",
            "task-10.json",
            "task-99.json",
            "task-100.json",
            "task-999.json",
            "task-1000.json",
            "task-9999.json",
            "task-10000.json",
        ]

        manifest_content = {
            "expectedArtifacts": {"file": "test.py", "contains": []},
            "creatableFiles": ["test.py"],
        }

        for filename in manifests_to_create:
            path = manifest_dir / filename
            with open(path, "w") as f:
                json.dump(manifest_content, f)

        # Mock the manifest directory
        import validators.manifest_validator as mv

        original_path = mv.Path
        mv.Path = lambda x: manifest_dir if x == "manifests" else original_path(x)

        try:
            manifests = _discover_related_manifests("test.py")
            # Verify correct numerical ordering
            assert len(manifests) == 9
            assert "task-1" in manifests[0]
            assert "task-9" in manifests[1]
            assert "task-10" in manifests[2]
            assert "task-99" in manifests[3]
            assert "task-100" in manifests[4]
            assert "task-999" in manifests[5]
            assert "task-1000" in manifests[6]
            assert "task-9999" in manifests[7]
            assert "task-10000" in manifests[8]
        finally:
            mv.Path = original_path


def test_descriptive_names_with_numbers():
    """Test that descriptive names after task numbers work correctly."""
    with tempfile.TemporaryDirectory() as tmpdir:
        manifest_dir = Path(tmpdir) / "manifests"
        manifest_dir.mkdir()

        # Create manifests with descriptive names
        manifests_to_create = [
            "task-1-initial-setup.manifest.json",
            "task-2-add-user-model.json",
            "task-10-implement-validation.json",
            "task-100-major-refactor.json",
            "task-999-fix-critical-bug.json",
            "task-1000-add-oauth.json",
            "task-1001-update-dependencies.manifest.json",
        ]

        manifest_content = {
            "expectedArtifacts": {"file": "test.py", "contains": []},
            "creatableFiles": ["test.py"],
        }

        for filename in manifests_to_create:
            path = manifest_dir / filename
            with open(path, "w") as f:
                json.dump(manifest_content, f)

        # Mock the manifest directory
        import validators.manifest_validator as mv

        original_path = mv.Path
        mv.Path = lambda x: manifest_dir if x == "manifests" else original_path(x)

        try:
            manifests = _discover_related_manifests("test.py")
            # Verify correct ordering despite descriptive names
            assert len(manifests) == 7
            assert "task-1-initial-setup" in manifests[0]
            assert "task-2-add-user-model" in manifests[1]
            assert "task-10-implement-validation" in manifests[2]
            assert "task-100-major-refactor" in manifests[3]
            assert "task-999-fix-critical-bug" in manifests[4]
            assert "task-1000-add-oauth" in manifests[5]
            assert "task-1001-update-dependencies" in manifests[6]
        finally:
            mv.Path = original_path


def test_non_task_files_sorted_last():
    """Test that non-task JSON files are sorted at the end."""
    with tempfile.TemporaryDirectory() as tmpdir:
        manifest_dir = Path(tmpdir) / "manifests"
        manifest_dir.mkdir()

        # Create mix of task and non-task files
        manifests_to_create = [
            "task-1.json",
            "config.json",
            "task-10.json",
            "settings.json",
            "task-100.json",
            "metadata.json",
        ]

        manifest_content = {
            "expectedArtifacts": {"file": "test.py", "contains": []},
            "creatableFiles": ["test.py"],
        }

        for filename in manifests_to_create:
            path = manifest_dir / filename
            with open(path, "w") as f:
                json.dump(manifest_content, f)

        # Mock the manifest directory
        import validators.manifest_validator as mv

        original_path = mv.Path
        mv.Path = lambda x: manifest_dir if x == "manifests" else original_path(x)

        try:
            manifests = _discover_related_manifests("test.py")
            # Task files should come first, then non-task files
            assert len(manifests) == 6
            assert "task-1" in manifests[0]
            assert "task-10" in manifests[1]
            assert "task-100" in manifests[2]
            # Non-task files should be at the end (order among them doesn't matter)
            non_task_files = manifests[3:]
            assert any("config" in f for f in non_task_files)
            assert any("settings" in f for f in non_task_files)
            assert any("metadata" in f for f in non_task_files)
        finally:
            mv.Path = original_path


def test_malformed_task_names():
    """Test handling of malformed task names."""
    with tempfile.TemporaryDirectory() as tmpdir:
        manifest_dir = Path(tmpdir) / "manifests"
        manifest_dir.mkdir()

        # Create manifests with various edge cases
        manifests_to_create = [
            "task-1.json",
            "task-abc.json",  # Non-numeric task number
            "task-.json",  # Missing number
            "task.json",  # No dash
            "task-10.json",
            "task-2-5.json",  # Multiple numbers in name
            "task-100.json",
        ]

        manifest_content = {
            "expectedArtifacts": {"file": "test.py", "contains": []},
            "creatableFiles": ["test.py"],
        }

        for filename in manifests_to_create:
            path = manifest_dir / filename
            with open(path, "w") as f:
                json.dump(manifest_content, f)

        # Mock the manifest directory
        import validators.manifest_validator as mv

        original_path = mv.Path
        mv.Path = lambda x: manifest_dir if x == "manifests" else original_path(x)

        try:
            manifests = _discover_related_manifests("test.py")
            # Valid task files should be sorted numerically
            assert "task-1" in manifests[0]
            assert "task-2-5" in manifests[1]  # This parses as task-2
            assert "task-10" in manifests[2]
            assert "task-100" in manifests[3]
            # Malformed task files should be at the end
            assert len(manifests) == 7
        finally:
            mv.Path = original_path


def test_backward_compatibility_three_digit():
    """Test that existing 3-digit format still works correctly."""
    with tempfile.TemporaryDirectory() as tmpdir:
        manifest_dir = Path(tmpdir) / "manifests"
        manifest_dir.mkdir()

        # Create traditional 3-digit format manifests
        manifests_to_create = [
            "task-001.json",
            "task-002.json",
            "task-010.json",
            "task-099.json",
            "task-100.json",
        ]

        manifest_content = {
            "expectedArtifacts": {"file": "test.py", "contains": []},
            "creatableFiles": ["test.py"],
        }

        for filename in manifests_to_create:
            path = manifest_dir / filename
            with open(path, "w") as f:
                json.dump(manifest_content, f)

        # Mock the manifest directory
        import validators.manifest_validator as mv

        original_path = mv.Path
        mv.Path = lambda x: manifest_dir if x == "manifests" else original_path(x)

        try:
            manifests = _discover_related_manifests("test.py")
            # Should maintain correct ordering with leading zeros
            assert len(manifests) == 5
            assert "task-001" in manifests[0]
            assert "task-002" in manifests[1]
            assert "task-010" in manifests[2]
            assert "task-099" in manifests[3]
            assert "task-100" in manifests[4]
        finally:
            mv.Path = original_path


def test_empty_manifest_directory():
    """Test behavior with no manifest files."""
    with tempfile.TemporaryDirectory() as tmpdir:
        manifest_dir = Path(tmpdir) / "manifests"
        manifest_dir.mkdir()

        # Mock the manifest directory
        import validators.manifest_validator as mv

        original_path = mv.Path
        mv.Path = lambda x: manifest_dir if x == "manifests" else original_path(x)

        try:
            manifests = _discover_related_manifests("test.py")
            assert manifests == []
        finally:
            mv.Path = original_path


def test_mixed_formats():
    """Test sorting with mixed 3-digit padded and unpadded formats."""
    with tempfile.TemporaryDirectory() as tmpdir:
        manifest_dir = Path(tmpdir) / "manifests"
        manifest_dir.mkdir()

        # Mix of padded and unpadded formats
        manifests_to_create = [
            "task-001.json",  # Padded
            "task-2.json",  # Unpadded
            "task-010.json",  # Padded
            "task-11.json",  # Unpadded
            "task-100.json",  # Both formats align here
        ]

        manifest_content = {
            "expectedArtifacts": {"file": "test.py", "contains": []},
            "creatableFiles": ["test.py"],
        }

        for filename in manifests_to_create:
            path = manifest_dir / filename
            with open(path, "w") as f:
                json.dump(manifest_content, f)

        # Mock the manifest directory
        import validators.manifest_validator as mv

        original_path = mv.Path
        mv.Path = lambda x: manifest_dir if x == "manifests" else original_path(x)

        try:
            manifests = _discover_related_manifests("test.py")
            # Should sort numerically regardless of padding
            assert len(manifests) == 5
            assert "task-001" in manifests[0]  # 1
            assert "task-2" in manifests[1]  # 2
            assert "task-010" in manifests[2]  # 10
            assert "task-11" in manifests[3]  # 11
            assert "task-100" in manifests[4]  # 100
        finally:
            mv.Path = original_path
