"""Behavioral tests for task-097: Manifest Create Core Logic module.

These tests verify the core functions in `maid_runner/cli/manifest_create.py`:
- _get_next_task_number(): Find next available task number by scanning manifest directory
- _detect_task_type(): Auto-detect create/edit based on file existence
- _find_active_snapshot_to_supersede(): Find active snapshot that must be superseded
- _generate_manifest(): Build manifest dictionary from parameters
- _write_manifest(): Write manifest dictionary to JSON file
- run_create_manifest(): Main entry point for manifest creation

Tests focus on actual behavior (inputs/outputs), not implementation details.
"""

import json

import pytest

from maid_runner.cli.manifest_create import (
    _get_next_task_number,
    _detect_task_type,
    _find_active_snapshot_to_supersede,
    _generate_manifest,
    _write_manifest,
    run_create_manifest,
)


class TestGetNextTaskNumber:
    """Tests for _get_next_task_number() function."""

    def test_returns_one_for_empty_directory(self, tmp_path):
        """Returns 1 when manifest directory is empty."""
        manifests_dir = tmp_path / "manifests"
        manifests_dir.mkdir()

        result = _get_next_task_number(manifests_dir)

        assert result == 1

    def test_returns_one_when_directory_does_not_exist(self, tmp_path):
        """Returns 1 when manifest directory does not exist."""
        manifests_dir = tmp_path / "manifests"
        # Directory not created

        result = _get_next_task_number(manifests_dir)

        assert result == 1

    def test_returns_max_plus_one_when_manifests_exist(self, tmp_path):
        """Returns max+1 when manifest files exist."""
        manifests_dir = tmp_path / "manifests"
        manifests_dir.mkdir()

        # Create some manifest files
        (manifests_dir / "task-001-initial.manifest.json").write_text(
            '{"goal": "test"}'
        )
        (manifests_dir / "task-005-feature.manifest.json").write_text(
            '{"goal": "test"}'
        )
        (manifests_dir / "task-094-latest.manifest.json").write_text('{"goal": "test"}')

        result = _get_next_task_number(manifests_dir)

        assert result == 95

    def test_handles_non_sequential_task_numbers(self, tmp_path):
        """Correctly handles non-sequential task numbers."""
        manifests_dir = tmp_path / "manifests"
        manifests_dir.mkdir()

        # Create non-sequential manifest files with gaps
        (manifests_dir / "task-010-first.manifest.json").write_text('{"goal": "test"}')
        (manifests_dir / "task-050-middle.manifest.json").write_text('{"goal": "test"}')
        (manifests_dir / "task-030-another.manifest.json").write_text(
            '{"goal": "test"}'
        )

        result = _get_next_task_number(manifests_dir)

        # Should return max+1, not fill gaps
        assert result == 51

    def test_ignores_non_manifest_files(self, tmp_path):
        """Ignores files that don't match task-*.manifest.json pattern."""
        manifests_dir = tmp_path / "manifests"
        manifests_dir.mkdir()

        # Create manifest file and other files
        (manifests_dir / "task-005-real.manifest.json").write_text('{"goal": "test"}')
        (manifests_dir / "other-file.json").write_text("{}")
        (manifests_dir / "readme.md").write_text("# README")
        (manifests_dir / "snapshot-001.manifest.json").write_text("{}")

        result = _get_next_task_number(manifests_dir)

        assert result == 6

    def test_handles_three_digit_task_numbers(self, tmp_path):
        """Handles task numbers with more than 3 digits."""
        manifests_dir = tmp_path / "manifests"
        manifests_dir.mkdir()

        (manifests_dir / "task-099-before.manifest.json").write_text('{"goal": "test"}')
        (manifests_dir / "task-100-century.manifest.json").write_text(
            '{"goal": "test"}'
        )
        (manifests_dir / "task-101-after.manifest.json").write_text('{"goal": "test"}')

        result = _get_next_task_number(manifests_dir)

        assert result == 102


class TestDetectTaskType:
    """Tests for _detect_task_type() function."""

    def test_returns_create_when_file_does_not_exist(self, tmp_path):
        """Returns 'create' when the target file does not exist."""
        file_path = tmp_path / "new_module.py"
        # File not created

        result = _detect_task_type(file_path)

        assert result == "create"

    def test_returns_edit_when_file_exists(self, tmp_path):
        """Returns 'edit' when the target file exists."""
        file_path = tmp_path / "existing_module.py"
        file_path.write_text("# Existing content")

        result = _detect_task_type(file_path)

        assert result == "edit"

    def test_returns_edit_for_empty_file(self, tmp_path):
        """Returns 'edit' even for empty files (they exist)."""
        file_path = tmp_path / "empty_module.py"
        file_path.write_text("")

        result = _detect_task_type(file_path)

        assert result == "edit"

    def test_accepts_path_as_path_object(self, tmp_path):
        """Works with Path objects."""
        file_path = tmp_path / "module.py"

        result = _detect_task_type(file_path)

        assert result == "create"

    def test_handles_nested_path_that_does_not_exist(self, tmp_path):
        """Handles file in non-existent directory."""
        file_path = tmp_path / "src" / "deep" / "nested" / "module.py"

        result = _detect_task_type(file_path)

        assert result == "create"


class TestFindActiveSnapshotToSupersede:
    """Tests for _find_active_snapshot_to_supersede() function."""

    def test_returns_none_when_no_snapshot_exists(self, tmp_path):
        """Returns None when no snapshot manifest exists for the file."""
        manifests_dir = tmp_path / "manifests"
        manifests_dir.mkdir()

        # Create a non-snapshot manifest for a different file
        manifest_data = {
            "goal": "Add feature",
            "taskType": "edit",
            "expectedArtifacts": {"file": "other/file.py", "contains": []},
        }
        (manifests_dir / "task-001-add-feature.manifest.json").write_text(
            json.dumps(manifest_data)
        )

        result = _find_active_snapshot_to_supersede("src/service.py", manifests_dir)

        assert result is None

    def test_returns_snapshot_name_when_active_snapshot_exists(self, tmp_path):
        """Returns snapshot manifest name when an active snapshot exists."""
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
        (manifests_dir / "task-012-snapshot-service.manifest.json").write_text(
            json.dumps(snapshot_data)
        )

        result = _find_active_snapshot_to_supersede("src/service.py", manifests_dir)

        assert result == "task-012-snapshot-service.manifest.json"

    def test_skips_already_superseded_snapshots(self, tmp_path):
        """Skips snapshot manifests that have been superseded by other manifests."""
        manifests_dir = tmp_path / "manifests"
        manifests_dir.mkdir()

        # Create an old snapshot
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

        result = _find_active_snapshot_to_supersede("src/service.py", manifests_dir)

        # Should not return the superseded snapshot
        assert result is None

    def test_returns_only_snapshot_not_edit_manifest(self, tmp_path):
        """Returns only snapshot manifests, not edit/create manifests."""
        manifests_dir = tmp_path / "manifests"
        manifests_dir.mkdir()

        # Create an edit manifest for our target file
        edit_manifest = {
            "goal": "Edit service",
            "taskType": "edit",
            "expectedArtifacts": {"file": "src/service.py", "contains": []},
        }
        (manifests_dir / "task-020-edit-service.manifest.json").write_text(
            json.dumps(edit_manifest)
        )

        # Create a create manifest for our target file
        create_manifest = {
            "goal": "Create service",
            "taskType": "create",
            "expectedArtifacts": {"file": "src/service.py", "contains": []},
        }
        (manifests_dir / "task-021-create-service.manifest.json").write_text(
            json.dumps(create_manifest)
        )

        result = _find_active_snapshot_to_supersede("src/service.py", manifests_dir)

        # Should not return edit/create manifests, only snapshots
        assert result is None

    def test_returns_none_when_directory_empty(self, tmp_path):
        """Returns None when manifest directory is empty."""
        manifests_dir = tmp_path / "manifests"
        manifests_dir.mkdir()

        result = _find_active_snapshot_to_supersede("src/service.py", manifests_dir)

        assert result is None

    def test_returns_none_when_directory_does_not_exist(self, tmp_path):
        """Returns None when manifest directory does not exist."""
        manifests_dir = tmp_path / "manifests"
        # Not created

        result = _find_active_snapshot_to_supersede("src/service.py", manifests_dir)

        assert result is None

    def test_handles_manifest_without_expected_artifacts(self, tmp_path):
        """Gracefully handles manifest without expectedArtifacts field."""
        manifests_dir = tmp_path / "manifests"
        manifests_dir.mkdir()

        # Create a malformed manifest
        malformed = {
            "goal": "Some task",
            "taskType": "snapshot",
            # Missing expectedArtifacts
        }
        (manifests_dir / "task-001-malformed.manifest.json").write_text(
            json.dumps(malformed)
        )

        result = _find_active_snapshot_to_supersede("src/service.py", manifests_dir)

        # Should not crash, just return None
        assert result is None

    def test_finds_snapshot_among_multiple_manifests(self, tmp_path):
        """Finds correct snapshot when multiple manifests exist."""
        manifests_dir = tmp_path / "manifests"
        manifests_dir.mkdir()

        # Create multiple manifests for different files
        for i, (file, task_type) in enumerate(
            [
                ("src/other.py", "snapshot"),
                ("src/service.py", "edit"),
                ("src/service.py", "snapshot"),  # This is the one
                ("src/another.py", "create"),
            ],
            start=1,
        ):
            manifest = {
                "goal": f"Task {i}",
                "taskType": task_type,
                "expectedArtifacts": {"file": file, "contains": []},
            }
            (manifests_dir / f"task-{i:03d}-task.manifest.json").write_text(
                json.dumps(manifest)
            )

        result = _find_active_snapshot_to_supersede("src/service.py", manifests_dir)

        assert result == "task-003-task.manifest.json"


class TestGenerateManifest:
    """Tests for _generate_manifest() function."""

    def test_generates_correct_structure_with_all_fields(self):
        """Generates manifest with all required fields."""
        result = _generate_manifest(
            goal="Add AuthService class",
            file_path="src/auth/service.py",
            task_type="edit",
            artifacts=[{"type": "class", "name": "AuthService"}],
            supersedes=["task-012-snapshot.manifest.json"],
            readonly_files=["src/utils.py"],
            validation_command=["pytest", "tests/test_auth.py", "-v"],
        )

        assert result["goal"] == "Add AuthService class"
        assert result["taskType"] == "edit"
        assert result["supersedes"] == ["task-012-snapshot.manifest.json"]
        assert result["readonlyFiles"] == ["src/utils.py"]
        assert result["validationCommand"] == ["pytest", "tests/test_auth.py", "-v"]

    def test_uses_creatable_files_for_new_files(self):
        """Uses creatableFiles when task type is 'create'."""
        result = _generate_manifest(
            goal="Create new module",
            file_path="src/new_module.py",
            task_type="create",
            artifacts=[],
            supersedes=[],
            readonly_files=[],
            validation_command=[],
        )

        assert "src/new_module.py" in result["creatableFiles"]
        assert result["editableFiles"] == []

    def test_uses_editable_files_for_existing_files(self):
        """Uses editableFiles when task type is 'edit'."""
        result = _generate_manifest(
            goal="Edit existing module",
            file_path="src/existing.py",
            task_type="edit",
            artifacts=[],
            supersedes=[],
            readonly_files=[],
            validation_command=[],
        )

        assert "src/existing.py" in result["editableFiles"]
        assert result["creatableFiles"] == []

    def test_includes_supersedes_when_provided(self):
        """Includes supersedes array when provided."""
        result = _generate_manifest(
            goal="Complete rewrite",
            file_path="src/module.py",
            task_type="edit",
            artifacts=[],
            supersedes=["task-050-old-manifest.manifest.json"],
            readonly_files=[],
            validation_command=[],
        )

        assert result["supersedes"] == ["task-050-old-manifest.manifest.json"]

    def test_includes_artifacts_in_expected_artifacts(self):
        """Includes artifacts in expectedArtifacts.contains."""
        artifacts = [
            {"type": "function", "name": "authenticate"},
            {"type": "class", "name": "AuthService"},
        ]

        result = _generate_manifest(
            goal="Add auth",
            file_path="src/auth.py",
            task_type="create",
            artifacts=artifacts,
            supersedes=[],
            readonly_files=[],
            validation_command=[],
        )

        assert result["expectedArtifacts"]["file"] == "src/auth.py"
        assert result["expectedArtifacts"]["contains"] == artifacts

    def test_empty_artifacts_generates_empty_contains(self):
        """Empty artifacts list generates empty contains array."""
        result = _generate_manifest(
            goal="Add module",
            file_path="src/module.py",
            task_type="create",
            artifacts=[],
            supersedes=[],
            readonly_files=[],
            validation_command=[],
        )

        assert result["expectedArtifacts"]["contains"] == []

    def test_refactor_task_type_uses_editable_files(self):
        """Refactor task type uses editableFiles like edit."""
        result = _generate_manifest(
            goal="Refactor module",
            file_path="src/module.py",
            task_type="refactor",
            artifacts=[],
            supersedes=[],
            readonly_files=[],
            validation_command=[],
        )

        assert "src/module.py" in result["editableFiles"]
        assert result["creatableFiles"] == []

    def test_empty_supersedes_generates_empty_array(self):
        """Empty supersedes list generates empty array in manifest."""
        result = _generate_manifest(
            goal="New feature",
            file_path="src/module.py",
            task_type="create",
            artifacts=[],
            supersedes=[],
            readonly_files=[],
            validation_command=[],
        )

        assert result["supersedes"] == []


class TestWriteManifest:
    """Tests for _write_manifest() function."""

    def test_writes_valid_json_to_file(self, tmp_path):
        """Writes manifest data as valid JSON to file."""
        manifest_data = {
            "goal": "Test goal",
            "taskType": "create",
            "creatableFiles": ["src/module.py"],
            "editableFiles": [],
            "readonlyFiles": [],
            "expectedArtifacts": {"file": "src/module.py", "contains": []},
            "validationCommand": ["pytest", "tests/test.py", "-v"],
        }
        output_path = tmp_path / "manifests" / "task-001-test.manifest.json"
        output_path.parent.mkdir(parents=True, exist_ok=True)

        _write_manifest(manifest_data, output_path)

        # Read back and verify it's valid JSON
        assert output_path.exists()
        with open(output_path) as f:
            loaded = json.load(f)
        assert loaded == manifest_data

    def test_creates_parent_directories_if_needed(self, tmp_path):
        """Creates parent directories if they don't exist."""
        manifest_data = {"goal": "Test", "taskType": "create"}
        output_path = (
            tmp_path / "deep" / "nested" / "manifests" / "task-001.manifest.json"
        )

        _write_manifest(manifest_data, output_path)

        assert output_path.exists()
        assert output_path.parent.exists()

    def test_writes_formatted_json(self, tmp_path):
        """Writes human-readable formatted JSON (not compact)."""
        manifest_data = {
            "goal": "Test",
            "taskType": "create",
            "expectedArtifacts": {"file": "test.py", "contains": []},
        }
        output_path = tmp_path / "task-001.manifest.json"

        _write_manifest(manifest_data, output_path)

        content = output_path.read_text()
        # Formatted JSON should have newlines
        assert "\n" in content
        # Should have some indentation
        assert "  " in content or "\t" in content

    def test_overwrites_existing_file(self, tmp_path):
        """Overwrites existing manifest file."""
        output_path = tmp_path / "task-001.manifest.json"
        output_path.write_text('{"goal": "old"}')

        new_data = {"goal": "new", "taskType": "edit"}

        _write_manifest(new_data, output_path)

        loaded = json.loads(output_path.read_text())
        assert loaded["goal"] == "new"


class TestRunCreateManifest:
    """Integration tests for run_create_manifest() function."""

    def test_creates_manifest_file_with_correct_naming(self, tmp_path, capsys):
        """Creates manifest file with correct task number and naming."""
        manifests_dir = tmp_path / "manifests"
        manifests_dir.mkdir()

        # Create one existing manifest
        (manifests_dir / "task-050-existing.manifest.json").write_text(
            '{"goal": "existing"}'
        )

        # Create the target file
        target_file = tmp_path / "src" / "service.py"
        target_file.parent.mkdir(parents=True)
        target_file.write_text("# Service")

        result = run_create_manifest(
            file_path=str(target_file),
            goal="Add new feature",
            artifacts=[],
            task_type=None,  # Auto-detect
            force_supersede=None,
            test_file=None,
            readonly_files=[],
            output_dir=manifests_dir,
            task_number=None,  # Auto-number
            json_output=False,
            quiet=False,
            dry_run=False,
        )

        assert result == 0
        # Should create task-051-*.manifest.json
        manifests = list(manifests_dir.glob("task-051-*.manifest.json"))
        assert len(manifests) == 1

    def test_handles_dry_run_does_not_write_file(self, tmp_path, capsys):
        """Dry run mode does not write manifest file."""
        manifests_dir = tmp_path / "manifests"
        manifests_dir.mkdir()

        result = run_create_manifest(
            file_path="src/new_module.py",
            goal="Test dry run",
            artifacts=[],
            task_type=None,
            force_supersede=None,
            test_file=None,
            readonly_files=[],
            output_dir=manifests_dir,
            task_number=None,
            json_output=False,
            quiet=False,
            dry_run=True,
        )

        assert result == 0
        # No manifest file should be created
        manifests = list(manifests_dir.glob("task-*.manifest.json"))
        assert len(manifests) == 0

    def test_handles_json_output_mode(self, tmp_path, capsys):
        """JSON output mode outputs parseable JSON."""
        manifests_dir = tmp_path / "manifests"
        manifests_dir.mkdir()

        result = run_create_manifest(
            file_path="src/service.py",
            goal="Add login method",
            artifacts=[{"type": "function", "name": "login"}],
            task_type="create",
            force_supersede=None,
            test_file=None,
            readonly_files=[],
            output_dir=manifests_dir,
            task_number=None,
            json_output=True,
            quiet=True,
            dry_run=False,
        )

        assert result == 0
        captured = capsys.readouterr()
        # Output should be valid JSON
        output = json.loads(captured.out)
        assert "success" in output or "manifest" in output

    def test_auto_supersedes_active_snapshots(self, tmp_path):
        """Automatically supersedes active snapshot manifests."""
        manifests_dir = tmp_path / "manifests"
        manifests_dir.mkdir()

        # Create an active snapshot for our target file
        snapshot_data = {
            "goal": "Snapshot service",
            "taskType": "snapshot",
            "expectedArtifacts": {
                "file": "src/service.py",
                "contains": [{"type": "function", "name": "serve"}],
            },
        }
        (manifests_dir / "task-012-snapshot-service.manifest.json").write_text(
            json.dumps(snapshot_data)
        )

        # Create the target file (simulating existing snapshotted file)
        target_file = tmp_path / "src" / "service.py"
        target_file.parent.mkdir(parents=True)
        target_file.write_text("def serve(): pass")

        result = run_create_manifest(
            file_path="src/service.py",
            goal="Add login method",
            artifacts=[],
            task_type=None,
            force_supersede=None,
            test_file=None,
            readonly_files=[],
            output_dir=manifests_dir,
            task_number=None,
            json_output=False,
            quiet=True,
            dry_run=False,
        )

        assert result == 0

        # Find the created manifest
        created_manifests = [
            m
            for m in manifests_dir.glob("task-*.manifest.json")
            if "snapshot-service" not in m.name
        ]
        assert len(created_manifests) == 1

        # Verify it supersedes the snapshot
        created_data = json.loads(created_manifests[0].read_text())
        assert "task-012-snapshot-service.manifest.json" in created_data.get(
            "supersedes", []
        )

    def test_returns_zero_on_success(self, tmp_path):
        """Returns exit code 0 on success."""
        manifests_dir = tmp_path / "manifests"
        manifests_dir.mkdir()

        result = run_create_manifest(
            file_path="src/module.py",
            goal="Test success",
            artifacts=[],
            task_type="create",
            force_supersede=None,
            test_file=None,
            readonly_files=[],
            output_dir=manifests_dir,
            task_number=None,
            json_output=False,
            quiet=True,
            dry_run=False,
        )

        assert result == 0

    def test_uses_explicit_task_type(self, tmp_path):
        """Uses explicitly provided task type instead of auto-detect."""
        manifests_dir = tmp_path / "manifests"
        manifests_dir.mkdir()

        # Create an existing file
        target_file = tmp_path / "src" / "module.py"
        target_file.parent.mkdir(parents=True)
        target_file.write_text("# Existing")

        result = run_create_manifest(
            file_path=str(target_file),
            goal="Refactor module",
            artifacts=[],
            task_type="refactor",  # Explicitly set
            force_supersede=None,
            test_file=None,
            readonly_files=[],
            output_dir=manifests_dir,
            task_number=None,
            json_output=False,
            quiet=True,
            dry_run=False,
        )

        assert result == 0
        created = list(manifests_dir.glob("task-*.manifest.json"))[0]
        data = json.loads(created.read_text())
        assert data["taskType"] == "refactor"

    def test_uses_explicit_task_number(self, tmp_path):
        """Uses explicitly provided task number instead of auto-number."""
        manifests_dir = tmp_path / "manifests"
        manifests_dir.mkdir()

        # Create existing manifests
        (manifests_dir / "task-001-first.manifest.json").write_text('{"goal": "first"}')
        (manifests_dir / "task-002-second.manifest.json").write_text(
            '{"goal": "second"}'
        )

        result = run_create_manifest(
            file_path="src/module.py",
            goal="Test explicit number",
            artifacts=[],
            task_type="create",
            force_supersede=None,
            test_file=None,
            readonly_files=[],
            output_dir=manifests_dir,
            task_number=100,  # Explicitly set
            json_output=False,
            quiet=True,
            dry_run=False,
        )

        assert result == 0
        created = list(manifests_dir.glob("task-100-*.manifest.json"))
        assert len(created) == 1

    def test_uses_force_supersede_manifest(self, tmp_path):
        """Uses force_supersede to supersede specific manifest."""
        manifests_dir = tmp_path / "manifests"
        manifests_dir.mkdir()

        # Create a non-snapshot manifest
        edit_manifest = {
            "goal": "Old edit",
            "taskType": "edit",
            "expectedArtifacts": {"file": "src/service.py", "contains": []},
        }
        (manifests_dir / "task-050-old-edit.manifest.json").write_text(
            json.dumps(edit_manifest)
        )

        result = run_create_manifest(
            file_path="src/service.py",
            goal="Complete rewrite",
            artifacts=[],
            task_type="edit",
            force_supersede="task-050-old-edit.manifest.json",
            test_file=None,
            readonly_files=[],
            output_dir=manifests_dir,
            task_number=None,
            json_output=False,
            quiet=True,
            dry_run=False,
        )

        assert result == 0

        # Find the created manifest
        created_manifests = [
            m
            for m in manifests_dir.glob("task-*.manifest.json")
            if "old-edit" not in m.name
        ]
        assert len(created_manifests) == 1

        created_data = json.loads(created_manifests[0].read_text())
        assert "task-050-old-edit.manifest.json" in created_data.get("supersedes", [])

    def test_includes_test_file_in_validation_command(self, tmp_path):
        """Uses specified test file in validation command."""
        manifests_dir = tmp_path / "manifests"
        manifests_dir.mkdir()

        result = run_create_manifest(
            file_path="src/service.py",
            goal="Add feature",
            artifacts=[],
            task_type="create",
            force_supersede=None,
            test_file="tests/test_service.py",
            readonly_files=[],
            output_dir=manifests_dir,
            task_number=None,
            json_output=False,
            quiet=True,
            dry_run=False,
        )

        assert result == 0
        created = list(manifests_dir.glob("task-*.manifest.json"))[0]
        data = json.loads(created.read_text())
        # Validation command should include the test file
        assert "tests/test_service.py" in str(data.get("validationCommand", []))

    def test_includes_readonly_files(self, tmp_path):
        """Includes readonly files in manifest."""
        manifests_dir = tmp_path / "manifests"
        manifests_dir.mkdir()

        result = run_create_manifest(
            file_path="src/service.py",
            goal="Add feature",
            artifacts=[],
            task_type="create",
            force_supersede=None,
            test_file=None,
            readonly_files=["src/utils.py", "src/config.py"],
            output_dir=manifests_dir,
            task_number=None,
            json_output=False,
            quiet=True,
            dry_run=False,
        )

        assert result == 0
        created = list(manifests_dir.glob("task-*.manifest.json"))[0]
        data = json.loads(created.read_text())
        assert "src/utils.py" in data["readonlyFiles"]
        assert "src/config.py" in data["readonlyFiles"]


class TestIntegration:
    """Integration tests combining multiple functions."""

    def test_full_workflow_new_file(self, tmp_path, capsys):
        """Full workflow for creating manifest for a new file."""
        manifests_dir = tmp_path / "manifests"
        manifests_dir.mkdir()

        # Create some existing manifests
        (manifests_dir / "task-094-existing.manifest.json").write_text(
            json.dumps({"goal": "existing", "taskType": "edit"})
        )

        result = run_create_manifest(
            file_path="src/new_service.py",
            goal="Add NewService class for authentication",
            artifacts=[
                {"type": "class", "name": "NewService"},
                {"type": "function", "name": "authenticate", "class": "NewService"},
            ],
            task_type=None,  # Auto-detect -> should be "create"
            force_supersede=None,
            test_file=None,
            readonly_files=["src/utils.py"],
            output_dir=manifests_dir,
            task_number=None,  # Auto -> should be 95
            json_output=False,
            quiet=False,
            dry_run=False,
        )

        assert result == 0

        # Verify manifest was created with correct structure
        created = list(manifests_dir.glob("task-095-*.manifest.json"))
        assert len(created) == 1

        data = json.loads(created[0].read_text())
        assert data["goal"] == "Add NewService class for authentication"
        assert data["taskType"] == "create"
        assert "src/new_service.py" in data["creatableFiles"]
        assert data["editableFiles"] == []
        assert "src/utils.py" in data["readonlyFiles"]
        assert len(data["expectedArtifacts"]["contains"]) == 2

    def test_full_workflow_edit_with_snapshot_supersede(self, tmp_path):
        """Full workflow for editing file with active snapshot."""
        manifests_dir = tmp_path / "manifests"
        manifests_dir.mkdir()

        # Create an active snapshot
        snapshot_data = {
            "goal": "Snapshot auth service",
            "taskType": "snapshot",
            "expectedArtifacts": {
                "file": "src/auth.py",
                "contains": [{"type": "function", "name": "login"}],
            },
        }
        (manifests_dir / "task-010-snapshot-auth.manifest.json").write_text(
            json.dumps(snapshot_data)
        )

        # Create the target file
        target = tmp_path / "src" / "auth.py"
        target.parent.mkdir(parents=True)
        target.write_text("def login(): pass")

        result = run_create_manifest(
            file_path="src/auth.py",
            goal="Add logout method",
            artifacts=[{"type": "function", "name": "logout"}],
            task_type=None,  # Auto-detect -> should be "edit"
            force_supersede=None,  # Auto-supersede snapshot
            test_file=None,
            readonly_files=[],
            output_dir=manifests_dir,
            task_number=None,
            json_output=False,
            quiet=True,
            dry_run=False,
        )

        assert result == 0

        # Verify new manifest
        created = [
            m
            for m in manifests_dir.glob("task-*.manifest.json")
            if "snapshot-auth" not in m.name
        ]
        assert len(created) == 1

        data = json.loads(created[0].read_text())
        assert data["taskType"] == "edit"
        assert "src/auth.py" in data["editableFiles"]
        assert "task-010-snapshot-auth.manifest.json" in data["supersedes"]
        assert data["expectedArtifacts"]["contains"] == [
            {"type": "function", "name": "logout"}
        ]


class TestJsonErrorHandling:
    """Tests for JSON error output mode."""

    def test_json_mode_returns_json_error_on_invalid_artifacts(self, tmp_path, capsys):
        """When json_output=True and error occurs, returns JSON formatted error."""
        manifests_dir = tmp_path / "manifests"
        manifests_dir.mkdir()

        result = run_create_manifest(
            file_path="src/module.py",
            goal="Test error",
            artifacts="invalid json",  # Invalid JSON string
            task_type="create",
            force_supersede=None,
            test_file=None,
            readonly_files=[],
            output_dir=manifests_dir,
            task_number=None,
            json_output=True,  # JSON mode enabled
            quiet=True,
            dry_run=False,
        )

        assert result == 1  # Non-zero exit code
        captured = capsys.readouterr()
        output = json.loads(captured.out)
        assert output["success"] is False
        assert "error" in output
        assert "Invalid JSON" in output["error"]

    def test_non_json_mode_raises_exception_on_invalid_artifacts(self, tmp_path):
        """When json_output=False and error occurs, raises exception normally."""
        manifests_dir = tmp_path / "manifests"
        manifests_dir.mkdir()

        with pytest.raises(ValueError, match="Invalid JSON"):
            run_create_manifest(
                file_path="src/module.py",
                goal="Test error",
                artifacts="invalid json",
                task_type="create",
                force_supersede=None,
                test_file=None,
                readonly_files=[],
                output_dir=manifests_dir,
                task_number=None,
                json_output=False,  # Not JSON mode
                quiet=True,
                dry_run=False,
            )
