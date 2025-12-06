"""
Behavioral tests for Task-058: TypeScript Test Stub Generation

Tests validate the TypeScript test stub generation functionality by:
1. Detecting file language (Python vs TypeScript)
2. Generating .spec.ts files for TypeScript projects
3. Using TypeScript/Jest syntax instead of Python/pytest
4. Handling TypeScript-specific artifacts (interfaces, types, enums, namespaces)
5. Generating proper ES6 import statements
6. Using appropriate test runner commands (jest vs pytest)

These tests USE the declared artifacts to verify actual behavior.
"""

import json
import subprocess
import sys
from pathlib import Path
from unittest.mock import mock_open, patch
import pytest

# Add parent directory to path to enable imports
sys.path.insert(0, str(Path(__file__).parent.parent))

# Import private test modules for task-058 private artifacts
from tests._test_task_058_private_helpers import (  # noqa: F401
    TestGenerateTypeScriptTestStub,
    TestGeneratePythonTestStub,
)


@pytest.fixture
def mock_file_write():
    """Fixture to mock file writing and capture content."""

    def _mock_generate_stub(manifest_data, manifest_path):
        """Helper to generate stub with mocked file I/O and return written content."""
        from maid_runner.cli.snapshot import generate_test_stub

        # Store written content
        written_content = []
        original_open = open

        def selective_open(file, mode="r", *args, **kwargs):
            """Mock open that allows reading manifest but captures writes."""
            # Allow reading the manifest file
            if str(file) == manifest_path and "r" in mode:
                return original_open(file, mode, *args, **kwargs)
            # Mock writing the stub file
            elif "w" in mode:
                m = mock_open()()
                # Capture written content
                original_write = m.write

                def capture_write(text):
                    written_content.append(text)
                    return original_write(text)

                m.write = capture_write
                return m
            # Default: use real open
            return original_open(file, mode, *args, **kwargs)

        with patch("builtins.open", selective_open):
            with patch("pathlib.Path.mkdir"):
                stub_path = generate_test_stub(manifest_data, manifest_path)

        return stub_path, "".join(written_content)

    return _mock_generate_stub


class TestGetTestStubPath:
    """Test the get_test_stub_path function with TypeScript support."""

    def test_returns_py_for_python_files(self, tmp_path: Path):
        """Test that Python files get .py test extensions."""
        from maid_runner.cli.snapshot import get_test_stub_path

        # Create a manifest for a Python file
        manifest_data = {
            "goal": "Test Python file",
            "expectedArtifacts": {
                "file": "src/example.py",
                "contains": [{"type": "function", "name": "example"}],
            },
        }

        manifest_path = str(tmp_path / "task-001-python.manifest.json")
        with open(manifest_path, "w") as f:
            json.dump(manifest_data, f)

        stub_path = get_test_stub_path(manifest_path)

        # Should return .py extension
        assert stub_path.endswith(".py")
        assert "test_" in stub_path

    def test_returns_spec_ts_for_typescript_files(self, tmp_path: Path):
        """Test that TypeScript files get .spec.ts test extensions."""
        from maid_runner.cli.snapshot import get_test_stub_path

        # Create a manifest for a TypeScript file
        manifest_data = {
            "goal": "Test TypeScript file",
            "expectedArtifacts": {
                "file": "src/calculator.ts",
                "contains": [{"type": "class", "name": "Calculator"}],
            },
        }

        manifest_path = str(tmp_path / "task-002-typescript.manifest.json")
        with open(manifest_path, "w") as f:
            json.dump(manifest_data, f)

        stub_path = get_test_stub_path(manifest_path)

        # Should return .spec.ts extension for TypeScript
        assert stub_path.endswith(".spec.ts")

    def test_handles_tsx_files(self, tmp_path: Path):
        """Test that .tsx files get .spec.ts test extensions."""
        from maid_runner.cli.snapshot import get_test_stub_path

        manifest_data = {
            "goal": "Test TSX component",
            "expectedArtifacts": {
                "file": "src/components/Button.tsx",
                "contains": [{"type": "function", "name": "Button"}],
            },
        }

        manifest_path = str(tmp_path / "task-003-tsx.manifest.json")
        with open(manifest_path, "w") as f:
            json.dump(manifest_data, f)

        stub_path = get_test_stub_path(manifest_path)

        assert stub_path.endswith(".spec.ts")

    def test_handles_js_files(self, tmp_path: Path):
        """Test that .js files get .spec.ts test extensions."""
        from maid_runner.cli.snapshot import get_test_stub_path

        manifest_data = {
            "goal": "Test JavaScript file",
            "expectedArtifacts": {
                "file": "src/utils.js",
                "contains": [{"type": "function", "name": "formatDate"}],
            },
        }

        manifest_path = str(tmp_path / "task-004-js.manifest.json")
        with open(manifest_path, "w") as f:
            json.dump(manifest_data, f)

        stub_path = get_test_stub_path(manifest_path)

        assert stub_path.endswith(".spec.ts")


class TestPythonStubBackwardCompatibility:
    """Test that Python stub generation still works (backward compatibility)."""

    def test_python_files_still_generate_py_stubs(
        self, tmp_path: Path, mock_file_write
    ):
        """Test that Python files still generate .py test stubs."""
        manifest_data = {
            "goal": "Test Python stub compatibility",
            "expectedArtifacts": {
                "file": "validators/checker.py",
                "contains": [{"type": "function", "name": "validate"}],
            },
        }

        manifest_path = str(tmp_path / "task-py-001.manifest.json")
        with open(manifest_path, "w") as f:
            json.dump(manifest_data, f)

        stub_path, content = mock_file_write(manifest_data, manifest_path)

        # Should still create .py file
        assert stub_path.endswith(".py")

        # Should still use pytest syntax
        assert "import pytest" in content
        assert "pytest.fail" in content

    def test_python_stubs_use_pytest_syntax(self, tmp_path: Path, mock_file_write):
        """Test that Python stubs still use pytest syntax."""
        manifest_data = {
            "goal": "Test pytest syntax",
            "expectedArtifacts": {
                "file": "src/calculator.py",
                "contains": [{"type": "class", "name": "Calculator"}],
            },
        }

        manifest_path = str(tmp_path / "task-py-002.manifest.json")
        with open(manifest_path, "w") as f:
            json.dump(manifest_data, f)

        stub_path, content = mock_file_write(manifest_data, manifest_path)

        # Should use pytest
        assert "import pytest" in content
        assert "class Test" in content or "def test_" in content


class TestValidationCommandGeneration:
    """Test that validation commands use appropriate test runners."""

    def test_typescript_manifests_use_jest_validation(self, tmp_path: Path):
        """Test that TypeScript snapshots use jest in validationCommand."""
        from maid_runner.cli.snapshot import generate_snapshot

        # Create a TypeScript file
        ts_code = """
export function add(a: number, b: number): number {
    return a + b;
}
"""
        source_file = tmp_path / "calculator.ts"
        source_file.write_text(ts_code)

        output_dir = tmp_path / "manifests"
        output_dir.mkdir()

        try:
            # Generate snapshot
            manifest_path = generate_snapshot(str(source_file), str(output_dir))

            # Read the manifest
            with open(manifest_path, "r") as f:
                manifest = json.load(f)

            # Should use jest or npm test in validationCommand
            validation_cmd = manifest.get("validationCommand", [])

            # Should contain jest or npm
            cmd_str = " ".join(validation_cmd)
            assert (
                "jest" in cmd_str or "npm" in cmd_str
            ), f"Expected jest or npm in validation command, got: {validation_cmd}"
        finally:
            # Cleanup generated stub files
            for stub_file in Path("tests").glob("task-*-snapshot-calculator.spec.ts"):
                stub_file.unlink(missing_ok=True)
            for stub_file in Path("tests").glob("test_task_*_snapshot_calculator.py"):
                stub_file.unlink(missing_ok=True)

    def test_python_manifests_use_pytest_validation(self, tmp_path: Path):
        """Test that Python snapshots still use pytest in validationCommand."""
        from maid_runner.cli.snapshot import generate_snapshot

        # Create a Python file
        py_code = """
def add(a, b):
    return a + b
"""
        source_file = tmp_path / "calculator.py"
        source_file.write_text(py_code)

        output_dir = tmp_path / "manifests"
        output_dir.mkdir()

        try:
            # Generate snapshot
            manifest_path = generate_snapshot(str(source_file), str(output_dir))

            # Read the manifest
            with open(manifest_path, "r") as f:
                manifest = json.load(f)

            # Should use pytest in validationCommand
            validation_cmd = manifest.get("validationCommand", [])
            assert "pytest" in validation_cmd
        finally:
            # Cleanup generated stub files
            for stub_file in Path("tests").glob("test_task_*_snapshot_calculator.py"):
                stub_file.unlink(missing_ok=True)


class TestCLIIntegration:
    """Test CLI integration for TypeScript stub generation."""

    def test_generate_stubs_creates_typescript_stub(self, tmp_path: Path):
        """Test that generate-stubs creates .spec.ts for TypeScript manifests."""
        manifest_data = {
            "goal": "Generate TypeScript stub",
            "taskType": "create",
            "creatableFiles": ["feature.ts"],
            "expectedArtifacts": {
                "file": "src/feature.ts",
                "contains": [
                    {
                        "type": "function",
                        "name": "newFeature",
                        "args": [{"name": "data"}],
                    }
                ],
            },
            "validationCommand": [],
        }

        manifest_file = tmp_path / "task-typescript.manifest.json"
        manifest_file.write_text(json.dumps(manifest_data, indent=2))

        try:
            # Run generate-stubs
            result = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "maid_runner.cli.main",
                    "generate-stubs",
                    str(manifest_file),
                ],
                capture_output=True,
                text=True,
            )

            # Should succeed
            assert result.returncode == 0

            # Check output mentions .spec.ts
            assert ".spec.ts" in result.stdout
        finally:
            # Cleanup generated stub files
            for stub_file in Path("tests").glob("task-typescript.spec.ts"):
                stub_file.unlink(missing_ok=True)
            for stub_file in Path("tests").glob("test_task_typescript.py"):
                stub_file.unlink(missing_ok=True)
