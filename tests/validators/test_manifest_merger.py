"""Tests for the manifest merger functionality."""

import pytest
import json
import tempfile
from pathlib import Path
from validators.manifest_validator import (
    _discover_related_manifests,
    _merge_expected_artifacts,
    validate_with_ast,
    AlignmentError,
)


def test_discover_related_manifests():
    """Test that we can discover manifests that touched a specific file."""
    # This test uses the real manifests in the project
    target_file = "validators/manifest_validator.py"

    manifests = _discover_related_manifests(target_file)

    # Should find both task-001 and task-002 manifests
    assert len(manifests) == 2
    assert "task-001" in manifests[0]
    assert "task-002" in manifests[1]


def test_discover_manifests_chronological_order():
    """Test that manifests are returned in chronological order."""
    # Create a temporary manifest directory with out-of-order files
    with tempfile.TemporaryDirectory() as tmpdir:
        manifest_dir = Path(tmpdir) / "manifests"
        manifest_dir.mkdir()

        # Create manifests out of order
        task_003 = manifest_dir / "task-003.json"
        task_001 = manifest_dir / "task-001.json"
        task_002 = manifest_dir / "task-002.json"

        manifest_content = {
            "expectedArtifacts": {"file": "test.py", "contains": []},
            "creatableFiles": ["test.py"],
        }

        for path in [task_003, task_001, task_002]:
            with open(path, "w") as f:
                json.dump(manifest_content, f)

        # Mock the manifest directory for the function
        import validators.manifest_validator as mv

        original_path = mv.Path
        mv.Path = lambda x: manifest_dir if x == "manifests" else original_path(x)

        try:
            manifests = _discover_related_manifests("test.py")
            # Should be sorted chronologically
            assert "task-001" in manifests[0]
            assert "task-002" in manifests[1]
            assert "task-003" in manifests[2]
        finally:
            mv.Path = original_path


def test_merge_expected_artifacts():
    """Test merging artifacts from multiple manifests."""
    # Create temporary manifest files
    with tempfile.TemporaryDirectory() as tmpdir:
        manifest1 = Path(tmpdir) / "task-001.json"
        manifest2 = Path(tmpdir) / "task-002.json"

        # First manifest with validate_schema function
        content1 = {
            "expectedArtifacts": {
                "contains": [{"type": "function", "name": "validate_schema"}]
            }
        }

        # Second manifest with AlignmentError class and validate_with_ast function
        content2 = {
            "expectedArtifacts": {
                "contains": [
                    {"type": "class", "name": "AlignmentError", "bases": ["Exception"]},
                    {
                        "type": "function",
                        "name": "validate_with_ast",
                        "parameters": [
                            {"name": "manifest_data"},
                            {"name": "test_file_path"},
                        ],
                    },
                ]
            }
        }

        with open(manifest1, "w") as f:
            json.dump(content1, f)
        with open(manifest2, "w") as f:
            json.dump(content2, f)

        # Merge artifacts
        merged = _merge_expected_artifacts([str(manifest1), str(manifest2)])

        # Should have all three artifacts
        assert len(merged) == 3

        # Check that all artifacts are present
        artifact_names = {a["name"] for a in merged}
        assert "validate_schema" in artifact_names
        assert "AlignmentError" in artifact_names
        assert "validate_with_ast" in artifact_names

        # Check that details are preserved
        alignment_error = next(a for a in merged if a["name"] == "AlignmentError")
        assert alignment_error.get("bases") == ["Exception"]

        validate_ast = next(a for a in merged if a["name"] == "validate_with_ast")
        assert validate_ast.get("parameters") == [
            {"name": "manifest_data"},
            {"name": "test_file_path"},
        ]


def test_merge_handles_duplicates():
    """Test that merging handles duplicate artifacts correctly."""
    with tempfile.TemporaryDirectory() as tmpdir:
        manifest1 = Path(tmpdir) / "task-001.json"
        manifest2 = Path(tmpdir) / "task-002.json"

        # Both manifests declare the same function but with different detail levels
        content1 = {
            "expectedArtifacts": {
                "contains": [{"type": "function", "name": "process_data"}]
            }
        }

        # Second manifest adds parameters
        content2 = {
            "expectedArtifacts": {
                "contains": [
                    {
                        "type": "function",
                        "name": "process_data",
                        "parameters": [{"name": "data"}, {"name": "options"}],
                    }
                ]
            }
        }

        with open(manifest1, "w") as f:
            json.dump(content1, f)
        with open(manifest2, "w") as f:
            json.dump(content2, f)

        # Merge artifacts
        merged = _merge_expected_artifacts([str(manifest1), str(manifest2)])

        # Should have only one function (not duplicated)
        assert len(merged) == 1
        assert merged[0]["name"] == "process_data"

        # Should keep the more detailed version
        assert merged[0].get("parameters") == [{"name": "data"}, {"name": "options"}]


def test_validate_with_manifest_chain(tmp_path: Path):
    """Test validation using the manifest chain mode."""
    # Create a Python file with multiple artifacts
    implementation = """
class AlignmentError(Exception):
    pass

def validate_schema(manifest_data, schema_path):
    pass

def validate_with_ast(manifest_data, test_file_path):
    pass
"""

    test_file = tmp_path / "implementation.py"
    test_file.write_text(implementation)

    # Create temporary manifests
    manifest_dir = tmp_path / "manifests"
    manifest_dir.mkdir()

    task1 = manifest_dir / "task-001.json"
    task2 = manifest_dir / "task-002.json"

    # Task 1 creates validate_schema
    content1 = {
        "expectedArtifacts": {
            "file": str(test_file),
            "contains": [
                {
                    "type": "function",
                    "name": "validate_schema",
                    "parameters": [{"name": "manifest_data"}, {"name": "schema_path"}],
                }
            ],
        },
        "creatableFiles": [str(test_file)],
    }

    # Task 2 adds AlignmentError and validate_with_ast
    content2 = {
        "expectedArtifacts": {
            "file": str(test_file),
            "contains": [
                {"type": "class", "name": "AlignmentError", "bases": ["Exception"]},
                {
                    "type": "function",
                    "name": "validate_with_ast",
                    "parameters": [
                        {"name": "manifest_data"},
                        {"name": "test_file_path"},
                    ],
                },
            ],
        },
        "editableFiles": [str(test_file)],
    }

    with open(task1, "w") as f:
        json.dump(content1, f)
    with open(task2, "w") as f:
        json.dump(content2, f)

    # Mock the manifest directory
    import validators.manifest_validator as mv

    original_path = mv.Path
    mv.Path = lambda x: manifest_dir if x == "manifests" else original_path(x)

    try:
        # Should pass with manifest chain mode
        validate_with_ast(content2, str(test_file), use_manifest_chain=True)

        # Should fail without manifest chain mode (strict validation)
        with pytest.raises(AlignmentError, match="Unexpected public function"):
            validate_with_ast(content2, str(test_file), use_manifest_chain=False)
    finally:
        mv.Path = original_path


def test_empty_manifest_chain():
    """Test behavior when no manifests are found."""
    manifests = _discover_related_manifests("non_existent_file.py")
    assert manifests == []

    merged = _merge_expected_artifacts([])
    assert merged == []


def test_discover_manifests_with_four_digit_numbers():
    """Test that 4-digit task numbers are sorted correctly after 3-digit ones."""
    # Create a temporary manifest directory with 3 and 4 digit task numbers
    with tempfile.TemporaryDirectory() as tmpdir:
        manifest_dir = Path(tmpdir) / "manifests"
        manifest_dir.mkdir()

        # Create manifests with both 3-digit and 4-digit numbers
        task_998 = manifest_dir / "task-998.json"
        task_999 = manifest_dir / "task-999.json"
        task_1000 = manifest_dir / "task-1000.json"
        task_1001 = manifest_dir / "task-1001-add-feature.json"  # With description

        manifest_content = {
            "expectedArtifacts": {"file": "test.py", "contains": []},
            "creatableFiles": ["test.py"],
        }

        for path in [task_998, task_999, task_1000, task_1001]:
            with open(path, "w") as f:
                json.dump(manifest_content, f)

        # Mock the manifest directory for the function
        import validators.manifest_validator as mv

        original_path = mv.Path
        mv.Path = lambda x: manifest_dir if x == "manifests" else original_path(x)

        try:
            manifests = _discover_related_manifests("test.py")
            # Should be sorted numerically, not lexicographically
            assert len(manifests) == 4
            assert "task-998" in manifests[0]
            assert "task-999" in manifests[1]
            assert "task-1000" in manifests[2]
            assert "task-1001-add-feature" in manifests[3]
        finally:
            mv.Path = original_path
