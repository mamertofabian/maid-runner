"""Tests for Task-049: Fix async function detection in manifest validator.

Tests that the validator's AST collector properly detects async function
definitions (AsyncFunctionDef nodes) by aliasing visit_AsyncFunctionDef to
visit_FunctionDef, following the pattern from snapshot.py.
"""

import ast
from maid_runner.validators.manifest_validator import _ArtifactCollector


class TestAsyncFunctionDetection:
    """Test async function detection in _ArtifactCollector."""

    def test_collector_has_async_function_visitor(self):
        """Test that _ArtifactCollector has visit_AsyncFunctionDef method."""
        collector = _ArtifactCollector()
        assert hasattr(
            collector, "visit_AsyncFunctionDef"
        ), "_ArtifactCollector should have visit_AsyncFunctionDef method"

    def test_async_function_visitor_is_aliased(self):
        """Test that visit_AsyncFunctionDef is aliased to visit_FunctionDef."""
        # Check at class level (before instantiation)
        assert (
            _ArtifactCollector.visit_AsyncFunctionDef
            is _ArtifactCollector.visit_FunctionDef
        ), "visit_AsyncFunctionDef should be the same as visit_FunctionDef at class level"

    def test_detects_async_function_at_module_level(self):
        """Test that async functions at module level are detected."""
        code = """
async def async_function(param1: str, param2: int) -> dict:
    '''Async function docstring.'''
    return {"result": True}
"""
        tree = ast.parse(code)
        collector = _ArtifactCollector()
        collector.visit(tree)

        # Check that the async function was detected
        assert (
            "async_function" in collector.found_functions
        ), "Async function should be detected in found_functions"

        # found_functions stores just the parameter list
        params = collector.found_functions["async_function"]
        assert params == [
            "param1",
            "param2",
        ], "Async function parameters should be captured"

    def test_detects_async_method_in_class(self):
        """Test that async methods in classes are detected."""
        code = """
class MyClass:
    async def async_method(self, data: str) -> bool:
        '''Async method docstring.'''
        return True
"""
        tree = ast.parse(code)
        collector = _ArtifactCollector()
        collector.visit(tree)

        # Check that the async method was detected
        assert "MyClass" in collector.found_methods, "Class should be in found_methods"
        assert (
            "async_method" in collector.found_methods["MyClass"]
        ), "Async method should be detected in class methods"

        # found_methods stores the parameter list (including self)
        params = collector.found_methods["MyClass"]["async_method"]
        assert params == ["self", "data"], "Async method parameters should be captured"

    def test_detects_multiple_async_functions(self):
        """Test that multiple async functions are all detected."""
        code = """
async def first_async(x: int) -> int:
    return x

async def second_async(y: str) -> str:
    return y

def regular_function(z: bool) -> bool:
    return z
"""
        tree = ast.parse(code)
        collector = _ArtifactCollector()
        collector.visit(tree)

        # Check that all functions (async and regular) were detected
        assert (
            "first_async" in collector.found_functions
        ), "First async function should be detected"
        assert (
            "second_async" in collector.found_functions
        ), "Second async function should be detected"
        assert (
            "regular_function" in collector.found_functions
        ), "Regular function should be detected"

    def test_async_function_with_no_annotations(self):
        """Test that async functions without type annotations are detected."""
        code = """
async def no_annotations(param1, param2):
    return None
"""
        tree = ast.parse(code)
        collector = _ArtifactCollector()
        collector.visit(tree)

        # Check that the async function was detected even without annotations
        assert (
            "no_annotations" in collector.found_functions
        ), "Async function without annotations should still be detected"

        params = collector.found_functions["no_annotations"]
        assert params == [
            "param1",
            "param2",
        ], "Parameters should be captured even without type annotations"

    def test_async_classmethod_and_staticmethod(self):
        """Test that async classmethods and staticmethods are detected."""
        code = """
class MyClass:
    @classmethod
    async def async_classmethod(cls, value: int) -> int:
        return value

    @staticmethod
    async def async_staticmethod(value: str) -> str:
        return value
"""
        tree = ast.parse(code)
        collector = _ArtifactCollector()
        collector.visit(tree)

        # Check that async classmethods and staticmethods are detected
        assert "MyClass" in collector.found_methods, "Class should be in found_methods"
        assert (
            "async_classmethod" in collector.found_methods["MyClass"]
        ), "Async classmethod should be detected"
        assert (
            "async_staticmethod" in collector.found_methods["MyClass"]
        ), "Async staticmethod should be detected"


class TestAsyncFunctionValidation:
    """Integration tests for async function validation in manifests."""

    def test_validates_async_function_artifact(self, tmp_path):
        """Test that manifest validation passes for async functions."""
        # This is an integration test that would use the actual validator
        # For now, we just verify the collector works correctly
        code = """
async def maid_validate(manifest_path: str, use_chain: bool) -> dict:
    '''Validate a manifest.'''
    return {"success": True}
"""
        tree = ast.parse(code)
        collector = _ArtifactCollector()
        collector.visit(tree)

        # Verify the function was collected
        assert "maid_validate" in collector.found_functions
        params = collector.found_functions["maid_validate"]
        assert params == ["manifest_path", "use_chain"]
