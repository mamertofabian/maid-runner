# tests/test_manifest_validator.py
import pytest
import json
from jsonschema import ValidationError
from validators.manifest_validator import validate_schema

SCHEMA_PATH = "validators/schemas/manifest.schema.json"

def test_validate_schema_with_valid_manifest():
    """
    Tests that a valid manifest passes schema validation without raising an error.
    """
    valid_manifest = {
        "goal": "Test goal",
        "creatableFiles": ["src/test.py"],
        "readonlyFiles": ["tests/test.py"],
        "expectedArtifacts": {
            "file": "src/test.py",
            "contains": [{"type": "class", "name": "MyClass"}]
        },
        "validationCommand": "pytest"
    }
    # This should not raise an exception
    validate_schema(valid_manifest, SCHEMA_PATH)

def test_validate_schema_with_invalid_manifest():
    """
    Tests that an invalid manifest (missing required 'goal' field) raises a ValidationError.
    """
    invalid_manifest = {
        "creatableFiles": ["src/test.py"]
    }
    with pytest.raises(ValidationError):
        validate_schema(invalid_manifest, SCHEMA_PATH)
