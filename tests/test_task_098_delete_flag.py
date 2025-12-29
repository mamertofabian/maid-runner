"""Behavioral tests for task-098: Delete flag support in `maid manifest create` command.

These tests verify the --delete flag functionality for creating deletion manifests:
- run_create_manifest() with delete=True parameter
- _find_active_manifests_to_supersede() helper function

Tests focus on actual behavior (inputs/outputs), not implementation details.
"""

import json

import pytest

from maid_runner.cli.manifest_create import (
    run_create_manifest,
    _find_active_manifests_to_supersede,
)


class TestRunCreateManifestWithDeleteFlag:
    """Tests for run_create_manifest() with delete=True parameter."""

    def test_delete_flag_sets_task_type_refactor(self, tmp_path):
        """When delete=True, manifest should have taskType='refactor'."""
        manifests_dir = tmp_path / "manifests"
        manifests_dir.mkdir()

        # Create an existing file to delete
        target_file = tmp_path / "src" / "service.py"
        target_file.parent.mkdir(parents=True)
        target_file.write_text("def serve(): pass")

        result = run_create_manifest(
            file_path="src/service.py",
            goal="Delete service module",
            artifacts=None,
            task_type=None,
            force_supersede=None,
            test_file=None,
            readonly_files=None,
            output_dir=manifests_dir,
            task_number=None,
            json_output=False,
            quiet=True,
            dry_run=False,
            delete=True,
        )

        assert result == 0

        # Find created manifest
        manifests = list(manifests_dir.glob("task-*.manifest.json"))
        assert len(manifests) == 1

        data = json.loads(manifests[0].read_text())
        assert data["taskType"] == "refactor"

    def test_delete_flag_sets_status_absent(self, tmp_path):
        """When delete=True, expectedArtifacts.status should be 'absent'."""
        manifests_dir = tmp_path / "manifests"
        manifests_dir.mkdir()

        result = run_create_manifest(
            file_path="src/service.py",
            goal="Delete service module",
            artifacts=None,
            task_type=None,
            force_supersede=None,
            test_file=None,
            readonly_files=None,
            output_dir=manifests_dir,
            task_number=None,
            json_output=False,
            quiet=True,
            dry_run=False,
            delete=True,
        )

        assert result == 0

        manifests = list(manifests_dir.glob("task-*.manifest.json"))
        assert len(manifests) == 1

        data = json.loads(manifests[0].read_text())
        assert data["expectedArtifacts"]["status"] == "absent"

    def test_delete_flag_works_for_nonexistent_file(self, tmp_path):
        """When delete=True, can create deletion manifest for file that doesn't exist.

        This is a valid use case: the file might have been previously deleted,
        or only exists in manifest records (e.g., marking legacy tracked files as absent).
        """
        manifests_dir = tmp_path / "manifests"
        manifests_dir.mkdir()

        # Explicitly verify the file does NOT exist
        target_path = tmp_path / "src" / "legacy_service.py"
        assert not target_path.exists()

        result = run_create_manifest(
            file_path="src/legacy_service.py",
            goal="Mark legacy service as deleted",
            artifacts=None,
            task_type=None,
            force_supersede=None,
            test_file=None,
            readonly_files=None,
            output_dir=manifests_dir,
            task_number=None,
            json_output=False,
            quiet=True,
            dry_run=False,
            delete=True,
        )

        assert result == 0

        # Verify manifest was created successfully
        manifests = list(manifests_dir.glob("task-*.manifest.json"))
        assert len(manifests) == 1

        data = json.loads(manifests[0].read_text())
        assert data["taskType"] == "refactor"
        assert data["expectedArtifacts"]["status"] == "absent"
        assert data["expectedArtifacts"]["file"] == "src/legacy_service.py"
        assert "src/legacy_service.py" in data["editableFiles"]

    def test_delete_flag_enforces_empty_artifacts(self, tmp_path, capsys):
        """When delete=True and artifacts provided, should raise ValueError."""
        manifests_dir = tmp_path / "manifests"
        manifests_dir.mkdir()

        with pytest.raises(ValueError, match="artifacts"):
            run_create_manifest(
                file_path="src/service.py",
                goal="Delete service module",
                artifacts=[{"type": "function", "name": "serve"}],
                task_type=None,
                force_supersede=None,
                test_file=None,
                readonly_files=None,
                output_dir=manifests_dir,
                task_number=None,
                json_output=False,
                quiet=True,
                dry_run=False,
                delete=True,
            )

    def test_delete_flag_uses_editable_files(self, tmp_path):
        """When delete=True, file should be in editableFiles (not creatableFiles)."""
        manifests_dir = tmp_path / "manifests"
        manifests_dir.mkdir()

        result = run_create_manifest(
            file_path="src/service.py",
            goal="Delete service module",
            artifacts=None,
            task_type=None,
            force_supersede=None,
            test_file=None,
            readonly_files=None,
            output_dir=manifests_dir,
            task_number=None,
            json_output=False,
            quiet=True,
            dry_run=False,
            delete=True,
        )

        assert result == 0

        manifests = list(manifests_dir.glob("task-*.manifest.json"))
        data = json.loads(manifests[0].read_text())

        assert "src/service.py" in data["editableFiles"]
        assert data["creatableFiles"] == []

    def test_delete_flag_has_empty_contains(self, tmp_path):
        """When delete=True, expectedArtifacts.contains should be []."""
        manifests_dir = tmp_path / "manifests"
        manifests_dir.mkdir()

        result = run_create_manifest(
            file_path="src/service.py",
            goal="Delete service module",
            artifacts=None,
            task_type=None,
            force_supersede=None,
            test_file=None,
            readonly_files=None,
            output_dir=manifests_dir,
            task_number=None,
            json_output=False,
            quiet=True,
            dry_run=False,
            delete=True,
        )

        assert result == 0

        manifests = list(manifests_dir.glob("task-*.manifest.json"))
        data = json.loads(manifests[0].read_text())

        assert data["expectedArtifacts"]["contains"] == []

    def test_delete_flag_auto_supersedes_active_manifests(self, tmp_path):
        """When delete=True, should find and supersede all active manifests for the file."""
        manifests_dir = tmp_path / "manifests"
        manifests_dir.mkdir()

        # Create active snapshot manifest for target file
        snapshot_data = {
            "goal": "Snapshot service",
            "taskType": "snapshot",
            "expectedArtifacts": {
                "file": "src/service.py",
                "contains": [{"type": "function", "name": "serve"}],
            },
        }
        (manifests_dir / "task-010-snapshot-service.manifest.json").write_text(
            json.dumps(snapshot_data)
        )

        # Create active edit manifest for target file
        edit_data = {
            "goal": "Edit service",
            "taskType": "edit",
            "supersedes": ["task-010-snapshot-service.manifest.json"],
            "expectedArtifacts": {
                "file": "src/service.py",
                "contains": [{"type": "function", "name": "serve"}],
            },
        }
        (manifests_dir / "task-020-edit-service.manifest.json").write_text(
            json.dumps(edit_data)
        )

        result = run_create_manifest(
            file_path="src/service.py",
            goal="Delete service module",
            artifacts=None,
            task_type=None,
            force_supersede=None,
            test_file=None,
            readonly_files=None,
            output_dir=manifests_dir,
            task_number=None,
            json_output=False,
            quiet=True,
            dry_run=False,
            delete=True,
        )

        assert result == 0

        # Find created manifest (not the snapshot or edit)
        created_manifests = [
            m
            for m in manifests_dir.glob("task-*.manifest.json")
            if "snapshot-service" not in m.name and "edit-service" not in m.name
        ]
        assert len(created_manifests) == 1

        data = json.loads(created_manifests[0].read_text())

        # Should supersede the active edit manifest (not the already-superseded snapshot)
        assert "task-020-edit-service.manifest.json" in data["supersedes"]


class TestFindActiveManifestsToSupersede:
    """Tests for _find_active_manifests_to_supersede() function."""

    def test_finds_snapshot_manifests_for_file(self, tmp_path):
        """Should find snapshot manifests referencing the file."""
        manifests_dir = tmp_path / "manifests"
        manifests_dir.mkdir()

        # Create a snapshot manifest for our target file
        snapshot_data = {
            "goal": "Snapshot service",
            "taskType": "snapshot",
            "expectedArtifacts": {
                "file": "src/service.py",
                "contains": [{"type": "function", "name": "serve"}],
            },
        }
        (manifests_dir / "task-010-snapshot-service.manifest.json").write_text(
            json.dumps(snapshot_data)
        )

        result = _find_active_manifests_to_supersede("src/service.py", manifests_dir)

        assert "task-010-snapshot-service.manifest.json" in result

    def test_finds_edit_manifests_for_file(self, tmp_path):
        """Should find edit/create manifests referencing the file."""
        manifests_dir = tmp_path / "manifests"
        manifests_dir.mkdir()

        # Create an edit manifest for our target file
        edit_data = {
            "goal": "Edit service",
            "taskType": "edit",
            "editableFiles": ["src/service.py"],
            "expectedArtifacts": {
                "file": "src/service.py",
                "contains": [{"type": "function", "name": "serve"}],
            },
        }
        (manifests_dir / "task-015-edit-service.manifest.json").write_text(
            json.dumps(edit_data)
        )

        # Create a create manifest for our target file
        create_data = {
            "goal": "Create service",
            "taskType": "create",
            "creatableFiles": ["src/service.py"],
            "expectedArtifacts": {
                "file": "src/service.py",
                "contains": [{"type": "class", "name": "Service"}],
            },
        }
        (manifests_dir / "task-016-create-service.manifest.json").write_text(
            json.dumps(create_data)
        )

        result = _find_active_manifests_to_supersede("src/service.py", manifests_dir)

        assert "task-015-edit-service.manifest.json" in result
        assert "task-016-create-service.manifest.json" in result

    def test_excludes_already_superseded_manifests(self, tmp_path):
        """Should not include manifests that are already superseded."""
        manifests_dir = tmp_path / "manifests"
        manifests_dir.mkdir()

        # Create an old snapshot (will be superseded)
        old_snapshot = {
            "goal": "Old snapshot",
            "taskType": "snapshot",
            "expectedArtifacts": {"file": "src/service.py", "contains": []},
        }
        (manifests_dir / "task-010-old-snapshot.manifest.json").write_text(
            json.dumps(old_snapshot)
        )

        # Create a manifest that supersedes the old snapshot
        superseding_manifest = {
            "goal": "Edit service",
            "taskType": "edit",
            "supersedes": ["task-010-old-snapshot.manifest.json"],
            "expectedArtifacts": {"file": "src/service.py", "contains": []},
        }
        (manifests_dir / "task-015-edit-service.manifest.json").write_text(
            json.dumps(superseding_manifest)
        )

        result = _find_active_manifests_to_supersede("src/service.py", manifests_dir)

        # Should include the edit manifest but not the superseded snapshot
        assert "task-015-edit-service.manifest.json" in result
        assert "task-010-old-snapshot.manifest.json" not in result

    def test_returns_empty_when_no_manifests(self, tmp_path):
        """Returns empty list when no manifests reference the file."""
        manifests_dir = tmp_path / "manifests"
        manifests_dir.mkdir()

        # Create a manifest for a different file
        other_data = {
            "goal": "Edit other",
            "taskType": "edit",
            "expectedArtifacts": {"file": "src/other.py", "contains": []},
        }
        (manifests_dir / "task-010-edit-other.manifest.json").write_text(
            json.dumps(other_data)
        )

        result = _find_active_manifests_to_supersede("src/service.py", manifests_dir)

        assert result == []

    def test_handles_missing_manifest_directory(self, tmp_path):
        """Returns empty list when manifest directory doesn't exist."""
        manifests_dir = tmp_path / "manifests"
        # Directory not created

        result = _find_active_manifests_to_supersede("src/service.py", manifests_dir)

        assert result == []


class TestDeleteFlagWithJsonOutput:
    """Tests for JSON output mode with delete flag."""

    def test_delete_json_output_includes_status(self, tmp_path, capsys):
        """JSON output should show status: 'absent' in manifest."""
        manifests_dir = tmp_path / "manifests"
        manifests_dir.mkdir()

        result = run_create_manifest(
            file_path="src/service.py",
            goal="Delete service module",
            artifacts=None,
            task_type=None,
            force_supersede=None,
            test_file=None,
            readonly_files=None,
            output_dir=manifests_dir,
            task_number=None,
            json_output=True,
            quiet=True,
            dry_run=False,
            delete=True,
        )

        assert result == 0

        captured = capsys.readouterr()
        output = json.loads(captured.out)

        assert output["success"] is True
        assert output["manifest"]["expectedArtifacts"]["status"] == "absent"


class TestDeleteFlagWithDryRun:
    """Tests for dry-run mode with delete flag."""

    def test_delete_dry_run_shows_absent_status(self, tmp_path, capsys):
        """Dry run output should preview the deletion manifest correctly."""
        manifests_dir = tmp_path / "manifests"
        manifests_dir.mkdir()

        result = run_create_manifest(
            file_path="src/service.py",
            goal="Delete service module",
            artifacts=None,
            task_type=None,
            force_supersede=None,
            test_file=None,
            readonly_files=None,
            output_dir=manifests_dir,
            task_number=None,
            json_output=True,
            quiet=False,
            dry_run=True,
            delete=True,
        )

        assert result == 0

        captured = capsys.readouterr()
        output = json.loads(captured.out)

        assert output["dry_run"] is True
        assert output["manifest"]["taskType"] == "refactor"
        assert output["manifest"]["expectedArtifacts"]["status"] == "absent"
        assert output["manifest"]["expectedArtifacts"]["contains"] == []

        # No manifest file should be created
        manifests = list(manifests_dir.glob("task-*.manifest.json"))
        assert len(manifests) == 0


class TestDeleteFlagErrorHandling:
    """Tests for error handling with delete flag."""

    def test_delete_with_artifacts_json_output_returns_error(self, tmp_path, capsys):
        """When json_output=True and artifacts provided with delete, returns JSON error."""
        manifests_dir = tmp_path / "manifests"
        manifests_dir.mkdir()

        result = run_create_manifest(
            file_path="src/service.py",
            goal="Delete service module",
            artifacts=[{"type": "function", "name": "serve"}],
            task_type=None,
            force_supersede=None,
            test_file=None,
            readonly_files=None,
            output_dir=manifests_dir,
            task_number=None,
            json_output=True,
            quiet=True,
            dry_run=False,
            delete=True,
        )

        assert result == 1  # Non-zero exit code

        captured = capsys.readouterr()
        output = json.loads(captured.out)

        assert output["success"] is False
        assert "error" in output
        assert "artifacts" in output["error"].lower()


class TestDeleteFlagWithExistingManifests:
    """Integration tests for delete flag with existing manifest chains."""

    def test_delete_creates_proper_manifest_chain(self, tmp_path):
        """Delete manifest properly supersedes and creates valid chain."""
        manifests_dir = tmp_path / "manifests"
        manifests_dir.mkdir()

        # Create original create manifest
        create_data = {
            "goal": "Create service module",
            "taskType": "create",
            "creatableFiles": ["src/service.py"],
            "expectedArtifacts": {
                "file": "src/service.py",
                "contains": [{"type": "function", "name": "serve"}],
            },
        }
        (manifests_dir / "task-001-create-service.manifest.json").write_text(
            json.dumps(create_data)
        )

        # Create edit manifest
        edit_data = {
            "goal": "Add logging to service",
            "taskType": "edit",
            "editableFiles": ["src/service.py"],
            "expectedArtifacts": {
                "file": "src/service.py",
                "contains": [
                    {"type": "function", "name": "serve"},
                    {"type": "function", "name": "log"},
                ],
            },
        }
        (manifests_dir / "task-002-add-logging.manifest.json").write_text(
            json.dumps(edit_data)
        )

        # Now delete the file
        result = run_create_manifest(
            file_path="src/service.py",
            goal="Remove deprecated service module",
            artifacts=None,
            task_type=None,
            force_supersede=None,
            test_file=None,
            readonly_files=None,
            output_dir=manifests_dir,
            task_number=None,
            json_output=False,
            quiet=True,
            dry_run=False,
            delete=True,
        )

        assert result == 0

        # Find the delete manifest
        delete_manifests = [
            m
            for m in manifests_dir.glob("task-*.manifest.json")
            if "create-service" not in m.name and "add-logging" not in m.name
        ]
        assert len(delete_manifests) == 1

        data = json.loads(delete_manifests[0].read_text())

        # Verify deletion manifest structure
        assert data["taskType"] == "refactor"
        assert data["expectedArtifacts"]["status"] == "absent"
        assert data["expectedArtifacts"]["contains"] == []
        assert "src/service.py" in data["editableFiles"]

        # Should supersede both active manifests that reference this file
        assert "task-001-create-service.manifest.json" in data["supersedes"]
        assert "task-002-add-logging.manifest.json" in data["supersedes"]

    def test_delete_flag_default_false(self, tmp_path):
        """By default, delete flag should be False (normal manifest creation)."""
        manifests_dir = tmp_path / "manifests"
        manifests_dir.mkdir()

        # Create without delete flag - using positional args that existed before
        result = run_create_manifest(
            file_path="src/service.py",
            goal="Add feature",
            artifacts=[{"type": "function", "name": "new_func"}],
            task_type="create",
            force_supersede=None,
            test_file=None,
            readonly_files=None,
            output_dir=manifests_dir,
            task_number=None,
            json_output=False,
            quiet=True,
            dry_run=False,
            delete=False,
        )

        assert result == 0

        manifests = list(manifests_dir.glob("task-*.manifest.json"))
        data = json.loads(manifests[0].read_text())

        # Should NOT have status: absent
        assert "status" not in data["expectedArtifacts"]
        # Should have artifacts in contains
        assert len(data["expectedArtifacts"]["contains"]) == 1
