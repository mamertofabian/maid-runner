"""Tests for maid_runner.validators.svelte - SvelteValidator."""

from __future__ import annotations

from pathlib import Path

import pytest

from maid_runner.core.identity import match_artifact_to_references
from maid_runner.core.types import ArtifactKind
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
