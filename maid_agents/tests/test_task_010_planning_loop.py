"""
Behavioral tests for Task-010: Planning Loop orchestration.

Tests the planning loop that iterates manifest + test creation with validation.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from maid_agents.core.orchestrator import MAIDOrchestrator


def test_run_planning_loop_method_exists():
    """Test run_planning_loop method exists with correct signature."""
    orchestrator = MAIDOrchestrator()

    result = orchestrator.run_planning_loop(goal="Test goal", max_iterations=5)

    assert isinstance(result, dict)
    assert "success" in result or "manifest_path" in result


def test_run_planning_loop_with_different_iterations():
    """Test run_planning_loop with different iteration counts."""
    orchestrator = MAIDOrchestrator()

    result = orchestrator.run_planning_loop(
        goal="Create a test feature", max_iterations=3
    )

    assert isinstance(result, dict)
