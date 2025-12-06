"""
Private test module for private helper functions declared in task-027 manifest.

These tests verify the actual behavior of private helper functions that are declared
in the manifest. While these are internal helpers, they're part of the declared API
and must be behaviorally validated.

Tests focus on meaningful behavior:
- How these helpers enable public APIs to work correctly
- Edge cases and error conditions
- Real-world usage scenarios

Related task: task-027-validate-unexpected-methods
"""

import pytest

# Import with fallback for Red phase testing
try:
    from maid_runner.validators.manifest_validator import (
        _check_unexpected_artifacts,
        _validate_no_unexpected_artifacts,
        _parse_file,
        _collect_artifacts_from_ast,
    )
    from maid_runner.validators.manifest_validator import AlignmentError
except ImportError as e:
    # In Red phase, these functions won't exist yet
    pytest.skip(f"Implementation not ready: {e}", allow_module_level=True)


class TestCheckUnexpectedArtifacts:
    """Test _check_unexpected_artifacts private function behavior."""

    def test_check_unexpected_artifacts_called_with_expected_items(self, tmp_path):
        """Test that _check_unexpected_artifacts is called with expected_items and collector."""
        test_file = tmp_path / "test.py"
        test_file.write_text(
            """
class Service:
    def expected_method(self):
        pass
    def unexpected_method(self):
        pass
"""
        )

        tree = _parse_file(str(test_file))
        collector = _collect_artifacts_from_ast(tree, "implementation")

        expected_items = [
            {"type": "class", "name": "Service"},
            {"type": "function", "name": "expected_method", "class": "Service"},
        ]

        # Call _check_unexpected_artifacts directly - should raise error
        with pytest.raises(AlignmentError, match="unexpected_method"):
            _check_unexpected_artifacts(expected_items, collector)

    def test_check_unexpected_artifacts_passes_when_all_declared(self, tmp_path):
        """Test that _check_unexpected_artifacts passes when all artifacts are declared."""
        test_file = tmp_path / "test.py"
        test_file.write_text(
            """
class Service:
    def expected_method(self):
        pass
"""
        )

        tree = _parse_file(str(test_file))
        collector = _collect_artifacts_from_ast(tree, "implementation")

        expected_items = [
            {"type": "class", "name": "Service"},
            {"type": "function", "name": "expected_method", "class": "Service"},
        ]

        # Call _check_unexpected_artifacts directly - should not raise error
        _check_unexpected_artifacts(expected_items, collector)

    def test_check_unexpected_artifacts_allows_private_methods(self, tmp_path):
        """Test that _check_unexpected_artifacts allows private methods."""
        test_file = tmp_path / "test.py"
        test_file.write_text(
            """
class Service:
    def public_method(self):
        pass
    def _private_method(self):
        pass
"""
        )

        tree = _parse_file(str(test_file))
        collector = _collect_artifacts_from_ast(tree, "implementation")

        expected_items = [
            {"type": "class", "name": "Service"},
            {"type": "function", "name": "public_method", "class": "Service"},
        ]

        # Call _check_unexpected_artifacts directly - should not raise error for private methods
        _check_unexpected_artifacts(expected_items, collector)


class TestValidateNoUnexpectedArtifacts:
    """Test _validate_no_unexpected_artifacts private function behavior."""

    def test_validate_no_unexpected_artifacts_called_with_artifacts(self, tmp_path):
        """Test that _validate_no_unexpected_artifacts is called with artifacts."""
        test_file = tmp_path / "test.py"
        test_file.write_text(
            """
class Service:
    def expected_method(self):
        pass
    def unexpected_method(self):
        pass
"""
        )

        tree = _parse_file(str(test_file))
        collector = _collect_artifacts_from_ast(tree, "implementation")

        expected_items = [
            {"type": "class", "name": "Service"},
            {"type": "function", "name": "expected_method", "class": "Service"},
        ]

        # Call _validate_no_unexpected_artifacts directly - should raise error
        with pytest.raises(AlignmentError, match="unexpected_method"):
            _validate_no_unexpected_artifacts(
                expected_items,
                collector.found_classes,
                collector.found_functions,
                collector.found_methods,
            )

    def test_validate_no_unexpected_artifacts_passes_when_all_declared(self, tmp_path):
        """Test that _validate_no_unexpected_artifacts passes when all artifacts are declared."""
        test_file = tmp_path / "test.py"
        test_file.write_text(
            """
class Service:
    def expected_method(self):
        pass
"""
        )

        tree = _parse_file(str(test_file))
        collector = _collect_artifacts_from_ast(tree, "implementation")

        expected_items = [
            {"type": "class", "name": "Service"},
            {"type": "function", "name": "expected_method", "class": "Service"},
        ]

        # Call _validate_no_unexpected_artifacts directly - should not raise error
        _validate_no_unexpected_artifacts(
            expected_items,
            collector.found_classes,
            collector.found_functions,
            collector.found_methods,
        )

    def test_validate_no_unexpected_artifacts_allows_private_methods(self, tmp_path):
        """Test that _validate_no_unexpected_artifacts allows private methods."""
        test_file = tmp_path / "test.py"
        test_file.write_text(
            """
class Service:
    def public_method(self):
        pass
    def _private_method(self):
        pass
"""
        )

        tree = _parse_file(str(test_file))
        collector = _collect_artifacts_from_ast(tree, "implementation")

        expected_items = [
            {"type": "class", "name": "Service"},
            {"type": "function", "name": "public_method", "class": "Service"},
        ]

        # Call _validate_no_unexpected_artifacts directly - should not raise error
        _validate_no_unexpected_artifacts(
            expected_items,
            collector.found_classes,
            collector.found_functions,
            collector.found_methods,
        )
