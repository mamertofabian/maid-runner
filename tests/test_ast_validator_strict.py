# tests/test_ast_validator_strict.py
import pytest
from pathlib import Path
from validators.manifest_validator import validate_with_ast, AlignmentError


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
        "expectedArtifacts": {
            "contains": [
                {"type": "function", "name": "expected_function"}
                # unexpected_public_function is NOT listed, should fail
            ]
        }
    }
    with pytest.raises(
        AlignmentError,
        match="Unexpected public function\\(s\\) found: unexpected_public_function",
    ):
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
        "expectedArtifacts": {
            "contains": [
                {"type": "class", "name": "ExpectedClass"}
                # UnexpectedPublicClass is NOT listed, should fail
            ]
        }
    }
    with pytest.raises(
        AlignmentError,
        match="Unexpected public class\\(es\\) found: UnexpectedPublicClass",
    ):
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
        "expectedArtifacts": {
            "contains": [
                {"type": "class", "name": "PublicClass"},
                {"type": "function", "name": "public_function"},
                # Private artifacts (_PrivateClass, _private_helper, etc.) not listed
            ]
        }
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
        "expectedArtifacts": {
            "contains": [
                {"type": "class", "name": "ValidationError", "base": "Exception"},
                {
                    "type": "function",
                    "name": "validate_data",
                    "parameters": ["data", "schema"],
                },
                {"type": "function", "name": "process_items", "parameters": ["items"]},
            ]
        }
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
        "expectedArtifacts": {
            "contains": [
                {"type": "class", "name": "Expected"},
                {"type": "function", "name": "expected_func"},
            ]
        }
    }
    # Should report all unexpected artifacts
    with pytest.raises(AlignmentError) as exc_info:
        validate_with_ast(manifest, str(test_file))

    error_msg = str(exc_info.value)
    # Check that it mentions unexpected classes or functions
    assert "Extra1" in error_msg or "extra_func1" in error_msg


