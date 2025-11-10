"""Tests for behavioral validation without implementation file existing.

Behavioral validation during the planning phase should:
- NOT require the implementation file to exist
- Check that test files exist instead
- Validate that tests USE the declared artifacts

Implementation validation should:
- Require the implementation file to exist
"""

import json
import subprocess
from pathlib import Path


def test_behavioral_validation_succeeds_without_implementation_file(tmp_path: Path):
    """Test that behavioral validation passes even when implementation doesn't exist."""
    # Create a manifest for a non-existent implementation file
    manifest = {
        "goal": "Test behavioral validation without implementation",
        "taskType": "create",
        "creatableFiles": ["src/nonexistent_module.py"],
        "readonlyFiles": ["tests/test_nonexistent.py"],
        "expectedArtifacts": {
            "file": "src/nonexistent_module.py",
            "contains": [
                {"type": "class", "name": "MyClass"},
                {
                    "type": "function",
                    "name": "my_function",
                    "class": "MyClass",
                    "args": [],
                },
            ],
        },
        "validationCommand": ["pytest", "tests/test_nonexistent.py", "-v"],
    }

    manifest_file = tmp_path / "test-manifest.json"
    manifest_file.write_text(json.dumps(manifest, indent=2))

    # Create test file that USES the artifacts
    test_dir = tmp_path / "tests"
    test_dir.mkdir()
    test_file = test_dir / "test_nonexistent.py"
    test_file.write_text(
        """
from src.nonexistent_module import MyClass

def test_my_class():
    obj = MyClass()
    obj.my_function()
"""
    )

    # The implementation file does NOT exist
    src_dir = tmp_path / "src"
    src_dir.mkdir()
    # DO NOT create src/nonexistent_module.py

    # Run behavioral validation - should PASS
    result = subprocess.run(
        ["maid", "validate", str(manifest_file), "--validation-mode", "behavioral"],
        cwd=str(tmp_path),
        capture_output=True,
        text=True,
    )

    # Should succeed because we're only checking if tests USE the artifacts
    assert (
        result.returncode == 0
    ), f"Behavioral validation should pass without implementation.\nStdout: {result.stdout}\nStderr: {result.stderr}"
    assert "Behavioral test validation PASSED" in result.stdout


def test_implementation_validation_fails_without_implementation_file(tmp_path: Path):
    """Test that implementation validation fails when implementation doesn't exist."""
    manifest = {
        "goal": "Test implementation validation requires implementation",
        "taskType": "create",
        "creatableFiles": ["src/nonexistent_impl.py"],
        "readonlyFiles": ["tests/test_nonexistent_impl.py"],
        "expectedArtifacts": {
            "file": "src/nonexistent_impl.py",
            "contains": [{"type": "function", "name": "my_func", "args": []}],
        },
        "validationCommand": ["pytest", "tests/test_nonexistent_impl.py", "-v"],
    }

    manifest_file = tmp_path / "test-manifest.json"
    manifest_file.write_text(json.dumps(manifest, indent=2))

    # Create test file
    test_dir = tmp_path / "tests"
    test_dir.mkdir()
    test_file = test_dir / "test_nonexistent_impl.py"
    test_file.write_text(
        """
from src.nonexistent_impl import my_func

def test_my_func():
    result = my_func()
    assert result is not None
"""
    )

    # The implementation file does NOT exist
    src_dir = tmp_path / "src"
    src_dir.mkdir()

    # Run implementation validation - should FAIL
    result = subprocess.run(
        ["maid", "validate", str(manifest_file), "--validation-mode", "implementation"],
        cwd=str(tmp_path),
        capture_output=True,
        text=True,
    )

    # Should fail because implementation file doesn't exist
    assert result.returncode != 0
    assert (
        "Target file not found" in result.stdout
        or "Target file not found" in result.stderr
    )


def test_behavioral_validation_fails_when_test_file_missing(tmp_path: Path):
    """Test that behavioral validation fails when test file doesn't exist."""
    manifest = {
        "goal": "Test behavioral validation requires test files",
        "taskType": "create",
        "creatableFiles": ["src/module.py"],
        "readonlyFiles": ["tests/test_missing.py"],
        "expectedArtifacts": {
            "file": "src/module.py",
            "contains": [{"type": "function", "name": "func", "args": []}],
        },
        "validationCommand": ["pytest", "tests/test_missing.py", "-v"],
    }

    manifest_file = tmp_path / "test-manifest.json"
    manifest_file.write_text(json.dumps(manifest, indent=2))

    # Create src directory but NO test file
    src_dir = tmp_path / "src"
    src_dir.mkdir()
    test_dir = tmp_path / "tests"
    test_dir.mkdir()
    # DO NOT create tests/test_missing.py

    # Run behavioral validation - should FAIL
    result = subprocess.run(
        ["maid", "validate", str(manifest_file), "--validation-mode", "behavioral"],
        cwd=str(tmp_path),
        capture_output=True,
        text=True,
    )

    # Should fail because test file doesn't exist
    assert result.returncode != 0
    assert (
        "test file" in result.stdout.lower()
        or "test file" in result.stderr.lower()
        or "not found" in result.stdout.lower()
    )


def test_default_mode_is_implementation(tmp_path: Path):
    """Test that default validation mode (no --validation-mode flag) checks implementation."""
    manifest = {
        "goal": "Test default validation mode",
        "taskType": "create",
        "creatableFiles": ["src/default_test.py"],
        "readonlyFiles": [],
        "expectedArtifacts": {
            "file": "src/default_test.py",
            "contains": [{"type": "function", "name": "test_func", "args": []}],
        },
        "validationCommand": [],
    }

    manifest_file = tmp_path / "test-manifest.json"
    manifest_file.write_text(json.dumps(manifest, indent=2))

    # Don't create implementation file
    src_dir = tmp_path / "src"
    src_dir.mkdir()

    # Run validation without --validation-mode flag (default is implementation)
    result = subprocess.run(
        ["maid", "validate", str(manifest_file)],
        cwd=str(tmp_path),
        capture_output=True,
        text=True,
    )

    # Should fail because default mode is implementation and file doesn't exist
    assert result.returncode != 0
