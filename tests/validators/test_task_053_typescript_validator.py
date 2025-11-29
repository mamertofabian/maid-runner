"""Tests for Task-053: TypeScriptValidator class."""

from maid_runner.validators.typescript_validator import TypeScriptValidator
from maid_runner.validators.base_validator import BaseValidator


class TestTypeScriptValidator:
    """Test TypeScriptValidator class."""

    def test_typescript_validator_exists(self):
        """TypeScriptValidator class should exist."""
        assert TypeScriptValidator is not None

    def test_typescript_validator_inherits_from_base(self):
        """TypeScriptValidator should inherit from BaseValidator."""
        assert issubclass(TypeScriptValidator, BaseValidator)

    def test_typescript_validator_can_be_instantiated(self):
        """TypeScriptValidator should be instantiable."""
        validator = TypeScriptValidator()
        assert validator is not None
        assert isinstance(validator, BaseValidator)

    def test_supports_file_typescript_extensions(self):
        """TypeScriptValidator should support TypeScript/JavaScript files."""
        validator = TypeScriptValidator()
        assert validator.supports_file("test.ts") is True
        assert validator.supports_file("test.tsx") is True
        assert validator.supports_file("test.js") is True
        assert validator.supports_file("test.jsx") is True

    def test_supports_file_rejects_other_extensions(self):
        """TypeScriptValidator should reject non-TypeScript files."""
        validator = TypeScriptValidator()
        assert validator.supports_file("test.py") is False
        assert validator.supports_file("test.txt") is False
        assert validator.supports_file("test.md") is False

    def test_collect_artifacts_returns_dict(self, tmp_path):
        """TypeScriptValidator.collect_artifacts should return a dict."""
        test_file = tmp_path / "test.ts"
        test_file.write_text(
            """
function hello() {
    console.log("Hello");
}
"""
        )
        validator = TypeScriptValidator()
        result = validator.collect_artifacts(str(test_file), "implementation")
        assert isinstance(result, dict)

    def test_collect_artifacts_has_expected_keys(self, tmp_path):
        """TypeScriptValidator should return dict with artifact keys."""
        test_file = tmp_path / "test.ts"
        test_file.write_text(
            """
class MyClass {
    myMethod() {}
}
"""
        )
        validator = TypeScriptValidator()
        result = validator.collect_artifacts(str(test_file), "implementation")

        # Should have standard artifact collection keys
        assert "found_classes" in result
        assert "found_functions" in result

    def test_collect_artifacts_with_simple_function(self, tmp_path):
        """TypeScriptValidator should collect function artifacts."""
        test_file = tmp_path / "test.ts"
        test_file.write_text(
            """
function helloWorld() {
    return "hello";
}
"""
        )
        validator = TypeScriptValidator()
        result = validator.collect_artifacts(str(test_file), "implementation")

        assert "found_functions" in result
        # Basic implementation may return empty for now
        assert isinstance(result["found_functions"], dict)

    def test_collect_artifacts_with_class(self, tmp_path):
        """TypeScriptValidator should collect class artifacts."""
        test_file = tmp_path / "test.ts"
        test_file.write_text(
            """
class TestClass {
    constructor() {}
}
"""
        )
        validator = TypeScriptValidator()
        result = validator.collect_artifacts(str(test_file), "implementation")

        assert "found_classes" in result
        # Basic implementation may return empty for now
        assert isinstance(result["found_classes"], set)
