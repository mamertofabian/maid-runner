"""
Behavioral tests for Task-001: MAIDOrchestrator skeleton.

These tests validate the WorkflowState enum, WorkflowResult dataclass,
and MAIDOrchestrator class with its core methods.

Tests MUST USE the artifacts (call methods, instantiate classes, access attributes)
rather than just checking for their existence.
"""

import sys
from pathlib import Path

# Add maid_agents package to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from maid_agents.core.orchestrator import (
    WorkflowState,
    WorkflowResult,
    MAIDOrchestrator,
)


def test_workflow_state_enum_init():
    """Test WorkflowState.INIT can be accessed and used."""

    state = WorkflowState.INIT
    assert isinstance(state, WorkflowState)
    assert state.name == "INIT" or state.value is not None


def test_workflow_state_enum_planning():
    """Test WorkflowState.PLANNING can be accessed and used."""

    state = WorkflowState.PLANNING
    assert isinstance(state, WorkflowState)
    assert state.name == "PLANNING" or state.value is not None


def test_workflow_state_enum_implementing():
    """Test WorkflowState.IMPLEMENTING can be accessed and used."""

    state = WorkflowState.IMPLEMENTING
    assert isinstance(state, WorkflowState)
    assert state.name == "IMPLEMENTING" or state.value is not None


def test_workflow_state_enum_refactoring():
    """Test WorkflowState.REFACTORING can be accessed and used."""

    state = WorkflowState.REFACTORING
    assert isinstance(state, WorkflowState)
    assert state.name == "REFACTORING" or state.value is not None


def test_workflow_state_enum_complete():
    """Test WorkflowState.COMPLETE can be accessed and used."""

    state = WorkflowState.COMPLETE
    assert isinstance(state, WorkflowState)
    assert state.name == "COMPLETE" or state.value is not None


def test_workflow_state_enum_failed():
    """Test WorkflowState.FAILED can be accessed and used."""

    state = WorkflowState.FAILED
    assert isinstance(state, WorkflowState)
    assert state.name == "FAILED" or state.value is not None


def test_workflow_state_enum_all_states():
    """Test all WorkflowState enum members can be used together."""

    states = [
        WorkflowState.INIT,
        WorkflowState.PLANNING,
        WorkflowState.IMPLEMENTING,
        WorkflowState.REFACTORING,
        WorkflowState.COMPLETE,
        WorkflowState.FAILED,
    ]

    # All states should be unique
    assert len(states) == len(set(states))

    # All should be WorkflowState instances
    for state in states:
        assert isinstance(state, WorkflowState)


def test_workflow_result_dataclass_creation():
    """Test WorkflowResult can be created with required fields."""

    # Create instance with all fields
    result = WorkflowResult(
        success=True,
        manifest_path="manifests/task-001.json",
        message="Workflow completed successfully",
    )

    # Validate fields exist and have correct types
    assert isinstance(result.success, bool)
    assert result.success is True

    assert isinstance(result.manifest_path, str)
    assert result.manifest_path == "manifests/task-001.json"

    assert isinstance(result.message, str)
    assert result.message == "Workflow completed successfully"


def test_workflow_result_dataclass_failure_case():
    """Test WorkflowResult can represent failure cases."""

    result = WorkflowResult(
        success=False, manifest_path="", message="Workflow failed: validation error"
    )

    assert result.success is False
    assert isinstance(result.manifest_path, str)
    assert isinstance(result.message, str)
    assert "failed" in result.message.lower()


def test_maid_orchestrator_instantiation():
    """Test MAIDOrchestrator can be instantiated."""

    orchestrator = MAIDOrchestrator()
    assert orchestrator is not None
    assert isinstance(orchestrator, MAIDOrchestrator)


def test_run_full_workflow_method_exists():
    """Test run_full_workflow method can be called and returns WorkflowResult."""

    orchestrator = MAIDOrchestrator()

    # CALL the method with required goal parameter
    result = orchestrator.run_full_workflow(goal="Create a test module")

    # Validate return type
    assert isinstance(result, WorkflowResult)

    # Validate result has expected attributes
    assert hasattr(result, "success")
    assert hasattr(result, "manifest_path")
    assert hasattr(result, "message")


def test_run_full_workflow_with_different_goals():
    """Test run_full_workflow can be called with different goal strings."""

    orchestrator = MAIDOrchestrator()

    goals = [
        "Implement user authentication",
        "Add logging functionality",
        "Refactor database layer",
    ]

    for goal in goals:
        result = orchestrator.run_full_workflow(goal=goal)
        assert isinstance(result, WorkflowResult)


def test_get_workflow_state_method_exists():
    """Test get_workflow_state method can be called and returns WorkflowState."""

    orchestrator = MAIDOrchestrator()

    # CALL the method
    state = orchestrator.get_workflow_state()

    # Validate return type
    assert isinstance(state, WorkflowState)


def test_workflow_state_after_instantiation():
    """Test orchestrator has a valid workflow state after instantiation."""

    orchestrator = MAIDOrchestrator()
    state = orchestrator.get_workflow_state()

    # State should be one of the valid WorkflowState enum members
    valid_states = [
        WorkflowState.INIT,
        WorkflowState.PLANNING,
        WorkflowState.IMPLEMENTING,
        WorkflowState.REFACTORING,
        WorkflowState.COMPLETE,
        WorkflowState.FAILED,
    ]

    assert state in valid_states


def test_orchestrator_workflow_integration():
    """Test integration between run_full_workflow and get_workflow_state."""
    orchestrator = MAIDOrchestrator()

    # Get initial state
    initial_state = orchestrator.get_workflow_state()
    assert isinstance(initial_state, WorkflowState)

    # Run workflow
    result = orchestrator.run_full_workflow(goal="Test workflow")
    assert isinstance(result, WorkflowResult)

    # Get final state
    final_state = orchestrator.get_workflow_state()
    assert isinstance(final_state, WorkflowState)

    # States should be valid (may or may not have changed, depending on implementation)
    valid_states = [
        WorkflowState.INIT,
        WorkflowState.PLANNING,
        WorkflowState.IMPLEMENTING,
        WorkflowState.REFACTORING,
        WorkflowState.COMPLETE,
        WorkflowState.FAILED,
    ]
    assert initial_state in valid_states
    assert final_state in valid_states
