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
