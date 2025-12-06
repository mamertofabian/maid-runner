from maid_runner.validators.typescript_validator import TypeScriptValidator

# =============================================================================
# SECTION 15: Edge Cases and Error Handling
# =============================================================================


class TestEdgeCases:
    """Test edge cases and error handling."""

    def test_empty_file(self, tmp_path):
        """Must handle empty files gracefully."""
        test_file = tmp_path / "empty.ts"
        test_file.write_text("")
        validator = TypeScriptValidator()
        result = validator.collect_artifacts(str(test_file), "implementation")
        assert isinstance(result, dict)
        assert "found_classes" in result
        assert "found_functions" in result

    def test_file_with_only_comments(self, tmp_path):
        """Must handle files with only comments."""
        test_file = tmp_path / "test.ts"
        test_file.write_text(
            """
// This is a comment
/* This is a block comment */
"""
        )
        validator = TypeScriptValidator()
        result = validator.collect_artifacts(str(test_file), "implementation")
        assert isinstance(result, dict)

    def test_comments_ignored_in_detection(self, tmp_path):
        """Must ignore commented-out code."""
        test_file = tmp_path / "test.ts"
        test_file.write_text(
            """
// class CommentedClass {}
/* function commentedFunction() {} */
class RealClass {}
function realFunction() {}
"""
        )
        validator = TypeScriptValidator()
        result = validator.collect_artifacts(str(test_file), "implementation")
        assert "RealClass" in result["found_classes"]
        assert "realFunction" in result["found_functions"]
        assert "CommentedClass" not in result["found_classes"]
        assert "commentedFunction" not in result["found_functions"]

    def test_unicode_identifiers(self, tmp_path):
        """Must handle Unicode in identifiers."""
        test_file = tmp_path / "test.ts"
        test_file.write_text(
            """
class Привет {}
function 你好() {}
"""
        )
        validator = TypeScriptValidator()
        result = validator.collect_artifacts(str(test_file), "implementation")
        # Should handle or gracefully skip Unicode identifiers
        assert isinstance(result, dict)

    def test_large_file_performance(self, tmp_path):
        """Must handle large files efficiently."""
        test_file = tmp_path / "large.ts"
        # Generate a file with many classes
        classes = "\n".join([f"class Class{i} {{}}" for i in range(100)])
        test_file.write_text(classes)
        validator = TypeScriptValidator()
        result = validator.collect_artifacts(str(test_file), "implementation")
        assert len(result["found_classes"]) == 100

    def test_deeply_nested_structures(self, tmp_path):
        """Must handle deeply nested structures."""
        test_file = tmp_path / "test.ts"
        test_file.write_text(
            """
class Outer {
    static Inner = class {
        static DeepInner = class {
            method() {}
        }
    }
}
"""
        )
        validator = TypeScriptValidator()
        result = validator.collect_artifacts(str(test_file), "implementation")
        assert "Outer" in result["found_classes"]
