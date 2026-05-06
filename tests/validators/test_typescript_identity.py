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
from maid_runner.validators.base import FoundArtifact
from maid_runner.validators.typescript import TypeScriptValidator


@pytest.fixture()
def validator() -> TypeScriptValidator:
    return TypeScriptValidator()


def _ref(artifacts: list[FoundArtifact], name: str) -> FoundArtifact | None:
    for a in artifacts:
        if a.name == name:
            return a
    return None


# ----------------------------------------------------------------------------
# Validator-owned resolver methods
# ----------------------------------------------------------------------------


class TestValidatorResolverMethods:
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
