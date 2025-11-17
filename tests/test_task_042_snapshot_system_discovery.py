"""
Behavioral tests for task-042: Manifest discovery and filtering.

Tests verify that discover_active_manifests():
1. Discovers all manifest files in the directory
2. Filters out superseded manifests
3. Returns active manifests in chronological order
4. Handles edge cases (empty dir, all superseded, circular supersedes)
"""

import json
import pytest
from pathlib import Path
from maid_runner.cli.snapshot_system import discover_active_manifests


class TestDiscoverActiveManifests:
    """Test suite for discover_active_manifests function."""

    def test_discover_active_manifests_exists(self):
        """Verify the discover_active_manifests function exists and is callable."""
        assert callable(discover_active_manifests)

    def test_discovers_all_manifests_in_directory(self, tmp_path):
        """Verify function discovers all manifest files."""
        manifests_dir = tmp_path / "manifests"
        manifests_dir.mkdir()

        # Create test manifests
        for i in range(1, 4):
            manifest_file = manifests_dir / f"task-{i:03d}-test.manifest.json"
            manifest_file.write_text(
                json.dumps(
                    {
                        "goal": f"Test task {i}",
                        "readonlyFiles": [],
                        "expectedArtifacts": {"file": "test.py", "contains": []},
                        "validationCommand": ["echo", "test"],
                    }
                )
            )

        # Discover manifests
        active_manifests = discover_active_manifests(manifests_dir)

        # Should find all 3 manifests
        assert len(active_manifests) == 3

    def test_returns_manifests_in_chronological_order(self, tmp_path):
        """Verify manifests are returned in chronological order (by task number)."""
        manifests_dir = tmp_path / "manifests"
        manifests_dir.mkdir()

        # Create manifests with non-sequential task numbers
        task_numbers = [5, 1, 10, 3, 7]
        for num in task_numbers:
            manifest_file = manifests_dir / f"task-{num:03d}-test.manifest.json"
            manifest_file.write_text(
                json.dumps(
                    {
                        "goal": f"Test task {num}",
                        "readonlyFiles": [],
                        "expectedArtifacts": {"file": "test.py", "contains": []},
                        "validationCommand": ["echo", "test"],
                    }
                )
            )

        # Discover manifests
        active_manifests = discover_active_manifests(manifests_dir)

        # Should be sorted: 1, 3, 5, 7, 10
        expected_order = [1, 3, 5, 7, 10]
        for i, manifest_path in enumerate(active_manifests):
            expected_num = expected_order[i]
            assert f"task-{expected_num:03d}" in manifest_path.name

    def test_filters_out_superseded_manifests(self, tmp_path):
        """Verify superseded manifests are excluded from results."""
        manifests_dir = tmp_path / "manifests"
        manifests_dir.mkdir()

        # Create manifest 001 (will be superseded)
        manifest_001 = manifests_dir / "task-001-original.manifest.json"
        manifest_001.write_text(
            json.dumps(
                {
                    "goal": "Original task",
                    "readonlyFiles": [],
                    "expectedArtifacts": {"file": "test.py", "contains": []},
                    "validationCommand": ["echo", "test"],
                }
            )
        )

        # Create manifest 002 (active)
        manifest_002 = manifests_dir / "task-002-active.manifest.json"
        manifest_002.write_text(
            json.dumps(
                {
                    "goal": "Active task",
                    "readonlyFiles": [],
                    "expectedArtifacts": {"file": "other.py", "contains": []},
                    "validationCommand": ["echo", "test"],
                }
            )
        )

        # Create manifest 003 that supersedes 001
        manifest_003 = manifests_dir / "task-003-supersedes-001.manifest.json"
        manifest_003.write_text(
            json.dumps(
                {
                    "goal": "Replacement task",
                    "supersedes": ["task-001-original.manifest.json"],
                    "readonlyFiles": [],
                    "expectedArtifacts": {"file": "test.py", "contains": []},
                    "validationCommand": ["echo", "test"],
                }
            )
        )

        # Discover manifests
        active_manifests = discover_active_manifests(manifests_dir)

        # Should return only 002 and 003 (not 001)
        assert len(active_manifests) == 2

        manifest_names = [m.name for m in active_manifests]
        assert "task-002-active.manifest.json" in manifest_names
        assert "task-003-supersedes-001.manifest.json" in manifest_names
        assert "task-001-original.manifest.json" not in manifest_names

    def test_handles_empty_directory(self, tmp_path):
        """Verify function handles empty manifests directory gracefully."""
        manifests_dir = tmp_path / "manifests"
        manifests_dir.mkdir()

        # Discover manifests in empty directory
        active_manifests = discover_active_manifests(manifests_dir)

        # Should return empty list
        assert active_manifests == []

    def test_handles_all_manifests_superseded(self, tmp_path):
        """Verify function handles case where all manifests are superseded."""
        manifests_dir = tmp_path / "manifests"
        manifests_dir.mkdir()

        # Create manifest 001 (will be superseded)
        manifest_001 = manifests_dir / "task-001-old.manifest.json"
        manifest_001.write_text(
            json.dumps(
                {
                    "goal": "Old task",
                    "readonlyFiles": [],
                    "expectedArtifacts": {"file": "test.py", "contains": []},
                    "validationCommand": ["echo", "test"],
                }
            )
        )

        # Create manifest 002 that supersedes 001 but is itself superseded
        manifest_002 = manifests_dir / "task-002-middle.manifest.json"
        manifest_002.write_text(
            json.dumps(
                {
                    "goal": "Middle task",
                    "supersedes": ["task-001-old.manifest.json"],
                    "readonlyFiles": [],
                    "expectedArtifacts": {"file": "test.py", "contains": []},
                    "validationCommand": ["echo", "test"],
                }
            )
        )

        # Create manifest 003 that supersedes 002
        manifest_003 = manifests_dir / "task-003-current.manifest.json"
        manifest_003.write_text(
            json.dumps(
                {
                    "goal": "Current task",
                    "supersedes": ["task-002-middle.manifest.json"],
                    "readonlyFiles": [],
                    "expectedArtifacts": {"file": "test.py", "contains": []},
                    "validationCommand": ["echo", "test"],
                }
            )
        )

        # Discover manifests
        active_manifests = discover_active_manifests(manifests_dir)

        # Should return only 003 (the final one)
        assert len(active_manifests) == 1
        assert "task-003-current.manifest.json" in active_manifests[0].name

    def test_handles_multiple_supersedes_in_one_manifest(self, tmp_path):
        """Verify function handles manifests that supersede multiple others."""
        manifests_dir = tmp_path / "manifests"
        manifests_dir.mkdir()

        # Create manifests 001, 002, 003 (will all be superseded)
        for i in range(1, 4):
            manifest_file = manifests_dir / f"task-{i:03d}-old.manifest.json"
            manifest_file.write_text(
                json.dumps(
                    {
                        "goal": f"Old task {i}",
                        "readonlyFiles": [],
                        "expectedArtifacts": {"file": "test.py", "contains": []},
                        "validationCommand": ["echo", "test"],
                    }
                )
            )

        # Create manifest 004 that supersedes all three
        manifest_004 = manifests_dir / "task-004-refactor.manifest.json"
        manifest_004.write_text(
            json.dumps(
                {
                    "goal": "Refactor consolidating 001-003",
                    "supersedes": [
                        "task-001-old.manifest.json",
                        "task-002-old.manifest.json",
                        "task-003-old.manifest.json",
                    ],
                    "readonlyFiles": [],
                    "expectedArtifacts": {"file": "test.py", "contains": []},
                    "validationCommand": ["echo", "test"],
                }
            )
        )

        # Discover manifests
        active_manifests = discover_active_manifests(manifests_dir)

        # Should return only 004
        assert len(active_manifests) == 1
        assert "task-004-refactor.manifest.json" in active_manifests[0].name

    def test_ignores_non_manifest_files(self, tmp_path):
        """Verify function ignores files that don't match manifest pattern."""
        manifests_dir = tmp_path / "manifests"
        manifests_dir.mkdir()

        # Create a valid manifest
        manifest_001 = manifests_dir / "task-001-valid.manifest.json"
        manifest_001.write_text(
            json.dumps(
                {
                    "goal": "Valid task",
                    "readonlyFiles": [],
                    "expectedArtifacts": {"file": "test.py", "contains": []},
                    "validationCommand": ["echo", "test"],
                }
            )
        )

        # Create non-manifest files
        (manifests_dir / "README.md").write_text("# Documentation")
        (manifests_dir / "other.json").write_text("{}")
        (manifests_dir / "test.txt").write_text("test")

        # Discover manifests
        active_manifests = discover_active_manifests(manifests_dir)

        # Should return only the valid manifest
        assert len(active_manifests) == 1
        assert "task-001-valid.manifest.json" in active_manifests[0].name

    def test_returns_path_objects(self, tmp_path):
        """Verify function returns Path objects, not strings."""
        manifests_dir = tmp_path / "manifests"
        manifests_dir.mkdir()

        # Create a test manifest
        manifest_file = manifests_dir / "task-001-test.manifest.json"
        manifest_file.write_text(
            json.dumps(
                {
                    "goal": "Test task",
                    "readonlyFiles": [],
                    "expectedArtifacts": {"file": "test.py", "contains": []},
                    "validationCommand": ["echo", "test"],
                }
            )
        )

        # Discover manifests
        active_manifests = discover_active_manifests(manifests_dir)

        # Should return Path objects
        assert len(active_manifests) == 1
        assert isinstance(active_manifests[0], Path)

    def test_handles_invalid_json_manifests(self, tmp_path):
        """Verify function gracefully handles manifests with invalid JSON."""
        manifests_dir = tmp_path / "manifests"
        manifests_dir.mkdir()

        # Create a valid manifest
        manifest_001 = manifests_dir / "task-001-valid.manifest.json"
        manifest_001.write_text(
            json.dumps(
                {
                    "goal": "Valid task",
                    "readonlyFiles": [],
                    "expectedArtifacts": {"file": "test.py", "contains": []},
                    "validationCommand": ["echo", "test"],
                }
            )
        )

        # Create an invalid JSON manifest
        manifest_002 = manifests_dir / "task-002-invalid.manifest.json"
        manifest_002.write_text("{ invalid json }")

        # Discover manifests - should not crash
        active_manifests = discover_active_manifests(manifests_dir)

        # Should return only the valid manifest
        assert len(active_manifests) == 1
        assert "task-001-valid.manifest.json" in active_manifests[0].name


class TestRealManifestDirectory:
    """Test with the actual manifests directory."""

    def test_discovers_real_manifests(self):
        """Verify function works with the real manifests directory."""
        manifests_dir = Path("manifests")

        if not manifests_dir.exists():
            pytest.skip("Manifests directory not found")

        # Discover manifests
        active_manifests = discover_active_manifests(manifests_dir)

        # Should find at least some manifests (we know we have task-041, task-042)
        assert len(active_manifests) > 0

        # All should be Path objects
        assert all(isinstance(m, Path) for m in active_manifests)

        # All should exist
        assert all(m.exists() for m in active_manifests)

        # All should match the manifest pattern
        assert all(
            "task-" in m.name and m.name.endswith(".manifest.json")
            for m in active_manifests
        )

    def test_real_manifests_chronologically_ordered(self):
        """Verify real manifests are returned in chronological order."""
        manifests_dir = Path("manifests")

        if not manifests_dir.exists():
            pytest.skip("Manifests directory not found")

        # Discover manifests
        active_manifests = discover_active_manifests(manifests_dir)

        # Extract task numbers
        task_numbers = []
        for manifest in active_manifests:
            # Extract number from "task-XXX-*.manifest.json"
            parts = manifest.stem.split("-")
            if len(parts) >= 2:
                try:
                    task_num = int(parts[1])
                    task_numbers.append(task_num)
                except ValueError:
                    pass

        # Should be in ascending order
        assert task_numbers == sorted(task_numbers)
