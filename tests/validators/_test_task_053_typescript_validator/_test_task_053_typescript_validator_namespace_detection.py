from maid_runner.validators.typescript_validator import TypeScriptValidator

# =============================================================================
# SECTION 7: Namespace Detection (_extract_namespaces)
# =============================================================================


class TestNamespaceDetection:
    """Test _extract_namespaces for namespace patterns."""

    def test_simple_namespace(self, tmp_path):
        """Must detect simple namespace declarations."""
        test_file = tmp_path / "test.ts"
        test_file.write_text(
            """
namespace Validation {
    export function isEmail(s: string): boolean {
        return true;
    }
}
"""
        )
        validator = TypeScriptValidator()
        result = validator.collect_artifacts(str(test_file), "implementation")
        assert "Validation" in result["found_classes"]

    def test_nested_namespace(self, tmp_path):
        """Must detect nested namespaces."""
        test_file = tmp_path / "test.ts"
        test_file.write_text(
            """
namespace App {
    export namespace Utils {
        export function helper() {}
    }
}
"""
        )
        validator = TypeScriptValidator()
        result = validator.collect_artifacts(str(test_file), "implementation")
        assert "App" in result["found_classes"]
        assert "Utils" in result["found_classes"]

    def test_exported_namespace(self, tmp_path):
        """Must detect exported namespaces."""
        test_file = tmp_path / "test.ts"
        test_file.write_text(
            """
export namespace Config {
    export const API_URL = "https://api.example.com";
}
"""
        )
        validator = TypeScriptValidator()
        result = validator.collect_artifacts(str(test_file), "implementation")
        assert "Config" in result["found_classes"]
