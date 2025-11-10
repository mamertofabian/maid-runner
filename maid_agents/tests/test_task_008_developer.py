"""Behavioral tests for Task-008: Developer Agent."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from maid_agents.agents.developer import Developer
from maid_agents.claude.cli_wrapper import ClaudeWrapper


def test_developer_instantiation():
    """Test Developer can be instantiated."""
    claude = ClaudeWrapper(mock_mode=True)
    developer = Developer(claude)
    assert developer is not None
    assert isinstance(developer, Developer)


def test_implement_method_signature():
    """Test implement method exists with correct signature."""
    claude = ClaudeWrapper(mock_mode=True)
    developer = Developer(claude)

    result = developer.implement(
        manifest_path="maid_agents/manifests/task-001-orchestrator-skeleton.manifest.json",
        test_errors="",
    )

    assert isinstance(result, dict)
    assert "success" in result or "files_modified" in result


def test_implement_response_structure():
    """Test implement returns dict with expected fields."""
    claude = ClaudeWrapper(mock_mode=True)
    developer = Developer(claude)

    result = developer.implement(
        manifest_path="maid_agents/manifests/task-001-orchestrator-skeleton.manifest.json",
        test_errors="",
    )

    # Verify response has expected structure
    assert "success" in result
    assert "files_modified" in result
    assert "error" in result


def test_implement_with_test_errors():
    """Test implement method handles test errors parameter."""
    claude = ClaudeWrapper(mock_mode=True)
    developer = Developer(claude)

    test_errors = """
FAILED test_example.py::test_function - AssertionError
Expected 42, got 0
    """

    result = developer.implement(
        manifest_path="maid_agents/manifests/task-001-orchestrator-skeleton.manifest.json",
        test_errors=test_errors,
    )

    assert isinstance(result, dict)
    assert "success" in result


def test_implement_handles_missing_manifest():
    """Test implement handles missing manifest file gracefully."""
    claude = ClaudeWrapper(mock_mode=True)
    developer = Developer(claude)

    result = developer.implement(
        manifest_path="nonexistent/manifest.json",
        test_errors="",
    )

    assert isinstance(result, dict)
    assert result["success"] is False
    assert "error" in result
    assert (
        "not found" in result["error"].lower() or "manifest" in result["error"].lower()
    )


def test_implement_lists_files_to_modify():
    """Test implement returns list of files that will be modified."""
    claude = ClaudeWrapper(mock_mode=True)
    developer = Developer(claude)

    result = developer.implement(
        manifest_path="maid_agents/manifests/task-001-orchestrator-skeleton.manifest.json",
        test_errors="",
    )

    # When successful, should return files_modified list
    if result["success"]:
        assert isinstance(result["files_modified"], list)


def test_execute_method_inherited():
    """Test execute method is available from BaseAgent."""
    claude = ClaudeWrapper(mock_mode=True)
    developer = Developer(claude)

    result = developer.execute()

    assert isinstance(result, dict)
