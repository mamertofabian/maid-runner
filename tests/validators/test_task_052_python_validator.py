"""Tests for Task-052: PythonValidator class."""

from maid_runner.validators.python_validator import PythonValidator
from maid_runner.validators.base_validator import BaseValidator


class TestPythonValidator:
    """Test PythonValidator class."""

    def test_python_validator_exists(self):
        """PythonValidator class should exist."""
        assert PythonValidator is not None

    def test_python_validator_inherits_from_base(self):
        """PythonValidator should inherit from BaseValidator."""
        assert issubclass(PythonValidator, BaseValidator)

    def test_python_validator_can_be_instantiated(self):
        """PythonValidator should be instantiable."""
        validator = PythonValidator()
        assert validator is not None
        assert isinstance(validator, BaseValidator)

    def test_supports_file_python_extensions(self):
        """PythonValidator should support .py files."""
        validator = PythonValidator()
        assert validator.supports_file("test.py") is True
        assert validator.supports_file("module/test.py") is True

    def test_supports_file_rejects_other_extensions(self):
        """PythonValidator should reject non-Python files."""
        validator = PythonValidator()
        assert validator.supports_file("test.ts") is False
        assert validator.supports_file("test.js") is False
        assert validator.supports_file("test.txt") is False

    def test_collect_artifacts_with_simple_function(self, tmp_path):
        """PythonValidator should collect function artifacts."""
        test_file = tmp_path / "test.py"
        test_file.write_text(
            """
def hello_world():
    pass
"""
        )
        validator = PythonValidator()
        result = validator.collect_artifacts(str(test_file), "implementation")

        assert "found_functions" in result
        assert "hello_world" in result["found_functions"]

    def test_collect_artifacts_with_class(self, tmp_path):
        """PythonValidator should collect class artifacts."""
        test_file = tmp_path / "test.py"
        test_file.write_text(
            """
class MyClass:
    pass
"""
        )
        validator = PythonValidator()
        result = validator.collect_artifacts(str(test_file), "implementation")

        assert "found_classes" in result
        assert "MyClass" in result["found_classes"]

    def test_collect_artifacts_with_method(self, tmp_path):
        """PythonValidator should collect method artifacts."""
        test_file = tmp_path / "test.py"
        test_file.write_text(
            """
class MyClass:
    def my_method(self):
        pass
"""
        )
        validator = PythonValidator()
        result = validator.collect_artifacts(str(test_file), "implementation")

        assert "found_methods" in result
        assert "MyClass" in result["found_methods"]
        assert "my_method" in result["found_methods"]["MyClass"]

    def test_collect_artifacts_behavioral_mode(self, tmp_path):
        """PythonValidator should collect usage in behavioral mode."""
        test_file = tmp_path / "test.py"
        test_file.write_text(
            """
def test_something():
    result = MyClass()
    result.my_method()
"""
        )
        validator = PythonValidator()
        result = validator.collect_artifacts(str(test_file), "behavioral")

        assert "used_classes" in result
        assert "used_functions" in result or "used_methods" in result
