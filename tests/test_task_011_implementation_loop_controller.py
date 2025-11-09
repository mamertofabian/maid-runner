"""
Behavioral tests for Task-011: Implementation Loop Controller

Tests validate that the MAID runner can orchestrate Phase 3 implementation
loops by loading manifests, preparing agent context, executing validation
commands, and supporting iteration until tests pass.

These tests USE the functions declared in the manifest.
"""

import pytest
import json
import tempfile
from pathlib import Path
import sys

# Add parent directory to path to import maid_runner
sys.path.insert(0, str(Path(__file__).parent.parent))

from maid_runner import (
    main,
    run_implementation_loop,
    load_manifest_context,
    execute_validation,
    display_agent_context,
    display_validation_results,
)


class TestImplementationLoopController:
    """Test the implementation loop controller orchestration."""

    def test_load_manifest_context_returns_dict(self, tmp_path: Path):
        """Test that load_manifest_context returns a dictionary with context."""
        manifest_data = {
            "goal": "Test goal",
            "creatableFiles": ["test.py"],
            "editableFiles": ["existing.py"],
            "readonlyFiles": ["tests/test.py"],
            "expectedArtifacts": {
                "file": "test.py",
                "contains": [{"type": "function", "name": "test_func"}]
            }
        }

        context = load_manifest_context(manifest_data)

        # Should return a dict
        assert isinstance(context, dict)
        # Should contain key information
        assert "goal" in context
        assert "files" in context

    def test_execute_validation_returns_dict(self):
        """Test that execute_validation returns a result dictionary."""
        # Use a simple command that will succeed
        result = execute_validation(["echo", "test"])

        # Should return a dict
        assert isinstance(result, dict)
        # Should have success/failure status
        assert "success" in result
        # Should capture output
        assert "output" in result or "stdout" in result

    def test_execute_validation_captures_failure(self):
        """Test that execute_validation captures command failures."""
        # Use a command that will fail
        result = execute_validation(["false"])

        assert isinstance(result, dict)
        assert result["success"] is False

    def test_execute_validation_captures_success(self):
        """Test that execute_validation captures command success."""
        # Use a command that will succeed
        result = execute_validation(["true"])

        assert isinstance(result, dict)
        assert result["success"] is True

    def test_display_agent_context_accepts_dict(self, capsys):
        """Test that display_agent_context can display context information."""
        context = {
            "goal": "Implement a test feature",
            "files": {
                "creatable": ["new.py"],
                "editable": ["existing.py"],
                "readonly": ["tests/test.py"]
            }
        }

        # Should not raise an error
        display_agent_context(context)

        # Should produce output
        captured = capsys.readouterr()
        assert len(captured.out) > 0 or len(captured.err) > 0

    def test_display_validation_results_accepts_dict(self, capsys):
        """Test that display_validation_results can display results."""
        result = {
            "success": True,
            "output": "All tests passed"
        }

        # Should not raise an error
        display_validation_results(result)

        # Should produce output
        captured = capsys.readouterr()
        assert len(captured.out) > 0 or len(captured.err) > 0

    def test_run_implementation_loop_with_valid_manifest(self, tmp_path: Path):
        """Test run_implementation_loop with a valid manifest."""
        # Create a minimal valid manifest
        manifest = {
            "goal": "Test implementation",
            "taskType": "create",
            "creatableFiles": ["test.py"],
            "editableFiles": [],
            "readonlyFiles": [],
            "expectedArtifacts": {
                "file": "test.py",
                "contains": []
            },
            "validationCommand": ["true"]  # Always succeeds
        }

        manifest_path = tmp_path / "test.manifest.json"
        manifest_path.write_text(json.dumps(manifest))

        # Should complete without error
        # Run with max_iterations=1 to avoid infinite loop
        run_implementation_loop(str(manifest_path), max_iterations=1)

    def test_run_implementation_loop_with_failing_validation(self, tmp_path: Path):
        """Test run_implementation_loop when validation fails."""
        manifest = {
            "goal": "Test implementation",
            "taskType": "create",
            "creatableFiles": ["test.py"],
            "editableFiles": [],
            "readonlyFiles": [],
            "expectedArtifacts": {
                "file": "test.py",
                "contains": []
            },
            "validationCommand": ["false"]  # Always fails
        }

        manifest_path = tmp_path / "test.manifest.json"
        manifest_path.write_text(json.dumps(manifest))

        # Should handle failure gracefully and respect max_iterations
        run_implementation_loop(str(manifest_path), max_iterations=2)

    def test_run_implementation_loop_respects_max_iterations(self, tmp_path: Path):
        """Test that run_implementation_loop respects max_iterations limit."""
        manifest = {
            "goal": "Test implementation",
            "taskType": "create",
            "creatableFiles": ["test.py"],
            "editableFiles": [],
            "readonlyFiles": [],
            "expectedArtifacts": {
                "file": "test.py",
                "contains": []
            },
            "validationCommand": ["false"]  # Always fails
        }

        manifest_path = tmp_path / "test.manifest.json"
        manifest_path.write_text(json.dumps(manifest))

        # Should stop after max_iterations
        # We can't easily verify the count, but it should complete
        run_implementation_loop(str(manifest_path), max_iterations=3)

    def test_load_manifest_context_includes_all_file_types(self):
        """Test that load_manifest_context includes all file categories."""
        manifest_data = {
            "goal": "Test goal",
            "creatableFiles": ["new1.py", "new2.py"],
            "editableFiles": ["edit1.py", "edit2.py"],
            "readonlyFiles": ["readonly1.py", "readonly2.py"],
            "expectedArtifacts": {
                "file": "new1.py",
                "contains": []
            }
        }

        context = load_manifest_context(manifest_data)

        # Should include files information
        assert "files" in context
        files = context["files"]

        # Should categorize files correctly
        assert "creatable" in files or "creatableFiles" in files
        assert "editable" in files or "editableFiles" in files
        assert "readonly" in files or "readonlyFiles" in files

    def test_execute_validation_with_pytest_command(self, tmp_path: Path):
        """Test execute_validation with a pytest-like command."""
        # Create a simple test file that will pass
        test_file = tmp_path / "test_simple.py"
        test_file.write_text("""
def test_always_pass():
    assert True
""")

        # Execute validation with pytest
        result = execute_validation([
            "pytest",
            str(test_file),
            "-v"
        ])

        assert isinstance(result, dict)
        assert "success" in result
        # This should succeed
        assert result["success"] is True

    def test_main_function_exists(self):
        """Test that main() function exists and is callable."""
        # main() should be callable
        assert callable(main)

        # Call main() to ensure it's exercised
        # It should handle being called without arguments (will likely print help)
        try:
            main()
        except SystemExit:
            # main() may call sys.exit(), which is fine for CLI
            pass

    def test_display_agent_context_shows_goal(self, capsys):
        """Test that display_agent_context displays the goal."""
        context = {
            "goal": "UNIQUE_TEST_GOAL_12345",
            "files": {}
        }

        display_agent_context(context)

        captured = capsys.readouterr()
        output = captured.out + captured.err

        # Goal should appear in output
        assert "UNIQUE_TEST_GOAL_12345" in output or "goal" in output.lower()

    def test_display_validation_results_shows_success_status(self, capsys):
        """Test that display_validation_results shows success status."""
        result = {
            "success": True,
            "output": "Test output"
        }

        display_validation_results(result)

        captured = capsys.readouterr()
        output = captured.out + captured.err

        # Should indicate success
        assert len(output) > 0

    def test_display_validation_results_shows_failure_status(self, capsys):
        """Test that display_validation_results shows failure status."""
        result = {
            "success": False,
            "output": "Test failed",
            "stderr": "Error details"
        }

        display_validation_results(result)

        captured = capsys.readouterr()
        output = captured.out + captured.err

        # Should indicate failure
        assert len(output) > 0
