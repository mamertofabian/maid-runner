"""Behavioral tests for command existence validation."""

import pytest

from maid_runner.utils import check_command_exists


def test_check_command_exists_returns_true_for_existing_command():
    """Test that check_command_exists returns True for commands that exist in PATH."""
    # Use a command that should exist on most systems
    result = check_command_exists(["pytest"])

    assert result[0] is True
    assert result[1] is None


def test_check_command_exists_returns_false_for_nonexistent_command():
    """Test that check_command_exists returns False for commands that don't exist."""
    result = check_command_exists(["nonexistent-command-xyz-12345"])

    assert result[0] is False
    assert result[1] == "Command 'nonexistent-command-xyz-12345' not found in PATH"


def test_check_command_exists_handles_empty_command():
    """Test that check_command_exists handles empty command list."""
    result = check_command_exists([])

    assert result[0] is False
    assert result[1] == "Empty command"


def test_check_command_exists_works_with_command_arguments():
    """Test that check_command_exists only checks the first element (command name)."""
    # Should work even with arguments - only first element is checked
    result = check_command_exists(["pytest", "tests/test.py", "-v"])

    assert result[0] is True
    assert result[1] is None


def test_check_command_exists_handles_common_commands():
    """Test that check_command_exists works with various common commands."""
    # Test with commands that might exist
    common_commands = ["python3", "python", "pytest", "uv"]

    for cmd in common_commands:
        exists, error_msg = check_command_exists([cmd])
        # At least one of these should exist
        if exists:
            assert error_msg is None
            break
    else:
        # If none exist, that's also a valid test scenario
        pytest.skip("No common commands found in PATH for testing")


def test_check_command_exists_error_message_format():
    """Test that error messages have the correct format."""
    result = check_command_exists(["missing-cmd-xyz"])

    assert result[0] is False
    assert isinstance(result[1], str)
    assert "Command 'missing-cmd-xyz' not found in PATH" in result[1]


def test_json_output_mode_validates_command_existence(tmp_path):
    """Test that JSON output mode validates command existence."""
    import json
    from maid_runner.cli.validate import _perform_core_validation

    # Create a manifest with a missing command
    manifest_path = tmp_path / "test.manifest.json"
    manifest_data = {
        "goal": "Test JSON validation",
        "taskType": "create",
        "creatableFiles": ["test.py"],
        "readonlyFiles": [],
        "expectedArtifacts": {
            "file": "test.py",
            "contains": [
                {"type": "function", "name": "test_func", "args": [], "returns": "str"}
            ],
        },
        "validationCommand": ["nonexistent-command-xyz-123"],
    }
    with open(manifest_path, "w") as f:
        json.dump(manifest_data, f)

    # Test behavioral mode
    result = _perform_core_validation(
        str(manifest_path), "behavioral", use_manifest_chain=False, use_cache=False
    )

    assert result.success is False
    assert len(result.errors) > 0
    assert any("not found in PATH" in error.message for error in result.errors)


def test_json_output_mode_validates_command_existence_implementation_mode(tmp_path):
    """Test that JSON output mode validates command existence in implementation mode."""
    import json
    from maid_runner.cli.validate import _perform_core_validation

    # Create a manifest with a missing command and existing file
    manifest_path = tmp_path / "test.manifest.json"
    test_file = tmp_path / "test.py"
    test_file.write_text('def test_func() -> str: return "test"')

    manifest_data = {
        "goal": "Test JSON validation",
        "taskType": "create",
        "creatableFiles": [str(test_file)],
        "readonlyFiles": [],
        "expectedArtifacts": {
            "file": str(test_file),
            "contains": [
                {"type": "function", "name": "test_func", "args": [], "returns": "str"}
            ],
        },
        "validationCommand": ["nonexistent-command-xyz-456"],
    }
    with open(manifest_path, "w") as f:
        json.dump(manifest_data, f)

    # Test implementation mode
    result = _perform_core_validation(
        str(manifest_path), "implementation", use_manifest_chain=False, use_cache=False
    )

    assert result.success is False
    assert len(result.errors) > 0
    assert any("not found in PATH" in error.message for error in result.errors)


def test_json_output_mode_validates_test_file_existence(tmp_path):
    """Test that JSON output mode validates test file existence."""
    import json
    from maid_runner.cli.validate import _perform_core_validation

    # Create a manifest with existing file but missing test file
    manifest_path = tmp_path / "test.manifest.json"
    test_file = tmp_path / "test.py"
    test_file.write_text('def test_func() -> str: return "test"')

    manifest_data = {
        "goal": "Test JSON validation",
        "taskType": "create",
        "creatableFiles": [str(test_file)],
        "readonlyFiles": [],
        "expectedArtifacts": {
            "file": str(test_file),
            "contains": [
                {"type": "function", "name": "test_func", "args": [], "returns": "str"}
            ],
        },
        "validationCommand": ["pytest", "tests/test_missing.py"],
    }
    with open(manifest_path, "w") as f:
        json.dump(manifest_data, f)

    # Test implementation mode
    result = _perform_core_validation(
        str(manifest_path), "implementation", use_manifest_chain=False, use_cache=False
    )

    assert result.success is False
    assert len(result.errors) > 0
    assert any("Test file(s) not found" in error.message for error in result.errors)


def test_json_output_mode_validates_test_file_existence_behavioral_mode(tmp_path):
    """Test that JSON output mode validates test file existence in behavioral mode."""
    import json
    from maid_runner.cli.validate import _perform_core_validation

    # Create a manifest with missing test file
    manifest_path = tmp_path / "test.manifest.json"

    manifest_data = {
        "goal": "Test JSON validation",
        "taskType": "create",
        "creatableFiles": ["test.py"],
        "readonlyFiles": [],
        "expectedArtifacts": {
            "file": "test.py",
            "contains": [
                {"type": "function", "name": "test_func", "args": [], "returns": "str"}
            ],
        },
        "validationCommand": ["pytest", "tests/test_missing.py"],
    }
    with open(manifest_path, "w") as f:
        json.dump(manifest_data, f)

    # Test behavioral mode
    result = _perform_core_validation(
        str(manifest_path), "behavioral", use_manifest_chain=False, use_cache=False
    )

    assert result.success is False
    assert len(result.errors) > 0
    assert any("Test file(s) not found" in error.message for error in result.errors)
