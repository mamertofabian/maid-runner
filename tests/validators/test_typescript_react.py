"""React TSX artifact characterization tests."""

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


def test_react_function_component_preserves_props_interface_and_signature() -> None:
    source = """import React from 'react';

export interface ButtonProps {
  label: string;
  disabled?: boolean;
}

export function Button(props: ButtonProps): JSX.Element {
  return <button disabled={props.disabled}>{props.label}</button>;
}
"""

    result = TypeScriptValidator().collect_implementation_artifacts(
        source, "src/components/Button.tsx"
    )
    names = {artifact.name for artifact in result.artifacts}

    props = _artifact(result, "ButtonProps", ArtifactKind.INTERFACE)
    button = _artifact(result, "Button", ArtifactKind.FUNCTION)

    assert result.errors == []
    assert props.kind == ArtifactKind.INTERFACE
    assert button.args[0].name == "props"
    assert button.args[0].type == "ButtonProps"
    assert button.returns == "JSX.Element"
    assert "button" not in names
    assert "disabled" in names


def test_react_fc_typed_const_component_preserves_props_type_and_function_artifact() -> (
    None
):
    source = """import type { FC } from 'react';

export type BadgeProps = {
  tone: 'info' | 'critical';
};

export const Badge: FC<BadgeProps> = ({ tone }) => {
  return <span data-tone={tone}>{tone}</span>;
};
"""

    result = TypeScriptValidator().collect_implementation_artifacts(
        source, "src/components/Badge.tsx"
    )
    names = {artifact.name for artifact in result.artifacts}

    badge = _artifact(result, "Badge", ArtifactKind.FUNCTION)
    props = _artifact(result, "BadgeProps", ArtifactKind.TYPE)

    assert result.errors == []
    assert badge.kind == ArtifactKind.FUNCTION
    assert props.type_annotation == "{\n  tone: 'info' | 'critical';\n}"
    assert "span" not in names
    assert "data-tone" not in names


def test_react_hook_and_provider_exports_remain_plain_typescript_functions() -> None:
    source = """import { createContext, useContext } from 'react';

export type Session = { userId: string };
export const SessionContext = createContext<Session | null>(null);

export function useSession(): Session {
  const session = useContext(SessionContext);
  if (!session) {
    throw new Error('missing session');
  }
  return session;
}

export function SessionProvider(props: { children: React.ReactNode }): JSX.Element {
  return <SessionContext.Provider value={{ userId: '42' }}>{props.children}</SessionContext.Provider>;
}
"""

    result = TypeScriptValidator().collect_implementation_artifacts(
        source, "src/session/SessionProvider.tsx"
    )

    assert result.errors == []
    assert _artifact(result, "useSession", ArtifactKind.FUNCTION).returns == "Session"
    assert (
        _artifact(result, "SessionProvider", ArtifactKind.FUNCTION).returns
        == "JSX.Element"
    )
    assert _artifact(result, "SessionContext", ArtifactKind.ATTRIBUTE)


def test_jsx_intrinsic_tags_and_attributes_do_not_become_implementation_artifacts() -> (
    None
):
    source = """export function Toolbar(): JSX.Element {
  return (
    <nav aria-label="Primary">
      <button type="button" data-testid="save">Save</button>
    </nav>
  );
}
"""

    result = TypeScriptValidator().collect_implementation_artifacts(
        source, "src/components/Toolbar.tsx"
    )
    names = {artifact.name for artifact in result.artifacts}

    assert result.errors == []
    assert "Toolbar" in names
    assert {"nav", "button", "aria-label", "data-testid", "type"}.isdisjoint(names)


def test_react_forward_ref_const_export_is_collected_as_function_component() -> None:
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
    assert component.args[0].name == "props"
    assert component.args[0].type == "InputProps"
    assert component.args[1].name == "ref"
    assert component.returns == "JSX.Element"


def test_react_memo_const_export_with_inline_component_is_collected_as_function_component() -> (
    None
):
    source = """import { memo } from 'react';

type RowProps = { label: string };

export const Row = memo(function Row(props: RowProps): JSX.Element {
  return <div>{props.label}</div>;
});
"""

    result = TypeScriptValidator().collect_implementation_artifacts(
        source, "src/components/Row.tsx"
    )
    component = _artifact(result, "Row", ArtifactKind.FUNCTION)

    assert result.errors == []
    assert component.args[0].name == "props"
    assert component.args[0].type == "RowProps"
    assert component.returns == "JSX.Element"


def test_react_composed_memo_forward_ref_export_is_collected_as_function_component() -> (
    None
):
    source = """import { forwardRef, memo } from 'react';

type InputProps = { value: string };

export const Input = memo(forwardRef<HTMLInputElement, InputProps>(
  (props: InputProps, ref: React.Ref<HTMLInputElement>): JSX.Element => {
    return <input ref={ref} value={props.value} />;
  }
));
"""

    result = TypeScriptValidator().collect_implementation_artifacts(
        source, "src/components/Input.tsx"
    )
    component = _artifact(result, "Input", ArtifactKind.FUNCTION)

    assert result.errors == []
    assert component.args[0].name == "props"
    assert component.args[0].type == "InputProps"
    assert component.args[1].name == "ref"
    assert component.returns == "JSX.Element"


def test_default_exported_anonymous_arrow_component_is_collected_as_default_function() -> (
    None
):
    source = """type BannerProps = { title: string };

export default (props: BannerProps): JSX.Element => {
  return <aside>{props.title}</aside>;
};
"""

    result = TypeScriptValidator().collect_implementation_artifacts(
        source, "src/components/Banner.tsx"
    )
    component = _artifact(result, "default", ArtifactKind.FUNCTION)

    assert result.errors == []
    assert component.args[0].name == "props"
    assert component.args[0].type == "BannerProps"
    assert component.returns == "JSX.Element"


def test_default_exported_memo_local_reference_is_collected_as_component() -> None:
    source = """import { memo } from 'react';

type RowProps = { label: string };

function Row(props: RowProps): JSX.Element {
  return <div>{props.label}</div>;
}

function localHelper(): string {
  return 'hidden';
}

export default memo(Row);
"""

    result = TypeScriptValidator().collect_implementation_artifacts(
        source, "src/components/Row.tsx"
    )
    names = {artifact.name for artifact in result.artifacts}
    component = _artifact(result, "Row", ArtifactKind.FUNCTION)

    assert result.errors == []
    assert component.args[0].name == "props"
    assert component.args[0].type == "RowProps"
    assert component.returns == "JSX.Element"
    assert "localHelper" not in names


def test_default_exported_memo_named_inline_component_is_collected_as_component() -> (
    None
):
    source = """import React from 'react';

type RowProps = { label: string };

export default React.memo(function Row(props: RowProps): JSX.Element {
  return <div>{props.label}</div>;
});
"""

    result = TypeScriptValidator().collect_implementation_artifacts(
        source, "src/components/Row.tsx"
    )
    component = _artifact(result, "Row", ArtifactKind.FUNCTION)

    assert result.errors == []
    assert component.args[0].name == "props"
    assert component.args[0].type == "RowProps"
    assert component.returns == "JSX.Element"


def test_default_exported_memo_anonymous_arrow_is_collected_as_default_function() -> (
    None
):
    source = """import { memo } from 'react';

type RowProps = { label: string };

export default memo((props: RowProps): JSX.Element => {
  return <div>{props.label}</div>;
});
"""

    result = TypeScriptValidator().collect_implementation_artifacts(
        source, "src/components/Row.tsx"
    )
    component = _artifact(result, "default", ArtifactKind.FUNCTION)

    assert result.errors == []
    assert component.args[0].name == "props"
    assert component.args[0].type == "RowProps"
    assert component.returns == "JSX.Element"


def test_non_component_react_calls_remain_attributes() -> None:
    source = """import React from 'react';

export const cached = React.useMemo(() => ({ ready: true }), []);
export const callback = React.useCallback(() => true, []);
export const LazyCard = React.lazy(() => import('./LazyCard'));
"""

    result = TypeScriptValidator().collect_implementation_artifacts(
        source, "src/components/cache.tsx"
    )

    assert result.errors == []
    assert _artifact(result, "cached", ArtifactKind.ATTRIBUTE)
    assert _artifact(result, "callback", ArtifactKind.ATTRIBUTE)
    assert _artifact(result, "LazyCard", ArtifactKind.ATTRIBUTE)
