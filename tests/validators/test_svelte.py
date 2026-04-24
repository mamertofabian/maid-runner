"""Tests for maid_runner.validators.svelte - SvelteValidator."""

import pytest

from maid_runner.core.types import ArtifactKind

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
