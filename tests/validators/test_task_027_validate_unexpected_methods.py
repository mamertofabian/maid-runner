# tests/validators/test_task_027_validate_unexpected_methods.py
import sys
from pathlib import Path

# Add parent directory to path to enable imports
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

import pytest
from maid_runner.validators.manifest_validator import validate_with_ast, AlignmentError

# Import private test modules for task-027 private artifacts
from tests._test_task_027_private_helpers import (  # noqa: F401
    TestCheckUnexpectedArtifacts,
    TestValidateNoUnexpectedArtifacts,
)


def test_unexpected_public_method_fails(tmp_path: Path):
    """Tests that unexpected public methods cause validation to fail."""
    code = """
class MyClass:
    def expected_method(self):
        pass

    def unexpected_public_method(self):
        # This method is NOT declared in manifest, should fail
        pass

    def _private_method(self):
        # Private methods should be allowed
        pass
"""
    test_file = tmp_path / "with_methods.py"
    test_file.write_text(code)

    manifest = {
        "expectedArtifacts": {
            "contains": [
                {"type": "class", "name": "MyClass"},
                {"type": "function", "name": "expected_method", "class": "MyClass"},
                # unexpected_public_method is NOT listed, should fail
            ]
        }
    }
    with pytest.raises(
        AlignmentError,
        match="Unexpected public method\\(s\\) in class 'MyClass': unexpected_public_method",
    ):
        validate_with_ast(manifest, str(test_file))


def test_private_methods_allowed(tmp_path: Path):
    """Tests that private methods (starting with _) are allowed without declaration."""
    code = """
class MyClass:
    def public_method(self):
        pass

    def _private_helper(self):
        # Should be allowed
        pass

    def __dunder_method__(self):
        # Should be allowed
        pass
"""
    test_file = tmp_path / "with_private.py"
    test_file.write_text(code)

    manifest = {
        "expectedArtifacts": {
            "contains": [
                {"type": "class", "name": "MyClass"},
                {"type": "function", "name": "public_method", "class": "MyClass"},
                # Private methods not listed but should pass
            ]
        }
    }
    # Should not raise an error - private methods are allowed
    validate_with_ast(manifest, str(test_file))


def test_declared_methods_pass(tmp_path: Path):
    """Tests that validation passes when all public methods are declared."""
    code = """
class Calculator:
    def add(self, a, b):
        return a + b

    def subtract(self, a, b):
        return a - b

    def _internal_helper(self):
        pass
"""
    test_file = tmp_path / "calculator.py"
    test_file.write_text(code)

    manifest = {
        "expectedArtifacts": {
            "contains": [
                {"type": "class", "name": "Calculator"},
                {
                    "type": "function",
                    "name": "add",
                    "class": "Calculator",
                    "parameters": [{"name": "a"}, {"name": "b"}],
                },
                {
                    "type": "function",
                    "name": "subtract",
                    "class": "Calculator",
                    "parameters": [{"name": "a"}, {"name": "b"}],
                },
            ]
        }
    }
    # Should pass - all public methods are declared
    validate_with_ast(manifest, str(test_file))


def test_multiple_unexpected_methods_reported(tmp_path: Path):
    """Tests that multiple unexpected methods are reported together."""
    code = """
class Service:
    def expected_method(self):
        pass

    def extra_method1(self):
        pass

    def extra_method2(self):
        pass
"""
    test_file = tmp_path / "service.py"
    test_file.write_text(code)

    manifest = {
        "expectedArtifacts": {
            "contains": [
                {"type": "class", "name": "Service"},
                {"type": "function", "name": "expected_method", "class": "Service"},
            ]
        }
    }
    # Should report all unexpected methods
    with pytest.raises(AlignmentError) as exc_info:
        validate_with_ast(manifest, str(test_file))

    error_msg = str(exc_info.value)
    # Check that it mentions unexpected methods
    assert "extra_method1" in error_msg and "extra_method2" in error_msg


def test_private_class_public_methods_allowed(tmp_path: Path):
    """Tests that public methods in private classes don't need declaration."""
    code = """
class _PrivateClass:
    def public_method(self):
        # Public method in private class - should be allowed
        pass

    def another_public_method(self):
        pass
"""
    test_file = tmp_path / "private_class.py"
    test_file.write_text(code)

    manifest = {
        "expectedArtifacts": {
            "contains": [
                # Private class not declared, and its methods not declared either
            ]
        }
    }
    # Should pass - private classes and their methods don't need declaration
    validate_with_ast(manifest, str(test_file))
