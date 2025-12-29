"""Behavioral tests for task-100: Supersession validity validation.

These tests verify that the supersession validation functions detect
invalid/abusive supersession in manifests. The validation ensures:
- Delete operations supersede manifests for the same file
- Rename operations supersede manifests for the old path only
- Snapshot edits only supersede snapshot manifests for the same file
- Unrelated file supersession is rejected

Tests focus on actual behavior (inputs/outputs), not implementation details.
"""

import json
from pathlib import Path

import pytest

from maid_runner.validators.semantic_validator import (
    ManifestSemanticError,
    validate_supersession,
    _get_superseded_manifest_files,
    _validate_delete_supersession,
    _validate_rename_supersession,
    _validate_snapshot_edit_supersession,
)


def _create_manifest_file(manifests_dir: Path, name: str, data: dict) -> Path:
    """Helper to create a manifest file in the temp directory."""
    manifest_path = manifests_dir / name
    manifest_path.write_text(json.dumps(data, indent=2))
    return manifest_path


class TestValidateSupersessionValidCases:
    """Tests for valid supersession patterns that should pass validation."""

    def test_delete_operation_superseding_same_file(self, tmp_path):
        """Delete manifest with status: absent can supersede manifests for the same file."""
        manifests_dir = tmp_path / "manifests"
        manifests_dir.mkdir()

        # Create a snapshot manifest for target file
        snapshot_data = {
            "goal": "Snapshot service",
            "taskType": "snapshot",
            "expectedArtifacts": {
                "file": "src/service.py",
                "contains": [{"type": "function", "name": "serve"}],
            },
        }
        _create_manifest_file(
            manifests_dir, "task-010-snapshot-service.manifest.json", snapshot_data
        )

        # Create deletion manifest that supersedes the snapshot
        delete_manifest = {
            "goal": "Delete service module",
            "taskType": "refactor",
            "supersedes": ["task-010-snapshot-service.manifest.json"],
            "editableFiles": ["src/service.py"],
            "expectedArtifacts": {
                "file": "src/service.py",
                "status": "absent",
                "contains": [],
            },
        }

        # Should NOT raise - valid delete supersession
        validate_supersession(delete_manifest, manifests_dir)

    def test_rename_operation_superseding_old_path(self, tmp_path):
        """Rename manifest can supersede manifests for the old file path."""
        manifests_dir = tmp_path / "manifests"
        manifests_dir.mkdir()

        # Create manifest for old file location
        old_manifest = {
            "goal": "Create old service",
            "taskType": "create",
            "creatableFiles": ["src/old_service.py"],
            "expectedArtifacts": {
                "file": "src/old_service.py",
                "contains": [{"type": "function", "name": "serve"}],
            },
        }
        _create_manifest_file(
            manifests_dir, "task-010-create-old-service.manifest.json", old_manifest
        )

        # Create rename manifest that supersedes old location
        rename_manifest = {
            "goal": "Rename old_service to new_service",
            "taskType": "refactor",
            "supersedes": ["task-010-create-old-service.manifest.json"],
            "creatableFiles": ["src/new_service.py"],
            "editableFiles": ["src/old_service.py"],
            "expectedArtifacts": {
                "file": "src/new_service.py",
                "contains": [{"type": "function", "name": "serve"}],
            },
        }

        # Should NOT raise - valid rename supersession
        validate_supersession(rename_manifest, manifests_dir)

    def test_snapshot_edit_superseding_only_snapshots(self, tmp_path):
        """Edit manifest can supersede snapshot manifests for the same file."""
        manifests_dir = tmp_path / "manifests"
        manifests_dir.mkdir()

        # Create snapshot manifest
        snapshot_data = {
            "goal": "Snapshot service",
            "taskType": "snapshot",
            "expectedArtifacts": {
                "file": "src/service.py",
                "contains": [{"type": "function", "name": "serve"}],
            },
        }
        _create_manifest_file(
            manifests_dir, "task-010-snapshot-service.manifest.json", snapshot_data
        )

        # Create edit manifest that supersedes the snapshot
        edit_manifest = {
            "goal": "Refactor service to add logging",
            "taskType": "edit",
            "supersedes": ["task-010-snapshot-service.manifest.json"],
            "editableFiles": ["src/service.py"],
            "expectedArtifacts": {
                "file": "src/service.py",
                "contains": [
                    {"type": "function", "name": "serve"},
                    {"type": "function", "name": "log_request"},
                ],
            },
        }

        # Should NOT raise - valid snapshot-to-edit transition
        validate_supersession(edit_manifest, manifests_dir)

    def test_no_supersession_empty_array(self, tmp_path):
        """Manifest with empty supersedes array is trivially valid."""
        manifests_dir = tmp_path / "manifests"
        manifests_dir.mkdir()

        # Manifest with no supersession
        manifest = {
            "goal": "Create new service",
            "taskType": "create",
            "supersedes": [],
            "creatableFiles": ["src/service.py"],
            "expectedArtifacts": {
                "file": "src/service.py",
                "contains": [{"type": "function", "name": "serve"}],
            },
        }

        # Should NOT raise - no supersession to validate
        validate_supersession(manifest, manifests_dir)

    def test_no_supersedes_field(self, tmp_path):
        """Manifest without supersedes field is trivially valid."""
        manifests_dir = tmp_path / "manifests"
        manifests_dir.mkdir()

        manifest = {
            "goal": "Create new service",
            "taskType": "create",
            "creatableFiles": ["src/service.py"],
            "expectedArtifacts": {
                "file": "src/service.py",
                "contains": [{"type": "function", "name": "serve"}],
            },
        }

        # Should NOT raise - no supersedes means no supersession validation needed
        validate_supersession(manifest, manifests_dir)

    def test_delete_superseding_multiple_manifests_same_file(self, tmp_path):
        """Delete can supersede multiple manifests as long as all reference same file."""
        manifests_dir = tmp_path / "manifests"
        manifests_dir.mkdir()

        # Create snapshot
        snapshot_data = {
            "goal": "Snapshot service",
            "taskType": "snapshot",
            "expectedArtifacts": {"file": "src/service.py", "contains": []},
        }
        _create_manifest_file(
            manifests_dir, "task-010-snapshot.manifest.json", snapshot_data
        )

        # Create edit that superseded the snapshot
        edit_data = {
            "goal": "Edit service",
            "taskType": "edit",
            "supersedes": ["task-010-snapshot.manifest.json"],
            "editableFiles": ["src/service.py"],
            "expectedArtifacts": {
                "file": "src/service.py",
                "contains": [{"type": "function", "name": "serve"}],
            },
        }
        _create_manifest_file(manifests_dir, "task-015-edit.manifest.json", edit_data)

        # Delete manifest superseding the edit
        delete_manifest = {
            "goal": "Delete service",
            "taskType": "refactor",
            "supersedes": ["task-015-edit.manifest.json"],
            "editableFiles": ["src/service.py"],
            "expectedArtifacts": {
                "file": "src/service.py",
                "status": "absent",
                "contains": [],
            },
        }

        # Should NOT raise - valid delete supersession
        validate_supersession(delete_manifest, manifests_dir)


class TestValidateSupersessionInvalidCases:
    """Tests for invalid supersession patterns that should raise errors."""

    def test_unrelated_file_supersession(self, tmp_path):
        """Superseding a manifest for a completely different file should fail."""
        manifests_dir = tmp_path / "manifests"
        manifests_dir.mkdir()

        # Create manifest for a different file
        other_manifest = {
            "goal": "Create other module",
            "taskType": "create",
            "creatableFiles": ["src/other.py"],
            "expectedArtifacts": {
                "file": "src/other.py",
                "contains": [{"type": "function", "name": "other_func"}],
            },
        }
        _create_manifest_file(
            manifests_dir, "task-010-create-other.manifest.json", other_manifest
        )

        # Create manifest that tries to supersede unrelated file
        invalid_manifest = {
            "goal": "Create service",
            "taskType": "create",
            "supersedes": ["task-010-create-other.manifest.json"],
            "creatableFiles": ["src/service.py"],
            "expectedArtifacts": {
                "file": "src/service.py",
                "contains": [{"type": "function", "name": "serve"}],
            },
        }

        with pytest.raises(ManifestSemanticError) as exc_info:
            validate_supersession(invalid_manifest, manifests_dir)

        error_msg = str(exc_info.value)
        assert "src/other.py" in error_msg or "unrelated" in error_msg.lower()

    def test_non_snapshot_consolidation(self, tmp_path):
        """Edit manifest superseding another edit (not snapshot) should fail."""
        manifests_dir = tmp_path / "manifests"
        manifests_dir.mkdir()

        # Create first edit manifest
        edit1_data = {
            "goal": "First edit",
            "taskType": "edit",
            "editableFiles": ["src/service.py"],
            "expectedArtifacts": {
                "file": "src/service.py",
                "contains": [{"type": "function", "name": "serve"}],
            },
        }
        _create_manifest_file(
            manifests_dir, "task-010-edit-service.manifest.json", edit1_data
        )

        # Create second edit that tries to supersede the first
        edit2_data = {
            "goal": "Second edit superseding first",
            "taskType": "edit",
            "supersedes": ["task-010-edit-service.manifest.json"],
            "editableFiles": ["src/service.py"],
            "expectedArtifacts": {
                "file": "src/service.py",
                "contains": [{"type": "function", "name": "serve_v2"}],
            },
        }

        with pytest.raises(ManifestSemanticError) as exc_info:
            validate_supersession(edit2_data, manifests_dir)

        error_msg = str(exc_info.value)
        assert "snapshot" in error_msg.lower() or "edit" in error_msg.lower()

    def test_delete_without_status_absent(self, tmp_path):
        """Superseding all manifests for a file without status:absent is suspicious."""
        manifests_dir = tmp_path / "manifests"
        manifests_dir.mkdir()

        # Create an edit manifest for target file (not snapshot/create)
        original_data = {
            "goal": "Edit service",
            "taskType": "edit",
            "editableFiles": ["src/service.py"],
            "expectedArtifacts": {
                "file": "src/service.py",
                "contains": [{"type": "function", "name": "serve"}],
            },
        }
        _create_manifest_file(
            manifests_dir, "task-010-edit-service.manifest.json", original_data
        )

        # Create manifest that supersedes the edit without proper delete pattern
        # This is consolidation abuse - edit superseding edit
        suspicious_manifest = {
            "goal": "Remove service functionality",
            "taskType": "refactor",
            "supersedes": ["task-010-edit-service.manifest.json"],
            "editableFiles": ["src/service.py"],
            "expectedArtifacts": {
                "file": "src/service.py",
                "contains": [],  # Empty but no status: absent
            },
        }

        # This should raise because it's consolidation (edit/refactor superseding edit)
        with pytest.raises(ManifestSemanticError) as exc_info:
            validate_supersession(suspicious_manifest, manifests_dir)

        error_msg = str(exc_info.value)
        assert "consolidation" in error_msg.lower() or "edit" in error_msg.lower()

    def test_rename_target_mismatch(self, tmp_path):
        """Rename superseding manifests for wrong file should fail."""
        manifests_dir = tmp_path / "manifests"
        manifests_dir.mkdir()

        # Create manifest for one file
        file_a_manifest = {
            "goal": "Create file A",
            "taskType": "create",
            "creatableFiles": ["src/file_a.py"],
            "expectedArtifacts": {
                "file": "src/file_a.py",
                "contains": [{"type": "function", "name": "func_a"}],
            },
        }
        _create_manifest_file(
            manifests_dir, "task-010-create-file-a.manifest.json", file_a_manifest
        )

        # Create manifest for a different file
        file_b_manifest = {
            "goal": "Create file B",
            "taskType": "create",
            "creatableFiles": ["src/file_b.py"],
            "expectedArtifacts": {
                "file": "src/file_b.py",
                "contains": [{"type": "function", "name": "func_b"}],
            },
        }
        _create_manifest_file(
            manifests_dir, "task-011-create-file-b.manifest.json", file_b_manifest
        )

        # Create a rename that claims to rename file_a to file_c
        # but supersedes file_b's manifest (wrong file!)
        invalid_rename = {
            "goal": "Rename file A to file C",
            "taskType": "refactor",
            "supersedes": ["task-011-create-file-b.manifest.json"],  # Wrong!
            "creatableFiles": ["src/file_c.py"],
            "editableFiles": ["src/file_a.py"],
            "expectedArtifacts": {
                "file": "src/file_c.py",
                "contains": [{"type": "function", "name": "func_a"}],
            },
        }

        with pytest.raises(ManifestSemanticError) as exc_info:
            validate_supersession(invalid_rename, manifests_dir)

        error_msg = str(exc_info.value)
        assert "file_b" in error_msg.lower() or "mismatch" in error_msg.lower()


class TestGetSupersededManifestFiles:
    """Tests for _get_superseded_manifest_files helper function."""

    def test_loads_superseded_manifest_contents(self, tmp_path):
        """Should load both path and content of superseded manifests."""
        manifests_dir = tmp_path / "manifests"
        manifests_dir.mkdir()

        # Create a manifest to be superseded
        target_data = {
            "goal": "Original service",
            "taskType": "create",
            "expectedArtifacts": {
                "file": "src/service.py",
                "contains": [{"type": "function", "name": "serve"}],
            },
        }
        _create_manifest_file(
            manifests_dir, "task-010-create-service.manifest.json", target_data
        )

        manifest = {
            "goal": "Edit service",
            "supersedes": ["task-010-create-service.manifest.json"],
        }

        result = _get_superseded_manifest_files(manifest, manifests_dir)

        assert len(result) == 1
        path, content = result[0]
        assert "task-010-create-service.manifest.json" in path
        assert content["goal"] == "Original service"
        assert content["expectedArtifacts"]["file"] == "src/service.py"

    def test_returns_empty_for_no_supersedes(self, tmp_path):
        """Should return empty list when no supersedes field."""
        manifests_dir = tmp_path / "manifests"
        manifests_dir.mkdir()

        manifest = {"goal": "New manifest"}

        result = _get_superseded_manifest_files(manifest, manifests_dir)

        assert result == []

    def test_returns_empty_for_empty_supersedes(self, tmp_path):
        """Should return empty list when supersedes is empty array."""
        manifests_dir = tmp_path / "manifests"
        manifests_dir.mkdir()

        manifest = {"goal": "New manifest", "supersedes": []}

        result = _get_superseded_manifest_files(manifest, manifests_dir)

        assert result == []

    def test_loads_multiple_superseded_manifests(self, tmp_path):
        """Should load all superseded manifest contents."""
        manifests_dir = tmp_path / "manifests"
        manifests_dir.mkdir()

        # Create multiple manifests
        for i in range(3):
            data = {
                "goal": f"Manifest {i}",
                "taskType": "snapshot",
                "expectedArtifacts": {"file": f"src/file_{i}.py", "contains": []},
            }
            _create_manifest_file(manifests_dir, f"task-00{i}-file.manifest.json", data)

        manifest = {
            "goal": "Superseding manifest",
            "supersedes": [
                "task-000-file.manifest.json",
                "task-001-file.manifest.json",
                "task-002-file.manifest.json",
            ],
        }

        result = _get_superseded_manifest_files(manifest, manifests_dir)

        assert len(result) == 3
        goals = [content["goal"] for _, content in result]
        assert "Manifest 0" in goals
        assert "Manifest 1" in goals
        assert "Manifest 2" in goals


class TestValidateDeleteSupersession:
    """Tests for _validate_delete_supersession helper function."""

    def test_accepts_delete_superseding_same_file_manifests(self, tmp_path):
        """Delete manifest can supersede manifests that all reference the deleted file."""
        manifests_dir = tmp_path / "manifests"
        manifests_dir.mkdir()

        delete_manifest = {
            "goal": "Delete service",
            "taskType": "refactor",
            "expectedArtifacts": {
                "file": "src/service.py",
                "status": "absent",
                "contains": [],
            },
        }

        superseded = [
            (
                "task-010.manifest.json",
                {
                    "taskType": "snapshot",
                    "expectedArtifacts": {"file": "src/service.py", "contains": []},
                },
            ),
            (
                "task-015.manifest.json",
                {
                    "taskType": "edit",
                    "expectedArtifacts": {"file": "src/service.py", "contains": []},
                },
            ),
        ]

        # Should NOT raise - all superseded manifests reference the deleted file
        _validate_delete_supersession(delete_manifest, superseded)

    def test_rejects_delete_superseding_unrelated_file(self, tmp_path):
        """Delete manifest cannot supersede manifests for different files."""
        delete_manifest = {
            "goal": "Delete service",
            "taskType": "refactor",
            "expectedArtifacts": {
                "file": "src/service.py",
                "status": "absent",
                "contains": [],
            },
        }

        superseded = [
            (
                "task-010.manifest.json",
                {
                    "taskType": "snapshot",
                    "expectedArtifacts": {
                        "file": "src/other.py",  # Different file!
                        "contains": [],
                    },
                },
            ),
        ]

        with pytest.raises(ManifestSemanticError) as exc_info:
            _validate_delete_supersession(delete_manifest, superseded)

        assert "src/other.py" in str(exc_info.value)


class TestValidateRenameSupersession:
    """Tests for _validate_rename_supersession helper function."""

    def test_accepts_rename_with_old_file_in_editable(self, tmp_path):
        """Rename can supersede manifests for the old file if old file is in editableFiles."""
        rename_manifest = {
            "goal": "Rename old to new",
            "taskType": "refactor",
            "editableFiles": ["src/old_service.py"],
            "creatableFiles": ["src/new_service.py"],
            "expectedArtifacts": {
                "file": "src/new_service.py",
                "contains": [{"type": "function", "name": "serve"}],
            },
        }

        superseded = [
            (
                "task-010.manifest.json",
                {
                    "taskType": "create",
                    "expectedArtifacts": {
                        "file": "src/old_service.py",
                        "contains": [],
                    },
                },
            ),
        ]

        # Should NOT raise - superseded manifest is for old file location
        _validate_rename_supersession(rename_manifest, superseded)

    def test_rejects_rename_superseding_wrong_old_file(self, tmp_path):
        """Rename cannot supersede manifests for files not being renamed."""
        rename_manifest = {
            "goal": "Rename old to new",
            "taskType": "refactor",
            "editableFiles": ["src/old_service.py"],
            "creatableFiles": ["src/new_service.py"],
            "expectedArtifacts": {
                "file": "src/new_service.py",
                "contains": [],
            },
        }

        superseded = [
            (
                "task-010.manifest.json",
                {
                    "taskType": "create",
                    "expectedArtifacts": {
                        "file": "src/unrelated.py",  # Not the old file!
                        "contains": [],
                    },
                },
            ),
        ]

        with pytest.raises(ManifestSemanticError) as exc_info:
            _validate_rename_supersession(rename_manifest, superseded)

        assert "unrelated" in str(exc_info.value).lower()


class TestValidateSnapshotEditSupersession:
    """Tests for _validate_snapshot_edit_supersession helper function."""

    def test_accepts_edit_superseding_snapshot_same_file(self, tmp_path):
        """Edit manifest can supersede snapshot manifests for the same file."""
        edit_manifest = {
            "goal": "Edit service",
            "taskType": "edit",
            "editableFiles": ["src/service.py"],
            "expectedArtifacts": {
                "file": "src/service.py",
                "contains": [{"type": "function", "name": "serve"}],
            },
        }

        superseded = [
            (
                "task-010.manifest.json",
                {
                    "taskType": "snapshot",
                    "expectedArtifacts": {"file": "src/service.py", "contains": []},
                },
            ),
        ]

        # Should NOT raise - valid snapshot-to-edit transition
        _validate_snapshot_edit_supersession(edit_manifest, superseded)

    def test_rejects_edit_superseding_non_snapshot(self, tmp_path):
        """Edit manifest cannot supersede other edit/create manifests."""
        edit_manifest = {
            "goal": "Edit service again",
            "taskType": "edit",
            "editableFiles": ["src/service.py"],
            "expectedArtifacts": {
                "file": "src/service.py",
                "contains": [],
            },
        }

        superseded = [
            (
                "task-010.manifest.json",
                {
                    "taskType": "edit",  # Not a snapshot!
                    "expectedArtifacts": {"file": "src/service.py", "contains": []},
                },
            ),
        ]

        with pytest.raises(ManifestSemanticError) as exc_info:
            _validate_snapshot_edit_supersession(edit_manifest, superseded)

        error_msg = str(exc_info.value).lower()
        assert "snapshot" in error_msg or "edit" in error_msg

    def test_rejects_edit_superseding_snapshot_different_file(self, tmp_path):
        """Edit manifest cannot supersede snapshot for a different file."""
        edit_manifest = {
            "goal": "Edit service",
            "taskType": "edit",
            "editableFiles": ["src/service.py"],
            "expectedArtifacts": {
                "file": "src/service.py",
                "contains": [],
            },
        }

        superseded = [
            (
                "task-010.manifest.json",
                {
                    "taskType": "snapshot",
                    "expectedArtifacts": {
                        "file": "src/other.py",  # Different file!
                        "contains": [],
                    },
                },
            ),
        ]

        with pytest.raises(ManifestSemanticError) as exc_info:
            _validate_snapshot_edit_supersession(edit_manifest, superseded)

        assert "other.py" in str(exc_info.value)


class TestValidateSupersessionEdgeCases:
    """Edge cases and error handling for supersession validation."""

    def test_handles_missing_superseded_manifest_file(self, tmp_path):
        """Should handle gracefully when superseded manifest file doesn't exist."""
        manifests_dir = tmp_path / "manifests"
        manifests_dir.mkdir()

        manifest = {
            "goal": "Edit service",
            "supersedes": ["task-999-nonexistent.manifest.json"],
            "expectedArtifacts": {"file": "src/service.py", "contains": []},
        }

        # Should either skip the missing file or raise informative error
        # The implementation will determine the exact behavior
        try:
            validate_supersession(manifest, manifests_dir)
        except (ManifestSemanticError, FileNotFoundError) as e:
            # Acceptable to raise an error for missing file
            assert "nonexistent" in str(e).lower() or "not found" in str(e).lower()

    def test_handles_manifest_without_expected_artifacts(self, tmp_path):
        """Should handle superseded manifests that have no expectedArtifacts."""
        manifests_dir = tmp_path / "manifests"
        manifests_dir.mkdir()

        # Create manifest without expectedArtifacts
        minimal_manifest = {
            "goal": "Minimal manifest",
            "taskType": "snapshot",
        }
        _create_manifest_file(
            manifests_dir, "task-010-minimal.manifest.json", minimal_manifest
        )

        superseding_manifest = {
            "goal": "Supersede minimal",
            "taskType": "edit",
            "supersedes": ["task-010-minimal.manifest.json"],
            "expectedArtifacts": {"file": "src/service.py", "contains": []},
        }

        # Should handle gracefully - either accept or give clear error
        try:
            validate_supersession(superseding_manifest, manifests_dir)
        except ManifestSemanticError:
            pass  # Acceptable to reject if file can't be determined

    def test_handles_system_manifests_gracefully(self, tmp_path):
        """System manifests with systemArtifacts should be handled."""
        manifests_dir = tmp_path / "manifests"
        manifests_dir.mkdir()

        # Create a system manifest
        system_manifest = {
            "goal": "System snapshot",
            "taskType": "system-snapshot",
            "systemArtifacts": [
                {"file": "src/a.py", "contains": []},
                {"file": "src/b.py", "contains": []},
            ],
        }
        _create_manifest_file(
            manifests_dir, "task-010-system.manifest.json", system_manifest
        )

        # Manifest superseding system manifest
        superseding_manifest = {
            "goal": "Supersede system manifest",
            "taskType": "edit",
            "supersedes": ["task-010-system.manifest.json"],
            "editableFiles": ["src/a.py"],
            "expectedArtifacts": {"file": "src/a.py", "contains": []},
        }

        # Should handle system manifests appropriately
        # (either accept or give clear error about system manifest handling)
        try:
            validate_supersession(superseding_manifest, manifests_dir)
        except ManifestSemanticError:
            pass  # Acceptable behavior

    def test_create_manifest_superseding_snapshot_is_valid(self, tmp_path):
        """Create manifest can supersede a snapshot if transitioning."""
        manifests_dir = tmp_path / "manifests"
        manifests_dir.mkdir()

        # Create snapshot for existing file
        snapshot_data = {
            "goal": "Snapshot existing code",
            "taskType": "snapshot",
            "expectedArtifacts": {
                "file": "src/service.py",
                "contains": [{"type": "function", "name": "old_func"}],
            },
        }
        _create_manifest_file(
            manifests_dir, "task-010-snapshot.manifest.json", snapshot_data
        )

        # Create manifest that supersedes snapshot (rewriting file)
        create_manifest = {
            "goal": "Rewrite service module",
            "taskType": "create",
            "supersedes": ["task-010-snapshot.manifest.json"],
            "creatableFiles": ["src/service.py"],
            "expectedArtifacts": {
                "file": "src/service.py",
                "contains": [{"type": "function", "name": "new_func"}],
            },
        }

        # Should accept - valid transition from snapshot to complete rewrite
        validate_supersession(create_manifest, manifests_dir)


class TestValidateSupersessionIntegration:
    """Integration tests for the complete validation flow."""

    def test_complete_lifecycle_create_edit_delete(self, tmp_path):
        """Test complete file lifecycle: create -> edit -> delete."""
        manifests_dir = tmp_path / "manifests"
        manifests_dir.mkdir()

        # 1. Create manifest
        create_data = {
            "goal": "Create service",
            "taskType": "create",
            "creatableFiles": ["src/service.py"],
            "expectedArtifacts": {
                "file": "src/service.py",
                "contains": [{"type": "function", "name": "serve"}],
            },
        }
        _create_manifest_file(
            manifests_dir, "task-001-create.manifest.json", create_data
        )

        # Validate create (no supersession)
        validate_supersession(create_data, manifests_dir)

        # 2. Edit manifest superseding nothing
        edit_data = {
            "goal": "Add logging",
            "taskType": "edit",
            "supersedes": [],
            "editableFiles": ["src/service.py"],
            "expectedArtifacts": {
                "file": "src/service.py",
                "contains": [
                    {"type": "function", "name": "serve"},
                    {"type": "function", "name": "log"},
                ],
            },
        }
        _create_manifest_file(manifests_dir, "task-002-edit.manifest.json", edit_data)

        # Validate edit
        validate_supersession(edit_data, manifests_dir)

        # 3. Delete manifest superseding both
        delete_data = {
            "goal": "Remove deprecated service",
            "taskType": "refactor",
            "supersedes": [
                "task-001-create.manifest.json",
                "task-002-edit.manifest.json",
            ],
            "editableFiles": ["src/service.py"],
            "expectedArtifacts": {
                "file": "src/service.py",
                "status": "absent",
                "contains": [],
            },
        }

        # Validate delete
        validate_supersession(delete_data, manifests_dir)

    def test_validates_supersession_chain_ordering(self, tmp_path):
        """Validate that supersession respects proper chain ordering."""
        manifests_dir = tmp_path / "manifests"
        manifests_dir.mkdir()

        # Create original
        original = {
            "goal": "Original",
            "taskType": "snapshot",
            "expectedArtifacts": {"file": "src/service.py", "contains": []},
        }
        _create_manifest_file(manifests_dir, "task-001-original.manifest.json", original)

        # First edit supersedes original snapshot
        edit1 = {
            "goal": "First edit",
            "taskType": "edit",
            "supersedes": ["task-001-original.manifest.json"],
            "expectedArtifacts": {
                "file": "src/service.py",
                "contains": [{"type": "function", "name": "func1"}],
            },
        }
        validate_supersession(edit1, manifests_dir)
        _create_manifest_file(manifests_dir, "task-002-edit1.manifest.json", edit1)

        # Second edit should NOT supersede first edit (would be consolidation abuse)
        edit2 = {
            "goal": "Second edit",
            "taskType": "edit",
            "supersedes": ["task-002-edit1.manifest.json"],  # Invalid!
            "expectedArtifacts": {
                "file": "src/service.py",
                "contains": [{"type": "function", "name": "func2"}],
            },
        }

        with pytest.raises(ManifestSemanticError):
            validate_supersession(edit2, manifests_dir)
