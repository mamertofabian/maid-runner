from maid_runner.validators.typescript_validator import TypeScriptValidator

# =============================================================================
# SECTION 4: Interface Detection (_extract_interfaces)
# =============================================================================


class TestInterfaceDetection:
    """Test _extract_interfaces for all interface patterns."""

    def test_simple_interface(self, tmp_path):
        """Must detect simple interface declarations."""
        test_file = tmp_path / "test.ts"
        test_file.write_text(
            """
interface User {
    id: number;
    name: string;
}
"""
        )
        validator = TypeScriptValidator()
        result = validator.collect_artifacts(str(test_file), "implementation")
        assert "User" in result["found_classes"]

    def test_exported_interface(self, tmp_path):
        """Must detect exported interfaces."""
        test_file = tmp_path / "test.ts"
        test_file.write_text(
            """
export interface ApiResponse {
    data: any;
    status: number;
}
"""
        )
        validator = TypeScriptValidator()
        result = validator.collect_artifacts(str(test_file), "implementation")
        assert "ApiResponse" in result["found_classes"]

    def test_interface_with_generics(self, tmp_path):
        """Must detect interfaces with generic type parameters."""
        test_file = tmp_path / "test.ts"
        test_file.write_text(
            """
interface Repository<T> {
    findById(id: number): T;
    save(entity: T): void;
}
"""
        )
        validator = TypeScriptValidator()
        result = validator.collect_artifacts(str(test_file), "implementation")
        assert "Repository" in result["found_classes"]

    def test_interface_with_extends(self, tmp_path):
        """Must detect interfaces with inheritance."""
        test_file = tmp_path / "test.ts"
        test_file.write_text(
            """
interface BaseEntity {
    id: number;
}
interface User extends BaseEntity {
    name: string;
}
"""
        )
        validator = TypeScriptValidator()
        result = validator.collect_artifacts(str(test_file), "implementation")
        assert "BaseEntity" in result["found_classes"]
        assert "User" in result["found_classes"]

    def test_interface_with_index_signature(self, tmp_path):
        """Must detect interfaces with index signatures."""
        test_file = tmp_path / "test.ts"
        test_file.write_text(
            """
interface StringMap {
    [key: string]: string;
}
"""
        )
        validator = TypeScriptValidator()
        result = validator.collect_artifacts(str(test_file), "implementation")
        assert "StringMap" in result["found_classes"]

    def test_interface_with_call_signature(self, tmp_path):
        """Must detect interfaces with call signatures."""
        test_file = tmp_path / "test.ts"
        test_file.write_text(
            """
interface Callable {
    (param: string): number;
}
"""
        )
        validator = TypeScriptValidator()
        result = validator.collect_artifacts(str(test_file), "implementation")
        assert "Callable" in result["found_classes"]
