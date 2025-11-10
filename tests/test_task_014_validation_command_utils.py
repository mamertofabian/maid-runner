"""Behavioral tests for validation command utilities."""

from maid_runner.utils import normalize_validation_commands


def test_normalizes_enhanced_validation_commands_format():
    """Test that enhanced format (validationCommands) is returned as-is."""
    manifest_data = {
        "validationCommands": [
            ["pytest", "tests/test1.py", "-v"],
            ["pytest", "tests/test2.py"],
        ]
    }
    result = normalize_validation_commands(manifest_data)
    assert result == [
        ["pytest", "tests/test1.py", "-v"],
        ["pytest", "tests/test2.py"],
    ]


def test_normalizes_legacy_single_command_array():
    """Test that legacy single command array format is normalized."""
    manifest_data = {"validationCommand": ["pytest", "tests/test.py", "-v"]}
    result = normalize_validation_commands(manifest_data)
    assert result == [["pytest", "tests/test.py", "-v"]]


def test_normalizes_legacy_multiple_string_commands():
    """Test that legacy multiple string commands format is normalized."""
    manifest_data = {
        "validationCommand": [
            "pytest tests/test1.py",
            "pytest tests/test2.py",
        ]
    }
    result = normalize_validation_commands(manifest_data)
    assert result == [
        ["pytest", "tests/test1.py"],
        ["pytest", "tests/test2.py"],
    ]


def test_normalizes_legacy_single_string_command():
    """Test that legacy single string command format is normalized."""
    manifest_data = {"validationCommand": "pytest tests/test.py -v"}
    result = normalize_validation_commands(manifest_data)
    assert result == [["pytest", "tests/test.py", "-v"]]


def test_normalizes_legacy_single_string_in_array():
    """Test that legacy single string command in array format is normalized."""
    manifest_data = {"validationCommand": ["pytest tests/test.py -v"]}
    result = normalize_validation_commands(manifest_data)
    assert result == [["pytest", "tests/test.py", "-v"]]


def test_returns_empty_list_when_no_validation_commands():
    """Test that empty list is returned when no validation commands exist."""
    manifest_data = {}
    result = normalize_validation_commands(manifest_data)
    assert result == []


def test_returns_empty_list_when_validation_command_is_empty():
    """Test that empty list is returned when validationCommand is empty."""
    manifest_data = {"validationCommand": []}
    result = normalize_validation_commands(manifest_data)
    assert result == []


def test_prefers_enhanced_format_over_legacy():
    """Test that enhanced format (validationCommands) is preferred over legacy."""
    manifest_data = {
        "validationCommands": [["pytest", "test1.py"]],
        "validationCommand": ["pytest", "test2.py"],
    }
    result = normalize_validation_commands(manifest_data)
    assert result == [["pytest", "test1.py"]]


def test_handles_complex_command_with_flags():
    """Test that complex commands with multiple flags are preserved."""
    manifest_data = {
        "validationCommand": [
            "pytest tests/test.py -v --tb=short --maxfail=1",
        ]
    }
    result = normalize_validation_commands(manifest_data)
    assert result == [["pytest", "tests/test.py", "-v", "--tb=short", "--maxfail=1"]]


def test_handles_multiple_commands_with_different_flags():
    """Test that multiple commands with different flags are preserved."""
    manifest_data = {
        "validationCommand": [
            "pytest tests/test1.py -v",
            "pytest tests/test2.py -vv",
        ]
    }
    result = normalize_validation_commands(manifest_data)
    assert result == [
        ["pytest", "tests/test1.py", "-v"],
        ["pytest", "tests/test2.py", "-vv"],
    ]


def test_normalize_handles_quoted_arguments():
    """Test command strings with quoted arguments."""
    manifest_data = {"validationCommand": "pytest tests/ -k 'test user validation'"}
    result = normalize_validation_commands(manifest_data)
    assert result == [["pytest", "tests/", "-k", "test user validation"]]


def test_normalize_handles_quoted_arguments_in_array():
    """Test command strings with quoted arguments in array format."""
    manifest_data = {
        "validationCommand": [
            "pytest tests/ -k 'test user validation'",
            "pytest tests/ -k 'test admin validation'",
        ]
    }
    result = normalize_validation_commands(manifest_data)
    assert result == [
        ["pytest", "tests/", "-k", "test user validation"],
        ["pytest", "tests/", "-k", "test admin validation"],
    ]


def test_normalize_handles_file_paths_with_spaces():
    """Test command strings with file paths containing spaces."""
    manifest_data = {"validationCommand": 'pytest "tests/test file with spaces.py" -v'}
    result = normalize_validation_commands(manifest_data)
    assert result == [["pytest", "tests/test file with spaces.py", "-v"]]
