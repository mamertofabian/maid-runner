"""
Behavioral tests for Task-080: Fix snapshot --force supersede self bug

Tests validate that when using --force flag with maid snapshot, the generated
manifest does not supersede itself, even when path formats differ (relative vs absolute).
"""

import json
import os
from pathlib import Path


class TestSnapshotForceSupersedeSelf:
    """Test that --force flag doesn't cause manifest to supersede itself."""

    def test_force_flag_does_not_supersede_self(self, tmp_path: Path):
        """Test that using --force to regenerate a snapshot doesn't cause it to supersede itself."""
        from maid_runner.cli.snapshot import generate_snapshot
        from maid_runner.validators.manifest_validator import discover_related_manifests

        code = "def hello(): pass"
        test_file = tmp_path / "test.py"
        test_file.write_text(code)

        manifests_dir = tmp_path / "manifests"
        manifests_dir.mkdir()

        # Change to tmp_path so discover_related_manifests can find manifests
        original_cwd = os.getcwd()
        try:
            os.chdir(tmp_path)

            # Generate first snapshot
            first_path = generate_snapshot(
                str(test_file), str(manifests_dir), force=False, skip_test_stub=True
            )

            # Verify that discover_related_manifests finds the first manifest
            # (This simulates what happens when we regenerate with --force)
            discovered = discover_related_manifests(str(test_file))
            # discover_related_manifests returns relative paths like "manifests/task-XXX.manifest.json"
            first_path_relative = Path(first_path).relative_to(tmp_path)
            assert str(first_path_relative) in discovered or any(
                Path(m).resolve() == Path(first_path).resolve() for m in discovered
            ), f"First manifest should be discoverable. Found: {discovered}, expected: {first_path_relative}"

            # Now simulate the bug scenario: generate a new snapshot that would
            # discover the existing one. The key is that when the new manifest path
            # is calculated, it should filter out any existing manifest that matches
            # its own path (even if path formats differ - relative vs absolute)
            second_path = generate_snapshot(
                str(test_file), str(manifests_dir), force=True, skip_test_stub=True
            )

            # Read second manifest
            with open(second_path, "r") as f:
                second_manifest = json.load(f)

            # The second manifest should NOT supersede itself
            # Convert all paths to resolved absolute paths for comparison
            second_path_resolved = Path(second_path).resolve()
            superseded_paths = []
            for m in second_manifest.get("supersedes", []):
                superseded_path = Path(m)
                if not superseded_path.is_absolute():
                    # Resolve relative to manifests_dir
                    superseded_path = manifests_dir / superseded_path
                superseded_paths.append(superseded_path.resolve())

            assert (
                second_path_resolved not in superseded_paths
            ), f"Manifest should not supersede itself. Found {second_path_resolved} in supersedes: {superseded_paths}"
        finally:
            os.chdir(original_cwd)
