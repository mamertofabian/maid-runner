"""
Behavioral tests for Task-005: Type Validation functionality - _ArtifactCollector attributes.
These tests USE the _ArtifactCollector class to verify it tracks types correctly.
"""

import ast
import pytest

# Import with fallback for Red phase testing
try:
    from maid_runner.validators.manifest_validator import (
        _ArtifactCollector,
    )
except ImportError as e:
    # In Red phase, these won't exist yet
    pytest.skip(f"Implementation not ready: {e}", allow_module_level=True)


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
