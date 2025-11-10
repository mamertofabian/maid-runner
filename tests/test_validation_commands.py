"""Tests for multiple validation commands support."""

import json
import subprocess
import tempfile
from pathlib import Path


from maid_runner.cli.validate import extract_test_files_from_command
from dev_bootstrap import MAIDDevRunner


def test_extract_from_validation_commands_format():
    """Test extracting test files from validationCommands format."""
    validation_commands = [
        ["pytest", "tests/test1.py", "-v"],
        ["pytest", "tests/test2.py", "-v"],
    ]
    test_files = extract_test_files_from_command(validation_commands)
    assert "tests/test1.py" in test_files
    assert "tests/test2.py" in test_files


def test_extract_from_legacy_validation_command_format():
    """Test extracting test files from legacy validationCommand format."""
    validation_command = ["pytest", "tests/test1.py", "tests/test2.py", "-v"]
    test_files = extract_test_files_from_command(validation_command)
    assert "tests/test1.py" in test_files
    assert "tests/test2.py" in test_files


def test_dev_bootstrap_executes_multiple_commands():
    """Test that dev_bootstrap.py executes multiple commands from validationCommands."""
    with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
        manifest = {
            "goal": "Test multiple commands",
            "readonlyFiles": [],
            "expectedArtifacts": {"file": "test.py", "contains": []},
            "validationCommands": [
                ["python", "-c", "print('Command 1')"],
                ["python", "-c", "print('Command 2')"],
            ],
        }
        json.dump(manifest, f)
        manifest_path = f.name

    try:
        runner = MAIDDevRunner(manifest_path)
        # Mock the subprocess.run to avoid actually running commands
        original_run = subprocess.run

        results = []

        def mock_run(cmd, **kwargs):
            results.append(cmd)

            class MockResult:
                returncode = 0
                stdout = f"Mock output for {' '.join(cmd)}"
                stderr = ""

            return MockResult()

        subprocess.run = mock_run
        try:
            success = runner.run_validation()
            assert success
            assert len(results) == 2
            assert results[0] == ["python", "-c", "print('Command 1')"]
            assert results[1] == ["python", "-c", "print('Command 2')"]
        finally:
            subprocess.run = original_run
    finally:
        Path(manifest_path).unlink()


def test_dev_bootstrap_still_works_with_single_command():
    """Test that dev_bootstrap.py still works with legacy validationCommand."""
    with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
        manifest = {
            "goal": "Test single command",
            "readonlyFiles": [],
            "expectedArtifacts": {"file": "test.py", "contains": []},
            "validationCommand": ["python", "-c", "print('Single command')"],
        }
        json.dump(manifest, f)
        manifest_path = f.name

    try:
        runner = MAIDDevRunner(manifest_path)
        # Mock the subprocess.run to avoid actually running commands
        original_run = subprocess.run

        results = []

        def mock_run(cmd, **kwargs):
            results.append(cmd)

            class MockResult:
                returncode = 0
                stdout = f"Mock output for {' '.join(cmd)}"
                stderr = ""

            return MockResult()

        subprocess.run = mock_run
        try:
            success = runner.run_validation()
            assert success
            assert len(results) == 1
            assert results[0] == ["python", "-c", "print('Single command')"]
        finally:
            subprocess.run = original_run
    finally:
        Path(manifest_path).unlink()


def test_extract_handles_empty_validation_commands():
    """Test that extract handles empty validationCommands."""
    test_files = extract_test_files_from_command([])
    assert test_files == []


def test_extract_handles_nested_empty_arrays():
    """Test that extract handles nested empty arrays in validationCommands."""
    validation_commands = [
        ["pytest", "tests/test1.py"],
        [],
        ["pytest", "tests/test2.py"],
    ]
    test_files = extract_test_files_from_command(validation_commands)
    assert "tests/test1.py" in test_files
    assert "tests/test2.py" in test_files
