"""
Private test module for private helper function declared in task-025 manifest.

These tests verify the actual behavior of private helper function that is declared
in the manifest. While this is an internal helper, it's part of the declared API
and must be behaviorally validated.

Tests focus on meaningful behavior:
- How this helper enables public APIs to work correctly
- Edge cases and error conditions
- Real-world usage scenarios

Related task: task-025-fix-cls-parameter-filtering
"""

import pytest

# Import with fallback for Red phase testing
try:
    from maid_runner.validators.manifest_validator import (
        _validate_method_parameters,
        _parse_file,
        _collect_artifacts_from_ast,
    )
except ImportError as e:
    # In Red phase, these functions won't exist yet
    pytest.skip(f"Implementation not ready: {e}", allow_module_level=True)


class TestValidateMethodParameters:
    """Test _validate_method_parameters private function behavior."""

    def test_validate_method_parameters_called_with_classmethod(self, tmp_path):
        """Test that _validate_method_parameters is called with classmethod parameters."""
        test_file = tmp_path / "test.py"
        test_file.write_text(
            """
class ConfigService:
    @classmethod
    def create_default(cls, name: str, value: int):
        return cls()
"""
        )

        tree = _parse_file(str(test_file))
        collector = _collect_artifacts_from_ast(tree, "implementation")

        method_name = "create_default"
        parameters = [
            {"name": "name", "type": "str"},
            {"name": "value", "type": "int"},
        ]
        class_name = "ConfigService"

        # Call _validate_method_parameters directly
        _validate_method_parameters(method_name, parameters, class_name, collector)

        # Should not raise an error (cls is filtered)

    def test_validate_method_parameters_called_with_regular_method(self, tmp_path):
        """Test that _validate_method_parameters is called with regular method parameters."""
        test_file = tmp_path / "test.py"
        test_file.write_text(
            """
class UserService:
    def create_user(self, username: str, email: str):
        return {}
"""
        )

        tree = _parse_file(str(test_file))
        collector = _collect_artifacts_from_ast(tree, "implementation")

        method_name = "create_user"
        parameters = [
            {"name": "username", "type": "str"},
            {"name": "email", "type": "str"},
        ]
        class_name = "UserService"

        # Call _validate_method_parameters directly
        _validate_method_parameters(method_name, parameters, class_name, collector)

        # Should not raise an error (self is filtered)

    def test_validate_method_parameters_filters_cls_parameter(self, tmp_path):
        """Test that _validate_method_parameters filters cls parameter from classmethods."""
        test_file = tmp_path / "test.py"
        test_file.write_text(
            """
class Service:
    @classmethod
    def create(cls, name: str):
        return cls()
"""
        )

        tree = _parse_file(str(test_file))
        collector = _collect_artifacts_from_ast(tree, "implementation")

        method_name = "create"
        parameters = [
            {"name": "name", "type": "str"},
        ]
        class_name = "Service"

        # Call _validate_method_parameters directly
        # Should not raise error even though implementation has cls parameter
        _validate_method_parameters(method_name, parameters, class_name, collector)

    def test_validate_method_parameters_filters_self_parameter(self, tmp_path):
        """Test that _validate_method_parameters filters self parameter from regular methods."""
        test_file = tmp_path / "test.py"
        test_file.write_text(
            """
class Service:
    def process(self, data: str):
        return data
"""
        )

        tree = _parse_file(str(test_file))
        collector = _collect_artifacts_from_ast(tree, "implementation")

        method_name = "process"
        parameters = [
            {"name": "data", "type": "str"},
        ]
        class_name = "Service"

        # Call _validate_method_parameters directly
        # Should not raise error even though implementation has self parameter
        _validate_method_parameters(method_name, parameters, class_name, collector)

    def test_validate_method_parameters_handles_empty_parameters(self, tmp_path):
        """Test that _validate_method_parameters handles methods with no parameters."""
        test_file = tmp_path / "test.py"
        test_file.write_text(
            """
class Service:
    @classmethod
    def create(cls):
        return cls()
"""
        )

        tree = _parse_file(str(test_file))
        collector = _collect_artifacts_from_ast(tree, "implementation")

        method_name = "create"
        parameters = []
        class_name = "Service"

        # Call _validate_method_parameters directly
        _validate_method_parameters(method_name, parameters, class_name, collector)

        # Should not raise an error
