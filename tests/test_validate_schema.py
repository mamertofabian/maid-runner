import pytest
from jsonschema import ValidationError
from maid_runner.validators.manifest_validator import validate_schema

SCHEMA_PATH = "maid_runner/validators/schemas/manifest.schema.json"


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
        "validationCommand": ["pytest"],
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
                    "parameters": [
                        {"name": "input_data"},
                        {"name": "options"},
                        {"name": "verbose"},
                    ],
                }
            ],
        },
        "validationCommand": ["pytest"],
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
            "contains": [
                {"type": "class", "name": "CustomError", "bases": ["Exception"]}
            ],
        },
        "validationCommand": ["pytest"],
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
                {"type": "class", "name": "MyError", "bases": ["ValueError"]},
                {
                    "type": "function",
                    "name": "calculate",
                    "parameters": [{"name": "a"}, {"name": "b"}, {"name": "operation"}],
                },
                {"type": "attribute", "name": "value", "class": "MyClass"},
                {"type": "class", "name": "SimpleClass"},  # No base specified
                {"type": "function", "name": "simple_func"},  # No parameters specified
            ],
        },
        "validationCommand": ["pytest"],
    }
    # This should not raise an exception
    validate_schema(complex_manifest, SCHEMA_PATH)


def test_validate_schema_with_multiple_bases():
    """
    Tests that a manifest with multiple base classes (using the new 'bases' array) is valid.
    """
    manifest_with_multiple_bases = {
        "goal": "Test class with multiple inheritance",
        "readonlyFiles": ["tests/test.py"],
        "expectedArtifacts": {
            "file": "src/test.py",
            "contains": [
                {
                    "type": "class",
                    "name": "MultiDerivedClass",
                    "bases": ["BaseClass1", "BaseClass2", "Mixin"],
                }
            ],
        },
        "validationCommand": ["pytest", "-v"],
    }
    # This should not raise an exception
    validate_schema(manifest_with_multiple_bases, SCHEMA_PATH)


def test_validate_schema_with_invalid_parameter_missing_name():
    """
    Tests that a manifest with parameters missing 'name' property fails validation.
    """
    manifest_invalid_params = {
        "goal": "Test function with invalid parameters",
        "readonlyFiles": ["tests/test.py"],
        "expectedArtifacts": {
            "file": "src/test.py",
            "contains": [
                {
                    "type": "function",
                    "name": "process_data",
                    "parameters": [
                        {"type": "str"},  # Missing 'name' property
                        {"wrongkey": "value"},  # Completely wrong property
                    ],
                }
            ],
        },
        "validationCommand": ["pytest"],
    }
    # Now this should raise ValidationError due to missing 'name' in parameters
    with pytest.raises(ValidationError) as exc_info:
        validate_schema(manifest_invalid_params, SCHEMA_PATH)
    assert "'name' is a required property" in str(exc_info.value)


def test_validate_schema_with_invalid_artifact_type():
    """
    Tests that a manifest with invalid artifact type fails validation.
    """
    manifest_invalid_type = {
        "goal": "Test invalid artifact type",
        "readonlyFiles": ["tests/test.py"],
        "expectedArtifacts": {
            "file": "src/test.py",
            "contains": [
                {
                    "type": "invalid_type",  # Not in enum
                    "name": "something",
                }
            ],
        },
        "validationCommand": ["pytest"],
    }
    with pytest.raises(ValidationError) as exc_info:
        validate_schema(manifest_invalid_type, SCHEMA_PATH)
    # Verify it's specifically about the invalid enum value
    assert "invalid_type" in str(exc_info.value)


def test_validate_schema_with_missing_artifact_name():
    """
    Tests that a manifest with artifact missing required 'name' field fails validation.
    """
    manifest_missing_name = {
        "goal": "Test missing name in artifact",
        "readonlyFiles": ["tests/test.py"],
        "expectedArtifacts": {
            "file": "src/test.py",
            "contains": [
                {
                    "type": "function",
                    # Missing 'name' which is required
                    "parameters": [{"name": "arg"}],
                }
            ],
        },
        "validationCommand": ["pytest"],
    }
    with pytest.raises(ValidationError) as exc_info:
        validate_schema(manifest_missing_name, SCHEMA_PATH)
    assert "'name' is a required property" in str(exc_info.value)


def test_validate_schema_with_missing_artifact_type():
    """
    Tests that a manifest with artifact missing required 'type' field fails validation.
    """
    manifest_missing_type = {
        "goal": "Test missing type in artifact",
        "readonlyFiles": ["tests/test.py"],
        "expectedArtifacts": {
            "file": "src/test.py",
            "contains": [
                {
                    # Missing 'type' which is required
                    "name": "my_function",
                    "parameters": [],
                }
            ],
        },
        "validationCommand": ["pytest"],
    }
    with pytest.raises(ValidationError) as exc_info:
        validate_schema(manifest_missing_type, SCHEMA_PATH)
    assert "'type' is a required property" in str(exc_info.value)


def test_validate_schema_with_function_returns():
    """
    Tests that a manifest with function return type is valid.
    """
    manifest_with_returns = {
        "goal": "Test function with return type",
        "readonlyFiles": ["tests/test.py"],
        "expectedArtifacts": {
            "file": "src/test.py",
            "contains": [
                {
                    "type": "function",
                    "name": "get_value",
                    "parameters": [{"name": "key", "type": "str"}],
                    "returns": "Optional[str]",
                }
            ],
        },
        "validationCommand": ["pytest"],
    }
    # This should not raise an exception
    validate_schema(manifest_with_returns, SCHEMA_PATH)


def test_validate_schema_with_parameter_types():
    """
    Tests that parameters with 'type' property are valid.
    """
    manifest_with_param_types = {
        "goal": "Test parameters with types",
        "readonlyFiles": ["tests/test.py"],
        "expectedArtifacts": {
            "file": "src/test.py",
            "contains": [
                {
                    "type": "function",
                    "name": "typed_function",
                    "parameters": [
                        {"name": "text", "type": "str"},
                        {"name": "count", "type": "int"},
                        {"name": "options", "type": "Dict[str, Any]"},
                    ],
                }
            ],
        },
        "validationCommand": ["pytest"],
    }
    # This should not raise an exception
    validate_schema(manifest_with_param_types, SCHEMA_PATH)


def test_validate_schema_with_missing_expected_artifacts_file():
    """
    Tests that expectedArtifacts without 'file' field fails validation.
    """
    manifest_missing_file = {
        "goal": "Test missing file in expectedArtifacts",
        "readonlyFiles": ["tests/test.py"],
        "expectedArtifacts": {
            # Missing 'file' which is required
            "contains": [{"type": "function", "name": "test"}],
        },
        "validationCommand": ["pytest"],
    }
    with pytest.raises(ValidationError) as exc_info:
        validate_schema(manifest_missing_file, SCHEMA_PATH)
    assert "'file' is a required property" in str(exc_info.value)


def test_validate_schema_with_empty_contains_array():
    """
    Tests that manifest with empty 'contains' array is valid.
    """
    manifest_empty_contains = {
        "goal": "Test empty contains array",
        "readonlyFiles": ["tests/test.py"],
        "expectedArtifacts": {
            "file": "src/test.py",
            "contains": [],  # Empty array should be valid
        },
        "validationCommand": ["pytest"],
    }
    # This should not raise an exception
    validate_schema(manifest_empty_contains, SCHEMA_PATH)
