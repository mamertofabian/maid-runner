# tests/test_ast_validator_strict.py

import sys
from pathlib import Path

# Add parent directory to path to enable imports
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

# Import private test modules for task-076 private artifacts
from tests._test_task_076_private_helpers import (  # noqa: F401
    TestValidateSingleArtifact,
)
import pytest
from maid_runner.validators.manifest_validator import validate_with_ast, AlignmentError


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
                {"type": "class", "name": "ValidationError", "bases": ["Exception"]},
                {
                    "type": "function",
                    "name": "validate_data",
                    "parameters": [{"name": "data"}, {"name": "schema"}],
                },
                {
                    "type": "function",
                    "name": "process_items",
                    "parameters": [{"name": "items"}],
                },
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


# ============================================================================
# Test File Validation Exclusion Tests
# ============================================================================


def test_strict_validation_skipped_for_test_files(tmp_path: Path):
    """Test that files with test_ functions skip strict validation."""
    code = """
def expected_function():
    pass

def unexpected_function():
    pass

def test_something():
    # Presence of test function should disable strict validation
    pass

class UnexpectedClass:
    pass
"""
    test_file = tmp_path / "test_module.py"
    test_file.write_text(code)

    manifest = {
        "expectedArtifacts": {
            "contains": [
                {"type": "function", "name": "expected_function"}
                # unexpected_function and UnexpectedClass not listed
                # But should pass because test_ function present
            ]
        }
    }
    # Should pass - strict validation skipped for test files
    validate_with_ast(manifest, str(test_file))


def test_strict_validation_applied_to_non_test_files(tmp_path: Path):
    """Test that regular files get strict validation."""
    code = """
def expected_function():
    pass

def unexpected_function():
    # No test_ functions, so strict validation should apply
    pass
"""
    test_file = tmp_path / "regular.py"
    test_file.write_text(code)

    manifest = {
        "expectedArtifacts": {
            "contains": [
                {"type": "function", "name": "expected_function"}
                # unexpected_function not listed - should fail
            ]
        }
    }
    # Should fail - strict validation applies to non-test files
    with pytest.raises(AlignmentError, match="Unexpected public function"):
        validate_with_ast(manifest, str(test_file))


def test_file_with_test_prefix_skips_strict_validation(tmp_path: Path):
    """Test that file with test_ prefix in name skips strict validation (path-based detection)."""
    code = """
def setup():
    pass

def teardown():
    pass

def helper_function():
    # File named test_*.py should skip strict validation
    pass
"""
    test_file = tmp_path / "test_helpers.py"
    test_file.write_text(code)

    manifest = {
        "expectedArtifacts": {
            "contains": [
                {"type": "function", "name": "setup"},
                {"type": "function", "name": "teardown"},
                # helper_function not listed but OK since test file
            ]
        }
    }
    # Should pass - file with test_ prefix is a test file, skips strict validation
    validate_with_ast(manifest, str(test_file))
