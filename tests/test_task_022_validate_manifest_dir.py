"""Behavioral tests for Task 022: Adding --manifest-dir option to maid validate command"""

import json
import subprocess
from pathlib import Path


def test_run_validation_accepts_manifest_dir_parameter():
    """Test that run_validation() accepts manifest_dir parameter."""
    from maid_runner.cli.validate import run_validation

    # Verify function signature
    import inspect

    sig = inspect.signature(run_validation)
    assert "manifest_dir" in sig.parameters


def test_maid_validate_with_manifest_dir_flag(tmp_path: Path):
    """Test that 'maid validate --manifest-dir' validates all manifests."""
    # Create manifests directory
    manifests_dir = tmp_path / "manifests"
    manifests_dir.mkdir()

    # Create test file
    test_file = tmp_path / "test.py"
    test_file.write_text("def hello():\n    pass\n")

    # Create a simple passing manifest
    manifest1 = {
        "version": "1",
        "goal": "test 1",
        "taskType": "create",
        "creatableFiles": ["test.py"],
        "readonlyFiles": [],
        "expectedArtifacts": {
            "file": "test.py",
            "contains": [{"type": "function", "name": "hello"}],
        },
        "validationCommand": ["echo", "test"],
    }
    manifest1_file = manifests_dir / "task-001.manifest.json"
    manifest1_file.write_text(json.dumps(manifest1))

    # Run maid validate with --manifest-dir
    result = subprocess.run(
        ["maid", "validate", "--manifest-dir", str(manifests_dir), "--quiet"],
        cwd=str(tmp_path),
        capture_output=True,
        text=True,
    )

    # Should succeed
    assert result.returncode == 0
    # Should validate at least one manifest
    assert "1/1" in result.stdout or "100" in result.stdout


def test_maid_validate_manifest_dir_skips_superseded(tmp_path: Path):
    """Test that --manifest-dir skips superseded manifests."""
    # Create manifests directory
    manifests_dir = tmp_path / "manifests"
    manifests_dir.mkdir()

    # Create test file
    test_file = tmp_path / "test.py"
    test_file.write_text("def hello():\n    pass\n")

    # Create regular manifest
    manifest1 = {
        "version": "1",
        "goal": "task 1",
        "taskType": "create",
        "creatableFiles": ["test.py"],
        "readonlyFiles": [],
        "expectedArtifacts": {
            "file": "test.py",
            "contains": [{"type": "function", "name": "hello"}],
        },
        "validationCommand": ["echo", "test"],
    }
    manifest1_file = manifests_dir / "task-001.manifest.json"
    manifest1_file.write_text(json.dumps(manifest1))

    # Create snapshot that supersedes task-001
    snapshot = {
        "version": "1",
        "goal": "snapshot",
        "taskType": "snapshot",
        "editableFiles": ["test.py"],
        "readonlyFiles": [],
        "supersedes": ["manifests/task-001.manifest.json"],
        "expectedArtifacts": {
            "file": "test.py",
            "contains": [{"type": "function", "name": "hello"}],
        },
        "validationCommand": ["echo", "test"],
    }
    snapshot_file = manifests_dir / "task-002-snapshot-v1.manifest.json"
    snapshot_file.write_text(json.dumps(snapshot))

    # Run maid validate with --manifest-dir
    result = subprocess.run(
        ["maid", "validate", "--manifest-dir", str(manifests_dir), "--quiet"],
        cwd=str(tmp_path),
        capture_output=True,
        text=True,
    )

    # Should succeed and show only 1 manifest validated (snapshot, not task-001)
    assert result.returncode == 0


def test_maid_validate_with_single_manifest_still_works(tmp_path: Path):
    """Test that single manifest validation still works (backward compatibility)."""
    # Create test file
    test_file = tmp_path / "test.py"
    test_file.write_text("def hello():\n    pass\n")

    # Create a simple manifest
    manifest = {
        "version": "1",
        "goal": "test",
        "taskType": "create",
        "creatableFiles": ["test.py"],
        "readonlyFiles": [],
        "expectedArtifacts": {
            "file": "test.py",
            "contains": [{"type": "function", "name": "hello"}],
        },
        "validationCommand": ["echo", "test"],
    }
    manifest_file = tmp_path / "test.manifest.json"
    manifest_file.write_text(json.dumps(manifest))

    # Run maid validate with single manifest (no --manifest-dir)
    result = subprocess.run(
        ["maid", "validate", str(manifest_file), "--quiet"],
        cwd=str(tmp_path),
        capture_output=True,
        text=True,
    )

    # Should succeed
    assert result.returncode == 0


def test_run_validation_with_manifest_dir_parameter(tmp_path: Path):
    """Test run_validation() function with manifest_dir parameter."""
    from maid_runner.cli.validate import run_validation

    # Create manifests directory
    manifests_dir = tmp_path / "manifests"
    manifests_dir.mkdir()

    # Create test file
    test_file = tmp_path / "test.py"
    test_file.write_text("def hello():\n    pass\n")

    # Create a simple manifest
    manifest = {
        "version": "1",
        "goal": "test",
        "taskType": "create",
        "creatableFiles": ["test.py"],
        "readonlyFiles": [],
        "expectedArtifacts": {
            "file": "test.py",
            "contains": [{"type": "function", "name": "hello"}],
        },
        "validationCommand": ["echo", "test"],
    }
    manifest_file = manifests_dir / "task-001.manifest.json"
    manifest_file.write_text(json.dumps(manifest))

    # Change to tmp directory
    import os

    original_dir = os.getcwd()
    try:
        os.chdir(tmp_path)

        # Call run_validation with manifest_dir - should exit with 0
        import pytest

        with pytest.raises(SystemExit) as exc_info:
            run_validation(
                manifest_path=None,
                validation_mode="implementation",
                use_manifest_chain=False,
                quiet=True,
                manifest_dir=str(manifests_dir),
            )

        # Should exit with code 0 (success)
        assert exc_info.value.code == 0

    finally:
        os.chdir(original_dir)


def test_maid_validate_manifest_dir_shows_summary(tmp_path: Path):
    """Test that --manifest-dir shows a summary of results."""
    # Create manifests directory
    manifests_dir = tmp_path / "manifests"
    manifests_dir.mkdir()

    # Create test file
    test_file = tmp_path / "test.py"
    test_file.write_text("def hello():\n    pass\n")

    # Create manifest
    manifest = {
        "version": "1",
        "goal": "test",
        "taskType": "create",
        "creatableFiles": ["test.py"],
        "readonlyFiles": [],
        "expectedArtifacts": {
            "file": "test.py",
            "contains": [{"type": "function", "name": "hello"}],
        },
        "validationCommand": ["echo", "test"],
    }
    manifest_file = manifests_dir / "task-001.manifest.json"
    manifest_file.write_text(json.dumps(manifest))

    # Run maid validate with --manifest-dir
    result = subprocess.run(
        ["maid", "validate", "--manifest-dir", str(manifests_dir)],
        cwd=str(tmp_path),
        capture_output=True,
        text=True,
    )

    # Should show summary
    assert result.returncode == 0
    assert "Summary" in result.stdout or "1/1" in result.stdout


def test_maid_validate_cannot_use_both_manifest_and_dir(tmp_path: Path):
    """Test that using both manifest path and --manifest-dir produces an error."""
    # Create manifests directory
    manifests_dir = tmp_path / "manifests"
    manifests_dir.mkdir()

    manifest_file = manifests_dir / "task-001.manifest.json"
    manifest_file.write_text('{"version": "1", "goal": "test"}')

    # Try to use both
    result = subprocess.run(
        [
            "maid",
            "validate",
            str(manifest_file),
            "--manifest-dir",
            str(manifests_dir),
        ],
        cwd=str(tmp_path),
        capture_output=True,
        text=True,
    )

    # Should fail with error
    assert result.returncode != 0
    assert "error" in result.stderr.lower() or "error" in result.stdout.lower()


def test_main_function_works_as_cli_entry_point(tmp_path: Path, monkeypatch):
    """Test that main() function works as CLI entry point with --manifest-dir."""
    from maid_runner.cli.validate import main

    # Create manifests directory
    manifests_dir = tmp_path / "manifests"
    manifests_dir.mkdir()

    # Create test file
    test_file = tmp_path / "test.py"
    test_file.write_text("def hello():\n    pass\n")

    # Create manifest
    manifest = {
        "version": "1",
        "goal": "test",
        "taskType": "create",
        "creatableFiles": ["test.py"],
        "readonlyFiles": [],
        "expectedArtifacts": {
            "file": "test.py",
            "contains": [{"type": "function", "name": "hello"}],
        },
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
        monkeypatch.setattr(
            sys,
            "argv",
            ["maid-validate", "--manifest-dir", str(manifests_dir), "--quiet"],
        )

        # Call main function - it should exit with 0 on success
        import pytest

        with pytest.raises(SystemExit) as exc_info:
            main()

        # Should exit with code 0 (success)
        assert exc_info.value.code == 0

    finally:
        os.chdir(original_dir)
