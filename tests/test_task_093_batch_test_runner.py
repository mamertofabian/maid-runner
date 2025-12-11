"""Tests for task-093: Batch test runner module.

This module tests the batch test runner functionality that enables running
all pytest test files in a single invocation instead of N separate invocations.
"""

import json
import subprocess
from pathlib import Path
from unittest.mock import MagicMock, patch


from maid_runner.cli._batch_test_runner import (
    collect_pytest_test_files,
    collect_test_files_by_runner,
    detect_test_runner,
    extract_test_file_from_command,
    is_pytest_command,
    run_batch_pytest,
    run_batch_tests,
)


class TestExtractTestFileFromCommand:
    """Test extraction of test file paths from validation commands."""

    def test_extract_from_pytest_command(self):
        """Should extract test file from pytest command."""
        command = ["pytest", "tests/test_example.py", "-v"]
        result = extract_test_file_from_command(command)
        assert result == "tests/test_example.py"

    def test_extract_from_python_pytest_command(self):
        """Should extract test file from python -m pytest command."""
        command = ["python", "-m", "pytest", "tests/test_example.py", "-v"]
        result = extract_test_file_from_command(command)
        assert result == "tests/test_example.py"

    def test_extract_from_uv_run_pytest_command(self):
        """Should extract test file from uv run pytest command."""
        command = ["uv", "run", "pytest", "tests/test_example.py", "-v"]
        result = extract_test_file_from_command(command)
        assert result == "tests/test_example.py"

    def test_extract_handles_multiple_flags(self):
        """Should extract test file when multiple flags are present."""
        command = ["pytest", "tests/test_example.py", "-v", "-x", "--tb=short"]
        result = extract_test_file_from_command(command)
        assert result == "tests/test_example.py"

    def test_extract_returns_none_for_non_test_file(self):
        """Should return None when command has no test file."""
        command = ["pytest", "-v"]
        result = extract_test_file_from_command(command)
        assert result is None

    def test_extract_returns_none_for_non_pytest_command(self):
        """Should extract test file from non-pytest commands too."""
        command = ["vitest", "run", "test.spec.ts"]
        result = extract_test_file_from_command(command)
        # Now supports vitest
        assert result == "test.spec.ts"

    def test_extract_handles_test_directory(self):
        """Should extract test directory path."""
        command = ["pytest", "tests/", "-v"]
        result = extract_test_file_from_command(command)
        assert result == "tests/"


class TestIsPytestCommand:
    """Test detection of pytest commands."""

    def test_detects_basic_pytest_command(self):
        """Should detect basic pytest command."""
        command = ["pytest", "tests/test_example.py"]
        assert is_pytest_command(command) is True

    def test_detects_python_m_pytest_command(self):
        """Should detect python -m pytest command."""
        command = ["python", "-m", "pytest", "tests/test_example.py"]
        assert is_pytest_command(command) is True

    def test_detects_uv_run_pytest_command(self):
        """Should detect uv run pytest command."""
        command = ["uv", "run", "pytest", "tests/test_example.py"]
        assert is_pytest_command(command) is True

    def test_rejects_non_pytest_command(self):
        """Should reject non-pytest commands."""
        command = ["vitest", "run", "test.spec.ts"]
        assert is_pytest_command(command) is False

    def test_rejects_empty_command(self):
        """Should reject empty command."""
        command = []
        assert is_pytest_command(command) is False


class TestDetectTestRunner:
    """Test detection of test runner types."""

    def test_detects_pytest(self):
        """Should detect pytest command."""
        command = ["pytest", "tests/test_example.py"]
        assert detect_test_runner(command) == "pytest"

    def test_detects_vitest(self):
        """Should detect vitest command."""
        command = ["vitest", "run", "test.spec.ts"]
        assert detect_test_runner(command) == "vitest"

    def test_detects_jest(self):
        """Should detect jest command."""
        command = ["jest", "test.test.js"]
        assert detect_test_runner(command) == "jest"

    def test_detects_npm_test(self):
        """Should detect npm test command."""
        command = ["npm", "test"]
        assert detect_test_runner(command) == "npm-test"

    def test_detects_pnpm_test(self):
        """Should detect pnpm test command."""
        command = ["pnpm", "test"]
        assert detect_test_runner(command) == "pnpm-test"

    def test_returns_none_for_unknown_command(self):
        """Should return None for unknown commands."""
        command = ["make", "build"]
        assert detect_test_runner(command) is None

    def test_returns_none_for_empty_command(self):
        """Should return None for empty command."""
        command = []
        assert detect_test_runner(command) is None


class TestCollectPytestTestFiles:
    """Test collection of pytest test files from manifests."""

    def test_collects_test_files_from_single_manifest(self, tmp_path):
        """Should collect test files from a single manifest."""
        manifests_dir = tmp_path / "manifests"
        manifests_dir.mkdir()

        manifest_data = {
            "version": "1",
            "validationCommand": ["pytest", "tests/test_example.py", "-v"],
        }
        manifest_path = manifests_dir / "task-001.manifest.json"
        manifest_path.write_text(json.dumps(manifest_data))

        result = collect_pytest_test_files(manifests_dir, [manifest_path])
        assert result == {"tests/test_example.py"}

    def test_collects_and_deduplicates_test_files(self, tmp_path):
        """Should deduplicate test files from multiple manifests."""
        manifests_dir = tmp_path / "manifests"
        manifests_dir.mkdir()

        # Two manifests with same test file
        manifest1_data = {
            "version": "1",
            "validationCommand": ["pytest", "tests/test_shared.py", "-v"],
        }
        manifest1_path = manifests_dir / "task-001.manifest.json"
        manifest1_path.write_text(json.dumps(manifest1_data))

        manifest2_data = {
            "version": "1",
            "validationCommand": ["pytest", "tests/test_shared.py", "-v"],
        }
        manifest2_path = manifests_dir / "task-002.manifest.json"
        manifest2_path.write_text(json.dumps(manifest2_data))

        result = collect_pytest_test_files(
            manifests_dir, [manifest1_path, manifest2_path]
        )
        # Should deduplicate
        assert result == {"tests/test_shared.py"}

    def test_returns_none_for_mixed_commands(self, tmp_path):
        """Should return None when manifests have mixed pytest/non-pytest commands."""
        manifests_dir = tmp_path / "manifests"
        manifests_dir.mkdir()

        # Pytest command
        manifest1_data = {
            "version": "1",
            "validationCommand": ["pytest", "tests/test_example.py", "-v"],
        }
        manifest1_path = manifests_dir / "task-001.manifest.json"
        manifest1_path.write_text(json.dumps(manifest1_data))

        # Non-pytest command
        manifest2_data = {
            "version": "1",
            "validationCommand": ["vitest", "run", "test.spec.ts"],
        }
        manifest2_path = manifests_dir / "task-002.manifest.json"
        manifest2_path.write_text(json.dumps(manifest2_data))

        result = collect_pytest_test_files(
            manifests_dir, [manifest1_path, manifest2_path]
        )
        assert result is None

    def test_handles_validationCommands_array(self, tmp_path):
        """Should handle validationCommands (plural) array format."""
        manifests_dir = tmp_path / "manifests"
        manifests_dir.mkdir()

        manifest_data = {
            "version": "1",
            "validationCommands": [
                ["pytest", "tests/test_one.py", "-v"],
                ["pytest", "tests/test_two.py", "-v"],
            ],
        }
        manifest_path = manifests_dir / "task-001.manifest.json"
        manifest_path.write_text(json.dumps(manifest_data))

        result = collect_pytest_test_files(manifests_dir, [manifest_path])
        assert result == {"tests/test_one.py", "tests/test_two.py"}

    def test_skips_manifests_without_validation_commands(self, tmp_path):
        """Should skip manifests without validation commands."""
        manifests_dir = tmp_path / "manifests"
        manifests_dir.mkdir()

        manifest_data = {
            "version": "1"
            # No validationCommand
        }
        manifest_path = manifests_dir / "task-001.manifest.json"
        manifest_path.write_text(json.dumps(manifest_data))

        result = collect_pytest_test_files(manifests_dir, [manifest_path])
        assert result == set()


class TestCollectTestFilesByRunner:
    """Test collection of test files grouped by runner type."""

    def test_collects_and_groups_by_single_runner(self, tmp_path):
        """Should group test files by runner type for single runner."""
        manifests_dir = tmp_path / "manifests"
        manifests_dir.mkdir()

        # Create manifests with pytest commands
        for i in range(2):
            manifest_data = {
                "version": "1",
                "validationCommand": ["pytest", f"tests/test_{i}.py", "-v"],
            }
            manifest_path = manifests_dir / f"task-00{i}.manifest.json"
            manifest_path.write_text(json.dumps(manifest_data))

        result = collect_test_files_by_runner(
            manifests_dir, list(manifests_dir.glob("*.json"))
        )

        assert "pytest" in result
        assert result["pytest"] == {"tests/test_0.py", "tests/test_1.py"}

    def test_collects_and_groups_multiple_runners(self, tmp_path):
        """Should group test files by runner type for multiple runners."""
        manifests_dir = tmp_path / "manifests"
        manifests_dir.mkdir()

        # Pytest manifest
        manifest1_data = {
            "version": "1",
            "validationCommand": ["pytest", "tests/test_py.py", "-v"],
        }
        manifest1_path = manifests_dir / "task-001.manifest.json"
        manifest1_path.write_text(json.dumps(manifest1_data))

        # Vitest manifest
        manifest2_data = {
            "version": "1",
            "validationCommand": ["vitest", "run", "test.spec.ts"],
        }
        manifest2_path = manifests_dir / "task-002.manifest.json"
        manifest2_path.write_text(json.dumps(manifest2_data))

        result = collect_test_files_by_runner(
            manifests_dir, [manifest1_path, manifest2_path]
        )

        assert "pytest" in result
        assert "vitest" in result
        assert result["pytest"] == {"tests/test_py.py"}
        assert result["vitest"] == {"test.spec.ts"}

    def test_deduplicates_within_runner_groups(self, tmp_path):
        """Should deduplicate test files within same runner group."""
        manifests_dir = tmp_path / "manifests"
        manifests_dir.mkdir()

        # Two manifests with same pytest test file
        for i in range(2):
            manifest_data = {
                "version": "1",
                "validationCommand": ["pytest", "tests/test_shared.py", "-v"],
            }
            manifest_path = manifests_dir / f"task-00{i}.manifest.json"
            manifest_path.write_text(json.dumps(manifest_data))

        result = collect_test_files_by_runner(
            manifests_dir, list(manifests_dir.glob("*.json"))
        )

        assert result["pytest"] == {"tests/test_shared.py"}

    def test_returns_empty_dict_for_no_test_commands(self, tmp_path):
        """Should return empty dict when no test commands found."""
        manifests_dir = tmp_path / "manifests"
        manifests_dir.mkdir()

        manifest_data = {
            "version": "1"
            # No validationCommand
        }
        manifest_path = manifests_dir / "task-001.manifest.json"
        manifest_path.write_text(json.dumps(manifest_data))

        result = collect_test_files_by_runner(manifests_dir, [manifest_path])
        assert result == {}


class TestRunBatchTests:
    """Test generic batch test execution for any runner."""

    @patch("subprocess.run")
    def test_runs_batch_pytest(self, mock_run, tmp_path):
        """Should run batch pytest tests."""
        mock_run.return_value = MagicMock(returncode=0, stdout="", stderr="")

        project_root = tmp_path
        (project_root / "pyproject.toml").write_text("[project]\nname='test'")

        test_files = {"tests/test_one.py", "tests/test_two.py"}

        passed, failed, total = run_batch_tests(
            "pytest", test_files, project_root, verbose=False, timeout=300
        )

        assert passed == 1
        assert failed == 0
        assert total == 1

        call_args = mock_run.call_args[0][0]
        assert "pytest" in call_args
        assert "tests/test_one.py" in call_args or "tests/test_two.py" in call_args

    @patch("subprocess.run")
    def test_runs_batch_vitest(self, mock_run, tmp_path):
        """Should run batch vitest tests."""
        mock_run.return_value = MagicMock(returncode=0, stdout="", stderr="")

        project_root = tmp_path
        (project_root / "package.json").write_text('{"name":"test"}')
        (project_root / "pnpm-lock.yaml").write_text("")

        test_files = {"test1.spec.ts", "test2.spec.ts"}

        passed, failed, total = run_batch_tests(
            "vitest", test_files, project_root, verbose=False, timeout=300
        )

        assert passed == 1
        assert failed == 0
        assert total == 1

        call_args = mock_run.call_args[0][0]
        assert "vitest" in call_args
        assert "run" in call_args

    @patch("subprocess.run")
    def test_handles_test_failure(self, mock_run, tmp_path):
        """Should handle test failures correctly."""
        mock_run.return_value = MagicMock(
            returncode=1, stdout="", stderr="Tests failed"
        )

        test_files = {"tests/test_failing.py"}

        passed, failed, total = run_batch_tests(
            "pytest", test_files, tmp_path, verbose=False, timeout=300
        )

        assert passed == 0
        assert failed == 1
        assert total == 1


class TestRunBatchPytest:
    """Test batch pytest execution."""

    @patch("subprocess.run")
    def test_runs_batch_pytest_successfully(self, mock_run):
        """Should run batch pytest with all test files."""
        mock_run.return_value = MagicMock(
            returncode=0, stdout="All tests passed", stderr=""
        )

        test_files = {"tests/test_one.py", "tests/test_two.py"}
        project_root = Path("/project")

        passed, failed, total = run_batch_pytest(
            test_files, project_root, verbose=False, timeout=300
        )

        assert passed == 1
        assert failed == 0
        assert total == 1

        # Verify pytest was called with correct arguments
        call_args = mock_run.call_args
        assert "pytest" in call_args[0][0]
        assert "tests/test_one.py" in call_args[0][0]
        assert "tests/test_two.py" in call_args[0][0]

    @patch("subprocess.run")
    def test_handles_pytest_failure(self, mock_run):
        """Should handle pytest failure correctly."""
        mock_run.return_value = MagicMock(
            returncode=1, stdout="", stderr="Tests failed"
        )

        test_files = {"tests/test_failing.py"}
        project_root = Path("/project")

        passed, failed, total = run_batch_pytest(
            test_files, project_root, verbose=False, timeout=300
        )

        assert passed == 0
        assert failed == 1
        assert total == 1

    @patch("subprocess.run")
    def test_includes_uv_run_prefix_when_pyproject_exists(self, mock_run, tmp_path):
        """Should prefix command with 'uv run' when pyproject.toml exists."""
        mock_run.return_value = MagicMock(returncode=0, stdout="", stderr="")

        # Create pyproject.toml
        project_root = tmp_path
        (project_root / "pyproject.toml").write_text("[project]\nname='test'")

        test_files = {"tests/test_example.py"}

        run_batch_pytest(test_files, project_root, verbose=False, timeout=300)

        call_args = mock_run.call_args[0][0]
        assert call_args[0] == "uv"
        assert call_args[1] == "run"
        assert call_args[2] == "pytest"

    @patch("subprocess.run")
    def test_handles_timeout(self, mock_run):
        """Should handle subprocess timeout."""
        mock_run.side_effect = subprocess.TimeoutExpired("pytest", 300)

        test_files = {"tests/test_slow.py"}
        project_root = Path("/project")

        passed, failed, total = run_batch_pytest(
            test_files, project_root, verbose=False, timeout=300
        )

        assert passed == 0
        assert failed == 1
        assert total == 1
