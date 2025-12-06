from maid_runner.validators.typescript_validator import TypeScriptValidator

# =============================================================================
# SECTION 10: Method Detection (_extract_methods, _find_class_methods)
# =============================================================================


class TestMethodDetection:
    """Test _extract_methods and _find_class_methods."""

    def test_regular_methods(self, tmp_path):
        """Must detect regular class methods."""
        test_file = tmp_path / "test.ts"
        test_file.write_text(
            """
class Calculator {
    add(a: number, b: number): number {
        return a + b;
    }

    subtract(a: number, b: number): number {
        return a - b;
    }
}
"""
        )
        validator = TypeScriptValidator()
        result = validator.collect_artifacts(str(test_file), "implementation")
        assert "Calculator" in result["found_methods"]
        assert "add" in result["found_methods"]["Calculator"]
        assert "subtract" in result["found_methods"]["Calculator"]
        assert result["found_methods"]["Calculator"]["add"] == [
            {"name": "a", "type": "number"},
            {"name": "b", "type": "number"},
        ]
        assert result["found_methods"]["Calculator"]["subtract"] == [
            {"name": "a", "type": "number"},
            {"name": "b", "type": "number"},
        ]

    def test_static_methods(self, tmp_path):
        """Must detect static methods."""
        test_file = tmp_path / "test.ts"
        test_file.write_text(
            """
class MathUtils {
    static square(n: number): number {
        return n * n;
    }
}
"""
        )
        validator = TypeScriptValidator()
        result = validator.collect_artifacts(str(test_file), "implementation")
        assert "MathUtils" in result["found_methods"]
        assert "square" in result["found_methods"]["MathUtils"]

    def test_async_methods(self, tmp_path):
        """Must detect async methods."""
        test_file = tmp_path / "test.ts"
        test_file.write_text(
            """
class UserService {
    async fetchUser(id: number): Promise<User> {
        return await api.get(id);
    }
}
"""
        )
        validator = TypeScriptValidator()
        result = validator.collect_artifacts(str(test_file), "implementation")
        assert "UserService" in result["found_methods"]
        assert "fetchUser" in result["found_methods"]["UserService"]

    def test_private_methods(self, tmp_path):
        """Must detect private methods."""
        test_file = tmp_path / "test.ts"
        test_file.write_text(
            """
class DataProcessor {
    private validate(data: any): boolean {
        return true;
    }
}
"""
        )
        validator = TypeScriptValidator()
        result = validator.collect_artifacts(str(test_file), "implementation")
        assert "DataProcessor" in result["found_methods"]
        assert "validate" in result["found_methods"]["DataProcessor"]

    def test_protected_methods(self, tmp_path):
        """Must detect protected methods."""
        test_file = tmp_path / "test.ts"
        test_file.write_text(
            """
class BaseService {
    protected log(message: string): void {
        console.log(message);
    }
}
"""
        )
        validator = TypeScriptValidator()
        result = validator.collect_artifacts(str(test_file), "implementation")
        assert "BaseService" in result["found_methods"]
        assert "log" in result["found_methods"]["BaseService"]

    def test_public_methods(self, tmp_path):
        """Must detect public methods (explicit public modifier)."""
        test_file = tmp_path / "test.ts"
        test_file.write_text(
            """
class Service {
    public execute(): void {}
}
"""
        )
        validator = TypeScriptValidator()
        result = validator.collect_artifacts(str(test_file), "implementation")
        assert "Service" in result["found_methods"]
        assert "execute" in result["found_methods"]["Service"]

    def test_getter_methods(self, tmp_path):
        """Must detect getter methods."""
        test_file = tmp_path / "test.ts"
        test_file.write_text(
            """
class Person {
    private _name: string;

    get name(): string {
        return this._name;
    }
}
"""
        )
        validator = TypeScriptValidator()
        result = validator.collect_artifacts(str(test_file), "implementation")
        assert "Person" in result["found_methods"]
        assert "name" in result["found_methods"]["Person"]

    def test_setter_methods(self, tmp_path):
        """Must detect setter methods."""
        test_file = tmp_path / "test.ts"
        test_file.write_text(
            """
class Person {
    private _name: string;

    set name(value: string) {
        this._name = value;
    }
}
"""
        )
        validator = TypeScriptValidator()
        result = validator.collect_artifacts(str(test_file), "implementation")
        assert "Person" in result["found_methods"]
        assert "name" in result["found_methods"]["Person"]

    def test_abstract_methods(self, tmp_path):
        """Must detect abstract methods in abstract classes."""
        test_file = tmp_path / "test.ts"
        test_file.write_text(
            """
abstract class BaseRepository {
    abstract save(entity: any): void;
    abstract delete(id: number): void;
}
"""
        )
        validator = TypeScriptValidator()
        result = validator.collect_artifacts(str(test_file), "implementation")
        assert "BaseRepository" in result["found_methods"]
        assert "save" in result["found_methods"]["BaseRepository"]
        assert "delete" in result["found_methods"]["BaseRepository"]

    def test_method_with_decorator(self, tmp_path):
        """Must detect methods with decorators."""
        test_file = tmp_path / "test.ts"
        test_file.write_text(
            """
class UserController {
    @Get('/users')
    getUsers() {
        return [];
    }
}
"""
        )
        validator = TypeScriptValidator()
        result = validator.collect_artifacts(str(test_file), "implementation")
        assert "UserController" in result["found_methods"]
        assert "getUsers" in result["found_methods"]["UserController"]

    def test_constructor_not_in_methods(self, tmp_path):
        """Constructor should not be included in methods."""
        test_file = tmp_path / "test.ts"
        test_file.write_text(
            """
class Service {
    constructor(private config: Config) {}

    execute(): void {}
}
"""
        )
        validator = TypeScriptValidator()
        result = validator.collect_artifacts(str(test_file), "implementation")
        assert "Service" in result["found_methods"]
        assert "constructor" not in result["found_methods"]["Service"]
        assert "execute" in result["found_methods"]["Service"]
