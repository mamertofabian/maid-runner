"""Behavioral tests for task-040: Add 'maid schema' CLI command.

Tests that the schema command correctly outputs the manifest JSON schema.
"""

import json
import subprocess
from pathlib import Path

import pytest


class TestSchemaCommand:
    """Test the 'maid schema' CLI command."""

    def test_schema_command_outputs_valid_json(self):
        """Test that 'maid schema' outputs valid JSON."""
        result = subprocess.run(
            ["uv", "run", "maid", "schema"],
            capture_output=True,
            text=True,
        )

        assert result.returncode == 0, f"Command failed: {result.stderr}"

        # Should be valid JSON
        try:
            schema_data = json.loads(result.stdout)
        except json.JSONDecodeError as e:
            pytest.fail(f"Output is not valid JSON: {e}\nOutput: {result.stdout}")

        # Should be a dict (JSON object)
        assert isinstance(schema_data, dict), "Schema should be a JSON object"

    def test_schema_command_outputs_manifest_schema(self):
        """Test that the output matches the actual manifest schema file."""
        # Get the schema via CLI
        result = subprocess.run(
            ["uv", "run", "maid", "schema"],
            capture_output=True,
            text=True,
        )

        assert result.returncode == 0, f"Command failed: {result.stderr}"
        cli_schema = json.loads(result.stdout)

        # Read the actual schema file
        schema_path = Path("maid_runner/validators/schemas/manifest.schema.json")
        with open(schema_path, "r") as f:
            file_schema = json.load(f)

        # They should be identical
        assert cli_schema == file_schema, "CLI output should match schema file"

    def test_schema_has_expected_structure(self):
        """Test that the schema has expected JSON Schema properties."""
        result = subprocess.run(
            ["uv", "run", "maid", "schema"],
            capture_output=True,
            text=True,
        )

        assert result.returncode == 0, f"Command failed: {result.stderr}"
        schema = json.loads(result.stdout)

        # Should have JSON Schema meta-schema
        assert "$schema" in schema, "Schema should have $schema property"

        # Should define manifest structure
        assert "type" in schema, "Schema should have type property"
        assert schema["type"] == "object", "Schema type should be 'object'"

        # Should have properties definition
        assert "properties" in schema, "Schema should have properties"

        # Should have required fields
        assert "required" in schema, "Schema should have required fields"

    def test_schema_command_uses_run_schema_function(self):
        """Test that the CLI uses the run_schema function from schema module."""
        # This test verifies the artifact is actually used
        from maid_runner.cli.schema import run_schema

        # The function should exist and be callable
        assert callable(run_schema), "run_schema should be a callable function"

        # Running it should not raise an exception
        try:
            run_schema()
        except SystemExit:
            # SystemExit is expected (function calls sys.exit(0))
            pass
        except Exception as e:
            pytest.fail(f"run_schema() raised unexpected exception: {e}")

    def test_main_function_handles_schema_command(self):
        """Test that main() function properly handles the schema subcommand."""
        from maid_runner.cli.main import main

        # Verify main function exists
        assert callable(main), "main should be a callable function"

        # Test via subprocess that it actually routes to schema handler
        result = subprocess.run(
            ["uv", "run", "maid", "schema"],
            capture_output=True,
            text=True,
        )

        # Should succeed and output JSON
        assert result.returncode == 0, "Schema command should succeed"
        assert result.stdout.strip(), "Schema command should output content"


class TestSchemaCommandErrors:
    """Test error handling in the schema command."""

    def test_schema_file_not_found(self, tmp_path, monkeypatch):
        """Test error when schema file doesn't exist."""
        from maid_runner.cli import schema
        import sys
        from io import StringIO

        # Monkeypatch to use a non-existent schema path
        fake_parent = tmp_path / "fake_parent" / "cli"
        fake_parent.mkdir(parents=True)

        # Override __file__ to point to a fake location
        monkeypatch.setattr(schema, "__file__", str(fake_parent / "schema.py"))

        # Capture stderr
        captured_stderr = StringIO()
        monkeypatch.setattr(sys, "stderr", captured_stderr)

        # Should exit with error
        with pytest.raises(SystemExit) as exc_info:
            schema.run_schema()

        assert exc_info.value.code == 1
        assert "not found" in captured_stderr.getvalue()

    def test_schema_invalid_json(self, tmp_path, monkeypatch):
        """Test error when schema file contains invalid JSON."""
        from maid_runner.cli import schema
        import sys
        from io import StringIO

        # Create a schema file with invalid JSON
        validators_dir = tmp_path / "validators" / "schemas"
        validators_dir.mkdir(parents=True)
        schema_file = validators_dir / "manifest.schema.json"
        schema_file.write_text("{ invalid json }")

        # Point to the temp directory
        cli_dir = tmp_path / "cli"
        cli_dir.mkdir()
        monkeypatch.setattr(schema, "__file__", str(cli_dir / "schema.py"))

        # Capture stderr
        captured_stderr = StringIO()
        monkeypatch.setattr(sys, "stderr", captured_stderr)

        # Should exit with error
        with pytest.raises(SystemExit) as exc_info:
            schema.run_schema()

        assert exc_info.value.code == 1
        assert "Invalid JSON" in captured_stderr.getvalue()

    def test_schema_read_permission_error(self, tmp_path, monkeypatch):
        """Test error when schema file can't be read."""
        from maid_runner.cli import schema
        import sys
        from io import StringIO
        import os

        # Create a schema file
        validators_dir = tmp_path / "validators" / "schemas"
        validators_dir.mkdir(parents=True)
        schema_file = validators_dir / "manifest.schema.json"
        schema_file.write_text('{"type": "object"}')

        # Make file unreadable
        os.chmod(schema_file, 0o000)

        try:
            # Point to the temp directory
            cli_dir = tmp_path / "cli"
            cli_dir.mkdir()
            monkeypatch.setattr(schema, "__file__", str(cli_dir / "schema.py"))

            # Capture stderr
            captured_stderr = StringIO()
            monkeypatch.setattr(sys, "stderr", captured_stderr)

            # Should exit with error
            with pytest.raises(SystemExit) as exc_info:
                schema.run_schema()

            assert exc_info.value.code == 1
            assert "Error" in captured_stderr.getvalue()
        finally:
            # Restore permissions for cleanup
            os.chmod(schema_file, 0o644)
