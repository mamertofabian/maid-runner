"""Behavioral tests for task-064: Generic[T] base class support.

Tests that the validator properly handles ast.Subscript base classes
like Generic[T], List[str], etc.
"""

import ast
from maid_runner.validators.manifest_validator import _extract_base_class_name


class TestExtractBaseClassName:
    """Test the _extract_base_class_name function with various AST node types."""

    def test_extract_simple_name(self):
        """Test extracting base class from simple ast.Name node."""
        # Create AST for: class Foo(Bar)
        code = "class Foo(Bar): pass"
        tree = ast.parse(code)
        class_def = tree.body[0]
        base = class_def.bases[0]

        result = _extract_base_class_name(base)
        assert result == "Bar"

    def test_extract_qualified_name(self):
        """Test extracting base class from ast.Attribute node (qualified name)."""
        # Create AST for: class Foo(module.Bar)
        code = "import module\nclass Foo(module.Bar): pass"
        tree = ast.parse(code)
        class_def = tree.body[1]
        base = class_def.bases[0]

        result = _extract_base_class_name(base)
        assert result == "module.Bar"

    def test_extract_generic_subscript(self):
        """Test extracting base class from ast.Subscript node (Generic[T])."""
        # Create AST for: class Foo(Generic[T])
        code = "from typing import Generic, TypeVar\nT = TypeVar('T')\nclass Foo(Generic[T]): pass"
        tree = ast.parse(code)
        class_def = tree.body[2]
        base = class_def.bases[0]

        result = _extract_base_class_name(base)
        assert result == "Generic"

    def test_extract_qualified_generic_subscript(self):
        """Test extracting base class from qualified generic (typing.Generic[T])."""
        # Create AST for: class Foo(typing.Generic[T])
        code = (
            "import typing\nT = typing.TypeVar('T')\nclass Foo(typing.Generic[T]): pass"
        )
        tree = ast.parse(code)
        class_def = tree.body[2]
        base = class_def.bases[0]

        result = _extract_base_class_name(base)
        assert result == "typing.Generic"

    def test_extract_list_subscript(self):
        """Test extracting base class from List[str] type."""
        # Create AST for: class Foo(List[str])
        code = "from typing import List\nclass Foo(List[str]): pass"
        tree = ast.parse(code)
        class_def = tree.body[1]
        base = class_def.bases[0]

        result = _extract_base_class_name(base)
        assert result == "List"

    def test_extract_none_for_unsupported(self):
        """Test that unsupported node types return None."""
        # Create a node type that shouldn't be a base class
        node = ast.Constant(value=42)

        result = _extract_base_class_name(node)
        assert result is None


class TestGenericClassValidation:
    """Integration tests for Generic[T] class validation."""

    def test_generic_class_with_type_parameter(self):
        """Test that Generic[T] is properly registered as a base class."""
        # Create AST for a class with Generic[T] base
        code = """
from typing import Generic, TypeVar

T = TypeVar('T')

class LRUCache(Generic[T]):
    def __init__(self, capacity: int):
        self.capacity = capacity

    def get(self, key: str) -> T:
        pass

    def put(self, key: str, value: T) -> None:
        pass
"""
        tree = ast.parse(code)

        # Import the collector
        from maid_runner.validators.manifest_validator import _ArtifactCollector

        collector = _ArtifactCollector(validation_mode="implementation")
        collector.visit(tree)

        # Verify class was found
        assert "LRUCache" in collector.found_classes

        # Verify Generic is registered as a base class
        assert "LRUCache" in collector.found_class_bases
        assert "Generic" in collector.found_class_bases["LRUCache"]

    def test_multiple_generics(self):
        """Test class with multiple generic type parameters."""
        code = """
from typing import Generic, TypeVar

K = TypeVar('K')
V = TypeVar('V')

class MyDict(Generic[K, V]):
    pass
"""
        tree = ast.parse(code)

        from maid_runner.validators.manifest_validator import _ArtifactCollector

        collector = _ArtifactCollector(validation_mode="implementation")
        collector.visit(tree)

        assert "MyDict" in collector.found_classes
        assert "MyDict" in collector.found_class_bases
        assert "Generic" in collector.found_class_bases["MyDict"]

    def test_generic_with_other_bases(self):
        """Test class inheriting from both Generic[T] and other classes."""
        code = """
from typing import Generic, TypeVar

T = TypeVar('T')

class BaseClass:
    pass

class MyClass(BaseClass, Generic[T]):
    pass
"""
        tree = ast.parse(code)

        from maid_runner.validators.manifest_validator import _ArtifactCollector

        collector = _ArtifactCollector(validation_mode="implementation")
        collector.visit(tree)

        assert "MyClass" in collector.found_classes
        assert "MyClass" in collector.found_class_bases
        bases = collector.found_class_bases["MyClass"]
        assert "BaseClass" in bases
        assert "Generic" in bases

    def test_qualified_generic(self):
        """Test class with qualified Generic (typing.Generic[T])."""
        code = """
import typing

T = typing.TypeVar('T')

class MyClass(typing.Generic[T]):
    pass
"""
        tree = ast.parse(code)

        from maid_runner.validators.manifest_validator import _ArtifactCollector

        collector = _ArtifactCollector(validation_mode="implementation")
        collector.visit(tree)

        assert "MyClass" in collector.found_classes
        assert "MyClass" in collector.found_class_bases
        # Should match either "typing.Generic" or just "Generic"
        bases = collector.found_class_bases["MyClass"]
        assert "typing.Generic" in bases or "Generic" in bases
