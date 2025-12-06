from maid_runner.validators.typescript_validator import TypeScriptValidator

# =============================================================================
# SECTION 14: Advanced TypeScript Features
# =============================================================================


class TestAdvancedFeatures:
    """Test advanced TypeScript features and edge cases."""

    def test_multiple_decorators_on_class(self, tmp_path):
        """Must handle multiple decorators on a class."""
        test_file = tmp_path / "test.ts"
        test_file.write_text(
            """
@Injectable()
@Component({
    selector: 'app-root'
})
class AppComponent {}
"""
        )
        validator = TypeScriptValidator()
        result = validator.collect_artifacts(str(test_file), "implementation")
        assert "AppComponent" in result["found_classes"]

    def test_ambient_declarations(self, tmp_path):
        """Must handle ambient declarations (declare keyword)."""
        test_file = tmp_path / "test.d.ts"
        test_file.write_text(
            """
declare class GlobalClass {
    method(): void;
}
declare function globalFunction(): void;
"""
        )
        validator = TypeScriptValidator()
        result = validator.collect_artifacts(str(test_file), "implementation")
        # Should detect ambient declarations
        assert "GlobalClass" in result["found_classes"]
        assert "globalFunction" in result["found_functions"]

    def test_readonly_properties(self, tmp_path):
        """Must handle classes with readonly properties."""
        test_file = tmp_path / "test.ts"
        test_file.write_text(
            """
class Config {
    readonly apiUrl: string;
    readonly timeout: number;
}
"""
        )
        validator = TypeScriptValidator()
        result = validator.collect_artifacts(str(test_file), "implementation")
        assert "Config" in result["found_classes"]

    def test_const_assertions(self, tmp_path):
        """Must handle const assertions."""
        test_file = tmp_path / "test.ts"
        test_file.write_text(
            """
const config = {
    api: "https://api.example.com",
    timeout: 5000
} as const;
"""
        )
        validator = TypeScriptValidator()
        result = validator.collect_artifacts(str(test_file), "implementation")
        # Should parse without errors
        assert isinstance(result, dict)

    def test_satisfies_operator(self, tmp_path):
        """Must handle satisfies operator."""
        test_file = tmp_path / "test.ts"
        test_file.write_text(
            """
const config = {
    api: "https://api.example.com"
} satisfies Config;
"""
        )
        validator = TypeScriptValidator()
        result = validator.collect_artifacts(str(test_file), "implementation")
        # Should parse without errors
        assert isinstance(result, dict)
