"""Behavioral tests for Task-015: Error Handling."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from maid_agents.core.orchestrator import MAIDOrchestrator


def test_handle_error_method_exists():
    """Test _handle_error method exists."""
    orchestrator = MAIDOrchestrator(dry_run=True)

    # Call the method with a test exception
    error = Exception("Test error")
    result = orchestrator._handle_error(error)

    assert isinstance(result, dict)
    assert "error" in result or "message" in result


def test_handle_error_with_different_exceptions():
    """Test _handle_error handles different exception types."""
    orchestrator = MAIDOrchestrator(dry_run=True)

    # Test with ValueError
    result1 = orchestrator._handle_error(ValueError("Value error"))
    assert isinstance(result1, dict)

    # Test with RuntimeError
    result2 = orchestrator._handle_error(RuntimeError("Runtime error"))
    assert isinstance(result2, dict)
