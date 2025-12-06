"""
Behavioral tests for Task-005: Type Validation functionality - validate_type_hints.
These tests USE the validate_type_hints function to verify it works correctly.
"""

import pytest

# Import with fallback for Red phase testing
try:
    from maid_runner.validators.manifest_validator import (
        validate_type_hints,
    )
except ImportError as e:
    # In Red phase, these won't exist yet
    pytest.skip(f"Implementation not ready: {e}", allow_module_level=True)


class TestValidateTypeHints:
    """Test the validate_type_hints function with various scenarios."""

    def test_validate_matching_simple_types(self):
        """Test validation when simple types match between manifest and implementation."""
        manifest_artifacts = {
            "file": "example.py",
            "contains": [
                {
                    "type": "function",
                    "name": "add_numbers",
                    "parameters": [
                        {"name": "x", "type": "int"},
                        {"name": "y", "type": "int"},
                    ],
                    "returns": "int",
                }
            ],
        }

        implementation_artifacts = {
            "functions": {
                "add_numbers": {
                    "parameters": [
                        {"name": "x", "type": "int"},
                        {"name": "y", "type": "int"},
                    ],
                    "returns": "int",
                }
            }
        }

        # USE the function - should return empty list (no errors)
        errors = validate_type_hints(manifest_artifacts, implementation_artifacts)
        assert errors == []

    def test_validate_type_mismatch_in_parameters(self):
        """Test validation catches parameter type mismatches."""
        manifest_artifacts = {
            "file": "example.py",
            "contains": [
                {
                    "type": "function",
                    "name": "process_data",
                    "parameters": [{"name": "data", "type": "str"}],
                    "returns": "bool",
                }
            ],
        }

        implementation_artifacts = {
            "functions": {
                "process_data": {
                    "parameters": [{"name": "data", "type": "int"}],  # Wrong type
                    "returns": "bool",
                }
            }
        }

        # USE the function - should return errors
        errors = validate_type_hints(manifest_artifacts, implementation_artifacts)
        assert len(errors) > 0
        assert "type mismatch" in errors[0].lower()

    def test_validate_missing_type_annotations(self):
        """Test validation when implementation lacks type annotations."""
        manifest_artifacts = {
            "file": "example.py",
            "contains": [
                {
                    "type": "function",
                    "name": "compute",
                    "parameters": [{"name": "value", "type": "float"}],
                    "returns": "float",
                }
            ],
        }

        implementation_artifacts = {
            "functions": {
                "compute": {
                    "parameters": [
                        {"name": "value", "type": None}  # No type annotation
                    ],
                    "returns": None,  # No return type
                }
            }
        }

        # USE the function - should return errors for missing annotations
        errors = validate_type_hints(manifest_artifacts, implementation_artifacts)
        assert len(errors) > 0

    def test_validate_complex_types(self):
        """Test validation with complex type hints like List, Dict, Optional."""
        manifest_artifacts = {
            "file": "example.py",
            "contains": [
                {
                    "type": "function",
                    "name": "process_list",
                    "parameters": [
                        {"name": "items", "type": "List[str]"},
                        {"name": "mapping", "type": "Dict[str, int]"},
                        {"name": "optional_value", "type": "Optional[int]"},
                    ],
                    "returns": "Union[str, int]",
                }
            ],
        }

        implementation_artifacts = {
            "functions": {
                "process_list": {
                    "parameters": [
                        {"name": "items", "type": "List[str]"},
                        {"name": "mapping", "type": "Dict[str, int]"},
                        {"name": "optional_value", "type": "Optional[int]"},
                    ],
                    "returns": "Union[str, int]",
                }
            }
        }

        # USE the function - should validate complex types correctly
        errors = validate_type_hints(manifest_artifacts, implementation_artifacts)
        assert errors == []

    def test_validate_method_types_in_classes(self):
        """Test validation of method type hints within classes."""
        manifest_artifacts = {
            "file": "example.py",
            "contains": [
                {
                    "type": "function",
                    "name": "calculate",
                    "class": "Calculator",
                    "parameters": [
                        {"name": "self", "type": None},  # self has no type
                        {"name": "x", "type": "float"},
                        {"name": "y", "type": "float"},
                    ],
                    "returns": "float",
                }
            ],
        }

        implementation_artifacts = {
            "methods": {
                "Calculator": {
                    "calculate": {
                        "parameters": [
                            {"name": "self", "type": None},
                            {"name": "x", "type": "float"},
                            {"name": "y", "type": "float"},
                        ],
                        "returns": "float",
                    }
                }
            }
        }

        # USE the function - should handle method validation
        errors = validate_type_hints(manifest_artifacts, implementation_artifacts)
        assert errors == []

    def test_validate_with_any_type(self):
        """Test validation with Any type annotation."""
        manifest_artifacts = {
            "file": "example.py",
            "contains": [
                {
                    "type": "function",
                    "name": "accept_anything",
                    "parameters": [{"name": "data", "type": "Any"}],
                    "returns": "Any",
                }
            ],
        }

        implementation_artifacts = {
            "functions": {
                "accept_anything": {
                    "parameters": [{"name": "data", "type": "Any"}],
                    "returns": "Any",
                }
            }
        }

        # USE the function - should handle Any type
        errors = validate_type_hints(manifest_artifacts, implementation_artifacts)
        assert errors == []

    def test_validate_type_hints_with_corrupted_manifest_data(self):
        """Test validate_type_hints with malformed manifest_artifacts."""
        implementation_artifacts = {
            "functions": {
                "test_func": {
                    "parameters": [{"name": "x", "type": "int"}],
                    "returns": "str",
                }
            }
        }

        # USE the function with None manifest
        errors = validate_type_hints(None, implementation_artifacts)
        assert isinstance(errors, list)  # Should handle gracefully

        # USE the function with missing required keys
        bad_manifest = {"file": "test.py"}  # Missing "contains"
        errors = validate_type_hints(bad_manifest, implementation_artifacts)
        assert isinstance(errors, list)

        # USE the function with wrong data types
        bad_manifest = {"file": "test.py", "contains": "not a list"}
        errors = validate_type_hints(bad_manifest, implementation_artifacts)
        assert isinstance(errors, list)

        # USE the function with malformed contains items
        bad_manifest = {
            "file": "test.py",
            "contains": [
                "not a dict",  # Should be a dict
                {"type": "function", "name": "test_func"},  # Missing parameters/returns
            ],
        }
        errors = validate_type_hints(bad_manifest, implementation_artifacts)
        assert isinstance(errors, list)

    def test_validate_type_hints_with_corrupted_implementation_data(self):
        """Test validate_type_hints with malformed implementation_artifacts."""
        manifest_artifacts = {
            "file": "example.py",
            "contains": [
                {
                    "type": "function",
                    "name": "test_func",
                    "parameters": [{"name": "x", "type": "int"}],
                    "returns": "str",
                }
            ],
        }

        # USE the function with None implementation
        errors = validate_type_hints(manifest_artifacts, None)
        assert isinstance(errors, list)  # Should handle gracefully

        # USE the function with wrong data structure
        bad_implementation = "not a dict"
        errors = validate_type_hints(manifest_artifacts, bad_implementation)
        assert isinstance(errors, list)

        # USE the function with missing function data
        bad_implementation = {"functions": None}
        errors = validate_type_hints(manifest_artifacts, bad_implementation)
        assert isinstance(errors, list)

        # USE the function with malformed function data
        bad_implementation = {
            "functions": {
                "test_func": "not a dict"  # Should be a dict with parameters/returns
            }
        }
        errors = validate_type_hints(manifest_artifacts, bad_implementation)
        assert isinstance(errors, list)

    def test_validate_type_hints_with_missing_required_fields(self):
        """Test validate_type_hints with missing required fields in data structures."""
        # USE the function with manifest missing function name
        bad_manifest = {
            "file": "test.py",
            "contains": [
                {
                    "type": "function",
                    # "name": "missing",  # Missing required name field
                    "parameters": [],
                    "returns": "None",
                }
            ],
        }
        implementation_artifacts = {"functions": {}}
        errors = validate_type_hints(bad_manifest, implementation_artifacts)
        assert isinstance(errors, list)

        # USE the function with implementation missing parameter types
        manifest_artifacts = {
            "file": "test.py",
            "contains": [
                {
                    "type": "function",
                    "name": "test_func",
                    "parameters": [{"name": "x", "type": "int"}],
                    "returns": "str",
                }
            ],
        }
        bad_implementation = {
            "functions": {
                "test_func": {
                    # Missing "parameters" and "returns" keys
                }
            }
        }
        errors = validate_type_hints(manifest_artifacts, bad_implementation)
        assert isinstance(errors, list)

    def test_validate_type_hints_with_recursive_data_structures(self):
        """Test validate_type_hints with pathological recursive data."""
        # Create circular reference in data (should handle gracefully)
        circular_dict = {"functions": {}}
        circular_dict["functions"]["self_ref"] = circular_dict

        manifest_artifacts = {
            "file": "test.py",
            "contains": [{"type": "function", "name": "any_func"}],
        }

        # USE the function with circular references - should not crash
        errors = validate_type_hints(manifest_artifacts, circular_dict)
        assert isinstance(errors, list)
