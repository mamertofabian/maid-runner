from maid_runner.validators.typescript_validator import TypeScriptValidator

# =============================================================================
# SECTION 2: File Extension Support
# =============================================================================


class TestFileExtensionSupport:
    """Test supports_file for all TypeScript/JavaScript file extensions."""

    def test_supports_typescript_files(self):
        """Must support .ts files."""
        validator = TypeScriptValidator()
        assert validator.supports_file("example.ts") is True
        assert validator.supports_file("/path/to/file.ts") is True

    def test_supports_tsx_files(self):
        """Must support .tsx files (TypeScript + JSX)."""
        validator = TypeScriptValidator()
        assert validator.supports_file("Component.tsx") is True
        assert validator.supports_file("/src/components/App.tsx") is True

    def test_supports_javascript_files(self):
        """Must support .js files."""
        validator = TypeScriptValidator()
        assert validator.supports_file("script.js") is True
        assert validator.supports_file("/lib/utils.js") is True

    def test_supports_jsx_files(self):
        """Must support .jsx files (JavaScript + JSX)."""
        validator = TypeScriptValidator()
        assert validator.supports_file("Component.jsx") is True
        assert validator.supports_file("/components/Header.jsx") is True

    def test_rejects_non_typescript_files(self):
        """Must reject non-TypeScript/JavaScript files."""
        validator = TypeScriptValidator()
        assert validator.supports_file("test.py") is False
        assert validator.supports_file("README.md") is False
        assert validator.supports_file("config.json") is False
        assert validator.supports_file("styles.css") is False
        assert validator.supports_file("test.html") is False
