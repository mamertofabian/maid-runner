"""Test that discover_related_manifests filters out superseded manifests.

This test verifies the fix for the bug where discover_related_manifests was
returning ALL manifests that touch a file, including superseded ones. This
caused manifest chain validation to incorrectly merge artifacts from superseded
manifests, leading to validation failures when active manifests removed artifacts.

Bug scenario:
- task-032 (snapshot) declares artifact A
- task-154 supersedes task-032, removes artifact A
- discover_related_manifests("file.tsx") returned both task-032 and task-154
- Manifest chain merged both, expecting artifact A to still exist
- Validation failed because artifact A was correctly removed

Expected behavior:
- discover_related_manifests should filter out superseded manifests
- Only active manifests should be included in the chain
- Removed artifacts should not cause validation failures
"""

import json
from pathlib import Path

from maid_runner.validators.manifest_validator import discover_related_manifests


class TestDiscoverRelatedManifeststFiltersSuperseded:
    """Test that discover_related_manifests filters out superseded manifests."""

    def test_filters_out_superseded_manifests(self, tmp_path: Path):
        """Verify that superseded manifests are excluded from discovery results."""
        # Create a temporary manifests directory
        manifests_dir = tmp_path / "manifests"
        manifests_dir.mkdir()

        # Create task-001: snapshot with artifact A
        task_001 = {
            "goal": "Snapshot of file.py",
            "taskType": "snapshot",
            "supersedes": [],
            "creatableFiles": [],
            "editableFiles": ["src/file.py"],
            "readonlyFiles": [],
            "expectedArtifacts": {
                "file": "src/file.py",
                "contains": [{"type": "function", "name": "artifact_a"}],
            },
            "validationCommand": [],
        }

        # Create task-002: edit that supersedes task-001, removes artifact A
        task_002 = {
            "goal": "Refactor file.py",
            "taskType": "edit",
            "supersedes": ["task-001-snapshot.manifest.json"],
            "creatableFiles": [],
            "editableFiles": ["src/file.py"],
            "readonlyFiles": [],
            "expectedArtifacts": {
                "file": "src/file.py",
                "contains": [{"type": "function", "name": "artifact_b"}],
            },
            "validationCommand": [],
        }

        # Write manifests
        with open(manifests_dir / "task-001-snapshot.manifest.json", "w") as f:
            json.dump(task_001, f)

        with open(manifests_dir / "task-002-refactor.manifest.json", "w") as f:
            json.dump(task_002, f)

        # Change to tmp_path so discover_related_manifests finds the manifests
        import os

        original_cwd = os.getcwd()
        try:
            os.chdir(tmp_path)

            # Call discover_related_manifests
            related = discover_related_manifests("src/file.py")

            # Verify: should only return task-002, NOT task-001 (superseded)
            assert (
                len(related) == 1
            ), f"Expected 1 manifest, got {len(related)}: {related}"

            # Check that only task-002 is returned
            assert any(
                "task-002" in str(path) for path in related
            ), f"task-002 not found in results: {related}"

            # Check that task-001 is NOT returned
            assert not any(
                "task-001" in str(path) for path in related
            ), f"task-001 (superseded) should not be in results: {related}"

        finally:
            os.chdir(original_cwd)

    def test_includes_all_active_manifests_for_same_file(self, tmp_path: Path):
        """Verify that multiple active manifests for the same file are all included."""
        # Create a temporary manifests directory
        manifests_dir = tmp_path / "manifests"
        manifests_dir.mkdir()

        # Create task-001: creates file with artifact A
        task_001 = {
            "goal": "Create file.py",
            "taskType": "create",
            "supersedes": [],
            "creatableFiles": ["src/file.py"],
            "editableFiles": [],
            "readonlyFiles": [],
            "expectedArtifacts": {
                "file": "src/file.py",
                "contains": [{"type": "function", "name": "artifact_a"}],
            },
            "validationCommand": [],
        }

        # Create task-002: adds artifact B (does NOT supersede task-001)
        task_002 = {
            "goal": "Add feature B",
            "taskType": "edit",
            "supersedes": [],
            "creatableFiles": [],
            "editableFiles": ["src/file.py"],
            "readonlyFiles": [],
            "expectedArtifacts": {
                "file": "src/file.py",
                "contains": [{"type": "function", "name": "artifact_b"}],
            },
            "validationCommand": [],
        }

        # Write manifests
        with open(manifests_dir / "task-001-create.manifest.json", "w") as f:
            json.dump(task_001, f)

        with open(manifests_dir / "task-002-add-feature.manifest.json", "w") as f:
            json.dump(task_002, f)

        # Change to tmp_path
        import os

        original_cwd = os.getcwd()
        try:
            os.chdir(tmp_path)

            # Call discover_related_manifests
            related = discover_related_manifests("src/file.py")

            # Verify: should return BOTH task-001 and task-002 (both active)
            assert (
                len(related) == 2
            ), f"Expected 2 manifests, got {len(related)}: {related}"

            # Check that both are included
            assert any(
                "task-001" in str(path) for path in related
            ), f"task-001 not found in results: {related}"
            assert any(
                "task-002" in str(path) for path in related
            ), f"task-002 not found in results: {related}"

        finally:
            os.chdir(original_cwd)

    def test_handles_chain_of_superseded_manifests(self, tmp_path: Path):
        """Verify that chains of superseded manifests are handled correctly."""
        # Create a temporary manifests directory
        manifests_dir = tmp_path / "manifests"
        manifests_dir.mkdir()

        # Create task-001: initial snapshot
        task_001 = {
            "goal": "Snapshot",
            "taskType": "snapshot",
            "supersedes": [],
            "creatableFiles": [],
            "editableFiles": ["src/file.py"],
            "readonlyFiles": [],
            "expectedArtifacts": {
                "file": "src/file.py",
                "contains": [{"type": "function", "name": "old_func"}],
            },
            "validationCommand": [],
        }

        # Create task-002: supersedes task-001
        task_002 = {
            "goal": "Refactor v1",
            "taskType": "edit",
            "supersedes": ["task-001-snapshot.manifest.json"],
            "creatableFiles": [],
            "editableFiles": ["src/file.py"],
            "readonlyFiles": [],
            "expectedArtifacts": {
                "file": "src/file.py",
                "contains": [{"type": "function", "name": "mid_func"}],
            },
            "validationCommand": [],
        }

        # Create task-003: supersedes task-002
        task_003 = {
            "goal": "Refactor v2",
            "taskType": "edit",
            "supersedes": ["task-002-refactor-v1.manifest.json"],
            "creatableFiles": [],
            "editableFiles": ["src/file.py"],
            "readonlyFiles": [],
            "expectedArtifacts": {
                "file": "src/file.py",
                "contains": [{"type": "function", "name": "new_func"}],
            },
            "validationCommand": [],
        }

        # Write manifests
        with open(manifests_dir / "task-001-snapshot.manifest.json", "w") as f:
            json.dump(task_001, f)

        with open(manifests_dir / "task-002-refactor-v1.manifest.json", "w") as f:
            json.dump(task_002, f)

        with open(manifests_dir / "task-003-refactor-v2.manifest.json", "w") as f:
            json.dump(task_003, f)

        # Change to tmp_path
        import os

        original_cwd = os.getcwd()
        try:
            os.chdir(tmp_path)

            # Call discover_related_manifests
            related = discover_related_manifests("src/file.py")

            # Verify: should only return task-003 (most recent, active)
            assert (
                len(related) == 1
            ), f"Expected 1 manifest, got {len(related)}: {related}"

            # Check that only task-003 is returned
            assert any(
                "task-003" in str(path) for path in related
            ), f"task-003 not found in results: {related}"

            # Check that task-001 and task-002 are NOT returned
            assert not any(
                "task-001" in str(path) for path in related
            ), f"task-001 (superseded) should not be in results: {related}"
            assert not any(
                "task-002" in str(path) for path in related
            ), f"task-002 (superseded) should not be in results: {related}"

        finally:
            os.chdir(original_cwd)
