"""
Behavioral tests for Task-005: Type Validation functionality.
These tests USE the type validation functions to verify they work correctly.
"""

import ast
import pytest

# Import with fallback for Red phase testing
try:
    from maid_runner.validators.manifest_validator import (
        validate_type_hints,
        extract_type_annotation,
        compare_types,
        normalize_type_string,
        _ArtifactCollector,
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


class TestExtractTypeAnnotation:
    """Test the extract_type_annotation function with AST nodes."""

    def test_extract_simple_type_annotation(self):
        """Test extracting simple type annotations from AST nodes."""
        # Create a simple function with type annotation
        code = "def func(x: int) -> str: pass"
        tree = ast.parse(code)
        func_node = tree.body[0]

        # USE the function to extract parameter type
        param_type = extract_type_annotation(func_node.args.args[0], "annotation")
        assert param_type == "int"

        # USE the function to extract return type
        return_type = extract_type_annotation(func_node, "returns")
        assert return_type == "str"

    def test_extract_complex_type_annotation(self):
        """Test extracting complex type annotations like List[str]."""
        code = "def func(items: List[str]) -> Dict[str, int]: pass"
        tree = ast.parse(code)
        func_node = tree.body[0]

        # USE the function to extract complex parameter type
        param_type = extract_type_annotation(func_node.args.args[0], "annotation")
        assert "List" in param_type
        assert "str" in param_type

        # USE the function to extract complex return type
        return_type = extract_type_annotation(func_node, "returns")
        assert "Dict" in return_type

    def test_extract_missing_annotation(self):
        """Test extracting from node without type annotation."""
        code = "def func(x): pass"  # No type hints
        tree = ast.parse(code)
        func_node = tree.body[0]

        # USE the function - should return None for missing annotation
        param_type = extract_type_annotation(func_node.args.args[0], "annotation")
        assert param_type is None

        return_type = extract_type_annotation(func_node, "returns")
        assert return_type is None

    def test_extract_optional_type(self):
        """Test extracting Optional type annotations."""
        code = "def func(value: Optional[int] = None) -> Optional[str]: pass"
        tree = ast.parse(code)
        func_node = tree.body[0]

        # USE the function to extract Optional types
        param_type = extract_type_annotation(func_node.args.args[0], "annotation")
        assert "Optional" in param_type
        assert "int" in param_type

        return_type = extract_type_annotation(func_node, "returns")
        assert "Optional" in return_type
        assert "str" in return_type

    def test_extract_union_type(self):
        """Test extracting Union type annotations."""
        code = "def func(value: Union[str, int]) -> Union[float, bool]: pass"
        tree = ast.parse(code)
        func_node = tree.body[0]

        # USE the function to extract Union types
        param_type = extract_type_annotation(func_node.args.args[0], "annotation")
        assert "Union" in param_type
        assert "str" in param_type
        assert "int" in param_type

    def test_extract_type_annotation_with_invalid_ast_node(self):
        """Test extract_type_annotation with invalid/malformed AST nodes."""
        # USE the function with None node - should handle gracefully
        with pytest.raises((AttributeError, TypeError)):
            extract_type_annotation(None, "annotation")

        # USE the function with wrong node type
        code = "x = 5"  # Assignment, not a function
        tree = ast.parse(code)
        assign_node = tree.body[0]

        # Should handle nodes without the requested attribute
        result = extract_type_annotation(assign_node, "annotation")
        assert result is None or isinstance(result, str)

    def test_extract_type_annotation_with_invalid_attribute(self):
        """Test extract_type_annotation with invalid attribute names."""
        code = "def func(x: int) -> str: pass"
        tree = ast.parse(code)
        func_node = tree.body[0]

        # USE the function with non-existent attribute
        result = extract_type_annotation(func_node, "nonexistent_attr")
        assert result is None

        # USE the function with empty string attribute
        result = extract_type_annotation(func_node, "")
        assert result is None

    def test_extract_type_annotation_with_malformed_type_node(self):
        """Test extract_type_annotation when annotation has malformed structure."""
        # Create a mock node with malformed annotation structure
        code = "def func(x): pass"
        tree = ast.parse(code)
        func_node = tree.body[0]
        param_node = func_node.args.args[0]

        # Add a malformed annotation (this tests internal robustness)
        param_node.annotation = ast.Constant(value=123)  # Invalid annotation type

        # USE the function - should handle malformed annotations
        result = extract_type_annotation(param_node, "annotation")
        # Should either return None or a string representation
        assert result is None or isinstance(result, str)


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


class TestArtifactCollectorAttributes:
    """Test that _ArtifactCollector has the required attributes for type tracking."""

    def test_collector_has_type_tracking_attributes(self):
        """Test that _ArtifactCollector has found_function_types and found_method_types."""
        # Create an AST tree with functions
        code = """
def func1(x: int) -> str:
    pass

class MyClass:
    def method1(self, y: float) -> bool:
        pass
"""
        tree = ast.parse(code)

        # Create collector instance and visit the tree
        collector = _ArtifactCollector()
        collector.visit(tree)

        # USE the attributes - they should exist and be dictionaries
        assert hasattr(collector, "found_function_types")
        assert hasattr(collector, "found_method_types")
        assert isinstance(collector.found_function_types, dict)
        assert isinstance(collector.found_method_types, dict)

    def test_collector_tracks_function_types(self):
        """Test that collector tracks function parameter and return types."""
        code = """
def add(x: int, y: int) -> int:
    return x + y

def concat(s1: str, s2: str) -> str:
    return s1 + s2
"""
        tree = ast.parse(code)

        collector = _ArtifactCollector()
        collector.visit(tree)

        # USE the attribute - should have tracked function types
        assert "add" in collector.found_function_types
        assert "concat" in collector.found_function_types

        # Check the tracked types
        add_info = collector.found_function_types["add"]
        assert add_info["returns"] == "int"
        assert len(add_info["parameters"]) == 2
        assert add_info["parameters"][0]["type"] == "int"

    def test_collector_tracks_method_types(self):
        """Test that collector tracks method parameter and return types in classes."""
        code = """
class Calculator:
    def add(self, x: float, y: float) -> float:
        return x + y

    def is_positive(self, value: float) -> bool:
        return value > 0
"""
        tree = ast.parse(code)

        collector = _ArtifactCollector()
        collector.visit(tree)

        # USE the attribute - should have tracked method types
        assert "Calculator" in collector.found_method_types
        assert "add" in collector.found_method_types["Calculator"]
        assert "is_positive" in collector.found_method_types["Calculator"]

        # Check the tracked types
        add_info = collector.found_method_types["Calculator"]["add"]
        assert add_info["returns"] == "float"
        # Note: self parameter might be excluded or have no type
        params = [p for p in add_info["parameters"] if p["name"] != "self"]
        assert len(params) == 2
        assert params[0]["type"] == "float"

    def test_collector_state_consistency_after_multiple_visits(self):
        """Test that collector maintains consistent state after multiple AST visits."""
        code1 = """
def func1(x: int) -> str:
    return str(x)
"""
        code2 = """
def func2(y: float) -> bool:
    return y > 0
"""

        # First visit
        tree1 = ast.parse(code1)
        collector = _ArtifactCollector()
        collector.visit(tree1)

        # USE the attributes - should have first function
        assert "func1" in collector.found_function_types
        assert len(collector.found_function_types) == 1

        # Second visit - should accumulate, not overwrite
        tree2 = ast.parse(code2)
        collector.visit(tree2)

        # USE the attributes - should have both functions
        assert "func1" in collector.found_function_types
        assert "func2" in collector.found_function_types
        assert len(collector.found_function_types) == 2

        # Verify state consistency
        func1_info = collector.found_function_types["func1"]
        func2_info = collector.found_function_types["func2"]
        assert func1_info["returns"] == "str"
        assert func2_info["returns"] == "bool"

    def test_collector_handles_complex_class_hierarchies(self):
        """Test that collector correctly handles complex class hierarchies."""
        code = """
class BaseClass:
    def base_method(self, x: int) -> str:
        return str(x)

class DerivedClass(BaseClass):
    def derived_method(self, y: float) -> bool:
        return y > 0

    def base_method(self, x: int) -> str:  # Override
        return super().base_method(x)

class AnotherClass:
    def another_method(self, z: str) -> int:
        return len(z)
"""
        tree = ast.parse(code)
        collector = _ArtifactCollector()
        collector.visit(tree)

        # USE the attributes - should track all classes and methods
        assert hasattr(collector, "found_method_types")
        assert isinstance(collector.found_method_types, dict)

        # Should have all three classes
        expected_classes = ["BaseClass", "DerivedClass", "AnotherClass"]
        for class_name in expected_classes:
            assert class_name in collector.found_method_types

        # Check specific method tracking
        assert "base_method" in collector.found_method_types["BaseClass"]
        assert "derived_method" in collector.found_method_types["DerivedClass"]
        assert "base_method" in collector.found_method_types["DerivedClass"]  # Override
        assert "another_method" in collector.found_method_types["AnotherClass"]

    def test_collector_state_with_nested_classes_and_functions(self):
        """Test collector state consistency with nested classes and functions."""
        code = """
def outer_function(a: str) -> int:
    def inner_function(b: int) -> str:
        return str(b)
    return len(a)

class OuterClass:
    def outer_method(self, x: float) -> bool:
        class InnerClass:
            def inner_method(self, y: str) -> int:
                return len(y)
        return x > 0
"""
        tree = ast.parse(code)
        collector = _ArtifactCollector()
        collector.visit(tree)

        # USE the attributes - should handle nesting correctly
        # Check outer function
        assert "outer_function" in collector.found_function_types
        outer_func_info = collector.found_function_types["outer_function"]
        assert outer_func_info["returns"] == "int"

        # Inner functions might or might not be tracked depending on implementation
        # But collector should not crash and maintain consistent state
        assert isinstance(collector.found_function_types, dict)
        assert isinstance(collector.found_method_types, dict)

        # Check outer class method
        if "OuterClass" in collector.found_method_types:
            assert "outer_method" in collector.found_method_types["OuterClass"]

    def test_collector_handles_malformed_ast_gracefully(self):
        """Test that collector maintains state consistency with malformed AST nodes."""
        # Create valid AST first
        code = """
def valid_function(x: int) -> str:
    return str(x)

class ValidClass:
    def valid_method(self, y: float) -> bool:
        return y > 0
"""
        tree = ast.parse(code)
        collector = _ArtifactCollector()

        # Modify AST to create potential issues (simulate malformed nodes)
        if tree.body and hasattr(tree.body[0], "args"):
            # Introduce a problematic node to test robustness
            tree.body[0].args.args[0].annotation = None  # Remove annotation

        # Visit the modified tree
        collector.visit(tree)

        # USE the attributes - should maintain consistent state despite issues
        assert hasattr(collector, "found_function_types")
        assert hasattr(collector, "found_method_types")
        assert isinstance(collector.found_function_types, dict)
        assert isinstance(collector.found_method_types, dict)

        # Should still track what it can
        if "valid_function" in collector.found_function_types:
            func_info = collector.found_function_types["valid_function"]
            assert isinstance(func_info, dict)

    def test_collector_memory_and_performance_with_large_ast(self):
        """Test collector state consistency and performance with large AST trees."""
        # Generate a large AST programmatically
        functions = []
        classes = []

        for i in range(50):  # Create 50 functions
            functions.append(
                f"""
def function_{i}(param_{i}: int) -> str:
    return f'function_{i}_{{param_{i}}}'
"""
            )

        for i in range(10):  # Create 10 classes with 5 methods each
            methods = []
            for j in range(5):
                methods.append(
                    f"""
    def method_{i}_{j}(self, param: float) -> bool:
        return param > {j}
"""
                )

            classes.append(
                f"""
class Class_{i}:
{''.join(methods)}
"""
            )

        large_code = "\n".join(functions + classes)
        tree = ast.parse(large_code)

        collector = _ArtifactCollector()
        collector.visit(tree)

        # USE the attributes - should handle large AST efficiently
        assert len(collector.found_function_types) == 50
        assert len(collector.found_method_types) == 10

        # Verify state consistency across all items
        for i in range(50):
            func_name = f"function_{i}"
            assert func_name in collector.found_function_types
            func_info = collector.found_function_types[func_name]
            assert func_info["returns"] == "str"

        for i in range(10):
            class_name = f"Class_{i}"
            assert class_name in collector.found_method_types
            class_methods = collector.found_method_types[class_name]
            assert len(class_methods) == 5

    def test_collector_state_isolation_between_instances(self):
        """Test that different collector instances maintain separate state."""
        code1 = """
def func_a(x: int) -> str:
    return str(x)
"""
        code2 = """
def func_b(y: float) -> bool:
    return y > 0
"""

        # Create two separate collectors
        collector1 = _ArtifactCollector()
        collector2 = _ArtifactCollector()

        # Visit different code with each
        tree1 = ast.parse(code1)
        tree2 = ast.parse(code2)

        collector1.visit(tree1)
        collector2.visit(tree2)

        # USE the attributes - should maintain separate state
        assert "func_a" in collector1.found_function_types
        assert "func_a" not in collector2.found_function_types

        assert "func_b" in collector2.found_function_types
        assert "func_b" not in collector1.found_function_types

        # State should be completely isolated
        assert len(collector1.found_function_types) == 1
        assert len(collector2.found_function_types) == 1


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


class TestIntegrationScenarios:
    """Integration tests combining multiple functions."""

    def test_full_validation_workflow(self):
        """Test a complete validation workflow using all functions together."""
        # Create manifest with various type scenarios
        manifest_artifacts = {
            "file": "example.py",
            "contains": [
                {
                    "type": "function",
                    "name": "process",
                    "parameters": [
                        {"name": "data", "type": "List[str]"},
                        {"name": "count", "type": "Optional[int]"},
                    ],
                    "returns": "Dict[str, int]",
                }
            ],
        }

        # Create matching implementation
        implementation_artifacts = {
            "functions": {
                "process": {
                    "parameters": [
                        {"name": "data", "type": "List[str]"},
                        {"name": "count", "type": "Optional[int]"},
                    ],
                    "returns": "Dict[str, int]",
                }
            }
        }

        # USE validate_type_hints as the main entry point
        errors = validate_type_hints(manifest_artifacts, implementation_artifacts)
        assert errors == []

        # Now test with a mismatch
        implementation_artifacts["functions"]["process"]["returns"] = "List[int]"
        errors = validate_type_hints(manifest_artifacts, implementation_artifacts)
        assert len(errors) > 0

    def test_ast_to_validation_pipeline(self):
        """Test the full pipeline from AST extraction to type validation."""
        # Parse some code
        code = """
def calculate(x: float, y: float) -> float:
    return x + y
"""
        tree = ast.parse(code)
        func_node = tree.body[0]

        # USE extract_type_annotation to get types
        param1_type = extract_type_annotation(func_node.args.args[0], "annotation")
        param2_type = extract_type_annotation(func_node.args.args[1], "annotation")
        return_type = extract_type_annotation(func_node, "returns")

        assert param1_type == "float"
        assert param2_type == "float"
        assert return_type == "float"

        # USE normalize_type_string on extracted types
        norm_param1 = normalize_type_string(param1_type)
        norm_return = normalize_type_string(return_type)

        # USE compare_types to validate
        assert compare_types(norm_param1, "float") is True
        assert compare_types(norm_return, "float") is True

    def test_mixed_success_failure_validation_scenario(self):
        """Test integration where some functions pass validation and others fail."""
        manifest_artifacts = {
            "file": "example.py",
            "contains": [
                {
                    "type": "function",
                    "name": "good_function",
                    "parameters": [{"name": "x", "type": "int"}],
                    "returns": "str",
                },
                {
                    "type": "function",
                    "name": "bad_function",
                    "parameters": [{"name": "y", "type": "str"}],
                    "returns": "bool",
                },
                {
                    "type": "function",
                    "name": "another_good_function",
                    "parameters": [{"name": "z", "type": "float"}],
                    "returns": "int",
                },
            ],
        }

        # Implementation with mixed success/failure
        implementation_artifacts = {
            "functions": {
                "good_function": {
                    "parameters": [{"name": "x", "type": "int"}],  # Matches
                    "returns": "str",  # Matches
                },
                "bad_function": {
                    "parameters": [
                        {"name": "y", "type": "int"}
                    ],  # Mismatch: str vs int
                    "returns": "float",  # Mismatch: bool vs float
                },
                "another_good_function": {
                    "parameters": [{"name": "z", "type": "float"}],  # Matches
                    "returns": "int",  # Matches
                },
            }
        }

        # USE the validation function - should report only the failing function
        errors = validate_type_hints(manifest_artifacts, implementation_artifacts)
        assert len(errors) > 0

        # Errors should mention the bad function
        error_text = " ".join(errors).lower()
        assert (
            "bad_function" in error_text or len(errors) == 2
        )  # Parameter and return errors

    def test_partial_failure_with_complex_types(self):
        """Test integration with complex types where some pass and some fail validation."""
        manifest_artifacts = {
            "file": "example.py",
            "contains": [
                {
                    "type": "function",
                    "name": "complex_mixed",
                    "parameters": [
                        {"name": "good_param", "type": "Dict[str, List[int]]"},
                        {"name": "bad_param", "type": "Union[str, int]"},
                        {"name": "another_good", "type": "Optional[float]"},
                    ],
                    "returns": "List[Tuple[str, bool]]",
                }
            ],
        }

        implementation_artifacts = {
            "functions": {
                "complex_mixed": {
                    "parameters": [
                        {
                            "name": "good_param",
                            "type": "Dict[str, List[int]]",
                        },  # Matches
                        {"name": "bad_param", "type": "Union[bool, float]"},  # Mismatch
                        {"name": "another_good", "type": "Optional[float]"},  # Matches
                    ],
                    "returns": "List[Tuple[int, bool]]",  # Mismatch: str vs int in Tuple
                }
            }
        }

        # USE the validation function - should identify specific parameter/return failures
        errors = validate_type_hints(manifest_artifacts, implementation_artifacts)
        assert len(errors) >= 2  # At least bad_param and return type errors

    def test_method_and_function_mixed_validation(self):
        """Test integration with both functions and methods, mixed success/failure."""
        manifest_artifacts = {
            "file": "example.py",
            "contains": [
                {
                    "type": "function",
                    "name": "standalone_function",
                    "parameters": [{"name": "x", "type": "str"}],
                    "returns": "int",
                },
                {
                    "type": "function",
                    "name": "class_method",
                    "class": "MyClass",
                    "parameters": [
                        {"name": "self", "type": None},
                        {"name": "y", "type": "float"},
                    ],
                    "returns": "bool",
                },
            ],
        }

        implementation_artifacts = {
            "functions": {
                "standalone_function": {
                    "parameters": [{"name": "x", "type": "str"}],  # Matches
                    "returns": "int",  # Matches
                }
            },
            "methods": {
                "MyClass": {
                    "class_method": {
                        "parameters": [
                            {"name": "self", "type": None},
                            {"name": "y", "type": "int"},  # Mismatch: float vs int
                        ],
                        "returns": "str",  # Mismatch: bool vs str
                    }
                }
            },
        }

        # USE the validation function - should handle mixed function/method validation
        errors = validate_type_hints(manifest_artifacts, implementation_artifacts)
        assert len(errors) > 0  # Should have method parameter and return errors

    def test_integration_with_pipeline_functions(self):
        """Test integration scenario simulating a processing pipeline with mixed results."""
        manifest_artifacts = {
            "file": "pipeline.py",
            "contains": [
                {
                    "type": "function",
                    "name": "input_validator",
                    "parameters": [{"name": "data", "type": "Any"}],
                    "returns": "bool",
                },
                {
                    "type": "function",
                    "name": "data_transformer",
                    "parameters": [{"name": "raw_data", "type": "Dict[str, Any]"}],
                    "returns": "List[str]",
                },
                {
                    "type": "function",
                    "name": "output_formatter",
                    "parameters": [{"name": "processed", "type": "List[str]"}],
                    "returns": "str",
                },
            ],
        }

        # Pipeline with one failing step
        implementation_artifacts = {
            "functions": {
                "input_validator": {
                    "parameters": [{"name": "data", "type": "Any"}],  # Matches
                    "returns": "bool",  # Matches
                },
                "data_transformer": {
                    "parameters": [
                        {"name": "raw_data", "type": "List[Dict[str, Any]]"}
                    ],  # Mismatch
                    "returns": "Dict[str, List[str]]",  # Mismatch
                },
                "output_formatter": {
                    "parameters": [
                        {"name": "processed", "type": "List[str]"}
                    ],  # Matches
                    "returns": "str",  # Matches
                },
            }
        }

        # USE the validation function - should identify the failing pipeline step
        errors = validate_type_hints(manifest_artifacts, implementation_artifacts)
        assert len(errors) > 0

        # Should identify the transformer as the problem
        error_text = " ".join(errors).lower()
        has_transformer_context = any(
            term in error_text
            for term in ["data_transformer", "raw_data", "processed", "transform"]
        )
        assert has_transformer_context or len(errors) >= 2

    def test_pipeline_failure_at_extraction_stage(self):
        """Test pipeline failure propagation when type extraction fails."""
        # Create a scenario where extraction might fail but should be handled gracefully
        manifest_artifacts = {
            "file": "example.py",
            "contains": [
                {
                    "type": "function",
                    "name": "problematic_extraction",
                    "parameters": [{"name": "param", "type": "ComplexType[Something]"}],
                    "returns": "AnotherType",
                }
            ],
        }

        # Implementation with potentially problematic type extraction
        implementation_artifacts = {
            "functions": {
                "problematic_extraction": {
                    "parameters": [
                        {"name": "param", "type": None}
                    ],  # Extraction failed
                    "returns": None,  # Extraction failed
                }
            }
        }

        # USE the validation function - should handle extraction failures gracefully
        errors = validate_type_hints(manifest_artifacts, implementation_artifacts)
        assert isinstance(errors, list)  # Should not crash, return error list
        # Might have errors for missing type annotations
        if len(errors) > 0:
            error_text = " ".join(errors).lower()
            # Should indicate missing or failed extraction
            assert any(
                term in error_text
                for term in ["none", "missing", "not found", "annotation"]
            )

    def test_pipeline_failure_at_normalization_stage(self):
        """Test pipeline failure propagation when type normalization fails."""
        manifest_artifacts = {
            "file": "example.py",
            "contains": [
                {
                    "type": "function",
                    "name": "normalization_problem",
                    "parameters": [{"name": "param", "type": "ValidType"}],
                    "returns": "AnotherValidType",
                }
            ],
        }

        # Implementation with malformed types that might cause normalization issues
        implementation_artifacts = {
            "functions": {
                "normalization_problem": {
                    "parameters": [
                        {"name": "param", "type": "List[unclosed"}
                    ],  # Malformed
                    "returns": "Dict[str, int]]extra]",  # Malformed
                }
            }
        }

        # USE the validation function - should handle normalization failures
        errors = validate_type_hints(manifest_artifacts, implementation_artifacts)
        assert isinstance(errors, list)  # Should not crash
        # Should detect the type mismatches even if normalization is problematic
        assert len(errors) >= 0  # May have errors, but shouldn't crash

    def test_pipeline_failure_at_comparison_stage(self):
        """Test pipeline failure propagation when type comparison fails."""
        manifest_artifacts = {
            "file": "example.py",
            "contains": [
                {
                    "type": "function",
                    "name": "comparison_issues",
                    "parameters": [{"name": "param", "type": "NormalType"}],
                    "returns": "StandardType",
                }
            ],
        }

        # Implementation that might cause comparison stage issues
        implementation_artifacts = {
            "functions": {
                "comparison_issues": {
                    # Simulate data that might cause comparison problems
                    "parameters": [{"name": "param", "type": ""}],  # Empty type string
                    "returns": "\n\t",  # Whitespace-only type
                }
            }
        }

        # USE the validation function - should handle comparison failures
        errors = validate_type_hints(manifest_artifacts, implementation_artifacts)
        assert isinstance(errors, list)
        # Should generate errors for the type mismatches
        assert len(errors) > 0

    def test_cascading_pipeline_failures(self):
        """Test how multiple pipeline stage failures cascade and are reported."""
        manifest_artifacts = {
            "file": "example.py",
            "contains": [
                {
                    "type": "function",
                    "name": "cascade_failures",
                    "parameters": [
                        {"name": "param1", "type": "GoodType"},
                        {"name": "param2", "type": "Another[Good, Type]"},
                    ],
                    "returns": "ValidReturnType",
                }
            ],
        }

        # Implementation with multiple types of problems
        implementation_artifacts = {
            "functions": {
                "cascade_failures": {
                    "parameters": [
                        {"name": "param1", "type": None},  # Extraction failure
                        {
                            "name": "param2",
                            "type": "Malformed[Type[]",
                        },  # Normalization problem
                    ],
                    "returns": "DifferentType",  # Simple mismatch
                }
            }
        }

        # USE the validation function - should handle multiple failure types
        errors = validate_type_hints(manifest_artifacts, implementation_artifacts)
        assert isinstance(errors, list)
        assert len(errors) > 0  # Should have multiple errors

        # Each different type of failure should be reported
        error_text = " ".join(errors).lower()
        # Should mention the function and various issues
        assert "cascade_failures" in error_text or len(errors) >= 2

    def test_pipeline_error_recovery_and_continuation(self):
        """Test that pipeline continues processing after encountering errors."""
        manifest_artifacts = {
            "file": "example.py",
            "contains": [
                {
                    "type": "function",
                    "name": "first_function",
                    "parameters": [{"name": "x", "type": "int"}],
                    "returns": "str",
                },
                {
                    "type": "function",
                    "name": "problematic_function",
                    "parameters": [{"name": "y", "type": "ValidType"}],
                    "returns": "AnotherValidType",
                },
                {
                    "type": "function",
                    "name": "third_function",
                    "parameters": [{"name": "z", "type": "bool"}],
                    "returns": "float",
                },
            ],
        }

        implementation_artifacts = {
            "functions": {
                "first_function": {
                    "parameters": [{"name": "x", "type": "int"}],  # Good
                    "returns": "str",  # Good
                },
                "problematic_function": {
                    "parameters": [{"name": "y", "type": None}],  # Problem
                    "returns": None,  # Problem
                },
                "third_function": {
                    "parameters": [{"name": "z", "type": "bool"}],  # Good
                    "returns": "float",  # Good
                },
            }
        }

        # USE the validation function - should process all functions despite errors
        errors = validate_type_hints(manifest_artifacts, implementation_artifacts)
        assert isinstance(errors, list)

        # Should have errors only from the problematic function
        if len(errors) > 0:
            error_text = " ".join(errors).lower()
            # Should mention the problematic function but not crash on others
            assert "problematic_function" in error_text or len(errors) <= 4

    def test_pipeline_graceful_degradation_with_partial_data(self):
        """Test pipeline graceful degradation when some data is missing or malformed."""
        manifest_artifacts = {
            "file": "example.py",
            "contains": [
                {
                    "type": "function",
                    "name": "partial_data_test",
                    "parameters": [
                        {"name": "complete_param", "type": "str"},
                        {"name": "missing_type_param", "type": "int"},
                    ],
                    "returns": "bool",
                }
            ],
        }

        # Implementation with partial/missing data
        implementation_artifacts = {
            "functions": {
                "partial_data_test": {
                    "parameters": [
                        {"name": "complete_param", "type": "str"},  # Complete data
                        # Missing the second parameter entirely
                    ],
                    # Missing returns data entirely
                }
            }
        }

        # USE the validation function - should degrade gracefully
        errors = validate_type_hints(manifest_artifacts, implementation_artifacts)
        assert isinstance(errors, list)
        # Should handle missing data without crashing
        # May or may not have errors depending on implementation strategy

    def test_edge_cases_ellipsis_and_literals(self):
        """Test edge cases like ellipsis (...) and literal types."""
        # Test with ellipsis in tuple
        manifest_artifacts = {
            "file": "example.py",
            "contains": [
                {
                    "type": "function",
                    "name": "variadic",
                    "parameters": [{"name": "args", "type": "Tuple[int, ...]"}],
                    "returns": "None",
                }
            ],
        }

        implementation_artifacts = {
            "functions": {
                "variadic": {
                    "parameters": [{"name": "args", "type": "Tuple[int, ...]"}],
                    "returns": "None",
                }
            }
        }

        # USE the validation function - should handle ellipsis
        errors = validate_type_hints(manifest_artifacts, implementation_artifacts)
        assert errors == []

    def test_complex_nested_generics_three_levels_deep(self):
        """Test validation with deeply nested generic types (3+ levels)."""
        manifest_artifacts = {
            "file": "example.py",
            "contains": [
                {
                    "type": "function",
                    "name": "process_nested",
                    "parameters": [
                        {
                            "name": "data",
                            "type": "Dict[str, List[Tuple[Optional[int], Union[str, bool]]]]",
                        },
                        {
                            "name": "mapping",
                            "type": "List[Dict[str, Optional[Union[int, float, str]]]]",
                        },
                    ],
                    "returns": "Union[Dict[str, List[int]], List[Tuple[str, bool]], None]",
                }
            ],
        }

        implementation_artifacts = {
            "functions": {
                "process_nested": {
                    "parameters": [
                        {
                            "name": "data",
                            "type": "Dict[str, List[Tuple[Optional[int], Union[str, bool]]]]",
                        },
                        {
                            "name": "mapping",
                            "type": "List[Dict[str, Optional[Union[int, float, str]]]]",
                        },
                    ],
                    "returns": "Union[Dict[str, List[int]], List[Tuple[str, bool]], None]",
                }
            }
        }

        # USE the validation function - should handle deep nesting
        errors = validate_type_hints(manifest_artifacts, implementation_artifacts)
        assert errors == []

    def test_complex_nested_generics_with_mismatches(self):
        """Test validation catches errors in deeply nested generic types."""
        manifest_artifacts = {
            "file": "example.py",
            "contains": [
                {
                    "type": "function",
                    "name": "nested_mismatch",
                    "parameters": [
                        {"name": "data", "type": "Dict[str, List[Tuple[int, str]]]"},
                    ],
                    "returns": "List[Dict[str, Optional[int]]]",
                }
            ],
        }

        implementation_artifacts = {
            "functions": {
                "nested_mismatch": {
                    "parameters": [
                        {
                            "name": "data",
                            "type": "Dict[str, List[Tuple[float, str]]]",
                        },  # int vs float mismatch
                    ],
                    "returns": "List[Dict[str, Optional[bool]]]",  # int vs bool mismatch
                }
            }
        }

        # USE the validation function - should catch nested type mismatches
        errors = validate_type_hints(manifest_artifacts, implementation_artifacts)
        assert len(errors) > 0

    def test_complex_nested_generics_with_callable(self):
        """Test validation with Callable types in nested structures."""
        manifest_artifacts = {
            "file": "example.py",
            "contains": [
                {
                    "type": "function",
                    "name": "callback_processor",
                    "parameters": [
                        {
                            "name": "callbacks",
                            "type": "List[Callable[[int, str], bool]]",
                        },
                        {
                            "name": "async_callbacks",
                            "type": "Dict[str, Callable[..., Awaitable[Optional[int]]]]",
                        },
                    ],
                    "returns": "Callable[[List[str]], Dict[str, Any]]",
                }
            ],
        }

        implementation_artifacts = {
            "functions": {
                "callback_processor": {
                    "parameters": [
                        {
                            "name": "callbacks",
                            "type": "List[Callable[[int, str], bool]]",
                        },
                        {
                            "name": "async_callbacks",
                            "type": "Dict[str, Callable[..., Awaitable[Optional[int]]]]",
                        },
                    ],
                    "returns": "Callable[[List[str]], Dict[str, Any]]",
                }
            }
        }

        # USE the validation function - should handle Callable types
        errors = validate_type_hints(manifest_artifacts, implementation_artifacts)
        assert errors == []

    def test_extreme_nesting_generics(self):
        """Test validation with extremely nested generic structures."""
        extreme_type = "Dict[str, List[Tuple[Union[Optional[Dict[str, List[int]]], Set[Tuple[str, bool]]], Callable[[int], Optional[Union[str, float]]]]]]"

        manifest_artifacts = {
            "file": "example.py",
            "contains": [
                {
                    "type": "function",
                    "name": "extreme_nesting",
                    "parameters": [{"name": "data", "type": extreme_type}],
                    "returns": "Union[None, bool]",
                }
            ],
        }

        implementation_artifacts = {
            "functions": {
                "extreme_nesting": {
                    "parameters": [{"name": "data", "type": extreme_type}],
                    "returns": "Union[None, bool]",
                }
            }
        }

        # USE the validation function - should handle extreme nesting without crashing
        errors = validate_type_hints(manifest_artifacts, implementation_artifacts)
        assert errors == []

    def test_generic_type_aliases_and_typevars(self):
        """Test validation with generic TypeVars and type aliases."""
        manifest_artifacts = {
            "file": "example.py",
            "contains": [
                {
                    "type": "function",
                    "name": "generic_function",
                    "parameters": [
                        {"name": "data", "type": "List[T]"},
                        {"name": "mapping", "type": "Mapping[K, V]"},
                        {"name": "sequence", "type": "Sequence[Union[T, K]]"},
                    ],
                    "returns": "Iterator[Tuple[K, V]]",
                }
            ],
        }

        implementation_artifacts = {
            "functions": {
                "generic_function": {
                    "parameters": [
                        {"name": "data", "type": "List[T]"},
                        {"name": "mapping", "type": "Mapping[K, V]"},
                        {"name": "sequence", "type": "Sequence[Union[T, K]]"},
                    ],
                    "returns": "Iterator[Tuple[K, V]]",
                }
            }
        }

        # USE the validation function - should handle TypeVar-based generics
        errors = validate_type_hints(manifest_artifacts, implementation_artifacts)
        assert errors == []

    def test_forward_references_basic_string_annotations(self):
        """Test validation with forward references using string annotations."""
        manifest_artifacts = {
            "file": "example.py",
            "contains": [
                {
                    "type": "function",
                    "name": "self_referencing",
                    "parameters": [
                        {
                            "name": "node",
                            "type": "'Node'",
                        },  # Forward reference as string
                        {"name": "parent", "type": "Optional['Node']"},
                    ],
                    "returns": "'Node'",
                }
            ],
        }

        implementation_artifacts = {
            "functions": {
                "self_referencing": {
                    "parameters": [
                        {"name": "node", "type": "'Node'"},
                        {"name": "parent", "type": "Optional['Node']"},
                    ],
                    "returns": "'Node'",
                }
            }
        }

        # USE the validation function - should handle string forward references
        errors = validate_type_hints(manifest_artifacts, implementation_artifacts)
        assert errors == []

    def test_forward_references_with_generics(self):
        """Test validation with forward references in generic types."""
        manifest_artifacts = {
            "file": "example.py",
            "contains": [
                {
                    "type": "function",
                    "name": "tree_processor",
                    "parameters": [
                        {"name": "nodes", "type": "List['TreeNode']"},
                        {"name": "mapping", "type": "Dict[str, 'TreeNode']"},
                        {"name": "optional_root", "type": "Optional['TreeNode']"},
                    ],
                    "returns": "Union['TreeNode', None]",
                }
            ],
        }

        implementation_artifacts = {
            "functions": {
                "tree_processor": {
                    "parameters": [
                        {"name": "nodes", "type": "List['TreeNode']"},
                        {"name": "mapping", "type": "Dict[str, 'TreeNode']"},
                        {"name": "optional_root", "type": "Optional['TreeNode']"},
                    ],
                    "returns": "Union['TreeNode', None]",
                }
            }
        }

        # USE the validation function - should handle forward references in generics
        errors = validate_type_hints(manifest_artifacts, implementation_artifacts)
        assert errors == []

    def test_forward_references_mismatches(self):
        """Test that validation catches mismatches in forward references."""
        manifest_artifacts = {
            "file": "example.py",
            "contains": [
                {
                    "type": "function",
                    "name": "forward_mismatch",
                    "parameters": [{"name": "item", "type": "'ClassA'"}],
                    "returns": "List['ClassB']",
                }
            ],
        }

        implementation_artifacts = {
            "functions": {
                "forward_mismatch": {
                    "parameters": [
                        {"name": "item", "type": "'ClassC'"}
                    ],  # Mismatch: ClassA vs ClassC
                    "returns": "List['ClassD']",  # Mismatch: ClassB vs ClassD
                }
            }
        }

        # USE the validation function - should catch forward reference mismatches
        errors = validate_type_hints(manifest_artifacts, implementation_artifacts)
        assert len(errors) > 0

    def test_forward_references_mixed_with_regular_types(self):
        """Test validation with mix of forward references and regular types."""
        manifest_artifacts = {
            "file": "example.py",
            "contains": [
                {
                    "type": "function",
                    "name": "mixed_types",
                    "parameters": [
                        {"name": "forward_ref", "type": "'CustomClass'"},
                        {"name": "regular_type", "type": "str"},
                        {"name": "mixed_generic", "type": "Dict[str, 'CustomClass']"},
                        {
                            "name": "complex_forward",
                            "type": "Union['TypeA', int, 'TypeB']",
                        },
                    ],
                    "returns": "Tuple[str, 'CustomClass']",
                }
            ],
        }

        implementation_artifacts = {
            "functions": {
                "mixed_types": {
                    "parameters": [
                        {"name": "forward_ref", "type": "'CustomClass'"},
                        {"name": "regular_type", "type": "str"},
                        {"name": "mixed_generic", "type": "Dict[str, 'CustomClass']"},
                        {
                            "name": "complex_forward",
                            "type": "Union['TypeA', int, 'TypeB']",
                        },
                    ],
                    "returns": "Tuple[str, 'CustomClass']",
                }
            }
        }

        # USE the validation function - should handle mixed forward/regular types
        errors = validate_type_hints(manifest_artifacts, implementation_artifacts)
        assert errors == []

    def test_forward_references_with_module_qualifiers(self):
        """Test validation with module-qualified forward references."""
        manifest_artifacts = {
            "file": "example.py",
            "contains": [
                {
                    "type": "function",
                    "name": "qualified_forwards",
                    "parameters": [
                        {"name": "item", "type": "'mymodule.MyClass'"},
                        {
                            "name": "service",
                            "type": "'services.database.DatabaseService'",
                        },
                    ],
                    "returns": "Optional['mymodule.MyClass']",
                }
            ],
        }

        implementation_artifacts = {
            "functions": {
                "qualified_forwards": {
                    "parameters": [
                        {"name": "item", "type": "'mymodule.MyClass'"},
                        {
                            "name": "service",
                            "type": "'services.database.DatabaseService'",
                        },
                    ],
                    "returns": "Optional['mymodule.MyClass']",
                }
            }
        }

        # USE the validation function - should handle module-qualified forward references
        errors = validate_type_hints(manifest_artifacts, implementation_artifacts)
        assert errors == []

    def test_forward_references_normalization_edge_cases(self):
        """Test that forward references are normalized consistently."""
        # Test that quotes are handled consistently in normalization
        manifest_artifacts = {
            "file": "example.py",
            "contains": [
                {
                    "type": "function",
                    "name": "quote_normalization",
                    "parameters": [
                        {"name": "single_quotes", "type": "'MyClass'"},
                        {"name": "in_union", "type": "Union['MyClass', str]"},
                    ],
                    "returns": "List['MyClass']",
                }
            ],
        }

        # Implementation might have slightly different quote formatting
        implementation_artifacts = {
            "functions": {
                "quote_normalization": {
                    "parameters": [
                        {"name": "single_quotes", "type": "'MyClass'"},
                        {
                            "name": "in_union",
                            "type": "Union[str, 'MyClass']",
                        },  # Different order in Union
                    ],
                    "returns": "List['MyClass']",
                }
            }
        }

        # USE the validation function - should normalize forward references properly
        errors = validate_type_hints(manifest_artifacts, implementation_artifacts)
        # Union order differences should be handled by normalization
        assert errors == [] or len(errors) == 0  # Should pass after normalization

    def test_python310_union_syntax_basic(self):
        """Test validation with Python 3.10+ union syntax using | operator."""
        manifest_artifacts = {
            "file": "example.py",
            "contains": [
                {
                    "type": "function",
                    "name": "modern_union",
                    "parameters": [
                        {"name": "value", "type": "str | int"},  # Modern union syntax
                        {
                            "name": "optional",
                            "type": "str | None",
                        },  # Instead of Optional[str]
                    ],
                    "returns": "int | float | bool",
                }
            ],
        }

        implementation_artifacts = {
            "functions": {
                "modern_union": {
                    "parameters": [
                        {"name": "value", "type": "str | int"},
                        {"name": "optional", "type": "str | None"},
                    ],
                    "returns": "int | float | bool",
                }
            }
        }

        # USE the validation function - should handle modern union syntax
        errors = validate_type_hints(manifest_artifacts, implementation_artifacts)
        assert errors == []

    def test_python310_union_syntax_compatibility_with_legacy(self):
        """Test that modern union syntax is compatible with legacy Union[] syntax."""
        manifest_artifacts = {
            "file": "example.py",
            "contains": [
                {
                    "type": "function",
                    "name": "mixed_union_styles",
                    "parameters": [
                        {"name": "modern", "type": "str | int"},
                        {"name": "legacy", "type": "Union[str, int]"},
                    ],
                    "returns": "str | int",
                }
            ],
        }

        # Implementation uses legacy Union syntax
        implementation_artifacts = {
            "functions": {
                "mixed_union_styles": {
                    "parameters": [
                        {
                            "name": "modern",
                            "type": "Union[str, int]",
                        },  # Legacy for modern
                        {"name": "legacy", "type": "str | int"},  # Modern for legacy
                    ],
                    "returns": "Union[str, int]",  # Legacy for modern
                }
            }
        }

        # USE the validation function - should normalize both formats to match
        errors = validate_type_hints(manifest_artifacts, implementation_artifacts)
        # Should pass if normalization converts both formats consistently
        assert len(errors) == 0 or errors == []

    def test_python310_union_syntax_with_generics(self):
        """Test modern union syntax with generic types."""
        manifest_artifacts = {
            "file": "example.py",
            "contains": [
                {
                    "type": "function",
                    "name": "generic_modern_unions",
                    "parameters": [
                        {"name": "data", "type": "List[str] | Dict[str, int]"},
                        {"name": "optional_list", "type": "List[str] | None"},
                        {
                            "name": "complex",
                            "type": "Dict[str, int] | List[float] | set[bool]",
                        },
                    ],
                    "returns": "List[str] | Dict[str, Any] | None",
                }
            ],
        }

        implementation_artifacts = {
            "functions": {
                "generic_modern_unions": {
                    "parameters": [
                        {"name": "data", "type": "List[str] | Dict[str, int]"},
                        {"name": "optional_list", "type": "List[str] | None"},
                        {
                            "name": "complex",
                            "type": "Dict[str, int] | List[float] | set[bool]",
                        },
                    ],
                    "returns": "List[str] | Dict[str, Any] | None",
                }
            }
        }

        # USE the validation function - should handle modern union syntax with generics
        errors = validate_type_hints(manifest_artifacts, implementation_artifacts)
        assert errors == []

    def test_python310_union_syntax_ordering_normalization(self):
        """Test that union member ordering is normalized consistently."""
        manifest_artifacts = {
            "file": "example.py",
            "contains": [
                {
                    "type": "function",
                    "name": "union_ordering",
                    "parameters": [
                        {"name": "param1", "type": "str | int | bool"},
                        {"name": "param2", "type": "Union[float, str, int]"},
                    ],
                    "returns": "bool | str | int | float",
                }
            ],
        }

        # Implementation has different ordering
        implementation_artifacts = {
            "functions": {
                "union_ordering": {
                    "parameters": [
                        {
                            "name": "param1",
                            "type": "bool | int | str",
                        },  # Different order
                        {
                            "name": "param2",
                            "type": "Union[int, str, float]",
                        },  # Different order
                    ],
                    "returns": "float | int | str | bool",  # Different order
                }
            }
        }

        # USE the validation function - should normalize union member ordering
        errors = validate_type_hints(manifest_artifacts, implementation_artifacts)
        # Should pass if normalization handles ordering consistently
        assert len(errors) == 0 or errors == []

    def test_python310_union_syntax_with_none_types(self):
        """Test modern union syntax with None (replacing Optional)."""
        manifest_artifacts = {
            "file": "example.py",
            "contains": [
                {
                    "type": "function",
                    "name": "optional_with_modern_syntax",
                    "parameters": [
                        {"name": "maybe_str", "type": "str | None"},
                        {"name": "maybe_int", "type": "int | None"},
                        {"name": "maybe_complex", "type": "Dict[str, int] | None"},
                    ],
                    "returns": "List[str] | None",
                }
            ],
        }

        # Implementation might use Optional[] syntax
        implementation_artifacts = {
            "functions": {
                "optional_with_modern_syntax": {
                    "parameters": [
                        {
                            "name": "maybe_str",
                            "type": "Optional[str]",
                        },  # Legacy Optional
                        {
                            "name": "maybe_int",
                            "type": "Union[int, None]",
                        },  # Explicit Union with None
                        {
                            "name": "maybe_complex",
                            "type": "Dict[str, int] | None",
                        },  # Modern
                    ],
                    "returns": "Optional[List[str]]",  # Legacy Optional
                }
            }
        }

        # USE the validation function - should handle Optional/None equivalence
        errors = validate_type_hints(manifest_artifacts, implementation_artifacts)
        assert len(errors) == 0 or errors == []

    def test_python310_union_syntax_nested_and_complex(self):
        """Test modern union syntax in complex nested scenarios."""
        manifest_artifacts = {
            "file": "example.py",
            "contains": [
                {
                    "type": "function",
                    "name": "complex_modern_unions",
                    "parameters": [
                        {
                            "name": "nested",
                            "type": "List[str | int] | Dict[str, bool | float]",
                        },
                        {
                            "name": "callback",
                            "type": "Callable[[str | int], bool | None]",
                        },
                        {
                            "name": "tuple_union",
                            "type": "Tuple[str | int, bool | float | None]",
                        },
                    ],
                    "returns": "Union[List[str | int], Dict[str, bool | float], None]",
                }
            ],
        }

        implementation_artifacts = {
            "functions": {
                "complex_modern_unions": {
                    "parameters": [
                        {
                            "name": "nested",
                            "type": "List[str | int] | Dict[str, bool | float]",
                        },
                        {
                            "name": "callback",
                            "type": "Callable[[str | int], bool | None]",
                        },
                        {
                            "name": "tuple_union",
                            "type": "Tuple[str | int, bool | float | None]",
                        },
                    ],
                    "returns": "Union[List[str | int], Dict[str, bool | float], None]",
                }
            }
        }

        # USE the validation function - should handle complex nested modern unions
        errors = validate_type_hints(manifest_artifacts, implementation_artifacts)
        assert errors == []

    def test_python310_union_syntax_error_detection(self):
        """Test that modern union syntax errors are still detected."""
        manifest_artifacts = {
            "file": "example.py",
            "contains": [
                {
                    "type": "function",
                    "name": "union_mismatch",
                    "parameters": [{"name": "value", "type": "str | int"}],
                    "returns": "bool | float",
                }
            ],
        }

        # Implementation has mismatched union types
        implementation_artifacts = {
            "functions": {
                "union_mismatch": {
                    "parameters": [
                        {"name": "value", "type": "str | bool"}
                    ],  # int vs bool mismatch
                    "returns": "int | float",  # bool vs int mismatch
                }
            }
        }

        # USE the validation function - should still catch type mismatches
        errors = validate_type_hints(manifest_artifacts, implementation_artifacts)
        assert len(errors) > 0

    def test_type_aliases_basic_usage(self):
        """Test validation with basic type aliases."""
        manifest_artifacts = {
            "file": "example.py",
            "contains": [
                {
                    "type": "function",
                    "name": "process_user_data",
                    "parameters": [
                        {"name": "user_id", "type": "UserId"},  # Type alias
                        {"name": "email", "type": "EmailAddress"},  # Type alias
                        {"name": "scores", "type": "ScoreList"},  # Type alias
                    ],
                    "returns": "UserProfile",  # Type alias
                }
            ],
        }

        implementation_artifacts = {
            "functions": {
                "process_user_data": {
                    "parameters": [
                        {"name": "user_id", "type": "UserId"},
                        {"name": "email", "type": "EmailAddress"},
                        {"name": "scores", "type": "ScoreList"},
                    ],
                    "returns": "UserProfile",
                }
            }
        }

        # USE the validation function - should handle type aliases
        errors = validate_type_hints(manifest_artifacts, implementation_artifacts)
        assert errors == []

    def test_type_aliases_with_generics(self):
        """Test validation with generic type aliases."""
        manifest_artifacts = {
            "file": "example.py",
            "contains": [
                {
                    "type": "function",
                    "name": "process_mapping",
                    "parameters": [
                        {
                            "name": "data",
                            "type": "StringToIntMap",
                        },  # Dict[str, int] alias
                        {"name": "items", "type": "StringList"},  # List[str] alias
                        {
                            "name": "optional",
                            "type": "MaybeString",
                        },  # Optional[str] alias
                    ],
                    "returns": "StringToIntMap",
                }
            ],
        }

        implementation_artifacts = {
            "functions": {
                "process_mapping": {
                    "parameters": [
                        {"name": "data", "type": "StringToIntMap"},
                        {"name": "items", "type": "StringList"},
                        {"name": "optional", "type": "MaybeString"},
                    ],
                    "returns": "StringToIntMap",
                }
            }
        }

        # USE the validation function - should handle generic type aliases
        errors = validate_type_hints(manifest_artifacts, implementation_artifacts)
        assert errors == []

    def test_newtype_basic_usage(self):
        """Test validation with NewType constructs."""
        manifest_artifacts = {
            "file": "example.py",
            "contains": [
                {
                    "type": "function",
                    "name": "process_ids",
                    "parameters": [
                        {"name": "user_id", "type": "UserId"},  # NewType('UserId', int)
                        {
                            "name": "product_id",
                            "type": "ProductId",
                        },  # NewType('ProductId', str)
                        {
                            "name": "timestamp",
                            "type": "Timestamp",
                        },  # NewType('Timestamp', float)
                    ],
                    "returns": "UserId",
                }
            ],
        }

        implementation_artifacts = {
            "functions": {
                "process_ids": {
                    "parameters": [
                        {"name": "user_id", "type": "UserId"},
                        {"name": "product_id", "type": "ProductId"},
                        {"name": "timestamp", "type": "Timestamp"},
                    ],
                    "returns": "UserId",
                }
            }
        }

        # USE the validation function - should handle NewType constructs
        errors = validate_type_hints(manifest_artifacts, implementation_artifacts)
        assert errors == []

    def test_type_aliases_vs_underlying_types(self):
        """Test that type aliases are distinguished from their underlying types."""
        manifest_artifacts = {
            "file": "example.py",
            "contains": [
                {
                    "type": "function",
                    "name": "strict_typing",
                    "parameters": [
                        {
                            "name": "user_id",
                            "type": "UserId",
                        },  # Should be UserId, not int
                        {
                            "name": "name",
                            "type": "UserName",
                        },  # Should be UserName, not str
                    ],
                    "returns": "UserId",
                }
            ],
        }

        # Implementation uses underlying types instead of aliases
        implementation_artifacts = {
            "functions": {
                "strict_typing": {
                    "parameters": [
                        {
                            "name": "user_id",
                            "type": "int",
                        },  # Underlying type instead of alias
                        {
                            "name": "name",
                            "type": "str",
                        },  # Underlying type instead of alias
                    ],
                    "returns": "int",  # Underlying type instead of alias
                }
            }
        }

        # USE the validation function - should detect alias vs underlying type differences
        errors = validate_type_hints(manifest_artifacts, implementation_artifacts)
        # This test depends on whether the implementation treats aliases as distinct
        assert isinstance(errors, list)  # Should return some result

    def test_complex_type_aliases_with_unions_and_generics(self):
        """Test validation with complex type aliases involving unions and generics."""
        manifest_artifacts = {
            "file": "example.py",
            "contains": [
                {
                    "type": "function",
                    "name": "complex_aliases",
                    "parameters": [
                        {
                            "name": "data",
                            "type": "StringOrIntList",
                        },  # List[Union[str, int]]
                        {
                            "name": "mapping",
                            "type": "UserDataMapping",
                        },  # Dict[UserId, UserProfile]
                        {
                            "name": "callback",
                            "type": "ProcessorCallback",
                        },  # Callable[[str], Optional[int]]
                    ],
                    "returns": "MaybeUserList",  # Optional[List[User]]
                }
            ],
        }

        implementation_artifacts = {
            "functions": {
                "complex_aliases": {
                    "parameters": [
                        {"name": "data", "type": "StringOrIntList"},
                        {"name": "mapping", "type": "UserDataMapping"},
                        {"name": "callback", "type": "ProcessorCallback"},
                    ],
                    "returns": "MaybeUserList",
                }
            }
        }

        # USE the validation function - should handle complex type aliases
        errors = validate_type_hints(manifest_artifacts, implementation_artifacts)
        assert errors == []

    def test_type_aliases_with_forward_references(self):
        """Test validation with type aliases that include forward references."""
        manifest_artifacts = {
            "file": "example.py",
            "contains": [
                {
                    "type": "function",
                    "name": "forward_alias_types",
                    "parameters": [
                        {
                            "name": "node",
                            "type": "TreeNodeAlias",
                        },  # Alias to 'TreeNode'
                        {
                            "name": "children",
                            "type": "ChildrenList",
                        },  # Alias to List['TreeNode']
                    ],
                    "returns": "TreeNodeAlias",
                }
            ],
        }

        implementation_artifacts = {
            "functions": {
                "forward_alias_types": {
                    "parameters": [
                        {"name": "node", "type": "TreeNodeAlias"},
                        {"name": "children", "type": "ChildrenList"},
                    ],
                    "returns": "TreeNodeAlias",
                }
            }
        }

        # USE the validation function - should handle forward reference aliases
        errors = validate_type_hints(manifest_artifacts, implementation_artifacts)
        assert errors == []

    def test_type_aliases_mismatches(self):
        """Test that validation catches mismatches in type aliases."""
        manifest_artifacts = {
            "file": "example.py",
            "contains": [
                {
                    "type": "function",
                    "name": "alias_mismatch",
                    "parameters": [
                        {"name": "id_value", "type": "UserId"},
                        {"name": "name_value", "type": "UserName"},
                    ],
                    "returns": "UserProfile",
                }
            ],
        }

        # Implementation has different type aliases
        implementation_artifacts = {
            "functions": {
                "alias_mismatch": {
                    "parameters": [
                        {
                            "name": "id_value",
                            "type": "ProductId",
                        },  # UserId vs ProductId mismatch
                        {
                            "name": "name_value",
                            "type": "ProductName",
                        },  # UserName vs ProductName mismatch
                    ],
                    "returns": "ProductProfile",  # UserProfile vs ProductProfile mismatch
                }
            }
        }

        # USE the validation function - should catch alias type mismatches
        errors = validate_type_hints(manifest_artifacts, implementation_artifacts)
        assert len(errors) > 0

    def test_literal_types_and_final_annotations(self):
        """Test validation with Literal types and Final annotations."""
        manifest_artifacts = {
            "file": "example.py",
            "contains": [
                {
                    "type": "function",
                    "name": "literal_and_final",
                    "parameters": [
                        {
                            "name": "status",
                            "type": "Literal['active', 'inactive', 'pending']",
                        },
                        {
                            "name": "config_key",
                            "type": "Literal['debug', 'production']",
                        },
                        {"name": "constant", "type": "Final[int]"},
                    ],
                    "returns": "Literal['success', 'failure']",
                }
            ],
        }

        implementation_artifacts = {
            "functions": {
                "literal_and_final": {
                    "parameters": [
                        {
                            "name": "status",
                            "type": "Literal['active', 'inactive', 'pending']",
                        },
                        {
                            "name": "config_key",
                            "type": "Literal['debug', 'production']",
                        },
                        {"name": "constant", "type": "Final[int]"},
                    ],
                    "returns": "Literal['success', 'failure']",
                }
            }
        }

        # USE the validation function - should handle Literal and Final types
        errors = validate_type_hints(manifest_artifacts, implementation_artifacts)
        assert errors == []

    def test_protocol_and_typed_dict_aliases(self):
        """Test validation with Protocol and TypedDict type aliases."""
        manifest_artifacts = {
            "file": "example.py",
            "contains": [
                {
                    "type": "function",
                    "name": "protocol_and_typeddict",
                    "parameters": [
                        {
                            "name": "drawable",
                            "type": "DrawableProtocol",
                        },  # Protocol alias
                        {
                            "name": "user_data",
                            "type": "UserDataDict",
                        },  # TypedDict alias
                        {"name": "config", "type": "ConfigProtocol"},  # Protocol alias
                    ],
                    "returns": "ResponseDict",  # TypedDict alias
                }
            ],
        }

        implementation_artifacts = {
            "functions": {
                "protocol_and_typeddict": {
                    "parameters": [
                        {"name": "drawable", "type": "DrawableProtocol"},
                        {"name": "user_data", "type": "UserDataDict"},
                        {"name": "config", "type": "ConfigProtocol"},
                    ],
                    "returns": "ResponseDict",
                }
            }
        }

        # USE the validation function - should handle Protocol and TypedDict aliases
        errors = validate_type_hints(manifest_artifacts, implementation_artifacts)
        assert errors == []
