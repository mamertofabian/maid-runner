"""
Behavioral tests for Task-005: Type Validation functionality - extract_type_annotation.
These tests USE the extract_type_annotation function to verify it works correctly.
"""

import ast
import pytest

# Import with fallback for Red phase testing
try:
    from maid_runner.validators.manifest_validator import (
        extract_type_annotation,
    )
except ImportError as e:
    # In Red phase, these won't exist yet
    pytest.skip(f"Implementation not ready: {e}", allow_module_level=True)


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
