# tests/cli/test_task_145_skip_superseded_validation.py
"""Behavioral tests for skipping validation of superseded manifests.

When validating a manifest that has been superseded by another manifest,
the validation should return success with an informational warning instead
of running full validation. This prevents false positive errors for inactive
manifests in LSP integration.
"""

import json
from pathlib import Path

from maid_runner.cli.validate import _check_if_superseded


class TestCheckIfSuperseded:
    """Tests for the _check_if_superseded function."""

    def test_returns_true_when_manifest_is_superseded(self, tmp_path: Path):
        """Test that function returns True when manifest is superseded by another."""
        # Create a superseding manifest that supersedes task-001
        superseding_manifest = {
            "goal": "Superseding manifest",
            "taskType": "edit",
            "supersedes": ["manifests/task-001-example.manifest.json"],
            "creatableFiles": [],
            "editableFiles": ["src/example.py"],
            "readonlyFiles": [],
            "expectedArtifacts": {"file": "src/example.py", "contains": []},
        }

        # Create a superseded manifest (task-001)
        superseded_manifest = {
            "goal": "Original manifest",
            "taskType": "create",
            "supersedes": [],
            "creatableFiles": ["src/example.py"],
            "editableFiles": [],
            "readonlyFiles": [],
            "expectedArtifacts": {"file": "src/example.py", "contains": []},
        }

        # Write manifests to temp directory
        manifests_dir = tmp_path / "manifests"
        manifests_dir.mkdir()

        superseded_path = manifests_dir / "task-001-example.manifest.json"
        superseding_path = manifests_dir / "task-002-update.manifest.json"

        superseded_path.write_text(json.dumps(superseded_manifest))
        superseding_path.write_text(json.dumps(superseding_manifest))

        # Check if task-001 is superseded
        is_superseded, superseding_manifest_path = _check_if_superseded(
            superseded_path, manifests_dir
        )

        assert is_superseded is True
        assert superseding_manifest_path is not None
        assert "task-002" in str(superseding_manifest_path)

    def test_returns_false_when_manifest_is_not_superseded(self, tmp_path: Path):
        """Test that function returns False when manifest is NOT superseded."""
        # Create a manifest that is not superseded
        active_manifest = {
            "goal": "Active manifest",
            "taskType": "create",
            "supersedes": [],
            "creatableFiles": ["src/module.py"],
            "editableFiles": [],
            "readonlyFiles": [],
            "expectedArtifacts": {"file": "src/module.py", "contains": []},
        }

        # Write manifest to temp directory
        manifests_dir = tmp_path / "manifests"
        manifests_dir.mkdir()

        manifest_path = manifests_dir / "task-001-module.manifest.json"
        manifest_path.write_text(json.dumps(active_manifest))

        # Check if manifest is superseded
        is_superseded, superseding_manifest_path = _check_if_superseded(
            manifest_path, manifests_dir
        )

        assert is_superseded is False
        assert superseding_manifest_path is None

    def test_handles_transitive_supersession(self, tmp_path: Path):
        """Test detection when manifest is superseded transitively.

        If task-001 is superseded by task-002, and task-002 is superseded by task-003,
        both task-001 and task-002 should be detected as superseded.
        """
        manifests_dir = tmp_path / "manifests"
        manifests_dir.mkdir()

        # task-001: original
        task_001 = {
            "goal": "Original",
            "taskType": "create",
            "supersedes": [],
            "creatableFiles": ["src/a.py"],
            "editableFiles": [],
            "readonlyFiles": [],
            "expectedArtifacts": {"file": "src/a.py", "contains": []},
        }

        # task-002: supersedes task-001
        task_002 = {
            "goal": "First update",
            "taskType": "edit",
            "supersedes": ["manifests/task-001-original.manifest.json"],
            "creatableFiles": [],
            "editableFiles": ["src/a.py"],
            "readonlyFiles": [],
            "expectedArtifacts": {"file": "src/a.py", "contains": []},
        }

        # task-003: supersedes task-002
        task_003 = {
            "goal": "Second update",
            "taskType": "edit",
            "supersedes": ["manifests/task-002-update.manifest.json"],
            "creatableFiles": [],
            "editableFiles": ["src/a.py"],
            "readonlyFiles": [],
            "expectedArtifacts": {"file": "src/a.py", "contains": []},
        }

        (manifests_dir / "task-001-original.manifest.json").write_text(
            json.dumps(task_001)
        )
        (manifests_dir / "task-002-update.manifest.json").write_text(
            json.dumps(task_002)
        )
        (manifests_dir / "task-003-final.manifest.json").write_text(
            json.dumps(task_003)
        )

        # Both task-001 and task-002 should be detected as superseded
        is_superseded_001, _ = _check_if_superseded(
            manifests_dir / "task-001-original.manifest.json", manifests_dir
        )
        is_superseded_002, _ = _check_if_superseded(
            manifests_dir / "task-002-update.manifest.json", manifests_dir
        )
        is_superseded_003, _ = _check_if_superseded(
            manifests_dir / "task-003-final.manifest.json", manifests_dir
        )

        assert is_superseded_001 is True
        assert is_superseded_002 is True
        assert is_superseded_003 is False  # The final one is not superseded


class TestValidationSkipsSupersededManifest:
    """Tests that validation properly skips superseded manifests."""

    def test_json_output_returns_success_for_superseded_manifest(self, tmp_path: Path):
        """Test that JSON output returns success=True for superseded manifest."""
        from maid_runner.cli.validate import _perform_core_validation

        manifests_dir = tmp_path / "manifests"
        manifests_dir.mkdir()

        # Create a superseded manifest
        superseded_manifest = {
            "goal": "Original manifest",
            "taskType": "create",
            "supersedes": [],
            "creatableFiles": ["src/example.py"],
            "editableFiles": [],
            "readonlyFiles": [],
            "expectedArtifacts": {"file": "src/example.py", "contains": []},
        }

        # Create a superseding manifest
        superseding_manifest = {
            "goal": "Superseding manifest",
            "taskType": "edit",
            "supersedes": ["manifests/task-001-example.manifest.json"],
            "creatableFiles": [],
            "editableFiles": ["src/example.py"],
            "readonlyFiles": [],
            "expectedArtifacts": {"file": "src/example.py", "contains": []},
        }

        superseded_path = manifests_dir / "task-001-example.manifest.json"
        superseding_path = manifests_dir / "task-002-update.manifest.json"

        superseded_path.write_text(json.dumps(superseded_manifest))
        superseding_path.write_text(json.dumps(superseding_manifest))

        # Validate the superseded manifest - should return success
        result = _perform_core_validation(
            str(superseded_path),
            validation_mode="implementation",
            use_manifest_chain=False,
            use_cache=False,
        )

        # Should succeed (not an error to validate a superseded manifest)
        assert result.success is True

        # Should have informational warning about being superseded
        assert len(result.warnings) >= 1
        warning_messages = [w.message for w in result.warnings]
        assert any("superseded" in msg.lower() for msg in warning_messages)

        # Metadata should indicate superseded status
        assert result.metadata.get("is_superseded") is True
