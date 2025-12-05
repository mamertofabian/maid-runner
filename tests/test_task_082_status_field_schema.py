"""
Behavioral tests for Task-082: Add status field to expectedArtifacts schema.

Tests verify that the manifest schema correctly accepts the new optional 'status' field
with enum values 'present' (default) and 'absent' for file deletion tracking.
"""

import pytest
from jsonschema import ValidationError
from maid_runner.validators.manifest_validator import validate_schema

SCHEMA_PATH = "maid_runner/validators/schemas/manifest.schema.json"


def test_status_present_validates():
    """Test that status: 'present' is accepted by the schema."""
    manifest_with_status_present = {
        "goal": "Test status field with 'present' value",
        "readonlyFiles": ["tests/test.py"],
        "expectedArtifacts": {
            "file": "src/test.py",
            "status": "present",
            "contains": [{"type": "function", "name": "test_func"}],
        },
        "validationCommand": ["pytest"],
    }
    # This should not raise an exception
    validate_schema(manifest_with_status_present, SCHEMA_PATH)


def test_status_absent_validates():
    """Test that status: 'absent' is accepted by the schema."""
    manifest_with_status_absent = {
        "goal": "Test status field with 'absent' value for deletion tracking",
        "readonlyFiles": ["tests/test.py"],
        "expectedArtifacts": {
            "file": "src/deleted_file.py",
            "status": "absent",
            "contains": [],
        },
        "validationCommand": ["pytest"],
    }
    # This should not raise an exception
    validate_schema(manifest_with_status_absent, SCHEMA_PATH)


def test_status_field_optional_backward_compatibility():
    """Test that manifests without status field validate successfully (backward compatibility)."""
    manifest_without_status = {
        "goal": "Test backward compatibility without status field",
        "readonlyFiles": ["tests/test.py"],
        "expectedArtifacts": {
            "file": "src/test.py",
            "contains": [
                {"type": "class", "name": "MyClass"},
                {"type": "function", "name": "my_function"},
            ],
        },
        "validationCommand": ["pytest"],
    }
    # This should not raise an exception (status is optional)
    validate_schema(manifest_without_status, SCHEMA_PATH)


def test_invalid_status_value_rejected():
    """Test that manifests with invalid status values are rejected."""
    manifest_with_invalid_status = {
        "goal": "Test invalid status value",
        "readonlyFiles": ["tests/test.py"],
        "expectedArtifacts": {
            "file": "src/test.py",
            "status": "deleted",  # Invalid value - should be 'present' or 'absent'
            "contains": [],
        },
        "validationCommand": ["pytest"],
    }
    # This should raise ValidationError due to invalid enum value
    with pytest.raises(ValidationError) as exc_info:
        validate_schema(manifest_with_invalid_status, SCHEMA_PATH)
    # Verify it's specifically about the invalid status value
    assert "deleted" in str(exc_info.value) or "'status'" in str(exc_info.value)
