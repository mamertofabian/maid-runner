"""Behavioral tests for Task 104: Manifest Loader.

Tests the load_manifests and load_manifest functions that load and parse
manifest files for knowledge graph building, reusing discover_active_manifests.
"""

import json
import pytest
from pathlib import Path

from maid_runner.graph.builder import load_manifests, load_manifest


class TestLoadManifest:
    """Tests for load_manifest function."""

    def test_load_manifest_returns_dict(self, tmp_path: Path) -> None:
        """load_manifest returns a dictionary from a valid JSON file."""
        manifest_path = tmp_path / "task-001-test.manifest.json"
        manifest_data = {
            "goal": "Test goal",
            "taskType": "create",
            "creatableFiles": ["test.py"],
            "readonlyFiles": [],
            "expectedArtifacts": {"file": "test.py", "contains": []},
            "validationCommand": ["pytest", "tests/"],
        }
        manifest_path.write_text(json.dumps(manifest_data))

        result = load_manifest(manifest_path)

        assert isinstance(result, dict)

    def test_load_manifest_returns_expected_structure(self, tmp_path: Path) -> None:
        """load_manifest returns dict with manifest fields intact."""
        manifest_path = tmp_path / "task-001-test.manifest.json"
        manifest_data = {
            "goal": "Create utility module",
            "taskType": "create",
            "creatableFiles": ["src/utils.py"],
            "readonlyFiles": ["src/base.py"],
            "expectedArtifacts": {
                "file": "src/utils.py",
                "contains": [
                    {"type": "function", "name": "helper", "args": []}
                ],
            },
            "validationCommand": ["pytest", "tests/test_utils.py", "-v"],
        }
        manifest_path.write_text(json.dumps(manifest_data))

        result = load_manifest(manifest_path)

        assert result["goal"] == "Create utility module"
        assert result["taskType"] == "create"
        assert result["creatableFiles"] == ["src/utils.py"]
        assert result["readonlyFiles"] == ["src/base.py"]
        assert result["expectedArtifacts"]["file"] == "src/utils.py"
        assert result["validationCommand"] == ["pytest", "tests/test_utils.py", "-v"]

    def test_load_manifest_with_supersedes(self, tmp_path: Path) -> None:
        """load_manifest correctly loads manifests with supersedes field."""
        manifest_path = tmp_path / "task-002-update.manifest.json"
        manifest_data = {
            "goal": "Update module",
            "taskType": "edit",
            "supersedes": ["task-001-initial.manifest.json"],
            "editableFiles": ["src/module.py"],
            "readonlyFiles": [],
            "expectedArtifacts": {
                "file": "src/module.py",
                "contains": [],
            },
            "validationCommand": ["pytest", "tests/"],
        }
        manifest_path.write_text(json.dumps(manifest_data))

        result = load_manifest(manifest_path)

        assert result["supersedes"] == ["task-001-initial.manifest.json"]

    def test_load_manifest_raises_error_for_nonexistent_file(
        self, tmp_path: Path
    ) -> None:
        """load_manifest raises appropriate error for non-existent file."""
        nonexistent_path = tmp_path / "nonexistent.manifest.json"

        with pytest.raises((FileNotFoundError, OSError)):
            load_manifest(nonexistent_path)

    def test_load_manifest_raises_error_for_invalid_json(
        self, tmp_path: Path
    ) -> None:
        """load_manifest raises error when file contains invalid JSON."""
        invalid_json_path = tmp_path / "task-001-invalid.manifest.json"
        invalid_json_path.write_text("{ invalid json content }")

        with pytest.raises(json.JSONDecodeError):
            load_manifest(invalid_json_path)

    def test_load_manifest_preserves_nested_structures(self, tmp_path: Path) -> None:
        """load_manifest preserves nested artifact structures."""
        manifest_path = tmp_path / "task-001-complex.manifest.json"
        manifest_data = {
            "goal": "Complex manifest",
            "taskType": "create",
            "creatableFiles": ["module.py"],
            "readonlyFiles": [],
            "expectedArtifacts": {
                "file": "module.py",
                "contains": [
                    {
                        "type": "class",
                        "name": "MyClass",
                    },
                    {
                        "type": "function",
                        "name": "my_method",
                        "class": "MyClass",
                        "args": [
                            {"name": "self", "type": ""},
                            {"name": "value", "type": "int"},
                        ],
                        "returns": "str",
                    },
                ],
            },
            "validationCommand": ["pytest", "tests/"],
        }
        manifest_path.write_text(json.dumps(manifest_data))

        result = load_manifest(manifest_path)

        contains = result["expectedArtifacts"]["contains"]
        assert len(contains) == 2
        assert contains[0]["type"] == "class"
        assert contains[0]["name"] == "MyClass"
        assert contains[1]["type"] == "function"
        assert contains[1]["name"] == "my_method"
        assert contains[1]["class"] == "MyClass"
        assert contains[1]["args"][1]["name"] == "value"
        assert contains[1]["args"][1]["type"] == "int"
        assert contains[1]["returns"] == "str"

    def test_load_manifest_accepts_path_object(self, tmp_path: Path) -> None:
        """load_manifest accepts Path object as argument."""
        manifest_path = tmp_path / "task-001.manifest.json"
        manifest_data = {"goal": "Test", "readonlyFiles": []}
        manifest_path.write_text(json.dumps(manifest_data))

        # Should accept Path without error
        result = load_manifest(manifest_path)

        assert result["goal"] == "Test"


class TestLoadManifests:
    """Tests for load_manifests function."""

    def test_load_manifests_returns_list(self, tmp_path: Path) -> None:
        """load_manifests returns a list."""
        manifest_dir = tmp_path / "manifests"
        manifest_dir.mkdir()

        result = load_manifests(manifest_dir)

        assert isinstance(result, list)

    def test_load_manifests_empty_directory(self, tmp_path: Path) -> None:
        """load_manifests returns empty list for empty directory."""
        manifest_dir = tmp_path / "manifests"
        manifest_dir.mkdir()

        result = load_manifests(manifest_dir)

        assert result == []

    def test_load_manifests_loads_multiple_manifests(self, tmp_path: Path) -> None:
        """load_manifests loads all manifests from directory."""
        manifest_dir = tmp_path / "manifests"
        manifest_dir.mkdir()

        # Create multiple manifests
        for i in range(1, 4):
            manifest_path = manifest_dir / f"task-{i:03d}-test.manifest.json"
            manifest_data = {
                "goal": f"Task {i}",
                "taskType": "create",
                "creatableFiles": [f"file{i}.py"],
                "readonlyFiles": [],
                "expectedArtifacts": {"file": f"file{i}.py", "contains": []},
                "validationCommand": ["pytest"],
            }
            manifest_path.write_text(json.dumps(manifest_data))

        result = load_manifests(manifest_dir)

        assert len(result) == 3
        goals = [m["goal"] for m in result]
        assert "Task 1" in goals
        assert "Task 2" in goals
        assert "Task 3" in goals

    def test_load_manifests_returns_dicts(self, tmp_path: Path) -> None:
        """load_manifests returns list of dictionaries."""
        manifest_dir = tmp_path / "manifests"
        manifest_dir.mkdir()

        manifest_path = manifest_dir / "task-001-test.manifest.json"
        manifest_data = {
            "goal": "Test",
            "readonlyFiles": [],
            "expectedArtifacts": {"file": "test.py", "contains": []},
            "validationCommand": ["pytest"],
        }
        manifest_path.write_text(json.dumps(manifest_data))

        result = load_manifests(manifest_dir)

        assert len(result) == 1
        assert isinstance(result[0], dict)

    def test_load_manifests_excludes_superseded(self, tmp_path: Path) -> None:
        """load_manifests excludes superseded manifests via discover_active_manifests."""
        manifest_dir = tmp_path / "manifests"
        manifest_dir.mkdir()

        # Create manifest that will be superseded
        manifest_001 = manifest_dir / "task-001-original.manifest.json"
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

        # Create manifest that supersedes the first one
        manifest_002 = manifest_dir / "task-002-replacement.manifest.json"
        manifest_002.write_text(
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

        result = load_manifests(manifest_dir)

        # Should only return the non-superseded manifest
        assert len(result) == 1
        assert result[0]["goal"] == "Replacement task"

    def test_load_manifests_preserves_chronological_order(
        self, tmp_path: Path
    ) -> None:
        """load_manifests returns manifests in chronological order."""
        manifest_dir = tmp_path / "manifests"
        manifest_dir.mkdir()

        # Create manifests out of order
        for task_num in [5, 1, 10, 3]:
            manifest_path = manifest_dir / f"task-{task_num:03d}-test.manifest.json"
            manifest_data = {
                "goal": f"Task {task_num}",
                "readonlyFiles": [],
                "expectedArtifacts": {"file": "test.py", "contains": []},
                "validationCommand": ["pytest"],
            }
            manifest_path.write_text(json.dumps(manifest_data))

        result = load_manifests(manifest_dir)

        # Should be in chronological order: 1, 3, 5, 10
        goals = [m["goal"] for m in result]
        assert goals == ["Task 1", "Task 3", "Task 5", "Task 10"]

    def test_load_manifests_with_invalid_directory(self, tmp_path: Path) -> None:
        """load_manifests handles non-existent directory appropriately."""
        invalid_dir = tmp_path / "nonexistent_manifests"

        # Depending on implementation, this could return empty list or raise error
        # Testing that it handles the case without crashing
        try:
            result = load_manifests(invalid_dir)
            # If it returns, it should be an empty list
            assert result == []
        except (FileNotFoundError, OSError):
            # Raising an error is also acceptable
            pass

    def test_load_manifests_ignores_non_manifest_files(self, tmp_path: Path) -> None:
        """load_manifests only loads task manifest files, ignoring others."""
        manifest_dir = tmp_path / "manifests"
        manifest_dir.mkdir()

        # Create a valid manifest
        manifest_001 = manifest_dir / "task-001-valid.manifest.json"
        manifest_001.write_text(
            json.dumps(
                {
                    "goal": "Valid manifest",
                    "readonlyFiles": [],
                    "expectedArtifacts": {"file": "test.py", "contains": []},
                    "validationCommand": ["pytest"],
                }
            )
        )

        # Create non-manifest files
        (manifest_dir / "README.md").write_text("# Documentation")
        (manifest_dir / "config.json").write_text('{"setting": true}')
        (manifest_dir / "other.manifest.json").write_text('{"goal": "Not a task"}')

        result = load_manifests(manifest_dir)

        assert len(result) == 1
        assert result[0]["goal"] == "Valid manifest"

    def test_load_manifests_handles_complex_supersession(
        self, tmp_path: Path
    ) -> None:
        """load_manifests correctly handles chain of supersessions."""
        manifest_dir = tmp_path / "manifests"
        manifest_dir.mkdir()

        # Create a chain: 001 -> 002 supersedes 001 -> 003 supersedes 002
        manifest_001 = manifest_dir / "task-001-original.manifest.json"
        manifest_001.write_text(
            json.dumps(
                {
                    "goal": "Original",
                    "readonlyFiles": [],
                    "expectedArtifacts": {"file": "test.py", "contains": []},
                    "validationCommand": ["pytest"],
                }
            )
        )

        manifest_002 = manifest_dir / "task-002-middle.manifest.json"
        manifest_002.write_text(
            json.dumps(
                {
                    "goal": "Middle",
                    "supersedes": ["task-001-original.manifest.json"],
                    "readonlyFiles": [],
                    "expectedArtifacts": {"file": "test.py", "contains": []},
                    "validationCommand": ["pytest"],
                }
            )
        )

        manifest_003 = manifest_dir / "task-003-final.manifest.json"
        manifest_003.write_text(
            json.dumps(
                {
                    "goal": "Final",
                    "supersedes": ["task-002-middle.manifest.json"],
                    "readonlyFiles": [],
                    "expectedArtifacts": {"file": "test.py", "contains": []},
                    "validationCommand": ["pytest"],
                }
            )
        )

        result = load_manifests(manifest_dir)

        # Only task-003 should remain active
        assert len(result) == 1
        assert result[0]["goal"] == "Final"

    def test_load_manifests_accepts_path_object(self, tmp_path: Path) -> None:
        """load_manifests accepts Path object as manifest_dir argument."""
        manifest_dir = tmp_path / "manifests"
        manifest_dir.mkdir()

        manifest_path = manifest_dir / "task-001-test.manifest.json"
        manifest_data = {"goal": "Test", "readonlyFiles": []}
        manifest_path.write_text(json.dumps(manifest_data))

        # Should accept Path without error
        result = load_manifests(manifest_dir)

        assert len(result) == 1


class TestLoadManifestsIntegration:
    """Integration tests for load_manifests with discover_active_manifests."""

    def test_load_manifests_uses_discover_active_manifests(
        self, tmp_path: Path
    ) -> None:
        """load_manifests integrates with discover_active_manifests to filter superseded."""
        manifest_dir = tmp_path / "manifests"
        manifest_dir.mkdir()

        # Create manifests where one supersedes another
        manifest_001 = manifest_dir / "task-001-superseded.manifest.json"
        manifest_001.write_text(
            json.dumps(
                {
                    "goal": "Superseded task",
                    "readonlyFiles": [],
                    "expectedArtifacts": {"file": "old.py", "contains": []},
                    "validationCommand": ["pytest"],
                }
            )
        )

        manifest_002 = manifest_dir / "task-002-active.manifest.json"
        manifest_002.write_text(
            json.dumps(
                {
                    "goal": "Active task",
                    "readonlyFiles": [],
                    "expectedArtifacts": {"file": "new.py", "contains": []},
                    "validationCommand": ["pytest"],
                }
            )
        )

        manifest_003 = manifest_dir / "task-003-supersedes.manifest.json"
        manifest_003.write_text(
            json.dumps(
                {
                    "goal": "Task that supersedes 001",
                    "supersedes": ["task-001-superseded.manifest.json"],
                    "readonlyFiles": [],
                    "expectedArtifacts": {"file": "replacement.py", "contains": []},
                    "validationCommand": ["pytest"],
                }
            )
        )

        result = load_manifests(manifest_dir)

        # Should have 002 and 003, but not 001
        goals = [m["goal"] for m in result]
        assert len(result) == 2
        assert "Superseded task" not in goals
        assert "Active task" in goals
        assert "Task that supersedes 001" in goals

    def test_load_manifests_handles_skip_invalid_json(self, tmp_path: Path) -> None:
        """load_manifests skips manifests with invalid JSON (via discover_active_manifests)."""
        manifest_dir = tmp_path / "manifests"
        manifest_dir.mkdir()

        # Create a valid manifest
        manifest_001 = manifest_dir / "task-001-valid.manifest.json"
        manifest_001.write_text(
            json.dumps(
                {
                    "goal": "Valid manifest",
                    "readonlyFiles": [],
                    "expectedArtifacts": {"file": "test.py", "contains": []},
                    "validationCommand": ["pytest"],
                }
            )
        )

        # Create an invalid JSON manifest
        manifest_002 = manifest_dir / "task-002-invalid.manifest.json"
        manifest_002.write_text("{ this is not valid JSON }")

        result = load_manifests(manifest_dir)

        # Should only return the valid manifest
        assert len(result) == 1
        assert result[0]["goal"] == "Valid manifest"
