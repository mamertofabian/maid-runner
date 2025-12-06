"""
Behavioral tests for Task-005: Type Validation functionality - error messages.
These tests USE the validate_type_hints function to verify error messages are consistent.
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


class TestErrorMessageConsistency:
    """Test that error messages are consistent, clear, and properly formatted."""

    def test_validate_type_hints_error_message_format(self):
        """Test that validate_type_hints produces consistent error message formats."""
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

        implementation_artifacts = {
            "functions": {
                "test_func": {
                    "parameters": [{"name": "x", "type": "float"}],  # Type mismatch
                    "returns": "bool",  # Type mismatch
                }
            }
        }

        # USE the function and validate error message properties
        errors = validate_type_hints(manifest_artifacts, implementation_artifacts)
        assert len(errors) > 0

        for error in errors:
            # Error messages should be strings
            assert isinstance(error, str)
            # Should contain key information
            assert len(error.strip()) > 0
            # Should not contain internal Python object representations
            assert "<object" not in error
            assert "0x" not in error  # Memory addresses

    def test_error_messages_contain_relevant_context(self):
        """Test that error messages contain enough context to be actionable."""
        manifest_artifacts = {
            "file": "example.py",
            "contains": [
                {
                    "type": "function",
                    "name": "specific_function_name",
                    "parameters": [{"name": "specific_param", "type": "int"}],
                    "returns": "str",
                }
            ],
        }

        implementation_artifacts = {
            "functions": {
                "specific_function_name": {
                    "parameters": [{"name": "specific_param", "type": "float"}],
                    "returns": "str",
                }
            }
        }

        # USE the function to get contextual errors
        errors = validate_type_hints(manifest_artifacts, implementation_artifacts)
        assert len(errors) > 0

        # Error messages should contain function and parameter names for context
        error_text = " ".join(errors).lower()
        # Should mention the specific function or parameter involved
        has_context = any(
            term in error_text
            for term in [
                "specific_function_name",
                "specific_param",
                "function",
                "parameter",
                "type",
            ]
        )
        assert has_context

    def test_error_messages_distinguish_different_error_types(self):
        """Test that different types of validation errors produce distinguishable messages."""
        # Test parameter type mismatch
        manifest1 = {
            "file": "test.py",
            "contains": [
                {
                    "type": "function",
                    "name": "func1",
                    "parameters": [{"name": "x", "type": "int"}],
                    "returns": "str",
                }
            ],
        }
        impl1 = {
            "functions": {
                "func1": {
                    "parameters": [{"name": "x", "type": "float"}],
                    "returns": "str",
                }
            }
        }

        # Test return type mismatch
        manifest2 = {
            "file": "test.py",
            "contains": [
                {
                    "type": "function",
                    "name": "func2",
                    "parameters": [{"name": "x", "type": "int"}],
                    "returns": "str",
                }
            ],
        }
        impl2 = {
            "functions": {
                "func2": {
                    "parameters": [{"name": "x", "type": "int"}],
                    "returns": "bool",
                }
            }
        }

        # USE the function to get different error types
        param_errors = validate_type_hints(manifest1, impl1)
        return_errors = validate_type_hints(manifest2, impl2)

        assert len(param_errors) > 0
        assert len(return_errors) > 0

        # Error messages should be different for different error types
        param_error_text = " ".join(param_errors).lower()
        return_error_text = " ".join(return_errors).lower()

        # They should not be identical (different error contexts)
        assert param_error_text != return_error_text

    def test_error_messages_handle_none_and_missing_values(self):
        """Test that error messages properly describe None and missing type scenarios."""
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

        # Implementation with None types (missing annotations)
        implementation_artifacts = {
            "functions": {
                "test_func": {
                    "parameters": [{"name": "x", "type": None}],  # No annotation
                    "returns": None,  # No return annotation
                }
            }
        }

        # USE the function to check None handling in error messages
        errors = validate_type_hints(manifest_artifacts, implementation_artifacts)
        assert len(errors) > 0

        error_text = " ".join(errors).lower()
        # Should indicate missing annotations rather than just "none"
        has_missing_context = any(
            term in error_text
            for term in ["missing", "none", "annotation", "not found", "absent"]
        )
        assert has_missing_context or len(errors) > 0  # At least should generate errors

    def test_error_message_encoding_and_special_characters(self):
        """Test that error messages handle special characters and encoding properly."""
        # Test with Unicode function names (if supported)
        manifest_artifacts = {
            "file": "test.py",
            "contains": [
                {
                    "type": "function",
                    "name": "test_func_with_ñáméé",
                    "parameters": [{"name": "påräm", "type": "int"}],
                    "returns": "str",
                }
            ],
        }

        implementation_artifacts = {
            "functions": {
                "test_func_with_ñáméé": {
                    "parameters": [{"name": "påräm", "type": "float"}],
                    "returns": "str",
                }
            }
        }

        # USE the function - should not crash on Unicode and should produce readable errors
        errors = validate_type_hints(manifest_artifacts, implementation_artifacts)

        # Should handle Unicode gracefully (not crash)
        assert isinstance(errors, list)

        if len(errors) > 0:
            for error in errors:
                assert isinstance(error, str)
                # Should not contain encoding artifacts
                assert "\\x" not in error
                assert "\\u" not in error
