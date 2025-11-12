"""Behavioral tests for task-039: enhance schema descriptions.

This test file verifies the manifest schema has enhanced descriptions
for key properties to help with artifact implementation.
"""

import json
import pytest
from pathlib import Path


class TestManifestSchemaDescriptions:
    """Tests for enhanced descriptions in manifest schema."""

    @pytest.fixture
    def schema(self):
        """Load the manifest schema."""
        schema_path = Path("maid_runner/validators/schemas/manifest.schema.json")
        with open(schema_path) as f:
            return json.load(f)

    def test_schema_exists(self, schema):
        """Test that manifest schema can be loaded."""
        assert schema is not None
        assert isinstance(schema, dict)

    def test_goal_property_has_description(self, schema):
        """Test that 'goal' property has an enhanced description."""
        assert "properties" in schema
        assert "goal" in schema["properties"]
        goal_property = schema["properties"]["goal"]
        assert "description" in goal_property
        assert isinstance(goal_property["description"], str)
        assert len(goal_property["description"]) > 0

    def test_description_property_exists(self, schema):
        """Test that 'description' property exists in schema."""
        assert "properties" in schema
        assert "description" in schema["properties"]
        description_property = schema["properties"]["description"]
        assert "type" in description_property
        assert description_property["type"] == "string"

    def test_description_property_has_description(self, schema):
        """Test that 'description' property has its own description."""
        description_property = schema["properties"]["description"]
        assert "description" in description_property
        assert isinstance(description_property["description"], str)
        assert len(description_property["description"]) > 0

    def test_taskType_property_has_description(self, schema):
        """Test that 'taskType' property has an enhanced description."""
        assert "taskType" in schema["properties"]
        task_type_property = schema["properties"]["taskType"]
        assert "description" in task_type_property
        assert isinstance(task_type_property["description"], str)
        assert len(task_type_property["description"]) > 0

    def test_creatableFiles_property_has_description(self, schema):
        """Test that 'creatableFiles' property has an enhanced description."""
        assert "creatableFiles" in schema["properties"]
        creatable_files_property = schema["properties"]["creatableFiles"]
        assert "description" in creatable_files_property
        assert isinstance(creatable_files_property["description"], str)
        assert len(creatable_files_property["description"]) > 0

    def test_editableFiles_property_has_description(self, schema):
        """Test that 'editableFiles' property has an enhanced description."""
        assert "editableFiles" in schema["properties"]
        editable_files_property = schema["properties"]["editableFiles"]
        assert "description" in editable_files_property
        assert isinstance(editable_files_property["description"], str)
        assert len(editable_files_property["description"]) > 0

    def test_readonlyFiles_property_has_description(self, schema):
        """Test that 'readonlyFiles' property has an enhanced description."""
        assert "readonlyFiles" in schema["properties"]
        readonly_files_property = schema["properties"]["readonlyFiles"]
        assert "description" in readonly_files_property
        assert isinstance(readonly_files_property["description"], str)
        assert len(readonly_files_property["description"]) > 0

    def test_expectedArtifacts_property_has_description(self, schema):
        """Test that 'expectedArtifacts' property has an enhanced description."""
        assert "expectedArtifacts" in schema["properties"]
        expected_artifacts_property = schema["properties"]["expectedArtifacts"]
        assert "description" in expected_artifacts_property
        assert isinstance(expected_artifacts_property["description"], str)
        assert len(expected_artifacts_property["description"]) > 0

    def test_expectedArtifacts_nested_properties_have_descriptions(self, schema):
        """Test that nested properties in 'expectedArtifacts' have descriptions."""
        expected_artifacts = schema["properties"]["expectedArtifacts"]
        assert "properties" in expected_artifacts

        # Test 'file' property
        assert "file" in expected_artifacts["properties"]
        file_property = expected_artifacts["properties"]["file"]
        assert "description" in file_property
        assert isinstance(file_property["description"], str)
        assert len(file_property["description"]) > 0

        # Test 'contains' property
        assert "contains" in expected_artifacts["properties"]
        contains_property = expected_artifacts["properties"]["contains"]
        assert "description" in contains_property
        assert isinstance(contains_property["description"], str)
        assert len(contains_property["description"]) > 0

    def test_all_required_properties_present(self, schema):
        """Test that all required properties exist in schema."""
        required_props = [
            "goal",
            "description",
            "taskType",
            "creatableFiles",
            "editableFiles",
            "readonlyFiles",
            "expectedArtifacts",
        ]

        for prop in required_props:
            assert (
                prop in schema["properties"]
            ), f"Property '{prop}' not found in schema"

    def test_schema_structure_intact(self, schema):
        """Test that schema maintains its core structure."""
        assert "$schema" in schema
        assert "title" in schema
        assert "type" in schema
        assert schema["type"] == "object"
        assert "properties" in schema
        assert "required" in schema
