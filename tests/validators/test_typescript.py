"""Tests for maid_runner.validators.typescript - TypeScriptValidator.

Golden test cases from 15-golden-tests.md section 8 plus edge cases
from tasks 053, 076-078, 153-159.
"""

import pytest

from maid_runner.core.types import ArtifactKind

try:
    from maid_runner.validators.typescript import TypeScriptValidator

    HAS_TREE_SITTER = True
except ImportError:
    HAS_TREE_SITTER = False

pytestmark = pytest.mark.skipif(
    not HAS_TREE_SITTER,
    reason="tree-sitter-typescript not installed",
)


@pytest.fixture()
def validator():
    return TypeScriptValidator()


def _find(artifacts, name, kind=None, of=None):
    for a in artifacts:
        if a.name == name:
            if kind is not None and a.kind != kind:
                continue
            if of is not None and a.of != of:
                continue
            return a
    return None


def _names(artifacts, kind=None, of=None):
    result = set()
    for a in artifacts:
        if kind is not None and a.kind != kind:
            continue
        if of is not None and a.of != of:
            continue
        result.add(a.name)
    return result


# ── Golden Tests (15-golden-tests.md section 8) ──


class TestInterfaceDetection:
    """Golden test 8.1."""

    def test_interface(self, validator):
        source = "interface UserProps {\n  name: string;\n  age: number;\n}\n"
        result = validator.collect_implementation_artifacts(source, "test.ts")
        a = _find(result.artifacts, "UserProps")
        assert a is not None
        assert a.kind == ArtifactKind.INTERFACE


class TestArrowFunction:
    """Golden test 8.2."""

    def test_module_level_arrow(self, validator):
        source = "const greet = (name: string): string => {\n  return `Hello, ${name}!`;\n};\n"
        result = validator.collect_implementation_artifacts(source, "test.ts")
        a = _find(result.artifacts, "greet")
        assert a is not None
        assert a.kind == ArtifactKind.FUNCTION
        assert a.args[0].name == "name"
        assert a.args[0].type == "string"
        assert a.returns == "string"


class TestClassWithMethods:
    """Golden test 8.3."""

    def test_class_and_methods(self, validator):
        source = """class AuthService {
  async login(username: string, password: string): Promise<boolean> {
    return true;
  }
}
"""
        result = validator.collect_implementation_artifacts(source, "test.ts")
        cls = _find(result.artifacts, "AuthService")
        assert cls is not None
        assert cls.kind == ArtifactKind.CLASS

        login = _find(result.artifacts, "login", of="AuthService")
        assert login is not None
        assert login.kind == ArtifactKind.METHOD
        assert login.is_async is True
        assert len(login.args) == 2


class TestPrivateMembers:
    """Golden test 8.4."""

    def test_privacy_detection(self, validator):
        source = """class Foo {
  public bar(): void {}
  private _baz(): void {}
}
"""
        result = validator.collect_implementation_artifacts(source, "test.ts")
        bar = _find(result.artifacts, "bar", of="Foo")
        baz = _find(result.artifacts, "_baz", of="Foo")
        assert bar is not None and bar.is_private is False
        assert baz is not None and baz.is_private is True

    def test_es_private_method(self, validator):
        """#name ES private methods must be collected and marked private."""
        source = """class Foo {
  #secret(): void {}
  public bar(): void {}
}
"""
        result = validator.collect_implementation_artifacts(source, "test.ts")
        bar = _find(result.artifacts, "bar", of="Foo")
        assert bar is not None and bar.is_private is False

        secret = _find(result.artifacts, "#secret", of="Foo")
        assert secret is not None, "ES private #secret method not collected"
        assert secret.kind == ArtifactKind.METHOD
        assert secret.is_private is True


class TestObjectPropertyArrows:
    """Golden test 8.5."""

    def test_not_module_functions(self, validator):
        source = """const config = {
  handler: () => console.log("hi"),
  process: (x: number) => x * 2
};
"""
        result = validator.collect_implementation_artifacts(source, "test.ts")
        # handler and process should NOT be collected as module-level functions
        fns = _names(result.artifacts, kind=ArtifactKind.FUNCTION)
        assert "handler" not in fns
        assert "process" not in fns


class TestEnumDetection:
    """Golden test 8.6."""

    def test_enum(self, validator):
        source = 'enum Direction {\n  Up = "UP",\n  Down = "DOWN"\n}\n'
        result = validator.collect_implementation_artifacts(source, "test.ts")
        a = _find(result.artifacts, "Direction")
        assert a is not None
        assert a.kind == ArtifactKind.ENUM


class TestSupportedExtensions:
    def test_extensions(self):
        assert ".ts" in TypeScriptValidator.supported_extensions()
        assert ".tsx" in TypeScriptValidator.supported_extensions()
        assert ".js" in TypeScriptValidator.supported_extensions()
        assert ".jsx" in TypeScriptValidator.supported_extensions()


# ── Edge Cases from Porting Reference ──


class TestAbstractClass:
    """Abstract classes must be detected."""

    def test_abstract_class_detected(self, validator):
        source = """abstract class BaseService {
  abstract execute(): void;
  getName(): string { return "base"; }
}
"""
        result = validator.collect_implementation_artifacts(source, "test.ts")
        cls = _find(result.artifacts, "BaseService")
        assert cls is not None
        assert cls.kind == ArtifactKind.CLASS


class TestArrowFunctionClassProperties:
    """Arrow functions as class properties (public_field_definition)."""

    def test_arrow_class_property(self, validator):
        source = """class AuthService {
  login = async (username: string, password: string): Promise<boolean> => {
    return true;
  };
}
"""
        result = validator.collect_implementation_artifacts(source, "test.ts")
        login = _find(result.artifacts, "login", of="AuthService")
        assert login is not None
        assert login.kind == ArtifactKind.METHOD
        assert login.is_async is True
        assert len(login.args) == 2
        assert login.args[0].name == "username"


class TestNamespaceDetection:
    """Namespace declarations."""

    def test_namespace(self, validator):
        source = """namespace API {
  export function fetch(url: string): Promise<Response> {
    return Promise.resolve(new Response());
  }
}
"""
        result = validator.collect_implementation_artifacts(source, "test.ts")
        ns = _find(result.artifacts, "API")
        assert ns is not None
        assert ns.kind == ArtifactKind.NAMESPACE


class TestConstructorSkipping:
    """Constructor should not appear as a public method artifact."""

    def test_constructor_not_in_artifacts(self, validator):
        source = """class User {
  constructor(public id: string, private name: string) {}
  greet(): string { return this.name; }
}
"""
        result = validator.collect_implementation_artifacts(source, "test.ts")
        ctor = _find(result.artifacts, "constructor", of="User")
        assert ctor is None
        greet = _find(result.artifacts, "greet", of="User")
        assert greet is not None


class TestGetterSetter:
    """Getters and setters should be detected as attributes."""

    def test_getter_detected(self, validator):
        source = """class User {
  get id(): string { return this._id; }
  set id(value: string) { this._id = value; }
}
"""
        result = validator.collect_implementation_artifacts(source, "test.ts")
        # Getters/setters may be either attributes or methods
        # The key is that "id" is detectable
        names = _names(result.artifacts, of="User")
        assert "id" in names


class TestGeneratorFunctions:
    """Generator functions detection."""

    def test_generator_function(self, validator):
        source = """function* generateNumbers(): Generator<number> {
  yield 1;
  yield 2;
}
"""
        result = validator.collect_implementation_artifacts(source, "test.ts")
        gen = _find(result.artifacts, "generateNumbers")
        assert gen is not None
        assert gen.kind == ArtifactKind.FUNCTION

    def test_async_generator_function(self, validator):
        source = """async function* asyncGen(): AsyncGenerator<number> {
  yield await Promise.resolve(1);
}
"""
        result = validator.collect_implementation_artifacts(source, "test.ts")
        gen = _find(result.artifacts, "asyncGen")
        assert gen is not None
        assert gen.is_async is True


class TestExportStatements:
    """Export declarations should be detected."""

    def test_export_function(self, validator):
        source = "export function greet(name: string): string { return name; }\n"
        result = validator.collect_implementation_artifacts(source, "test.ts")
        a = _find(result.artifacts, "greet")
        assert a is not None
        assert a.kind == ArtifactKind.FUNCTION

    def test_export_class(self, validator):
        source = "export class Service { run(): void {} }\n"
        result = validator.collect_implementation_artifacts(source, "test.ts")
        cls = _find(result.artifacts, "Service")
        assert cls is not None

    def test_export_default_class(self, validator):
        source = "export default class App { render(): void {} }\n"
        result = validator.collect_implementation_artifacts(source, "test.ts")
        cls = _find(result.artifacts, "App")
        assert cls is not None

    def test_export_interface(self, validator):
        source = "export interface Config { debug: boolean; }\n"
        result = validator.collect_implementation_artifacts(source, "test.ts")
        iface = _find(result.artifacts, "Config")
        assert iface is not None
        assert iface.kind == ArtifactKind.INTERFACE

    def test_export_type(self, validator):
        source = "export type UserID = string;\n"
        result = validator.collect_implementation_artifacts(source, "test.ts")
        t = _find(result.artifacts, "UserID")
        assert t is not None
        assert t.kind == ArtifactKind.TYPE


class TestClassInheritance:
    """Class extends/implements should be captured in bases."""

    def test_extends(self, validator):
        source = "class MyService extends BaseService {}\n"
        result = validator.collect_implementation_artifacts(source, "test.ts")
        cls = _find(result.artifacts, "MyService")
        assert cls is not None
        assert "BaseService" in cls.bases

    def test_implements(self, validator):
        source = "class MyService implements IService {}\n"
        result = validator.collect_implementation_artifacts(source, "test.ts")
        cls = _find(result.artifacts, "MyService")
        assert cls is not None
        assert "IService" in cls.bases


class TestInterfaceExtends:
    """Interface extends should be captured in bases."""

    def test_single_extends(self, validator):
        source = "interface Foo extends Bar { name: string; }\n"
        result = validator.collect_implementation_artifacts(source, "test.ts")
        iface = _find(result.artifacts, "Foo")
        assert iface is not None
        assert iface.kind == ArtifactKind.INTERFACE
        assert "Bar" in iface.bases

    def test_multiple_extends(self, validator):
        source = """interface Foo extends Bar, Baz {
  name: string;
}
"""
        result = validator.collect_implementation_artifacts(source, "test.ts")
        iface = _find(result.artifacts, "Foo")
        assert iface is not None
        assert "Bar" in iface.bases
        assert "Baz" in iface.bases


class TestEmptySource:
    """Empty source should produce empty results, no errors."""

    def test_empty_source(self, validator):
        result = validator.collect_implementation_artifacts("", "test.ts")
        assert result.artifacts == []
        assert result.errors == []

    def test_empty_behavioral(self, validator):
        result = validator.collect_behavioral_artifacts("", "test.ts")
        assert result.artifacts == []
        assert result.errors == []


class TestPublicFieldDefinition:
    """Class property declarations (public_field_definition)."""

    def test_class_properties(self, validator):
        source = """class Config {
  readonly debug: boolean = false;
  port: number = 8080;
}
"""
        result = validator.collect_implementation_artifacts(source, "test.ts")
        names = _names(result.artifacts, of="Config")
        assert "debug" in names
        assert "port" in names


class TestInterfaceMembers:
    """Interface members should be extracted as attributes/methods."""

    def test_interface_properties_as_attributes(self, validator):
        source = "interface Todo { id: string; title: string; }\n"
        result = validator.collect_implementation_artifacts(source, "test.ts")

        iface = _find(result.artifacts, "Todo", kind=ArtifactKind.INTERFACE)
        assert iface is not None

        id_attr = _find(result.artifacts, "id", kind=ArtifactKind.ATTRIBUTE, of="Todo")
        assert id_attr is not None
        assert id_attr.type_annotation == "string"

        title_attr = _find(
            result.artifacts, "title", kind=ArtifactKind.ATTRIBUTE, of="Todo"
        )
        assert title_attr is not None
        assert title_attr.type_annotation == "string"

    def test_interface_methods(self, validator):
        source = """interface Service {
  start(): void;
  stop(force: boolean): Promise<void>;
}
"""
        result = validator.collect_implementation_artifacts(source, "test.ts")

        iface = _find(result.artifacts, "Service", kind=ArtifactKind.INTERFACE)
        assert iface is not None

        start = _find(result.artifacts, "start", kind=ArtifactKind.METHOD, of="Service")
        assert start is not None
        assert start.returns == "void"

        stop = _find(result.artifacts, "stop", kind=ArtifactKind.METHOD, of="Service")
        assert stop is not None
        assert len(stop.args) == 1
        assert stop.args[0].name == "force"

    def test_empty_interface_no_members(self, validator):
        source = "interface Empty {}\n"
        result = validator.collect_implementation_artifacts(source, "test.ts")

        iface = _find(result.artifacts, "Empty", kind=ArtifactKind.INTERFACE)
        assert iface is not None

        members = [a for a in result.artifacts if a.of == "Empty"]
        assert members == []

    def test_extending_interface_with_members(self, validator):
        source = """interface Animal extends LivingThing {
  species: string;
  sound(): string;
}
"""
        result = validator.collect_implementation_artifacts(source, "test.ts")

        iface = _find(result.artifacts, "Animal", kind=ArtifactKind.INTERFACE)
        assert iface is not None
        assert "LivingThing" in iface.bases

        species = _find(
            result.artifacts, "species", kind=ArtifactKind.ATTRIBUTE, of="Animal"
        )
        assert species is not None
        assert species.type_annotation == "string"

        sound = _find(result.artifacts, "sound", kind=ArtifactKind.METHOD, of="Animal")
        assert sound is not None


class TestStubDetection:
    """Tests for is_stub detection on TypeScript functions."""

    def test_empty_body_is_stub(self, validator):
        source = "export function foo(): void {}\n"
        result = validator.collect_implementation_artifacts(source, "test.ts")
        a = _find(result.artifacts, "foo")
        assert a is not None
        assert a.is_stub is True

    def test_throw_not_implemented_is_stub(self, validator):
        source = 'function foo(): string { throw new Error("Not implemented"); }\n'
        result = validator.collect_implementation_artifacts(source, "test.ts")
        a = _find(result.artifacts, "foo")
        assert a.is_stub is True

    def test_return_null_is_stub(self, validator):
        source = "function foo(): string | null { return null; }\n"
        result = validator.collect_implementation_artifacts(source, "test.ts")
        a = _find(result.artifacts, "foo")
        assert a.is_stub is True

    def test_return_empty_string_is_stub(self, validator):
        source = 'function foo(): string { return ""; }\n'
        result = validator.collect_implementation_artifacts(source, "test.ts")
        a = _find(result.artifacts, "foo")
        assert a.is_stub is True

    def test_return_zero_is_stub(self, validator):
        source = "function foo(): number { return 0; }\n"
        result = validator.collect_implementation_artifacts(source, "test.ts")
        a = _find(result.artifacts, "foo")
        assert a.is_stub is True

    def test_return_empty_object_is_stub(self, validator):
        source = "function foo(): object { return {}; }\n"
        result = validator.collect_implementation_artifacts(source, "test.ts")
        a = _find(result.artifacts, "foo")
        assert a.is_stub is True

    def test_return_empty_array_is_stub(self, validator):
        source = "function foo(): string[] { return []; }\n"
        result = validator.collect_implementation_artifacts(source, "test.ts")
        a = _find(result.artifacts, "foo")
        assert a.is_stub is True

    def test_real_function_not_stub(self, validator):
        source = "function greet(name: string): string { return `Hello, ${name}!`; }\n"
        result = validator.collect_implementation_artifacts(source, "test.ts")
        a = _find(result.artifacts, "greet")
        assert a.is_stub is False

    def test_multi_statement_not_stub(self, validator):
        source = "function foo(): number { const x = 1; return x + 1; }\n"
        result = validator.collect_implementation_artifacts(source, "test.ts")
        a = _find(result.artifacts, "foo")
        assert a.is_stub is False

    def test_arrow_function_stub(self, validator):
        source = "export const foo = (): void => {};\n"
        result = validator.collect_implementation_artifacts(source, "test.ts")
        a = _find(result.artifacts, "foo")
        assert a is not None
        assert a.is_stub is True

    def test_arrow_function_real(self, validator):
        source = (
            "export const add = (a: number, b: number): number => { return a + b; };\n"
        )
        result = validator.collect_implementation_artifacts(source, "test.ts")
        a = _find(result.artifacts, "add")
        assert a.is_stub is False

    def test_class_method_stub(self, validator):
        source = "class Foo {\n  bar(): void {}\n}\n"
        result = validator.collect_implementation_artifacts(source, "test.ts")
        a = _find(result.artifacts, "bar", kind=ArtifactKind.METHOD, of="Foo")
        assert a is not None
        assert a.is_stub is True

    def test_class_method_real(self, validator):
        source = 'class Foo {\n  bar(): string { return "hello"; }\n}\n'
        result = validator.collect_implementation_artifacts(source, "test.ts")
        a = _find(result.artifacts, "bar", kind=ArtifactKind.METHOD, of="Foo")
        # Single return with literal is a stub
        assert a.is_stub is True

    def test_class_method_with_logic(self, validator):
        source = "class Foo {\n  bar(x: number): number { const y = x * 2; return y + 1; }\n}\n"
        result = validator.collect_implementation_artifacts(source, "test.ts")
        a = _find(result.artifacts, "bar", kind=ArtifactKind.METHOD, of="Foo")
        assert a.is_stub is False


class TestTypeScriptArrowFunctions:
    def test_arrow_expression_body_detected(self, validator):
        """Arrow function with expression body (no braces) collected."""
        source = "export const add = (a: number, b: number): number => a + b;\n"
        result = validator.collect_implementation_artifacts(source, "math.ts")
        names = {a.name for a in result.artifacts}
        assert "add" in names

    def test_arrow_expression_body_is_function_kind(self, validator):
        """Arrow function with expression body has FUNCTION kind."""
        source = "export const double = (x: number): number => x * 2;\n"
        result = validator.collect_implementation_artifacts(source, "math.ts")
        a = _find(result.artifacts, "double")
        assert a is not None
        assert a.kind == ArtifactKind.FUNCTION

    def test_arrow_expression_body_args(self, validator):
        """Arrow function with expression body has correct args."""
        source = "export const greet = (name: string): string => `Hello, ${name}!`;\n"
        result = validator.collect_implementation_artifacts(source, "math.ts")
        a = _find(result.artifacts, "greet")
        assert a is not None
        assert len(a.args) == 1
        assert a.args[0].name == "name"
        assert a.args[0].type == "string"


class TestTypeScriptTemplateStringStub:
    def test_template_string_with_substitution_not_stub(self, validator):
        """Template string with substitution is not a stub."""
        source = "function greet(name: string): string { return `Hello, ${name}!`; }\n"
        result = validator.collect_implementation_artifacts(source, "test.ts")
        a = _find(result.artifacts, "greet")
        assert a is not None
        assert a.is_stub is False

    def test_template_string_without_substitution_is_stub(self, validator):
        """Plain template string (no substitution) is a stub."""
        source = "function foo(): string { return ``; }\n"
        result = validator.collect_implementation_artifacts(source, "test.ts")
        a = _find(result.artifacts, "foo")
        assert a is not None
        assert a.is_stub is True
