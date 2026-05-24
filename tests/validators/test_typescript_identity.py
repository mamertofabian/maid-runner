"""Behavioral tests for TypeScript validator identity-aware collection.

Verifies that TypeScriptValidator populates module_path/import_source/
alias_of, that BaseValidator's resolver methods are wired through, and
that the matcher rejects cross-module name collisions through TS
attribute (member_expression) chains.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from maid_runner.core.identity import match_artifact_to_references
from maid_runner.core.types import ArtifactKind
from maid_runner.validators.base import BaseValidator, CollectionResult, FoundArtifact
from maid_runner.validators._typescript_behavioral import collect_behavioral_artifacts
from maid_runner.validators._typescript_parse import parse_typescript_source
from maid_runner.validators.typescript import TypeScriptValidator


@pytest.fixture()
def validator() -> TypeScriptValidator:
    return TypeScriptValidator()


def _ref(artifacts: list[FoundArtifact], name: str) -> FoundArtifact | None:
    for a in artifacts:
        if a.name == name:
            return a
    return None


class _NoopValidator(BaseValidator):
    @classmethod
    def supported_extensions(cls) -> tuple[str, ...]:
        return (".noop",)

    def collect_implementation_artifacts(
        self,
        source: str,
        file_path: str | Path,
    ) -> CollectionResult:
        return CollectionResult(artifacts=[], language="noop", file_path=str(file_path))

    def collect_behavioral_artifacts(
        self,
        source: str,
        file_path: str | Path,
    ) -> CollectionResult:
        return CollectionResult(artifacts=[], language="noop", file_path=str(file_path))


# ----------------------------------------------------------------------------
# Validator-owned resolver methods
# ----------------------------------------------------------------------------


class TestValidatorResolverMethods:
    def test_base_validator_module_path_defaults_to_none(self, tmp_path: Path) -> None:
        assert issubclass(_NoopValidator, BaseValidator)
        assert _NoopValidator().module_path(tmp_path / "source.noop", tmp_path) is None

    def test_module_path_strips_extension_and_normalizes(
        self, validator: TypeScriptValidator, tmp_path: Path
    ) -> None:
        target = tmp_path / "src" / "models" / "user.ts"
        target.parent.mkdir(parents=True)
        target.write_text("")
        assert validator.module_path(target, tmp_path) == "src/models/user"

    def test_resolve_reexport_through_index_ts(
        self, validator: TypeScriptValidator, tmp_path: Path
    ) -> None:
        models = tmp_path / "src" / "models"
        models.mkdir(parents=True)
        (models / "index.ts").write_text("export { Foo } from './user';\n")
        (models / "user.ts").write_text("export class Foo {}\n")

        assert validator.resolve_reexport("src/models", "Foo", tmp_path) == (
            "src/models/user",
            "Foo",
        )


# ----------------------------------------------------------------------------
# Behavioral collection: import_source and alias_of
# ----------------------------------------------------------------------------


class TestNamedImportRecordsSource:
    def test_named_import_records_source_module(
        self, validator: TypeScriptValidator
    ) -> None:
        source = "import { Foo } from './user';\nit('uses Foo', () => { Foo(); });\n"
        result = validator.collect_behavioral_artifacts(source, "src/models/test_x.ts")
        foo = _ref(result.artifacts, "Foo")
        assert foo is not None
        assert foo.import_source == "src/models/user"
        assert foo.alias_of is None

    def test_import_and_access_references_carry_distinct_contexts(
        self, validator: TypeScriptValidator
    ) -> None:
        source = "import { Foo } from './user';\nit('uses Foo', () => { Foo(); });\n"
        result = validator.collect_behavioral_artifacts(source, "src/models/test_x.ts")
        foo_refs = [artifact for artifact in result.artifacts if artifact.name == "Foo"]

        assert any(
            ref.reference_context == "import" and ref.import_source == "src/models/user"
            for ref in foo_refs
        )
        assert any(
            ref.reference_context == "access" and ref.import_source == "src/models/user"
            for ref in foo_refs
        )

    def test_named_import_with_alias_records_alias_of(
        self, validator: TypeScriptValidator
    ) -> None:
        source = (
            "import { Foo as Bar } from './user';\nit('uses Bar', () => { Bar(); });\n"
        )
        result = validator.collect_behavioral_artifacts(source, "src/models/test_x.ts")
        bar = _ref(result.artifacts, "Bar")
        assert bar is not None
        assert bar.import_source == "src/models/user"
        assert bar.alias_of == "Foo"

    @pytest.mark.parametrize(
        ("source", "expected_reference_context", "scenario"),
        [
            (
                "function update() {\n"
                "  return 'local';\n"
                "}\n\n"
                "it('uses local update', () => {\n"
                "  expect(update()).toBe('local');\n"
                "});\n",
                "local",
                "local function declaration",
            ),
            (
                "import { noop } from '../src/other';\n\n"
                "it('uses unrelated import before bare update', () => {\n"
                "  expect(noop()).toBe('noop');\n"
                "  update();\n"
                "});\n",
                "access",
                "bare same-name call with unrelated import",
            ),
            (
                "class Local {\n"
                "  update() {\n"
                "    return 'local';\n"
                "  }\n"
                "}\n\n"
                "it('uses local update method', () => {\n"
                "  expect(new Local().update()).toBe('local');\n"
                "});\n",
                "local",
                "local method call",
            ),
        ],
    )
    def test_local_same_name_helpers_keep_non_import_reference_context(
        self,
        validator: TypeScriptValidator,
        tmp_path: Path,
        source: str,
        expected_reference_context: str,
        scenario: str,
    ) -> None:
        test_path = tmp_path / "tests" / "widget.test.ts"
        session = parse_typescript_source(
            source,
            test_path,
            validator._ts_parser,
            validator._tsx_parser,
        )
        collected_references = collect_behavioral_artifacts(
            session.tree.root_node,
            session.source_bytes,
            test_path,
        )

        assert any(
            ref.name == "update" and ref.reference_context == expected_reference_context
            for ref in collected_references
        ), scenario

    def test_tsconfig_paths_alias_records_source_module(
        self, validator: TypeScriptValidator, tmp_path: Path
    ) -> None:
        (tmp_path / "tsconfig.json").write_text(
            '{"compilerOptions": {"baseUrl": ".", "paths": {"@/*": ["src/*"]}}}'
        )
        source = (
            "import { Button } from '@/components/Button';\n"
            "it('uses Button', () => { return <Button />; });\n"
        )
        result = validator.collect_behavioral_artifacts(
            source, tmp_path / "src" / "Button.test.tsx"
        )
        button = _ref(result.artifacts, "Button")
        assert button is not None
        assert button.import_source == "src/components/Button"

    def test_tsconfig_extends_paths_alias_records_source_module(
        self, validator: TypeScriptValidator, tmp_path: Path
    ) -> None:
        (tmp_path / "tsconfig.base.json").write_text(
            '{"compilerOptions": {"baseUrl": ".", "paths": {"@/*": ["src/*"]}}}'
        )
        (tmp_path / "tsconfig.json").write_text('{"extends": "./tsconfig.base.json"}')
        source = (
            "import { Button } from '@/components/Button';\n"
            "it('uses Button', () => { return <Button />; });\n"
        )
        result = validator.collect_behavioral_artifacts(
            source, tmp_path / "src" / "Button.test.tsx"
        )
        button = _ref(result.artifacts, "Button")
        assert button is not None
        assert button.import_source == "src/components/Button"

    def test_package_import_records_package_source(
        self, validator: TypeScriptValidator, tmp_path: Path
    ) -> None:
        (tmp_path / "tsconfig.json").write_text(
            '{"compilerOptions": {"baseUrl": ".", "paths": {"@/*": ["src/*"]}}}'
        )
        source = (
            "import { render } from '@testing-library/react';\n"
            "it('uses render', () => { render(null); });\n"
        )
        result = validator.collect_behavioral_artifacts(
            source, tmp_path / "src" / "render.test.tsx"
        )
        render = _ref(result.artifacts, "render")
        assert render is not None
        assert render.import_source == "@testing-library/react"

    def test_workspace_package_import_records_workspace_source(
        self, validator: TypeScriptValidator, tmp_path: Path
    ) -> None:
        (tmp_path / "package.json").write_text('{"workspaces": ["packages/*"]}')
        (tmp_path / "tsconfig.json").write_text(
            '{"compilerOptions": {"moduleResolution": "Bundler", "module": "ESNext", "baseUrl": "."}, "include": ["src/**/*", "packages/**/*"]}'
        )
        src = tmp_path / "src"
        src.mkdir()
        package_dir = tmp_path / "packages" / "ui"
        package_dir.mkdir(parents=True)
        (package_dir / "package.json").write_text(
            '{"name": "@scope/ui", "exports": {"./Button": "./src/Button.ts"}}'
        )
        button_file = package_dir / "src" / "Button.ts"
        button_file.parent.mkdir()
        button_file.write_text("export function Button() {}\n")
        scope_dir = tmp_path / "node_modules" / "@scope"
        scope_dir.mkdir(parents=True)
        (scope_dir / "ui").symlink_to(package_dir, target_is_directory=True)
        source = (
            "import { Button } from '@scope/ui/Button';\n"
            "it('uses Button', () => { Button(); });\n"
        )
        result = validator.collect_behavioral_artifacts(
            source, tmp_path / "src" / "Button.test.ts"
        )
        button = _ref(result.artifacts, "Button")
        assert button is not None
        assert button.import_source == "packages/ui/src/Button"

    def test_package_export_import_records_project_local_source_when_compiler_succeeds(
        self, validator: TypeScriptValidator, tmp_path: Path
    ) -> None:
        (tmp_path / "package.json").write_text('{"workspaces": ["packages/*"]}')
        (tmp_path / "tsconfig.json").write_text(
            '{"compilerOptions": {"moduleResolution": "Bundler", "module": "ESNext", "baseUrl": "."}, "include": ["src/**/*", "packages/**/*"]}'
        )
        src = tmp_path / "src"
        src.mkdir()
        package_dir = tmp_path / "packages" / "ui"
        package_dir.mkdir(parents=True)
        (package_dir / "package.json").write_text(
            '{"name": "@scope/ui", "exports": {"./features/*": "./src/features/*.ts"}}'
        )
        card = package_dir / "src" / "features" / "card.ts"
        card.parent.mkdir(parents=True)
        card.write_text("export function Card() {}\n")
        scope_dir = tmp_path / "node_modules" / "@scope"
        scope_dir.mkdir(parents=True)
        (scope_dir / "ui").symlink_to(package_dir, target_is_directory=True)
        source = (
            "import { Card } from '@scope/ui/features/card';\n"
            "it('uses Card', () => { Card(); });\n"
        )

        result = validator.collect_behavioral_artifacts(
            source, tmp_path / "src" / "Card.test.ts"
        )

        card_ref = _ref(result.artifacts, "Card")
        assert card_ref is not None
        assert card_ref.import_source == "packages/ui/src/features/card"

    def test_direct_dependency_import_records_package_source_with_compiler_available(
        self, validator: TypeScriptValidator, tmp_path: Path
    ) -> None:
        (tmp_path / "tsconfig.json").write_text(
            '{"compilerOptions": {"moduleResolution": "Bundler", "module": "ESNext", "baseUrl": "."}, "include": ["src/**/*"]}'
        )
        # Direct dependency: real directory in node_modules, no workspace symlink
        pkg_dir = tmp_path / "node_modules" / "@scope" / "ui"
        pkg_dir.mkdir(parents=True)
        (pkg_dir / "package.json").write_text(
            '{"name": "@scope/ui", "exports": {"./Button": "./src/Button.js"}}'
        )
        source = (
            "import { Button } from '@scope/ui/Button';\n"
            "it('uses Button', () => { Button(); });\n"
        )
        result = validator.collect_behavioral_artifacts(
            source, tmp_path / "src" / "Button.test.ts"
        )
        button = _ref(result.artifacts, "Button")
        assert button is not None
        assert button.import_source == "@scope/ui/Button"


class TestDefaultImportRecordsSource:
    def test_default_import_records_source_module(
        self, validator: TypeScriptValidator
    ) -> None:
        source = "import Foo from './user';\nit('uses Foo', () => { Foo(); });\n"
        result = validator.collect_behavioral_artifacts(source, "src/models/test_x.ts")
        foo = _ref(result.artifacts, "Foo")
        assert foo is not None
        assert foo.import_source == "src/models/user"


class TestNamespaceImport:
    def test_namespace_import_records_source(
        self, validator: TypeScriptValidator
    ) -> None:
        source = (
            "import * as utils from './utils';\n"
            "it('uses utils', () => { utils.go(); });\n"
        )
        result = validator.collect_behavioral_artifacts(source, "src/models/test_x.ts")
        utils = _ref(result.artifacts, "utils")
        assert utils is not None
        assert utils.import_source == "src/models/utils"

    def test_namespace_member_call_resolves_leaf_to_module(
        self, validator: TypeScriptValidator
    ) -> None:
        # The high-priority bug fix's TS analogue:
        # `utils.go()` should record `go` with import_source=src/models/utils,
        # not as a bare reference that falls back to name-only matching.
        source = (
            "import * as utils from './utils';\n"
            "it('uses utils.go', () => { utils.go(); });\n"
        )
        result = validator.collect_behavioral_artifacts(source, "src/models/test_x.ts")
        go = _ref(result.artifacts, "go")
        assert go is not None
        assert go.import_source == "src/models/utils"


class TestSideEffectImportSkipped:
    def test_bare_import_adds_no_reference(
        self, validator: TypeScriptValidator
    ) -> None:
        # `import './setup';` binds nothing — no reference should be added
        # for the module path itself.
        source = "import './setup';\nit('runs', () => { x(); });\n"
        result = validator.collect_behavioral_artifacts(source, "src/models/test_x.ts")
        # No reference named 'setup' or './setup' should appear.
        assert _ref(result.artifacts, "setup") is None
        assert _ref(result.artifacts, "./setup") is None


# ----------------------------------------------------------------------------
# JSX/TSX component references
# ----------------------------------------------------------------------------


class TestJsxComponentReference:
    def test_jsx_component_inherits_import_source(
        self, validator: TypeScriptValidator
    ) -> None:
        source = (
            "import { Button } from './Button';\n"
            "it('renders', () => { return <Button />; });\n"
        )
        result = validator.collect_behavioral_artifacts(
            source, "src/components/test_x.tsx"
        )
        button = _ref(result.artifacts, "Button")
        assert button is not None
        assert button.import_source == "src/components/Button"


class TestPropAttributeReferences:
    def test_object_literal_prop_keys_are_behavioral_references(
        self, validator: TypeScriptValidator
    ) -> None:
        source = (
            "import { render } from '@testing-library/react';\n"
            "import { RiderDashboard } from './RiderDashboard';\n"
            "it('renders rider details', () => {\n"
            "  const props = {\n"
            "    currentUserName: 'Ari',\n"
            "    communityStatus: 'active',\n"
            "  };\n"
            "  render(<RiderDashboard {...props} />);\n"
            "});\n"
        )
        result = validator.collect_behavioral_artifacts(
            source, "src/components/RiderDashboard.test.tsx"
        )

        assert _ref(result.artifacts, "currentUserName") is not None
        assert _ref(result.artifacts, "communityStatus") is not None

    def test_shorthand_object_props_are_behavioral_references(
        self, validator: TypeScriptValidator
    ) -> None:
        source = (
            "import { render } from '@testing-library/react';\n"
            "import { RiderDashboard } from './RiderDashboard';\n"
            "it('renders rider details', () => {\n"
            "  const currentUserName = 'Ari';\n"
            "  const props = { currentUserName };\n"
            "  render(<RiderDashboard {...props} />);\n"
            "});\n"
        )
        result = validator.collect_behavioral_artifacts(
            source, "src/components/RiderDashboard.test.tsx"
        )

        assert _ref(result.artifacts, "currentUserName") is not None

    def test_jsx_attribute_names_are_behavioral_references(
        self, validator: TypeScriptValidator
    ) -> None:
        source = (
            "import { render } from '@testing-library/react';\n"
            "import { RiderDashboard } from './RiderDashboard';\n"
            "it('renders rider details', () => {\n"
            "  render(\n"
            "    <RiderDashboard\n"
            "      currentUserName='Ari'\n"
            "      communityStatus='active'\n"
            "    />\n"
            "  );\n"
            "});\n"
        )
        result = validator.collect_behavioral_artifacts(
            source, "src/components/RiderDashboard.test.tsx"
        )

        assert _ref(result.artifacts, "currentUserName") is not None
        assert _ref(result.artifacts, "communityStatus") is not None

    def test_computed_object_key_names_are_behavioral_references(
        self, validator: TypeScriptValidator
    ) -> None:
        source = (
            "import { ManualAuditStep } from './steps';\n"
            "it('uses completion flags', () => {\n"
            "  const completion = {\n"
            "    [ManualAuditStep.AUDIT_DETAILS]: true,\n"
            "  };\n"
            "  expect(completion[ManualAuditStep.AUDIT_DETAILS]).toBe(true);\n"
            "});\n"
        )
        result = validator.collect_behavioral_artifacts(
            source, "src/audit/audit-management.service.spec.ts"
        )

        assert _ref(result.artifacts, "[ManualAuditStep.AUDIT_DETAILS]") is not None

    def test_computed_subscript_key_names_are_behavioral_references(
        self, validator: TypeScriptValidator
    ) -> None:
        source = (
            "import { ManualAuditStep } from './steps';\n"
            "it('reads loading flags', () => {\n"
            "  const loading = getLoadingState();\n"
            "  expect(loading[ManualAuditStep.CONTENT_CREATION]).toBe(false);\n"
            "});\n"
        )
        result = validator.collect_behavioral_artifacts(
            source, "src/audit/audit-management.service.spec.ts"
        )

        assert _ref(result.artifacts, "[ManualAuditStep.CONTENT_CREATION]") is not None

    def test_literal_computed_subscript_key_names_are_behavioral_references(
        self, validator: TypeScriptValidator
    ) -> None:
        source = (
            "it('reads literal computed flags', () => {\n"
            "  const completion = getCompletionState();\n"
            '  expect(completion["audit-details"]).toBe(true);\n'
            "  expect(completion[404]).toBe(false);\n"
            "});\n"
        )
        result = validator.collect_behavioral_artifacts(
            source, "src/audit/audit-management.service.spec.ts"
        )

        assert _ref(result.artifacts, '["audit-details"]') is not None
        assert _ref(result.artifacts, "[404]") is not None


# ----------------------------------------------------------------------------
# Implementation collection: module_path on defined artifacts
# ----------------------------------------------------------------------------


class TestModulePathOnImplementation:
    def test_class_carries_module_path(self, validator: TypeScriptValidator) -> None:
        source = "export class Foo {}\nexport function bar() {}\n"
        result = validator.collect_implementation_artifacts(
            source, "src/models/user.ts"
        )
        foo = _ref(result.artifacts, "Foo")
        bar = _ref(result.artifacts, "bar")
        assert foo is not None and foo.module_path == "src/models/user"
        assert bar is not None and bar.module_path == "src/models/user"


# ----------------------------------------------------------------------------
# Integration: identity matcher rejects cross-module name collision via chain
# ----------------------------------------------------------------------------


class TestIdentityRejectsCrossModuleCollision:
    def test_member_chain_rejects_wrong_module_artifact(
        self, validator: TypeScriptValidator, tmp_path: Path
    ) -> None:
        source = (
            "import * as utils from './utils';\n"
            "it('uses utils.go', () => { utils.go(); });\n"
        )
        result = validator.collect_behavioral_artifacts(source, "src/models/test_x.ts")

        wrong = FoundArtifact(
            kind=ArtifactKind.FUNCTION,
            name="go",
            module_path="src/other/utils",
        )
        right = FoundArtifact(
            kind=ArtifactKind.FUNCTION,
            name="go",
            module_path="src/models/utils",
        )
        assert not match_artifact_to_references(
            wrong,
            result.artifacts,
            tmp_path,
            reexport_resolver=validator.resolve_reexport,
        )
        assert match_artifact_to_references(
            right,
            result.artifacts,
            tmp_path,
            reexport_resolver=validator.resolve_reexport,
        )

    def test_aliased_barrel_bridges_alias_back_to_artifact_name(
        self, validator: TypeScriptValidator, tmp_path: Path
    ) -> None:
        # index.ts: export { Foo as Bar } from './user'
        # Test imports `Bar` from the barrel `./models`. Artifact lives in
        # `src/models/user` under its true name `Foo`. The matcher must
        # bridge Bar back to Foo via the barrel's alias mapping.
        models = tmp_path / "src" / "models"
        models.mkdir(parents=True)
        (models / "index.ts").write_text("export { Foo as Bar } from './user';\n")
        (models / "user.ts").write_text("export class Foo {}\n")

        source = "import { Bar } from './models';\nit('uses Bar', () => { Bar(); });\n"
        result = validator.collect_behavioral_artifacts(source, "src/test_x.ts")

        artifact = FoundArtifact(
            kind=ArtifactKind.CLASS,
            name="Foo",
            module_path="src/models/user",
        )
        assert match_artifact_to_references(
            artifact,
            result.artifacts,
            tmp_path,
            reexport_resolver=validator.resolve_reexport,
        )

    def test_match_through_one_level_index_reexport(
        self, validator: TypeScriptValidator, tmp_path: Path
    ) -> None:
        # index.ts re-exports Foo from ./user.
        # Test imports from the barrel `./models`. Artifact lives in
        # `src/models/user`. Identity must match through resolve_reexport.
        models = tmp_path / "src" / "models"
        models.mkdir(parents=True)
        (models / "index.ts").write_text("export { Foo } from './user';\n")
        (models / "user.ts").write_text("export class Foo {}\n")

        source = "import { Foo } from './models';\nit('uses Foo', () => { Foo(); });\n"
        # file_path is project-relative — same convention as the Python pass.
        # project_root (tmp_path) is what locates index.ts during reexport.
        result = validator.collect_behavioral_artifacts(source, "src/test_x.ts")

        artifact = FoundArtifact(
            kind=ArtifactKind.CLASS,
            name="Foo",
            module_path="src/models/user",
        )
        assert match_artifact_to_references(
            artifact,
            result.artifacts,
            tmp_path,
            reexport_resolver=validator.resolve_reexport,
        )

    def test_match_through_one_level_star_reexport(
        self, validator: TypeScriptValidator, tmp_path: Path
    ) -> None:
        models = tmp_path / "src" / "models"
        models.mkdir(parents=True)
        (models / "index.ts").write_text("export * from './user';\n")
        (models / "user.ts").write_text("export class Foo {}\n")

        source = "import { Foo } from './models';\nit('uses Foo', () => { Foo(); });\n"
        result = validator.collect_behavioral_artifacts(source, "src/test_x.ts")
        foo = _ref(result.artifacts, "Foo")
        assert foo is not None
        assert foo.import_source == "src/models"

        artifact = FoundArtifact(
            kind=ArtifactKind.CLASS,
            name="Foo",
            module_path="src/models/user",
        )
        wrong = FoundArtifact(
            kind=ArtifactKind.CLASS,
            name="Foo",
            module_path="src/other/user",
        )
        assert not match_artifact_to_references(
            wrong,
            result.artifacts,
            tmp_path,
            reexport_resolver=validator.resolve_reexport,
        )
        assert match_artifact_to_references(
            artifact,
            result.artifacts,
            tmp_path,
            reexport_resolver=validator.resolve_reexport,
        )

    def test_namespace_star_reexport_does_not_match_direct_named_import(
        self, validator: TypeScriptValidator, tmp_path: Path
    ) -> None:
        components = tmp_path / "src" / "components"
        components.mkdir(parents=True)
        (components / "index.ts").write_text("export * as Icons from './icons';\n")
        (components / "icons.ts").write_text("export function Camera() {}\n")

        source = (
            "import { Camera } from './components';\n"
            "it('uses Camera', () => { Camera(); });\n"
        )
        result = validator.collect_behavioral_artifacts(source, "src/test_x.ts")
        camera = _ref(result.artifacts, "Camera")
        assert camera is not None
        assert camera.import_source == "src/components"

        artifact = FoundArtifact(
            kind=ArtifactKind.FUNCTION,
            name="Camera",
            module_path="src/components/icons",
        )
        assert not match_artifact_to_references(
            artifact,
            result.artifacts,
            tmp_path,
            reexport_resolver=validator.resolve_reexport,
        )

    def test_match_through_default_as_reexport(
        self, validator: TypeScriptValidator, tmp_path: Path
    ) -> None:
        components = tmp_path / "src" / "components"
        components.mkdir(parents=True)
        (components / "index.ts").write_text(
            "export { default as Button } from './Button';\n"
        )
        (components / "Button.tsx").write_text("export default class Button {}\n")

        source = (
            "import { Button } from './components';\n"
            "it('uses Button', () => { return <Button />; });\n"
        )
        result = validator.collect_behavioral_artifacts(source, "src/Button.test.tsx")
        button = _ref(result.artifacts, "Button")
        assert button is not None
        assert button.import_source == "src/components"

        artifact = FoundArtifact(
            kind=ArtifactKind.CLASS,
            name="Button",
            module_path="src/components/Button",
        )
        wrong = FoundArtifact(
            kind=ArtifactKind.CLASS,
            name="Button",
            module_path="src/other/Button",
        )
        assert not match_artifact_to_references(
            wrong,
            result.artifacts,
            tmp_path,
            reexport_resolver=validator.resolve_reexport,
        )
        assert match_artifact_to_references(
            artifact,
            result.artifacts,
            tmp_path,
            reexport_resolver=validator.resolve_reexport,
        )

    def test_recursive_barrel_reexport_matches_final_artifact(
        self, validator: TypeScriptValidator, tmp_path: Path
    ) -> None:
        (tmp_path / "tsconfig.json").write_text(
            '{"compilerOptions": {"moduleResolution": "Bundler", "module": "ESNext", "baseUrl": "."}, "include": ["src/**/*"]}'
        )
        components = tmp_path / "src" / "components"
        nested = components / "nested"
        nested.mkdir(parents=True)
        (components / "index.ts").write_text("export { Button } from './nested';\n")
        (nested / "index.ts").write_text("export { Button } from './Button';\n")
        (nested / "Button.tsx").write_text("export function Button() {}\n")

        source = (
            "import { Button } from './components';\n"
            "it('uses Button', () => { return <Button />; });\n"
        )
        result = validator.collect_behavioral_artifacts(source, "src/Button.test.tsx")
        button = _ref(result.artifacts, "Button")
        assert button is not None
        assert button.import_source == "src/components"

        artifact = FoundArtifact(
            kind=ArtifactKind.FUNCTION,
            name="Button",
            module_path="src/components/nested/Button",
        )
        assert match_artifact_to_references(
            artifact,
            result.artifacts,
            tmp_path,
            reexport_resolver=validator.resolve_reexport,
        )

    def test_package_export_reexport_matches_project_local_source_when_compiler_succeeds(
        self, validator: TypeScriptValidator, tmp_path: Path
    ) -> None:
        (tmp_path / "package.json").write_text('{"workspaces": ["packages/*"]}')
        (tmp_path / "tsconfig.json").write_text(
            '{"compilerOptions": {"moduleResolution": "Bundler", "module": "ESNext", "baseUrl": "."}, "include": ["src/**/*", "packages/**/*"]}'
        )
        src = tmp_path / "src"
        src.mkdir()
        package_dir = tmp_path / "packages" / "ui"
        package_dir.mkdir(parents=True)
        (package_dir / "package.json").write_text(
            '{"name": "@scope/ui", "exports": {".": "./src/index.ts"}}'
        )
        package_src = package_dir / "src"
        package_src.mkdir()
        (package_src / "index.ts").write_text("export { Button } from './Button';\n")
        (package_src / "Button.ts").write_text("export function Button() {}\n")
        scope_dir = tmp_path / "node_modules" / "@scope"
        scope_dir.mkdir(parents=True)
        (scope_dir / "ui").symlink_to(package_dir, target_is_directory=True)
        source = (
            "import { Button } from '@scope/ui';\n"
            "it('uses Button', () => { Button(); });\n"
        )

        result = validator.collect_behavioral_artifacts(
            source, tmp_path / "src" / "Button.test.ts"
        )
        button = _ref(result.artifacts, "Button")
        assert button is not None
        assert button.import_source == "packages/ui/src"

        artifact = FoundArtifact(
            kind=ArtifactKind.FUNCTION,
            name="Button",
            module_path="packages/ui/src/Button",
        )
        assert match_artifact_to_references(
            artifact,
            result.artifacts,
            tmp_path,
            reexport_resolver=validator.resolve_reexport,
        )

    def test_match_through_tsconfig_alias_to_barrel_reexport(
        self, validator: TypeScriptValidator, tmp_path: Path
    ) -> None:
        (tmp_path / "tsconfig.json").write_text(
            '{"compilerOptions": {"baseUrl": ".", "paths": {"@components": ["src/components"]}}}'
        )
        components = tmp_path / "src" / "components"
        components.mkdir(parents=True)
        (components / "index.ts").write_text(
            "export { default as Button } from './Button';\n"
        )
        (components / "Button.tsx").write_text("export default class Button {}\n")

        source = (
            "import { Button } from '@components';\n"
            "it('uses Button', () => { return <Button />; });\n"
        )
        result = validator.collect_behavioral_artifacts(
            source, tmp_path / "src" / "Button.test.tsx"
        )
        button = _ref(result.artifacts, "Button")
        assert button is not None
        assert button.import_source == "src/components"

        artifact = FoundArtifact(
            kind=ArtifactKind.CLASS,
            name="Button",
            module_path="src/components/Button",
        )
        wrong = FoundArtifact(
            kind=ArtifactKind.CLASS,
            name="Button",
            module_path="src/other/Button",
        )
        assert not match_artifact_to_references(
            wrong,
            result.artifacts,
            tmp_path,
            reexport_resolver=validator.resolve_reexport,
        )
        assert match_artifact_to_references(
            artifact,
            result.artifacts,
            tmp_path,
            reexport_resolver=validator.resolve_reexport,
        )

    def test_match_through_index_mjs_reexport(
        self, validator: TypeScriptValidator, tmp_path: Path
    ) -> None:
        components = tmp_path / "src" / "components"
        components.mkdir(parents=True)
        (components / "index.mjs").write_text(
            "export { Button } from './Button.mjs';\n"
        )
        (components / "Button.mjs").write_text("export function Button() {}\n")

        source = (
            "import { Button } from './components';\n"
            "it('uses Button', () => { Button(); });\n"
        )
        result = validator.collect_behavioral_artifacts(source, "src/Button.test.ts")
        button = _ref(result.artifacts, "Button")
        assert button is not None
        assert button.import_source == "src/components"

        artifact = FoundArtifact(
            kind=ArtifactKind.FUNCTION,
            name="Button",
            module_path="src/components/Button",
        )
        assert match_artifact_to_references(
            artifact,
            result.artifacts,
            tmp_path,
            reexport_resolver=validator.resolve_reexport,
        )

    def test_direct_dependency_reexport_does_not_match_project_local_artifact(
        self, validator: TypeScriptValidator, tmp_path: Path
    ) -> None:
        (tmp_path / "tsconfig.json").write_text(
            '{"compilerOptions": {"moduleResolution": "Node10"}, "include": ["src/**/*"]}'
        )
        # Direct dependency (real node_modules dir, no workspace symlink)
        pkg_dir = tmp_path / "node_modules" / "@scope" / "ui"
        pkg_dir.mkdir(parents=True)
        (pkg_dir / "package.json").write_text(
            '{"name": "@scope/ui", "types": "./index.d.ts"}'
        )
        (pkg_dir / "index.d.ts").write_text("export declare function Button(): void;\n")
        barrel = tmp_path / "src" / "components"
        barrel.mkdir(parents=True)
        (barrel / "index.ts").write_text("export { Button } from '@scope/ui';\n")

        source = (
            "import { Button } from './components';\n"
            "it('uses Button', () => { Button(); });\n"
        )
        result = validator.collect_behavioral_artifacts(source, "src/test_x.ts")
        button = _ref(result.artifacts, "Button")
        assert button is not None
        assert button.import_source == "src/components"

        # A project-local artifact must not match through a barrel that chains to a direct dep
        local_button = FoundArtifact(
            kind=ArtifactKind.FUNCTION,
            name="Button",
            module_path="src/local/Button",
        )
        assert not match_artifact_to_references(
            local_button,
            result.artifacts,
            tmp_path,
            reexport_resolver=validator.resolve_reexport,
        )
