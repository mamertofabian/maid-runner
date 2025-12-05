"""Tests for Task-081: Fix method parameter validation to handle dict format.

This test verifies that _validate_method_parameters correctly handles
parameters in dict format (with 'name' and 'type' keys) as returned by
TypeScript validator after Task-077.
"""

import pytest
from maid_runner.validators.manifest_validator import (
    _validate_method_parameters,
    AlignmentError,
)


class MockArtifactCollector:
    """Mock artifact collector for testing."""

    def __init__(self, found_methods):
        self.found_methods = found_methods


class TestMethodParameterValidation:
    """Test _validate_method_parameters handles dict format parameters."""

    def test_validate_method_with_dict_format_parameters(self):
        """Must validate method parameters when actual_parameters are dicts."""
        # Simulate TypeScript validator output (dict format)
        found_methods = {
            "PushNotificationService": {
                "clearAllSubscriptions": [{"name": "userId", "type": "string"}]
            }
        }
        collector = MockArtifactCollector(found_methods)

        # Manifest expects parameter in dict format
        expected_parameters = [{"name": "userId", "type": "string"}]

        # Should not raise an error
        _validate_method_parameters(
            "clearAllSubscriptions",
            expected_parameters,
            "PushNotificationService",
            collector,
        )

    def test_validate_method_with_legacy_string_format_parameters(self):
        """Must validate method parameters when actual_parameters are strings (legacy)."""
        # Simulate Python validator output (legacy string format)
        found_methods = {"MyClass": {"myMethod": ["param1", "param2"]}}
        collector = MockArtifactCollector(found_methods)

        # Manifest expects parameters
        expected_parameters = [{"name": "param1"}, {"name": "param2"}]

        # Should not raise an error
        _validate_method_parameters(
            "myMethod",
            expected_parameters,
            "MyClass",
            collector,
        )

    def test_validate_method_missing_parameter_dict_format(self):
        """Must raise error when expected parameter is missing (dict format)."""
        found_methods = {
            "MyService": {"processData": [{"name": "data", "type": "string"}]}
        }
        collector = MockArtifactCollector(found_methods)

        # Manifest expects userId but method only has data
        expected_parameters = [{"name": "userId", "type": "string"}]

        with pytest.raises(AlignmentError) as exc_info:
            _validate_method_parameters(
                "processData",
                expected_parameters,
                "MyService",
                collector,
            )

        assert "Parameter 'userId' not found in method 'processData'" in str(
            exc_info.value
        )

    def test_validate_method_missing_parameter_legacy_format(self):
        """Must raise error when expected parameter is missing (legacy format)."""
        found_methods = {"MyClass": {"myMethod": ["param1"]}}
        collector = MockArtifactCollector(found_methods)

        # Manifest expects param2 but method only has param1
        expected_parameters = [{"name": "param2"}]

        with pytest.raises(AlignmentError) as exc_info:
            _validate_method_parameters(
                "myMethod",
                expected_parameters,
                "MyClass",
                collector,
            )

        assert "Parameter 'param2' not found in method 'myMethod'" in str(
            exc_info.value
        )

    def test_validate_method_with_multiple_dict_parameters(self):
        """Must validate method with multiple parameters in dict format."""
        found_methods = {
            "UserService": {
                "createUser": [
                    {"name": "name", "type": "string"},
                    {"name": "email", "type": "string"},
                    {"name": "age", "type": "number"},
                ]
            }
        }
        collector = MockArtifactCollector(found_methods)

        expected_parameters = [
            {"name": "name", "type": "string"},
            {"name": "email", "type": "string"},
            {"name": "age", "type": "number"},
        ]

        # Should not raise an error
        _validate_method_parameters(
            "createUser",
            expected_parameters,
            "UserService",
            collector,
        )

    def test_validate_method_filters_self_and_cls_legacy_format(self):
        """Must filter out 'self' and 'cls' parameters in legacy format."""
        found_methods = {
            "MyClass": {
                "instanceMethod": ["self", "param1"],
                "classMethod": ["cls", "param2"],
            }
        }
        collector = MockArtifactCollector(found_methods)

        # Should only validate param1, not self
        expected_parameters = [{"name": "param1"}]
        _validate_method_parameters(
            "instanceMethod",
            expected_parameters,
            "MyClass",
            collector,
        )

        # Should only validate param2, not cls
        expected_parameters = [{"name": "param2"}]
        _validate_method_parameters(
            "classMethod",
            expected_parameters,
            "MyClass",
            collector,
        )

    def test_validate_method_empty_parameters(self):
        """Must validate method with no parameters."""
        found_methods = {"MyService": {"noParams": []}}
        collector = MockArtifactCollector(found_methods)

        expected_parameters = []

        # Should not raise an error
        _validate_method_parameters(
            "noParams",
            expected_parameters,
            "MyService",
            collector,
        )

    def test_validate_method_mixed_format_handling(self):
        """Must handle edge case where parameters list might be empty dicts."""
        found_methods = {"MyClass": {"myMethod": []}}
        collector = MockArtifactCollector(found_methods)

        # Empty parameters should work
        expected_parameters = []

        # Should not raise an error
        _validate_method_parameters(
            "myMethod",
            expected_parameters,
            "MyClass",
            collector,
        )
