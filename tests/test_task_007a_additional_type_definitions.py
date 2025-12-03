"""Test Task-007a: Additional type definitions for manifest validator.

This test module verifies the new type definitions added to validators/types.py
that are needed for properly type-hinting the manifest_validator.py module.
"""

import sys
from pathlib import Path
from typing import get_args, get_origin

# Add parent directory to path to import validators module
sys.path.insert(0, str(Path(__file__).parent.parent))

from maid_runner.validators.types import (
    ValidationMode,
    ParameterInfo,
    FunctionTypeInfo,
    CollectorTypeInfo,
)


class TestValidationMode:
    """Test the ValidationMode literal type."""

    def test_validation_mode_exists(self):
        """Verify ValidationMode type alias is defined."""
        # ValidationMode should be importable
        assert ValidationMode is not None

    def test_validation_mode_is_literal(self):
        """Verify ValidationMode is a Literal type with correct values."""
        # Get the origin and args of the type
        origin = get_origin(ValidationMode)
        args = get_args(ValidationMode)

        # Check it's a Literal type
        from typing import Literal

        assert origin is Literal

        # Check it has the correct literal values
        assert set(args) == {"implementation", "behavioral", "schema"}


class TestParameterInfo:
    """Test the ParameterInfo TypedDict."""

    def test_parameter_info_exists(self):
        """Verify ParameterInfo class exists."""
        assert ParameterInfo is not None

    def test_parameter_info_is_typed_dict(self):
        """Verify ParameterInfo is a TypedDict."""
        assert issubclass(ParameterInfo, dict)
        # Check it has TypedDict annotations
        assert hasattr(ParameterInfo, "__annotations__")

    def test_parameter_info_has_required_fields(self):
        """Verify ParameterInfo has the required field annotations."""
        annotations = ParameterInfo.__annotations__

        # Check required fields
        assert "name" in annotations
        assert annotations["name"] is str

        # Check optional fields
        assert "type" in annotations
        from typing import Optional

        # The type field should be Optional[str]
        assert (
            get_origin(annotations["type"]) is Optional
            or annotations["type"] == Optional[str]
        )


class TestFunctionTypeInfo:
    """Test the FunctionTypeInfo TypedDict."""

    def test_function_type_info_exists(self):
        """Verify FunctionTypeInfo class exists."""
        assert FunctionTypeInfo is not None

    def test_function_type_info_is_typed_dict(self):
        """Verify FunctionTypeInfo is a TypedDict."""
        assert issubclass(FunctionTypeInfo, dict)
        assert hasattr(FunctionTypeInfo, "__annotations__")

    def test_function_type_info_has_required_fields(self):
        """Verify FunctionTypeInfo has the required field annotations."""
        from typing import List, Optional

        annotations = FunctionTypeInfo.__annotations__

        # Check parameters field
        assert "parameters" in annotations
        # Should be List[ParameterInfo]
        origin = get_origin(annotations["parameters"])
        assert origin is list or origin is List

        # Check returns field
        assert "returns" in annotations
        # Should be Optional[str]
        returns_origin = get_origin(annotations["returns"])
        assert returns_origin is Optional or annotations["returns"] == Optional[str]


class TestCollectorTypeInfo:
    """Test the CollectorTypeInfo TypedDict."""

    def test_collector_type_info_exists(self):
        """Verify CollectorTypeInfo class exists."""
        assert CollectorTypeInfo is not None

    def test_collector_type_info_is_typed_dict(self):
        """Verify CollectorTypeInfo is a TypedDict."""
        assert issubclass(CollectorTypeInfo, dict)
        assert hasattr(CollectorTypeInfo, "__annotations__")

    def test_collector_type_info_has_required_fields(self):
        """Verify CollectorTypeInfo has the required field annotations."""
        from typing import Dict

        annotations = CollectorTypeInfo.__annotations__

        # Check functions field
        assert "functions" in annotations
        # Should be Dict[str, FunctionTypeInfo]
        functions_origin = get_origin(annotations["functions"])
        assert functions_origin is dict or functions_origin is Dict

        # Check methods field
        assert "methods" in annotations
        # Should be Dict[str, Dict[str, FunctionTypeInfo]]
        methods_origin = get_origin(annotations["methods"])
        assert methods_origin is dict or methods_origin is Dict


class TestTypeUsageIntegration:
    """Integration tests verifying the types work together correctly."""

    def test_create_parameter_info(self):
        """Test creating a ParameterInfo instance."""
        # Should be able to create valid instances
        param1: ParameterInfo = {"name": "path", "type": "str"}
        param2: ParameterInfo = {"name": "data"}  # type is optional

        assert param1["name"] == "path"
        assert param1["type"] == "str"
        assert param2["name"] == "data"

    def test_create_function_type_info(self):
        """Test creating a FunctionTypeInfo instance."""
        func_info: FunctionTypeInfo = {
            "parameters": [{"name": "self"}, {"name": "path", "type": "str"}],
            "returns": "bool",
        }

        assert len(func_info["parameters"]) == 2
        assert func_info["returns"] == "bool"

    def test_create_collector_type_info(self):
        """Test creating a CollectorTypeInfo instance."""
        collector_info: CollectorTypeInfo = {
            "functions": {
                "validate": {
                    "parameters": [{"name": "path", "type": "str"}],
                    "returns": "ValidationResult",
                }
            },
            "methods": {
                "Validator": {
                    "check": {"parameters": [{"name": "self"}], "returns": "bool"}
                }
            },
        }

        assert "validate" in collector_info["functions"]
        assert "Validator" in collector_info["methods"]
        assert "check" in collector_info["methods"]["Validator"]

    def test_validation_mode_values(self):
        """Test that ValidationMode can be used with its literal values."""
        # These should be the valid literal values
        implementation_mode: ValidationMode = "implementation"
        behavioral_mode: ValidationMode = "behavioral"

        assert implementation_mode == "implementation"
        assert behavioral_mode == "behavioral"
