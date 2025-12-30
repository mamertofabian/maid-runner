"""
Behavioral tests for Task-085: Fix CLI validation for absent status files.

Tests verify that the CLI validation flow properly handles manifests with
status: "absent" and doesn't error out when the target file doesn't exist.
"""

import json
import subprocess


class TestCLIAbsentStatusValidation:
    """Test that CLI validation handles status: 'absent' correctly."""

    def test_cli_accepts_absent_file_that_doesnt_exist(self, tmp_path):
        """Test that CLI validation passes for absent files that don't exist."""
        # Create manifests directory and superseded manifest
        manifests_dir = tmp_path / "manifests"
        manifests_dir.mkdir()
        superseded_manifest = manifests_dir / "task-001.manifest.json"
        superseded_manifest.write_text(
            json.dumps(
                {
                    "goal": "Original file",
                    "taskType": "create",
                    "creatableFiles": ["deleted_file.py"],
                    "readonlyFiles": [],
                    "expectedArtifacts": {
                        "file": "deleted_file.py",
                        "contains": [{"type": "function", "name": "dummy"}],
                    },
                    "validationCommand": ["echo", "test"],
                },
                indent=2,
            )
        )

        # Create a manifest with status: "absent"
        manifest_path = manifests_dir / "test-delete.manifest.json"
        manifest_data = {
            "goal": "Delete obsolete module",
            "taskType": "refactor",
            "supersedes": ["task-001.manifest.json"],
            "editableFiles": ["deleted_file.py"],
            "readonlyFiles": [],
            "expectedArtifacts": {
                "file": "deleted_file.py",
                "status": "absent",
                "contains": [],
            },
            "validationCommand": ["echo", "test"],
        }

        manifest_path.write_text(json.dumps(manifest_data, indent=2))

        # Run validation - should pass because file is marked absent
        result = subprocess.run(
            ["uv", "run", "maid", "validate", str(manifest_path)],
            cwd=tmp_path.parent.parent.parent,
            capture_output=True,
            text=True,
        )

        # Should succeed (exit code 0)
        assert (
            result.returncode == 0
        ), f"Validation failed:\n{result.stderr}\n{result.stdout}"
        assert "PASSED" in result.stdout or "✓" in result.stdout

    def test_cli_rejects_absent_file_that_still_exists(self, tmp_path):
        """Test that CLI validation fails if file marked absent still exists."""
        # Create manifests directory and superseded manifest
        manifests_dir = tmp_path / "manifests"
        manifests_dir.mkdir()

        # Create a file that should be deleted
        existing_file = tmp_path / "should_be_deleted.py"
        existing_file.write_text("# This file should not exist\n")

        superseded_manifest = manifests_dir / "task-001.manifest.json"
        superseded_manifest.write_text(
            json.dumps(
                {
                    "goal": "Original file",
                    "taskType": "create",
                    "creatableFiles": [str(existing_file)],
                    "readonlyFiles": [],
                    "expectedArtifacts": {
                        "file": str(existing_file),
                        "contains": [{"type": "function", "name": "dummy"}],
                    },
                    "validationCommand": ["echo", "test"],
                },
                indent=2,
            )
        )

        # Create manifest marking it as absent
        manifest_path = manifests_dir / "test-delete.manifest.json"
        manifest_data = {
            "goal": "Delete file",
            "taskType": "refactor",
            "supersedes": ["task-001.manifest.json"],
            "editableFiles": [str(existing_file)],
            "readonlyFiles": [],
            "expectedArtifacts": {
                "file": str(existing_file),
                "status": "absent",
                "contains": [],
            },
            "validationCommand": ["echo", "test"],
        }

        manifest_path.write_text(json.dumps(manifest_data, indent=2))

        # Run validation - should fail because file still exists
        result = subprocess.run(
            ["uv", "run", "maid", "validate", str(manifest_path)],
            cwd=tmp_path.parent.parent.parent,
            capture_output=True,
            text=True,
        )

        # Should fail (non-zero exit code)
        assert result.returncode != 0, "Validation should have failed"
        assert "absent" in result.stderr.lower() or "absent" in result.stdout.lower()

    def test_cli_normal_validation_for_present_files(self, tmp_path):
        """Test that normal validation still works for present files."""
        # Create a Python file
        test_file = tmp_path / "normal_file.py"
        test_file.write_text("def hello(): pass\n")

        # Create manifest without status field (defaults to present)
        manifest_path = tmp_path / "test-create.manifest.json"
        manifest_data = {
            "goal": "Create file",
            "creatableFiles": [str(test_file)],
            "readonlyFiles": [],
            "expectedArtifacts": {
                "file": str(test_file),
                "contains": [{"type": "function", "name": "hello"}],
            },
            "validationCommand": ["echo", "test"],
        }

        manifest_path.write_text(json.dumps(manifest_data, indent=2))

        # Run validation - should pass
        result = subprocess.run(
            ["uv", "run", "maid", "validate", str(manifest_path)],
            cwd=tmp_path.parent.parent.parent,
            capture_output=True,
            text=True,
        )

        # Should succeed
        assert (
            result.returncode == 0
        ), f"Validation failed:\n{result.stderr}\n{result.stdout}"

    def test_cli_absent_file_skips_implementation_validation(self, tmp_path):
        """Test that absent files skip artifact validation."""
        # Create manifests directory and superseded manifest
        manifests_dir = tmp_path / "manifests"
        manifests_dir.mkdir()

        # Don't create the file (it should be absent)
        deleted_file = tmp_path / "deleted.py"

        superseded_manifest = manifests_dir / "task-001.manifest.json"
        superseded_manifest.write_text(
            json.dumps(
                {
                    "goal": "Original file",
                    "taskType": "create",
                    "creatableFiles": [str(deleted_file)],
                    "readonlyFiles": [],
                    "expectedArtifacts": {
                        "file": str(deleted_file),
                        "contains": [{"type": "function", "name": "dummy"}],
                    },
                    "validationCommand": ["echo", "test"],
                },
                indent=2,
            )
        )

        # Create manifest with status: "absent"
        manifest_path = manifests_dir / "test-delete.manifest.json"
        manifest_data = {
            "goal": "Delete file",
            "taskType": "refactor",
            "supersedes": ["task-001.manifest.json"],
            "editableFiles": [str(deleted_file)],
            "readonlyFiles": [],
            "expectedArtifacts": {
                "file": str(deleted_file),
                "status": "absent",
                "contains": [],  # Empty because file is deleted
            },
            "validationCommand": ["echo", "test"],
        }

        manifest_path.write_text(json.dumps(manifest_data, indent=2))

        # Run validation - should pass without trying to parse the file
        result = subprocess.run(
            ["uv", "run", "maid", "validate", str(manifest_path)],
            cwd=tmp_path.parent.parent.parent,
            capture_output=True,
            text=True,
        )

        # Should succeed - no artifact validation attempted
        assert (
            result.returncode == 0
        ), f"Validation failed:\n{result.stderr}\n{result.stdout}"
        # Should not contain "Target file not found" error
        assert "Target file not found" not in result.stderr
        assert "Target file not found" not in result.stdout


class TestCLIErrorMessages:
    """Test that error messages are clear for absent status validation."""

    def test_helpful_error_when_absent_file_exists(self, tmp_path):
        """Test that error message is clear when deleted file still exists."""
        # Create manifests directory and superseded manifest
        manifests_dir = tmp_path / "manifests"
        manifests_dir.mkdir()

        # Create file that should be deleted
        leftover_file = tmp_path / "should_be_gone.py"
        leftover_file.write_text("# Forgot to delete this\n")

        superseded_manifest = manifests_dir / "task-001.manifest.json"
        superseded_manifest.write_text(
            json.dumps(
                {
                    "goal": "Original file",
                    "taskType": "create",
                    "creatableFiles": [str(leftover_file)],
                    "readonlyFiles": [],
                    "expectedArtifacts": {
                        "file": str(leftover_file),
                        "contains": [{"type": "function", "name": "dummy"}],
                    },
                    "validationCommand": ["echo", "test"],
                },
                indent=2,
            )
        )

        # Create manifest
        manifest_path = manifests_dir / "test-delete.manifest.json"
        manifest_data = {
            "goal": "Delete file",
            "taskType": "refactor",
            "supersedes": ["task-001.manifest.json"],
            "editableFiles": [str(leftover_file)],
            "readonlyFiles": [],
            "expectedArtifacts": {
                "file": str(leftover_file),
                "status": "absent",
                "contains": [],
            },
            "validationCommand": ["echo", "test"],
        }

        manifest_path.write_text(json.dumps(manifest_data, indent=2))

        # Run validation
        result = subprocess.run(
            ["uv", "run", "maid", "validate", str(manifest_path)],
            cwd=tmp_path.parent.parent.parent,
            capture_output=True,
            text=True,
        )

        # Should fail with helpful error
        assert result.returncode != 0
        error_output = result.stderr + result.stdout
        assert "absent" in error_output.lower()
        # Should mention the file that still exists
        assert str(leftover_file) in error_output or leftover_file.name in error_output
