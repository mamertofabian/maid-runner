"""Behavioral tests for Task-009: Refactorer Agent."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from maid_agents.agents.refactorer import Refactorer
from maid_agents.claude.cli_wrapper import ClaudeWrapper


def test_refactorer_instantiation():
    """Test Refactorer can be instantiated."""
    claude = ClaudeWrapper(mock_mode=True)
    refactorer = Refactorer(claude)
    assert refactorer is not None
    assert isinstance(refactorer, Refactorer)


def test_refactor_method_signature():
    """Test refactor method exists with correct signature."""
    claude = ClaudeWrapper(mock_mode=True)
    refactorer = Refactorer(claude)

    result = refactorer.refactor(
        manifest_path="maid_agents/manifests/task-001-orchestrator-skeleton.manifest.json"
    )

    assert isinstance(result, dict)
    assert "success" in result or "improvements" in result


def test_refactor_returns_expected_structure():
    """Test refactor returns dict with expected fields."""
    claude = ClaudeWrapper(mock_mode=True)
    refactorer = Refactorer(claude)

    result = refactorer.refactor(
        manifest_path="maid_agents/manifests/task-001-orchestrator-skeleton.manifest.json"
    )

    # Verify response has expected structure
    assert "success" in result
    assert "improvements" in result
    assert "error" in result


def test_refactor_handles_nonexistent_manifest():
    """Test refactor handles missing manifest file gracefully."""
    claude = ClaudeWrapper(mock_mode=True)
    refactorer = Refactorer(claude)

    result = refactorer.refactor(manifest_path="nonexistent/manifest.json")

    assert isinstance(result, dict)
    assert result["success"] is False
    assert "error" in result
    assert result["error"] is not None


def test_refactor_loads_manifest_correctly():
    """Test refactor successfully loads and processes valid manifest."""
    claude = ClaudeWrapper(mock_mode=True)
    refactorer = Refactorer(claude)

    result = refactorer.refactor(
        manifest_path="maid_agents/manifests/task-005-base-agent.manifest.json"
    )

    # Should attempt to process (may succeed or fail depending on mock response)
    assert isinstance(result, dict)
    assert "success" in result
    assert "improvements" in result


def test_execute_method_inherited_from_base():
    """Test execute method is available from BaseAgent."""
    claude = ClaudeWrapper(mock_mode=True)
    refactorer = Refactorer(claude)

    result = refactorer.execute()

    assert isinstance(result, dict)
    assert "status" in result or "agent" in result
