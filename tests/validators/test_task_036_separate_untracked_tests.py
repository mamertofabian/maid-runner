# tests/validators/test_task_036_separate_untracked_tests.py
"""Behavioral tests for separating untracked test files from UNDECLARED category.

Untracked test files should be reported separately with informational-level
messaging rather than high-priority UNDECLARED warnings.
"""

from pathlib import Path
from maid_runner.validators.file_tracker import (
    FileTrackingAnalysis,
    analyze_file_tracking,
)


# ============================================================================
# Test FileTrackingAnalysis Structure
# ============================================================================


def test_file_tracking_analysis_has_untracked_tests_field():
    """Test that FileTrackingAnalysis TypedDict includes untracked_tests field."""
    # Verify the type annotation exists
    assert hasattr(FileTrackingAnalysis, "__annotations__")
    annotations = FileTrackingAnalysis.__annotations__

    # Check all expected fields
    assert "undeclared" in annotations
    assert "registered" in annotations
    assert "tracked" in annotations
    assert "untracked_tests" in annotations


# ============================================================================
# Test Untracked Test Files Separation
# ============================================================================


def test_analyze_file_tracking_separates_untracked_test_files(tmp_path: Path):
    """Test that test files not in manifests go to untracked_tests, not undeclared."""
    # Create test files
    (tmp_path / "module.py").write_text("# implementation file")
    (tmp_path / "tests").mkdir()
    (tmp_path / "tests" / "test_module.py").write_text("# test file")

    # Empty manifest chain - nothing is tracked
    manifest_chain = []

    analysis = analyze_file_tracking(manifest_chain, str(tmp_path))

    # Implementation file should be in undeclared
    undeclared_files = [f["file"] for f in analysis["undeclared"]]
    assert "module.py" in undeclared_files

    # Test file should be in untracked_tests, NOT undeclared
    assert "tests/test_module.py" not in undeclared_files
    assert "tests/test_module.py" in analysis["untracked_tests"]


def test_analyze_file_tracking_handles_test_prefix_files(tmp_path: Path):
    """Test that files with test_ prefix are categorized as untracked_tests."""
    # Create file with test_ prefix at root level
    (tmp_path / "test_integration.py").write_text("# integration test")
    (tmp_path / "app.py").write_text("# app file")

    manifest_chain = []

    analysis = analyze_file_tracking(manifest_chain, str(tmp_path))

    # test_ prefixed file should be in untracked_tests
    assert "test_integration.py" in analysis["untracked_tests"]

    # Regular file should be in undeclared
    undeclared_files = [f["file"] for f in analysis["undeclared"]]
    assert "app.py" in undeclared_files


def test_analyze_file_tracking_mixed_untracked_files(tmp_path: Path):
    """Test proper categorization with mix of untracked test and non-test files."""
    # Create various untracked files
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "module.py").write_text("# source")
    (tmp_path / "tests").mkdir()
    (tmp_path / "tests" / "test_one.py").write_text("# test")
    (tmp_path / "tests" / "test_two.py").write_text("# test")
    (tmp_path / "utils.py").write_text("# utility")
    (tmp_path / "test_manual.py").write_text("# manual test")

    manifest_chain = []

    analysis = analyze_file_tracking(manifest_chain, str(tmp_path))

    # Check undeclared (non-test files only)
    undeclared_files = [f["file"] for f in analysis["undeclared"]]
    assert "src/module.py" in undeclared_files
    assert "utils.py" in undeclared_files
    assert len(undeclared_files) == 2

    # Check untracked_tests (test files only)
    assert "tests/test_one.py" in analysis["untracked_tests"]
    assert "tests/test_two.py" in analysis["untracked_tests"]
    assert "test_manual.py" in analysis["untracked_tests"]
    assert len(analysis["untracked_tests"]) == 3


def test_analyze_file_tracking_tracked_test_files_not_in_untracked(tmp_path: Path):
    """Test that test files referenced in manifests don't appear in untracked_tests."""
    # Create test file
    (tmp_path / "tests").mkdir()
    (tmp_path / "tests" / "test_module.py").write_text("# test")

    # Manifest references the test file in readonlyFiles
    manifest_chain = [
        {
            "goal": "Create module",
            "creatableFiles": ["module.py"],
            "readonlyFiles": ["tests/test_module.py"],
            "expectedArtifacts": {
                "file": "module.py",
                "contains": [{"type": "function", "name": "func"}],
            },
            "validationCommand": ["pytest", "tests/test_module.py"],
        }
    ]

    analysis = analyze_file_tracking(manifest_chain, str(tmp_path))

    # Test file should be tracked, not in untracked_tests
    assert "tests/test_module.py" in analysis["tracked"]
    assert "tests/test_module.py" not in analysis["untracked_tests"]


def test_analyze_file_tracking_untracked_tests_empty_when_all_tracked(tmp_path: Path):
    """Test that untracked_tests is empty when all test files are in manifests."""
    (tmp_path / "tests").mkdir()
    (tmp_path / "tests" / "test_a.py").write_text("# test a")
    (tmp_path / "tests" / "test_b.py").write_text("# test b")

    manifest_chain = [
        {
            "goal": "Tests",
            "creatableFiles": ["app.py"],
            "readonlyFiles": ["tests/test_a.py", "tests/test_b.py"],
            "expectedArtifacts": {"file": "app.py", "contains": []},
            "validationCommand": ["pytest", "tests/"],
        }
    ]

    analysis = analyze_file_tracking(manifest_chain, str(tmp_path))

    # Both test files should be tracked
    assert "tests/test_a.py" in analysis["tracked"]
    assert "tests/test_b.py" in analysis["tracked"]

    # untracked_tests should be empty
    assert len(analysis["untracked_tests"]) == 0


# ============================================================================
# Test Return Type Structure
# ============================================================================


def test_analyze_file_tracking_returns_all_expected_fields(tmp_path: Path):
    """Test that analyze_file_tracking returns all expected fields in result."""
    manifest_chain = []

    analysis = analyze_file_tracking(manifest_chain, str(tmp_path))

    # Verify all expected fields are present
    assert "undeclared" in analysis
    assert "registered" in analysis
    assert "tracked" in analysis
    assert "untracked_tests" in analysis

    # Verify types
    assert isinstance(analysis["undeclared"], list)
    assert isinstance(analysis["registered"], list)
    assert isinstance(analysis["tracked"], list)
    assert isinstance(analysis["untracked_tests"], list)
