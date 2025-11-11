"""Behavioral tests for Task 020: Refactoring get_superseded_manifests() to utils.py"""

import json
from pathlib import Path


def test_get_superseded_manifests_in_utils():
    """Test that get_superseded_manifests() is importable from maid_runner.utils."""
    from maid_runner.utils import get_superseded_manifests

    # Verify function is importable
    assert callable(get_superseded_manifests)


def test_get_superseded_manifests_returns_set(tmp_path: Path):
    """Test that get_superseded_manifests() returns a set."""
    from maid_runner.utils import get_superseded_manifests

    # Create a manifests directory
    manifests_dir = tmp_path / "manifests"
    manifests_dir.mkdir()

    # Create a simple manifest (not superseded)
    manifest = {"goal": "test", "taskType": "edit"}
    manifest_file = manifests_dir / "task-001.manifest.json"
    manifest_file.write_text(json.dumps(manifest))

    # Call function
    result = get_superseded_manifests(manifests_dir)

    # Verify it returns a set
    assert isinstance(result, set)


def test_get_superseded_manifests_finds_superseded(tmp_path: Path):
    """Test that get_superseded_manifests() correctly identifies superseded manifests."""
    from maid_runner.utils import get_superseded_manifests

    # Create manifests directory
    manifests_dir = tmp_path / "manifests"
    manifests_dir.mkdir()

    # Create regular manifests
    manifest1 = {"goal": "task 1", "taskType": "edit"}
    manifest1_file = manifests_dir / "task-001.manifest.json"
    manifest1_file.write_text(json.dumps(manifest1))

    manifest2 = {"goal": "task 2", "taskType": "edit"}
    manifest2_file = manifests_dir / "task-002.manifest.json"
    manifest2_file.write_text(json.dumps(manifest2))

    # Create snapshot that supersedes task-001
    snapshot = {
        "goal": "snapshot",
        "taskType": "snapshot",
        "supersedes": ["manifests/task-001.manifest.json"],
    }
    snapshot_file = manifests_dir / "task-003-snapshot-v1.manifest.json"
    snapshot_file.write_text(json.dumps(snapshot))

    # Call function
    result = get_superseded_manifests(manifests_dir)

    # Verify task-001 is identified as superseded
    superseded_names = {p.name for p in result}
    assert "task-001.manifest.json" in superseded_names
    assert "task-002.manifest.json" not in superseded_names


def test_get_superseded_manifests_handles_empty_dir(tmp_path: Path):
    """Test that get_superseded_manifests() handles empty directory gracefully."""
    from maid_runner.utils import get_superseded_manifests

    # Create empty manifests directory
    manifests_dir = tmp_path / "manifests"
    manifests_dir.mkdir()

    # Call function
    result = get_superseded_manifests(manifests_dir)

    # Should return empty set
    assert result == set()


def test_get_superseded_manifests_handles_no_supersedes(tmp_path: Path):
    """Test that get_superseded_manifests() handles manifests without supersedes field."""
    from maid_runner.utils import get_superseded_manifests

    # Create manifests directory
    manifests_dir = tmp_path / "manifests"
    manifests_dir.mkdir()

    # Create snapshot without supersedes field
    snapshot = {"goal": "snapshot", "taskType": "snapshot"}
    snapshot_file = manifests_dir / "task-001-snapshot-v1.manifest.json"
    snapshot_file.write_text(json.dumps(snapshot))

    # Call function
    result = get_superseded_manifests(manifests_dir)

    # Should return empty set
    assert result == set()


def test_run_manifest_validation_commands_script_uses_utils_import(tmp_path: Path):
    """Test that run_manifest_validation_commands.py imports from utils correctly."""
    # Read the script
    script_path = Path("scripts/run_manifest_validation_commands.py")
    script_content = script_path.read_text()

    # Verify it imports from maid_runner.utils (not the hacky importlib way)
    assert "from maid_runner.utils import get_superseded_manifests" in script_content

    # Verify it doesn't use the old importlib.util pattern
    assert "importlib.util.spec_from_file_location" not in script_content
    assert 'spec_from_file_location("get_superseded_manifests"' not in script_content
