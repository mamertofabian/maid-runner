"""
Behavioral tests for Task-011: Implementation Loop orchestration.

Tests the implementation loop that iterates code generation until tests pass.
"""

import pytest
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from maid_agents.core.orchestrator import MAIDOrchestrator


def test_run_implementation_loop_method_exists():
    """Test run_implementation_loop method exists with correct signature."""
    orchestrator = MAIDOrchestrator()

    result = orchestrator.run_implementation_loop(
        manifest_path="maid_agents/manifests/task-001-orchestrator-skeleton.manifest.json",
        max_iterations=5
    )

    assert isinstance(result, dict)
    assert "success" in result or "iterations" in result


def test_run_implementation_loop_with_different_iterations():
    """Test run_implementation_loop with different iteration counts."""
    orchestrator = MAIDOrchestrator()

    result = orchestrator.run_implementation_loop(
        manifest_path="maid_agents/manifests/task-002-validation-runner.manifest.json",
        max_iterations=3
    )

    assert isinstance(result, dict)
