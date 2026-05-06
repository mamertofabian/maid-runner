"""Behavioral tests for TypeScript artifact extraction edge cases."""

from __future__ import annotations

from maid_runner.core.types import ArtifactKind
from maid_runner.validators.typescript import TypeScriptValidator


def test_abstract_class_method_signature_is_collected() -> None:
    source = """abstract class BaseService {
  abstract execute(input: Payload): Promise<Result>;
}
"""
    result = TypeScriptValidator().collect_implementation_artifacts(
        source, "src/services/base.ts"
    )

    base = next(a for a in result.artifacts if a.name == "BaseService")
    execute = next(a for a in result.artifacts if a.name == "execute")

    assert base.kind == ArtifactKind.CLASS
    assert execute.kind == ArtifactKind.METHOD
    assert execute.of == "BaseService"
    assert [(arg.name, arg.type, arg.default) for arg in execute.args] == [
        ("input", "Payload", None)
    ]
    assert execute.returns == "Promise<Result>"


def test_constructor_parameter_properties_become_public_attributes() -> None:
    source = """class User {
  constructor(
    public id: string,
    readonly email: string,
    private token: string,
    protected secret: string
  ) {}
}
"""
    result = TypeScriptValidator().collect_implementation_artifacts(
        source, "src/models/user.ts"
    )

    user = next(a for a in result.artifacts if a.name == "User")
    id_attr = next(a for a in result.artifacts if a.name == "id")
    email_attr = next(a for a in result.artifacts if a.name == "email")
    names = {a.name for a in result.artifacts}

    assert user.kind == ArtifactKind.CLASS
    assert id_attr.kind == ArtifactKind.ATTRIBUTE
    assert id_attr.of == "User"
    assert id_attr.type_annotation == "string"
    assert email_attr.kind == ArtifactKind.ATTRIBUTE
    assert email_attr.of == "User"
    assert email_attr.type_annotation == "string"
    assert "constructor" not in names
    assert "token" not in names
    assert "secret" not in names


def test_default_optional_and_rest_parameters_preserve_signature() -> None:
    source = """export function search(
  query: string,
  limit: number = 10,
  filter?: Filter,
  ...sortKeys: string[]
): SearchResult[] {
  return [];
}
"""
    result = TypeScriptValidator().collect_implementation_artifacts(
        source, "src/search.ts"
    )

    search = next(a for a in result.artifacts if a.name == "search")

    assert search.kind == ArtifactKind.FUNCTION
    assert [(arg.name, arg.type, arg.default) for arg in search.args] == [
        ("query", "string", None),
        ("limit", "number", "10"),
        ("filter", "Filter", None),
        ("sortKeys", "string[]", None),
    ]
    assert search.returns == "SearchResult[]"


def test_destructured_parameter_is_not_dropped_from_signature() -> None:
    source = """export function route(
  { id, slug }: RouteParams,
  context: RequestContext
): Response {
  return context.respond(id, slug);
}
"""
    result = TypeScriptValidator().collect_implementation_artifacts(
        source, "src/routes.ts"
    )

    route = next(a for a in result.artifacts if a.name == "route")

    assert route.kind == ArtifactKind.FUNCTION
    assert [(arg.name, arg.type, arg.default) for arg in route.args] == [
        ("{ id, slug }", "RouteParams", None),
        ("context", "RequestContext", None),
    ]
    assert route.returns == "Response"


def test_overload_signatures_are_collected_in_source_order() -> None:
    source = """export function parse(input: string): Parsed;
export function parse(input: Buffer): Parsed;
export function parse(input: string | Buffer): Parsed {
  return normalize(input);
}
"""
    result = TypeScriptValidator().collect_implementation_artifacts(
        source, "src/parse.ts"
    )

    overloads = [a for a in result.artifacts if a.name == "parse"]

    assert [a.kind for a in overloads] == [
        ArtifactKind.FUNCTION,
        ArtifactKind.FUNCTION,
        ArtifactKind.FUNCTION,
    ]
    assert [
        [(arg.name, arg.type, arg.default) for arg in a.args] for a in overloads
    ] == [
        [("input", "string", None)],
        [("input", "Buffer", None)],
        [("input", "string | Buffer", None)],
    ]
    assert [a.returns for a in overloads] == ["Parsed", "Parsed", "Parsed"]
    assert [a.line for a in overloads] == [1, 2, 3]


def test_decorated_class_and_method_are_collected() -> None:
    source = """@sealed
export class Service {
  @trace
  run(input: string): void {}
}
"""
    result = TypeScriptValidator().collect_implementation_artifacts(
        source, "src/service.ts"
    )

    service = next(a for a in result.artifacts if a.name == "Service")
    run = next(a for a in result.artifacts if a.name == "run")

    assert service.kind == ArtifactKind.CLASS
    assert service.line == 2
    assert run.kind == ArtifactKind.METHOD
    assert run.of == "Service"
    assert [(arg.name, arg.type, arg.default) for arg in run.args] == [
        ("input", "string", None)
    ]
    assert run.returns == "void"
    assert run.line == 4


def test_anonymous_default_function_is_collected_as_default() -> None:
    source = """export default function(input: string): Result {
  return make(input);
}
"""
    result = TypeScriptValidator().collect_implementation_artifacts(
        source, "src/default-factory.ts"
    )

    default_export = next(a for a in result.artifacts if a.name == "default")

    assert default_export.kind == ArtifactKind.FUNCTION
    assert [(arg.name, arg.type, arg.default) for arg in default_export.args] == [
        ("input", "string", None)
    ]
    assert default_export.returns == "Result"
    assert default_export.line == 1


def test_anonymous_default_class_is_collected_as_default() -> None:
    source = """export default class {
  render(): void {}
}
"""
    result = TypeScriptValidator().collect_implementation_artifacts(
        source, "src/default-view.ts"
    )

    default_export = next(a for a in result.artifacts if a.name == "default")
    render = next(a for a in result.artifacts if a.name == "render")

    assert default_export.kind == ArtifactKind.CLASS
    assert default_export.line == 1
    assert render.kind == ArtifactKind.METHOD
    assert render.of == "default"
    assert render.returns == "void"


def test_generic_extends_and_implements_bases_preserve_type_arguments() -> None:
    source = """export class Store<T extends Item = Item>
  extends Repository<T>
  implements Cache<T>, Serializable<Record<string, T>> {}
"""
    result = TypeScriptValidator().collect_implementation_artifacts(
        source, "src/store.ts"
    )

    store = next(a for a in result.artifacts if a.name == "Store")

    assert store.kind == ArtifactKind.CLASS
    assert store.bases == (
        "Repository<T>",
        "Cache<T>",
        "Serializable<Record<string, T>>",
    )


def test_computed_class_method_name_is_collected_from_source_text() -> None:
    source = """export class Registry {
  [Symbol.iterator](): Iterator<Item> {
    return items();
  }
}
"""
    result = TypeScriptValidator().collect_implementation_artifacts(
        source, "src/registry.ts"
    )

    iterator = next(a for a in result.artifacts if a.name == "[Symbol.iterator]")

    assert iterator.kind == ArtifactKind.METHOD
    assert iterator.of == "Registry"
    assert iterator.args == ()
    assert iterator.returns == "Iterator<Item>"
    assert iterator.line == 2


def test_type_alias_artifact_preserves_primitive_target() -> None:
    source = "export type UserId = string;\n"
    result = TypeScriptValidator().collect_implementation_artifacts(
        source, "src/types.ts"
    )

    user_id = next(a for a in result.artifacts if a.name == "UserId")

    assert user_id.kind == ArtifactKind.TYPE
    assert user_id.type_annotation == "string"
    assert user_id.line == 1


def test_type_alias_artifact_preserves_complex_target_text() -> None:
    source = """type Lookup = Readonly<Record<string, User | null>>;
"""
    result = TypeScriptValidator().collect_implementation_artifacts(
        source, "src/types.ts"
    )

    lookup = next(a for a in result.artifacts if a.name == "Lookup")

    assert lookup.kind == ArtifactKind.TYPE
    assert lookup.type_annotation == "Readonly<Record<string, User | null>>"
    assert lookup.line == 1
