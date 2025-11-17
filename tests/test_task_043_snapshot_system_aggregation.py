"""
Behavioral tests for task-043: Implement artifact aggregation for system-wide snapshots.

Tests verify that aggregate_system_artifacts():
1. Loads manifests and extracts expectedArtifacts
2. Groups artifacts by source file
3. Returns list of artifact blocks in correct format for systemArtifacts
4. Handles edge cases (empty lists, missing artifacts, etc.)
"""

import json
import pytest
from pathlib import Path
from typing import List, Dict, Any

from maid_runner.cli.snapshot_system import aggregate_system_artifacts


@pytest.fixture
def temp_manifest_dir(tmp_path):
    """Create a temporary directory with test manifests."""
    manifest_dir = tmp_path / "manifests"
    manifest_dir.mkdir()
    return manifest_dir


@pytest.fixture
def create_test_manifest(temp_manifest_dir):
    """Factory fixture for creating test manifests."""

    def _create_manifest(
        filename: str, file_path: str, artifacts: List[Dict[str, Any]]
    ) -> Path:
        manifest_path = temp_manifest_dir / filename
        manifest = {
            "version": "1",
            "goal": f"Test manifest for {filename}",
            "taskType": "edit",
            "readonlyFiles": [],
            "expectedArtifacts": {"file": file_path, "contains": artifacts},
            "validationCommand": ["pytest", "tests/"],
        }
        with open(manifest_path, "w") as f:
            json.dump(manifest, f, indent=2)
        return manifest_path

    return _create_manifest


class TestAggregateSystemArtifacts:
    """Test suite for aggregate_system_artifacts() function."""

    def test_function_exists(self):
        """Verify aggregate_system_artifacts function exists."""
        assert callable(aggregate_system_artifacts)

    def test_aggregates_single_manifest(self, create_test_manifest):
        """Verify aggregation works with a single manifest."""
        manifest_path = create_test_manifest(
            "task-001.manifest.json",
            "module/file1.py",
            [
                {"type": "function", "name": "test_func", "args": []},
                {"type": "class", "name": "TestClass"},
            ],
        )

        result = aggregate_system_artifacts([manifest_path])

        assert len(result) == 1
        assert result[0]["file"] == "module/file1.py"
        assert len(result[0]["contains"]) == 2
        assert result[0]["contains"][0]["name"] == "test_func"
        assert result[0]["contains"][1]["name"] == "TestClass"

    def test_aggregates_multiple_manifests_same_file(self, create_test_manifest):
        """Verify artifacts from multiple manifests for same file are combined."""
        manifest1 = create_test_manifest(
            "task-001.manifest.json",
            "module/file1.py",
            [{"type": "function", "name": "func1"}],
        )
        manifest2 = create_test_manifest(
            "task-002.manifest.json",
            "module/file1.py",
            [{"type": "function", "name": "func2"}],
        )

        result = aggregate_system_artifacts([manifest1, manifest2])

        # Should have one file block with both artifacts
        assert len(result) == 1
        assert result[0]["file"] == "module/file1.py"
        assert len(result[0]["contains"]) == 2

        artifact_names = {a["name"] for a in result[0]["contains"]}
        assert artifact_names == {"func1", "func2"}

    def test_aggregates_multiple_manifests_different_files(self, create_test_manifest):
        """Verify artifacts from different files are in separate blocks."""
        manifest1 = create_test_manifest(
            "task-001.manifest.json",
            "module/file1.py",
            [{"type": "function", "name": "func1"}],
        )
        manifest2 = create_test_manifest(
            "task-002.manifest.json",
            "module/file2.py",
            [{"type": "class", "name": "Class2"}],
        )

        result = aggregate_system_artifacts([manifest1, manifest2])

        # Should have two file blocks
        assert len(result) == 2

        # Sort by file for consistent testing
        result_sorted = sorted(result, key=lambda x: x["file"])

        assert result_sorted[0]["file"] == "module/file1.py"
        assert len(result_sorted[0]["contains"]) == 1
        assert result_sorted[0]["contains"][0]["name"] == "func1"

        assert result_sorted[1]["file"] == "module/file2.py"
        assert len(result_sorted[1]["contains"]) == 1
        assert result_sorted[1]["contains"][0]["name"] == "Class2"

    def test_preserves_artifact_structure(self, create_test_manifest):
        """Verify full artifact structure is preserved (args, returns, etc.)."""
        manifest = create_test_manifest(
            "task-001.manifest.json",
            "module/file1.py",
            [
                {
                    "type": "function",
                    "name": "complex_func",
                    "args": [
                        {"name": "arg1", "type": "str"},
                        {"name": "arg2", "type": "int", "default": "0"},
                    ],
                    "returns": "bool",
                    "description": "A complex function",
                }
            ],
        )

        result = aggregate_system_artifacts([manifest])

        artifact = result[0]["contains"][0]
        assert artifact["type"] == "function"
        assert artifact["name"] == "complex_func"
        assert len(artifact["args"]) == 2
        assert artifact["args"][0]["name"] == "arg1"
        assert artifact["args"][0]["type"] == "str"
        assert artifact["args"][1]["default"] == "0"
        assert artifact["returns"] == "bool"
        assert artifact["description"] == "A complex function"

    def test_handles_empty_manifest_list(self):
        """Verify handling of empty manifest list."""
        result = aggregate_system_artifacts([])
        assert result == []

    def test_handles_manifest_with_no_artifacts(self, create_test_manifest):
        """Verify handling of manifests with empty contains array."""
        manifest = create_test_manifest("task-001.manifest.json", "module/file1.py", [])

        result = aggregate_system_artifacts([manifest])

        # Should still create a file block even with no artifacts
        assert len(result) == 1
        assert result[0]["file"] == "module/file1.py"
        assert result[0]["contains"] == []

    def test_handles_duplicate_artifacts(self, create_test_manifest):
        """Verify handling when same artifact appears in multiple manifests."""
        manifest1 = create_test_manifest(
            "task-001.manifest.json",
            "module/file1.py",
            [{"type": "function", "name": "func1", "args": []}],
        )
        manifest2 = create_test_manifest(
            "task-002.manifest.json",
            "module/file1.py",
            [{"type": "function", "name": "func1", "args": []}],
        )

        result = aggregate_system_artifacts([manifest1, manifest2])

        # Both instances should be included (no deduplication at this level)
        assert len(result) == 1
        assert len(result[0]["contains"]) == 2
        assert result[0]["contains"][0]["name"] == "func1"
        assert result[0]["contains"][1]["name"] == "func1"

    def test_handles_manifest_without_expected_artifacts(self, temp_manifest_dir):
        """Verify handling of manifests that don't have expectedArtifacts."""
        # Create manifest with systemArtifacts instead
        manifest_path = temp_manifest_dir / "task-001.manifest.json"
        manifest = {
            "version": "1",
            "goal": "System snapshot",
            "taskType": "system-snapshot",
            "readonlyFiles": [],
            "systemArtifacts": [
                {"file": "file.py", "contains": [{"type": "function", "name": "f"}]}
            ],
            "validationCommand": ["pytest", "tests/"],
        }
        with open(manifest_path, "w") as f:
            json.dump(manifest, f)

        result = aggregate_system_artifacts([manifest_path])

        # Should return empty or skip this manifest (expectedArtifacts not present)
        # Depending on implementation, this might be [] or raise an exception
        # The function should handle this gracefully
        assert isinstance(result, list)

    def test_returns_correct_format(self, create_test_manifest):
        """Verify return value has correct structure for systemArtifacts."""
        manifest = create_test_manifest(
            "task-001.manifest.json",
            "module/file1.py",
            [{"type": "function", "name": "func"}],
        )

        result = aggregate_system_artifacts([manifest])

        # Should be a list
        assert isinstance(result, list)

        # Each item should have 'file' and 'contains'
        for block in result:
            assert isinstance(block, dict)
            assert "file" in block
            assert "contains" in block
            assert isinstance(block["file"], str)
            assert isinstance(block["contains"], list)

    def test_handles_invalid_json_gracefully(self, temp_manifest_dir):
        """Verify handling of manifests with invalid JSON."""
        invalid_manifest = temp_manifest_dir / "task-001.manifest.json"
        with open(invalid_manifest, "w") as f:
            f.write("{invalid json")

        # Should handle gracefully (skip or raise informative error)
        # Depending on implementation
        try:
            result = aggregate_system_artifacts([invalid_manifest])
            # If it doesn't raise, should return valid list
            assert isinstance(result, list)
        except json.JSONDecodeError:
            # Acceptable to raise if invalid JSON
            pass

    def test_mixed_file_count_manifests(self, create_test_manifest, temp_manifest_dir):
        """Verify aggregation with varying numbers of files per manifest."""
        # Manifest 1: touches file1 and file2
        m1_path = temp_manifest_dir / "task-001.manifest.json"
        m1 = {
            "version": "1",
            "goal": "Multi-file manifest",
            "taskType": "edit",
            "readonlyFiles": [],
            "expectedArtifacts": {
                "file": "file1.py",
                "contains": [{"type": "function", "name": "f1"}],
            },
            "validationCommand": ["pytest", "tests/"],
        }
        with open(m1_path, "w") as f:
            json.dump(m1, f)

        # Manifest 2: touches file2 (different artifacts)
        m2 = create_test_manifest(
            "task-002.manifest.json",
            "file2.py",
            [{"type": "class", "name": "C2"}],
        )

        # Manifest 3: touches file1 again
        m3 = create_test_manifest(
            "task-003.manifest.json",
            "file1.py",
            [{"type": "function", "name": "f3"}],
        )

        result = aggregate_system_artifacts([m1_path, m2, m3])

        # Should have 2 file blocks (file1.py and file2.py)
        assert len(result) == 2

        result_sorted = sorted(result, key=lambda x: x["file"])

        # file1.py should have artifacts from m1 and m3
        assert result_sorted[0]["file"] == "file1.py"
        assert len(result_sorted[0]["contains"]) == 2

        # file2.py should have artifacts from m2
        assert result_sorted[1]["file"] == "file2.py"
        assert len(result_sorted[1]["contains"]) == 1


class TestIntegrationWithRealManifests:
    """Integration tests using real manifests from the project."""

    def test_aggregates_real_project_manifests(self):
        """Verify aggregation works with actual project manifests."""
        from maid_runner.cli.snapshot_system import discover_active_manifests

        manifest_dir = Path("manifests")
        if not manifest_dir.exists():
            pytest.skip("Manifests directory not found")

        # Get first 5 active manifests for testing
        active_manifests = discover_active_manifests(manifest_dir)[:5]

        if not active_manifests:
            pytest.skip("No active manifests found")

        result = aggregate_system_artifacts(active_manifests)

        # Should return valid structure
        assert isinstance(result, list)

        for block in result:
            assert "file" in block
            assert "contains" in block
            assert isinstance(block["file"], str)
            assert isinstance(block["contains"], list)

            # Each artifact should have type and name at minimum
            for artifact in block["contains"]:
                assert "type" in artifact
                assert "name" in artifact
