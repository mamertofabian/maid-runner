from maid_runner.validators.typescript_validator import TypeScriptValidator

# =============================================================================
# SECTION 5: Type Alias Detection (_extract_type_aliases)
# =============================================================================


class TestTypeAliasDetection:
    """Test _extract_type_aliases for all type alias patterns."""

    def test_simple_type_alias(self, tmp_path):
        """Must detect simple type aliases."""
        test_file = tmp_path / "test.ts"
        test_file.write_text(
            """
type UserId = string;
type UserName = string;
"""
        )
        validator = TypeScriptValidator()
        result = validator.collect_artifacts(str(test_file), "implementation")
        assert "UserId" in result["found_classes"]
        assert "UserName" in result["found_classes"]

    def test_object_type_alias(self, tmp_path):
        """Must detect object type aliases."""
        test_file = tmp_path / "test.ts"
        test_file.write_text(
            """
type Point = { x: number; y: number };
"""
        )
        validator = TypeScriptValidator()
        result = validator.collect_artifacts(str(test_file), "implementation")
        assert "Point" in result["found_classes"]

    def test_union_type_alias(self, tmp_path):
        """Must detect union type aliases."""
        test_file = tmp_path / "test.ts"
        test_file.write_text(
            """
type Status = "active" | "inactive" | "pending";
"""
        )
        validator = TypeScriptValidator()
        result = validator.collect_artifacts(str(test_file), "implementation")
        assert "Status" in result["found_classes"]

    def test_intersection_type_alias(self, tmp_path):
        """Must detect intersection type aliases."""
        test_file = tmp_path / "test.ts"
        test_file.write_text(
            """
type Combined = TypeA & TypeB;
"""
        )
        validator = TypeScriptValidator()
        result = validator.collect_artifacts(str(test_file), "implementation")
        assert "Combined" in result["found_classes"]

    def test_generic_type_alias(self, tmp_path):
        """Must detect generic type aliases."""
        test_file = tmp_path / "test.ts"
        test_file.write_text(
            """
type Nullable<T> = T | null;
type ReadonlyArray<T> = readonly T[];
"""
        )
        validator = TypeScriptValidator()
        result = validator.collect_artifacts(str(test_file), "implementation")
        assert "Nullable" in result["found_classes"]
        assert "ReadonlyArray" in result["found_classes"]

    def test_conditional_type_alias(self, tmp_path):
        """Must detect conditional type aliases."""
        test_file = tmp_path / "test.ts"
        test_file.write_text(
            """
type IsString<T> = T extends string ? true : false;
"""
        )
        validator = TypeScriptValidator()
        result = validator.collect_artifacts(str(test_file), "implementation")
        assert "IsString" in result["found_classes"]

    def test_mapped_type_alias(self, tmp_path):
        """Must detect mapped type aliases."""
        test_file = tmp_path / "test.ts"
        test_file.write_text(
            """
type Readonly<T> = { readonly [P in keyof T]: T[P] };
"""
        )
        validator = TypeScriptValidator()
        result = validator.collect_artifacts(str(test_file), "implementation")
        assert "Readonly" in result["found_classes"]

    def test_template_literal_type_alias(self, tmp_path):
        """Must detect template literal type aliases."""
        test_file = tmp_path / "test.ts"
        test_file.write_text(
            """
type EventName = `on${string}`;
"""
        )
        validator = TypeScriptValidator()
        result = validator.collect_artifacts(str(test_file), "implementation")
        assert "EventName" in result["found_classes"]
