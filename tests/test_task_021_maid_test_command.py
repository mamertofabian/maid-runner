"""Behavioral tests for Task 021: Implementing maid test command"""

import json
import subprocess
from pathlib import Path

import pytest


def test_run_test_function_is_importable():
    """Test that run_test() is importable from maid_runner.cli.test."""
    from maid_runner.cli.test import run_test

    assert callable(run_test)


def test_execute_validation_commands_is_importable():
    """Test that execute_validation_commands() is importable."""
    from maid_runner.cli.test import execute_validation_commands

    assert callable(execute_validation_commands)


def test_main_function_is_importable():
    """Test that main() is importable from maid_runner.cli.test."""
    from maid_runner.cli.test import main

    assert callable(main)


def test_maid_test_command_runs(tmp_path: Path):
    """Test that 'maid test' command runs successfully with basic setup."""
    # Create manifests directory
    manifests_dir = tmp_path / "manifests"
    manifests_dir.mkdir()

    # Create a simple passing manifest
    manifest = {
        "version": "1",
        "goal": "test",
        "taskType": "edit",
        "editableFiles": ["test.py"],
        "validationCommand": ["echo", "test passed"],
    }
    manifest_file = manifests_dir / "task-001.manifest.json"
    manifest_file.write_text(json.dumps(manifest))

    # Run maid test
    result = subprocess.run(
        ["maid", "test", "--manifest-dir", str(manifests_dir)],
        cwd=str(tmp_path),
        capture_output=True,
        text=True,
    )

    # Should succeed
    assert result.returncode == 0
    assert "task-001.manifest.json" in result.stdout


def test_maid_test_skips_superseded_manifests(tmp_path: Path):
    """Test that maid test skips manifests listed in supersedes field."""
    # Create manifests directory
    manifests_dir = tmp_path / "manifests"
    manifests_dir.mkdir()

    # Create regular manifest
    manifest1 = {
        "version": "1",
        "goal": "task 1",
        "taskType": "edit",
        "editableFiles": ["test1.py"],
        "validationCommand": ["echo", "test1"],
    }
    manifest1_file = manifests_dir / "task-001.manifest.json"
    manifest1_file.write_text(json.dumps(manifest1))

    # Create snapshot that supersedes task-001
    snapshot = {
        "version": "1",
        "goal": "snapshot",
        "taskType": "snapshot",
        "editableFiles": ["test1.py"],
        "supersedes": ["manifests/task-001.manifest.json"],
        "validationCommand": ["echo", "snapshot"],
    }
    snapshot_file = manifests_dir / "task-002-snapshot-v1.manifest.json"
    snapshot_file.write_text(json.dumps(snapshot))

    # Run maid test
    result = subprocess.run(
        ["maid", "test", "--manifest-dir", str(manifests_dir)],
        cwd=str(tmp_path),
        capture_output=True,
        text=True,
    )

    # Should succeed and show skipped count
    assert result.returncode == 0
    assert "Skipping" in result.stdout and "superseded" in result.stdout
    # task-001 should not run, only snapshot should run
    assert "task-002-snapshot-v1.manifest.json" in result.stdout


def test_execute_validation_commands_returns_tuple(tmp_path: Path):
    """Test that execute_validation_commands() returns a tuple with pass/fail counts."""
    from maid_runner.cli.test import execute_validation_commands

    # Create a manifest with validation command
    manifest_data = {"validationCommand": ["echo", "test"]}
    manifest_path = tmp_path / "test.manifest.json"

    # Execute validation commands
    result = execute_validation_commands(
        manifest_path=manifest_path,
        manifest_data=manifest_data,
        timeout=300,
        verbose=False,
        project_root=tmp_path,
    )

    # Should return a tuple (passed, failed, total)
    assert isinstance(result, tuple)
    assert len(result) == 3
    passed, failed, total = result
    assert passed + failed == total


def test_execute_validation_commands_with_passing_command(tmp_path: Path):
    """Test that execute_validation_commands() correctly reports passing commands."""
    from maid_runner.cli.test import execute_validation_commands

    # Create a manifest with passing command
    manifest_data = {"validationCommand": ["echo", "success"]}
    manifest_path = tmp_path / "test.manifest.json"

    # Execute validation commands
    passed, failed, total = execute_validation_commands(
        manifest_path=manifest_path,
        manifest_data=manifest_data,
        timeout=300,
        verbose=False,
        project_root=tmp_path,
    )

    # Should have 1 passed, 0 failed
    assert passed == 1
    assert failed == 0
    assert total == 1


def test_execute_validation_commands_with_failing_command(tmp_path: Path):
    """Test that execute_validation_commands() correctly reports failing commands."""
    from maid_runner.cli.test import execute_validation_commands

    # Create a manifest with failing command
    manifest_data = {"validationCommand": ["false"]}  # 'false' command always exits 1
    manifest_path = tmp_path / "test.manifest.json"

    # Execute validation commands
    passed, failed, total = execute_validation_commands(
        manifest_path=manifest_path,
        manifest_data=manifest_data,
        timeout=300,
        verbose=False,
        project_root=tmp_path,
    )

    # Should have 0 passed, 1 failed
    assert passed == 0
    assert failed == 1
    assert total == 1


def test_maid_test_fail_fast_stops_on_failure(tmp_path: Path):
    """Test that --fail-fast flag stops execution on first failure."""
    # Create manifests directory
    manifests_dir = tmp_path / "manifests"
    manifests_dir.mkdir()

    # Create failing manifest
    manifest1 = {
        "version": "1",
        "goal": "failing task",
        "taskType": "edit",
        "editableFiles": ["test1.py"],
        "validationCommand": ["false"],
    }
    manifest1_file = manifests_dir / "task-001.manifest.json"
    manifest1_file.write_text(json.dumps(manifest1))

    # Create second manifest (should not run)
    manifest2 = {
        "version": "1",
        "goal": "second task",
        "taskType": "edit",
        "editableFiles": ["test2.py"],
        "validationCommand": ["echo", "should not run"],
    }
    manifest2_file = manifests_dir / "task-002.manifest.json"
    manifest2_file.write_text(json.dumps(manifest2))

    # Run with --fail-fast
    result = subprocess.run(
        ["maid", "test", "--manifest-dir", str(manifests_dir), "--fail-fast"],
        cwd=str(tmp_path),
        capture_output=True,
        text=True,
    )

    # Should fail (exit code 1)
    assert result.returncode == 1
    # Should mention failure
    assert "FAILED" in result.stdout or "failed" in result.stdout.lower()


def test_maid_test_handles_empty_manifests_dir(tmp_path: Path):
    """Test that maid test handles empty manifests directory gracefully."""
    # Create empty manifests directory
    manifests_dir = tmp_path / "manifests"
    manifests_dir.mkdir()

    # Run maid test
    result = subprocess.run(
        ["maid", "test", "--manifest-dir", str(manifests_dir)],
        cwd=str(tmp_path),
        capture_output=True,
        text=True,
    )

    # Should succeed (exit 0) with a message about no manifests
    assert result.returncode == 0
    assert "No manifest files found" in result.stdout or "No active" in result.stdout


def test_execute_validation_commands_handles_enhanced_format(tmp_path: Path):
    """Test that execute_validation_commands() handles enhanced validationCommands format."""
    from maid_runner.cli.test import execute_validation_commands

    # Create a manifest with enhanced format (array of arrays)
    manifest_data = {"validationCommands": [["echo", "test1"], ["echo", "test2"]]}
    manifest_path = tmp_path / "test.manifest.json"

    # Execute validation commands
    passed, failed, total = execute_validation_commands(
        manifest_path=manifest_path,
        manifest_data=manifest_data,
        timeout=300,
        verbose=False,
        project_root=tmp_path,
    )

    # Should have 2 passed commands
    assert passed == 2
    assert failed == 0
    assert total == 2


def test_maid_test_shows_summary(tmp_path: Path):
    """Test that maid test shows a summary of results."""
    # Create manifests directory
    manifests_dir = tmp_path / "manifests"
    manifests_dir.mkdir()

    # Create passing manifest
    manifest = {
        "version": "1",
        "goal": "test",
        "taskType": "edit",
        "editableFiles": ["test.py"],
        "validationCommand": ["echo", "test"],
    }
    manifest_file = manifests_dir / "task-001.manifest.json"
    manifest_file.write_text(json.dumps(manifest))

    # Run maid test
    result = subprocess.run(
        ["maid", "test", "--manifest-dir", str(manifests_dir)],
        cwd=str(tmp_path),
        capture_output=True,
        text=True,
    )

    # Should show summary
    assert result.returncode == 0
    assert "Summary" in result.stdout or "passed" in result.stdout.lower()


def test_run_test_function_with_valid_manifest_dir(tmp_path: Path, capsys):
    """Test that run_test() function executes correctly with valid manifest directory."""
    from maid_runner.cli.test import run_test

    # Create manifests directory
    manifests_dir = tmp_path / "manifests"
    manifests_dir.mkdir()

    # Create passing manifest
    manifest = {
        "version": "1",
        "goal": "test",
        "taskType": "edit",
        "editableFiles": ["test.py"],
        "validationCommand": ["echo", "test passed"],
    }
    manifest_file = manifests_dir / "task-001.manifest.json"
    manifest_file.write_text(json.dumps(manifest))

    # Change to tmp directory
    import os

    original_dir = os.getcwd()
    try:
        os.chdir(tmp_path)

        # Call run_test function - it should exit with 0 on success
        with pytest.raises(SystemExit) as exc_info:
            run_test(
                manifest_dir=str(manifests_dir),
                fail_fast=False,
                verbose=False,
                quiet=False,
                timeout=300,
                manifest_path=None,
            )

        # Should exit with code 0 (success)
        assert exc_info.value.code == 0

        # Capture output
        captured = capsys.readouterr()

        # Should show manifest name
        assert "task-001.manifest.json" in captured.out

    finally:
        os.chdir(original_dir)


def test_run_test_function_with_fail_fast(tmp_path: Path, capsys):
    """Test that run_test() respects fail_fast parameter."""
    from maid_runner.cli.test import run_test

    # Create manifests directory
    manifests_dir = tmp_path / "manifests"
    manifests_dir.mkdir()

    # Create failing manifest
    manifest = {
        "version": "1",
        "goal": "failing test",
        "taskType": "edit",
        "editableFiles": ["test.py"],
        "validationCommand": ["false"],
    }
    manifest_file = manifests_dir / "task-001.manifest.json"
    manifest_file.write_text(json.dumps(manifest))

    # Change to tmp directory
    import os

    original_dir = os.getcwd()
    try:
        os.chdir(tmp_path)

        # Call run_test with fail_fast=True
        # This should raise SystemExit when a test fails
        with pytest.raises(SystemExit):
            run_test(
                manifest_dir=str(manifests_dir),
                fail_fast=True,
                verbose=False,
                quiet=False,
                timeout=300,
                manifest_path=None,
            )

    finally:
        os.chdir(original_dir)


def test_main_function_runs_as_cli_entry_point(tmp_path: Path, monkeypatch):
    """Test that main() function works as CLI entry point."""
    from maid_runner.cli.test import main

    # Create manifests directory
    manifests_dir = tmp_path / "manifests"
    manifests_dir.mkdir()

    # Create passing manifest
    manifest = {
        "version": "1",
        "goal": "test",
        "taskType": "edit",
        "editableFiles": ["test.py"],
        "validationCommand": ["echo", "test"],
    }
    manifest_file = manifests_dir / "task-001.manifest.json"
    manifest_file.write_text(json.dumps(manifest))

    # Change to tmp directory
    import os
    import sys

    original_dir = os.getcwd()
    try:
        os.chdir(tmp_path)

        # Mock sys.argv to pass arguments
        # Note: main() in test.py is already at the test command level,
        # so we don't pass "test" as an argument
        monkeypatch.setattr(
            sys, "argv", ["maid-test", "--manifest-dir", str(manifests_dir)]
        )

        # Call main function - it should exit with 0 on success
        with pytest.raises(SystemExit) as exc_info:
            main()

        # Should exit with code 0 (success)
        assert exc_info.value.code == 0

    finally:
        os.chdir(original_dir)


def test_maid_test_single_manifest(tmp_path: Path):
    """Test that maid test can run validation commands for a single manifest."""
    # Create manifests directory
    manifests_dir = tmp_path / "manifests"
    manifests_dir.mkdir()

    # Create two manifests
    manifest1 = {
        "version": "1",
        "goal": "task 1",
        "taskType": "edit",
        "editableFiles": ["test1.py"],
        "validationCommand": ["echo", "test1"],
    }
    manifest1_file = manifests_dir / "task-001.manifest.json"
    manifest1_file.write_text(json.dumps(manifest1))

    manifest2 = {
        "version": "1",
        "goal": "task 2",
        "taskType": "edit",
        "editableFiles": ["test2.py"],
        "validationCommand": ["echo", "test2"],
    }
    manifest2_file = manifests_dir / "task-002.manifest.json"
    manifest2_file.write_text(json.dumps(manifest2))

    # Run maid test with --manifest option
    result = subprocess.run(
        [
            "maid",
            "test",
            "--manifest-dir",
            str(manifests_dir),
            "--manifest",
            "task-001.manifest.json",
        ],
        cwd=str(tmp_path),
        capture_output=True,
        text=True,
    )

    # Should succeed and only run task-001
    assert result.returncode == 0
    assert "task-001.manifest.json" in result.stdout
    # task-002 should NOT be in output
    assert "task-002.manifest.json" not in result.stdout
    assert "1/1 validation commands passed" in result.stdout


def test_run_test_with_single_manifest_path(tmp_path: Path, capsys):
    """Test that run_test() respects manifest_path parameter."""
    from maid_runner.cli.test import run_test

    # Create manifests directory
    manifests_dir = tmp_path / "manifests"
    manifests_dir.mkdir()

    # Create two manifests
    manifest1 = {
        "version": "1",
        "goal": "task 1",
        "taskType": "edit",
        "editableFiles": ["test1.py"],
        "validationCommand": ["echo", "only this one should run"],
    }
    manifest1_file = manifests_dir / "task-001.manifest.json"
    manifest1_file.write_text(json.dumps(manifest1))

    manifest2 = {
        "version": "1",
        "goal": "task 2",
        "taskType": "edit",
        "editableFiles": ["test2.py"],
        "validationCommand": ["echo", "this should not run"],
    }
    manifest2_file = manifests_dir / "task-002.manifest.json"
    manifest2_file.write_text(json.dumps(manifest2))

    # Change to tmp directory
    import os

    original_dir = os.getcwd()
    try:
        os.chdir(tmp_path)

        # Call run_test with manifest_path
        with pytest.raises(SystemExit) as exc_info:
            run_test(
                manifest_dir=str(manifests_dir),
                fail_fast=False,
                verbose=False,
                quiet=False,
                timeout=300,
                manifest_path="task-001.manifest.json",
            )

        # Should exit with code 0 (success)
        assert exc_info.value.code == 0

        # Capture output
        captured = capsys.readouterr()

        # Should only show task-001
        assert "task-001.manifest.json" in captured.out
        assert "only this one should run" in captured.out
        # task-002 should NOT be in output
        assert "task-002.manifest.json" not in captured.out
        assert "this should not run" not in captured.out

    finally:
        os.chdir(original_dir)


def test_maid_test_single_manifest_not_found(tmp_path: Path):
    """Test that maid test handles non-existent single manifest gracefully."""
    # Create manifests directory
    manifests_dir = tmp_path / "manifests"
    manifests_dir.mkdir()

    # Run maid test with non-existent manifest
    result = subprocess.run(
        [
            "maid",
            "test",
            "--manifest-dir",
            str(manifests_dir),
            "--manifest",
            "task-999.manifest.json",
        ],
        cwd=str(tmp_path),
        capture_output=True,
        text=True,
    )

    # Should fail with exit code 1
    assert result.returncode == 1
    assert "Manifest file not found" in result.stdout
