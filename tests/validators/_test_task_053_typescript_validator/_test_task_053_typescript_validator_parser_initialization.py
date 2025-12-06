from maid_runner.validators.typescript_validator import TypeScriptValidator

# =============================================================================
# SECTION 2.5: Parser Initialization (__init__)
# =============================================================================


class TestParserInitialization:
    """Test parser initialization and language selection."""

    def test_validator_initializes_parsers(self):
        """Must initialize both TypeScript and TSX parsers on instantiation."""
        validator = TypeScriptValidator()
        # Verify that the validator has parsers set up
        # The implementation should create ts_parser and tsx_parser
        assert hasattr(validator, "ts_parser"), "Must have ts_parser attribute"
        assert hasattr(validator, "tsx_parser"), "Must have tsx_parser attribute"
        assert validator.ts_parser is not None
        assert validator.tsx_parser is not None

    def test_validator_initializes_languages(self):
        """Must initialize both TypeScript and TSX language objects."""
        validator = TypeScriptValidator()
        # Verify that the validator has language objects
        assert hasattr(validator, "ts_language"), "Must have ts_language attribute"
        assert hasattr(validator, "tsx_language"), "Must have tsx_language attribute"
        assert validator.ts_language is not None
        assert validator.tsx_language is not None

    def test_parsers_are_different_instances(self):
        """TypeScript and TSX parsers must be separate instances."""
        validator = TypeScriptValidator()
        # ts_parser and tsx_parser should be different objects
        assert validator.ts_parser is not validator.tsx_parser

    def test_parses_valid_typescript(self, tmp_path):
        """Must successfully parse valid TypeScript code without errors."""
        test_file = tmp_path / "valid.ts"
        test_file.write_text(
            """
class Example {
    method(): string {
        return "hello";
    }
}
"""
        )
        validator = TypeScriptValidator()
        # Should not raise any exceptions
        result = validator.collect_artifacts(str(test_file), "implementation")
        # Should find the class
        assert "Example" in result.get("found_classes", set())

    def test_parses_valid_tsx(self, tmp_path):
        """Must successfully parse valid TSX code with JSX syntax."""
        test_file = tmp_path / "component.tsx"
        test_file.write_text(
            """
const MyComponent = () => {
    return <div>Hello</div>;
};
"""
        )
        validator = TypeScriptValidator()
        # Should not raise any exceptions
        result = validator.collect_artifacts(str(test_file), "implementation")
        # Should successfully parse TSX syntax
        assert isinstance(result, dict)

    def test_handles_syntax_errors_gracefully(self, tmp_path):
        """Must handle files with syntax errors without crashing."""
        test_file = tmp_path / "invalid.ts"
        test_file.write_text(
            """
class BrokenClass {
    // Missing closing brace
"""
        )
        validator = TypeScriptValidator()
        # Should not crash, but tree-sitter will produce error nodes
        # The validator should handle this gracefully
        result = validator.collect_artifacts(str(test_file), "implementation")
        assert isinstance(result, dict)

    def test_handles_empty_file(self, tmp_path):
        """Must handle empty TypeScript files without errors."""
        test_file = tmp_path / "empty.ts"
        test_file.write_text("")
        validator = TypeScriptValidator()
        result = validator.collect_artifacts(str(test_file), "implementation")
        assert isinstance(result, dict)
        # Empty file should have no artifacts
        assert len(result.get("found_classes", set())) == 0
        assert len(result.get("found_functions", {})) == 0

    def test_selects_correct_parser_for_ts_file(self, tmp_path):
        """Must use TypeScript parser for .ts files."""
        test_file = tmp_path / "test.ts"
        test_file.write_text("class Test {}")
        validator = TypeScriptValidator()
        # The _get_language_for_file method should return 'typescript'
        lang = validator._get_language_for_file(str(test_file))
        assert lang == "typescript"

    def test_selects_correct_parser_for_tsx_file(self, tmp_path):
        """Must use TSX parser for .tsx files."""
        test_file = tmp_path / "component.tsx"
        test_file.write_text("const C = () => <div />;")
        validator = TypeScriptValidator()
        # The _get_language_for_file method should return 'tsx'
        lang = validator._get_language_for_file(str(test_file))
        assert lang == "tsx"

    def test_selects_correct_parser_for_jsx_file(self, tmp_path):
        """Must use TSX parser for .jsx files."""
        test_file = tmp_path / "component.jsx"
        test_file.write_text("const C = () => <div />;")
        validator = TypeScriptValidator()
        # .jsx files should also use TSX parser
        lang = validator._get_language_for_file(str(test_file))
        assert lang == "tsx"

    def test_selects_correct_parser_for_js_file(self, tmp_path):
        """Must use TypeScript parser for .js files."""
        test_file = tmp_path / "script.js"
        test_file.write_text("function test() {}")
        validator = TypeScriptValidator()
        # .js files should use TypeScript parser (not TSX)
        lang = validator._get_language_for_file(str(test_file))
        assert lang == "typescript"
