"""
Behavioral tests for Task-005: Type Validation functionality.
These tests USE the type validation functions to verify they work correctly.
"""

import ast
import pytest

# Import with fallback for Red phase testing
try:
    from validators.manifest_validator import (
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
