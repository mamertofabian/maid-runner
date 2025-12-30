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


def test_file_with_test_prefix_but_no_test_functions(tmp_path: Path):
    """Test edge case: filename starts with test_ so it IS a test file.

    Files with test_ prefix in filename are test files regardless of function content.
    This is path-based detection (secure) vs function-name-based detection (vulnerable).
    Test helper files like test_helpers.py should skip strict validation.
    """
    code = """
def setup():
    pass

def teardown():
    pass

def helper_function():
    # File named test_*.py - considered test file by path
    pass
"""
    test_file = tmp_path / "test_helpers.py"
    test_file.write_text(code)

    manifest = {
        "expectedArtifacts": {
            "contains": [
                {"type": "function", "name": "setup"},
                {"type": "function", "name": "teardown"},
                # helper_function not listed - but that's OK for test files
            ]
        }
    }
    # Should pass - test_helpers.py IS a test file (filename starts with test_)
    # Strict validation is skipped for test files (path-based detection)
    validate_with_ast(manifest, str(test_file))


def test_production_file_with_test_prefixed_function_still_validated(tmp_path: Path):
    """Security test: production code can't bypass validation with test_ functions.

    This verifies the fix for the test file bypass loophole. Previously, a file like
    utils.py could bypass strict validation by including a function named test_helper().
    With path-based detection, only files in tests/ or named test_*.py skip validation.
    """
    code = """
def test_helper():
    # This function has test_ prefix but file is NOT a test file
    pass

def public_api():
    # This is an undeclared public function
    pass
"""
    # Production file (NOT in tests/, NOT named test_*)
    prod_file = tmp_path / "utils.py"
    prod_file.write_text(code)

    manifest = {
        "expectedArtifacts": {
            "contains": [
                {"type": "function", "name": "test_helper"},
                # public_api not listed - should be caught
            ]
        }
    }
    # Should FAIL - utils.py is NOT a test file, strict validation applies
    # The test_helper function name does NOT bypass validation (security fix)
    with pytest.raises(AlignmentError, match="Unexpected public function"):
        validate_with_ast(manifest, str(prod_file))


# Direct unit tests for _is_test_file_path() function
class TestIsTestFilePath:
    """Unit tests for the _is_test_file_path() helper function.

    These tests verify path-based test file detection handles various edge cases
    including absolute paths, Windows paths, and relative paths.
    """

    @pytest.fixture
    def is_test_file_path(self):
        """Import the function under test."""
        from maid_runner.validators._artifact_validation import _is_test_file_path

        return _is_test_file_path

    def test_empty_string_returns_false(self, is_test_file_path):
        """Empty string should return False."""
        assert is_test_file_path("") is False

    def test_none_like_empty_returns_false(self, is_test_file_path):
        """None-like empty values should return False."""
        assert is_test_file_path("") is False

    def test_relative_tests_directory(self, is_test_file_path):
        """Relative path in tests/ directory should return True."""
        assert is_test_file_path("tests/test_example.py") is True
        assert is_test_file_path("tests/subdir/test_example.py") is True

    def test_relative_with_dot_slash(self, is_test_file_path):
        """Paths starting with ./ should be handled correctly."""
        assert is_test_file_path("./tests/test_example.py") is True
        assert is_test_file_path("./tests/subdir/test_file.py") is True

    def test_absolute_unix_path(self, is_test_file_path):
        """Absolute Unix paths with tests/ directory should return True."""
        assert is_test_file_path("/home/user/project/tests/test_example.py") is True
        assert is_test_file_path("/var/project/tests/subdir/test_file.py") is True

    def test_absolute_windows_path(self, is_test_file_path):
        """Windows absolute paths should be normalized and handled."""
        assert is_test_file_path("C:\\project\\tests\\test_example.py") is True
        assert is_test_file_path("D:\\code\\tests\\subdir\\test_file.py") is True

    def test_mixed_path_separators(self, is_test_file_path):
        """Mixed path separators should be normalized."""
        assert is_test_file_path("tests\\subdir/test_example.py") is True
        assert is_test_file_path("C:/project\\tests/test_file.py") is True

    def test_test_prefixed_filename_not_in_tests_dir(self, is_test_file_path):
        """Files named test_*.py outside tests/ should return True."""
        assert is_test_file_path("src/test_utils.py") is True
        assert is_test_file_path("test_standalone.py") is True
        assert is_test_file_path("/home/user/test_file.py") is True

    def test_non_test_file_in_tests_dir(self, is_test_file_path):
        """Non-test files in tests/ directory should still return True (directory takes precedence)."""
        assert is_test_file_path("tests/conftest.py") is True
        assert is_test_file_path("tests/helpers.py") is True
        assert is_test_file_path("tests/__init__.py") is True

    def test_production_file_not_test(self, is_test_file_path):
        """Production files should return False."""
        assert is_test_file_path("src/utils.py") is False
        assert (
            is_test_file_path("maid_runner/validators/manifest_validator.py") is False
        )
        assert is_test_file_path("/home/user/project/src/service.py") is False

    def test_file_named_test_without_underscore(self, is_test_file_path):
        """File named exactly 'test.py' (without underscore) should return False."""
        assert is_test_file_path("test.py") is False
        assert is_test_file_path("src/test.py") is False

    def test_testing_in_name_not_test_file(self, is_test_file_path):
        """Files with 'testing' in name but not test_ prefix should return False."""
        assert is_test_file_path("testing_utils.py") is False
        assert is_test_file_path("src/testing_helpers.py") is False

    def test_my_test_not_test_file(self, is_test_file_path):
        """Files ending in test but not starting with test_ should return False."""
        assert is_test_file_path("my_test.py") is False
        assert is_test_file_path("src/unit_test.py") is False

    def test_tests_in_path_but_not_directory(self, is_test_file_path):
        """Path containing 'tests' as part of filename should not match."""
        assert is_test_file_path("my_tests_utils.py") is False
        assert is_test_file_path("src/tests_helper.py") is False
