"""Tests for enhanced manifest schema features."""

import pytest
from pathlib import Path

from maid_runner.validators.manifest_validator import validate_schema

SCHEMA_PATH = Path("maid_runner/validators/schemas/manifest.schema.json")


def test_enhanced_format_validation_commands():
    """Test that validationCommands (array of arrays) format validates."""
    manifest = {
        "goal": "Test enhanced format",
        "readonlyFiles": [],
        "expectedArtifacts": {"file": "test.py", "contains": []},
        "validationCommands": [
            ["pytest", "tests/test1.py", "-v"],
            ["pytest", "tests/test2.py", "-v"],
        ],
    }
    validate_schema(manifest, str(SCHEMA_PATH))


def test_enhanced_format_args():
    """Test that args field validates alongside parameters."""
    manifest = {
        "goal": "Test enhanced format",
        "readonlyFiles": [],
        "expectedArtifacts": {
            "file": "test.py",
            "contains": [
                {
                    "type": "function",
                    "name": "test_func",
                    "args": [
                        {"name": "param1", "type": "str"},
                        {"name": "param2", "type": "int"},
                    ],
                }
            ],
        },
        "validationCommand": ["pytest", "tests/test.py"],
    }
    validate_schema(manifest, str(SCHEMA_PATH))


def test_legacy_format_still_validates():
    """Test that legacy format (validationCommand, parameters) still validates."""
    manifest = {
        "goal": "Test legacy format",
        "readonlyFiles": [],
        "expectedArtifacts": {
            "file": "test.py",
            "contains": [
                {
                    "type": "function",
                    "name": "test_func",
                    "parameters": [{"name": "param1"}, {"name": "param2"}],
                }
            ],
        },
        "validationCommand": ["pytest", "tests/test.py"],
    }
    validate_schema(manifest, str(SCHEMA_PATH))


def test_mixed_format_validates():
    """Test that mixed format (some old, some new fields) validates."""
    manifest = {
        "goal": "Test mixed format",
        "readonlyFiles": [],
        "expectedArtifacts": {
            "file": "test.py",
            "contains": [
                {
                    "type": "function",
                    "name": "test_func",
                    "parameters": [{"name": "param1"}],  # Legacy
                    "args": [{"name": "param1", "type": "str"}],  # Enhanced
                }
            ],
        },
        "validationCommand": ["pytest", "tests/test.py"],  # Legacy
    }
    validate_schema(manifest, str(SCHEMA_PATH))


def test_metadata_field_validates():
    """Test that metadata field validates."""
    manifest = {
        "goal": "Test metadata",
        "readonlyFiles": [],
        "expectedArtifacts": {"file": "test.py", "contains": []},
        "validationCommand": ["pytest", "tests/test.py"],
        "metadata": {
            "author": "test@example.com",
            "created": "2025-01-10",
            "tags": ["test", "validation"],
            "priority": "high",
        },
    }
    validate_schema(manifest, str(SCHEMA_PATH))


def test_returns_object_format():
    """Test that returns field accepts object format."""
    manifest = {
        "goal": "Test returns object format",
        "readonlyFiles": [],
        "expectedArtifacts": {
            "file": "test.py",
            "contains": [
                {
                    "type": "function",
                    "name": "test_func",
                    "returns": {"type": "Optional[dict]"},
                }
            ],
        },
        "validationCommand": ["pytest", "tests/test.py"],
    }
    validate_schema(manifest, str(SCHEMA_PATH))


def test_returns_string_format_still_valid():
    """Test that returns string format still validates."""
    manifest = {
        "goal": "Test returns string format",
        "readonlyFiles": [],
        "expectedArtifacts": {
            "file": "test.py",
            "contains": [{"type": "function", "name": "test_func", "returns": "bool"}],
        },
        "validationCommand": ["pytest", "tests/test.py"],
    }
    validate_schema(manifest, str(SCHEMA_PATH))


def test_raises_field_validates():
    """Test that raises field validates."""
    manifest = {
        "goal": "Test raises field",
        "readonlyFiles": [],
        "expectedArtifacts": {
            "file": "test.py",
            "contains": [
                {
                    "type": "function",
                    "name": "test_func",
                    "raises": ["ValueError", "TypeError"],
                }
            ],
        },
        "validationCommand": ["pytest", "tests/test.py"],
    }
    validate_schema(manifest, str(SCHEMA_PATH))


def test_invalid_validation_commands_format():
    """Test that invalid validationCommands format fails."""
    manifest = {
        "goal": "Test invalid format",
        "readonlyFiles": [],
        "expectedArtifacts": {"file": "test.py", "contains": []},
        "validationCommands": "not an array",  # Invalid
    }
    with pytest.raises(Exception):  # Should raise ValidationError
        validate_schema(manifest, str(SCHEMA_PATH))


def test_missing_both_validation_fields():
    """Test that missing both validationCommand and validationCommands fails."""
    manifest = {
        "goal": "Test missing validation",
        "readonlyFiles": [],
        "expectedArtifacts": {"file": "test.py", "contains": []},
        # Missing both validationCommand and validationCommands
    }
    with pytest.raises(Exception):  # Should raise ValidationError
        validate_schema(manifest, str(SCHEMA_PATH))
