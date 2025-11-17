"""
Behavioral tests for task-041: Extend manifest schema with systemArtifacts field.

Tests verify that the manifest schema properly supports:
1. systemArtifacts field for system-wide snapshots
2. system-snapshot taskType enum value
3. Mutual exclusivity between expectedArtifacts and systemArtifacts
4. Proper structure validation for systemArtifacts
"""

import json
import pytest
from pathlib import Path
from jsonschema import validate, ValidationError

# Test fixtures
SCHEMA_PATH = Path("maid_runner/validators/schemas/manifest.schema.json")


@pytest.fixture
def manifest_schema():
    """Load the manifest schema."""
    with open(SCHEMA_PATH) as f:
        return json.load(f)


class TestSystemArtifactsSchema:
    """Test suite for systemArtifacts schema extension."""

    def test_schema_has_system_artifacts_property(self, manifest_schema):
        """Verify systemArtifacts property exists in schema."""
        assert "systemArtifacts" in manifest_schema["properties"]

    def test_schema_has_system_snapshot_task_type(self, manifest_schema):
        """Verify system-snapshot is a valid taskType enum value."""
        task_type_enum = manifest_schema["properties"]["taskType"]["enum"]
        assert "system-snapshot" in task_type_enum

    def test_system_artifacts_structure(self, manifest_schema):
        """Verify systemArtifacts has correct schema structure."""
        sys_artifacts = manifest_schema["properties"]["systemArtifacts"]

        # Should be an array
        assert sys_artifacts["type"] == "array"

        # Array items should be objects with 'file' and 'contains'
        items_schema = sys_artifacts["items"]
        assert items_schema["type"] == "object"
        assert "file" in items_schema["required"]
        assert "contains" in items_schema["required"]

        # Items should have 'file' (string) and 'contains' (array) properties
        assert items_schema["properties"]["file"]["type"] == "string"
        assert items_schema["properties"]["contains"]["type"] == "array"

    def test_valid_system_manifest_with_system_artifacts(self, manifest_schema):
        """Verify a valid system manifest with systemArtifacts validates."""
        system_manifest = {
            "version": "1",
            "goal": "System-wide manifest snapshot",
            "taskType": "system-snapshot",
            "readonlyFiles": [],
            "systemArtifacts": [
                {
                    "file": "module/file1.py",
                    "contains": [
                        {
                            "type": "function",
                            "name": "test_function",
                            "args": [{"name": "arg1", "type": "str"}],
                            "returns": "bool",
                        }
                    ],
                },
                {
                    "file": "module/file2.py",
                    "contains": [{"type": "class", "name": "TestClass"}],
                },
            ],
            "validationCommands": [["pytest", "tests/"]],
        }

        # Should not raise ValidationError
        validate(instance=system_manifest, schema=manifest_schema)

    def test_valid_regular_manifest_with_expected_artifacts(self, manifest_schema):
        """Verify regular manifests with expectedArtifacts still validate."""
        regular_manifest = {
            "version": "1",
            "goal": "Regular task manifest",
            "taskType": "edit",
            "readonlyFiles": [],
            "expectedArtifacts": {
                "file": "module/file.py",
                "contains": [{"type": "function", "name": "test_function"}],
            },
            "validationCommand": ["pytest", "tests/"],
        }

        # Should not raise ValidationError
        validate(instance=regular_manifest, schema=manifest_schema)

    def test_manifest_cannot_have_both_artifacts_fields(self, manifest_schema):
        """Verify manifest cannot have both expectedArtifacts and systemArtifacts."""
        invalid_manifest = {
            "version": "1",
            "goal": "Invalid manifest with both artifact fields",
            "taskType": "edit",
            "readonlyFiles": [],
            "expectedArtifacts": {
                "file": "module/file.py",
                "contains": [{"type": "function", "name": "func1"}],
            },
            "systemArtifacts": [
                {
                    "file": "module/file2.py",
                    "contains": [{"type": "class", "name": "Class1"}],
                }
            ],
            "validationCommand": ["pytest", "tests/"],
        }

        # Should raise ValidationError
        with pytest.raises(ValidationError):
            validate(instance=invalid_manifest, schema=manifest_schema)

    def test_system_manifest_must_have_one_artifact_field(self, manifest_schema):
        """Verify system manifest must have at least systemArtifacts or expectedArtifacts."""
        invalid_manifest = {
            "version": "1",
            "goal": "Invalid manifest with no artifact fields",
            "taskType": "system-snapshot",
            "readonlyFiles": [],
            "validationCommand": ["pytest", "tests/"],
        }

        # Should raise ValidationError (missing required artifact field)
        with pytest.raises(ValidationError):
            validate(instance=invalid_manifest, schema=manifest_schema)

    def test_system_artifacts_items_require_file_and_contains(self, manifest_schema):
        """Verify each systemArtifacts item must have 'file' and 'contains'."""
        invalid_manifest = {
            "version": "1",
            "goal": "System manifest with incomplete artifact block",
            "taskType": "system-snapshot",
            "readonlyFiles": [],
            "systemArtifacts": [
                {
                    "file": "module/file1.py"
                    # Missing 'contains' field
                }
            ],
            "validationCommand": ["pytest", "tests/"],
        }

        # Should raise ValidationError
        with pytest.raises(ValidationError):
            validate(instance=invalid_manifest, schema=manifest_schema)

    def test_system_artifacts_contains_array_structure(self, manifest_schema):
        """Verify 'contains' in systemArtifacts follows artifact schema."""
        valid_manifest = {
            "version": "1",
            "goal": "System manifest with various artifact types",
            "taskType": "system-snapshot",
            "readonlyFiles": [],
            "systemArtifacts": [
                {
                    "file": "module/file.py",
                    "contains": [
                        {"type": "class", "name": "MyClass", "bases": ["BaseClass"]},
                        {
                            "type": "function",
                            "name": "my_function",
                            "args": [
                                {"name": "param1", "type": "str"},
                                {"name": "param2", "type": "int", "default": "0"},
                            ],
                            "returns": "bool",
                        },
                        {"type": "attribute", "name": "MODULE_CONSTANT"},
                    ],
                }
            ],
            "validationCommands": [["pytest", "tests/"]],
        }

        # Should not raise ValidationError
        validate(instance=valid_manifest, schema=manifest_schema)

    def test_empty_system_artifacts_array_is_valid(self, manifest_schema):
        """Verify systemArtifacts can be an empty array."""
        valid_manifest = {
            "version": "1",
            "goal": "System manifest with no artifacts yet",
            "taskType": "system-snapshot",
            "readonlyFiles": [],
            "systemArtifacts": [],
            "validationCommand": ["pytest", "tests/"],
        }

        # Should not raise ValidationError
        validate(instance=valid_manifest, schema=manifest_schema)


class TestBackwardCompatibility:
    """Test that schema changes maintain backward compatibility."""

    def test_existing_manifests_still_validate(self, manifest_schema):
        """Verify existing manifest formats still work."""
        # Test various existing manifest patterns
        manifests = [
            # Create task
            {
                "version": "1",
                "goal": "Create new feature",
                "taskType": "create",
                "creatableFiles": ["new_file.py"],
                "readonlyFiles": ["tests/test_new.py"],
                "expectedArtifacts": {
                    "file": "new_file.py",
                    "contains": [{"type": "function", "name": "new_func"}],
                },
                "validationCommand": ["pytest", "tests/"],
            },
            # Edit task
            {
                "version": "1",
                "goal": "Edit existing code",
                "taskType": "edit",
                "editableFiles": ["existing.py"],
                "readonlyFiles": [],
                "expectedArtifacts": {
                    "file": "existing.py",
                    "contains": [{"type": "class", "name": "UpdatedClass"}],
                },
                "validationCommands": [["pytest", "tests/"]],
            },
            # Snapshot task
            {
                "version": "1",
                "goal": "Snapshot of current state",
                "taskType": "snapshot",
                "readonlyFiles": [],
                "expectedArtifacts": {
                    "file": "module.py",
                    "contains": [{"type": "function", "name": "func"}],
                },
                "validationCommand": ["pytest", "tests/"],
            },
        ]

        for manifest in manifests:
            # Should not raise ValidationError
            validate(instance=manifest, schema=manifest_schema)
