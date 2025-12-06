from maid_runner.validators.typescript_validator import TypeScriptValidator

# =============================================================================
# SECTION 9: Parameter Detection (_extract_parameters)
# =============================================================================


class TestParameterDetection:
    """Test _extract_parameters for all parameter patterns."""

    def test_required_parameters(self, tmp_path):
        """Must extract required parameters."""
        test_file = tmp_path / "test.ts"
        test_file.write_text(
            """
function greet(name: string, age: number): string {
    return `Hello ${name}, you are ${age}`;
}
"""
        )
        validator = TypeScriptValidator()
        result = validator.collect_artifacts(str(test_file), "implementation")
        assert result["found_functions"]["greet"] == [
            {"name": "name", "type": "string"},
            {"name": "age", "type": "number"},
        ]

    def test_optional_parameters(self, tmp_path):
        """Must extract optional parameters."""
        test_file = tmp_path / "test.ts"
        test_file.write_text(
            """
function greet(name: string, title?: string): string {
    return title ? `${title} ${name}` : name;
}
"""
        )
        validator = TypeScriptValidator()
        result = validator.collect_artifacts(str(test_file), "implementation")
        params = result["found_functions"]["greet"]
        param_names = [p["name"] for p in params]
        assert "name" in param_names
        assert "title" in param_names

    def test_rest_parameters(self, tmp_path):
        """Must extract rest parameters."""
        test_file = tmp_path / "test.ts"
        test_file.write_text(
            """
function sum(...numbers: number[]): number {
    return numbers.reduce((a, b) => a + b, 0);
}
"""
        )
        validator = TypeScriptValidator()
        result = validator.collect_artifacts(str(test_file), "implementation")
        params = result["found_functions"]["sum"]
        param_names = [p["name"] for p in params]
        assert "numbers" in param_names

    def test_default_parameters(self, tmp_path):
        """Must extract parameters with default values."""
        test_file = tmp_path / "test.ts"
        test_file.write_text(
            """
function createUser(name: string, role = "user"): void {}
"""
        )
        validator = TypeScriptValidator()
        result = validator.collect_artifacts(str(test_file), "implementation")
        params = result["found_functions"]["createUser"]
        param_names = [p["name"] for p in params]
        assert "name" in param_names
        assert "role" in param_names

    def test_destructured_object_parameters(self, tmp_path):
        """Must handle destructured object parameters."""
        test_file = tmp_path / "test.ts"
        test_file.write_text(
            """
function greet({ name, age }: { name: string, age: number }): string {
    return `${name} is ${age}`;
}
"""
        )
        validator = TypeScriptValidator()
        result = validator.collect_artifacts(str(test_file), "implementation")
        # Should detect the destructured parameter pattern
        assert "greet" in result["found_functions"]

    def test_destructured_array_parameters(self, tmp_path):
        """Must handle destructured array parameters."""
        test_file = tmp_path / "test.ts"
        test_file.write_text(
            """
function process([first, second]: [string, number]): void {}
"""
        )
        validator = TypeScriptValidator()
        result = validator.collect_artifacts(str(test_file), "implementation")
        assert "process" in result["found_functions"]
