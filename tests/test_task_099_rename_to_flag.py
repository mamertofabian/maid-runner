"""Behavioral tests for task-099: Rename-to flag support in `maid manifest create` command.

These tests verify the --rename-to flag functionality for creating rename/move manifests:
- run_create_manifest() with rename_to parameter
- _get_artifacts_from_manifests() helper function

Tests focus on actual behavior (inputs/outputs), not implementation details.
"""

import json

from maid_runner.cli.manifest_create import (
    run_create_manifest,
    _get_artifacts_from_manifests,
)


class TestRunCreateManifestWithRenameTo:
    """Tests for run_create_manifest() with rename_to parameter."""

    def test_rename_to_sets_task_type_refactor(self, tmp_path):
        """When rename_to is provided, manifest should have taskType='refactor'."""
        manifests_dir = tmp_path / "manifests"
        manifests_dir.mkdir()

        result = run_create_manifest(
            file_path="src/old_service.py",
            goal="Rename service module",
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
            delete=False,
            rename_to="src/new_service.py",
        )

        assert result == 0

        # Find created manifest
        manifests = list(manifests_dir.glob("task-*.manifest.json"))
        assert len(manifests) == 1

        data = json.loads(manifests[0].read_text())
        assert data["taskType"] == "refactor"

    def test_rename_to_uses_creatable_files_for_new_path(self, tmp_path):
        """New file path (rename_to) should be in creatableFiles."""
        manifests_dir = tmp_path / "manifests"
        manifests_dir.mkdir()

        result = run_create_manifest(
            file_path="src/old_service.py",
            goal="Rename service module",
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
            delete=False,
            rename_to="src/new_service.py",
        )

        assert result == 0

        manifests = list(manifests_dir.glob("task-*.manifest.json"))
        data = json.loads(manifests[0].read_text())

        # New file path should be in creatableFiles
        assert "src/new_service.py" in data["creatableFiles"]

    def test_rename_to_old_file_not_in_file_lists(self, tmp_path):
        """Old file path should NOT be in creatableFiles or editableFiles."""
        manifests_dir = tmp_path / "manifests"
        manifests_dir.mkdir()

        result = run_create_manifest(
            file_path="src/old_service.py",
            goal="Rename service module",
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
            delete=False,
            rename_to="src/new_service.py",
        )

        assert result == 0

        manifests = list(manifests_dir.glob("task-*.manifest.json"))
        data = json.loads(manifests[0].read_text())

        # Old file should NOT be in creatableFiles or editableFiles
        assert "src/old_service.py" not in data["creatableFiles"]
        assert "src/old_service.py" not in data["editableFiles"]

    def test_rename_to_auto_supersedes_active_manifests(self, tmp_path):
        """Should supersede all active manifests for the OLD file."""
        manifests_dir = tmp_path / "manifests"
        manifests_dir.mkdir()

        # Create active snapshot manifest for OLD file path
        snapshot_data = {
            "goal": "Snapshot old service",
            "taskType": "snapshot",
            "expectedArtifacts": {
                "file": "src/old_service.py",
                "contains": [{"type": "function", "name": "serve"}],
            },
        }
        (manifests_dir / "task-010-snapshot-service.manifest.json").write_text(
            json.dumps(snapshot_data)
        )

        # Create active edit manifest for OLD file path
        edit_data = {
            "goal": "Edit old service",
            "taskType": "edit",
            "supersedes": ["task-010-snapshot-service.manifest.json"],
            "expectedArtifacts": {
                "file": "src/old_service.py",
                "contains": [
                    {"type": "function", "name": "serve"},
                    {"type": "function", "name": "log"},
                ],
            },
        }
        (manifests_dir / "task-020-edit-service.manifest.json").write_text(
            json.dumps(edit_data)
        )

        result = run_create_manifest(
            file_path="src/old_service.py",
            goal="Rename service module",
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
            delete=False,
            rename_to="src/new_service.py",
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

    def test_rename_to_copies_artifacts_from_old_manifests(self, tmp_path):
        """When no --artifacts provided, should copy from existing manifests."""
        manifests_dir = tmp_path / "manifests"
        manifests_dir.mkdir()

        # Create active manifest with artifacts for OLD file path
        existing_data = {
            "goal": "Create old service",
            "taskType": "create",
            "creatableFiles": ["src/old_service.py"],
            "expectedArtifacts": {
                "file": "src/old_service.py",
                "contains": [
                    {"type": "class", "name": "OldService"},
                    {"type": "function", "name": "process", "class": "OldService"},
                ],
            },
        }
        (manifests_dir / "task-010-create-service.manifest.json").write_text(
            json.dumps(existing_data)
        )

        result = run_create_manifest(
            file_path="src/old_service.py",
            goal="Rename service module",
            artifacts=None,  # No explicit artifacts - should copy from existing
            task_type=None,
            force_supersede=None,
            test_file=None,
            readonly_files=None,
            output_dir=manifests_dir,
            task_number=None,
            json_output=False,
            quiet=True,
            dry_run=False,
            delete=False,
            rename_to="src/new_service.py",
        )

        assert result == 0

        # Find created manifest
        created_manifests = [
            m
            for m in manifests_dir.glob("task-*.manifest.json")
            if "create-service" not in m.name
        ]
        assert len(created_manifests) == 1

        data = json.loads(created_manifests[0].read_text())

        # Should have copied artifacts from existing manifest
        contains = data["expectedArtifacts"]["contains"]
        assert len(contains) >= 1
        artifact_names = [a["name"] for a in contains]
        assert "OldService" in artifact_names or "process" in artifact_names

    def test_rename_to_uses_provided_artifacts_when_given(self, tmp_path):
        """When --artifacts provided, use those instead of copying."""
        manifests_dir = tmp_path / "manifests"
        manifests_dir.mkdir()

        # Create existing manifest with OLD artifacts
        existing_data = {
            "goal": "Create old service",
            "taskType": "create",
            "creatableFiles": ["src/old_service.py"],
            "expectedArtifacts": {
                "file": "src/old_service.py",
                "contains": [{"type": "class", "name": "OldService"}],
            },
        }
        (manifests_dir / "task-010-create-service.manifest.json").write_text(
            json.dumps(existing_data)
        )

        # Provide explicit new artifacts
        new_artifacts = [
            {"type": "class", "name": "NewService"},
            {"type": "function", "name": "new_process"},
        ]

        result = run_create_manifest(
            file_path="src/old_service.py",
            goal="Rename and refactor service module",
            artifacts=new_artifacts,  # Explicit artifacts
            task_type=None,
            force_supersede=None,
            test_file=None,
            readonly_files=None,
            output_dir=manifests_dir,
            task_number=None,
            json_output=False,
            quiet=True,
            dry_run=False,
            delete=False,
            rename_to="src/new_service.py",
        )

        assert result == 0

        # Find created manifest
        created_manifests = [
            m
            for m in manifests_dir.glob("task-*.manifest.json")
            if "create-service" not in m.name
        ]
        assert len(created_manifests) == 1

        data = json.loads(created_manifests[0].read_text())

        # Should use provided artifacts, not copied ones
        contains = data["expectedArtifacts"]["contains"]
        artifact_names = [a["name"] for a in contains]
        assert "NewService" in artifact_names
        assert "new_process" in artifact_names
        # Should NOT have old artifacts
        assert "OldService" not in artifact_names

    def test_rename_to_expected_artifacts_references_new_file(self, tmp_path):
        """expectedArtifacts.file should be the NEW file path."""
        manifests_dir = tmp_path / "manifests"
        manifests_dir.mkdir()

        result = run_create_manifest(
            file_path="src/old_service.py",
            goal="Rename service module",
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
            delete=False,
            rename_to="src/new_service.py",
        )

        assert result == 0

        manifests = list(manifests_dir.glob("task-*.manifest.json"))
        data = json.loads(manifests[0].read_text())

        # expectedArtifacts.file should reference the NEW path
        assert data["expectedArtifacts"]["file"] == "src/new_service.py"


class TestGetArtifactsFromManifests:
    """Tests for _get_artifacts_from_manifests() function."""

    def test_gets_artifacts_from_snapshot_manifest(self, tmp_path):
        """Should extract artifacts from snapshot manifests."""
        manifests_dir = tmp_path / "manifests"
        manifests_dir.mkdir()

        # Create a snapshot manifest with artifacts
        snapshot_data = {
            "goal": "Snapshot service",
            "taskType": "snapshot",
            "expectedArtifacts": {
                "file": "src/service.py",
                "contains": [
                    {"type": "function", "name": "serve"},
                    {"type": "class", "name": "Server"},
                ],
            },
        }
        (manifests_dir / "task-010-snapshot-service.manifest.json").write_text(
            json.dumps(snapshot_data)
        )

        result = _get_artifacts_from_manifests("src/service.py", manifests_dir)

        assert len(result) == 2
        artifact_names = [a["name"] for a in result]
        assert "serve" in artifact_names
        assert "Server" in artifact_names

    def test_gets_artifacts_from_edit_manifest(self, tmp_path):
        """Should extract artifacts from edit manifests."""
        manifests_dir = tmp_path / "manifests"
        manifests_dir.mkdir()

        # Create an edit manifest with artifacts
        edit_data = {
            "goal": "Edit service",
            "taskType": "edit",
            "editableFiles": ["src/service.py"],
            "expectedArtifacts": {
                "file": "src/service.py",
                "contains": [
                    {"type": "function", "name": "process"},
                    {"type": "function", "name": "validate"},
                ],
            },
        }
        (manifests_dir / "task-015-edit-service.manifest.json").write_text(
            json.dumps(edit_data)
        )

        result = _get_artifacts_from_manifests("src/service.py", manifests_dir)

        assert len(result) == 2
        artifact_names = [a["name"] for a in result]
        assert "process" in artifact_names
        assert "validate" in artifact_names

    def test_merges_artifacts_from_multiple_manifests(self, tmp_path):
        """Should combine artifacts from multiple active manifests."""
        manifests_dir = tmp_path / "manifests"
        manifests_dir.mkdir()

        # Create first manifest with some artifacts
        first_data = {
            "goal": "Create service",
            "taskType": "create",
            "creatableFiles": ["src/service.py"],
            "expectedArtifacts": {
                "file": "src/service.py",
                "contains": [{"type": "function", "name": "serve"}],
            },
        }
        (manifests_dir / "task-010-create-service.manifest.json").write_text(
            json.dumps(first_data)
        )

        # Create second manifest with additional artifacts
        second_data = {
            "goal": "Add logging",
            "taskType": "edit",
            "editableFiles": ["src/service.py"],
            "expectedArtifacts": {
                "file": "src/service.py",
                "contains": [{"type": "function", "name": "log"}],
            },
        }
        (manifests_dir / "task-020-add-logging.manifest.json").write_text(
            json.dumps(second_data)
        )

        result = _get_artifacts_from_manifests("src/service.py", manifests_dir)

        # Should have artifacts from both manifests
        artifact_names = [a["name"] for a in result]
        assert "serve" in artifact_names
        assert "log" in artifact_names

    def test_excludes_superseded_manifest_artifacts(self, tmp_path):
        """Should not include artifacts from superseded manifests."""
        manifests_dir = tmp_path / "manifests"
        manifests_dir.mkdir()

        # Create old manifest (will be superseded)
        old_data = {
            "goal": "Old service",
            "taskType": "create",
            "creatableFiles": ["src/service.py"],
            "expectedArtifacts": {
                "file": "src/service.py",
                "contains": [{"type": "function", "name": "old_func"}],
            },
        }
        (manifests_dir / "task-010-old-service.manifest.json").write_text(
            json.dumps(old_data)
        )

        # Create new manifest that supersedes the old one
        new_data = {
            "goal": "Rewrite service",
            "taskType": "edit",
            "supersedes": ["task-010-old-service.manifest.json"],
            "editableFiles": ["src/service.py"],
            "expectedArtifacts": {
                "file": "src/service.py",
                "contains": [{"type": "function", "name": "new_func"}],
            },
        }
        (manifests_dir / "task-020-rewrite-service.manifest.json").write_text(
            json.dumps(new_data)
        )

        result = _get_artifacts_from_manifests("src/service.py", manifests_dir)

        artifact_names = [a["name"] for a in result]
        # Should NOT include old_func (from superseded manifest)
        assert "old_func" not in artifact_names
        # Should include new_func (from active manifest)
        assert "new_func" in artifact_names

    def test_returns_empty_when_no_manifests(self, tmp_path):
        """Returns empty list when no manifests exist for file."""
        manifests_dir = tmp_path / "manifests"
        manifests_dir.mkdir()

        # Create manifest for a DIFFERENT file
        other_data = {
            "goal": "Other module",
            "taskType": "create",
            "creatableFiles": ["src/other.py"],
            "expectedArtifacts": {
                "file": "src/other.py",
                "contains": [{"type": "function", "name": "other_func"}],
            },
        }
        (manifests_dir / "task-010-other.manifest.json").write_text(
            json.dumps(other_data)
        )

        result = _get_artifacts_from_manifests("src/service.py", manifests_dir)

        assert result == []

    def test_handles_missing_manifest_directory(self, tmp_path):
        """Returns empty list when manifest directory doesn't exist."""
        manifests_dir = tmp_path / "manifests"
        # Directory not created

        result = _get_artifacts_from_manifests("src/service.py", manifests_dir)

        assert result == []

    def test_handles_manifest_without_contains(self, tmp_path):
        """Gracefully handles manifests with missing contains array."""
        manifests_dir = tmp_path / "manifests"
        manifests_dir.mkdir()

        # Create manifest without contains array
        malformed_data = {
            "goal": "Malformed manifest",
            "taskType": "edit",
            "editableFiles": ["src/service.py"],
            "expectedArtifacts": {
                "file": "src/service.py",
                # Missing "contains" array
            },
        }
        (manifests_dir / "task-010-malformed.manifest.json").write_text(
            json.dumps(malformed_data)
        )

        # Should not crash
        result = _get_artifacts_from_manifests("src/service.py", manifests_dir)

        # Should return empty list (no artifacts found)
        assert result == []


class TestRenameToWithJsonOutput:
    """Tests for JSON output mode with rename_to flag."""

    def test_rename_json_output_shows_new_file_in_creatable(self, tmp_path, capsys):
        """JSON output shows new file in creatableFiles."""
        manifests_dir = tmp_path / "manifests"
        manifests_dir.mkdir()

        result = run_create_manifest(
            file_path="src/old_service.py",
            goal="Rename service module",
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
            delete=False,
            rename_to="src/new_service.py",
        )

        assert result == 0

        captured = capsys.readouterr()
        output = json.loads(captured.out)

        assert output["success"] is True
        assert "src/new_service.py" in output["manifest"]["creatableFiles"]
        assert output["manifest"]["expectedArtifacts"]["file"] == "src/new_service.py"


class TestRenameToWithDryRun:
    """Tests for dry-run mode with rename_to flag."""

    def test_rename_dry_run_shows_correct_structure(self, tmp_path, capsys):
        """Dry run previews rename manifest correctly."""
        manifests_dir = tmp_path / "manifests"
        manifests_dir.mkdir()

        result = run_create_manifest(
            file_path="src/old_service.py",
            goal="Rename service module",
            artifacts=[{"type": "function", "name": "serve"}],
            task_type=None,
            force_supersede=None,
            test_file=None,
            readonly_files=None,
            output_dir=manifests_dir,
            task_number=None,
            json_output=True,
            quiet=False,
            dry_run=True,
            delete=False,
            rename_to="src/new_service.py",
        )

        assert result == 0

        captured = capsys.readouterr()
        output = json.loads(captured.out)

        assert output["dry_run"] is True
        assert output["manifest"]["taskType"] == "refactor"
        assert "src/new_service.py" in output["manifest"]["creatableFiles"]
        assert output["manifest"]["expectedArtifacts"]["file"] == "src/new_service.py"

        # No manifest file should be created
        manifests = list(manifests_dir.glob("task-*.manifest.json"))
        assert len(manifests) == 0


class TestRenameToErrorHandling:
    """Tests for error handling with rename_to flag."""

    def test_rename_to_same_path_error(self, tmp_path, capsys):
        """Should error if rename_to is same as file_path."""
        manifests_dir = tmp_path / "manifests"
        manifests_dir.mkdir()

        # Using JSON output to capture error
        result = run_create_manifest(
            file_path="src/service.py",
            goal="Rename to same path",
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
            delete=False,
            rename_to="src/service.py",  # Same as file_path
        )

        assert result == 1  # Non-zero exit code

        captured = capsys.readouterr()
        output = json.loads(captured.out)

        assert output["success"] is False
        assert "error" in output

    def test_rename_to_and_delete_mutually_exclusive(self, tmp_path, capsys):
        """Should error if both --delete and --rename-to provided."""
        manifests_dir = tmp_path / "manifests"
        manifests_dir.mkdir()

        # Using JSON output to capture error
        result = run_create_manifest(
            file_path="src/service.py",
            goal="Invalid operation",
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
            rename_to="src/new_service.py",  # Both delete and rename_to
        )

        assert result == 1  # Non-zero exit code

        captured = capsys.readouterr()
        output = json.loads(captured.out)

        assert output["success"] is False
        assert "error" in output


class TestRenameToIntegration:
    """Integration tests for rename_to flag."""

    def test_rename_creates_valid_manifest_structure(self, tmp_path):
        """Full integration test verifying the manifest structure."""
        manifests_dir = tmp_path / "manifests"
        manifests_dir.mkdir()

        # Create existing manifest to supersede
        existing_data = {
            "goal": "Create auth module",
            "taskType": "create",
            "creatableFiles": ["src/auth/old_auth.py"],
            "expectedArtifacts": {
                "file": "src/auth/old_auth.py",
                "contains": [
                    {"type": "class", "name": "AuthHandler"},
                    {
                        "type": "function",
                        "name": "authenticate",
                        "class": "AuthHandler",
                    },
                ],
            },
        }
        (manifests_dir / "task-050-create-auth.manifest.json").write_text(
            json.dumps(existing_data)
        )

        result = run_create_manifest(
            file_path="src/auth/old_auth.py",
            goal="Rename auth module to better location",
            artifacts=None,  # Should copy from existing
            task_type=None,
            force_supersede=None,
            test_file="tests/test_auth.py",
            readonly_files=["src/config.py"],
            output_dir=manifests_dir,
            task_number=None,
            json_output=False,
            quiet=True,
            dry_run=False,
            delete=False,
            rename_to="src/authentication/handler.py",
        )

        assert result == 0

        # Find the created rename manifest
        created_manifests = [
            m
            for m in manifests_dir.glob("task-*.manifest.json")
            if "create-auth" not in m.name
        ]
        assert len(created_manifests) == 1

        data = json.loads(created_manifests[0].read_text())

        # Verify manifest structure
        assert data["goal"] == "Rename auth module to better location"
        assert data["taskType"] == "refactor"

        # New path in creatableFiles
        assert "src/authentication/handler.py" in data["creatableFiles"]
        # Old path NOT in file lists
        assert "src/auth/old_auth.py" not in data["creatableFiles"]
        assert "src/auth/old_auth.py" not in data["editableFiles"]

        # Supersedes the old manifest
        assert "task-050-create-auth.manifest.json" in data["supersedes"]

        # expectedArtifacts references new path
        assert data["expectedArtifacts"]["file"] == "src/authentication/handler.py"

        # Has readonly files
        assert "src/config.py" in data["readonlyFiles"]

        # Has validation command with test file
        assert "tests/test_auth.py" in data["validationCommand"]

    def test_rename_to_default_none(self, tmp_path):
        """Verifies rename_to=None is the default behavior (normal manifest creation)."""
        manifests_dir = tmp_path / "manifests"
        manifests_dir.mkdir()

        # Create without rename_to - should behave like normal manifest creation
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
            rename_to=None,  # Explicitly None (default)
        )

        assert result == 0

        manifests = list(manifests_dir.glob("task-*.manifest.json"))
        data = json.loads(manifests[0].read_text())

        # Should behave like normal create manifest
        assert data["taskType"] == "create"
        assert "src/service.py" in data["creatableFiles"]
        assert data["expectedArtifacts"]["file"] == "src/service.py"
        # Should have the artifact
        assert len(data["expectedArtifacts"]["contains"]) == 1
        assert data["expectedArtifacts"]["contains"][0]["name"] == "new_func"
