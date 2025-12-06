"""
Behavioral tests for Task-005: Type Validation functionality - compare_types.
These tests USE the compare_types function to verify it works correctly.
"""

import pytest

# Import with fallback for Red phase testing
try:
    from maid_runner.validators.manifest_validator import (
        compare_types,
    )
except ImportError as e:
    # In Red phase, these won't exist yet
    pytest.skip(f"Implementation not ready: {e}", allow_module_level=True)


class TestCompareTypes:
    """Test the compare_types function with various type string comparisons."""

    def test_compare_identical_simple_types(self):
        """Test comparing identical simple type strings."""
        # USE the function - identical types should match
        assert compare_types("int", "int") is True
        assert compare_types("str", "str") is True
        assert compare_types("bool", "bool") is True
        assert compare_types("float", "float") is True

    def test_compare_different_simple_types(self):
        """Test comparing different simple type strings."""
        # USE the function - different types should not match
        assert compare_types("int", "str") is False
        assert compare_types("bool", "int") is False
        assert compare_types("float", "str") is False

    def test_compare_complex_types_with_brackets(self):
        """Test comparing complex types with brackets."""
        # USE the function - should handle List, Dict, etc.
        assert compare_types("List[str]", "List[str]") is True
        assert compare_types("Dict[str, int]", "Dict[str, int]") is True
        assert compare_types("List[int]", "List[str]") is False

    def test_compare_optional_types(self):
        """Test comparing Optional type variations."""
        # USE the function - should handle Optional
        assert compare_types("Optional[int]", "Optional[int]") is True
        assert compare_types("Optional[str]", "Optional[int]") is False

        # Optional[X] should match Union[X, None]
        assert compare_types("Optional[int]", "Union[int, None]") is True

    def test_compare_union_types(self):
        """Test comparing Union types with different orderings."""
        # USE the function - Union order shouldn't matter
        assert compare_types("Union[str, int]", "Union[int, str]") is True
        assert compare_types("Union[str, int, bool]", "Union[bool, int, str]") is True
        assert compare_types("Union[str, int]", "Union[str, bool]") is False

    def test_compare_with_none_values(self):
        """Test comparing when one or both values are None."""
        # USE the function - None handling
        assert compare_types(None, None) is True
        assert compare_types("int", None) is False
        assert compare_types(None, "str") is False

    def test_compare_normalized_spacing(self):
        """Test that spacing differences are normalized."""
        # USE the function - should handle spacing variations
        assert compare_types("Dict[str,int]", "Dict[str, int]") is True
        assert compare_types("Union[ str , int ]", "Union[str,int]") is True

    def test_compare_types_with_non_string_inputs(self):
        """Test compare_types with non-string inputs."""
        # USE the function with integer inputs
        result = compare_types(123, 456)
        # Should handle gracefully by converting to string or returning False
        assert isinstance(result, bool)

        # USE the function with list inputs
        result = compare_types(["int", "str"], ["str", "int"])
        assert isinstance(result, bool)

        # USE the function with dict inputs
        result = compare_types({"type": "int"}, {"type": "str"})
        assert isinstance(result, bool)

    def test_compare_types_with_malformed_type_strings(self):
        """Test compare_types with malformed type syntax."""
        # USE the function with unclosed brackets
        result = compare_types("List[str", "List[str]")
        assert isinstance(result, bool)

        # USE the function with mismatched bracket types
        result = compare_types("Dict[str, int}", "Dict[str, int]")
        assert isinstance(result, bool)

        # USE the function with invalid nesting
        result = compare_types("Union[int, List[str, int]]", "Union[int, str]")
        assert isinstance(result, bool)

    def test_compare_types_with_extreme_inputs(self):
        """Test compare_types with extreme or pathological inputs."""
        # USE the function with extremely long type strings
        long_type1 = "Union[" + ", ".join([f"Type{i}" for i in range(1000)]) + "]"
        long_type2 = "Union[" + ", ".join([f"Type{i}" for i in range(1000)]) + "]"
        result = compare_types(long_type1, long_type2)
        assert isinstance(result, bool)

        # USE the function with deeply nested types
        nested_type = "Dict[str, List[Tuple[Optional[Union[int, str]], bool]]]"
        result = compare_types(nested_type, nested_type)
        assert isinstance(result, bool)

        # USE the function with circular-like patterns
        result = compare_types(
            "Union[int, Union[str, int]]", "Union[str, Union[int, str]]"
        )
        assert isinstance(result, bool)

    def test_compare_types_with_special_characters(self):
        """Test compare_types with special characters and edge cases."""
        # USE the function with Unicode characters
        result = compare_types("Tÿpë[ïñt]", "Type[int]")
        assert isinstance(result, bool)

        # USE the function with control characters
        result = compare_types("List\n[str\t]", "List[str]")
        assert isinstance(result, bool)

        # USE the function with quotes and escape sequences
        result = compare_types('Dict["str", "int"]', "Dict[str, int]")
        assert isinstance(result, bool)
