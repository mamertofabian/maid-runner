from maid_runner.validators.typescript_validator import TypeScriptValidator

# =============================================================================
# SECTION 12: Behavioral Validation (Usage Detection)
# =============================================================================


class TestBehavioralValidation:
    """Test _extract_class_usage, _extract_function_calls, _extract_method_calls."""

    def test_class_instantiation_detection(self, tmp_path):
        """Must detect class instantiations with 'new' keyword."""
        test_file = tmp_path / "test.ts"
        test_file.write_text(
            """
const service = new UserService();
const calculator = new Calculator();
const processor = new DataProcessor();
"""
        )
        validator = TypeScriptValidator()
        result = validator.collect_artifacts(str(test_file), "behavioral")
        assert "UserService" in result["used_classes"]
        assert "Calculator" in result["used_classes"]
        assert "DataProcessor" in result["used_classes"]

    def test_function_call_detection(self, tmp_path):
        """Must detect function calls."""
        test_file = tmp_path / "test.ts"
        test_file.write_text(
            """
const total = calculateTotal(10, 20);
const formatted = formatDate(new Date());
const user = fetchUser(123);
"""
        )
        validator = TypeScriptValidator()
        result = validator.collect_artifacts(str(test_file), "behavioral")
        assert "calculateTotal" in result["used_functions"]
        assert "formatDate" in result["used_functions"]
        assert "fetchUser" in result["used_functions"]

    def test_method_call_detection(self, tmp_path):
        """Must detect method calls on objects."""
        test_file = tmp_path / "test.ts"
        test_file.write_text(
            """
const service = new UserService();
service.fetchUser(123);
service.updateUser(user);
service.deleteUser(456);
"""
        )
        validator = TypeScriptValidator()
        result = validator.collect_artifacts(str(test_file), "behavioral")
        assert "service" in result["used_methods"]
        assert "fetchUser" in result["used_methods"]["service"]
        assert "updateUser" in result["used_methods"]["service"]
        assert "deleteUser" in result["used_methods"]["service"]

    def test_chained_method_calls(self, tmp_path):
        """Must detect chained method calls."""
        test_file = tmp_path / "test.ts"
        test_file.write_text(
            """
const result = builder
    .setName("test")
    .setAge(25)
    .build();
"""
        )
        validator = TypeScriptValidator()
        result = validator.collect_artifacts(str(test_file), "behavioral")
        assert "builder" in result["used_methods"]
