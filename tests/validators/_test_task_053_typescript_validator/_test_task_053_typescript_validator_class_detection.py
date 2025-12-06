from maid_runner.validators.typescript_validator import TypeScriptValidator

# =============================================================================
# SECTION 3: Class Detection (_extract_classes)
# =============================================================================


class TestClassDetection:
    """Test _extract_classes for all class patterns."""

    def test_simple_class_declaration(self, tmp_path):
        """Must detect simple class declarations."""
        test_file = tmp_path / "test.ts"
        test_file.write_text(
            """
class UserService {
    constructor() {}
}
"""
        )
        validator = TypeScriptValidator()
        result = validator.collect_artifacts(str(test_file), "implementation")
        assert "UserService" in result["found_classes"]

    def test_exported_class(self, tmp_path):
        """Must detect exported classes."""
        test_file = tmp_path / "test.ts"
        test_file.write_text(
            """
export class AuthService {
    login() {}
}
"""
        )
        validator = TypeScriptValidator()
        result = validator.collect_artifacts(str(test_file), "implementation")
        assert "AuthService" in result["found_classes"]

    def test_default_exported_class(self, tmp_path):
        """Must detect default exported classes."""
        test_file = tmp_path / "test.ts"
        test_file.write_text(
            """
export default class DefaultService {}
"""
        )
        validator = TypeScriptValidator()
        result = validator.collect_artifacts(str(test_file), "implementation")
        assert "DefaultService" in result["found_classes"]

    def test_class_with_inheritance(self, tmp_path):
        """Must detect classes with inheritance (extends)."""
        test_file = tmp_path / "test.ts"
        test_file.write_text(
            """
class BaseService {}
class UserService extends BaseService {}
"""
        )
        validator = TypeScriptValidator()
        result = validator.collect_artifacts(str(test_file), "implementation")
        assert "BaseService" in result["found_classes"]
        assert "UserService" in result["found_classes"]

    def test_abstract_class(self, tmp_path):
        """Must detect abstract classes."""
        test_file = tmp_path / "test.ts"
        test_file.write_text(
            """
abstract class BaseRepository {
    abstract save(): void;
}
"""
        )
        validator = TypeScriptValidator()
        result = validator.collect_artifacts(str(test_file), "implementation")
        assert "BaseRepository" in result["found_classes"]

    def test_generic_class(self, tmp_path):
        """Must detect classes with generic type parameters."""
        test_file = tmp_path / "test.ts"
        test_file.write_text(
            """
class Container<T> {
    value: T;
    constructor(value: T) {
        this.value = value;
    }
}
"""
        )
        validator = TypeScriptValidator()
        result = validator.collect_artifacts(str(test_file), "implementation")
        assert "Container" in result["found_classes"]

    def test_class_with_multiple_generics(self, tmp_path):
        """Must detect classes with multiple generic parameters."""
        test_file = tmp_path / "test.ts"
        test_file.write_text(
            """
class Pair<T, U> {
    first: T;
    second: U;
}
"""
        )
        validator = TypeScriptValidator()
        result = validator.collect_artifacts(str(test_file), "implementation")
        assert "Pair" in result["found_classes"]

    def test_class_with_constrained_generics(self, tmp_path):
        """Must detect classes with generic constraints."""
        test_file = tmp_path / "test.ts"
        test_file.write_text(
            """
class Repository<T extends BaseEntity> {
    save(entity: T): void {}
}
"""
        )
        validator = TypeScriptValidator()
        result = validator.collect_artifacts(str(test_file), "implementation")
        assert "Repository" in result["found_classes"]

    def test_class_with_decorator(self, tmp_path):
        """Must detect classes with decorators."""
        test_file = tmp_path / "test.ts"
        test_file.write_text(
            """
@Component({
    selector: 'app-root'
})
class AppComponent {}
"""
        )
        validator = TypeScriptValidator()
        result = validator.collect_artifacts(str(test_file), "implementation")
        assert "AppComponent" in result["found_classes"]

    def test_multiple_classes_in_file(self, tmp_path):
        """Must detect multiple classes in one file."""
        test_file = tmp_path / "test.ts"
        test_file.write_text(
            """
class ServiceA {}
class ServiceB {}
class ServiceC {}
"""
        )
        validator = TypeScriptValidator()
        result = validator.collect_artifacts(str(test_file), "implementation")
        assert "ServiceA" in result["found_classes"]
        assert "ServiceB" in result["found_classes"]
        assert "ServiceC" in result["found_classes"]
