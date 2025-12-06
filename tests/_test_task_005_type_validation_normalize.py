"""
Behavioral tests for Task-005: Type Validation functionality - normalize_type_string.
These tests USE the normalize_type_string function to verify it works correctly.
"""

import pytest

# Import with fallback for Red phase testing
try:
    from maid_runner.validators.manifest_validator import (
        normalize_type_string,
    )
except ImportError as e:
    # In Red phase, these won't exist yet
    pytest.skip(f"Implementation not ready: {e}", allow_module_level=True)


class TestNormalizeTypeString:
    """Test the normalize_type_string function."""

    def test_normalize_simple_types(self):
        """Test normalizing simple type strings."""
        # USE the function - simple types should remain unchanged
        assert normalize_type_string("int") == "int"
        assert normalize_type_string("str") == "str"
        assert normalize_type_string("bool") == "bool"

    def test_normalize_removes_extra_spaces(self):
        """Test that normalization removes extra spaces."""
        # USE the function - should remove extra spaces
        assert normalize_type_string("List[ str ]") == "List[str]"
        assert normalize_type_string("Dict[ str , int ]") == "Dict[str, int]"
        assert normalize_type_string("  int  ") == "int"

    def test_normalize_optional_to_union(self):
        """Test that Optional is normalized to Union with None."""
        # USE the function - Optional should become Union[X, None]
        result = normalize_type_string("Optional[int]")
        assert "Union" in result
        assert "int" in result
        assert "None" in result

    def test_normalize_union_sorting(self):
        """Test that Union types are sorted consistently."""
        # USE the function - Union members should be sorted
        result1 = normalize_type_string("Union[str, int]")
        result2 = normalize_type_string("Union[int, str]")
        assert result1 == result2

    def test_normalize_nested_types(self):
        """Test normalizing nested complex types."""
        # USE the function - should handle nested types
        result = normalize_type_string("Dict[str, List[int]]")
        assert "Dict[str, List[int]]" in result or "Dict[str,List[int]]" in result

    def test_normalize_none_input(self):
        """Test normalizing None input."""
        # USE the function - None should return None
        assert normalize_type_string(None) is None

    def test_normalize_any_type(self):
        """Test normalizing Any type."""
        # USE the function - Any should remain Any
        assert normalize_type_string("Any") == "Any"
        assert normalize_type_string("typing.Any") in ["typing.Any", "Any"]

    def test_normalize_type_string_with_invalid_syntax(self):
        """Test normalize_type_string with malformed type syntax."""
        # USE the function with unclosed brackets
        result = normalize_type_string("List[str")
        # Should handle gracefully - either fix it or return as-is
        assert isinstance(result, str)

        # USE the function with mismatched brackets
        result = normalize_type_string("Dict[str, int]]")
        assert isinstance(result, str)

        # USE the function with empty brackets
        result = normalize_type_string("List[]")
        assert isinstance(result, str)

    def test_normalize_type_string_with_invalid_characters(self):
        """Test normalize_type_string with invalid characters."""
        # USE the function with special characters
        result = normalize_type_string("List[@#$%]")
        assert isinstance(result, str)

        # USE the function with quotes in wrong places
        result = normalize_type_string('List["str"int]')
        assert isinstance(result, str)

        # USE the function with newlines and tabs
        result = normalize_type_string("Dict[str,\n\tint]")
        assert isinstance(result, str)

    def test_normalize_type_string_with_recursive_brackets(self):
        """Test normalize_type_string with deeply nested or recursive bracket issues."""
        # USE the function with extremely nested structure that might cause issues
        deeply_nested = "Dict[str, List[Tuple[Union[Optional[int], str], bool]]]" * 10
        result = normalize_type_string(deeply_nested)
        assert isinstance(result, str)

        # USE the function with circular-like references in string
        result = normalize_type_string("Union[Union[int, str], Union[str, int]]")
        assert isinstance(result, str)

    def test_normalize_type_string_with_empty_and_whitespace(self):
        """Test normalize_type_string with edge case inputs."""
        # USE the function with empty string
        result = normalize_type_string("")
        assert result == "" or result is None

        # USE the function with only whitespace
        result = normalize_type_string("   ")
        assert result == "" or result == "   "

        # USE the function with mixed whitespace and tabs
        result = normalize_type_string("\t  \n  \r")
        assert isinstance(result, str) or result is None
