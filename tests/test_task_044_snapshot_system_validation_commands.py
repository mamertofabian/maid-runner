"""
Behavioral tests for task-044: Implement validation command aggregation.

Tests verify that aggregate_validation_commands():
1. Loads manifests and extracts validation commands
2. Normalizes commands using normalize_validation_commands()
3. Deduplicates identical commands
4. Returns list suitable for validationCommands field
5. Handles edge cases (empty lists, missing commands, etc.)
"""

import json
import pytest
from pathlib import Path

from maid_runner.cli.snapshot_system import aggregate_validation_commands


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
        filename: str, validation_command=None, validation_commands=None
    ) -> Path:
        manifest_path = temp_manifest_dir / filename
        manifest = {
            "version": "1",
            "goal": f"Test manifest for {filename}",
            "taskType": "edit",
            "readonlyFiles": [],
            "expectedArtifacts": {"file": "test.py", "contains": []},
        }

        # Add validation commands
        if validation_commands is not None:
            manifest["validationCommands"] = validation_commands
        elif validation_command is not None:
            manifest["validationCommand"] = validation_command
        else:
            manifest["validationCommand"] = ["pytest", "tests/"]

        with open(manifest_path, "w") as f:
            json.dump(manifest, f, indent=2)
        return manifest_path

    return _create_manifest


class TestAggregateValidationCommands:
    """Test suite for aggregate_validation_commands() function."""

    def test_function_exists(self):
        """Verify aggregate_validation_commands function exists."""
        assert callable(aggregate_validation_commands)

    def test_aggregates_single_manifest_legacy_format(self, create_test_manifest):
        """Verify aggregation works with single manifest using legacy validationCommand."""
        manifest = create_test_manifest(
            "task-001.manifest.json",
            validation_command=["pytest", "tests/test_file.py", "-v"],
        )

        result = aggregate_validation_commands([manifest])

        assert len(result) == 1
        assert result[0] == ["pytest", "tests/test_file.py", "-v"]

    def test_aggregates_single_manifest_enhanced_format(self, create_test_manifest):
        """Verify aggregation works with single manifest using enhanced validationCommands."""
        manifest = create_test_manifest(
            "task-001.manifest.json",
            validation_commands=[
                ["pytest", "tests/test1.py"],
                ["pytest", "tests/test2.py"],
            ],
        )

        result = aggregate_validation_commands([manifest])

        assert len(result) == 2
        assert ["pytest", "tests/test1.py"] in result
        assert ["pytest", "tests/test2.py"] in result

    def test_aggregates_multiple_manifests(self, create_test_manifest):
        """Verify aggregation combines commands from multiple manifests."""
        manifest1 = create_test_manifest(
            "task-001.manifest.json", validation_command=["pytest", "tests/test1.py"]
        )
        manifest2 = create_test_manifest(
            "task-002.manifest.json", validation_command=["pytest", "tests/test2.py"]
        )

        result = aggregate_validation_commands([manifest1, manifest2])

        assert len(result) == 2
        assert ["pytest", "tests/test1.py"] in result
        assert ["pytest", "tests/test2.py"] in result

    def test_deduplicates_identical_commands(self, create_test_manifest):
        """Verify that identical commands are deduplicated."""
        manifest1 = create_test_manifest(
            "task-001.manifest.json", validation_command=["pytest", "tests/"]
        )
        manifest2 = create_test_manifest(
            "task-002.manifest.json", validation_command=["pytest", "tests/"]
        )
        manifest3 = create_test_manifest(
            "task-003.manifest.json", validation_command=["pytest", "tests/"]
        )

        result = aggregate_validation_commands([manifest1, manifest2, manifest3])

        # Should only have one instance of the command
        assert len(result) == 1
        assert result[0] == ["pytest", "tests/"]

    def test_preserves_different_commands(self, create_test_manifest):
        """Verify different commands are all preserved."""
        manifest1 = create_test_manifest(
            "task-001.manifest.json",
            validation_commands=[
                ["pytest", "tests/", "-v"],
                ["make", "lint"],
                ["make", "type-check"],
            ],
        )
        manifest2 = create_test_manifest(
            "task-002.manifest.json",
            validation_commands=[
                ["pytest", "tests/", "-v"],  # Duplicate
                ["make", "format"],  # New
            ],
        )

        result = aggregate_validation_commands([manifest1, manifest2])

        # Should have 4 unique commands (3 from m1, 1 new from m2)
        assert len(result) == 4
        assert ["pytest", "tests/", "-v"] in result
        assert ["make", "lint"] in result
        assert ["make", "type-check"] in result
        assert ["make", "format"] in result

    def test_handles_empty_manifest_list(self):
        """Verify handling of empty manifest list."""
        result = aggregate_validation_commands([])
        assert result == []

    def test_handles_manifest_without_validation_commands(self, temp_manifest_dir):
        """Verify handling of manifests without validation commands."""
        manifest_path = temp_manifest_dir / "task-001.manifest.json"
        manifest = {
            "version": "1",
            "goal": "Test manifest without validation",
            "taskType": "edit",
            "readonlyFiles": [],
            "expectedArtifacts": {"file": "test.py", "contains": []},
            # No validationCommand or validationCommands
        }
        with open(manifest_path, "w") as f:
            json.dump(manifest, f)

        result = aggregate_validation_commands([manifest_path])

        # Should return empty list or skip this manifest
        assert isinstance(result, list)

    def test_handles_mixed_command_formats(self, create_test_manifest):
        """Verify handling of mixed legacy and enhanced formats."""
        manifest1 = create_test_manifest(
            "task-001.manifest.json",
            validation_command=["pytest", "tests/test1.py"],  # Legacy
        )
        manifest2 = create_test_manifest(
            "task-002.manifest.json",
            validation_commands=[  # Enhanced
                ["pytest", "tests/test2.py"],
                ["make", "lint"],
            ],
        )

        result = aggregate_validation_commands([manifest1, manifest2])

        assert len(result) == 3
        assert ["pytest", "tests/test1.py"] in result
        assert ["pytest", "tests/test2.py"] in result
        assert ["make", "lint"] in result

    def test_returns_correct_format(self, create_test_manifest):
        """Verify return value has correct structure for validationCommands."""
        manifest = create_test_manifest(
            "task-001.manifest.json",
            validation_commands=[["pytest", "tests/"], ["make", "test"]],
        )

        result = aggregate_validation_commands([manifest])

        # Should be List[List[str]]
        assert isinstance(result, list)
        for command in result:
            assert isinstance(command, list)
            for part in command:
                assert isinstance(part, str)

    def test_handles_invalid_json_gracefully(self, temp_manifest_dir):
        """Verify handling of manifests with invalid JSON."""
        invalid_manifest = temp_manifest_dir / "task-001.manifest.json"
        with open(invalid_manifest, "w") as f:
            f.write("{invalid json")

        # Should handle gracefully (skip or raise informative error)
        try:
            result = aggregate_validation_commands([invalid_manifest])
            # If it doesn't raise, should return valid list
            assert isinstance(result, list)
        except json.JSONDecodeError:
            # Acceptable to raise if invalid JSON
            pass

    def test_command_order_preserved_within_manifest(self, create_test_manifest):
        """Verify that command order from a single manifest is preserved."""
        manifest = create_test_manifest(
            "task-001.manifest.json",
            validation_commands=[
                ["first", "command"],
                ["second", "command"],
                ["third", "command"],
            ],
        )

        result = aggregate_validation_commands([manifest])

        # Order should be preserved
        assert result[0] == ["first", "command"]
        assert result[1] == ["second", "command"]
        assert result[2] == ["third", "command"]

    def test_deduplication_case_sensitive(self, create_test_manifest):
        """Verify deduplication is case-sensitive."""
        manifest1 = create_test_manifest(
            "task-001.manifest.json",
            validation_command=["pytest", "Tests/"],  # Capital T
        )
        manifest2 = create_test_manifest(
            "task-002.manifest.json",
            validation_command=["pytest", "tests/"],  # Lowercase t
        )

        result = aggregate_validation_commands([manifest1, manifest2])

        # Should have both (case-sensitive)
        assert len(result) == 2
        assert ["pytest", "Tests/"] in result
        assert ["pytest", "tests/"] in result


class TestIntegrationWithRealManifests:
    """Integration tests using real manifests from the project."""

    def test_aggregates_real_project_manifests(self):
        """Verify aggregation works with actual project manifests."""
        from maid_runner.cli.snapshot_system import discover_active_manifests

        manifest_dir = Path("manifests")
        if not manifest_dir.exists():
            pytest.skip("Manifests directory not found")

        # Get first 10 active manifests for testing
        active_manifests = discover_active_manifests(manifest_dir)[:10]

        if not active_manifests:
            pytest.skip("No active manifests found")

        result = aggregate_validation_commands(active_manifests)

        # Should return valid structure
        assert isinstance(result, list)

        for command in result:
            assert isinstance(command, list)
            assert len(command) > 0  # Commands shouldn't be empty
            for part in command:
                assert isinstance(part, str)

    def test_real_manifests_deduplicated(self):
        """Verify real manifests have duplicates removed."""
        from maid_runner.cli.snapshot_system import discover_active_manifests

        manifest_dir = Path("manifests")
        if not manifest_dir.exists():
            pytest.skip("Manifests directory not found")

        active_manifests = discover_active_manifests(manifest_dir)

        if not active_manifests:
            pytest.skip("No active manifests found")

        result = aggregate_validation_commands(active_manifests)

        # Convert to tuples for set comparison
        result_tuples = [tuple(cmd) for cmd in result]

        # Should have no duplicates (length of set equals length of list)
        assert len(set(result_tuples)) == len(result_tuples)
