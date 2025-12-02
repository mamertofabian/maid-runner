"""
Behavioral tests for Task-071: Fix Snapshot Validation Command Language

Tests validate the fix for get_test_stub_path generating incorrect test file paths
when called before the manifest is written to disk. The fix adds an optional
target_language parameter that allows passing the known language directly.

These tests verify:
1. When target_language="typescript" is passed, returns .spec.ts path
2. When target_language="python" is passed, returns test_*.py path
3. When target_language=None (default), falls back to reading manifest
4. Existing behavior is preserved for manifests that exist on disk

These tests USE the declared artifacts to verify actual behavior.
"""

import json
from pathlib import Path

from maid_runner.cli.snapshot import get_test_stub_path


class TestGetTestStubPathTargetLanguageParameter:
    """Test the target_language parameter of get_test_stub_path."""

    def test_typescript_language_returns_spec_ts_extension(self, tmp_path: Path):
        """Test that target_language='typescript' returns .spec.ts path without reading manifest."""
        # Create a manifest path (but DON'T write the file - simulates pre-write scenario)
        manifest_path = str(tmp_path / "task-001-feature.manifest.json")

        # Call with explicit target_language - should work even without manifest file
        stub_path = get_test_stub_path(manifest_path, target_language="typescript")

        # Should return .spec.ts extension
        assert stub_path.endswith(
            ".spec.ts"
        ), f"Expected .spec.ts extension, got: {stub_path}"
        # Should be in tests directory
        assert stub_path.startswith(
            "tests/"
        ), f"Expected tests/ prefix, got: {stub_path}"
        # Should NOT have test_ prefix (TypeScript convention)
        assert (
            "test_" not in stub_path
        ), f"TypeScript should not have test_ prefix: {stub_path}"

    def test_python_language_returns_py_extension(self, tmp_path: Path):
        """Test that target_language='python' returns test_*.py path without reading manifest."""
        # Create a manifest path (but DON'T write the file - simulates pre-write scenario)
        manifest_path = str(tmp_path / "task-002-feature.manifest.json")

        # Call with explicit target_language - should work even without manifest file
        stub_path = get_test_stub_path(manifest_path, target_language="python")

        # Should return .py extension
        assert stub_path.endswith(".py"), f"Expected .py extension, got: {stub_path}"
        # Should be in tests directory
        assert stub_path.startswith(
            "tests/"
        ), f"Expected tests/ prefix, got: {stub_path}"
        # Should have test_ prefix (Python convention)
        assert "test_" in stub_path, f"Python should have test_ prefix: {stub_path}"

    def test_none_language_reads_from_manifest(self, tmp_path: Path):
        """Test that target_language=None (default) reads language from manifest file."""
        # Create and write a manifest with TypeScript target file
        manifest_data = {
            "goal": "Test TypeScript file",
            "expectedArtifacts": {
                "file": "src/calculator.ts",
                "contains": [{"type": "function", "name": "add"}],
            },
        }
        manifest_path = tmp_path / "task-003-typescript.manifest.json"
        with open(manifest_path, "w") as f:
            json.dump(manifest_data, f)

        # Call without target_language (default None) - should read from manifest
        stub_path = get_test_stub_path(str(manifest_path))

        # Should detect TypeScript from manifest and return .spec.ts
        assert stub_path.endswith(
            ".spec.ts"
        ), f"Expected .spec.ts from manifest detection, got: {stub_path}"

    def test_none_language_defaults_to_python_when_manifest_not_found(
        self, tmp_path: Path
    ):
        """Test that target_language=None defaults to Python when manifest doesn't exist."""
        # Use a non-existent manifest path
        manifest_path = str(tmp_path / "nonexistent.manifest.json")

        # Call without target_language - should default to Python
        stub_path = get_test_stub_path(manifest_path)

        # Should default to Python (.py extension)
        assert stub_path.endswith(
            ".py"
        ), f"Expected .py extension as default, got: {stub_path}"
        assert (
            "test_" in stub_path
        ), f"Expected test_ prefix for Python, got: {stub_path}"


class TestGetTestStubPathTargetLanguageOverridesManifest:
    """Test that target_language parameter takes precedence over manifest content."""

    def test_typescript_override_for_python_manifest(self, tmp_path: Path):
        """Test that target_language='typescript' overrides Python file in manifest."""
        # Create a manifest with Python target file
        manifest_data = {
            "goal": "Test Python file",
            "expectedArtifacts": {
                "file": "src/calculator.py",  # Python file in manifest
                "contains": [{"type": "function", "name": "add"}],
            },
        }
        manifest_path = tmp_path / "task-004-python.manifest.json"
        with open(manifest_path, "w") as f:
            json.dump(manifest_data, f)

        # Call with typescript override
        stub_path = get_test_stub_path(str(manifest_path), target_language="typescript")

        # Should use typescript despite manifest having Python file
        assert stub_path.endswith(
            ".spec.ts"
        ), f"Expected .spec.ts from override, got: {stub_path}"

    def test_python_override_for_typescript_manifest(self, tmp_path: Path):
        """Test that target_language='python' overrides TypeScript file in manifest."""
        # Create a manifest with TypeScript target file
        manifest_data = {
            "goal": "Test TypeScript file",
            "expectedArtifacts": {
                "file": "src/calculator.ts",  # TypeScript file in manifest
                "contains": [{"type": "function", "name": "add"}],
            },
        }
        manifest_path = tmp_path / "task-005-typescript.manifest.json"
        with open(manifest_path, "w") as f:
            json.dump(manifest_data, f)

        # Call with python override
        stub_path = get_test_stub_path(str(manifest_path), target_language="python")

        # Should use python despite manifest having TypeScript file
        assert stub_path.endswith(
            ".py"
        ), f"Expected .py from override, got: {stub_path}"
        assert (
            "test_" in stub_path
        ), f"Expected test_ prefix for Python, got: {stub_path}"


class TestGetTestStubPathPreWriteScenario:
    """Test the specific scenario where get_test_stub_path is called before manifest is written."""

    def test_typescript_path_generation_pre_write(self, tmp_path: Path):
        """Test generating TypeScript test path before manifest exists on disk."""
        # This is the exact scenario the bug fix addresses:
        # 1. generate_snapshot() detects the file is TypeScript
        # 2. It calls get_test_stub_path() BEFORE writing the manifest
        # 3. Without target_language param, it would default to Python
        # 4. With target_language="typescript", it returns correct .spec.ts path

        manifest_path = str(tmp_path / "task-006-snapshot-calculator.manifest.json")

        # Verify manifest doesn't exist
        assert not Path(
            manifest_path
        ).exists(), "Manifest should not exist for this test"

        # Call with TypeScript language (simulating what generate_snapshot does)
        stub_path = get_test_stub_path(manifest_path, target_language="typescript")

        # Should return correct TypeScript test path
        assert stub_path.endswith(
            ".spec.ts"
        ), f"Pre-write should return .spec.ts, got: {stub_path}"
        assert "tests/" in stub_path, f"Should be in tests directory, got: {stub_path}"

    def test_python_path_generation_pre_write(self, tmp_path: Path):
        """Test generating Python test path before manifest exists on disk."""
        manifest_path = str(tmp_path / "task-007-snapshot-module.manifest.json")

        # Verify manifest doesn't exist
        assert not Path(
            manifest_path
        ).exists(), "Manifest should not exist for this test"

        # Call with Python language
        stub_path = get_test_stub_path(manifest_path, target_language="python")

        # Should return correct Python test path
        assert stub_path.endswith(
            ".py"
        ), f"Pre-write should return .py, got: {stub_path}"
        assert "test_" in stub_path, f"Should have test_ prefix, got: {stub_path}"


class TestGetTestStubPathPathFormatting:
    """Test that path formatting is correct for both languages."""

    def test_typescript_path_preserves_hyphens(self, tmp_path: Path):
        """Test that TypeScript paths preserve hyphens in manifest name."""
        manifest_path = str(tmp_path / "task-010-add-feature.manifest.json")

        stub_path = get_test_stub_path(manifest_path, target_language="typescript")

        # TypeScript should preserve hyphens
        assert (
            "task-010-add-feature.spec.ts" in stub_path
        ), f"Expected preserved hyphens, got: {stub_path}"

    def test_python_path_converts_hyphens_to_underscores(self, tmp_path: Path):
        """Test that Python paths convert hyphens to underscores."""
        manifest_path = str(tmp_path / "task-020-fix-bug.manifest.json")

        stub_path = get_test_stub_path(manifest_path, target_language="python")

        # Python should convert hyphens to underscores
        assert (
            "test_task_020_fix_bug.py" in stub_path
        ), f"Expected underscore conversion, got: {stub_path}"

    def test_snapshot_manifest_typescript_path(self, tmp_path: Path):
        """Test path generation for snapshot manifest with TypeScript."""
        manifest_path = str(tmp_path / "task-030-snapshot-calculator.manifest.json")

        stub_path = get_test_stub_path(manifest_path, target_language="typescript")

        # Should generate correct snapshot test path
        assert stub_path.endswith(".spec.ts"), f"Expected .spec.ts, got: {stub_path}"
        assert (
            "task-030-snapshot-calculator.spec.ts" in stub_path
        ), f"Unexpected path: {stub_path}"

    def test_snapshot_manifest_python_path(self, tmp_path: Path):
        """Test path generation for snapshot manifest with Python."""
        manifest_path = str(tmp_path / "task-040-snapshot-module.manifest.json")

        stub_path = get_test_stub_path(manifest_path, target_language="python")

        # Should generate correct snapshot test path
        assert stub_path.endswith(".py"), f"Expected .py, got: {stub_path}"
        assert (
            "test_task_040_snapshot_module.py" in stub_path
        ), f"Unexpected path: {stub_path}"
