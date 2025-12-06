"""
Behavioral tests for Task-010: Type Validation Integration

Tests validate that type hint validation is integrated into the main
validation workflow, ensuring type mismatches are detected during
manifest validation.

These tests USE validate_with_ast to verify the integration works correctly.
"""

import pytest
from pathlib import Path
import sys

# Add parent directory to path to import validators
sys.path.insert(0, str(Path(__file__).parent.parent))

from maid_runner.validators.manifest_validator import validate_with_ast, AlignmentError

# Import private test modules for task-009 private artifacts
from tests._test_task_009_private_helpers import (  # noqa: F401
    TestArtifactCollectorBehavior,
    TestValidateExtractionInputsBehavior,
    TestAstToTypeStringBehavior,
    TestTypeNormalizationBehavior,
    TestSafeConversionBehavior,
    TestComplexTypeHandling,
    TestFallbackAndUtilityHelpers,
    TestTaskNumberExtraction,
    TestParseFileBehavior,
    TestCollectArtifactsFromAstBehavior,
    TestGetExpectedArtifactsBehavior,
    TestValidateAllArtifactsBehavior,
    TestCheckUnexpectedArtifactsBehavior,
    TestValidateSingleArtifactBehavior,
    TestValidateFunctionArtifactBehavior,
    TestValidateFunctionBehavioralBehavior,
    TestValidateParametersUsedBehavior,
    TestValidateMethodParametersBehavior,
    TestValidateFunctionImplementationBehavior,
    TestValidateClassBehavior,
    TestValidateAttributeBehavior,
    TestValidateFunctionBehavior,
    TestValidateNoUnexpectedArtifactsBehavior,
    TestTypeValidationHelpersBehavior,
    TestTypedDictHelpersBehavior,
    TestIntegrationWithValidation,
)


class TestTypeValidationIntegration:
    """Test that type validation is integrated into validate_with_ast."""

    def test_detects_missing_parameter_type_hint(self, tmp_path: Path):
        """Test that missing parameter type hints are detected."""
        # Create implementation with missing type hint
        code = """
def process_data(data):
    '''Process data'''
    return True
"""
        impl_file = tmp_path / "test.py"
        impl_file.write_text(code)

        # Manifest declares types
        manifest = {
            "expectedArtifacts": {
                "file": str(impl_file),
                "contains": [
                    {
                        "type": "function",
                        "name": "process_data",
                        "parameters": [{"name": "data", "type": "dict"}],
                        "returns": "bool",
                    }
                ],
            }
        }

        # Should detect missing type hint
        with pytest.raises(AlignmentError) as exc_info:
            validate_with_ast(manifest, str(impl_file), use_manifest_chain=False)

        error_msg = str(exc_info.value)
        assert "type" in error_msg.lower() or "hint" in error_msg.lower()

    def test_detects_wrong_parameter_type(self, tmp_path: Path):
        """Test that incorrect parameter types are detected."""
        code = """
def get_user(user_id: str) -> dict:
    '''Get user by ID'''
    return {}
"""
        impl_file = tmp_path / "test.py"
        impl_file.write_text(code)

        manifest = {
            "expectedArtifacts": {
                "file": str(impl_file),
                "contains": [
                    {
                        "type": "function",
                        "name": "get_user",
                        "parameters": [{"name": "user_id", "type": "int"}],
                        "returns": "dict",
                    }
                ],
            }
        }

        # Should detect type mismatch (str vs int)
        with pytest.raises(AlignmentError) as exc_info:
            validate_with_ast(manifest, str(impl_file), use_manifest_chain=False)

        error_msg = str(exc_info.value)
        assert "user_id" in error_msg
        assert "type" in error_msg.lower()

    def test_detects_missing_return_type(self, tmp_path: Path):
        """Test that missing return type hints are detected."""
        code = """
def calculate(x: int, y: int):
    '''Calculate sum'''
    return x + y
"""
        impl_file = tmp_path / "test.py"
        impl_file.write_text(code)

        manifest = {
            "expectedArtifacts": {
                "file": str(impl_file),
                "contains": [
                    {
                        "type": "function",
                        "name": "calculate",
                        "parameters": [
                            {"name": "x", "type": "int"},
                            {"name": "y", "type": "int"},
                        ],
                        "returns": "int",
                    }
                ],
            }
        }

        # Should detect missing return type
        with pytest.raises(AlignmentError) as exc_info:
            validate_with_ast(manifest, str(impl_file), use_manifest_chain=False)

        error_msg = str(exc_info.value)
        assert "return" in error_msg.lower() or "type" in error_msg.lower()

    def test_detects_wrong_return_type(self, tmp_path: Path):
        """Test that incorrect return types are detected."""
        code = """
def is_valid(value: str) -> str:
    '''Check if value is valid'''
    return "yes" if value else "no"
"""
        impl_file = tmp_path / "test.py"
        impl_file.write_text(code)

        manifest = {
            "expectedArtifacts": {
                "file": str(impl_file),
                "contains": [
                    {
                        "type": "function",
                        "name": "is_valid",
                        "parameters": [{"name": "value", "type": "str"}],
                        "returns": "bool",
                    }
                ],
            }
        }

        # Should detect return type mismatch (str vs bool)
        with pytest.raises(AlignmentError) as exc_info:
            validate_with_ast(manifest, str(impl_file), use_manifest_chain=False)

        error_msg = str(exc_info.value)
        assert "return" in error_msg.lower()
        assert "type" in error_msg.lower()

    def test_passes_with_correct_types(self, tmp_path: Path):
        """Test that correct type hints pass validation."""
        code = """
def greet(name: str, age: int) -> str:
    '''Greet a person'''
    return f"Hello {name}, age {age}"
"""
        impl_file = tmp_path / "test.py"
        impl_file.write_text(code)

        manifest = {
            "expectedArtifacts": {
                "file": str(impl_file),
                "contains": [
                    {
                        "type": "function",
                        "name": "greet",
                        "parameters": [
                            {"name": "name", "type": "str"},
                            {"name": "age", "type": "int"},
                        ],
                        "returns": "str",
                    }
                ],
            }
        }

        # Should pass - all types match
        validate_with_ast(manifest, str(impl_file), use_manifest_chain=False)

    def test_validates_method_types(self, tmp_path: Path):
        """Test that method type hints are validated."""
        code = """
class UserService:
    def get_user(self, user_id: str) -> dict:
        '''Get user by ID'''
        return {}
"""
        impl_file = tmp_path / "test.py"
        impl_file.write_text(code)

        manifest = {
            "expectedArtifacts": {
                "file": str(impl_file),
                "contains": [
                    {"type": "class", "name": "UserService"},
                    {
                        "type": "function",
                        "name": "get_user",
                        "class": "UserService",
                        "parameters": [{"name": "user_id", "type": "int"}],
                        "returns": "dict",
                    },
                ],
            }
        }

        # Should detect method parameter type mismatch
        with pytest.raises(AlignmentError) as exc_info:
            validate_with_ast(manifest, str(impl_file), use_manifest_chain=False)

        error_msg = str(exc_info.value)
        assert "user_id" in error_msg
        assert "type" in error_msg.lower()

    def test_handles_optional_types(self, tmp_path: Path):
        """Test that Optional types are handled correctly."""
        code = """
from typing import Optional

def find_user(user_id: int) -> Optional[dict]:
    '''Find user, may return None'''
    return None
"""
        impl_file = tmp_path / "test.py"
        impl_file.write_text(code)

        manifest = {
            "expectedArtifacts": {
                "file": str(impl_file),
                "contains": [
                    {
                        "type": "function",
                        "name": "find_user",
                        "parameters": [{"name": "user_id", "type": "int"}],
                        "returns": "Optional[dict]",
                    }
                ],
            }
        }

        # Should pass - Optional types match
        validate_with_ast(manifest, str(impl_file), use_manifest_chain=False)

    def test_handles_complex_generic_types(self, tmp_path: Path):
        """Test that complex generic types are validated."""
        code = """
from typing import List, Dict

def process_items(items: List[str]) -> Dict[str, int]:
    '''Process items and return counts'''
    return {}
"""
        impl_file = tmp_path / "test.py"
        impl_file.write_text(code)

        manifest = {
            "expectedArtifacts": {
                "file": str(impl_file),
                "contains": [
                    {
                        "type": "function",
                        "name": "process_items",
                        "parameters": [{"name": "items", "type": "List[str]"}],
                        "returns": "Dict[str, int]",
                    }
                ],
            }
        }

        # Should pass - generic types match
        validate_with_ast(manifest, str(impl_file), use_manifest_chain=False)

    def test_error_message_is_actionable(self, tmp_path: Path):
        """Test that error messages provide actionable information."""
        code = """
def bad_function(x: int, y: str) -> None:
    pass
"""
        impl_file = tmp_path / "test.py"
        impl_file.write_text(code)

        manifest = {
            "expectedArtifacts": {
                "file": str(impl_file),
                "contains": [
                    {
                        "type": "function",
                        "name": "bad_function",
                        "parameters": [
                            {"name": "x", "type": "str"},  # Wrong type
                            {"name": "y", "type": "int"},  # Wrong type
                        ],
                        "returns": "bool",  # Wrong type
                    }
                ],
            }
        }

        # Should provide clear error message
        with pytest.raises(AlignmentError) as exc_info:
            validate_with_ast(manifest, str(impl_file), use_manifest_chain=False)

        error_msg = str(exc_info.value)
        # Error should mention function name
        assert "bad_function" in error_msg
        # Error should mention type validation
        assert "type" in error_msg.lower()

    def test_type_validation_runs_in_implementation_mode(self, tmp_path: Path):
        """Test that type validation runs in implementation mode (default)."""
        # Missing type hint should cause failure in implementation mode
        code = """
def calculate(x):  # Missing type hint
    return x * 2
"""
        impl_file = tmp_path / "test.py"
        impl_file.write_text(code)

        manifest = {
            "expectedArtifacts": {
                "file": str(impl_file),
                "contains": [
                    {
                        "type": "function",
                        "name": "calculate",
                        "parameters": [{"name": "x", "type": "int"}],
                        "returns": "int",
                    }
                ],
            }
        }

        # Default mode is implementation - should detect missing type hint
        with pytest.raises(AlignmentError) as exc_info:
            validate_with_ast(manifest, str(impl_file), use_manifest_chain=False)

        error_msg = str(exc_info.value)
        assert "type" in error_msg.lower()
