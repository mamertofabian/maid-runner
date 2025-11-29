"""
Behavioral tests for task-046: Implement CLI integration for maid snapshot-system.

Tests verify that:
1. run_snapshot_system() orchestrates all components correctly
2. Calls discover_active_manifests, aggregate functions, create_system_manifest
3. Writes output to specified file
4. Handles edge cases and errors gracefully
5. CLI command works end-to-end
"""

import json
import pytest
from pathlib import Path
from unittest.mock import patch
from io import StringIO

from maid_runner.cli.snapshot_system import run_snapshot_system


@pytest.fixture
def temp_manifest_dir(tmp_path):
    """Create a temporary directory with test manifests."""
    manifest_dir = tmp_path / "manifests"
    manifest_dir.mkdir()
    return manifest_dir


@pytest.fixture
def temp_output_file(tmp_path):
    """Create a temporary output file path."""
    return tmp_path / "system.manifest.json"


@pytest.fixture
def create_test_manifest(temp_manifest_dir):
    """Factory fixture for creating test manifests."""

    def _create_manifest(filename: str, file_path: str = "test.py") -> Path:
        manifest_path = temp_manifest_dir / filename
        manifest = {
            "version": "1",
            "goal": f"Test manifest for {filename}",
            "taskType": "edit",
            "readonlyFiles": [],
            "expectedArtifacts": {
                "file": file_path,
                "contains": [
                    {"type": "function", "name": f"func_{filename.split('.')[0]}"}
                ],
            },
            "validationCommand": ["pytest", f"tests/test_{filename.split('.')[0]}.py"],
        }
        with open(manifest_path, "w") as f:
            json.dump(manifest, f, indent=2)
        return manifest_path

    return _create_manifest


class TestRunSnapshotSystem:
    """Test suite for run_snapshot_system() orchestration function."""

    def test_function_exists(self):
        """Verify run_snapshot_system function exists."""
        assert callable(run_snapshot_system)

    def test_creates_output_file(
        self, temp_manifest_dir, temp_output_file, create_test_manifest
    ):
        """Verify function creates output file."""
        # Create test manifests
        create_test_manifest("task-001.manifest.json", "file1.py")
        create_test_manifest("task-002.manifest.json", "file2.py")

        # Run snapshot system
        run_snapshot_system(str(temp_output_file), str(temp_manifest_dir), quiet=True)

        # Verify output file exists
        assert temp_output_file.exists()

    def test_output_is_valid_json(
        self, temp_manifest_dir, temp_output_file, create_test_manifest
    ):
        """Verify output file contains valid JSON."""
        create_test_manifest("task-001.manifest.json")

        run_snapshot_system(str(temp_output_file), str(temp_manifest_dir), quiet=True)

        # Should be valid JSON
        with open(temp_output_file) as f:
            data = json.load(f)

        assert isinstance(data, dict)

    def test_output_has_system_snapshot_task_type(
        self, temp_manifest_dir, temp_output_file, create_test_manifest
    ):
        """Verify output manifest has correct taskType."""
        create_test_manifest("task-001.manifest.json")

        run_snapshot_system(str(temp_output_file), str(temp_manifest_dir), quiet=True)

        with open(temp_output_file) as f:
            data = json.load(f)

        assert data["taskType"] == "system-snapshot"

    def test_output_has_systemArtifacts(
        self, temp_manifest_dir, temp_output_file, create_test_manifest
    ):
        """Verify output manifest has systemArtifacts field."""
        create_test_manifest("task-001.manifest.json", "file1.py")
        create_test_manifest("task-002.manifest.json", "file2.py")

        run_snapshot_system(str(temp_output_file), str(temp_manifest_dir), quiet=True)

        with open(temp_output_file) as f:
            data = json.load(f)

        assert "systemArtifacts" in data
        assert isinstance(data["systemArtifacts"], list)
        assert len(data["systemArtifacts"]) == 2  # Two files

    def test_output_has_validationCommands(
        self, temp_manifest_dir, temp_output_file, create_test_manifest
    ):
        """Verify output manifest has validationCommands field."""
        create_test_manifest("task-001.manifest.json")

        run_snapshot_system(str(temp_output_file), str(temp_manifest_dir), quiet=True)

        with open(temp_output_file) as f:
            data = json.load(f)

        assert "validationCommands" in data
        assert isinstance(data["validationCommands"], list)

    def test_aggregates_artifacts_from_multiple_manifests(
        self, temp_manifest_dir, temp_output_file, create_test_manifest
    ):
        """Verify artifacts from multiple manifests are aggregated."""
        create_test_manifest("task-001.manifest.json", "file1.py")
        create_test_manifest("task-002.manifest.json", "file2.py")
        create_test_manifest("task-003.manifest.json", "file3.py")

        run_snapshot_system(str(temp_output_file), str(temp_manifest_dir), quiet=True)

        with open(temp_output_file) as f:
            data = json.load(f)

        # Should have 3 file blocks
        assert len(data["systemArtifacts"]) == 3

        files = {block["file"] for block in data["systemArtifacts"]}
        assert files == {"file1.py", "file2.py", "file3.py"}

    def test_aggregates_validation_commands(
        self, temp_manifest_dir, temp_output_file, create_test_manifest
    ):
        """Verify validation commands are aggregated and deduplicated."""
        create_test_manifest("task-001.manifest.json")
        create_test_manifest("task-002.manifest.json")

        run_snapshot_system(str(temp_output_file), str(temp_manifest_dir), quiet=True)

        with open(temp_output_file) as f:
            data = json.load(f)

        # Should have validation commands
        assert len(data["validationCommands"]) >= 1

    def test_handles_empty_manifest_directory(
        self, temp_manifest_dir, temp_output_file
    ):
        """Verify handling of empty manifest directory."""
        run_snapshot_system(str(temp_output_file), str(temp_manifest_dir), quiet=True)

        # Should still create output file
        assert temp_output_file.exists()

        with open(temp_output_file) as f:
            data = json.load(f)

        # Should have empty systemArtifacts
        assert data["systemArtifacts"] == []

    def test_handles_nonexistent_manifest_directory(self, temp_output_file):
        """Verify handling of nonexistent manifest directory."""
        nonexistent_dir = "/nonexistent/path/to/manifests"

        # Should handle gracefully (create empty snapshot or raise error)
        try:
            run_snapshot_system(str(temp_output_file), nonexistent_dir, quiet=True)
            # If it doesn't raise, should create valid output
            assert temp_output_file.exists()
        except (FileNotFoundError, OSError):
            # Acceptable to raise if directory doesn't exist
            pass

    def test_quiet_mode_suppresses_output(
        self, temp_manifest_dir, temp_output_file, create_test_manifest, capsys
    ):
        """Verify quiet mode suppresses console output."""
        create_test_manifest("task-001.manifest.json")

        run_snapshot_system(str(temp_output_file), str(temp_manifest_dir), quiet=True)

        captured = capsys.readouterr()
        # In quiet mode, should have minimal or no output
        # (Implementation may vary, but generally should be minimal)
        assert len(captured.out) < 200  # Reasonable threshold

    def test_normal_mode_shows_output(
        self, temp_manifest_dir, temp_output_file, create_test_manifest, capsys
    ):
        """Verify normal mode shows progress output."""
        create_test_manifest("task-001.manifest.json")
        create_test_manifest("task-002.manifest.json")

        run_snapshot_system(str(temp_output_file), str(temp_manifest_dir), quiet=False)

        captured = capsys.readouterr()
        # Should have some informative output
        assert len(captured.out) > 0

    def test_output_validates_against_schema(
        self, temp_manifest_dir, temp_output_file, create_test_manifest
    ):
        """Verify generated manifest validates against manifest schema."""
        from jsonschema import validate

        create_test_manifest("task-001.manifest.json")

        run_snapshot_system(str(temp_output_file), str(temp_manifest_dir), quiet=True)

        # Load generated manifest
        with open(temp_output_file) as f:
            manifest_data = json.load(f)

        # Load schema
        schema_path = Path("maid_runner/validators/schemas/manifest.schema.json")
        with open(schema_path) as f:
            schema = json.load(f)

        # Should validate without errors
        validate(instance=manifest_data, schema=schema)

    def test_overwrites_existing_output_file(
        self, temp_manifest_dir, temp_output_file, create_test_manifest
    ):
        """Verify function overwrites existing output file."""
        # Create initial output
        with open(temp_output_file, "w") as f:
            json.dump({"old": "data"}, f)

        create_test_manifest("task-001.manifest.json")

        run_snapshot_system(str(temp_output_file), str(temp_manifest_dir), quiet=True)

        # Should have new content
        with open(temp_output_file) as f:
            data = json.load(f)

        assert "old" not in data
        assert "systemArtifacts" in data

    def test_creates_output_directory_if_needed(
        self, temp_manifest_dir, create_test_manifest, tmp_path
    ):
        """Verify function creates output directory if it doesn't exist."""
        output_file = tmp_path / "new_dir" / "system.manifest.json"
        create_test_manifest("task-001.manifest.json")

        run_snapshot_system(str(output_file), str(temp_manifest_dir), quiet=True)

        # Directory and file should be created
        assert output_file.parent.exists()
        assert output_file.exists()


class TestCLIIntegration:
    """Integration tests for CLI command."""

    def test_cli_command_accessible(self):
        """Verify snapshot-system command is accessible from CLI."""
        from maid_runner.cli.main import main

        # Capture stdout
        test_args = ["maid", "snapshot-system", "--help"]
        captured_output = StringIO()

        with patch("sys.argv", test_args):
            with patch("sys.stdout", captured_output):
                try:
                    main()
                except SystemExit as e:
                    # --help typically exits with 0
                    assert e.code == 0

        output = captured_output.getvalue()
        # Help text should mention snapshot-system
        assert "snapshot-system" in output.lower() or "system" in output.lower()

    def test_cli_end_to_end(self, temp_manifest_dir, tmp_path, create_test_manifest):
        """Verify CLI command works end-to-end."""
        from maid_runner.cli.main import main

        # Create test manifests
        create_test_manifest("task-001.manifest.json", "file1.py")
        create_test_manifest("task-002.manifest.json", "file2.py")

        output_file = tmp_path / "system.manifest.json"

        test_args = [
            "maid",
            "snapshot-system",
            "--output",
            str(output_file),
            "--manifest-dir",
            str(temp_manifest_dir),
            "--quiet",
        ]

        with patch("sys.argv", test_args):
            main()  # Should execute without raising

        # Output file should exist and be valid
        assert output_file.exists()

        with open(output_file) as f:
            data = json.load(f)

        assert data["taskType"] == "system-snapshot"
        assert len(data["systemArtifacts"]) == 2


class TestIntegrationWithRealManifests:
    """Integration tests using real manifests from the project."""

    def test_generates_system_snapshot_from_real_manifests(self, tmp_path):
        """Verify generation works with actual project manifests."""
        manifest_dir = Path("manifests")
        if not manifest_dir.exists():
            pytest.skip("Manifests directory not found")

        output_file = tmp_path / "system.manifest.json"

        run_snapshot_system(str(output_file), str(manifest_dir), quiet=True)

        # Verify output
        assert output_file.exists()

        with open(output_file) as f:
            data = json.load(f)

        # Should have system structure
        assert data["taskType"] == "system-snapshot"
        assert "systemArtifacts" in data
        assert "validationCommands" in data

        # Should have multiple files
        assert len(data["systemArtifacts"]) > 0

    def test_real_snapshot_validates_against_schema(self, tmp_path):
        """Verify real snapshot validates against manifest schema."""
        from jsonschema import validate

        manifest_dir = Path("manifests")
        if not manifest_dir.exists():
            pytest.skip("Manifests directory not found")

        output_file = tmp_path / "system.manifest.json"

        run_snapshot_system(str(output_file), str(manifest_dir), quiet=True)

        # Load generated manifest
        with open(output_file) as f:
            manifest_data = json.load(f)

        # Load schema
        schema_path = Path("maid_runner/validators/schemas/manifest.schema.json")
        with open(schema_path) as f:
            schema = json.load(f)

        # Should validate without errors
        validate(instance=manifest_data, schema=schema)
