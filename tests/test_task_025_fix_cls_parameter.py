"""
Behavioral tests for Task-025: Fix cls parameter filtering in validator.

These tests verify that the _validate_method_parameters function correctly
filters both 'self' and 'cls' parameters from method validation, allowing
classmethods to validate correctly without requiring 'cls' in the manifest.
"""

import sys
from pathlib import Path
import pytest
import tempfile

# Add parent directory to path to enable imports
sys.path.insert(0, str(Path(__file__).parent.parent))

# Import with fallback for Red phase testing
try:
    from maid_runner.validators.manifest_validator import validate_with_ast
except ImportError as e:
    # In Red phase, this function won't exist yet
    pytest.skip(f"Implementation not ready: {e}", allow_module_level=True)

# Import private test modules for task-025 private artifacts
from tests._test_task_025_private_helpers import (  # noqa: F401
    TestValidateMethodParameters,
)


class TestClsParameterFiltering:
    """Test that cls parameter is properly filtered in classmethod validation."""

    def test_classmethod_validates_without_cls_in_manifest(self):
        """Test that classmethods validate successfully without cls in manifest args."""
        # Create a temporary directory for test files
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp_path = Path(tmpdir)

            # Create a Python file with a classmethod
            code = '''
class ConfigService:
    """Service for managing configuration."""

    @classmethod
    def create_default(cls, name: str, value: int) -> "ConfigService":
        """Create a default configuration."""
        return cls()
'''
            test_file = tmp_path / "config_service.py"
            test_file.write_text(code)

            # Create manifest WITHOUT cls in the args (this should work after fix)
            manifest = {
                "expectedArtifacts": {
                    "file": str(test_file),
                    "contains": [
                        {"type": "class", "name": "ConfigService"},
                        {
                            "type": "function",
                            "name": "create_default",
                            "class": "ConfigService",
                            "args": [
                                {"name": "name", "type": "str"},
                                {"name": "value", "type": "int"},
                            ],
                            "returns": "ConfigService",
                        },
                    ],
                }
            }

            # USE the validator - should pass after fix (cls is filtered)
            validate_with_ast(manifest, str(test_file))

    def test_regular_method_validates_without_self_in_manifest(self):
        """Test that regular methods still validate successfully without self in manifest args."""
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp_path = Path(tmpdir)

            # Create a Python file with a regular method
            code = '''
class UserService:
    """Service for managing users."""

    def create_user(self, username: str, email: str) -> dict:
        """Create a new user."""
        return {"username": username, "email": email}
'''
            test_file = tmp_path / "user_service.py"
            test_file.write_text(code)

            # Create manifest WITHOUT self in the args
            manifest = {
                "expectedArtifacts": {
                    "file": str(test_file),
                    "contains": [
                        {"type": "class", "name": "UserService"},
                        {
                            "type": "function",
                            "name": "create_user",
                            "class": "UserService",
                            "args": [
                                {"name": "username", "type": "str"},
                                {"name": "email", "type": "str"},
                            ],
                            "returns": "dict",
                        },
                    ],
                }
            }

            # USE the validator - should pass (self is filtered)
            validate_with_ast(manifest, str(test_file))

    def test_mixed_methods_in_same_class(self):
        """Test class with both regular methods and classmethods."""
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp_path = Path(tmpdir)

            # Create a Python file with both method types
            code = '''
class DataService:
    """Service for managing data."""

    def process_data(self, data: str) -> str:
        """Process some data."""
        return data.upper()

    @classmethod
    def from_config(cls, config: dict) -> "DataService":
        """Create service from config."""
        return cls()

    @staticmethod
    def validate_input(value: str) -> bool:
        """Validate input value."""
        return bool(value)
'''
            test_file = tmp_path / "data_service.py"
            test_file.write_text(code)

            # Create manifest with all three method types
            manifest = {
                "expectedArtifacts": {
                    "file": str(test_file),
                    "contains": [
                        {"type": "class", "name": "DataService"},
                        {
                            "type": "function",
                            "name": "process_data",
                            "class": "DataService",
                            "args": [{"name": "data", "type": "str"}],
                            "returns": "str",
                        },
                        {
                            "type": "function",
                            "name": "from_config",
                            "class": "DataService",
                            "args": [{"name": "config", "type": "dict"}],
                            "returns": "DataService",
                        },
                        {
                            "type": "function",
                            "name": "validate_input",
                            "class": "DataService",
                            "args": [{"name": "value", "type": "str"}],
                            "returns": "bool",
                        },
                    ],
                }
            }

            # USE the validator - should pass for all method types
            validate_with_ast(manifest, str(test_file))

    def test_classmethod_with_no_additional_params(self):
        """Test classmethod with only cls parameter (no other params)."""
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp_path = Path(tmpdir)

            # Create a Python file with a classmethod that only has cls
            code = '''
class SimpleService:
    """Simple service."""

    @classmethod
    def create(cls) -> "SimpleService":
        """Create a simple service instance."""
        return cls()
'''
            test_file = tmp_path / "simple_service.py"
            test_file.write_text(code)

            # Create manifest with empty args list (no params after filtering cls)
            manifest = {
                "expectedArtifacts": {
                    "file": str(test_file),
                    "contains": [
                        {"type": "class", "name": "SimpleService"},
                        {
                            "type": "function",
                            "name": "create",
                            "class": "SimpleService",
                            "args": [],  # Empty - cls is filtered
                            "returns": "SimpleService",
                        },
                    ],
                }
            }

            # USE the validator - should pass with empty args
            validate_with_ast(manifest, str(test_file))


class TestBackwardCompatibility:
    """Test that the fix doesn't break existing functionality."""

    def test_self_parameter_still_filtered(self):
        """Verify that self parameter filtering still works correctly."""
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp_path = Path(tmpdir)

            code = '''
class LegacyService:
    """Legacy service class."""

    def legacy_method(self, param1: str, param2: int) -> None:
        """A legacy method."""
        pass
'''
            test_file = tmp_path / "legacy.py"
            test_file.write_text(code)

            manifest = {
                "expectedArtifacts": {
                    "file": str(test_file),
                    "contains": [
                        {"type": "class", "name": "LegacyService"},
                        {
                            "type": "function",
                            "name": "legacy_method",
                            "class": "LegacyService",
                            "args": [
                                {"name": "param1", "type": "str"},
                                {"name": "param2", "type": "int"},
                            ],
                            "returns": "None",
                        },
                    ],
                }
            }

            # USE the validator - should still pass (self still filtered)
            validate_with_ast(manifest, str(test_file))
