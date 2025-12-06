"""
Behavioral tests for Task-026: Detect classmethod calls on class name.

These tests verify that the validator correctly detects classmethod calls made
directly on the class name (e.g., ConfigService.create_default()) in behavioral
test validation mode.
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

# Import private test modules for task-026 private artifacts
from tests._test_task_026_private_helpers import (  # noqa: F401
    TestArtifactCollectorVisitCall,
)


class TestClassmethodCallDetection:
    """Test that classmethod calls on class names are properly detected."""

    def test_detects_classmethod_call_on_class_name(self):
        """Test that direct classmethod calls on class names are detected."""
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp_path = Path(tmpdir)

            # Create implementation with a classmethod
            impl_code = '''
class ConfigService:
    """Service for managing configuration."""

    @classmethod
    def create_default(cls, name: str):
        """Create a default configuration."""
        return cls()
'''
            impl_file = tmp_path / "config_service.py"
            impl_file.write_text(impl_code)

            # Create behavioral test that calls classmethod directly on class name
            test_code = '''
from config_service import ConfigService

def test_create_default_config():
    """Test creating a default configuration."""
    # Call classmethod directly on class name
    ConfigService.create_default("test")
'''
            test_file = tmp_path / "test_config.py"
            test_file.write_text(test_code)

            # Create manifest expecting the classmethod to be USED in tests
            manifest = {
                "expectedArtifacts": {
                    "file": str(impl_file),
                    "contains": [
                        {"type": "class", "name": "ConfigService"},
                        {
                            "type": "function",
                            "name": "create_default",
                            "class": "ConfigService",
                            "args": [{"name": "name", "type": "str"}],
                        },
                    ],
                },
                "validationCommand": ["pytest", str(test_file), "-v"],
            }

            # USE the validator in behavioral mode - should detect the classmethod call
            validate_with_ast(
                manifest,
                str(test_file),
                use_manifest_chain=False,
                validation_mode="behavioral",
            )

    def test_detects_staticmethod_call_on_class_name(self):
        """Test that staticmethod calls on class names are also detected."""
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp_path = Path(tmpdir)

            # Create implementation with a staticmethod
            impl_code = '''
class DataValidator:
    """Validator for data."""

    @staticmethod
    def validate_email(email: str):
        """Validate an email address."""
        return "@" in email
'''
            impl_file = tmp_path / "validator.py"
            impl_file.write_text(impl_code)

            # Create behavioral test that calls staticmethod directly on class name
            test_code = '''
from validator import DataValidator

def test_validate_email():
    """Test email validation."""
    # Call staticmethod directly on class name
    DataValidator.validate_email("test@example.com")
'''
            test_file = tmp_path / "test_validator.py"
            test_file.write_text(test_code)

            # Create manifest
            manifest = {
                "expectedArtifacts": {
                    "file": str(impl_file),
                    "contains": [
                        {"type": "class", "name": "DataValidator"},
                        {
                            "type": "function",
                            "name": "validate_email",
                            "class": "DataValidator",
                            "args": [{"name": "email", "type": "str"}],
                        },
                    ],
                },
                "validationCommand": ["pytest", str(test_file), "-v"],
            }

            # USE the validator - should detect the staticmethod call
            validate_with_ast(
                manifest,
                str(test_file),
                use_manifest_chain=False,
                validation_mode="behavioral",
            )

    def test_detects_multiple_classmethod_calls(self):
        """Test detecting multiple classmethod calls in the same test."""
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp_path = Path(tmpdir)

            # Create implementation with multiple classmethods
            impl_code = '''
class UserFactory:
    """Factory for creating users."""

    @classmethod
    def create_admin(cls, name: str):
        """Create an admin user."""
        return cls()

    @classmethod
    def create_guest(cls):
        """Create a guest user."""
        return cls()
'''
            impl_file = tmp_path / "user_factory.py"
            impl_file.write_text(impl_code)

            # Create behavioral test that calls multiple classmethods
            test_code = '''
from user_factory import UserFactory

def test_user_creation():
    """Test creating different types of users."""
    UserFactory.create_admin("admin")
    UserFactory.create_guest()
'''
            test_file = tmp_path / "test_users.py"
            test_file.write_text(test_code)

            # Create manifest
            manifest = {
                "expectedArtifacts": {
                    "file": str(impl_file),
                    "contains": [
                        {"type": "class", "name": "UserFactory"},
                        {
                            "type": "function",
                            "name": "create_admin",
                            "class": "UserFactory",
                            "args": [{"name": "name", "type": "str"}],
                        },
                        {
                            "type": "function",
                            "name": "create_guest",
                            "class": "UserFactory",
                            "args": [],
                        },
                    ],
                },
                "validationCommand": ["pytest", str(test_file), "-v"],
            }

            # USE the validator - should detect both classmethod calls
            validate_with_ast(
                manifest,
                str(test_file),
                use_manifest_chain=False,
                validation_mode="behavioral",
            )

    def test_instance_methods_still_work(self):
        """Test that regular instance method detection still works."""
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp_path = Path(tmpdir)

            # Create implementation with regular instance method
            impl_code = '''
class Calculator:
    """Simple calculator."""

    def add(self, a: int, b: int):
        """Add two numbers."""
        return a + b
'''
            impl_file = tmp_path / "calculator.py"
            impl_file.write_text(impl_code)

            # Create behavioral test that uses instance method
            test_code = '''
from calculator import Calculator

def test_addition():
    """Test addition."""
    calc = Calculator()
    calc.add(2, 3)
'''
            test_file = tmp_path / "test_calculator.py"
            test_file.write_text(test_code)

            # Create manifest
            manifest = {
                "expectedArtifacts": {
                    "file": str(impl_file),
                    "contains": [
                        {"type": "class", "name": "Calculator"},
                        {
                            "type": "function",
                            "name": "add",
                            "class": "Calculator",
                            "args": [
                                {"name": "a", "type": "int"},
                                {"name": "b", "type": "int"},
                            ],
                        },
                    ],
                },
                "validationCommand": ["pytest", str(test_file), "-v"],
            }

            # USE the validator - instance methods should still work
            validate_with_ast(
                manifest,
                str(test_file),
                use_manifest_chain=False,
                validation_mode="behavioral",
            )
