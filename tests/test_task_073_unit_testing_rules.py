"""
Behavioral tests for Task-073: Include unit-testing-rules.md in PyPI package.

Tests validate that:
1. copy_unit_testing_rules() function copies the file to .maid/docs/
2. The function handles missing source gracefully with warning
3. The copied file contains expected content
4. run_init() integrates copy_unit_testing_rules() during initialization

These tests USE the declared artifacts to verify actual behavior.
"""

from pathlib import Path
from unittest.mock import patch

import pytest

from maid_runner.cli.init import copy_unit_testing_rules


class TestCopyUnitTestingRulesBasicBehavior:
    """Test the basic file copying behavior of copy_unit_testing_rules."""

    def test_copies_file_to_maid_docs_directory(self, tmp_path: Path):
        """Test that copy_unit_testing_rules copies the file to .maid/docs/."""
        # Arrange: Create the target .maid/docs directory
        maid_docs_dir = tmp_path / ".maid" / "docs"
        maid_docs_dir.mkdir(parents=True, exist_ok=True)

        # Act: Call the function
        copy_unit_testing_rules(str(tmp_path))

        # Assert: Verify the file was copied
        dest_file = maid_docs_dir / "unit-testing-rules.md"
        assert (
            dest_file.exists()
        ), "unit-testing-rules.md should be copied to .maid/docs/"

    def test_copied_file_is_not_empty(self, tmp_path: Path):
        """Test that the copied unit-testing-rules.md contains content."""
        # Arrange
        maid_docs_dir = tmp_path / ".maid" / "docs"
        maid_docs_dir.mkdir(parents=True, exist_ok=True)

        # Act
        copy_unit_testing_rules(str(tmp_path))

        # Assert
        dest_file = maid_docs_dir / "unit-testing-rules.md"
        content = dest_file.read_text()
        assert len(content) > 0, "Copied file should not be empty"

    def test_copied_file_contains_testing_rules_content(self, tmp_path: Path):
        """Test that the copied file contains expected testing guidelines content."""
        # Arrange
        maid_docs_dir = tmp_path / ".maid" / "docs"
        maid_docs_dir.mkdir(parents=True, exist_ok=True)

        # Act
        copy_unit_testing_rules(str(tmp_path))

        # Assert: Check for key content that should be in unit-testing-rules.md
        dest_file = maid_docs_dir / "unit-testing-rules.md"
        content = dest_file.read_text()

        # Should contain key testing principles
        assert "pytest" in content.lower(), "File should mention pytest"
        assert "test" in content.lower(), "File should mention testing"
        assert (
            "behavior" in content.lower() or "mock" in content.lower()
        ), "File should mention behavior or mocking"


class TestCopyUnitTestingRulesErrorHandling:
    """Test error handling in copy_unit_testing_rules."""

    def test_handles_missing_source_gracefully(self, tmp_path: Path, capsys):
        """Test that function handles missing source file with warning message."""
        # Arrange: Create target directory
        maid_docs_dir = tmp_path / ".maid" / "docs"
        maid_docs_dir.mkdir(parents=True, exist_ok=True)

        # Mock the package path to simulate missing source file
        with patch("maid_runner.cli.init.Path") as mock_path_class:
            # Setup mock to return a path where the file does not exist
            mock_file = mock_path_class.return_value
            mock_parent = mock_file.parent
            mock_parent.parent = mock_parent  # chain .parent.parent
            mock_package_path = mock_parent
            mock_docs_path = (
                mock_package_path.__truediv__.return_value.__truediv__.return_value
            )
            mock_docs_path.exists.return_value = False
            mock_docs_path.__str__ = lambda self: "/fake/path/unit-testing-rules.md"

            # Reset Path for the actual target path construction
            mock_path_class.side_effect = [mock_file, Path(tmp_path)]

            # This test verifies the function doesn't crash when source is missing
            # The actual implementation should print a warning
            try:
                copy_unit_testing_rules(str(tmp_path))
            except Exception as e:
                pytest.fail(
                    f"Function should not raise exception for missing source: {e}"
                )

    def test_prints_success_message_on_copy(self, tmp_path: Path, capsys):
        """Test that function prints success message after copying."""
        # Arrange
        maid_docs_dir = tmp_path / ".maid" / "docs"
        maid_docs_dir.mkdir(parents=True, exist_ok=True)

        # Act
        copy_unit_testing_rules(str(tmp_path))

        # Assert
        captured = capsys.readouterr()
        # Should print a success message (similar to copy_maid_specs)
        assert (
            "unit-testing-rules" in captured.out.lower()
            or "unit_testing_rules" in captured.out.lower()
            or "Copied" in captured.out
        ), "Should print success message after copying"


class TestCopyUnitTestingRulesIdempotency:
    """Test that copy_unit_testing_rules can be run multiple times safely."""

    def test_overwrites_existing_file(self, tmp_path: Path):
        """Test that function overwrites existing unit-testing-rules.md."""
        # Arrange: Create directory and existing file
        maid_docs_dir = tmp_path / ".maid" / "docs"
        maid_docs_dir.mkdir(parents=True, exist_ok=True)
        existing_file = maid_docs_dir / "unit-testing-rules.md"
        existing_file.write_text("Old content that should be overwritten")

        # Act
        copy_unit_testing_rules(str(tmp_path))

        # Assert
        content = existing_file.read_text()
        assert (
            "Old content that should be overwritten" not in content
        ), "Old content should be replaced"
        assert len(content) > 50, "New content should have substantial length"

    def test_multiple_calls_do_not_fail(self, tmp_path: Path):
        """Test that calling the function multiple times works correctly."""
        # Arrange
        maid_docs_dir = tmp_path / ".maid" / "docs"
        maid_docs_dir.mkdir(parents=True, exist_ok=True)

        # Act: Call multiple times
        copy_unit_testing_rules(str(tmp_path))
        copy_unit_testing_rules(str(tmp_path))
        copy_unit_testing_rules(str(tmp_path))

        # Assert: File should still exist and be valid
        dest_file = maid_docs_dir / "unit-testing-rules.md"
        assert dest_file.exists()
        content = dest_file.read_text()
        assert len(content) > 0


class TestCopyUnitTestingRulesParameterValidation:
    """Test parameter handling for copy_unit_testing_rules."""

    def test_accepts_string_target_dir(self, tmp_path: Path):
        """Test that function accepts string path for target_dir."""
        # Arrange
        maid_docs_dir = tmp_path / ".maid" / "docs"
        maid_docs_dir.mkdir(parents=True, exist_ok=True)
        target_str = str(tmp_path)

        # Act & Assert: Should not raise TypeError
        copy_unit_testing_rules(target_str)

        dest_file = maid_docs_dir / "unit-testing-rules.md"
        assert dest_file.exists()

    def test_returns_none(self, tmp_path: Path):
        """Test that function returns None as specified in manifest."""
        # Arrange
        maid_docs_dir = tmp_path / ".maid" / "docs"
        maid_docs_dir.mkdir(parents=True, exist_ok=True)

        # Act
        result = copy_unit_testing_rules(str(tmp_path))

        # Assert: Function should return None
        assert result is None, "Function should return None"


class TestCopyUnitTestingRulesContentValidation:
    """Test that copied content matches the source unit-testing-rules.md."""

    def test_contains_pytest_usage_guidance(self, tmp_path: Path):
        """Test that copied file contains pytest usage guidance."""
        # Arrange
        maid_docs_dir = tmp_path / ".maid" / "docs"
        maid_docs_dir.mkdir(parents=True, exist_ok=True)

        # Act
        copy_unit_testing_rules(str(tmp_path))

        # Assert
        dest_file = maid_docs_dir / "unit-testing-rules.md"
        content = dest_file.read_text()
        assert "pytest" in content.lower(), "Should mention pytest"

    def test_contains_mocking_guidelines(self, tmp_path: Path):
        """Test that copied file contains mocking guidelines."""
        # Arrange
        maid_docs_dir = tmp_path / ".maid" / "docs"
        maid_docs_dir.mkdir(parents=True, exist_ok=True)

        # Act
        copy_unit_testing_rules(str(tmp_path))

        # Assert
        dest_file = maid_docs_dir / "unit-testing-rules.md"
        content = dest_file.read_text()
        assert "mock" in content.lower(), "Should mention mocking"

    def test_contains_behavior_testing_principles(self, tmp_path: Path):
        """Test that copied file contains behavior testing principles."""
        # Arrange
        maid_docs_dir = tmp_path / ".maid" / "docs"
        maid_docs_dir.mkdir(parents=True, exist_ok=True)

        # Act
        copy_unit_testing_rules(str(tmp_path))

        # Assert
        dest_file = maid_docs_dir / "unit-testing-rules.md"
        content = dest_file.read_text()
        assert "behavior" in content.lower(), "Should mention behavior testing"

    def test_contains_assertion_guidelines(self, tmp_path: Path):
        """Test that copied file contains assertion or assert guidelines."""
        # Arrange
        maid_docs_dir = tmp_path / ".maid" / "docs"
        maid_docs_dir.mkdir(parents=True, exist_ok=True)

        # Act
        copy_unit_testing_rules(str(tmp_path))

        # Assert
        dest_file = maid_docs_dir / "unit-testing-rules.md"
        content = dest_file.read_text()
        assert "assert" in content.lower(), "Should mention assertions"


class TestRunInitIntegration:
    """Test that run_init properly integrates copy_unit_testing_rules."""

    def test_run_init_copies_unit_testing_rules(self, tmp_path: Path):
        """Test that run_init creates unit-testing-rules.md alongside maid_specs.md."""
        from maid_runner.cli.init import run_init

        # Act
        run_init(str(tmp_path), force=True)

        # Assert: Both spec files should exist
        maid_docs_dir = tmp_path / ".maid" / "docs"
        maid_specs = maid_docs_dir / "maid_specs.md"
        unit_testing_rules = maid_docs_dir / "unit-testing-rules.md"

        assert maid_specs.exists(), "maid_specs.md should be created by run_init"
        assert (
            unit_testing_rules.exists()
        ), "unit-testing-rules.md should be created by run_init"

    def test_run_init_creates_non_empty_unit_testing_rules(self, tmp_path: Path):
        """Test that run_init creates a non-empty unit-testing-rules.md."""
        from maid_runner.cli.init import run_init

        # Act
        run_init(str(tmp_path), force=True)

        # Assert
        unit_testing_rules = tmp_path / ".maid" / "docs" / "unit-testing-rules.md"
        content = unit_testing_rules.read_text()
        assert (
            len(content) > 100
        ), "unit-testing-rules.md should have substantial content"
        assert "test" in content.lower(), "Content should mention testing"
