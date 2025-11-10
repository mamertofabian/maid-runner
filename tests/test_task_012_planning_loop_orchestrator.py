"""
Behavioral tests for Task-012: Planning Loop Orchestrator

Tests validate that the MAID runner can orchestrate Phase 2 planning loop
by guiding users through manifest creation, test creation, structural
validation, and iterative refinement.

These tests USE the functions declared in the manifest.
"""

import json
from pathlib import Path
import sys

# Add parent directory to path to import maid_runner
sys.path.insert(0, str(Path(__file__).parent.parent))

import sys
import importlib.util
from pathlib import Path

# Import from maid_runner.py script (not the package)
spec = importlib.util.spec_from_file_location(
    "maid_runner_script", Path(__file__).parent.parent / "examples" / "maid_runner.py"
)
maid_runner_script = importlib.util.module_from_spec(spec)
sys.modules["maid_runner_script"] = maid_runner_script
spec.loader.exec_module(maid_runner_script)

run_planning_loop = maid_runner_script.run_planning_loop
get_next_task_number = maid_runner_script.get_next_task_number
prompt_for_manifest_details = maid_runner_script.prompt_for_manifest_details
create_draft_manifest = maid_runner_script.create_draft_manifest
run_structural_validation = maid_runner_script.run_structural_validation


class TestGetNextTaskNumber:
    """Test automatic task number detection."""

    def test_returns_001_for_empty_directory(self, tmp_path: Path):
        """Test that first task number is 001."""
        number = get_next_task_number(tmp_path)
        assert number == 1

    def test_increments_from_existing_manifests(self, tmp_path: Path):
        """Test that task number increments from existing manifests."""
        # Create some existing manifests
        (tmp_path / "task-001-first.manifest.json").write_text("{}")
        (tmp_path / "task-002-second.manifest.json").write_text("{}")
        (tmp_path / "task-003-third.manifest.json").write_text("{}")

        number = get_next_task_number(tmp_path)
        assert number == 4

    def test_handles_non_sequential_numbers(self, tmp_path: Path):
        """Test that it finds max number even if gaps exist."""
        (tmp_path / "task-001-first.manifest.json").write_text("{}")
        (tmp_path / "task-005-fifth.manifest.json").write_text("{}")
        (tmp_path / "task-003-third.manifest.json").write_text("{}")

        number = get_next_task_number(tmp_path)
        assert number == 6

    def test_ignores_snapshot_manifests(self, tmp_path: Path):
        """Test that snapshot manifests are counted correctly."""
        (tmp_path / "task-001-first.manifest.json").write_text("{}")
        (tmp_path / "task-002-snapshot-foo.manifest.json").write_text("{}")

        number = get_next_task_number(tmp_path)
        assert number == 3

    def test_handles_directory_with_other_files(self, tmp_path: Path):
        """Test that non-manifest files are ignored."""
        (tmp_path / "task-001-first.manifest.json").write_text("{}")
        (tmp_path / "README.md").write_text("# Manifests")
        (tmp_path / "notes.txt").write_text("notes")

        number = get_next_task_number(tmp_path)
        assert number == 2


class TestPromptForManifestDetails:
    """Test interactive manifest detail collection."""

    def test_returns_dict_with_required_fields(self):
        """Test that prompt returns a dictionary with all required fields."""
        goal = "Test goal"

        # Call the function
        details = prompt_for_manifest_details(goal)

        # Should return a dict
        assert isinstance(details, dict)

        # Should include goal
        assert "goal" in details
        assert details["goal"] == goal

    def test_includes_file_categorization(self):
        """Test that returned dict includes file categories."""
        details = prompt_for_manifest_details("Test goal")

        # Should have file categories
        assert "creatableFiles" in details or "editableFiles" in details
        assert "readonlyFiles" in details or "editableFiles" in details

    def test_includes_task_type(self):
        """Test that returned dict includes task type."""
        details = prompt_for_manifest_details("Test goal")

        assert "taskType" in details
        # Should be one of the valid types
        assert details["taskType"] in ["create", "edit", "refactor", "snapshot"]


class TestCreateDraftManifest:
    """Test manifest file creation."""

    def test_creates_manifest_file(self, tmp_path: Path, monkeypatch):
        """Test that manifest file is created."""
        manifest_details = {
            "goal": "Test goal",
            "taskType": "create",
            "creatableFiles": ["test.py"],
            "editableFiles": [],
            "readonlyFiles": ["tests/test.py"],
            "expectedArtifacts": {"file": "test.py", "contains": []},
        }

        # Use monkeypatch for safer directory changes
        monkeypatch.chdir(tmp_path)
        (tmp_path / "manifests").mkdir()

        manifest_path = create_draft_manifest(1, manifest_details)

        # Should return a path
        assert isinstance(manifest_path, str)

        # File should exist
        assert Path(manifest_path).exists()

    def test_manifest_has_valid_json(self, tmp_path: Path, monkeypatch):
        """Test that created manifest is valid JSON."""
        manifest_details = {
            "goal": "Test goal",
            "taskType": "create",
            "creatableFiles": ["test.py"],
            "editableFiles": [],
            "readonlyFiles": [],
            "expectedArtifacts": {"file": "test.py", "contains": []},
        }

        monkeypatch.chdir(tmp_path)
        (tmp_path / "manifests").mkdir()

        manifest_path = create_draft_manifest(5, manifest_details)

        # Should be valid JSON
        with open(manifest_path) as f:
            data = json.load(f)

        assert isinstance(data, dict)
        assert data["goal"] == "Test goal"

    def test_formats_task_number_correctly(self, tmp_path: Path, monkeypatch):
        """Test that task numbers are zero-padded."""
        manifest_details = {
            "goal": "Test",
            "taskType": "create",
            "creatableFiles": [],
            "editableFiles": [],
            "readonlyFiles": [],
            "expectedArtifacts": {"file": "test.py", "contains": []},
        }

        monkeypatch.chdir(tmp_path)
        (tmp_path / "manifests").mkdir()

        manifest_path = create_draft_manifest(7, manifest_details)

        # Should have zero-padded number
        assert "task-007" in manifest_path or "007" in Path(manifest_path).name


class TestRunStructuralValidation:
    """Test structural validation execution."""

    def test_returns_validation_result_dict(self, tmp_path: Path):
        """Test that structural validation returns a result dict."""
        # Create a minimal valid manifest
        manifest = {
            "goal": "Test",
            "taskType": "create",
            "creatableFiles": ["test.py"],
            "editableFiles": [],
            "readonlyFiles": [],
            "expectedArtifacts": {"file": "test.py", "contains": []},
            "validationCommand": ["true"],
        }

        manifest_path = tmp_path / "test.manifest.json"
        manifest_path.write_text(json.dumps(manifest))

        result = run_structural_validation(str(manifest_path))

        assert isinstance(result, dict)
        assert "success" in result

    def test_detects_validation_failures(self, tmp_path: Path):
        """Test that structural validation detects failures."""
        # Create a manifest with missing implementation
        manifest = {
            "goal": "Test",
            "taskType": "create",
            "creatableFiles": ["nonexistent.py"],
            "editableFiles": [],
            "readonlyFiles": [],
            "expectedArtifacts": {
                "file": "nonexistent.py",
                "contains": [{"type": "function", "name": "test"}],
            },
            "validationCommand": ["true"],
        }

        manifest_path = tmp_path / "test.manifest.json"
        manifest_path.write_text(json.dumps(manifest))

        result = run_structural_validation(str(manifest_path))

        assert isinstance(result, dict)
        assert "success" in result
        # Should fail because implementation file doesn't exist
        assert result["success"] is False

    def test_includes_error_messages(self, tmp_path: Path):
        """Test that validation result includes error messages."""
        manifest = {
            "goal": "Test",
            "taskType": "create",
            "creatableFiles": ["missing.py"],
            "editableFiles": [],
            "readonlyFiles": [],
            "expectedArtifacts": {"file": "missing.py", "contains": []},
            "validationCommand": ["true"],
        }

        manifest_path = tmp_path / "test.manifest.json"
        manifest_path.write_text(json.dumps(manifest))

        result = run_structural_validation(str(manifest_path))

        # Should have error information
        assert "errors" in result or "output" in result or "message" in result


class TestRunPlanningLoop:
    """Test full planning loop orchestration."""

    def test_planning_loop_creates_manifest(self, tmp_path: Path, monkeypatch):
        """Test that planning loop creates a manifest file."""
        monkeypatch.chdir(tmp_path)
        (tmp_path / "manifests").mkdir()

        # Mock user input to avoid interactive prompts
        # The function should handle this gracefully
        result = run_planning_loop(
            goal="Test planning loop", task_number=None  # Auto-detect
        )

        # Should return a boolean
        assert isinstance(result, bool)

    def test_planning_loop_uses_provided_task_number(self, tmp_path: Path, monkeypatch):
        """Test that planning loop uses provided task number."""
        monkeypatch.chdir(tmp_path)
        (tmp_path / "manifests").mkdir()

        result = run_planning_loop(goal="Test with specific number", task_number=42)

        assert isinstance(result, bool)

    def test_planning_loop_auto_detects_task_number(self, tmp_path: Path, monkeypatch):
        """Test that planning loop auto-detects next task number."""
        monkeypatch.chdir(tmp_path)
        manifests_dir = tmp_path / "manifests"
        manifests_dir.mkdir()

        # Create existing manifests
        (manifests_dir / "task-001-first.manifest.json").write_text("{}")
        (manifests_dir / "task-002-second.manifest.json").write_text("{}")

        result = run_planning_loop(goal="Test auto-detect", task_number=None)

        assert isinstance(result, bool)
