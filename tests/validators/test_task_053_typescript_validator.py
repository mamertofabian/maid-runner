"""Comprehensive behavioral tests for Task-053: Production-ready TypeScriptValidator.

This test suite validates all 36 expected artifacts in the manifest, ensuring complete
coverage of TypeScript/JavaScript language features using tree-sitter AST parsing.

Test Organization:
- Basic validator structure and interface compliance
- Core TypeScript declarations (classes, interfaces, type aliases, enums, namespaces)
- Functions (regular, arrow, async, generic)
- Methods (regular, static, private, async, getters/setters, abstract)
- Parameters (required, optional, rest, destructured, parameter properties)
- Advanced features (decorators, generics, abstract classes, access modifiers)
- JSX/TSX support for React
- Behavioral validation (class/function/method usage)
- Edge cases and real-world patterns
- Artifact structure consistency
"""

from maid_runner.validators.typescript_validator import TypeScriptValidator
from maid_runner.validators.base_validator import BaseValidator


# =============================================================================
# SECTION 1: Validator Structure and Interface Compliance
# =============================================================================


class TestValidatorStructure:
    """Test TypeScriptValidator class structure and BaseValidator compliance."""

    def test_validator_class_exists(self):
        """TypeScriptValidator class must exist."""
        assert TypeScriptValidator is not None

    def test_validator_inherits_from_base(self):
        """TypeScriptValidator must inherit from BaseValidator."""
        assert issubclass(TypeScriptValidator, BaseValidator)

    def test_validator_can_be_instantiated(self):
        """TypeScriptValidator must be instantiable."""
        validator = TypeScriptValidator()
        assert validator is not None
        assert isinstance(validator, BaseValidator)

    def test_supports_file_method_exists(self):
        """supports_file method must exist and return bool."""
        validator = TypeScriptValidator()
        result = validator.supports_file("test.ts")
        assert isinstance(result, bool)

    def test_collect_artifacts_method_exists(self, tmp_path):
        """collect_artifacts method must exist and return dict."""
        test_file = tmp_path / "test.ts"
        test_file.write_text("class Test {}")
        validator = TypeScriptValidator()
        result = validator.collect_artifacts(str(test_file), "implementation")
        assert isinstance(result, dict)


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


# =============================================================================
# SECTION 6: Enum Detection (_extract_enums)
# =============================================================================


class TestEnumDetection:
    """Test _extract_enums for all enum patterns."""

    def test_numeric_enum(self, tmp_path):
        """Must detect numeric enums."""
        test_file = tmp_path / "test.ts"
        test_file.write_text(
            """
enum Color {
    Red,
    Green,
    Blue
}
"""
        )
        validator = TypeScriptValidator()
        result = validator.collect_artifacts(str(test_file), "implementation")
        assert "Color" in result["found_classes"]

    def test_string_enum(self, tmp_path):
        """Must detect string enums."""
        test_file = tmp_path / "test.ts"
        test_file.write_text(
            """
enum Direction {
    Up = "UP",
    Down = "DOWN",
    Left = "LEFT",
    Right = "RIGHT"
}
"""
        )
        validator = TypeScriptValidator()
        result = validator.collect_artifacts(str(test_file), "implementation")
        assert "Direction" in result["found_classes"]

    def test_const_enum(self, tmp_path):
        """Must detect const enums."""
        test_file = tmp_path / "test.ts"
        test_file.write_text(
            """
const enum HttpStatus {
    OK = 200,
    NotFound = 404,
    ServerError = 500
}
"""
        )
        validator = TypeScriptValidator()
        result = validator.collect_artifacts(str(test_file), "implementation")
        assert "HttpStatus" in result["found_classes"]

    def test_exported_enum(self, tmp_path):
        """Must detect exported enums."""
        test_file = tmp_path / "test.ts"
        test_file.write_text(
            """
export enum LogLevel {
    Debug,
    Info,
    Warning,
    Error
}
"""
        )
        validator = TypeScriptValidator()
        result = validator.collect_artifacts(str(test_file), "implementation")
        assert "LogLevel" in result["found_classes"]

    def test_heterogeneous_enum(self, tmp_path):
        """Must detect heterogeneous enums (mixed string/number)."""
        test_file = tmp_path / "test.ts"
        test_file.write_text(
            """
enum BooleanLikeEnum {
    No = 0,
    Yes = "YES"
}
"""
        )
        validator = TypeScriptValidator()
        result = validator.collect_artifacts(str(test_file), "implementation")
        assert "BooleanLikeEnum" in result["found_classes"]


# =============================================================================
# SECTION 7: Namespace Detection (_extract_namespaces)
# =============================================================================


class TestNamespaceDetection:
    """Test _extract_namespaces for namespace patterns."""

    def test_simple_namespace(self, tmp_path):
        """Must detect simple namespace declarations."""
        test_file = tmp_path / "test.ts"
        test_file.write_text(
            """
namespace Validation {
    export function isEmail(s: string): boolean {
        return true;
    }
}
"""
        )
        validator = TypeScriptValidator()
        result = validator.collect_artifacts(str(test_file), "implementation")
        assert "Validation" in result["found_classes"]

    def test_nested_namespace(self, tmp_path):
        """Must detect nested namespaces."""
        test_file = tmp_path / "test.ts"
        test_file.write_text(
            """
namespace App {
    export namespace Utils {
        export function helper() {}
    }
}
"""
        )
        validator = TypeScriptValidator()
        result = validator.collect_artifacts(str(test_file), "implementation")
        assert "App" in result["found_classes"]
        assert "Utils" in result["found_classes"]

    def test_exported_namespace(self, tmp_path):
        """Must detect exported namespaces."""
        test_file = tmp_path / "test.ts"
        test_file.write_text(
            """
export namespace Config {
    export const API_URL = "https://api.example.com";
}
"""
        )
        validator = TypeScriptValidator()
        result = validator.collect_artifacts(str(test_file), "implementation")
        assert "Config" in result["found_classes"]


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
        assert result["found_functions"]["calculateTotal"] == ["a", "b"]

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
        assert result["found_functions"]["formatDate"] == ["date"]

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
        assert result["found_functions"]["fetchUser"] == ["id"]

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
        assert result["found_functions"]["identity"] == ["value"]

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
        assert result["found_functions"]["add"] == ["x", "y"]

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
        assert result["found_functions"]["process"] == ["data"]

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


# =============================================================================
# SECTION 9: Parameter Detection (_extract_parameters)
# =============================================================================


class TestParameterDetection:
    """Test _extract_parameters for all parameter patterns."""

    def test_required_parameters(self, tmp_path):
        """Must extract required parameters."""
        test_file = tmp_path / "test.ts"
        test_file.write_text(
            """
function greet(name: string, age: number): string {
    return `Hello ${name}, you are ${age}`;
}
"""
        )
        validator = TypeScriptValidator()
        result = validator.collect_artifacts(str(test_file), "implementation")
        assert result["found_functions"]["greet"] == ["name", "age"]

    def test_optional_parameters(self, tmp_path):
        """Must extract optional parameters."""
        test_file = tmp_path / "test.ts"
        test_file.write_text(
            """
function greet(name: string, title?: string): string {
    return title ? `${title} ${name}` : name;
}
"""
        )
        validator = TypeScriptValidator()
        result = validator.collect_artifacts(str(test_file), "implementation")
        assert "name" in result["found_functions"]["greet"]
        assert "title" in result["found_functions"]["greet"]

    def test_rest_parameters(self, tmp_path):
        """Must extract rest parameters."""
        test_file = tmp_path / "test.ts"
        test_file.write_text(
            """
function sum(...numbers: number[]): number {
    return numbers.reduce((a, b) => a + b, 0);
}
"""
        )
        validator = TypeScriptValidator()
        result = validator.collect_artifacts(str(test_file), "implementation")
        assert "numbers" in result["found_functions"]["sum"]

    def test_default_parameters(self, tmp_path):
        """Must extract parameters with default values."""
        test_file = tmp_path / "test.ts"
        test_file.write_text(
            """
function createUser(name: string, role = "user"): void {}
"""
        )
        validator = TypeScriptValidator()
        result = validator.collect_artifacts(str(test_file), "implementation")
        assert "name" in result["found_functions"]["createUser"]
        assert "role" in result["found_functions"]["createUser"]

    def test_destructured_object_parameters(self, tmp_path):
        """Must handle destructured object parameters."""
        test_file = tmp_path / "test.ts"
        test_file.write_text(
            """
function greet({ name, age }: { name: string, age: number }): string {
    return `${name} is ${age}`;
}
"""
        )
        validator = TypeScriptValidator()
        result = validator.collect_artifacts(str(test_file), "implementation")
        # Should detect the destructured parameter pattern
        assert "greet" in result["found_functions"]

    def test_destructured_array_parameters(self, tmp_path):
        """Must handle destructured array parameters."""
        test_file = tmp_path / "test.ts"
        test_file.write_text(
            """
function process([first, second]: [string, number]): void {}
"""
        )
        validator = TypeScriptValidator()
        result = validator.collect_artifacts(str(test_file), "implementation")
        assert "process" in result["found_functions"]


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
        assert result["found_methods"]["Calculator"]["add"] == ["a", "b"]
        assert result["found_methods"]["Calculator"]["subtract"] == ["a", "b"]

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


# =============================================================================
# SECTION 11: Parameter Properties
# =============================================================================


class TestParameterProperties:
    """Test detection of parameter properties (constructor parameters that create class properties)."""

    def test_public_parameter_property(self, tmp_path):
        """Must handle public parameter properties."""
        test_file = tmp_path / "test.ts"
        test_file.write_text(
            """
class User {
    constructor(public name: string, public age: number) {}
}
"""
        )
        validator = TypeScriptValidator()
        result = validator.collect_artifacts(str(test_file), "implementation")
        assert "User" in result["found_classes"]

    def test_private_parameter_property(self, tmp_path):
        """Must handle private parameter properties."""
        test_file = tmp_path / "test.ts"
        test_file.write_text(
            """
class Service {
    constructor(private config: Config) {}
}
"""
        )
        validator = TypeScriptValidator()
        result = validator.collect_artifacts(str(test_file), "implementation")
        assert "Service" in result["found_classes"]

    def test_readonly_parameter_property(self, tmp_path):
        """Must handle readonly parameter properties."""
        test_file = tmp_path / "test.ts"
        test_file.write_text(
            """
class Config {
    constructor(readonly apiUrl: string) {}
}
"""
        )
        validator = TypeScriptValidator()
        result = validator.collect_artifacts(str(test_file), "implementation")
        assert "Config" in result["found_classes"]


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


# =============================================================================
# SECTION 13: JSX/TSX Support
# =============================================================================


class TestJSXTSXSupport:
    """Test JSX/TSX file handling for React components."""

    def test_react_class_component(self, tmp_path):
        """Must detect React class components."""
        test_file = tmp_path / "Component.tsx"
        test_file.write_text(
            """
class MyComponent extends React.Component {
    render() {
        return <div>Hello</div>;
    }
}
"""
        )
        validator = TypeScriptValidator()
        result = validator.collect_artifacts(str(test_file), "implementation")
        assert "MyComponent" in result["found_classes"]
        assert "MyComponent" in result["found_methods"]
        assert "render" in result["found_methods"]["MyComponent"]

    def test_react_functional_component(self, tmp_path):
        """Must detect React functional components."""
        test_file = tmp_path / "Component.tsx"
        test_file.write_text(
            """
const MyComponent = () => {
    return <div>Hello</div>;
};
"""
        )
        validator = TypeScriptValidator()
        result = validator.collect_artifacts(str(test_file), "implementation")
        assert "MyComponent" in result["found_functions"]

    def test_react_functional_component_with_props(self, tmp_path):
        """Must detect React functional components with props."""
        test_file = tmp_path / "Component.tsx"
        test_file.write_text(
            """
const Greeting = (props: { name: string }) => {
    return <div>Hello {props.name}</div>;
};
"""
        )
        validator = TypeScriptValidator()
        result = validator.collect_artifacts(str(test_file), "implementation")
        assert "Greeting" in result["found_functions"]

    def test_react_component_with_hooks(self, tmp_path):
        """Must detect React components using hooks."""
        test_file = tmp_path / "Component.tsx"
        test_file.write_text(
            """
const Counter = () => {
    const [count, setCount] = useState(0);
    return <button onClick={() => setCount(count + 1)}>{count}</button>;
};
"""
        )
        validator = TypeScriptValidator()
        result = validator.collect_artifacts(str(test_file), "implementation")
        assert "Counter" in result["found_functions"]


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


# =============================================================================
# SECTION 16: Artifact Structure Consistency
# =============================================================================


class TestArtifactStructure:
    """Test that collected artifacts have consistent structure."""

    def test_implementation_mode_structure(self, tmp_path):
        """Implementation mode must return all required keys."""
        test_file = tmp_path / "test.ts"
        test_file.write_text(
            """
class TestClass {
    method() {}
}
function testFunc() {}
"""
        )
        validator = TypeScriptValidator()
        result = validator.collect_artifacts(str(test_file), "implementation")

        # Must have all required keys
        required_keys = [
            "found_classes",
            "found_functions",
            "found_methods",
            "found_class_bases",
            "found_attributes",
            "variable_to_class",
            "found_function_types",
            "found_method_types",
            "used_classes",
            "used_functions",
            "used_methods",
            "used_arguments",
        ]
        for key in required_keys:
            assert key in result, f"Missing required key: {key}"

        # Check types
        assert isinstance(result["found_classes"], set)
        assert isinstance(result["found_functions"], dict)
        assert isinstance(result["found_methods"], dict)
        assert isinstance(result["used_classes"], set)
        assert isinstance(result["used_functions"], set)
        assert isinstance(result["used_methods"], dict)

    def test_behavioral_mode_structure(self, tmp_path):
        """Behavioral mode must return all required keys."""
        test_file = tmp_path / "test.ts"
        test_file.write_text(
            """
const obj = new TestClass();
obj.method();
testFunc();
"""
        )
        validator = TypeScriptValidator()
        result = validator.collect_artifacts(str(test_file), "behavioral")

        # Must have all required keys
        assert "used_classes" in result
        assert "used_functions" in result
        assert "used_methods" in result

        # Check types
        assert isinstance(result["used_classes"], set)
        assert isinstance(result["used_functions"], set)
        assert isinstance(result["used_methods"], dict)

    def test_method_parameters_are_lists(self, tmp_path):
        """Method parameters must be returned as lists."""
        test_file = tmp_path / "test.ts"
        test_file.write_text(
            """
class Service {
    process(a: string, b: number): void {}
}
"""
        )
        validator = TypeScriptValidator()
        result = validator.collect_artifacts(str(test_file), "implementation")
        assert isinstance(result["found_methods"]["Service"]["process"], list)
        assert result["found_methods"]["Service"]["process"] == ["a", "b"]

    def test_function_parameters_are_lists(self, tmp_path):
        """Function parameters must be returned as lists."""
        test_file = tmp_path / "test.ts"
        test_file.write_text(
            """
function process(x: number, y: string): void {}
"""
        )
        validator = TypeScriptValidator()
        result = validator.collect_artifacts(str(test_file), "implementation")
        assert isinstance(result["found_functions"]["process"], list)
        assert result["found_functions"]["process"] == ["x", "y"]


# =============================================================================
# SECTION 17: Real-World Framework Patterns
# =============================================================================


class TestFrameworkPatterns:
    """Test patterns from real-world TypeScript frameworks."""

    def test_angular_component_pattern(self, tmp_path):
        """Must detect Angular component pattern."""
        test_file = tmp_path / "app.component.ts"
        test_file.write_text(
            """
@Component({
    selector: 'app-root',
    templateUrl: './app.component.html',
    styleUrls: ['./app.component.css']
})
export class AppComponent {
    title = 'my-app';

    ngOnInit() {
        console.log('Initialized');
    }
}
"""
        )
        validator = TypeScriptValidator()
        result = validator.collect_artifacts(str(test_file), "implementation")
        assert "AppComponent" in result["found_classes"]
        assert "ngOnInit" in result["found_methods"]["AppComponent"]

    def test_nestjs_controller_pattern(self, tmp_path):
        """Must detect NestJS controller pattern."""
        test_file = tmp_path / "users.controller.ts"
        test_file.write_text(
            """
@Controller('users')
export class UsersController {
    @Get()
    findAll() {
        return [];
    }

    @Post()
    create(@Body() createUserDto: CreateUserDto) {
        return {};
    }
}
"""
        )
        validator = TypeScriptValidator()
        result = validator.collect_artifacts(str(test_file), "implementation")
        assert "UsersController" in result["found_classes"]
        assert "findAll" in result["found_methods"]["UsersController"]
        assert "create" in result["found_methods"]["UsersController"]

    def test_vue_component_pattern(self, tmp_path):
        """Must detect Vue component pattern."""
        test_file = tmp_path / "MyComponent.vue.ts"
        test_file.write_text(
            """
@Component
export default class MyComponent extends Vue {
    private message: string = 'Hello';

    mounted() {
        console.log('Mounted');
    }
}
"""
        )
        validator = TypeScriptValidator()
        result = validator.collect_artifacts(str(test_file), "implementation")
        assert "MyComponent" in result["found_classes"]
        assert "mounted" in result["found_methods"]["MyComponent"]
