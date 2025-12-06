from maid_runner.validators.typescript_validator import TypeScriptValidator

# =============================================================================
# SECTION 16: Artifact Structure Consistency
# =============================================================================


class TestArtifactStructure:
    """Test that collected artifacts have consistent structure."""

    def test_implementation_mode_structure(self, tmp_path):
        """Implementation mode must return all required keys."""
        test_file = tmp_path / "test.ts"
        test_file.write_text(
            """
class TestClass {
    method() {}
}
function testFunc() {}
"""
        )
        validator = TypeScriptValidator()
        result = validator.collect_artifacts(str(test_file), "implementation")

        # Must have all required keys
        required_keys = [
            "found_classes",
            "found_functions",
            "found_methods",
            "found_class_bases",
            "found_attributes",
            "variable_to_class",
            "found_function_types",
            "found_method_types",
            "used_classes",
            "used_functions",
            "used_methods",
            "used_arguments",
        ]
        for key in required_keys:
            assert key in result, f"Missing required key: {key}"

        # Check types
        assert isinstance(result["found_classes"], set)
        assert isinstance(result["found_functions"], dict)
        assert isinstance(result["found_methods"], dict)
        assert isinstance(result["used_classes"], set)
        assert isinstance(result["used_functions"], set)
        assert isinstance(result["used_methods"], dict)

    def test_behavioral_mode_structure(self, tmp_path):
        """Behavioral mode must return all required keys."""
        test_file = tmp_path / "test.ts"
        test_file.write_text(
            """
const obj = new TestClass();
obj.method();
testFunc();
"""
        )
        validator = TypeScriptValidator()
        result = validator.collect_artifacts(str(test_file), "behavioral")

        # Must have all required keys
        assert "used_classes" in result
        assert "used_functions" in result
        assert "used_methods" in result

        # Check types
        assert isinstance(result["used_classes"], set)
        assert isinstance(result["used_functions"], set)
        assert isinstance(result["used_methods"], dict)

    def test_method_parameters_are_lists(self, tmp_path):
        """Method parameters must be returned as lists."""
        test_file = tmp_path / "test.ts"
        test_file.write_text(
            """
class Service {
    process(a: string, b: number): void {}
}
"""
        )
        validator = TypeScriptValidator()
        result = validator.collect_artifacts(str(test_file), "implementation")
        assert isinstance(result["found_methods"]["Service"]["process"], list)
        assert result["found_methods"]["Service"]["process"] == [
            {"name": "a", "type": "string"},
            {"name": "b", "type": "number"},
        ]

    def test_function_parameters_are_lists(self, tmp_path):
        """Function parameters must be returned as lists."""
        test_file = tmp_path / "test.ts"
        test_file.write_text(
            """
function process(x: number, y: string): void {}
"""
        )
        validator = TypeScriptValidator()
        result = validator.collect_artifacts(str(test_file), "implementation")
        assert isinstance(result["found_functions"]["process"], list)
        assert result["found_functions"]["process"] == [
            {"name": "x", "type": "number"},
            {"name": "y", "type": "string"},
        ]
