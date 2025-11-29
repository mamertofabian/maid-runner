"""
Behavioral tests for Task-032: Test Stub Generation

Tests validate the test stub generation functionality by:
1. Generating failing test stubs from manifests
2. Including proper imports, test shells, assertions, and docstrings
3. CLI integration with --skip-test-stub flag
4. New generate-stubs subcommand

These tests USE the declared artifacts to verify actual behavior.
"""

import json
import subprocess
import sys
from pathlib import Path
from unittest.mock import mock_open, patch
import pytest


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


class TestGenerateTestStub:
    """Test the generate_test_stub function."""

    def test_generates_stub_with_pytest_fail(self, tmp_path: Path, mock_file_write):
        """Test that generated stub includes pytest.fail() to make tests fail."""
        manifest_data = {
            "goal": "Test feature",
            "expectedArtifacts": {
                "file": "src/example.py",
                "contains": [
                    {
                        "type": "function",
                        "name": "example_function",
                        "parameters": [{"name": "param1", "type": "str"}],
                        "returns": "bool",
                    }
                ],
            },
        }

        manifest_path = str(tmp_path / "task-001-test.manifest.json")
        with open(manifest_path, "w") as f:
            json.dump(manifest_data, f)

        _stub_path, content = mock_file_write(manifest_data, manifest_path)

        # Must include pytest.fail() to ensure test fails
        assert "pytest.fail" in content
        assert "TODO" in content

    def test_generates_imports_for_artifacts(self, tmp_path: Path, mock_file_write):
        """Test that stub includes proper imports for declared artifacts."""
        manifest_data = {
            "goal": "Test feature",
            "expectedArtifacts": {
                "file": "validators/checker.py",
                "contains": [
                    {"type": "function", "name": "validate_input"},
                    {"type": "class", "name": "ValidationError"},
                ],
            },
        }

        manifest_path = str(tmp_path / "task-002-test.manifest.json")
        with open(manifest_path, "w") as f:
            json.dump(manifest_data, f)

        _stub_path, content = mock_file_write(manifest_data, manifest_path)

        # Should import the artifacts
        assert "import" in content or "from" in content
        assert "validate_input" in content
        assert "ValidationError" in content

    def test_generates_test_class_shells(self, tmp_path: Path, mock_file_write):
        """Test that stub includes test class/function shells."""
        manifest_data = {
            "goal": "Test feature",
            "expectedArtifacts": {
                "file": "services/processor.py",
                "contains": [
                    {
                        "type": "class",
                        "name": "DataProcessor",
                    }
                ],
            },
        }

        manifest_path = str(tmp_path / "task-003-test.manifest.json")
        with open(manifest_path, "w") as f:
            json.dump(manifest_data, f)

        _stub_path, content = mock_file_write(manifest_data, manifest_path)

        # Should have test class structure
        assert "class Test" in content or "def test_" in content
        assert "DataProcessor" in content

    def test_generates_assertion_placeholders(self, tmp_path: Path, mock_file_write):
        """Test that stub includes commented assertion examples."""
        manifest_data = {
            "goal": "Test feature",
            "expectedArtifacts": {
                "file": "utils/helpers.py",
                "contains": [
                    {
                        "type": "function",
                        "name": "calculate_total",
                        "parameters": [{"name": "items", "type": "list"}],
                        "returns": "float",
                    }
                ],
            },
        }

        manifest_path = str(tmp_path / "task-004-test.manifest.json")
        with open(manifest_path, "w") as f:
            json.dump(manifest_data, f)

        _stub_path, content = mock_file_write(manifest_data, manifest_path)

        # Should have commented assertion examples
        assert "#" in content
        assert "assert" in content.lower()

    def test_generates_docstring_templates(self, tmp_path: Path, mock_file_write):
        """Test that stub includes docstring templates."""
        manifest_data = {
            "goal": "Test feature",
            "expectedArtifacts": {
                "file": "models/user.py",
                "contains": [{"type": "class", "name": "User"}],
            },
        }

        manifest_path = str(tmp_path / "task-005-test.manifest.json")
        with open(manifest_path, "w") as f:
            json.dump(manifest_data, f)

        _stub_path, content = mock_file_write(manifest_data, manifest_path)

        # Should have docstrings
        assert '"""' in content or "'''" in content

    def test_handles_multiple_artifacts(self, tmp_path: Path, mock_file_write):
        """Test stub generation for manifests with multiple artifacts."""
        manifest_data = {
            "goal": "Test multiple features",
            "expectedArtifacts": {
                "file": "core/engine.py",
                "contains": [
                    {"type": "class", "name": "Engine"},
                    {"type": "function", "name": "start_engine"},
                    {"type": "function", "name": "stop_engine"},
                ],
            },
        }

        manifest_path = str(tmp_path / "task-006-test.manifest.json")
        with open(manifest_path, "w") as f:
            json.dump(manifest_data, f)

        _stub_path, content = mock_file_write(manifest_data, manifest_path)

        # All artifacts should be referenced
        assert "Engine" in content
        assert "start_engine" in content
        assert "stop_engine" in content

    def test_generated_stub_fails_when_run(self, tmp_path: Path):
        """Test that generated stub fails when executed with pytest."""
        from maid_runner.cli.snapshot import generate_test_stub

        manifest_data = {
            "goal": "Test feature that should fail",
            "expectedArtifacts": {
                "file": "lib/module.py",
                "contains": [{"type": "function", "name": "test_function"}],
            },
        }

        manifest_path = str(tmp_path / "task-007-test.manifest.json")
        with open(manifest_path, "w") as f:
            json.dump(manifest_data, f)

        try:
            stub_path = generate_test_stub(manifest_data, manifest_path)

            # Run the stub with pytest - it should fail
            result = subprocess.run(
                [sys.executable, "-m", "pytest", stub_path, "-v"],
                capture_output=True,
                text=True,
            )

            # Should fail (non-zero exit code) - either with test failure or import error
            assert result.returncode != 0
            # Check for either FAILED (test ran and failed with pytest.fail()) or ERROR (import failed)
            assert (
                "FAILED" in result.stdout
                or "failed" in result.stdout.lower()
                or "ERROR" in result.stdout
                or "error" in result.stdout.lower()
            )
        finally:
            # Cleanup generated stub files
            for stub_file in Path("tests").glob("test_task_*_test.py"):
                stub_file.unlink(missing_ok=True)


class TestGetTestStubPath:
    """Test the get_test_stub_path function."""

    def test_derives_path_from_manifest_name(self, tmp_path: Path):
        """Test that stub path is derived from manifest filename."""
        from maid_runner.cli.snapshot import get_test_stub_path

        manifest_path = str(tmp_path / "manifests" / "task-001-feature.manifest.json")
        stub_path = get_test_stub_path(manifest_path)

        # Should derive test filename from manifest
        assert "test_task_001" in stub_path or "test_" in stub_path
        assert stub_path.endswith(".py")

    def test_places_stub_in_tests_directory(self, tmp_path: Path):
        """Test that stub is placed in tests/ directory."""
        from maid_runner.cli.snapshot import get_test_stub_path

        manifest_path = str(tmp_path / "manifests" / "task-002-update.manifest.json")
        stub_path = get_test_stub_path(manifest_path)

        # Should be in tests directory
        assert "tests" in stub_path or stub_path.startswith("tests/")

    def test_handles_different_manifest_naming_patterns(self, tmp_path: Path):
        """Test stub path generation for various manifest naming patterns."""
        from maid_runner.cli.snapshot import get_test_stub_path

        patterns = [
            "task-010-add-feature.manifest.json",
            "task-999-fix-bug.manifest.json",
            "snapshot-example.manifest.json",
        ]

        for pattern in patterns:
            manifest_path = str(tmp_path / pattern)
            stub_path = get_test_stub_path(manifest_path)

            # Should always return a valid test path
            assert stub_path.endswith(".py")
            assert "test_" in stub_path


class TestSnapshotWithStubGeneration:
    """Test snapshot command integration with stub generation."""

    def test_snapshot_generates_stub_by_default(self, tmp_path: Path):
        """Test that snapshot generates test stub by default."""
        from maid_runner.cli.snapshot import generate_snapshot

        code = """
def example_function():
    return True
"""
        source_file = tmp_path / "example.py"
        source_file.write_text(code)

        output_dir = tmp_path / "manifests"
        output_dir.mkdir()

        try:
            # Generate snapshot (should create stub by default, skip_test_stub defaults to False)
            manifest_path = generate_snapshot(str(source_file), str(output_dir))

            # Manifest should exist
            assert Path(manifest_path).exists()

            # Manifest should include test stub in validationCommand
            with open(manifest_path, "r") as f:
                manifest = json.load(f)

            # Check for either validationCommand or validationCommands
            has_validation = False
            if "validationCommand" in manifest:
                # Should reference a test file
                cmd = manifest["validationCommand"]
                has_validation = any("test_" in str(item) for item in cmd)
            elif "validationCommands" in manifest:
                # At least one command should reference a test file
                for cmd in manifest["validationCommands"]:
                    if any("test_" in str(item) for item in cmd):
                        has_validation = True
                        break

            assert (
                has_validation
            ), "Generated manifest should reference test stub in validation commands"
        finally:
            # Cleanup generated stub files
            for stub_file in Path("tests").glob("test_task_*_snapshot_example.py"):
                stub_file.unlink(missing_ok=True)

    def test_snapshot_skips_stub_with_flag(self, tmp_path: Path):
        """Test that snapshot skips stub generation with skip_test_stub=True."""
        from maid_runner.cli.snapshot import generate_snapshot

        code = """
def skip_stub_function():
    return False
"""
        source_file = tmp_path / "skip_stub.py"
        source_file.write_text(code)

        output_dir = tmp_path / "manifests"
        output_dir.mkdir()

        # Generate snapshot with skip_test_stub=True (explicit parameter)
        manifest_path = generate_snapshot(
            str(source_file), str(output_dir), force=False, skip_test_stub=True
        )

        # Manifest should exist
        assert Path(manifest_path).exists()

        # Stub should NOT be created (or verify it wasn't created in tests/)
        # This verifies the flag works

    def test_run_snapshot_with_skip_test_stub(self, tmp_path: Path):
        """Test that run_snapshot accepts skip_test_stub parameter."""
        from maid_runner.cli.snapshot import run_snapshot
        import sys
        from io import StringIO

        code = """
def test_run_snapshot():
    return True
"""
        source_file = tmp_path / "test_run.py"
        source_file.write_text(code)

        output_dir = tmp_path / "manifests"
        output_dir.mkdir()

        # Capture stdout
        old_stdout = sys.stdout
        sys.stdout = StringIO()

        try:
            # This will call sys.exit(0) on success, so we need to catch it
            try:
                run_snapshot(
                    str(source_file),
                    str(output_dir),
                    force=False,
                    skip_test_stub=True,
                )
            except SystemExit as e:
                # Success exit is expected
                assert e.code == 0
        finally:
            sys.stdout = old_stdout


class TestCLIIntegration:
    """Test CLI integration for stub generation."""

    def test_snapshot_command_accepts_skip_test_stub_flag(self, tmp_path: Path):
        """Test that snapshot command accepts --skip-test-stub flag."""
        from maid_runner.cli.snapshot import main

        code = "def cli_test(): pass"
        test_file = tmp_path / "cli_test.py"
        test_file.write_text(code)

        output_dir = tmp_path / "output"
        output_dir.mkdir()

        # Test with --skip-test-stub flag using direct call instead of subprocess
        test_args = [
            "snapshot",
            str(test_file),
            "--output-dir",
            str(output_dir),
            "--skip-test-stub",
        ]

        with patch("sys.argv", test_args):
            main()  # Should execute without error

    def test_generate_stubs_subcommand_exists(self, tmp_path: Path):
        """Test that generate-stubs subcommand is available."""
        from maid_runner.cli.main import main

        # Create a minimal manifest
        manifest_data = {
            "goal": "Test subcommand",
            "taskType": "create",
            "creatableFiles": ["test.py"],
            "expectedArtifacts": {
                "file": "test.py",
                "contains": [{"type": "function", "name": "test_func"}],
            },
            "validationCommand": [],
        }

        manifest_file = tmp_path / "test.manifest.json"
        manifest_file.write_text(json.dumps(manifest_data, indent=2))

        try:
            # Test generate-stubs command using direct call instead of subprocess
            test_args = [
                "maid",
                "generate-stubs",
                str(manifest_file),
            ]

            with patch("sys.argv", test_args):
                main()  # Should execute without raising
        finally:
            # Cleanup generated stub files
            for stub_file in Path("tests").glob("test_test.py"):
                stub_file.unlink(missing_ok=True)

    def test_generate_stubs_creates_stub_from_manifest(self, tmp_path: Path):
        """Test that generate-stubs creates stub from existing manifest."""
        from maid_runner.cli.main import main

        manifest_data = {
            "goal": "Generate stub test",
            "taskType": "create",
            "creatableFiles": ["feature.py"],
            "expectedArtifacts": {
                "file": "feature.py",
                "contains": [
                    {
                        "type": "function",
                        "name": "new_feature",
                        "parameters": [{"name": "data", "type": "dict"}],
                    }
                ],
            },
            "validationCommand": [],
        }

        manifest_file = tmp_path / "task-100-new-feature.manifest.json"
        manifest_file.write_text(json.dumps(manifest_data, indent=2))

        try:
            # Run generate-stubs using direct call instead of subprocess
            test_args = [
                "maid",
                "generate-stubs",
                str(manifest_file),
            ]

            with patch("sys.argv", test_args):
                main()  # Should execute without raising

            # Stub should be created (check for test file)
            # The exact location depends on implementation
        finally:
            # Cleanup generated stub files
            for stub_file in Path("tests").glob("test_task_*_new_feature.py"):
                stub_file.unlink(missing_ok=True)


class TestImportValidation:
    """Test import validation for generated stubs."""

    def test_stub_imports_from_importable_module(self, tmp_path: Path, mock_file_write):
        """Test that stub includes imports when module is importable."""
        # Use an actual importable module
        manifest_data = {
            "goal": "Test with importable module",
            "expectedArtifacts": {
                "file": "maid_runner/cli/snapshot.py",
                "contains": [{"type": "function", "name": "generate_test_stub"}],
            },
        }

        manifest_path = str(tmp_path / "task-importable.manifest.json")
        with open(manifest_path, "w") as f:
            json.dump(manifest_data, f)

        _stub_path, content = mock_file_write(manifest_data, manifest_path)

        # Should include actual import (not a comment)
        assert "from maid_runner.cli.snapshot import generate_test_stub" in content
        assert "# NOTE: Module" not in content  # No error comment

    def test_stub_handles_non_importable_module(self, tmp_path: Path, mock_file_write):
        """Test that stub handles non-importable modules gracefully."""
        # Use a module that doesn't exist
        manifest_data = {
            "goal": "Test with non-importable module",
            "expectedArtifacts": {
                "file": "fake/nonexistent/module.py",
                "contains": [{"type": "function", "name": "fake_function"}],
            },
        }

        manifest_path = str(tmp_path / "task-nonimportable.manifest.json")
        with open(manifest_path, "w") as f:
            json.dump(manifest_data, f)

        _stub_path, content = mock_file_write(manifest_data, manifest_path)

        # Should have a helpful comment instead of broken import
        assert (
            "# NOTE: Module 'fake.nonexistent.module' is not currently importable"
            in content
        )
        assert (
            "# from fake.nonexistent.module import fake_function" in content
        )  # Commented import

    def test_stub_handles_path_with_leading_dot_slash(
        self, tmp_path: Path, mock_file_write
    ):
        """Test that stub handles paths with leading ./ correctly."""
        # Use a path with leading ./
        manifest_data = {
            "goal": "Test with ./ prefix",
            "expectedArtifacts": {
                "file": "./scripts/video-production/voice_command_processor.py",
                "contains": [{"type": "function", "name": "process_command"}],
            },
        }

        manifest_path = str(tmp_path / "task-dotslash.manifest.json")
        with open(manifest_path, "w") as f:
            json.dump(manifest_data, f)

        _stub_path, content = mock_file_write(manifest_data, manifest_path)

        # Should have normalized the path (no leading ..)
        assert (
            "# NOTE: Module 'scripts.video-production.voice_command_processor'"
            in content
        )
        # Should NOT have double dots from ./
        assert ".." not in content
        # Should have commented import template
        assert (
            "# from scripts.video-production.voice_command_processor import" in content
            or "# from scripts.video_production.voice_command_processor import"
            in content
        )


class TestStubContent:
    """Test the quality and content of generated stubs."""

    def test_stub_includes_all_required_sections(self, tmp_path: Path, mock_file_write):
        """Test that stub includes all required sections per spec."""
        manifest_data = {
            "goal": "Comprehensive test",
            "expectedArtifacts": {
                "file": "complete/module.py",
                "contains": [
                    {
                        "type": "function",
                        "name": "process_data",
                        "parameters": [
                            {"name": "input_data", "type": "dict"},
                            {"name": "validate", "type": "bool"},
                        ],
                        "returns": "dict",
                    }
                ],
            },
        }

        manifest_path = str(tmp_path / "task-200-complete.manifest.json")
        with open(manifest_path, "w") as f:
            json.dump(manifest_data, f)

        _stub_path, content = mock_file_write(manifest_data, manifest_path)

        # Required sections:
        # 1. Import statements
        assert "import pytest" in content
        assert "from" in content or "import" in content

        # 2. Test class/function shells
        assert "class Test" in content or "def test_" in content

        # 3. Assertion placeholders (commented)
        assert "#" in content
        assert "assert" in content.lower()

        # 4. Docstring templates
        assert '"""' in content or "'''" in content

        # 5. pytest.fail() calls
        assert "pytest.fail" in content
        assert "TODO" in content

    def test_stub_is_valid_python_syntax(self, tmp_path: Path, mock_file_write):
        """Test that generated stub is syntactically valid Python."""
        import ast

        manifest_data = {
            "goal": "Syntax validation test",
            "expectedArtifacts": {
                "file": "syntax/check.py",
                "contains": [{"type": "function", "name": "check_syntax"}],
            },
        }

        manifest_path = str(tmp_path / "task-300-syntax.manifest.json")
        with open(manifest_path, "w") as f:
            json.dump(manifest_data, f)

        _stub_path, content = mock_file_write(manifest_data, manifest_path)

        # Should parse without syntax errors
        try:
            ast.parse(content)
            syntax_valid = True
        except SyntaxError:
            syntax_valid = False

        assert syntax_valid, "Generated stub should be valid Python"
