"""Tests for task-094: Integration of batch mode into maid test CLI.

This module tests that the maid test command automatically uses batch mode
when all validation commands are pytest-compatible, and falls back to
sequential mode for mixed test runners.
"""

import json
from unittest.mock import patch

import pytest

from maid_runner.cli.test import run_test


class TestBatchModeIntegration:
    """Test batch mode integration in run_test."""

    @patch("maid_runner.cli.test.run_batch_tests")
    @patch("maid_runner.cli.test.collect_test_files_by_runner")
    def test_uses_batch_mode_for_all_pytest_commands(
        self, mock_collect, mock_run_batch, tmp_path
    ):
        """Should use batch mode when all validation commands are pytest."""
        manifests_dir = tmp_path / "manifests"
        manifests_dir.mkdir()

        # Create manifests with pytest commands
        for i in range(3):
            manifest_data = {
                "version": "1",
                "validationCommand": ["pytest", f"tests/test_{i}.py", "-v"],
            }
            manifest_path = manifests_dir / f"task-00{i}.manifest.json"
            manifest_path.write_text(json.dumps(manifest_data))

        # Mock batch collection to return test files grouped by runner
        mock_collect.return_value = {
            "pytest": {"tests/test_0.py", "tests/test_1.py", "tests/test_2.py"}
        }
        # Mock batch run to succeed
        mock_run_batch.return_value = (1, 0, 1)

        # Run test command
        with pytest.raises(SystemExit) as exc_info:
            run_test(
                manifest_dir=str(manifests_dir),
                fail_fast=False,
                verbose=False,
                quiet=False,
                timeout=300,
                manifest_path=None,
                watch=False,
                watch_all=False,
            )

        # Should exit with success code
        assert exc_info.value.code == 0

        # Should have called batch mode
        assert mock_collect.called
        assert mock_run_batch.called

    @patch("maid_runner.cli.test.run_batch_tests")
    @patch("maid_runner.cli.test.collect_test_files_by_runner")
    def test_handles_mixed_runners_with_multi_batch(
        self, mock_collect, mock_run_batch, tmp_path
    ):
        """Should batch each runner separately for mixed pytest/vitest commands."""
        manifests_dir = tmp_path / "manifests"
        manifests_dir.mkdir()

        # Create manifests with mixed commands
        manifest1_data = {
            "version": "1",
            "validationCommand": ["pytest", "tests/test_1.py", "-v"],
        }
        manifest1_path = manifests_dir / "task-001.manifest.json"
        manifest1_path.write_text(json.dumps(manifest1_data))

        manifest2_data = {
            "version": "1",
            "validationCommand": ["vitest", "run", "test.spec.ts"],
        }
        manifest2_path = manifests_dir / "task-002.manifest.json"
        manifest2_path.write_text(json.dumps(manifest2_data))

        # Mock batch collection to return both runners
        mock_collect.return_value = {
            "pytest": {"tests/test_1.py"},
            "vitest": {"test.spec.ts"},
        }
        # Mock batch run to succeed
        mock_run_batch.return_value = (1, 0, 1)

        # Run test command
        with pytest.raises(SystemExit) as exc_info:
            run_test(
                manifest_dir=str(manifests_dir),
                fail_fast=False,
                verbose=False,
                quiet=False,
                timeout=300,
                manifest_path=None,
                watch=False,
                watch_all=False,
            )

        # Should exit with success code
        assert exc_info.value.code == 0

        # Should have called batch mode for both runners
        assert mock_collect.called
        assert mock_run_batch.call_count == 2  # Called once per runner

    @patch("maid_runner.cli.test.execute_validation_commands")
    @patch("maid_runner.cli.test.collect_test_files_by_runner")
    def test_skips_batch_mode_for_single_manifest(
        self, mock_collect, mock_execute, tmp_path
    ):
        """Should skip batch mode when running single manifest."""
        manifests_dir = tmp_path / "manifests"
        manifests_dir.mkdir()

        manifest_data = {
            "version": "1",
            "validationCommand": ["pytest", "tests/test_example.py", "-v"],
        }
        manifest_path = manifests_dir / "task-001.manifest.json"
        manifest_path.write_text(json.dumps(manifest_data))

        # Mock sequential execution
        mock_execute.return_value = (1, 0, 1)

        # Run test command with specific manifest
        with pytest.raises(SystemExit) as exc_info:
            run_test(
                manifest_dir=str(manifests_dir),
                fail_fast=False,
                verbose=False,
                quiet=False,
                timeout=300,
                manifest_path="task-001.manifest.json",
                watch=False,
                watch_all=False,
            )

        # Should exit with success code
        assert exc_info.value.code == 0

        # Should NOT have called batch mode for single manifest
        assert not mock_collect.called
        # Should have used sequential mode
        assert mock_execute.called

    @patch("maid_runner.cli.test.watch_manifest")
    def test_skips_batch_mode_for_watch_mode(self, mock_watch, tmp_path):
        """Should skip batch mode when in watch mode."""
        manifests_dir = tmp_path / "manifests"
        manifests_dir.mkdir()

        manifest_data = {
            "version": "1",
            "validationCommand": ["pytest", "tests/test_example.py", "-v"],
        }
        manifest_path = manifests_dir / "task-001.manifest.json"
        manifest_path.write_text(json.dumps(manifest_data))

        # Mock watch_manifest (it will run indefinitely otherwise)
        def mock_watch_fn(*args, **kwargs):
            raise SystemExit(0)

        mock_watch.side_effect = mock_watch_fn

        # Run test command with watch mode
        with pytest.raises(SystemExit):
            run_test(
                manifest_dir=str(manifests_dir),
                fail_fast=False,
                verbose=False,
                quiet=False,
                timeout=300,
                manifest_path="task-001.manifest.json",
                watch=True,
                watch_all=False,
            )

        # Should have called watch mode
        assert mock_watch.called

    @patch("maid_runner.cli.test.run_batch_tests")
    @patch("maid_runner.cli.test.collect_test_files_by_runner")
    def test_batch_mode_respects_quiet_flag(
        self, mock_collect, mock_run_batch, tmp_path, capsys
    ):
        """Should respect quiet flag in batch mode."""
        manifests_dir = tmp_path / "manifests"
        manifests_dir.mkdir()

        # Create multiple manifests to trigger batch mode
        for i in range(2):
            manifest_data = {
                "version": "1",
                "validationCommand": ["pytest", f"tests/test_{i}.py", "-v"],
            }
            manifest_path = manifests_dir / f"task-00{i}.manifest.json"
            manifest_path.write_text(json.dumps(manifest_data))

        # Mock batch collection and execution
        mock_collect.return_value = {"pytest": {"tests/test_0.py", "tests/test_1.py"}}
        mock_run_batch.return_value = (1, 0, 1)

        # Run with quiet flag
        with pytest.raises(SystemExit) as exc_info:
            run_test(
                manifest_dir=str(manifests_dir),
                fail_fast=False,
                verbose=False,
                quiet=True,  # Quiet mode
                timeout=300,
                manifest_path=None,
                watch=False,
                watch_all=False,
            )

        # Should exit with success
        assert exc_info.value.code == 0

        # Batch mode should still run
        assert mock_run_batch.called
