"""Tests for maid_runner.validators.svelte - SvelteValidator."""

from __future__ import annotations

from pathlib import Path

import pytest

from maid_runner.core.identity import match_artifact_to_references
from maid_runner.core.result import ErrorCode
from maid_runner.core.types import ArtifactKind
from maid_runner.core.types import ValidationMode
from maid_runner.core.validate import ValidationEngine
from maid_runner.validators.base import FoundArtifact

try:
    from maid_runner.validators.svelte import SvelteValidator

    HAS_SVELTE = True
except ImportError:
    HAS_SVELTE = False

pytestmark = pytest.mark.skipif(
    not HAS_SVELTE,
    reason="tree-sitter-typescript not installed",
)


@pytest.fixture()
def validator():
    return SvelteValidator()


def _find(artifacts, name, kind=None):
    for a in artifacts:
        if a.name == name:
            if kind is not None and a.kind != kind:
                continue
            return a
    return None


def test_component_file_stem_is_collected_as_function_artifact(
    validator: SvelteValidator,
) -> None:
    source = """<script lang="ts">
export let repoName: string;
</script>

<section>{repoName}</section>
"""

    result = validator.collect_implementation_artifacts(
        source, "src/lib/components/RepoSettings.svelte"
    )

    component = _find(result.artifacts, "RepoSettings", ArtifactKind.FUNCTION)
    assert component is not None
    assert component.module_path == "src/lib/components/RepoSettings"
    assert component.line == 1


def test_component_artifact_takes_precedence_over_same_name_script_helper(
    validator: SvelteValidator,
) -> None:
    source = """<script lang="ts">
function RepoSettings(repoName: string): string {
    return repoName;
}
</script>

<section>{RepoSettings('demo')}</section>
"""

    result = validator.collect_implementation_artifacts(
        source, "src/lib/components/RepoSettings.svelte"
    )

    components = [
        artifact
        for artifact in result.artifacts
        if artifact.name == "RepoSettings" and artifact.kind == ArtifactKind.FUNCTION
    ]
    assert len(components) == 1
    assert components[0].returns == "Svelte component instance"
    assert components[0].args == ()
    assert components[0].line == 1


def test_component_artifact_satisfies_implementation_validation(
    tmp_path: Path,
) -> None:
    manifest_path = tmp_path / "manifests" / "add-settings.manifest.yaml"
    manifest_path.parent.mkdir()
    manifest_path.write_text(
        """schema: "2"
goal: "Add settings component"
type: feature
files:
  edit:
    - path: src/lib/components/RepoSettings.svelte
      artifacts:
        - kind: function
          name: RepoSettings
          args:
            - name: props
              type: RepoSettings component props
          returns: Svelte component instance
  read:
    - tests/repo-settings.test.ts
validate:
  - vitest run tests/repo-settings.test.ts
"""
    )
    component_path = tmp_path / "src" / "lib" / "components" / "RepoSettings.svelte"
    component_path.parent.mkdir(parents=True)
    component_path.write_text(
        """<script lang="ts">
export let repoName: string;
</script>

<section>{repoName}</section>
"""
    )
    test_path = tmp_path / "tests" / "repo-settings.test.ts"
    test_path.parent.mkdir()
    test_path.write_text(
        """import RepoSettings from '../src/lib/components/RepoSettings.svelte';

test('component can be imported', () => {
  expect(RepoSettings).toBeDefined();
});
"""
    )

    result = ValidationEngine(project_root=tmp_path).validate(
        manifest_path,
        mode=ValidationMode.IMPLEMENTATION,
    )

    assert result.success is True
    assert not any(
        error.code == ErrorCode.ARTIFACT_NOT_DEFINED for error in result.errors
    )


def test_svelte5_props_destructuring_collects_component_attributes(
    validator: SvelteValidator,
) -> None:
    source = """<script lang="ts">
import type { PageData, PublicSection } from '$lib/types/public-api';

let { section, data }: { section: PublicSection; data: PageData } = $props();
</script>

<section>{section.title}</section>
"""

    result = validator.collect_implementation_artifacts(
        source, "src/lib/components/SectionRenderer.svelte"
    )

    section = next(
        (
            artifact
            for artifact in result.artifacts
            if artifact.name == "section"
            and artifact.kind == ArtifactKind.ATTRIBUTE
            and artifact.of == "SectionRenderer"
        ),
        None,
    )
    data = next(
        (
            artifact
            for artifact in result.artifacts
            if artifact.name == "data"
            and artifact.kind == ArtifactKind.ATTRIBUTE
            and artifact.of == "SectionRenderer"
        ),
        None,
    )

    assert section is not None
    assert section.type_annotation == "PublicSection"
    assert section.module_path == "src/lib/components/SectionRenderer"
    assert data is not None
    assert data.type_annotation == "PageData"
    assert data.module_path == "src/lib/components/SectionRenderer"


def test_svelte5_props_destructuring_satisfies_implementation_validation(
    tmp_path: Path,
) -> None:
    manifest_path = tmp_path / "manifests" / "svelte5-props.manifest.yaml"
    manifest_path.parent.mkdir()
    manifest_path.write_text(
        """schema: "2"
goal: "Validate Svelte 5 component props"
type: feature
files:
  edit:
    - path: src/lib/components/SectionRenderer.svelte
      artifacts:
        - kind: function
          name: SectionRenderer
          returns: Svelte component instance
        - kind: attribute
          name: section
          of: SectionRenderer
          type: PublicSection
        - kind: attribute
          name: data
          of: SectionRenderer
          type: PageData
  read:
    - tests/section-renderer.test.ts
validate:
  - vitest run tests/section-renderer.test.ts
"""
    )
    component_path = tmp_path / "src" / "lib" / "components" / "SectionRenderer.svelte"
    component_path.parent.mkdir(parents=True)
    component_path.write_text(
        """<script lang="ts">
import type { PageData, PublicSection } from '$lib/types/public-api';

let { section, data }: { section: PublicSection; data: PageData } = $props();
</script>

<section>{section.title}</section>
"""
    )
    test_path = tmp_path / "tests" / "section-renderer.test.ts"
    test_path.parent.mkdir()
    test_path.write_text(
        """import SectionRenderer from '../src/lib/components/SectionRenderer.svelte';
import type { PageData, PublicSection } from '../src/lib/types/public-api';

test('component props can be declared', () => {
  const section = { title: 'Overview' } as PublicSection;
  const data = { sections: [section] } as PageData;
  expect(SectionRenderer).toBeDefined();
  expect(section).toBeDefined();
  expect(data).toBeDefined();
});
"""
    )

    result = ValidationEngine(project_root=tmp_path).validate(
        manifest_path,
        mode=ValidationMode.IMPLEMENTATION,
    )

    assert result.success is True
    assert not any(
        error.code == ErrorCode.ARTIFACT_NOT_DEFINED for error in result.errors
    )


def test_svelte5_props_destructuring_ignores_non_props_object_patterns(
    validator: SvelteValidator,
) -> None:
    source = """<script lang="ts">
type LocalState = { section: string; data: string };

const localState: LocalState = { section: 'local', data: 'local' };
let { section, data }: LocalState = localState;
</script>

<section>{section}</section>
"""

    result = validator.collect_implementation_artifacts(
        source, "src/lib/components/SectionRenderer.svelte"
    )

    assert not any(
        artifact.name in {"section", "data"}
        and artifact.kind == ArtifactKind.ATTRIBUTE
        and artifact.of == "SectionRenderer"
        for artifact in result.artifacts
    )


def test_svelte5_props_destructuring_ignores_module_scripts(
    validator: SvelteValidator,
) -> None:
    source = """<script context="module" lang="ts">
let { section }: { section: PublicSection } = $props();
</script>

<script module lang="ts">
let { data }: { data: PageData } = $props();
</script>

<section>module props are not component props</section>
"""

    result = validator.collect_implementation_artifacts(
        source, "src/lib/components/SectionRenderer.svelte"
    )

    assert not any(
        artifact.name in {"section", "data"}
        and artifact.kind == ArtifactKind.ATTRIBUTE
        and artifact.of == "SectionRenderer"
        for artifact in result.artifacts
    )


class TestSvelteScriptExtraction:
    def test_extracts_functions_from_script(self, validator):
        source = """<script>
function greet(name) {
    return `Hello, ${name}!`;
}
</script>

<h1>{greet('World')}</h1>
"""
        result = validator.collect_implementation_artifacts(source, "App.svelte")
        a = _find(result.artifacts, "greet")
        assert a is not None
        assert a.kind == ArtifactKind.FUNCTION

    def test_extracts_from_typescript_script(self, validator):
        source = """<script lang="ts">
interface User {
    name: string;
}

const greeting: string = "hello";
</script>
"""
        result = validator.collect_implementation_artifacts(source, "App.svelte")
        user = _find(result.artifacts, "User")
        assert user is not None
        assert user.kind == ArtifactKind.INTERFACE

    def test_empty_script(self, validator):
        source = "<h1>Hello</h1>"
        result = validator.collect_implementation_artifacts(source, "App.svelte")
        assert result.artifacts == []

    def test_ignores_script_tags_inside_comments(self, validator):
        source = """<!-- <script>
function fake() {
    return "not real";
}
</script> -->

<script>
function real() {
    return "real";
}
</script>
"""
        result = validator.collect_implementation_artifacts(source, "App.svelte")

        assert _find(result.artifacts, "fake") is None
        assert _find(result.artifacts, "real", ArtifactKind.FUNCTION) is not None

    def test_handles_quoted_greater_than_in_script_attributes(self, validator):
        source = """<script lang="ts" data-rule="count > 0">
function real(): number {
    return 1;
}
</script>
"""
        result = validator.collect_implementation_artifacts(source, "App.svelte")

        assert result.errors == []
        assert _find(result.artifacts, "real", ArtifactKind.FUNCTION) is not None

    def test_combines_module_and_instance_scripts_in_document_order(self, validator):
        source = """<script context="module" lang="ts">
export function loadConfig() {
    return {};
}
</script>

<script lang="ts">
export function renderWidget() {
    return loadConfig();
}
</script>
"""
        result = validator.collect_implementation_artifacts(source, "App.svelte")

        assert _find(result.artifacts, "loadConfig", ArtifactKind.FUNCTION) is not None
        assert (
            _find(result.artifacts, "renderWidget", ArtifactKind.FUNCTION) is not None
        )


class TestSupportedExtensions:
    def test_svelte_extension(self):
        assert SvelteValidator.supported_extensions() == (".svelte",)

    def test_can_validate(self, validator):
        assert validator.can_validate("App.svelte") is True
        assert validator.can_validate("app.ts") is False


class TestSvelteNoScript:
    def test_no_script_tag_returns_empty(self, validator):
        """Svelte file with only markup returns empty artifacts."""
        source = "<div>Hello</div>"
        result = validator.collect_implementation_artifacts(source, "comp.svelte")
        assert result.artifacts == []

    def test_no_script_behavioral_returns_empty(self, validator):
        """Behavioral collection on markup-only Svelte file returns empty."""
        source = "<p>Just markup</p>"
        result = validator.collect_behavioral_artifacts(source, "comp.svelte")
        assert result.artifacts == []


class TestSvelteBehavioralCollection:
    def test_behavioral_collection_from_script(self, validator):
        """Behavioral artifacts collected from script block."""
        source = '<script lang="ts">\nimport { onMount } from "svelte";\nonMount(() => {});\n</script>\n<div>Hello</div>'
        result = validator.collect_behavioral_artifacts(source, "test.svelte")
        # Should not crash, may or may not find artifacts
        assert hasattr(result, "artifacts")
        names = {a.name for a in result.artifacts}
        assert "onMount" in names

    def test_behavioral_empty_script(self, validator):
        """Behavioral collection on empty script returns empty artifacts."""
        source = "<script></script>\n<div>Hi</div>"
        result = validator.collect_behavioral_artifacts(source, "test.svelte")
        assert hasattr(result, "artifacts")

    def test_get_test_function_bodies_delegates_to_typescript(self, validator):
        """Svelte test body extraction should use the TypeScript validator hook."""
        source = """<script lang="ts">
it("test_svelte_fetch", () => {
    fetchData("/api/svelte");
});
</script>

<h1>Test</h1>
"""
        bodies = validator.get_test_function_bodies(source, "component.test.svelte")

        assert "test_svelte_fetch" in bodies
        assert "fetchData" in bodies["test_svelte_fetch"]
        assert "/api/svelte" in bodies["test_svelte_fetch"]

    def test_get_test_function_bodies_ignores_commented_script(self, validator):
        source = """<!-- <script>
it("test_commented_out", () => {
    callCommentedCode();
});
</script> -->

<script lang="ts">
it("test_real_svelte_body", () => {
    callRealCode();
});
</script>
"""
        bodies = validator.get_test_function_bodies(source, "component.test.svelte")

        assert "test_commented_out" not in bodies
        assert "test_real_svelte_body" in bodies
        assert "callRealCode" in bodies["test_real_svelte_body"]


# ---------------------------------------------------------------------------
# Semantic Reference Index: validator-owned resolver methods
# ---------------------------------------------------------------------------


class TestSvelteResolverMethods:
    """Verify SvelteValidator provides module_path and resolve_reexport."""

    def test_module_path_strips_svelte_extension(
        self, validator: SvelteValidator, tmp_path: Path
    ) -> None:
        target = tmp_path / "src" / "components" / "App.svelte"
        target.parent.mkdir(parents=True)
        target.write_text("")

        result = validator.module_path(target, tmp_path)
        assert result == "src/components/App"

    def test_resolve_reexport_delegates_to_ts_resolver(
        self, validator: SvelteValidator, tmp_path: Path
    ) -> None:
        models = tmp_path / "src" / "models"
        models.mkdir(parents=True)
        (models / "index.ts").write_text("export { Foo } from './user';\n")
        (models / "user.ts").write_text("export class Foo {}\n")

        result = validator.resolve_reexport("src/models", "Foo", tmp_path)
        assert result == ("src/models/user", "Foo")


# ---------------------------------------------------------------------------
# Identity-aware collection: module_path and import_source on artifacts
# ---------------------------------------------------------------------------


class TestSvelteIdentityAwareCollection:
    def test_impl_artifact_carries_module_path(
        self, validator: SvelteValidator
    ) -> None:
        source = """<script lang="ts">
export function greet(name: string): string {
    return `Hello, ${name}!`;
}
</script>

<h1>{greet('World')}</h1>
"""
        result = validator.collect_implementation_artifacts(
            source, "src/lib/Greeter.svelte"
        )
        greet = _find(result.artifacts, "greet")
        assert greet is not None
        assert greet.module_path is not None
        assert greet.module_path == "src/lib/Greeter"

    def test_behavioral_import_records_source(self, validator: SvelteValidator) -> None:
        source = """<script lang="ts">
import { onMount } from "svelte";

onMount(() => {
    console.log("mounted");
});
</script>

<div>Hello</div>
"""
        result = validator.collect_behavioral_artifacts(
            source, "src/routes/test.svelte"
        )
        on_mount = _find(result.artifacts, "onMount")
        assert on_mount is not None
        assert on_mount.import_source == "svelte"


# ---------------------------------------------------------------------------
# Integration: identity matcher works with Svelte artifacts
# ---------------------------------------------------------------------------


class TestSvelteIdentityMatching:
    def test_matcher_rejects_wrong_module_for_svelte_artifact(
        self, validator: SvelteValidator, tmp_path: Path
    ) -> None:
        source = """<script lang="ts">
import * as utils from './utils';

it("uses utils.go", () => {
    utils.go();
});
</script>
"""
        result = validator.collect_behavioral_artifacts(
            source, "src/models/test_x.svelte"
        )

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

    def test_barrel_reexport_resolves_for_svelte_behavioral(
        self, validator: SvelteValidator, tmp_path: Path
    ) -> None:
        models = tmp_path / "src" / "models"
        models.mkdir(parents=True)
        (models / "index.ts").write_text("export { Widget } from './widget';\n")
        (models / "widget.ts").write_text("export class Widget {}\n")

        source = """<script lang="ts">
import { Widget } from './models';

it("uses Widget", () => {
    const w = new Widget();
});
</script>
"""
        result = validator.collect_behavioral_artifacts(source, "src/test_x.svelte")

        artifact = FoundArtifact(
            kind=ArtifactKind.CLASS,
            name="Widget",
            module_path="src/models/widget",
        )

        assert match_artifact_to_references(
            artifact,
            result.artifacts,
            tmp_path,
            reexport_resolver=validator.resolve_reexport,
        )

    def test_explicit_svelte_import_matches_extensionless_identity(
        self, validator: SvelteValidator, tmp_path: Path
    ) -> None:
        """Regression: import Foo from './Foo.svelte' must match
        artifact module_path='src/components/Foo' (extensionless)."""
        source = """<script lang="ts">
import Foo from './Foo.svelte';

it("uses Foo", () => {
    Foo();
});
</script>
"""
        result = validator.collect_behavioral_artifacts(
            source, "src/components/test.svelte"
        )

        foo_ref = _find(result.artifacts, "Foo")
        assert foo_ref is not None
        assert foo_ref.import_source == "src/components/Foo"

        artifact = FoundArtifact(
            kind=ArtifactKind.CLASS,
            name="Foo",
            module_path="src/components/Foo",
        )

        assert match_artifact_to_references(
            artifact,
            result.artifacts,
            tmp_path,
            reexport_resolver=validator.resolve_reexport,
        )
