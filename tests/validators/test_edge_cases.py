"""
Tests for edge cases and special syntax in the manifest validator.

This module tests how the validator handles:
- Empty parameter lists vs unspecified parameters
- *args and **kwargs in function signatures
- Decorated functions
- Async functions
- Properties
- Empty manifests
- Minimal and full field specifications
"""

import pytest
from pathlib import Path
from validators.manifest_validator import validate_with_ast, AlignmentError


def test_empty_parameter_list_vs_none(tmp_path: Path):
    """Test distinction between empty parameter list and unspecified."""
    code = """
def no_params():
    pass

def with_params(a, b, c):
    pass
"""
    test_file = tmp_path / "params.py"
    test_file.write_text(code)

    # Test with empty parameter list
    manifest1 = {
        "expectedArtifacts": {
            "contains": [
                {"type": "function", "name": "no_params", "parameters": []},
                {
                    "type": "function",
                    "name": "with_params",
                    "parameters": ["a", "b", "c"],
                },
            ]
        }
    }
    # Should pass - empty list means no parameters expected
    validate_with_ast(manifest1, str(test_file))

    # Test with unspecified parameters (None)
    manifest2 = {
        "expectedArtifacts": {
            "contains": [
                {"type": "function", "name": "no_params"},  # No parameters field
                {"type": "function", "name": "with_params"},  # No parameters field
            ]
        }
    }
    # Should pass - unspecified means don't validate parameters
    validate_with_ast(manifest2, str(test_file))


def test_function_with_args_kwargs(tmp_path: Path):
    """Test functions with *args and **kwargs."""
    code = """
def variadic_function(a, *args, **kwargs):
    pass

def only_kwargs(**options):
    pass

def only_args(*values):
    pass
"""
    test_file = tmp_path / "variadic.py"
    test_file.write_text(code)

    # The validator captures only regular parameters
    # *args and **kwargs are not included in parameter lists
    manifest = {
        "expectedArtifacts": {
            "contains": [
                {
                    "type": "function",
                    "name": "variadic_function",
                    "parameters": ["a"],
                },  # Only regular arg
                {
                    "type": "function",
                    "name": "only_kwargs",
                    "parameters": [],
                },  # No regular args
                {
                    "type": "function",
                    "name": "only_args",
                    "parameters": [],
                },  # No regular args
            ]
        }
    }
    # Should pass - only regular parameters are tracked
    validate_with_ast(manifest, str(test_file))

    # Verify *args and **kwargs are not included
    manifest_with_varargs = {
        "expectedArtifacts": {
            "contains": [
                {
                    "type": "function",
                    "name": "variadic_function",
                    "parameters": ["a", "args", "kwargs"],
                }
            ]
        }
    }
    # Should fail - *args and **kwargs not captured
    with pytest.raises(AlignmentError, match="Parameter 'args' not found"):
        validate_with_ast(manifest_with_varargs, str(test_file))


def test_decorated_functions(tmp_path: Path):
    """Test functions with decorators."""
    code = """
@decorator
def decorated_function():
    pass

@decorator1
@decorator2
def multi_decorated():
    pass

@property
def prop_function():
    pass
"""
    test_file = tmp_path / "decorated.py"
    test_file.write_text(code)

    manifest = {
        "expectedArtifacts": {
            "contains": [
                {"type": "function", "name": "decorated_function"},
                {"type": "function", "name": "multi_decorated"},
                {"type": "function", "name": "prop_function"},
            ]
        }
    }
    # Should pass - decorators don't affect function collection
    validate_with_ast(manifest, str(test_file))


def test_async_functions(tmp_path: Path):
    """Test async def functions."""
    code = """
async def async_function(data):
    return data

def sync_function(data):
    return data

async def async_no_params():
    pass
"""
    test_file = tmp_path / "async.py"
    test_file.write_text(code)

    # Async functions are not collected by the validator
    manifest = {
        "expectedArtifacts": {
            "contains": [
                # Only sync functions are collected
                {"type": "function", "name": "sync_function", "parameters": ["data"]}
            ]
        }
    }
    # Should pass - only sync functions are collected
    validate_with_ast(manifest, str(test_file))

    # Verify async functions are not tracked
    manifest_with_async = {
        "expectedArtifacts": {
            "contains": [
                {"type": "function", "name": "async_function", "parameters": ["data"]}
            ]
        }
    }
    # Should fail - async functions not supported
    with pytest.raises(AlignmentError, match="Artifact 'async_function' not found"):
        validate_with_ast(manifest_with_async, str(test_file))


def test_properties(tmp_path: Path):
    """Test @property decorated methods in classes."""
    code = """
class MyClass:
    @property
    def value(self):
        return self._value

    @value.setter
    def value(self, new_value):
        self._value = new_value

    @value.deleter
    def value(self):
        del self._value

def module_function():
    pass
"""
    test_file = tmp_path / "properties.py"
    test_file.write_text(code)

    manifest = {
        "expectedArtifacts": {
            "contains": [
                {"type": "class", "name": "MyClass"},
                {"type": "function", "name": "module_function"},
                # Property methods should not be module functions
            ]
        }
    }
    # Should pass - property methods are not module functions
    validate_with_ast(manifest, str(test_file))


def test_manifest_with_empty_artifacts_list(tmp_path: Path):
    """Test manifest with empty artifacts list."""
    code = """
def some_function():
    pass

class SomeClass:
    pass
"""
    test_file = tmp_path / "empty_manifest.py"
    test_file.write_text(code)

    manifest = {
        "expectedArtifacts": {"contains": []}  # Empty list - no artifacts expected
    }
    # Empty manifests don't trigger strict validation
    # Validation is only enforced when expected_items is non-empty
    validate_with_ast(manifest, str(test_file))


def test_artifact_with_minimal_fields(tmp_path: Path):
    """Test artifacts with only required fields (type and name)."""
    code = """
class SimpleClass:
    pass

def simple_function(a, b, c):
    pass
"""
    test_file = tmp_path / "minimal.py"
    test_file.write_text(code)

    manifest = {
        "expectedArtifacts": {
            "contains": [
                {"type": "class", "name": "SimpleClass"},  # Minimal class
                {"type": "function", "name": "simple_function"},  # Minimal function
            ]
        }
    }
    # Should pass - minimal fields are sufficient
    validate_with_ast(manifest, str(test_file))


def test_artifact_with_all_optional_fields(tmp_path: Path):
    """Test artifacts with all possible fields populated."""
    code = """
class DerivedClass(BaseClass):
    pass

def complex_function(param1, param2):
    pass

class Container:
    pass

def use_container():
    c = Container()
    c.attribute = "value"
"""
    test_file = tmp_path / "full_fields.py"
    test_file.write_text(code)

    manifest = {
        "expectedArtifacts": {
            "contains": [
                {
                    "type": "class",
                    "name": "DerivedClass",
                    "bases": ["BaseClass"],  # Optional bases field
                },
                {
                    "type": "function",
                    "name": "complex_function",
                    "parameters": ["param1", "param2"],  # Optional parameters field
                },
                {"type": "class", "name": "Container"},
                {"type": "function", "name": "use_container"},
                {
                    "type": "attribute",
                    "name": "attribute",
                    "class": "Container",  # Required class field for attributes
                },
            ]
        }
    }
    # Should pass - all optional fields work correctly
    validate_with_ast(manifest, str(test_file))
