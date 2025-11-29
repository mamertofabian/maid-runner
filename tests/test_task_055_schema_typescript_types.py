"""Behavioral tests for Task-055: Extend manifest schema for TypeScript types.

This test suite validates that the manifest schema supports TypeScript-specific
artifact types (interface, type, enum, namespace) while maintaining backward
compatibility with existing Python manifests.

Test Organization:
- Schema validity and structure
- TypeScript artifact type validation
- Backward compatibility with Python manifests
- Schema documentation and metadata
"""

import json
from pathlib import Path

import jsonschema
import pytest


# =============================================================================
# SECTION 1: Schema File Validity
# =============================================================================


class TestSchemaValidity:
    """Test that the schema file is valid JSON Schema."""

    def test_schema_file_exists(self):
        """Schema file must exist at expected location."""
        schema_path = Path("maid_runner/validators/schemas/manifest.schema.json")
        assert schema_path.exists()

    def test_schema_is_valid_json(self):
        """Schema file must be valid JSON."""
        schema_path = Path("maid_runner/validators/schemas/manifest.schema.json")
        with open(schema_path) as f:
            schema = json.load(f)
        assert isinstance(schema, dict)

    def test_schema_has_required_meta_fields(self):
        """Schema must have JSON Schema metadata fields."""
        schema_path = Path("maid_runner/validators/schemas/manifest.schema.json")
        with open(schema_path) as f:
            schema = json.load(f)

        assert "$schema" in schema
        assert "type" in schema


# =============================================================================
# SECTION 2: TypeScript Artifact Type Support
# =============================================================================


class TestTypescriptArtifactTypes:
    """Test that schema supports TypeScript-specific artifact types."""

    def test_schema_allows_interface_type(self):
        """Schema must allow 'interface' as artifact type."""
        schema_path = Path("maid_runner/validators/schemas/manifest.schema.json")
        with open(schema_path) as f:
            schema = json.load(f)

        # Test manifest with interface type
        manifest = {
            "version": "1",
            "goal": "Test interface",
            "taskType": "create",
            "creatableFiles": ["test.ts"],
            "readonlyFiles": [],
            "expectedArtifacts": {
                "file": "test.ts",
                "contains": [{"type": "interface", "name": "User"}],
            },
            "validationCommand": ["echo", "test"],
        }

        # Should validate without errors
        jsonschema.validate(instance=manifest, schema=schema)

    def test_schema_allows_type_alias_type(self):
        """Schema must allow 'type' as artifact type for type aliases."""
        schema_path = Path("maid_runner/validators/schemas/manifest.schema.json")
        with open(schema_path) as f:
            schema = json.load(f)

        manifest = {
            "version": "1",
            "goal": "Test type alias",
            "taskType": "create",
            "creatableFiles": ["test.ts"],
            "readonlyFiles": [],
            "expectedArtifacts": {
                "file": "test.ts",
                "contains": [{"type": "type", "name": "UserID"}],
            },
            "validationCommand": ["echo", "test"],
        }

        jsonschema.validate(instance=manifest, schema=schema)

    def test_schema_allows_enum_type(self):
        """Schema must allow 'enum' as artifact type."""
        schema_path = Path("maid_runner/validators/schemas/manifest.schema.json")
        with open(schema_path) as f:
            schema = json.load(f)

        manifest = {
            "version": "1",
            "goal": "Test enum",
            "taskType": "create",
            "creatableFiles": ["test.ts"],
            "readonlyFiles": [],
            "expectedArtifacts": {
                "file": "test.ts",
                "contains": [{"type": "enum", "name": "Status"}],
            },
            "validationCommand": ["echo", "test"],
        }

        jsonschema.validate(instance=manifest, schema=schema)

    def test_schema_allows_namespace_type(self):
        """Schema must allow 'namespace' as artifact type."""
        schema_path = Path("maid_runner/validators/schemas/manifest.schema.json")
        with open(schema_path) as f:
            schema = json.load(f)

        manifest = {
            "version": "1",
            "goal": "Test namespace",
            "taskType": "create",
            "creatableFiles": ["test.ts"],
            "readonlyFiles": [],
            "expectedArtifacts": {
                "file": "test.ts",
                "contains": [{"type": "namespace", "name": "Utils"}],
            },
            "validationCommand": ["echo", "test"],
        }

        jsonschema.validate(instance=manifest, schema=schema)

    def test_schema_allows_multiple_typescript_types(self):
        """Schema must allow manifests with multiple TypeScript types."""
        schema_path = Path("maid_runner/validators/schemas/manifest.schema.json")
        with open(schema_path) as f:
            schema = json.load(f)

        manifest = {
            "version": "1",
            "goal": "Test multiple TS types",
            "taskType": "create",
            "creatableFiles": ["test.ts"],
            "readonlyFiles": [],
            "expectedArtifacts": {
                "file": "test.ts",
                "contains": [
                    {"type": "interface", "name": "User"},
                    {"type": "type", "name": "UserID"},
                    {"type": "enum", "name": "Role"},
                    {"type": "namespace", "name": "Auth"},
                    {"type": "class", "name": "UserService"},
                    {"type": "function", "name": "validateUser"},
                ],
            },
            "validationCommand": ["echo", "test"],
        }

        jsonschema.validate(instance=manifest, schema=schema)


# =============================================================================
# SECTION 3: Backward Compatibility with Python
# =============================================================================


class TestPythonBackwardCompatibility:
    """Test that existing Python manifests still validate correctly."""

    def test_schema_still_allows_class_type(self):
        """Schema must still allow 'class' type for Python."""
        schema_path = Path("maid_runner/validators/schemas/manifest.schema.json")
        with open(schema_path) as f:
            schema = json.load(f)

        manifest = {
            "version": "1",
            "goal": "Test Python class",
            "taskType": "create",
            "creatableFiles": ["test.py"],
            "readonlyFiles": [],
            "expectedArtifacts": {
                "file": "test.py",
                "contains": [{"type": "class", "name": "UserService"}],
            },
            "validationCommand": ["pytest", "test_file.py"],
        }

        jsonschema.validate(instance=manifest, schema=schema)

    def test_schema_still_allows_function_type(self):
        """Schema must still allow 'function' type for Python."""
        schema_path = Path("maid_runner/validators/schemas/manifest.schema.json")
        with open(schema_path) as f:
            schema = json.load(f)

        manifest = {
            "version": "1",
            "goal": "Test Python function",
            "taskType": "create",
            "creatableFiles": ["test.py"],
            "readonlyFiles": [],
            "expectedArtifacts": {
                "file": "test.py",
                "contains": [
                    {
                        "type": "function",
                        "name": "process_data",
                        "args": [{"name": "data"}],
                    }
                ],
            },
            "validationCommand": ["pytest", "test_file.py"],
        }

        jsonschema.validate(instance=manifest, schema=schema)

    def test_schema_still_allows_attribute_type(self):
        """Schema must still allow 'attribute' type for Python."""
        schema_path = Path("maid_runner/validators/schemas/manifest.schema.json")
        with open(schema_path) as f:
            schema = json.load(f)

        manifest = {
            "version": "1",
            "goal": "Test Python attribute",
            "taskType": "create",
            "creatableFiles": ["test.py"],
            "readonlyFiles": [],
            "expectedArtifacts": {
                "file": "test.py",
                "contains": [{"type": "attribute", "name": "MAX_SIZE"}],
            },
            "validationCommand": ["pytest", "test_file.py"],
        }

        jsonschema.validate(instance=manifest, schema=schema)

    def test_schema_still_allows_parameter_type(self):
        """Schema must still allow 'parameter' type for Python."""
        schema_path = Path("maid_runner/validators/schemas/manifest.schema.json")
        with open(schema_path) as f:
            schema = json.load(f)

        manifest = {
            "version": "1",
            "goal": "Test Python parameter",
            "taskType": "create",
            "creatableFiles": ["test.py"],
            "readonlyFiles": [],
            "expectedArtifacts": {
                "file": "test.py",
                "contains": [
                    {
                        "type": "function",
                        "name": "test_func",
                        "args": [{"name": "param1", "type": "str"}],
                    }
                ],
            },
            "validationCommand": ["pytest", "test_file.py"],
        }

        jsonschema.validate(instance=manifest, schema=schema)

    def test_existing_python_manifest_validates(self):
        """Real existing Python manifest must still validate."""
        schema_path = Path("maid_runner/validators/schemas/manifest.schema.json")
        with open(schema_path) as f:
            schema = json.load(f)

        # Read an actual existing manifest
        existing_manifest_path = Path(
            "manifests/task-054-typescript-test-runner.manifest.json"
        )
        with open(existing_manifest_path) as f:
            existing_manifest = json.load(f)

        # Should validate without errors
        jsonschema.validate(instance=existing_manifest, schema=schema)


# =============================================================================
# SECTION 4: Mixed Language Support
# =============================================================================


class TestMixedLanguageSupport:
    """Test that schema supports manifests with both Python and TypeScript."""

    def test_schema_allows_mixed_artifact_types(self):
        """Schema must allow manifests with both Python and TypeScript types."""
        schema_path = Path("maid_runner/validators/schemas/manifest.schema.json")
        with open(schema_path) as f:
            schema = json.load(f)

        manifest = {
            "version": "1",
            "goal": "Test mixed types",
            "taskType": "edit",
            "creatableFiles": [],
            "editableFiles": ["test.py", "test.ts"],
            "readonlyFiles": [],
            "expectedArtifacts": {
                "file": "test.py",
                "contains": [
                    {"type": "class", "name": "PythonService"},
                    {"type": "function", "name": "python_func"},
                ],
            },
            "validationCommand": ["pytest", "test_file.py"],
        }

        jsonschema.validate(instance=manifest, schema=schema)

    def test_schema_allows_typescript_in_python_project(self):
        """Schema must allow TypeScript artifacts in primarily Python project."""
        schema_path = Path("maid_runner/validators/schemas/manifest.schema.json")
        with open(schema_path) as f:
            schema = json.load(f)

        manifest = {
            "version": "1",
            "goal": "Add TypeScript to Python project",
            "taskType": "create",
            "creatableFiles": ["frontend.ts"],
            "readonlyFiles": ["backend.py"],
            "expectedArtifacts": {
                "file": "frontend.ts",
                "contains": [
                    {"type": "interface", "name": "ApiResponse"},
                    {"type": "class", "name": "ApiClient"},
                ],
            },
            "validationCommand": ["npm", "test"],
        }

        jsonschema.validate(instance=manifest, schema=schema)


# =============================================================================
# SECTION 5: Schema Validation Error Cases
# =============================================================================


class TestSchemaValidationErrors:
    """Test that schema properly rejects invalid artifact types."""

    def test_schema_rejects_invalid_artifact_type(self):
        """Schema must reject invalid artifact types."""
        schema_path = Path("maid_runner/validators/schemas/manifest.schema.json")
        with open(schema_path) as f:
            schema = json.load(f)

        manifest = {
            "version": "1",
            "goal": "Test invalid type",
            "taskType": "create",
            "creatableFiles": ["test.ts"],
            "readonlyFiles": [],
            "expectedArtifacts": {
                "file": "test.ts",
                "contains": [{"type": "invalid_type", "name": "Test"}],
            },
            "validationCommand": ["echo", "test"],
        }

        with pytest.raises(jsonschema.ValidationError):
            jsonschema.validate(instance=manifest, schema=schema)

    def test_schema_requires_artifact_name(self):
        """Schema must require 'name' field in artifacts."""
        schema_path = Path("maid_runner/validators/schemas/manifest.schema.json")
        with open(schema_path) as f:
            schema = json.load(f)

        manifest = {
            "version": "1",
            "goal": "Test missing name",
            "taskType": "create",
            "creatableFiles": ["test.ts"],
            "readonlyFiles": [],
            "expectedArtifacts": {
                "file": "test.ts",
                "contains": [{"type": "interface"}],  # Missing name
            },
            "validationCommand": ["echo", "test"],
        }

        with pytest.raises(jsonschema.ValidationError):
            jsonschema.validate(instance=manifest, schema=schema)


# =============================================================================
# SECTION 6: All Existing Manifests Validation
# =============================================================================


class TestAllExistingManifestsStillValid:
    """Test that ALL existing manifests still validate with updated schema."""

    def test_all_active_manifests_validate(self):
        """All non-superseded manifests must validate with updated schema."""
        schema_path = Path("maid_runner/validators/schemas/manifest.schema.json")
        with open(schema_path) as f:
            schema = json.load(f)

        from maid_runner.utils import get_superseded_manifests

        manifests_dir = Path("manifests")
        all_manifests = sorted(manifests_dir.glob("task-*.manifest.json"))
        superseded = get_superseded_manifests(manifests_dir)
        active_manifests = [m for m in all_manifests if m not in superseded]

        assert len(active_manifests) > 0, "No active manifests found"

        for manifest_file in active_manifests:
            with open(manifest_file) as f:
                manifest = json.load(f)

            # Should validate without errors
            try:
                jsonschema.validate(instance=manifest, schema=schema)
            except jsonschema.ValidationError as e:
                pytest.fail(f"Manifest {manifest_file.name} failed validation: {e}")
