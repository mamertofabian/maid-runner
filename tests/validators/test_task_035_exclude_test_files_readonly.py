# tests/validators/test_task_035_exclude_test_files_readonly.py
"""Behavioral tests for excluding test files from readonlyFiles warning.

Test files are naturally and correctly placed in readonlyFiles, so they
should not trigger the "Only in readonlyFiles" warning in file tracking analysis.
"""

from maid_runner.validators.file_tracker import (
    FILE_STATUS_REGISTERED,
    FILE_STATUS_TRACKED,
    classify_file_status,
    _is_test_file,
)


# ============================================================================
# Test Helper Function _is_test_file
# ============================================================================


def test_is_test_file_identifies_test_directory():
    """Test that _is_test_file identifies files in tests/ directory."""
    assert _is_test_file("tests/test_module.py") is True
    assert _is_test_file("tests/subdir/test_utils.py") is True
    assert _is_test_file("tests/validators/test_tracking.py") is True


def test_is_test_file_identifies_test_prefix():
    """Test that _is_test_file identifies files with test_ prefix."""
    assert _is_test_file("test_module.py") is True
    assert _is_test_file("subdir/test_utils.py") is True


def test_is_test_file_rejects_non_test_files():
    """Test that _is_test_file rejects non-test files."""
    assert _is_test_file("module.py") is False
    assert _is_test_file("src/utils.py") is False
    assert _is_test_file("maid_runner/cli/main.py") is False


def test_is_test_file_rejects_files_containing_test():
    """Test that _is_test_file rejects files that merely contain 'test' in name."""
    # Files must start with test_ or be in tests/, not just contain 'test'
    assert _is_test_file("my_testing_module.py") is False
    assert _is_test_file("attest.py") is False


# ============================================================================
# Test classify_file_status with Test Files
# ============================================================================


def test_classify_file_status_test_file_readonly_only_is_tracked():
    """Test that test files only in readonlyFiles are classified as TRACKED."""
    tracked_info = {
        "readonly": True,
        "created": False,
        "edited": False,
        "has_artifacts": False,
        "has_tests": False,
        "manifests": ["task-001"],
    }

    # Test file in tests/ directory
    status, issues = classify_file_status("tests/test_module.py", tracked_info)

    assert status == FILE_STATUS_TRACKED
    assert len(issues) == 0


def test_classify_file_status_test_file_with_prefix_readonly_only_is_tracked():
    """Test that test_ prefixed files only in readonlyFiles are TRACKED."""
    tracked_info = {
        "readonly": True,
        "created": False,
        "edited": False,
        "has_artifacts": False,
        "has_tests": False,
        "manifests": ["task-001"],
    }

    # Test file with test_ prefix
    status, issues = classify_file_status("test_integration.py", tracked_info)

    assert status == FILE_STATUS_TRACKED
    assert len(issues) == 0


def test_classify_file_status_non_test_file_readonly_only_is_registered():
    """Test that non-test files only in readonlyFiles are still REGISTERED."""
    tracked_info = {
        "readonly": True,
        "created": False,
        "edited": False,
        "has_artifacts": False,
        "has_tests": False,
        "manifests": ["task-001"],
    }

    # Non-test file
    status, issues = classify_file_status("utils.py", tracked_info)

    assert status == FILE_STATUS_REGISTERED
    assert any("Only in readonlyFiles" in issue for issue in issues)


def test_classify_file_status_test_file_in_subdir():
    """Test that test files in subdirectories are handled correctly."""
    tracked_info = {
        "readonly": True,
        "created": False,
        "edited": False,
        "has_artifacts": False,
        "has_tests": False,
        "manifests": ["task-010"],
    }

    status, issues = classify_file_status(
        "tests/validators/test_ast_validator.py", tracked_info
    )

    assert status == FILE_STATUS_TRACKED
    assert len(issues) == 0
