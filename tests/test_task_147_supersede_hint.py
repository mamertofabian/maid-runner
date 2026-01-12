"""Behavioral tests for Task 147: Supersede hint for unexpected artifacts.

These tests verify that the _build_supersede_hint function provides helpful
hints when validation fails due to unexpected artifacts from newer manifests.
"""

import json
from pathlib import Path
from unittest.mock import patch

from maid_runner.cli.validate import _build_supersede_hint


class TestBuildSupersedeHint:
    """Tests for _build_supersede_hint function."""

    def test_returns_none_when_not_snapshot_and_no_newer_manifests(
        self, tmp_path: Path
    ):
        """Returns None when manifest is not a snapshot and has no newer related manifests."""
        manifest_path = tmp_path / "manifests" / "task-001-feature.manifest.json"
        manifest_path.parent.mkdir(parents=True)
        manifest_data = {
            "goal": "Add feature",
            "taskType": "edit",
            "editableFiles": ["src/module.py"],
        }
        manifest_path.write_text(json.dumps(manifest_data))

        result = _build_supersede_hint(
            manifest_path=manifest_path,
            manifest_data=manifest_data,
            target_file="src/module.py",
            error_message="Unexpected public class(es) found: NewClass",
        )

        assert result is None

    def test_returns_hint_when_snapshot_has_newer_manifest_for_same_file(
        self, tmp_path: Path
    ):
        """Returns hint when a snapshot manifest has newer manifests for the same file."""
        manifests_dir = tmp_path / "manifests"
        manifests_dir.mkdir(parents=True)

        # Create snapshot manifest (older)
        snapshot_path = manifests_dir / "task-010-snapshot-module.manifest.json"
        snapshot_data = {
            "goal": "Snapshot module",
            "taskType": "snapshot",
            "creatableFiles": ["src/module.py"],
            "expectedArtifacts": {
                "file": "src/module.py",
                "contains": [{"type": "class", "name": "OldClass"}],
            },
        }
        snapshot_path.write_text(json.dumps(snapshot_data))

        # Create newer edit manifest for the same file
        edit_path = manifests_dir / "task-020-add-feature.manifest.json"
        edit_data = {
            "goal": "Add feature to module",
            "taskType": "edit",
            "editableFiles": ["src/module.py"],
            "expectedArtifacts": {
                "file": "src/module.py",
                "contains": [{"type": "class", "name": "NewClass"}],
            },
        }
        edit_path.write_text(json.dumps(edit_data))

        # Mock discover_related_manifests to return both manifests
        with patch(
            "maid_runner.cli.validate.discover_related_manifests"
        ) as mock_discover:
            mock_discover.return_value = [str(snapshot_path), str(edit_path)]

            result = _build_supersede_hint(
                manifest_path=snapshot_path,
                manifest_data=snapshot_data,
                target_file="src/module.py",
                error_message="Unexpected public class(es) found: NewClass",
            )

        assert result is not None
        assert "task-020-add-feature.manifest.json" in result
        assert "supersedes" in result.lower()

    def test_returns_hint_for_non_snapshot_with_newer_manifest(self, tmp_path: Path):
        """Returns hint when any older manifest has newer manifests for the same file."""
        manifests_dir = tmp_path / "manifests"
        manifests_dir.mkdir(parents=True)

        # Create older edit manifest
        older_path = manifests_dir / "task-010-initial.manifest.json"
        older_data = {
            "goal": "Initial implementation",
            "taskType": "edit",
            "editableFiles": ["src/module.py"],
            "expectedArtifacts": {
                "file": "src/module.py",
                "contains": [{"type": "class", "name": "OldClass"}],
            },
        }
        older_path.write_text(json.dumps(older_data))

        # Create newer edit manifest for the same file
        newer_path = manifests_dir / "task-020-extend.manifest.json"
        newer_data = {
            "goal": "Extend module",
            "taskType": "edit",
            "editableFiles": ["src/module.py"],
            "expectedArtifacts": {
                "file": "src/module.py",
                "contains": [{"type": "class", "name": "NewClass"}],
            },
        }
        newer_path.write_text(json.dumps(newer_data))

        with patch(
            "maid_runner.cli.validate.discover_related_manifests"
        ) as mock_discover:
            mock_discover.return_value = [str(older_path), str(newer_path)]

            result = _build_supersede_hint(
                manifest_path=older_path,
                manifest_data=older_data,
                target_file="src/module.py",
                error_message="Unexpected public class(es) found: NewClass",
            )

        assert result is not None
        assert "task-020-extend.manifest.json" in result

    def test_returns_none_when_error_is_not_unexpected_artifacts(self, tmp_path: Path):
        """Returns None when error message is not about unexpected artifacts."""
        manifests_dir = tmp_path / "manifests"
        manifests_dir.mkdir(parents=True)

        manifest_path = manifests_dir / "task-010-snapshot.manifest.json"
        manifest_data = {
            "goal": "Snapshot",
            "taskType": "snapshot",
            "creatableFiles": ["src/module.py"],
        }
        manifest_path.write_text(json.dumps(manifest_data))

        result = _build_supersede_hint(
            manifest_path=manifest_path,
            manifest_data=manifest_data,
            target_file="src/module.py",
            error_message="Target file not found: src/module.py",
        )

        assert result is None

    def test_returns_none_when_manifest_is_the_newest(self, tmp_path: Path):
        """Returns None when the current manifest is the newest for the file."""
        manifests_dir = tmp_path / "manifests"
        manifests_dir.mkdir(parents=True)

        # Create older manifest
        older_path = manifests_dir / "task-010-snapshot.manifest.json"
        older_data = {"goal": "Snapshot", "taskType": "snapshot"}
        older_path.write_text(json.dumps(older_data))

        # Create newer manifest (the one being validated)
        newer_path = manifests_dir / "task-020-current.manifest.json"
        newer_data = {
            "goal": "Current",
            "taskType": "edit",
            "editableFiles": ["src/module.py"],
        }
        newer_path.write_text(json.dumps(newer_data))

        with patch(
            "maid_runner.cli.validate.discover_related_manifests"
        ) as mock_discover:
            mock_discover.return_value = [str(older_path), str(newer_path)]

            result = _build_supersede_hint(
                manifest_path=newer_path,
                manifest_data=newer_data,
                target_file="src/module.py",
                error_message="Unexpected public class(es) found: SomeClass",
            )

        assert result is None

    def test_hint_mentions_supersedes_field(self, tmp_path: Path):
        """Hint should mention the supersedes field for the fix."""
        manifests_dir = tmp_path / "manifests"
        manifests_dir.mkdir(parents=True)

        snapshot_path = manifests_dir / "task-010-snapshot.manifest.json"
        snapshot_data = {
            "goal": "Snapshot",
            "taskType": "snapshot",
            "creatableFiles": ["src/module.py"],
        }
        snapshot_path.write_text(json.dumps(snapshot_data))

        newer_path = manifests_dir / "task-020-edit.manifest.json"
        newer_data = {"goal": "Edit", "taskType": "edit"}
        newer_path.write_text(json.dumps(newer_data))

        with patch(
            "maid_runner.cli.validate.discover_related_manifests"
        ) as mock_discover:
            mock_discover.return_value = [str(snapshot_path), str(newer_path)]

            result = _build_supersede_hint(
                manifest_path=snapshot_path,
                manifest_data=snapshot_data,
                target_file="src/module.py",
                error_message="Unexpected public class(es) found: NewClass",
            )

        assert result is not None
        assert "supersedes" in result.lower()

    def test_hint_includes_manifest_filename(self, tmp_path: Path):
        """Hint should include the filename of the manifest that should supersede."""
        manifests_dir = tmp_path / "manifests"
        manifests_dir.mkdir(parents=True)

        snapshot_path = manifests_dir / "task-010-snapshot.manifest.json"
        snapshot_data = {
            "goal": "Snapshot",
            "taskType": "snapshot",
            "creatableFiles": ["src/module.py"],
        }
        snapshot_path.write_text(json.dumps(snapshot_data))

        newer_path = manifests_dir / "task-025-new-feature.manifest.json"
        newer_data = {"goal": "New feature", "taskType": "edit"}
        newer_path.write_text(json.dumps(newer_data))

        with patch(
            "maid_runner.cli.validate.discover_related_manifests"
        ) as mock_discover:
            mock_discover.return_value = [str(snapshot_path), str(newer_path)]

            result = _build_supersede_hint(
                manifest_path=snapshot_path,
                manifest_data=snapshot_data,
                target_file="src/module.py",
                error_message="Unexpected public class(es) found: NewClass",
            )

        assert result is not None
        assert "task-025-new-feature.manifest.json" in result

    def test_hint_mentions_redeclaring_artifacts(self, tmp_path: Path):
        """Hint should mention that artifacts need to be redeclared."""
        manifests_dir = tmp_path / "manifests"
        manifests_dir.mkdir(parents=True)

        snapshot_path = manifests_dir / "task-010-snapshot.manifest.json"
        snapshot_data = {
            "goal": "Snapshot",
            "taskType": "snapshot",
            "creatableFiles": ["src/module.py"],
        }
        snapshot_path.write_text(json.dumps(snapshot_data))

        newer_path = manifests_dir / "task-020-edit.manifest.json"
        newer_data = {"goal": "Edit", "taskType": "edit"}
        newer_path.write_text(json.dumps(newer_data))

        with patch(
            "maid_runner.cli.validate.discover_related_manifests"
        ) as mock_discover:
            mock_discover.return_value = [str(snapshot_path), str(newer_path)]

            result = _build_supersede_hint(
                manifest_path=snapshot_path,
                manifest_data=snapshot_data,
                target_file="src/module.py",
                error_message="Unexpected public class(es) found: NewClass",
            )

        assert result is not None
        # Should mention redeclaring artifacts
        assert "redeclare" in result.lower() or "artifacts" in result.lower()
        # Should explain why (superseded manifests excluded from chain)
        assert "excluded" in result.lower() or "chain" in result.lower()
