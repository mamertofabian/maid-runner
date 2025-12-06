from maid_runner.validators.typescript_validator import TypeScriptValidator

# =============================================================================
# SECTION 6: Enum Detection (_extract_enums)
# =============================================================================


class TestEnumDetection:
    """Test _extract_enums for all enum patterns."""

    def test_numeric_enum(self, tmp_path):
        """Must detect numeric enums."""
        test_file = tmp_path / "test.ts"
        test_file.write_text(
            """
enum Color {
    Red,
    Green,
    Blue
}
"""
        )
        validator = TypeScriptValidator()
        result = validator.collect_artifacts(str(test_file), "implementation")
        assert "Color" in result["found_classes"]

    def test_string_enum(self, tmp_path):
        """Must detect string enums."""
        test_file = tmp_path / "test.ts"
        test_file.write_text(
            """
enum Direction {
    Up = "UP",
    Down = "DOWN",
    Left = "LEFT",
    Right = "RIGHT"
}
"""
        )
        validator = TypeScriptValidator()
        result = validator.collect_artifacts(str(test_file), "implementation")
        assert "Direction" in result["found_classes"]

    def test_const_enum(self, tmp_path):
        """Must detect const enums."""
        test_file = tmp_path / "test.ts"
        test_file.write_text(
            """
const enum HttpStatus {
    OK = 200,
    NotFound = 404,
    ServerError = 500
}
"""
        )
        validator = TypeScriptValidator()
        result = validator.collect_artifacts(str(test_file), "implementation")
        assert "HttpStatus" in result["found_classes"]

    def test_exported_enum(self, tmp_path):
        """Must detect exported enums."""
        test_file = tmp_path / "test.ts"
        test_file.write_text(
            """
export enum LogLevel {
    Debug,
    Info,
    Warning,
    Error
}
"""
        )
        validator = TypeScriptValidator()
        result = validator.collect_artifacts(str(test_file), "implementation")
        assert "LogLevel" in result["found_classes"]

    def test_heterogeneous_enum(self, tmp_path):
        """Must detect heterogeneous enums (mixed string/number)."""
        test_file = tmp_path / "test.ts"
        test_file.write_text(
            """
enum BooleanLikeEnum {
    No = 0,
    Yes = "YES"
}
"""
        )
        validator = TypeScriptValidator()
        result = validator.collect_artifacts(str(test_file), "implementation")
        assert "BooleanLikeEnum" in result["found_classes"]
