"""
Tests for _find_imported_test_files private function in validate.py.

This tests the implementation detail that discovers imported test modules
from test files, supporting split test file patterns.
"""

import pytest
from pathlib import Path

from maid_runner.cli.validate import _find_imported_test_files


class TestFindImportedTestFiles:
    """Test the _find_imported_test_files function."""

    def test_finds_imported_test_files_from_tests_module(self, tmp_path: Path):
        """Test finding imported test files from tests.* imports."""
        # Create test directory structure
        tests_dir = tmp_path / "tests"
        tests_dir.mkdir()

        # Create imported test files
        imported_file1 = tests_dir / "_test_split_one.py"
        imported_file1.write_text("def test_one(): pass")

        imported_file2 = tests_dir / "_test_split_two.py"
        imported_file2.write_text("def test_two(): pass")

        # Create main test file that imports from tests module
        main_test_file = tests_dir / "test_main.py"
        main_test_file.write_text(
            """
import pytest
from tests._test_split_one import TestClassOne
from tests._test_split_two import TestClassTwo

def test_main():
    pass
"""
        )

        result = _find_imported_test_files(str(main_test_file))

        # Should find both imported test files
        assert len(result) == 2
        assert str(imported_file1) in result
        assert str(imported_file2) in result

    def test_finds_imported_test_files_with_underscore_prefix(self, tmp_path: Path):
        """Test finding imported test files with _ prefix."""
        tests_dir = tmp_path / "tests"
        tests_dir.mkdir()

        imported_file = (
            tests_dir / "_test_task_005_type_validation_validate_type_hints.py"
        )
        imported_file.write_text("class TestValidateTypeHints: pass")

        main_test_file = tests_dir / "test_task_005_type_validation.py"
        main_test_file.write_text(
            """
from tests._test_task_005_type_validation_validate_type_hints import TestValidateTypeHints
"""
        )

        result = _find_imported_test_files(str(main_test_file))

        assert len(result) == 1
        assert str(imported_file) in result

    def test_ignores_non_test_imports(self, tmp_path: Path):
        """Test that non-test imports are ignored."""
        tests_dir = tmp_path / "tests"
        tests_dir.mkdir()

        main_test_file = tests_dir / "test_main.py"
        main_test_file.write_text(
            """
import pytest
from pathlib import Path
from typing import List
from src.service import Service  # Not a test import
from tests._test_split import TestClass  # This should be found
"""
        )

        # Create the imported test file
        imported_file = tests_dir / "_test_split.py"
        imported_file.write_text("class TestClass: pass")

        result = _find_imported_test_files(str(main_test_file))

        # Should only find the tests.* import, not src.* or stdlib imports
        assert len(result) == 1
        assert str(imported_file) in result

    def test_handles_missing_imported_files_gracefully(self, tmp_path: Path):
        """Test that missing imported files don't cause errors."""
        tests_dir = tmp_path / "tests"
        tests_dir.mkdir()

        main_test_file = tests_dir / "test_main.py"
        main_test_file.write_text(
            """
from tests._test_nonexistent import TestClass
"""
        )

        # Don't create the imported file - it doesn't exist
        result = _find_imported_test_files(str(main_test_file))

        # Should return empty list, not crash
        assert result == []

    def test_handles_multiple_imports_from_same_module(self, tmp_path: Path):
        """Test handling multiple imports from the same test module."""
        tests_dir = tmp_path / "tests"
        tests_dir.mkdir()

        imported_file = tests_dir / "_test_split.py"
        imported_file.write_text("class TestClass1: pass\nclass TestClass2: pass")

        main_test_file = tests_dir / "test_main.py"
        main_test_file.write_text(
            """
from tests._test_split import TestClass1, TestClass2
"""
        )

        result = _find_imported_test_files(str(main_test_file))

        # Should only return the file once, not duplicate
        assert len(result) == 1
        assert str(imported_file) in result

    def test_handles_relative_imports(self, tmp_path: Path):
        """Test that relative imports are handled correctly."""
        tests_dir = tmp_path / "tests"
        tests_dir.mkdir()

        imported_file = tests_dir / "_test_split.py"
        imported_file.write_text("class TestClass: pass")

        # Create a subdirectory test file
        subdir = tests_dir / "subdir"
        subdir.mkdir()
        main_test_file = subdir / "test_main.py"
        main_test_file.write_text(
            """
from tests._test_split import TestClass
"""
        )

        result = _find_imported_test_files(str(main_test_file))

        # Should find the imported file even from subdirectory
        assert len(result) == 1
        assert str(imported_file) in result

    def test_handles_syntax_errors_gracefully(self, tmp_path: Path):
        """Test that syntax errors in test file don't crash the function."""
        tests_dir = tmp_path / "tests"
        tests_dir.mkdir()

        main_test_file = tests_dir / "test_main.py"
        main_test_file.write_text(
            """
invalid python syntax !!!
"""
        )

        # Should not crash, return empty list
        result = _find_imported_test_files(str(main_test_file))
        assert isinstance(result, list)

    def test_handles_nonexistent_test_file(self, tmp_path: Path):
        """Test handling of nonexistent test file."""
        nonexistent_file = tmp_path / "nonexistent.py"

        result = _find_imported_test_files(str(nonexistent_file))

        # Should return empty list, not crash
        assert result == []

    def test_real_world_example_task_005(self):
        """Test with the actual task-005 test file structure."""
        # Use the actual test file from the codebase
        test_file = Path("tests/test_task_005_type_validation.py")
        if not test_file.exists():
            pytest.skip("test_task_005_type_validation.py not found")

        result = _find_imported_test_files(str(test_file))

        # Should find all 7 imported test files
        assert len(result) == 7

        # Verify specific files are found
        expected_files = [
            "_test_task_005_type_validation_validate_type_hints.py",
            "_test_task_005_type_validation_extract_annotation.py",
            "_test_task_005_type_validation_compare_types.py",
            "_test_task_005_type_validation_normalize.py",
            "_test_task_005_type_validation_artifact_collector.py",
            "_test_task_005_type_validation_error_messages.py",
            "_test_task_005_type_validation_integration.py",
        ]

        found_names = [Path(f).name for f in result]
        for expected_name in expected_files:
            assert expected_name in found_names
