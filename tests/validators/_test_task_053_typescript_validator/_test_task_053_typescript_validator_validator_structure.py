from maid_runner.validators.typescript_validator import TypeScriptValidator
from maid_runner.validators.base_validator import BaseValidator

# =============================================================================
# SECTION 1: Validator Structure and Interface Compliance
# =============================================================================


class TestValidatorStructure:
    """Test TypeScriptValidator class structure and BaseValidator compliance."""

    def test_validator_class_exists(self):
        """TypeScriptValidator class must exist."""
        assert TypeScriptValidator is not None

    def test_validator_inherits_from_base(self):
        """TypeScriptValidator must inherit from BaseValidator."""
        assert issubclass(TypeScriptValidator, BaseValidator)

    def test_validator_can_be_instantiated(self):
        """TypeScriptValidator must be instantiable."""
        validator = TypeScriptValidator()
        assert validator is not None
        assert isinstance(validator, BaseValidator)

    def test_supports_file_method_exists(self):
        """supports_file method must exist and return bool."""
        validator = TypeScriptValidator()
        result = validator.supports_file("test.ts")
        assert isinstance(result, bool)

    def test_collect_artifacts_method_exists(self, tmp_path):
        """collect_artifacts method must exist and return dict."""
        test_file = tmp_path / "test.ts"
        test_file.write_text("class Test {}")
        validator = TypeScriptValidator()
        result = validator.collect_artifacts(str(test_file), "implementation")
        assert isinstance(result, dict)
