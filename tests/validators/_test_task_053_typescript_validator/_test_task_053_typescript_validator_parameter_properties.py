from maid_runner.validators.typescript_validator import TypeScriptValidator

# =============================================================================
# SECTION 11: Parameter Properties
# =============================================================================


class TestParameterProperties:
    """Test detection of parameter properties (constructor parameters that create class properties)."""

    def test_public_parameter_property(self, tmp_path):
        """Must handle public parameter properties."""
        test_file = tmp_path / "test.ts"
        test_file.write_text(
            """
class User {
    constructor(public name: string, public age: number) {}
}
"""
        )
        validator = TypeScriptValidator()
        result = validator.collect_artifacts(str(test_file), "implementation")
        assert "User" in result["found_classes"]

    def test_private_parameter_property(self, tmp_path):
        """Must handle private parameter properties."""
        test_file = tmp_path / "test.ts"
        test_file.write_text(
            """
class Service {
    constructor(private config: Config) {}
}
"""
        )
        validator = TypeScriptValidator()
        result = validator.collect_artifacts(str(test_file), "implementation")
        assert "Service" in result["found_classes"]

    def test_readonly_parameter_property(self, tmp_path):
        """Must handle readonly parameter properties."""
        test_file = tmp_path / "test.ts"
        test_file.write_text(
            """
class Config {
    constructor(readonly apiUrl: string) {}
}
"""
        )
        validator = TypeScriptValidator()
        result = validator.collect_artifacts(str(test_file), "implementation")
        assert "Config" in result["found_classes"]
