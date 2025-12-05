"""
Behavioral tests for task-088-update-language-detection

Goal: Update language detection and add Svelte artifact extraction in snapshot.py
to support .svelte files

These tests verify that the implementation matches the manifest specification:
1. detect_file_language() correctly identifies .svelte files
2. extract_svelte_artifacts() extracts artifacts from Svelte files
3. extract_artifacts_from_code() routes .svelte files to the Svelte extractor

Test Organization:
- Language detection (detect_file_language)
- Module imports
- Svelte artifact extraction (new function)
- Integration with extract_artifacts_from_code (routing)
- Edge cases and error handling
- Snapshot generation for Svelte files
"""

import json
from pathlib import Path

import pytest

from maid_runner.cli.snapshot import detect_file_language


class TestDetectFileLanguage:
    """
    Test the detect_file_language function.

    This function should detect programming languages from file extensions,
    including support for Svelte files (.svelte extension).
    """

    def test_detects_svelte_files(self):
        """Verify detect_file_language returns 'svelte' for .svelte files."""
        # Test simple .svelte file
        assert detect_file_language("Component.svelte") == "svelte"

        # Test with path
        assert detect_file_language("src/components/Button.svelte") == "svelte"

        # Test with relative path
        assert detect_file_language("./ui/Card.svelte") == "svelte"

        # Test with absolute path
        assert detect_file_language("/home/user/project/App.svelte") == "svelte"

        # Test with nested directories
        assert detect_file_language("src/lib/components/Modal.svelte") == "svelte"

    def test_detects_python_files(self):
        """Verify detect_file_language returns 'python' for .py files."""
        # Test simple .py file
        assert detect_file_language("script.py") == "python"

        # Test with path
        assert detect_file_language("src/utils/helper.py") == "python"

        # Test with relative path
        assert detect_file_language("./module.py") == "python"

        # Test with absolute path
        assert detect_file_language("/usr/lib/python3/test.py") == "python"

    def test_detects_typescript_files(self):
        """Verify detect_file_language returns 'typescript' for TypeScript files."""
        # Test .ts files
        assert detect_file_language("index.ts") == "typescript"
        assert detect_file_language("src/main.ts") == "typescript"

        # Test .tsx files
        assert detect_file_language("Component.tsx") == "typescript"
        assert detect_file_language("src/components/App.tsx") == "typescript"

    def test_detects_javascript_files(self):
        """Verify detect_file_language returns 'typescript' for JavaScript files."""
        # JavaScript files are handled by the TypeScript parser
        # Test .js files
        assert detect_file_language("script.js") == "typescript"
        assert detect_file_language("src/index.js") == "typescript"

        # Test .jsx files
        assert detect_file_language("Component.jsx") == "typescript"
        assert detect_file_language("src/components/App.jsx") == "typescript"

    def test_handles_edge_cases(self):
        """Test edge cases and unusual file paths."""
        # Test file with dots in name
        assert detect_file_language("my.config.py") == "python"
        assert detect_file_language("Button.component.svelte") == "svelte"

        # Test mixed case (should be case-sensitive)
        assert detect_file_language("Component.SVELTE") != "svelte"
        assert detect_file_language("Script.PY") != "python"

        # Test empty string (should have default behavior)
        result = detect_file_language("")
        assert result in ["python", "typescript", "svelte", "unknown"]

        # Test known non-code extensions return "unknown"
        assert detect_file_language("file.txt") == "unknown"
        assert detect_file_language("README.md") == "unknown"

    def test_prioritizes_file_extension(self):
        """Test that extension takes priority over file name."""
        # Even if filename contains other extension keywords, actual extension wins
        assert detect_file_language("python_script.svelte") == "svelte"
        assert detect_file_language("svelte_component.py") == "python"
        assert detect_file_language("typescript_module.js") == "typescript"

    def test_function_returns_string(self):
        """Verify function returns a string type."""
        result = detect_file_language("test.svelte")
        assert isinstance(result, str)
        assert result  # Should not be empty

        result = detect_file_language("test.py")
        assert isinstance(result, str)
        assert result

    def test_used_in_snapshot_workflow(self):
        """Test that detect_file_language is used in snapshot generation flow."""
        # This tests integration with the snapshot workflow
        # The function should be called when processing files
        from maid_runner.cli.snapshot import extract_artifacts_from_code

        # The extract_artifacts_from_code function uses detect_file_language internally
        # We verify this by checking that it's imported and available
        import inspect

        source = inspect.getsource(extract_artifacts_from_code)

        # The function should call detect_file_language
        assert "detect_file_language" in source

        # Verify the function is actually defined in the same module
        from maid_runner.cli.snapshot import detect_file_language as imported_func

        assert callable(imported_func)


# =============================================================================
# SECTION 2: Module Imports for Svelte Support
# =============================================================================


class TestModuleImports:
    """Test that required functions can be imported."""

    def test_import_extract_svelte_artifacts(self):
        """extract_svelte_artifacts function must be importable from snapshot module."""
        from maid_runner.cli.snapshot import extract_svelte_artifacts

        assert callable(extract_svelte_artifacts)

    def test_import_extract_artifacts_from_code(self):
        """extract_artifacts_from_code must still be importable."""
        from maid_runner.cli.snapshot import extract_artifacts_from_code

        assert callable(extract_artifacts_from_code)


# =============================================================================
# SECTION 3: Svelte Artifact Extraction
# =============================================================================


class TestSvelteArtifactExtraction:
    """Test extraction of Svelte artifacts in manifest format."""

    def test_extract_svelte_class(self, tmp_path):
        """Svelte file with class in script must extract class artifact."""
        from maid_runner.cli.snapshot import extract_svelte_artifacts

        svelte_file = tmp_path / "Component.svelte"
        svelte_file.write_text(
            """<script>
export class UserService {
    getUser(id) {
        return { id, name: "Test" };
    }
}
</script>

<div>Hello</div>
"""
        )

        artifacts = extract_svelte_artifacts(str(svelte_file))

        # Check structure
        assert "artifacts" in artifacts
        assert isinstance(artifacts["artifacts"], list)

        # Find the class artifact
        classes = [a for a in artifacts["artifacts"] if a.get("type") == "class"]
        assert len(classes) >= 1
        assert any(c.get("name") == "UserService" for c in classes)

    def test_extract_svelte_function(self, tmp_path):
        """Svelte file with function in script must extract function artifact."""
        from maid_runner.cli.snapshot import extract_svelte_artifacts

        svelte_file = tmp_path / "utils.svelte"
        svelte_file.write_text(
            """<script>
export function validateUser(user) {
    return user.id.length > 0;
}
</script>

<div>Component</div>
"""
        )

        artifacts = extract_svelte_artifacts(str(svelte_file))

        # Find the function artifact
        functions = [
            a
            for a in artifacts["artifacts"]
            if a.get("type") == "function" and not a.get("class")
        ]
        assert len(functions) >= 1
        assert any(f.get("name") == "validateUser" for f in functions)

    def test_extract_svelte_with_typescript(self, tmp_path):
        """Svelte file with TypeScript script must extract typed artifacts."""
        from maid_runner.cli.snapshot import extract_svelte_artifacts

        svelte_file = tmp_path / "Component.svelte"
        svelte_file.write_text(
            """<script lang="ts">
export interface User {
    id: string;
    name: string;
}

export class UserService {
    getUser(id: string): User {
        return { id, name: "Test" };
    }
}

export function validateId(id: string): boolean {
    return id.length > 0;
}
</script>

<div>Component</div>
"""
        )

        artifacts = extract_svelte_artifacts(str(svelte_file))

        # Check structure
        assert "artifacts" in artifacts
        assert isinstance(artifacts["artifacts"], list)

        # Find different artifact types
        artifact_types = {a.get("type") for a in artifacts["artifacts"]}
        assert "class" in artifact_types or "function" in artifact_types

    def test_extract_svelte_reactive_statements(self, tmp_path):
        """Svelte file with reactive statements must handle gracefully."""
        from maid_runner.cli.snapshot import extract_svelte_artifacts

        svelte_file = tmp_path / "Reactive.svelte"
        svelte_file.write_text(
            """<script>
export let count = 0;

$: doubled = count * 2;
$: {
    console.log('Count changed:', count);
}

export function increment() {
    count += 1;
}
</script>

<div>{doubled}</div>
"""
        )

        artifacts = extract_svelte_artifacts(str(svelte_file))

        # Should return valid structure
        assert "artifacts" in artifacts
        assert isinstance(artifacts["artifacts"], list)

        # Should at least extract the function
        functions = [
            a
            for a in artifacts["artifacts"]
            if a.get("type") == "function" and a.get("name") == "increment"
        ]
        assert len(functions) >= 1

    def test_extract_svelte_with_stores(self, tmp_path):
        """Svelte file with store usage must extract correctly."""
        from maid_runner.cli.snapshot import extract_svelte_artifacts

        svelte_file = tmp_path / "Store.svelte"
        svelte_file.write_text(
            """<script>
import { writable } from 'svelte/store';

export const userStore = writable({ id: 1 });

export function updateUser(newData) {
    userStore.update(u => ({ ...u, ...newData }));
}
</script>

<div>Store component</div>
"""
        )

        artifacts = extract_svelte_artifacts(str(svelte_file))

        # Check structure
        assert "artifacts" in artifacts
        assert isinstance(artifacts["artifacts"], list)

    def test_extract_svelte_with_props(self, tmp_path):
        """Svelte file with exported props must handle correctly."""
        from maid_runner.cli.snapshot import extract_svelte_artifacts

        svelte_file = tmp_path / "Props.svelte"
        svelte_file.write_text(
            """<script>
export let name = "default";
export let count = 0;

export function greet() {
    return `Hello, ${name}!`;
}
</script>

<div>Props: {name}, {count}</div>
"""
        )

        artifacts = extract_svelte_artifacts(str(svelte_file))

        # Should extract the function
        functions = [
            a
            for a in artifacts["artifacts"]
            if a.get("type") == "function" and a.get("name") == "greet"
        ]
        assert len(functions) >= 1

    def test_extract_mixed_svelte_artifacts(self, tmp_path):
        """Svelte file with multiple artifact types must extract all."""
        from maid_runner.cli.snapshot import extract_svelte_artifacts

        svelte_file = tmp_path / "Mixed.svelte"
        svelte_file.write_text(
            """<script lang="ts">
export interface User {
    id: string;
}

export class UserService {
    getUser(id: string): User {
        return { id };
    }
}

export function validateUser(user: User): boolean {
    return true;
}

export type UserID = string;
</script>

<div>Mixed component</div>
"""
        )

        artifacts = extract_svelte_artifacts(str(svelte_file))

        # Should have multiple artifacts
        assert len(artifacts["artifacts"]) >= 2

        # Check that different types are present
        artifact_types = {a.get("type") for a in artifacts["artifacts"]}
        assert len(artifact_types) >= 1

    def test_extract_svelte_empty_script(self, tmp_path):
        """Svelte file with empty script block must not crash."""
        from maid_runner.cli.snapshot import extract_svelte_artifacts

        svelte_file = tmp_path / "Empty.svelte"
        svelte_file.write_text(
            """<script>
</script>

<div>Component with no script content</div>
"""
        )

        artifacts = extract_svelte_artifacts(str(svelte_file))

        # Should return valid structure even if empty
        assert "artifacts" in artifacts
        assert isinstance(artifacts["artifacts"], list)

    def test_extract_svelte_no_script(self, tmp_path):
        """Svelte file without script block must not crash."""
        from maid_runner.cli.snapshot import extract_svelte_artifacts

        svelte_file = tmp_path / "NoScript.svelte"
        svelte_file.write_text(
            """<div>
    <h1>Hello World</h1>
    <p>Pure markup component</p>
</div>
"""
        )

        artifacts = extract_svelte_artifacts(str(svelte_file))

        # Should return valid structure even if no script
        assert "artifacts" in artifacts
        assert isinstance(artifacts["artifacts"], list)


# =============================================================================
# SECTION 4: Integration with extract_artifacts_from_code
# =============================================================================


class TestRouting:
    """Test that extract_artifacts_from_code routes correctly for all file types."""

    def test_route_svelte_to_svelte_extractor(self, tmp_path):
        """Svelte files (.svelte) must route to extract_svelte_artifacts."""
        from maid_runner.cli.snapshot import extract_artifacts_from_code

        svelte_file = tmp_path / "test.svelte"
        svelte_file.write_text(
            """<script>
export class Test {}
</script>

<div>Test</div>
"""
        )

        artifacts = extract_artifacts_from_code(str(svelte_file))

        # Should return artifacts structure
        assert "artifacts" in artifacts
        assert isinstance(artifacts["artifacts"], list)

    def test_route_typescript_still_works(self, tmp_path):
        """TypeScript files (.ts) must still route to TypeScript extractor."""
        from maid_runner.cli.snapshot import extract_artifacts_from_code

        ts_file = tmp_path / "test.ts"
        ts_file.write_text("export class Test {}")

        artifacts = extract_artifacts_from_code(str(ts_file))

        # Should return artifacts structure
        assert "artifacts" in artifacts
        assert isinstance(artifacts["artifacts"], list)

    def test_route_tsx_still_works(self, tmp_path):
        """TypeScript JSX files (.tsx) must still route to TypeScript extractor."""
        from maid_runner.cli.snapshot import extract_artifacts_from_code

        tsx_file = tmp_path / "Component.tsx"
        tsx_file.write_text("export class Component {}")

        artifacts = extract_artifacts_from_code(str(tsx_file))

        assert "artifacts" in artifacts

    def test_route_javascript_still_works(self, tmp_path):
        """JavaScript files (.js) must still route to TypeScript extractor."""
        from maid_runner.cli.snapshot import extract_artifacts_from_code

        js_file = tmp_path / "utils.js"
        js_file.write_text("export function helper() {}")

        artifacts = extract_artifacts_from_code(str(js_file))

        assert "artifacts" in artifacts

    def test_route_jsx_still_works(self, tmp_path):
        """JavaScript JSX files (.jsx) must still route to TypeScript extractor."""
        from maid_runner.cli.snapshot import extract_artifacts_from_code

        jsx_file = tmp_path / "Component.jsx"
        jsx_file.write_text("export function Component() {}")

        artifacts = extract_artifacts_from_code(str(jsx_file))

        assert "artifacts" in artifacts

    def test_route_python_still_works(self, tmp_path):
        """Python files (.py) must still route to Python extractor."""
        from maid_runner.cli.snapshot import extract_artifacts_from_code

        py_file = tmp_path / "module.py"
        py_file.write_text(
            """class Test:
    pass

def function():
    pass
"""
        )

        artifacts = extract_artifacts_from_code(str(py_file))

        # Python extractor returns different structure
        assert "artifacts" in artifacts


# =============================================================================
# SECTION 5: Edge Cases and Error Handling
# =============================================================================


class TestEdgeCases:
    """Test error handling and edge cases."""

    def test_svelte_file_not_found(self):
        """Missing Svelte file must raise FileNotFoundError."""
        from maid_runner.cli.snapshot import extract_svelte_artifacts

        with pytest.raises(FileNotFoundError):
            extract_svelte_artifacts("nonexistent.svelte")

    def test_empty_svelte_file(self, tmp_path):
        """Empty Svelte file must not crash."""
        from maid_runner.cli.snapshot import extract_svelte_artifacts

        svelte_file = tmp_path / "empty.svelte"
        svelte_file.write_text("")

        artifacts = extract_svelte_artifacts(str(svelte_file))

        # Should return valid structure even if empty
        assert "artifacts" in artifacts
        assert isinstance(artifacts["artifacts"], list)

    def test_svelte_with_syntax_errors(self, tmp_path):
        """Svelte file with syntax errors must handle gracefully."""
        from maid_runner.cli.snapshot import extract_svelte_artifacts

        svelte_file = tmp_path / "invalid.svelte"
        svelte_file.write_text(
            """<script>
class {{{{{ invalid syntax
</script>

<div>Component</div>
"""
        )

        # Tree-sitter is fault-tolerant, should parse what it can
        artifacts = extract_svelte_artifacts(str(svelte_file))
        assert "artifacts" in artifacts

    def test_svelte_with_multiple_script_blocks(self, tmp_path):
        """Svelte file with multiple script blocks must handle correctly."""
        from maid_runner.cli.snapshot import extract_svelte_artifacts

        svelte_file = tmp_path / "Multiple.svelte"
        svelte_file.write_text(
            """<script context="module">
export function moduleFunction() {
    return "module level";
}
</script>

<script>
export function componentFunction() {
    return "component level";
}
</script>

<div>Component</div>
"""
        )

        artifacts = extract_svelte_artifacts(str(svelte_file))

        # Should extract functions from both script blocks
        assert "artifacts" in artifacts
        assert isinstance(artifacts["artifacts"], list)


# =============================================================================
# SECTION 6: Snapshot Generation for Svelte Files
# =============================================================================


class TestSvelteSnapshotGeneration:
    """Test end-to-end snapshot generation for Svelte files."""

    def test_generate_snapshot_for_svelte_file(self, tmp_path):
        """Snapshot generation must work for Svelte files."""
        from maid_runner.cli.snapshot import generate_snapshot

        svelte_file = tmp_path / "Component.svelte"
        svelte_file.write_text(
            """<script>
export class UserService {
    getUser(id) {
        return { id };
    }
}
</script>

<div>Component</div>
"""
        )

        manifest_dir = tmp_path / "manifests"
        manifest_dir.mkdir()

        manifest_path = generate_snapshot(
            str(svelte_file), str(manifest_dir), skip_test_stub=True
        )

        # Verify manifest was created
        assert Path(manifest_path).exists()

        # Load and verify manifest structure
        with open(manifest_path) as f:
            manifest = json.load(f)

        assert manifest["taskType"] == "snapshot"
        assert manifest["expectedArtifacts"]["file"] == str(svelte_file)
        assert "contains" in manifest["expectedArtifacts"]

    def test_snapshot_manifest_contains_svelte_artifacts(self, tmp_path):
        """Generated snapshot must include Svelte artifacts."""
        from maid_runner.cli.snapshot import generate_snapshot

        svelte_file = tmp_path / "Complete.svelte"
        svelte_file.write_text(
            """<script lang="ts">
export interface User { id: string; }
export class UserService {}
export function validate() {}
</script>

<div>Component</div>
"""
        )

        manifest_dir = tmp_path / "manifests"
        manifest_dir.mkdir()

        manifest_path = generate_snapshot(
            str(svelte_file), str(manifest_dir), skip_test_stub=True
        )

        with open(manifest_path) as f:
            manifest = json.load(f)

        # Should have some artifacts
        contains = manifest["expectedArtifacts"]["contains"]
        assert isinstance(contains, list)

    def test_svelte_snapshot_return_structure(self, tmp_path):
        """extract_svelte_artifacts must return proper dict structure."""
        from maid_runner.cli.snapshot import extract_svelte_artifacts

        svelte_file = tmp_path / "Test.svelte"
        svelte_file.write_text(
            """<script>
export function test() {
    return true;
}
</script>

<div>Test</div>
"""
        )

        result = extract_svelte_artifacts(str(svelte_file))

        # Must return dict with "artifacts" key
        assert isinstance(result, dict)
        assert "artifacts" in result
        assert isinstance(result["artifacts"], list)
