# tests/test_ast_validator.py
import pytest
from pathlib import Path
from validators.manifest_validator import validate_with_ast, AlignmentError

# We'll use a more complex dummy file now
DUMMY_TEST_CODE = """
import pytest
from my_app.models import User, Product

def test_user_creation():
    # Using a standard variable name
    user = User(name="Alice", user_id=123)
    assert user.name == "Alice"

def test_admin_user_creation():
    # Using a different variable name for the SAME class
    admin_user = User(name="Bob", user_id=456)
    assert admin_user.user_id == 456

def test_product_creation():
    # Using a completely different class
    item = Product(sku="abc", price=99.99)
    assert item.sku == "abc"
"""

def test_ast_validation_passes_when_aligned(tmp_path: Path):
    """Tests that a correctly aligned manifest passes."""
    test_file = tmp_path / "test_complex.py"
    test_file.write_text(DUMMY_TEST_CODE)

    aligned_manifest = {
        "expectedArtifacts": { "contains": [
            {"type": "class", "name": "User"},
            {"type": "class", "name": "Product"},
            {"type": "attribute", "name": "name", "class": "User"},
            {"type": "attribute", "name": "user_id", "class": "User"},
            {"type": "attribute", "name": "sku", "class": "Product"}
        ]}
    }
    # Should not raise an error
    validate_with_ast(aligned_manifest, str(test_file))

def test_ast_validation_fails_on_missing_attribute(tmp_path: Path):
    """Tests that a misaligned manifest (missing attribute) fails."""
    test_file = tmp_path / "test_complex.py"
    test_file.write_text(DUMMY_TEST_CODE)

    misaligned_manifest = {
        "expectedArtifacts": { "contains": [
            {"type": "class", "name": "User"},
            # The 'email' attribute is NOT in the test code
            {"type": "attribute", "name": "email", "class": "User"}
        ]}
    }
    with pytest.raises(AlignmentError, match="Artifact 'email' not found"):
        validate_with_ast(misaligned_manifest, str(test_file))

def test_ast_validation_fails_on_missing_class(tmp_path: Path):
    """Tests that a misaligned manifest (missing class) fails."""
    test_file = tmp_path / "test_complex.py"
    test_file.write_text(DUMMY_TEST_CODE)

    misaligned_manifest = {
        "expectedArtifacts": { "contains": [
            # The 'Order' class is NOT in the test code
            {"type": "class", "name": "Order"}
        ]}
    }
    with pytest.raises(AlignmentError, match="Artifact 'Order' not found"):
        validate_with_ast(misaligned_manifest, str(test_file))


# Test cases for function parameter validation
def test_function_parameters_validation_passes(tmp_path: Path):
    """Tests that function parameter validation passes when parameters match."""
    code_with_functions = """
def process_data(input_data, options, verbose=False):
    return input_data

def calculate_total(items, tax_rate):
    return sum(items) * (1 + tax_rate)

class Calculator:
    def add(self, a, b):
        return a + b
"""
    test_file = tmp_path / "functions.py"
    test_file.write_text(code_with_functions)

    manifest = {
        "expectedArtifacts": { "contains": [
            {"type": "function", "name": "process_data", "parameters": ["input_data", "options", "verbose"]},
            {"type": "function", "name": "calculate_total", "parameters": ["items", "tax_rate"]},
            {"type": "class", "name": "Calculator"}  # Include the class in manifest
        ]}
    }
    # Should not raise an error
    validate_with_ast(manifest, str(test_file))


def test_function_parameters_validation_fails(tmp_path: Path):
    """Tests that function parameter validation fails when parameters don't match."""
    code_with_functions = """
def process_data(input_data, options):
    return input_data
"""
    test_file = tmp_path / "functions.py"
    test_file.write_text(code_with_functions)

    manifest = {
        "expectedArtifacts": { "contains": [
            # Function exists but 'verbose' parameter is missing
            {"type": "function", "name": "process_data", "parameters": ["input_data", "options", "verbose"]}
        ]}
    }
    with pytest.raises(AlignmentError, match="Parameter 'verbose' not found in function 'process_data'"):
        validate_with_ast(manifest, str(test_file))


def test_function_without_parameters_specified(tmp_path: Path):
    """Tests that function validation works when parameters are not specified in manifest."""
    code_with_functions = """
def process_data(input_data, options, verbose=False):
    return input_data
"""
    test_file = tmp_path / "functions.py"
    test_file.write_text(code_with_functions)

    manifest = {
        "expectedArtifacts": { "contains": [
            # No parameters specified - should only check function existence
            {"type": "function", "name": "process_data"}
        ]}
    }
    # Should not raise an error
    validate_with_ast(manifest, str(test_file))


# Test cases for base class validation
def test_base_class_validation_passes(tmp_path: Path):
    """Tests that base class validation passes when inheritance matches."""
    code_with_classes = """
class CustomError(Exception):
    pass

class ValidationError(ValueError):
    def __init__(self, message):
        self.message = message

class Animal:
    pass

class Dog(Animal):
    def bark(self):
        return "Woof!"
"""
    test_file = tmp_path / "classes.py"
    test_file.write_text(code_with_classes)

    manifest = {
        "expectedArtifacts": { "contains": [
            {"type": "class", "name": "CustomError", "base": "Exception"},
            {"type": "class", "name": "ValidationError", "base": "ValueError"},
            {"type": "class", "name": "Dog", "base": "Animal"},
            {"type": "class", "name": "Animal"}  # No base specified
        ]}
    }
    # Should not raise an error
    validate_with_ast(manifest, str(test_file))


def test_base_class_validation_fails(tmp_path: Path):
    """Tests that base class validation fails when inheritance doesn't match."""
    code_with_classes = """
class CustomError(ValueError):  # Inherits from ValueError, not Exception
    pass
"""
    test_file = tmp_path / "classes.py"
    test_file.write_text(code_with_classes)

    manifest = {
        "expectedArtifacts": { "contains": [
            # Expects Exception but actual base is ValueError
            {"type": "class", "name": "CustomError", "base": "Exception"}
        ]}
    }
    with pytest.raises(AlignmentError, match="Class 'CustomError' does not inherit from 'Exception'"):
        validate_with_ast(manifest, str(test_file))


def test_class_without_base_specified(tmp_path: Path):
    """Tests that class validation works when base class is not specified in manifest."""
    code_with_classes = """
class CustomError(Exception):
    pass
"""
    test_file = tmp_path / "classes.py"
    test_file.write_text(code_with_classes)

    manifest = {
        "expectedArtifacts": { "contains": [
            # No base class specified - should only check class existence
            {"type": "class", "name": "CustomError"}
        ]}
    }
    # Should not raise an error
    validate_with_ast(manifest, str(test_file))


def test_strict_parameter_validation_catches_extra_params(tmp_path: Path):
    """Tests that strict parameter validation catches unexpected parameters."""
    code_with_function = """
def process_data(input_data, options, verbose=False):
    return input_data
"""
    test_file = tmp_path / "functions.py"
    test_file.write_text(code_with_function)

    manifest = {
        "expectedArtifacts": { "contains": [
            # Only declaring two parameters, but function has three
            {"type": "function", "name": "process_data", "parameters": ["input_data", "options"]}
        ]}
    }

    # Should fail because 'verbose' parameter is not declared
    with pytest.raises(AlignmentError, match="Unexpected parameter\\(s\\) in function 'process_data': verbose"):
        validate_with_ast(manifest, str(test_file))


def test_strict_parameter_validation_exact_match(tmp_path: Path):
    """Tests that strict parameter validation passes with exact parameter match."""
    code_with_function = """
def process_data(input_data, options, verbose=False):
    return input_data
"""
    test_file = tmp_path / "functions.py"
    test_file.write_text(code_with_function)

    manifest = {
        "expectedArtifacts": { "contains": [
            # Declaring all three parameters
            {"type": "function", "name": "process_data", "parameters": ["input_data", "options", "verbose"]}
        ]}
    }

    # Should pass with all parameters declared
    validate_with_ast(manifest, str(test_file))


# Test cases for strict validation (no unexpected public artifacts)
def test_unexpected_public_function_fails(tmp_path: Path):
    """Tests that unexpected public functions cause validation to fail."""
    code = """
def expected_function():
    pass

def unexpected_public_function():
    pass

def _private_function():
    # This should be allowed even though not in manifest
    pass
"""
    test_file = tmp_path / "strict.py"
    test_file.write_text(code)

    manifest = {
        "expectedArtifacts": { "contains": [
            {"type": "function", "name": "expected_function"}
            # unexpected_public_function is NOT listed, should fail
        ]}
    }
    with pytest.raises(AlignmentError, match="Unexpected public function\\(s\\) found: unexpected_public_function"):
        validate_with_ast(manifest, str(test_file))


def test_unexpected_public_class_fails(tmp_path: Path):
    """Tests that unexpected public classes cause validation to fail."""
    code = """
class ExpectedClass:
    pass

class UnexpectedPublicClass:
    pass

class _PrivateClass:
    # This should be allowed even though not in manifest
    pass
"""
    test_file = tmp_path / "strict.py"
    test_file.write_text(code)

    manifest = {
        "expectedArtifacts": { "contains": [
            {"type": "class", "name": "ExpectedClass"}
            # UnexpectedPublicClass is NOT listed, should fail
        ]}
    }
    with pytest.raises(AlignmentError, match="Unexpected public class\\(es\\) found: UnexpectedPublicClass"):
        validate_with_ast(manifest, str(test_file))


def test_private_artifacts_allowed(tmp_path: Path):
    """Tests that private artifacts (starting with _) are allowed without being in manifest."""
    code = """
class PublicClass:
    pass

class _PrivateClass:
    pass

def public_function():
    pass

def _private_helper():
    pass

def _another_private_function():
    pass
"""
    test_file = tmp_path / "mixed.py"
    test_file.write_text(code)

    manifest = {
        "expectedArtifacts": { "contains": [
            {"type": "class", "name": "PublicClass"},
            {"type": "function", "name": "public_function"}
            # Private artifacts (_PrivateClass, _private_helper, etc.) not listed
        ]}
    }
    # Should not raise an error - private artifacts are allowed
    validate_with_ast(manifest, str(test_file))


def test_exact_match_public_artifacts(tmp_path: Path):
    """Tests that validation passes when public artifacts exactly match manifest."""
    code = """
class ValidationError(Exception):
    pass

def validate_data(data, schema):
    return True

def process_items(items):
    return items

# Private helpers are allowed
def _internal_helper():
    pass

class _InternalCache:
    pass
"""
    test_file = tmp_path / "exact.py"
    test_file.write_text(code)

    manifest = {
        "expectedArtifacts": { "contains": [
            {"type": "class", "name": "ValidationError", "base": "Exception"},
            {"type": "function", "name": "validate_data", "parameters": ["data", "schema"]},
            {"type": "function", "name": "process_items", "parameters": ["items"]}
        ]}
    }
    # Should pass - all public artifacts are declared, private ones are ignored
    validate_with_ast(manifest, str(test_file))


def test_multiple_unexpected_artifacts_reported(tmp_path: Path):
    """Tests that multiple unexpected artifacts are reported together."""
    code = """
class Expected:
    pass

class Extra1:
    pass

class Extra2:
    pass

def expected_func():
    pass

def extra_func1():
    pass

def extra_func2():
    pass
"""
    test_file = tmp_path / "multiple.py"
    test_file.write_text(code)

    manifest = {
        "expectedArtifacts": { "contains": [
            {"type": "class", "name": "Expected"},
            {"type": "function", "name": "expected_func"}
        ]}
    }
    # Should report all unexpected artifacts
    with pytest.raises(AlignmentError) as exc_info:
        validate_with_ast(manifest, str(test_file))

    error_msg = str(exc_info.value)
    # Check that it mentions unexpected classes or functions
    assert "Extra1" in error_msg or "extra_func1" in error_msg
