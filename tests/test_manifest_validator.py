# tests/test_manifest_validator.py
import pytest
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
            "contains": [{"type": "class", "name": "MyClass"}],
        },
        "validationCommand": "pytest",
    }
    # This should not raise an exception
    validate_schema(valid_manifest, SCHEMA_PATH)


def test_validate_schema_with_invalid_manifest():
    """
    Tests that an invalid manifest (missing required 'goal' field) raises a ValidationError.
    """
    invalid_manifest = {"creatableFiles": ["src/test.py"]}
    with pytest.raises(ValidationError):
        validate_schema(invalid_manifest, SCHEMA_PATH)


def test_validate_schema_with_function_parameters():
    """
    Tests that a manifest with function parameters is valid against the schema.
    """
    manifest_with_params = {
        "goal": "Test function with parameters",
        "readonlyFiles": ["tests/test.py"],
        "expectedArtifacts": {
            "file": "src/test.py",
            "contains": [
                {
                    "type": "function",
                    "name": "process_data",
                    "parameters": ["input_data", "options", "verbose"],
                }
            ],
        },
        "validationCommand": "pytest",
    }
    # This should not raise an exception
    validate_schema(manifest_with_params, SCHEMA_PATH)


def test_validate_schema_with_class_base():
    """
    Tests that a manifest with class base is valid against the schema.
    """
    manifest_with_base = {
        "goal": "Test class with base",
        "readonlyFiles": ["tests/test.py"],
        "expectedArtifacts": {
            "file": "src/test.py",
            "contains": [{"type": "class", "name": "CustomError", "base": "Exception"}],
        },
        "validationCommand": "pytest",
    }
    # This should not raise an exception
    validate_schema(manifest_with_base, SCHEMA_PATH)


def test_validate_schema_with_mixed_artifacts():
    """
    Tests that a manifest with various artifact types including new fields is valid.
    """
    complex_manifest = {
        "goal": "Test complex manifest",
        "editableFiles": ["src/existing.py"],
        "readonlyFiles": ["tests/test.py"],
        "expectedArtifacts": {
            "file": "src/test.py",
            "contains": [
                {"type": "class", "name": "MyError", "base": "ValueError"},
                {
                    "type": "function",
                    "name": "calculate",
                    "parameters": ["a", "b", "operation"],
                },
                {"type": "attribute", "name": "value", "class": "MyClass"},
                {"type": "class", "name": "SimpleClass"},  # No base specified
                {"type": "function", "name": "simple_func"},  # No parameters specified
            ],
        },
        "validationCommand": "pytest",
    }
    # This should not raise an exception
    validate_schema(complex_manifest, SCHEMA_PATH)
