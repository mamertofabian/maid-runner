"""Tests for snapshot generator functionality."""

import json
import tempfile
from pathlib import Path
import pytest

from snapshot_generator import SnapshotGenerator, ArtifactExtractor, generate_all_snapshots
from validators.manifest_validator import _get_active_manifests


class TestSupersedesLogic:
    """Test supersedes filtering and validation."""

    def test_no_supersedes_returns_all_manifests(self, tmp_path):
        """Test that manifests without supersedes are all considered active."""
        # Create test manifests
        manifest1 = tmp_path / "task-001.json"
        manifest2 = tmp_path / "task-002.json"

        manifest1.write_text(json.dumps({
            "goal": "Task 1",
            "supersedes": [],
            "readonlyFiles": [],
            "expectedArtifacts": {"file": "test.py", "contains": []},
            "validationCommand": ["pytest"]
        }))

        manifest2.write_text(json.dumps({
            "goal": "Task 2",
            "supersedes": [],
            "readonlyFiles": [],
            "expectedArtifacts": {"file": "test.py", "contains": []},
            "validationCommand": ["pytest"]
        }))

        paths = [str(manifest1), str(manifest2)]
        active = _get_active_manifests(paths)

        assert len(active) == 2
        assert str(manifest1) in active
        assert str(manifest2) in active

    def test_supersedes_filters_out_old_manifests(self, tmp_path):
        """Test that superseded manifests are filtered out."""
        # Create test manifests
        manifest1 = tmp_path / "task-001.json"
        manifest2 = tmp_path / "task-002.json"
        manifest3 = tmp_path / "task-003-snapshot.json"

        manifest1.write_text(json.dumps({
            "goal": "Task 1",
            "supersedes": [],
            "readonlyFiles": [],
            "expectedArtifacts": {"file": "test.py", "contains": []},
            "validationCommand": ["pytest"]
        }))

        manifest2.write_text(json.dumps({
            "goal": "Task 2",
            "supersedes": [],
            "readonlyFiles": [],
            "expectedArtifacts": {"file": "test.py", "contains": []},
            "validationCommand": ["pytest"]
        }))

        manifest3.write_text(json.dumps({
            "goal": "Snapshot",
            "supersedes": [str(manifest1), str(manifest2)],
            "readonlyFiles": [],
            "expectedArtifacts": {"file": "test.py", "contains": []},
            "validationCommand": ["pytest"]
        }))

        paths = [str(manifest1), str(manifest2), str(manifest3)]
        active = _get_active_manifests(paths)

        assert len(active) == 1
        assert str(manifest3) in active
        assert str(manifest1) not in active
        assert str(manifest2) not in active

    def test_circular_supersedes_raises_error(self, tmp_path):
        """Test that circular supersedes relationships are detected."""
        manifest1 = tmp_path / "task-001.json"
        manifest2 = tmp_path / "task-002.json"

        manifest1.write_text(json.dumps({
            "goal": "Task 1",
            "supersedes": [str(manifest2)],
            "readonlyFiles": [],
            "expectedArtifacts": {"file": "test.py", "contains": []},
            "validationCommand": ["pytest"]
        }))

        manifest2.write_text(json.dumps({
            "goal": "Task 2",
            "supersedes": [str(manifest1)],
            "readonlyFiles": [],
            "expectedArtifacts": {"file": "test.py", "contains": []},
            "validationCommand": ["pytest"]
        }))

        paths = [str(manifest1), str(manifest2)]

        with pytest.raises(ValueError, match="Circular supersedes"):
            _get_active_manifests(paths)

    def test_partial_supersedes_chain(self, tmp_path):
        """Test snapshot supersedes some but not all manifests."""
        manifest1 = tmp_path / "task-001.json"
        manifest2 = tmp_path / "task-002.json"
        manifest3 = tmp_path / "task-003-snapshot.json"
        manifest4 = tmp_path / "task-004.json"

        manifest1.write_text(json.dumps({
            "goal": "Task 1",
            "supersedes": [],
            "readonlyFiles": [],
            "expectedArtifacts": {"file": "test.py", "contains": []},
            "validationCommand": ["pytest"]
        }))

        manifest2.write_text(json.dumps({
            "goal": "Task 2",
            "supersedes": [],
            "readonlyFiles": [],
            "expectedArtifacts": {"file": "test.py", "contains": []},
            "validationCommand": ["pytest"]
        }))

        # Snapshot supersedes only task-001 and task-002
        manifest3.write_text(json.dumps({
            "goal": "Snapshot",
            "supersedes": [str(manifest1), str(manifest2)],
            "readonlyFiles": [],
            "expectedArtifacts": {"file": "test.py", "contains": []},
            "validationCommand": ["pytest"]
        }))

        # Task 4 comes after snapshot
        manifest4.write_text(json.dumps({
            "goal": "Task 4",
            "supersedes": [],
            "readonlyFiles": [],
            "expectedArtifacts": {"file": "test.py", "contains": []},
            "validationCommand": ["pytest"]
        }))

        paths = [str(manifest1), str(manifest2), str(manifest3), str(manifest4)]
        active = _get_active_manifests(paths)

        assert len(active) == 2
        assert str(manifest3) in active
        assert str(manifest4) in active
        assert str(manifest1) not in active
        assert str(manifest2) not in active


class TestArtifactExtractor:
    """Test artifact extraction from Python code."""

    def test_extracts_class_definition(self):
        """Test extraction of class definition."""
        code = """
class MyClass:
    pass
"""
        tree = __import__('ast').parse(code)
        extractor = ArtifactExtractor()
        extractor.visit(tree)

        assert len(extractor.artifacts) == 1
        assert extractor.artifacts[0]["type"] == "class"
        assert extractor.artifacts[0]["name"] == "MyClass"

    def test_extracts_class_with_bases(self):
        """Test extraction of class with base classes."""
        code = """
class MyClass(BaseClass, Mixin):
    pass
"""
        tree = __import__('ast').parse(code)
        extractor = ArtifactExtractor()
        extractor.visit(tree)

        assert len(extractor.artifacts) == 1
        assert extractor.artifacts[0]["bases"] == ["BaseClass", "Mixin"]

    def test_extracts_function_definition(self):
        """Test extraction of function definition."""
        code = """
def my_function():
    pass
"""
        tree = __import__('ast').parse(code)
        extractor = ArtifactExtractor()
        extractor.visit(tree)

        assert len(extractor.artifacts) == 1
        assert extractor.artifacts[0]["type"] == "function"
        assert extractor.artifacts[0]["name"] == "my_function"

    def test_extracts_function_with_parameters(self):
        """Test extraction of function with parameters and types."""
        code = """
def my_function(name: str, count: int) -> bool:
    pass
"""
        tree = __import__('ast').parse(code)
        extractor = ArtifactExtractor()
        extractor.visit(tree)

        assert len(extractor.artifacts) == 1
        artifact = extractor.artifacts[0]
        assert artifact["parameters"] == [
            {"name": "name", "type": "str"},
            {"name": "count", "type": "int"}
        ]
        assert artifact["returns"] == "bool"

    def test_extracts_method_in_class(self):
        """Test extraction of class method."""
        code = """
class MyClass:
    def my_method(self, value: int):
        pass
"""
        tree = __import__('ast').parse(code)
        extractor = ArtifactExtractor()
        extractor.visit(tree)

        # Should have class and method
        assert len(extractor.artifacts) == 2

        method = [a for a in extractor.artifacts if a["type"] == "function"][0]
        assert method["name"] == "my_method"
        assert method["class"] == "MyClass"
        assert method["parameters"] == [{"name": "value", "type": "int"}]

    def test_ignores_private_artifacts(self):
        """Test that private (underscore-prefixed) artifacts are ignored."""
        code = """
class _PrivateClass:
    pass

def _private_function():
    pass

class PublicClass:
    def _private_method(self):
        pass
"""
        tree = __import__('ast').parse(code)
        extractor = ArtifactExtractor()
        extractor.visit(tree)

        # Should only have PublicClass
        assert len(extractor.artifacts) == 1
        assert extractor.artifacts[0]["name"] == "PublicClass"

    def test_extracts_module_level_attributes(self):
        """Test extraction of module-level attributes."""
        code = """
MY_CONSTANT = 42
ANOTHER_VALUE = "hello"
"""
        tree = __import__('ast').parse(code)
        extractor = ArtifactExtractor()
        extractor.visit(tree)

        assert len(extractor.artifacts) == 2
        names = [a["name"] for a in extractor.artifacts]
        assert "MY_CONSTANT" in names
        assert "ANOTHER_VALUE" in names


class TestSnapshotGenerator:
    """Test snapshot generation functionality."""

    def test_generates_snapshot_for_file_with_manifests(self, tmp_path):
        """Test snapshot generation for a file with existing manifests."""
        # Create a simple Python file
        test_file = tmp_path / "test_module.py"
        test_file.write_text("""
def hello():
    pass

class MyClass:
    pass
""")

        # Create manifests directory
        manifests_dir = tmp_path / "manifests"
        manifests_dir.mkdir()

        # Create some manifests for this file
        manifest1 = manifests_dir / "task-001.json"
        manifest1.write_text(json.dumps({
            "goal": "Add hello function",
            "supersedes": [],
            "creatableFiles": [],
            "editableFiles": [str(test_file)],
            "readonlyFiles": [],
            "expectedArtifacts": {
                "file": str(test_file),
                "contains": [{"type": "function", "name": "hello"}]
            },
            "validationCommand": ["pytest"]
        }))

        manifest2 = manifests_dir / "task-002.json"
        manifest2.write_text(json.dumps({
            "goal": "Add MyClass",
            "supersedes": [],
            "creatableFiles": [],
            "editableFiles": [str(test_file)],
            "readonlyFiles": [],
            "expectedArtifacts": {
                "file": str(test_file),
                "contains": [{"type": "class", "name": "MyClass"}]
            },
            "validationCommand": ["pytest"]
        }))

        # Generate snapshot
        generator = SnapshotGenerator(str(test_file), str(manifests_dir))
        snapshot = generator.generate_snapshot(dry_run=True)

        # Verify snapshot structure
        assert snapshot["taskType"] == "snapshot"
        assert len(snapshot["supersedes"]) == 2
        assert snapshot["expectedArtifacts"]["file"] == str(test_file)

        # Should contain both artifacts
        artifacts = snapshot["expectedArtifacts"]["contains"]
        artifact_names = [a["name"] for a in artifacts]
        assert "hello" in artifact_names
        assert "MyClass" in artifact_names

    def test_generates_legacy_snapshot(self, tmp_path):
        """Test snapshot generation for legacy code with no manifests."""
        # Create a Python file
        test_file = tmp_path / "legacy_module.py"
        test_file.write_text("""
def legacy_function(x: int) -> str:
    return str(x)

class LegacyClass:
    def method(self):
        pass
""")

        # Create manifests directory (but no manifests for this file)
        manifests_dir = tmp_path / "manifests"
        manifests_dir.mkdir()

        # Generate legacy snapshot
        generator = SnapshotGenerator(str(test_file), str(manifests_dir))
        snapshot = generator.generate_legacy_snapshot(dry_run=True)

        # Verify snapshot structure
        assert snapshot["taskType"] == "snapshot"
        assert snapshot["supersedes"] == []  # No previous manifests
        assert snapshot["snapshotMetadata"]["isLegacyOnboarding"] is True

        # Should extract artifacts from code
        artifacts = snapshot["expectedArtifacts"]["contains"]
        artifact_names = [a["name"] for a in artifacts]
        assert "legacy_function" in artifact_names
        assert "LegacyClass" in artifact_names

    def test_snapshot_validates_against_implementation(self, tmp_path):
        """Test that generated snapshot validates against current code."""
        # Create a Python file
        test_file = tmp_path / "validate_module.py"
        test_file.write_text("""
def my_function():
    pass
""")

        manifests_dir = tmp_path / "manifests"
        manifests_dir.mkdir()

        # Create manifest
        manifest = manifests_dir / "task-001.json"
        manifest.write_text(json.dumps({
            "goal": "Add function",
            "supersedes": [],
            "creatableFiles": [],
            "editableFiles": [str(test_file)],
            "readonlyFiles": [],
            "expectedArtifacts": {
                "file": str(test_file),
                "contains": [{"type": "function", "name": "my_function"}]
            },
            "validationCommand": ["pytest"]
        }))

        # Generate and validate snapshot (should not raise)
        generator = SnapshotGenerator(str(test_file), str(manifests_dir))
        snapshot = generator.generate_snapshot(dry_run=True)

        # Snapshot should be valid
        assert "my_function" in [a["name"] for a in snapshot["expectedArtifacts"]["contains"]]

    def test_snapshot_includes_metadata(self, tmp_path):
        """Test that snapshot includes proper metadata."""
        test_file = tmp_path / "meta_module.py"
        test_file.write_text("def foo(): pass")

        manifests_dir = tmp_path / "manifests"
        manifests_dir.mkdir()

        manifest = manifests_dir / "task-001.json"
        manifest.write_text(json.dumps({
            "goal": "Test",
            "supersedes": [],
            "creatableFiles": [],
            "editableFiles": [str(test_file)],
            "readonlyFiles": [],
            "expectedArtifacts": {
                "file": str(test_file),
                "contains": [{"type": "function", "name": "foo"}]
            },
            "validationCommand": ["pytest"]
        }))

        generator = SnapshotGenerator(str(test_file), str(manifests_dir))
        snapshot = generator.generate_snapshot(dry_run=True)

        # Check metadata
        assert "snapshotMetadata" in snapshot
        metadata = snapshot["snapshotMetadata"]
        assert "generatedAt" in metadata
        assert "generatedBy" in metadata
        assert metadata["generatedBy"] == "snapshot-generator"
        assert "manifestsSuperseded" in metadata
        assert metadata["manifestsSuperseded"] == 1


class TestSnapshotIntegration:
    """Integration tests for snapshot functionality."""

    def test_snapshot_then_new_task_workflow(self, tmp_path):
        """Test that a snapshot + new task workflow works correctly."""
        # Create file and manifests
        test_file = tmp_path / "workflow_module.py"
        test_file.write_text("""
def original_function():
    pass

class OriginalClass:
    pass

def new_function():
    pass
""")

        manifests_dir = tmp_path / "manifests"
        manifests_dir.mkdir()

        # Create original manifests
        manifest1 = manifests_dir / "task-001.json"
        manifest1.write_text(json.dumps({
            "goal": "Original",
            "supersedes": [],
            "creatableFiles": [],
            "editableFiles": [str(test_file)],
            "readonlyFiles": [],
            "expectedArtifacts": {
                "file": str(test_file),
                "contains": [
                    {"type": "function", "name": "original_function"},
                    {"type": "class", "name": "OriginalClass"}
                ]
            },
            "validationCommand": ["pytest"]
        }))

        # Generate snapshot
        generator = SnapshotGenerator(str(test_file), str(manifests_dir))
        snapshot = generator.generate_snapshot(dry_run=True)

        # Save snapshot manually for this test
        snapshot_path = manifests_dir / "task-002-snapshot.json"
        with open(snapshot_path, "w") as f:
            json.dump(snapshot, f)

        # Create new task after snapshot
        manifest3 = manifests_dir / "task-003.json"
        manifest3.write_text(json.dumps({
            "goal": "Add new function",
            "supersedes": [],
            "creatableFiles": [],
            "editableFiles": [str(test_file)],
            "readonlyFiles": [],
            "expectedArtifacts": {
                "file": str(test_file),
                "contains": [{"type": "function", "name": "new_function"}]
            },
            "validationCommand": ["pytest"]
        }))

        # Now verify that active manifests = snapshot + new task
        # Re-create generator to get updated manifest list
        generator2 = SnapshotGenerator(str(test_file), str(manifests_dir))
        all_manifests = generator2._discover_manifests_for_file()
        active_manifests = _get_active_manifests(all_manifests)

        # Should have snapshot and task-003, but not task-001 (superseded)
        assert len(active_manifests) == 2
        assert str(snapshot_path) in active_manifests
        assert str(manifest3) in active_manifests
        assert str(manifest1) not in active_manifests


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
