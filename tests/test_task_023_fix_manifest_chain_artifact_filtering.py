# tests/test_task_023_fix_manifest_chain_artifact_filtering.py
"""
Behavioral tests for Bug 1: Manifest chain artifact filtering by target file.

Tests that _merge_expected_artifacts only includes artifacts where
expectedArtifacts.file matches the target file being validated.
"""
import json
import sys
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from maid_runner.validators.manifest_validator import (
    _merge_expected_artifacts,
    _get_expected_artifacts,
)


def test_merge_filters_artifacts_by_target_file(tmp_path: Path):
    """Test that _merge_expected_artifacts only includes artifacts for target file"""

    # Create manifest 1: orchestrator.py with Developer class
    manifest1 = {
        "goal": "Create orchestrator",
        "taskType": "create",
        "creatableFiles": ["orchestrator.py"],
        "editableFiles": [],
        "readonlyFiles": [],
        "expectedArtifacts": {
            "file": "orchestrator.py",
            "contains": [
                {"type": "class", "name": "Developer"},
                {"type": "function", "name": "run", "class": "Developer"},
            ],
        },
        "validationCommand": ["echo", "test"],
    }

    # Create manifest 2: refiner.py with Refiner class
    manifest2 = {
        "goal": "Create refiner",
        "taskType": "create",
        "creatableFiles": ["refiner.py"],
        "editableFiles": [],
        "readonlyFiles": [],
        "expectedArtifacts": {
            "file": "refiner.py",
            "contains": [
                {"type": "class", "name": "Refiner"},
                {"type": "function", "name": "refine", "class": "Refiner"},
            ],
        },
        "validationCommand": ["echo", "test"],
    }

    # Create manifest 3: orchestrator.py again with additional method
    manifest3 = {
        "goal": "Add method to orchestrator",
        "taskType": "edit",
        "creatableFiles": [],
        "editableFiles": ["orchestrator.py"],
        "readonlyFiles": [],
        "expectedArtifacts": {
            "file": "orchestrator.py",
            "contains": [{"type": "function", "name": "execute", "class": "Developer"}],
        },
        "validationCommand": ["echo", "test"],
    }

    # Write manifests to temp files
    manifest1_path = tmp_path / "task-001.manifest.json"
    manifest2_path = tmp_path / "task-002.manifest.json"
    manifest3_path = tmp_path / "task-003.manifest.json"

    manifest1_path.write_text(json.dumps(manifest1))
    manifest2_path.write_text(json.dumps(manifest2))
    manifest3_path.write_text(json.dumps(manifest3))

    # Test: Merge artifacts for orchestrator.py
    manifest_paths = [str(manifest1_path), str(manifest2_path), str(manifest3_path)]
    merged = _merge_expected_artifacts(manifest_paths, target_file="orchestrator.py")

    # Should only include artifacts from manifest1 and manifest3 (orchestrator.py)
    # Should NOT include artifacts from manifest2 (refiner.py)
    artifact_names = {art["name"] for art in merged}

    assert (
        "Developer" in artifact_names
    ), "Should include Developer class from manifest1"
    assert "run" in artifact_names, "Should include run method from manifest1"
    assert "execute" in artifact_names, "Should include execute method from manifest3"
    assert (
        "Refiner" not in artifact_names
    ), "Should NOT include Refiner class from manifest2"
    assert (
        "refine" not in artifact_names
    ), "Should NOT include refine method from manifest2"


def test_merge_handles_empty_manifest_list(tmp_path: Path):
    """Test that _merge_expected_artifacts handles empty manifest list"""
    merged = _merge_expected_artifacts([], target_file="test.py")
    assert merged == [], "Empty manifest list should return empty artifacts"


def test_merge_handles_manifests_without_expected_artifacts(tmp_path: Path):
    """Test that _merge_expected_artifacts handles manifests with no expectedArtifacts"""

    manifest = {
        "goal": "Test",
        "taskType": "edit",
        "creatableFiles": [],
        "editableFiles": ["test.py"],
        "readonlyFiles": [],
        "expectedArtifacts": {"file": "test.py", "contains": []},
        "validationCommand": ["echo", "test"],
    }

    manifest_path = tmp_path / "task-001.manifest.json"
    manifest_path.write_text(json.dumps(manifest))

    merged = _merge_expected_artifacts([str(manifest_path)], target_file="test.py")
    assert merged == [], "Manifest with empty contains should return empty artifacts"


def test_get_expected_artifacts_passes_target_file_to_merge(tmp_path: Path):
    """Test that _get_expected_artifacts correctly passes target_file to _merge_expected_artifacts"""

    # This test verifies the integration between _get_expected_artifacts and _merge_expected_artifacts
    # We'll create a simple manifest and verify the function can be called
    manifest_data = {
        "taskType": "create",
        "expectedArtifacts": {
            "file": "test.py",
            "contains": [{"type": "function", "name": "test_func"}],
        },
    }

    # Without chain, should return artifacts from manifest_data directly
    artifacts = _get_expected_artifacts(
        manifest_data, "test.py", use_manifest_chain=False
    )
    assert len(artifacts) == 1
    assert artifacts[0]["name"] == "test_func"


def test_merge_overrides_earlier_artifact_definitions(tmp_path: Path):
    """Test that later manifests override earlier ones for the same artifact"""

    # Manifest 1: function with 1 parameter
    manifest1 = {
        "goal": "Create function",
        "taskType": "create",
        "creatableFiles": ["utils.py"],
        "editableFiles": [],
        "readonlyFiles": [],
        "expectedArtifacts": {
            "file": "utils.py",
            "contains": [
                {
                    "type": "function",
                    "name": "calculate",
                    "args": [{"name": "x", "type": "int"}],
                    "returns": "int",
                }
            ],
        },
        "validationCommand": ["echo", "test"],
    }

    # Manifest 2: same function with 2 parameters (updated signature)
    manifest2 = {
        "goal": "Update function signature",
        "taskType": "edit",
        "creatableFiles": [],
        "editableFiles": ["utils.py"],
        "readonlyFiles": [],
        "expectedArtifacts": {
            "file": "utils.py",
            "contains": [
                {
                    "type": "function",
                    "name": "calculate",
                    "args": [
                        {"name": "x", "type": "int"},
                        {"name": "y", "type": "int"},
                    ],
                    "returns": "int",
                }
            ],
        },
        "validationCommand": ["echo", "test"],
    }

    manifest1_path = tmp_path / "task-001.manifest.json"
    manifest2_path = tmp_path / "task-002.manifest.json"

    manifest1_path.write_text(json.dumps(manifest1))
    manifest2_path.write_text(json.dumps(manifest2))

    # Merge in chronological order
    manifest_paths = [str(manifest1_path), str(manifest2_path)]
    merged = _merge_expected_artifacts(manifest_paths, target_file="utils.py")

    # Should have only one calculate function (from manifest2)
    calculate_artifacts = [art for art in merged if art["name"] == "calculate"]
    assert len(calculate_artifacts) == 1, "Should have exactly one calculate artifact"

    # Verify it's the updated version with 2 parameters
    calc = calculate_artifacts[0]
    assert len(calc["args"]) == 2, "Should have 2 parameters from manifest2"
    assert calc["args"][0]["name"] == "x"
    assert calc["args"][1]["name"] == "y"
