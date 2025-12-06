from maid_runner.validators.typescript_validator import TypeScriptValidator

# =============================================================================
# SECTION 8: Function Detection (_extract_functions, _extract_arrow_functions)
# =============================================================================


class TestFunctionDetection:
    """Test _extract_functions and _extract_arrow_functions."""

    def test_simple_function_declaration(self, tmp_path):
        """Must detect simple function declarations."""
        test_file = tmp_path / "test.ts"
        test_file.write_text(
            """
function calculateTotal(a: number, b: number): number {
    return a + b;
}
"""
        )
        validator = TypeScriptValidator()
        result = validator.collect_artifacts(str(test_file), "implementation")
        assert "calculateTotal" in result["found_functions"]
        assert result["found_functions"]["calculateTotal"] == [
            {"name": "a", "type": "number"},
            {"name": "b", "type": "number"},
        ]

    def test_exported_function(self, tmp_path):
        """Must detect exported functions."""
        test_file = tmp_path / "test.ts"
        test_file.write_text(
            """
export function formatDate(date: Date): string {
    return date.toISOString();
}
"""
        )
        validator = TypeScriptValidator()
        result = validator.collect_artifacts(str(test_file), "implementation")
        assert "formatDate" in result["found_functions"]
        assert result["found_functions"]["formatDate"] == [
            {"name": "date", "type": "Date"}
        ]

    def test_async_function(self, tmp_path):
        """Must detect async functions."""
        test_file = tmp_path / "test.ts"
        test_file.write_text(
            """
async function fetchUser(id: number): Promise<User> {
    return await api.get(id);
}
"""
        )
        validator = TypeScriptValidator()
        result = validator.collect_artifacts(str(test_file), "implementation")
        assert "fetchUser" in result["found_functions"]
        assert result["found_functions"]["fetchUser"] == [
            {"name": "id", "type": "number"}
        ]

    def test_generic_function(self, tmp_path):
        """Must detect generic functions."""
        test_file = tmp_path / "test.ts"
        test_file.write_text(
            """
function identity<T>(value: T): T {
    return value;
}
"""
        )
        validator = TypeScriptValidator()
        result = validator.collect_artifacts(str(test_file), "implementation")
        assert "identity" in result["found_functions"]
        assert result["found_functions"]["identity"] == [{"name": "value", "type": "T"}]

    def test_arrow_function_const(self, tmp_path):
        """Must detect arrow functions assigned to const."""
        test_file = tmp_path / "test.ts"
        test_file.write_text(
            """
const add = (x: number, y: number): number => x + y;
"""
        )
        validator = TypeScriptValidator()
        result = validator.collect_artifacts(str(test_file), "implementation")
        assert "add" in result["found_functions"]
        assert result["found_functions"]["add"] == [
            {"name": "x", "type": "number"},
            {"name": "y", "type": "number"},
        ]

    def test_arrow_function_with_block_body(self, tmp_path):
        """Must detect arrow functions with block bodies."""
        test_file = tmp_path / "test.ts"
        test_file.write_text(
            """
const process = (data: string) => {
    console.log(data);
    return data.trim();
};
"""
        )
        validator = TypeScriptValidator()
        result = validator.collect_artifacts(str(test_file), "implementation")
        assert "process" in result["found_functions"]
        assert result["found_functions"]["process"] == [
            {"name": "data", "type": "string"}
        ]

    def test_function_with_no_parameters(self, tmp_path):
        """Must detect functions with no parameters."""
        test_file = tmp_path / "test.ts"
        test_file.write_text(
            """
function getCurrentTimestamp(): number {
    return Date.now();
}
"""
        )
        validator = TypeScriptValidator()
        result = validator.collect_artifacts(str(test_file), "implementation")
        assert "getCurrentTimestamp" in result["found_functions"]
        assert result["found_functions"]["getCurrentTimestamp"] == []

    def test_function_overloads(self, tmp_path):
        """Must detect function overloads (should detect implementation signature)."""
        test_file = tmp_path / "test.ts"
        test_file.write_text(
            """
function process(value: string): string;
function process(value: number): number;
function process(value: any): any {
    return value;
}
"""
        )
        validator = TypeScriptValidator()
        result = validator.collect_artifacts(str(test_file), "implementation")
        assert "process" in result["found_functions"]
