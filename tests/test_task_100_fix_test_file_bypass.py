"""Behavioral tests for task-100: Fix Test File Bypass Loophole.

These tests verify that _check_unexpected_artifacts uses path-based detection
instead of function-name-based detection to determine if a file is a test file.

The loophole: Previously, if ANY function in a file started with 'test_',
strict validation would be skipped. This allowed production code to hide
undeclared artifacts by having a test_helper() function in the file.

The fix: Use path-based detection - a file is a test file if:
  1. It's in a 'tests/' directory, OR
  2. Its filename starts with 'test_'
"""

import pytest

from maid_runner.validators._artifact_validation import _check_unexpected_artifacts
from maid_runner.validators.manifest_validator import (
    _ArtifactCollector,
    _VALIDATION_MODE_IMPLEMENTATION,
    AlignmentError,
)


class TestLoopholeClosure:
    """Tests verifying the bypass loophole is closed."""

    def test_catches_undeclared_in_non_test_file_with_test_prefix_function(
        self, tmp_path
    ):
        """Production file with test_ prefixed function should NOT bypass validation.

        This is the core loophole test. A file like src/utils.py with:
          - test_helper() function (which previously caused bypass)
          - public_api() function (undeclared)

        Should raise AlignmentError for undeclared public_api.
        """
        # Create a production file with test_helper and public_api functions
        prod_file = tmp_path / "src" / "utils.py"
        prod_file.parent.mkdir(parents=True)
        prod_file.write_text("""
def test_helper():
    '''A helper with test_ prefix that should NOT cause bypass.'''
    pass

def public_api():
    '''Undeclared public function that should be caught.'''
    pass
""")

        # Collect artifacts from the file
        collector = _ArtifactCollector(validation_mode=_VALIDATION_MODE_IMPLEMENTATION)
        import ast
        with open(prod_file, "r") as f:
            tree = ast.parse(f.read())
        collector.visit(tree)

        # Expected artifacts only declare test_helper, not public_api
        expected_items = [{"type": "function", "name": "test_helper"}]

        # Call the function with file path - should raise for undeclared public_api
        with pytest.raises(AlignmentError) as exc_info:
            _check_unexpected_artifacts(
                expected_items, collector, str(prod_file)
            )

        # Verify the error mentions the undeclared function
        assert "public_api" in str(exc_info.value)
        assert "Unexpected public function" in str(exc_info.value)

    def test_catches_undeclared_class_in_non_test_file(self, tmp_path):
        """Production file with undeclared class should raise error."""
        # Create production file with undeclared class
        prod_file = tmp_path / "src" / "models.py"
        prod_file.parent.mkdir(parents=True)
        prod_file.write_text("""
def test_data_factory():
    '''Has test_ prefix but file is NOT a test file.'''
    pass

class UndeclaredModel:
    '''This class is not declared in expected_items.'''
    pass
""")

        # Collect artifacts
        collector = _ArtifactCollector(validation_mode=_VALIDATION_MODE_IMPLEMENTATION)
        import ast
        with open(prod_file, "r") as f:
            tree = ast.parse(f.read())
        collector.visit(tree)

        # Only declare the function, not the class
        expected_items = [{"type": "function", "name": "test_data_factory"}]

        # Should raise for undeclared class
        with pytest.raises(AlignmentError) as exc_info:
            _check_unexpected_artifacts(
                expected_items, collector, str(prod_file)
            )

        assert "UndeclaredModel" in str(exc_info.value)
        assert "Unexpected public class" in str(exc_info.value)


class TestLegitimateTestFileSkipping:
    """Tests verifying legitimate test files ARE skipped."""

    def test_skips_validation_for_file_in_tests_directory(self, tmp_path):
        """File in tests/ directory should skip strict validation."""
        # Create a test file in tests/ directory
        test_file = tmp_path / "tests" / "test_example.py"
        test_file.parent.mkdir(parents=True)
        test_file.write_text("""
def test_something():
    pass

def helper_function():
    '''Not declared but should be allowed in test file.'''
    pass

class TestClass:
    '''Not declared but should be allowed in test file.'''
    pass
""")

        # Collect artifacts
        collector = _ArtifactCollector(validation_mode=_VALIDATION_MODE_IMPLEMENTATION)
        import ast
        with open(test_file, "r") as f:
            tree = ast.parse(f.read())
        collector.visit(tree)

        # Only declare test_something - undeclared helper_function and TestClass
        expected_items = [{"type": "function", "name": "test_something"}]

        # Use a path that looks like tests/test_example.py
        test_path = "tests/test_example.py"

        # Should NOT raise - test file validation is skipped
        _check_unexpected_artifacts(
            expected_items, collector, test_path
        )
        # If we get here without exception, the test passes

    def test_skips_validation_for_test_prefixed_filename(self, tmp_path):
        """File with test_ prefix in filename should skip strict validation."""
        # Create a test file with test_ prefix (not in tests/ dir)
        test_file = tmp_path / "test_integration.py"
        test_file.write_text("""
def test_api():
    pass

def undeclared_helper():
    '''Not declared but should be allowed.'''
    pass
""")

        # Collect artifacts
        collector = _ArtifactCollector(validation_mode=_VALIDATION_MODE_IMPLEMENTATION)
        import ast
        with open(test_file, "r") as f:
            tree = ast.parse(f.read())
        collector.visit(tree)

        # Only declare test_api
        expected_items = [{"type": "function", "name": "test_api"}]

        # Use path with test_ prefix in filename
        test_path = "test_integration.py"

        # Should NOT raise - test file validation is skipped
        _check_unexpected_artifacts(
            expected_items, collector, test_path
        )

    def test_skips_validation_for_nested_tests_directory(self, tmp_path):
        """File in nested tests/ directory should skip validation."""
        # Create file in nested tests directory
        test_file = tmp_path / "tests" / "unit" / "test_module.py"
        test_file.parent.mkdir(parents=True)
        test_file.write_text("""
def test_unit():
    pass

def fixture_helper():
    pass
""")

        # Collect artifacts
        collector = _ArtifactCollector(validation_mode=_VALIDATION_MODE_IMPLEMENTATION)
        import ast
        with open(test_file, "r") as f:
            tree = ast.parse(f.read())
        collector.visit(tree)

        expected_items = [{"type": "function", "name": "test_unit"}]

        # Path starts with tests/
        test_path = "tests/unit/test_module.py"

        # Should NOT raise
        _check_unexpected_artifacts(
            expected_items, collector, test_path
        )


class TestEdgeCases:
    """Tests for edge cases in path-based detection."""

    def test_testing_utils_file_is_not_test_file(self, tmp_path):
        """File named testing_utils.py is NOT a test file (no test_ prefix)."""
        # Create a utility file that contains 'test' but doesn't start with 'test_'
        util_file = tmp_path / "src" / "testing_utils.py"
        util_file.parent.mkdir(parents=True)
        util_file.write_text("""
def create_test_data():
    '''Function to create test data.'''
    pass

def undeclared_function():
    pass
""")

        # Collect artifacts
        collector = _ArtifactCollector(validation_mode=_VALIDATION_MODE_IMPLEMENTATION)
        import ast
        with open(util_file, "r") as f:
            tree = ast.parse(f.read())
        collector.visit(tree)

        expected_items = [{"type": "function", "name": "create_test_data"}]

        # Path does NOT start with test_ in filename
        file_path = "src/testing_utils.py"

        # Should raise - this is NOT a test file
        with pytest.raises(AlignmentError) as exc_info:
            _check_unexpected_artifacts(
                expected_items, collector, file_path
            )

        assert "undeclared_function" in str(exc_info.value)

    def test_my_test_file_is_not_test_file(self, tmp_path):
        """File named my_test.py is NOT a test file (improper naming)."""
        # Create file with improper test naming
        file = tmp_path / "src" / "my_test.py"
        file.parent.mkdir(parents=True)
        file.write_text("""
def run_tests():
    pass

def undeclared():
    pass
""")

        # Collect artifacts
        collector = _ArtifactCollector(validation_mode=_VALIDATION_MODE_IMPLEMENTATION)
        import ast
        with open(file, "r") as f:
            tree = ast.parse(f.read())
        collector.visit(tree)

        expected_items = [{"type": "function", "name": "run_tests"}]

        # Filename is my_test.py, not test_my.py
        file_path = "src/my_test.py"

        # Should raise - this is NOT a test file
        with pytest.raises(AlignmentError) as exc_info:
            _check_unexpected_artifacts(
                expected_items, collector, file_path
            )

        assert "undeclared" in str(exc_info.value)

    def test_tests_directory_non_test_filename(self, tmp_path):
        """File in tests/ dir but NOT named test_*.py should still be skipped.

        Directory takes precedence - if in tests/ directory, skip validation.
        This covers conftest.py, fixtures.py, etc.
        """
        # Create a helper file in tests/ directory
        helper_file = tmp_path / "tests" / "conftest.py"
        helper_file.parent.mkdir(parents=True)
        helper_file.write_text("""
import pytest

@pytest.fixture
def sample_fixture():
    pass

def helper():
    pass
""")

        # Collect artifacts
        collector = _ArtifactCollector(validation_mode=_VALIDATION_MODE_IMPLEMENTATION)
        import ast
        with open(helper_file, "r") as f:
            tree = ast.parse(f.read())
        collector.visit(tree)

        expected_items = [{"type": "function", "name": "sample_fixture"}]

        # In tests/ directory
        file_path = "tests/conftest.py"

        # Should NOT raise - file is in tests/ directory
        _check_unexpected_artifacts(
            expected_items, collector, file_path
        )

    def test_private_functions_not_caught(self, tmp_path):
        """Private functions (starting with _) should not be flagged."""
        prod_file = tmp_path / "src" / "module.py"
        prod_file.parent.mkdir(parents=True)
        prod_file.write_text("""
def public_api():
    pass

def _private_helper():
    '''Private function should not trigger error.'''
    pass
""")

        # Collect artifacts
        collector = _ArtifactCollector(validation_mode=_VALIDATION_MODE_IMPLEMENTATION)
        import ast
        with open(prod_file, "r") as f:
            tree = ast.parse(f.read())
        collector.visit(tree)

        # Declare public_api, don't declare _private_helper
        expected_items = [{"type": "function", "name": "public_api"}]

        file_path = "src/module.py"

        # Should NOT raise - _private_helper is private
        _check_unexpected_artifacts(
            expected_items, collector, file_path
        )


class TestNonTestFileWithNoTestFunctions:
    """Tests verifying normal non-test files work correctly."""

    def test_normal_file_catches_undeclared_artifacts(self, tmp_path):
        """Normal production file should catch undeclared artifacts."""
        prod_file = tmp_path / "src" / "service.py"
        prod_file.parent.mkdir(parents=True)
        prod_file.write_text("""
def get_user():
    pass

def delete_user():
    pass
""")

        # Collect artifacts
        collector = _ArtifactCollector(validation_mode=_VALIDATION_MODE_IMPLEMENTATION)
        import ast
        with open(prod_file, "r") as f:
            tree = ast.parse(f.read())
        collector.visit(tree)

        # Only declare get_user
        expected_items = [{"type": "function", "name": "get_user"}]

        file_path = "src/service.py"

        # Should raise for undeclared delete_user
        with pytest.raises(AlignmentError) as exc_info:
            _check_unexpected_artifacts(
                expected_items, collector, file_path
            )

        assert "delete_user" in str(exc_info.value)

    def test_all_declared_artifacts_pass(self, tmp_path):
        """When all artifacts are declared, no error should be raised."""
        prod_file = tmp_path / "src" / "complete.py"
        prod_file.parent.mkdir(parents=True)
        prod_file.write_text("""
def func_a():
    pass

def func_b():
    pass

class MyClass:
    def method(self):
        pass
""")

        # Collect artifacts
        collector = _ArtifactCollector(validation_mode=_VALIDATION_MODE_IMPLEMENTATION)
        import ast
        with open(prod_file, "r") as f:
            tree = ast.parse(f.read())
        collector.visit(tree)

        # Declare all public artifacts
        expected_items = [
            {"type": "function", "name": "func_a"},
            {"type": "function", "name": "func_b"},
            {"type": "class", "name": "MyClass"},
            {"type": "function", "name": "method", "class": "MyClass"},
        ]

        file_path = "src/complete.py"

        # Should NOT raise - all artifacts declared
        _check_unexpected_artifacts(
            expected_items, collector, file_path
        )


class TestPathNormalization:
    """Tests for different path formats."""

    def test_handles_forward_slashes(self, tmp_path):
        """Paths with forward slashes should work correctly."""
        prod_file = tmp_path / "deep" / "nested" / "module.py"
        prod_file.parent.mkdir(parents=True)
        prod_file.write_text("""
def declared_func():
    pass

def test_like_name():
    '''Has test_ prefix but file path is NOT a test path.'''
    pass

def undeclared():
    pass
""")

        collector = _ArtifactCollector(validation_mode=_VALIDATION_MODE_IMPLEMENTATION)
        import ast
        with open(prod_file, "r") as f:
            tree = ast.parse(f.read())
        collector.visit(tree)

        expected_items = [
            {"type": "function", "name": "declared_func"},
            {"type": "function", "name": "test_like_name"},
        ]

        # Forward slash path
        file_path = "deep/nested/module.py"

        with pytest.raises(AlignmentError) as exc_info:
            _check_unexpected_artifacts(
                expected_items, collector, file_path
            )

        assert "undeclared" in str(exc_info.value)

    def test_handles_tests_path_with_subdirectory(self, tmp_path):
        """tests/ path with subdirectories should be recognized."""
        test_file = tmp_path / "tests" / "integration" / "api" / "test_endpoints.py"
        test_file.parent.mkdir(parents=True)
        test_file.write_text("""
def test_get_endpoint():
    pass

def undeclared_helper():
    pass
""")

        collector = _ArtifactCollector(validation_mode=_VALIDATION_MODE_IMPLEMENTATION)
        import ast
        with open(test_file, "r") as f:
            tree = ast.parse(f.read())
        collector.visit(tree)

        expected_items = [{"type": "function", "name": "test_get_endpoint"}]

        # Deeply nested in tests/
        file_path = "tests/integration/api/test_endpoints.py"

        # Should NOT raise - in tests/ directory
        _check_unexpected_artifacts(
            expected_items, collector, file_path
        )


class TestEmptyExpectedItems:
    """Tests for behavior when expected_items is empty."""

    def test_empty_expected_items_skips_validation(self, tmp_path):
        """When expected_items is empty, no validation occurs."""
        prod_file = tmp_path / "src" / "empty_manifest.py"
        prod_file.parent.mkdir(parents=True)
        prod_file.write_text("""
def some_function():
    pass
""")

        collector = _ArtifactCollector(validation_mode=_VALIDATION_MODE_IMPLEMENTATION)
        import ast
        with open(prod_file, "r") as f:
            tree = ast.parse(f.read())
        collector.visit(tree)

        # Empty expected_items
        expected_items = []

        file_path = "src/empty_manifest.py"

        # Should NOT raise - empty expected_items skips strict validation
        _check_unexpected_artifacts(
            expected_items, collector, file_path
        )
