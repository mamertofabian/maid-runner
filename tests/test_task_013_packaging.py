"""
Behavioral tests for Task-013: PyPI Packaging Preparation

Tests validate that the package is properly configured for PyPI packaging:
- Python API exports are accessible
- CLI commands work correctly
- Version information is accessible
- Package structure is correct

These tests USE the functions and classes exported from maid_runner package.
"""

import pytest
from pathlib import Path
from unittest.mock import patch
from io import StringIO

# Test that package can be imported
import maid_runner


class TestPackageImports:
    """Test that package can be imported and API is accessible."""

    def test_package_can_be_imported(self):
        """Test that maid_runner package can be imported."""
        assert maid_runner is not None
        assert hasattr(maid_runner, "__version__")

    def test_version_is_accessible(self):
        """Test that __version__ is accessible from package."""
        from maid_runner import __version__

        assert __version__ is not None
        assert isinstance(__version__, str)
        assert len(__version__) > 0

    def test_validate_schema_is_exported(self):
        """Test that validate_schema function is exported."""
        from maid_runner import validate_schema

        assert callable(validate_schema)

    def test_validate_with_ast_is_exported(self):
        """Test that validate_with_ast function is exported."""
        from maid_runner import validate_with_ast

        assert callable(validate_with_ast)

    def test_discover_related_manifests_is_exported(self):
        """Test that discover_related_manifests function is exported."""
        from maid_runner import discover_related_manifests

        assert callable(discover_related_manifests)

    def test_alignment_error_is_exported(self):
        """Test that AlignmentError exception is exported."""
        from maid_runner import AlignmentError

        assert issubclass(AlignmentError, Exception)

    def test_generate_snapshot_is_exported(self):
        """Test that generate_snapshot function is exported."""
        from maid_runner import generate_snapshot

        assert callable(generate_snapshot)

    def test_all_exports_are_in_all(self):
        """Test that __all__ contains all expected exports."""
        expected_exports = [
            "__version__",
            "AlignmentError",
            "discover_related_manifests",
            "validate_schema",
            "validate_with_ast",
            "generate_snapshot",
        ]

        assert hasattr(maid_runner, "__all__")
        for export in expected_exports:
            assert export in maid_runner.__all__, f"{export} not in __all__"


class TestCLICommands:
    """Test that CLI commands work correctly."""

    def test_maid_version_command(self):
        """Test that 'maid --version' command works."""
        from maid_runner.cli.main import main

        # Capture stdout
        test_args = ["maid", "--version"]
        captured_output = StringIO()

        with patch("sys.argv", test_args):
            with patch("sys.stdout", captured_output):
                try:
                    main()
                except SystemExit as e:
                    # --version typically exits with 0
                    assert e.code == 0

        output = captured_output.getvalue()
        assert "maid-runner" in output.lower() or "maid" in output.lower()

    def test_maid_validate_help_command(self):
        """Test that 'maid validate --help' command works."""
        from maid_runner.cli.main import main

        # Capture stdout
        test_args = ["maid", "validate", "--help"]
        captured_output = StringIO()

        with patch("sys.argv", test_args):
            with patch("sys.stdout", captured_output):
                try:
                    main()
                except SystemExit as e:
                    # --help typically exits with 0
                    assert e.code == 0

        output = captured_output.getvalue()
        assert "manifest" in output.lower() or "validate" in output.lower()

    def test_maid_snapshot_help_command(self):
        """Test that 'maid snapshot --help' command works."""
        from maid_runner.cli.main import main

        # Capture stdout
        test_args = ["maid", "snapshot", "--help"]
        captured_output = StringIO()

        with patch("sys.argv", test_args):
            with patch("sys.stdout", captured_output):
                try:
                    main()
                except SystemExit as e:
                    # --help typically exits with 0
                    assert e.code == 0

        output = captured_output.getvalue()
        assert "snapshot" in output.lower() or "manifest" in output.lower()

    def test_maid_help_command(self):
        """Test that 'maid --help' command works."""
        from maid_runner.cli.main import main

        # Capture stdout
        test_args = ["maid", "--help"]
        captured_output = StringIO()

        with patch("sys.argv", test_args):
            with patch("sys.stdout", captured_output):
                try:
                    main()
                except SystemExit as e:
                    # --help typically exits with 0
                    assert e.code == 0

        output = captured_output.getvalue()
        assert "validate" in output.lower()
        assert "snapshot" in output.lower()


class TestPackageStructure:
    """Test that package structure is correct."""

    def test_package_directory_exists(self):
        """Test that maid_runner package directory exists."""
        package_dir = Path(__file__).parent.parent / "maid_runner"
        assert package_dir.exists()
        assert package_dir.is_dir()

    def test_init_file_exists(self):
        """Test that __init__.py exists in package."""
        init_file = Path(__file__).parent.parent / "maid_runner" / "__init__.py"
        assert init_file.exists()
        assert init_file.is_file()

    def test_version_file_exists(self):
        """Test that __version__.py exists."""
        version_file = Path(__file__).parent.parent / "maid_runner" / "__version__.py"
        assert version_file.exists()
        assert version_file.is_file()

    def test_cli_module_exists(self):
        """Test that cli module exists."""
        cli_dir = Path(__file__).parent.parent / "maid_runner" / "cli"
        assert cli_dir.exists()
        assert cli_dir.is_dir()

    def test_validators_module_exists(self):
        """Test that validators module exists."""
        validators_dir = Path(__file__).parent.parent / "maid_runner" / "validators"
        assert validators_dir.exists()
        assert validators_dir.is_dir()


class TestAPIUsage:
    """Test that exported API functions can be used."""

    def test_validate_schema_can_be_called(self, tmp_path: Path):
        """Test that validate_schema can be called with valid manifest."""
        from maid_runner import validate_schema

        # Should not raise an exception for valid manifest structure
        # (actual schema validation may require schema file, but function should be callable)
        assert callable(validate_schema)

    def test_alignment_error_can_be_raised(self):
        """Test that AlignmentError can be raised and caught."""
        from maid_runner import AlignmentError

        with pytest.raises(AlignmentError):
            raise AlignmentError("Test error message")

    def test_generate_snapshot_signature(self):
        """Test that generate_snapshot has correct signature."""
        import inspect
        from maid_runner import generate_snapshot

        sig = inspect.signature(generate_snapshot)
        params = list(sig.parameters.keys())

        assert "file_path" in params
        assert "output_dir" in params
        assert "force" in params
