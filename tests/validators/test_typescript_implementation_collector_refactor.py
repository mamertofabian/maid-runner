"""Characterization coverage for TypeScript implementation artifact collection."""

from __future__ import annotations

from maid_runner.core.types import ArtifactKind
from maid_runner.validators.typescript import TypeScriptValidator


def _artifact(result, name: str, kind: ArtifactKind | None = None):
    for artifact in result.artifacts:
        if artifact.name != name:
            continue
        if kind is not None and artifact.kind != kind:
            continue
        return artifact
    raise AssertionError(f"Artifact {name!r} not found in {result.artifacts!r}")


def test_implementation_collector_preserves_class_method_and_field_artifacts() -> None:
    source = """export class Store<T extends Item = Item> extends Repository<T> {
  readonly count: number = 0;

  async load(id: string): Promise<T> {
    return this.fetch(id);
  }
}
"""
    result = TypeScriptValidator().collect_implementation_artifacts(
        source, "src/store.ts"
    )

    store = _artifact(result, "Store", ArtifactKind.CLASS)
    count = _artifact(result, "count", ArtifactKind.ATTRIBUTE)
    load = _artifact(result, "load", ArtifactKind.METHOD)

    assert result.errors == []
    assert store.bases == ("Repository<T>",)
    assert store.type_parameters == ("T extends Item = Item",)
    assert store.module_path == "src/store"
    assert count.of == "Store"
    assert count.type_annotation == "number"
    assert count.line == 2
    assert load.of == "Store"
    assert [(arg.name, arg.type, arg.default) for arg in load.args] == [
        ("id", "string", None)
    ]
    assert load.returns == "Promise<T>"
    assert load.is_async is True
    assert load.line == 4


def test_implementation_collector_preserves_interface_members_and_type_aliases() -> (
    None
):
    source = """export interface Repository<T> extends Readable {
  readonly id: string;
  find(id: string): Promise<T>;
}

export type Lookup<T = Item> = Readonly<Record<string, T>>;
"""
    result = TypeScriptValidator().collect_implementation_artifacts(
        source, "src/contracts.ts"
    )

    repository = _artifact(result, "Repository", ArtifactKind.INTERFACE)
    id_attr = _artifact(result, "id", ArtifactKind.ATTRIBUTE)
    find = _artifact(result, "find", ArtifactKind.METHOD)
    lookup = _artifact(result, "Lookup", ArtifactKind.TYPE)

    assert result.errors == []
    assert repository.bases == ("Readable",)
    assert repository.type_parameters == ("T",)
    assert id_attr.of == "Repository"
    assert id_attr.type_annotation == "string"
    assert find.of == "Repository"
    assert [(arg.name, arg.type, arg.default) for arg in find.args] == [
        ("id", "string", None)
    ]
    assert find.returns == "Promise<T>"
    assert lookup.type_parameters == ("T = Item",)
    assert lookup.type_annotation == "Readonly<Record<string, T>>"
    assert lookup.module_path == "src/contracts"


def test_implementation_collector_preserves_react_wrapped_component_signature() -> None:
    source = """import React from 'react';

export type InputProps = { value: string };

export const TextInput = React.forwardRef<HTMLInputElement, InputProps>(
  (props: InputProps, ref: React.Ref<HTMLInputElement>): JSX.Element => {
    return <input ref={ref} value={props.value} />;
  }
);
"""
    result = TypeScriptValidator().collect_implementation_artifacts(
        source, "src/components/TextInput.tsx"
    )

    component = _artifact(result, "TextInput", ArtifactKind.FUNCTION)

    assert result.errors == []
    assert [(arg.name, arg.type, arg.default) for arg in component.args] == [
        ("props", "InputProps", None),
        ("ref", "React.Ref<HTMLInputElement>", None),
    ]
    assert component.returns == "JSX.Element"
    assert component.module_path == "src/components/TextInput"


def test_implementation_collector_preserves_constructor_parameter_properties() -> None:
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

    names = {artifact.name for artifact in result.artifacts}
    id_attr = _artifact(result, "id", ArtifactKind.ATTRIBUTE)
    email_attr = _artifact(result, "email", ArtifactKind.ATTRIBUTE)

    assert "constructor" not in names
    assert "token" not in names
    assert "secret" not in names
    assert id_attr.of == "User"
    assert id_attr.type_annotation == "string"
    assert id_attr.line == 3
    assert email_attr.of == "User"
    assert email_attr.type_annotation == "string"
    assert email_attr.line == 4
