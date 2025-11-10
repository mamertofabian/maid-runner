"""Behavioral tests for Task-017: Refiner Agent."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from maid_agents.agents.refiner import Refiner
from maid_agents.claude.cli_wrapper import ClaudeWrapper
from maid_agents.core.orchestrator import MAIDOrchestrator


def test_refiner_instantiation():
    """Test Refiner can be instantiated."""
    claude = ClaudeWrapper(mock_mode=True)
    refiner = Refiner(claude)
    assert refiner is not None
    assert isinstance(refiner, Refiner)


def test_refine_method_signature():
    """Test refine method exists with correct signature."""
    claude = ClaudeWrapper(mock_mode=True)
    refiner = Refiner(claude)

    result = refiner.refine(
        manifest_path="maid_agents/manifests/task-001-orchestrator-skeleton.manifest.json",
        refinement_goal="Add edge case tests",
        validation_feedback=""
    )

    assert isinstance(result, dict)
    assert "success" in result or "manifest_data" in result


def test_refine_returns_expected_structure():
    """Test refine returns dict with expected fields."""
    claude = ClaudeWrapper(mock_mode=True)
    refiner = Refiner(claude)

    result = refiner.refine(
        manifest_path="maid_agents/manifests/task-001-orchestrator-skeleton.manifest.json",
        refinement_goal="Improve test coverage",
        validation_feedback=""
    )

    # Verify response has expected structure
    assert "success" in result
    assert "manifest_data" in result or "error" in result
    assert "test_code" in result or "error" in result
    assert "improvements" in result or "error" in result


def test_refine_handles_nonexistent_manifest():
    """Test refine handles missing manifest file gracefully."""
    claude = ClaudeWrapper(mock_mode=True)
    refiner = Refiner(claude)

    result = refiner.refine(
        manifest_path="nonexistent/manifest.json",
        refinement_goal="Improve tests",
        validation_feedback=""
    )

    assert isinstance(result, dict)
    assert result["success"] is False
    assert "error" in result
    assert result["error"] is not None


def test_refine_with_validation_feedback():
    """Test refine accepts validation feedback parameter."""
    claude = ClaudeWrapper(mock_mode=True)
    refiner = Refiner(claude)

    result = refiner.refine(
        manifest_path="maid_agents/manifests/task-005-base-agent.manifest.json",
        refinement_goal="Fix validation errors",
        validation_feedback="Artifact 'foo' not found in tests"
    )

    assert isinstance(result, dict)
    assert "success" in result


def test_execute_method_inherited_from_base():
    """Test execute method is available from BaseAgent."""
    claude = ClaudeWrapper(mock_mode=True)
    refiner = Refiner(claude)

    result = refiner.execute()

    assert isinstance(result, dict)
    assert "status" in result or "agent" in result


def test_orchestrator_run_refinement_loop_exists():
    """Test run_refinement_loop method exists in MAIDOrchestrator."""
    orchestrator = MAIDOrchestrator(dry_run=True)

    result = orchestrator.run_refinement_loop(
        manifest_path="maid_agents/manifests/task-001-orchestrator-skeleton.manifest.json",
        refinement_goal="Add more comprehensive tests",
        max_iterations=2
    )

    assert isinstance(result, dict)
    assert "success" in result or "iterations" in result


def test_orchestrator_run_refinement_loop_returns_structure():
    """Test run_refinement_loop returns expected structure."""
    orchestrator = MAIDOrchestrator(dry_run=True)

    result = orchestrator.run_refinement_loop(
        manifest_path="maid_agents/manifests/task-005-base-agent.manifest.json",
        refinement_goal="Improve test quality",
        max_iterations=3
    )

    assert isinstance(result, dict)
    assert "success" in result
    assert "error" in result or "iterations" in result


def test_orchestrator_run_refinement_loop_with_different_iterations():
    """Test run_refinement_loop accepts different max_iterations values."""
    orchestrator = MAIDOrchestrator(dry_run=True)

    result1 = orchestrator.run_refinement_loop(
        manifest_path="maid_agents/manifests/task-001-orchestrator-skeleton.manifest.json",
        refinement_goal="Test goal 1",
        max_iterations=1
    )

    result2 = orchestrator.run_refinement_loop(
        manifest_path="maid_agents/manifests/task-001-orchestrator-skeleton.manifest.json",
        refinement_goal="Test goal 2",
        max_iterations=5
    )

    assert isinstance(result1, dict)
    assert isinstance(result2, dict)
