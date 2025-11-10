"""
Behavioral tests for Task-004: ClaudeWrapper.

Tests the ClaudeWrapper class that invokes Claude Code headless CLI.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from maid_agents.claude.cli_wrapper import ClaudeWrapper, ClaudeResponse


def test_claude_response_creation():
    """Test ClaudeResponse can be instantiated."""
    response = ClaudeResponse(
        success=True, result="Test response", error="", session_id="test-123"
    )

    assert isinstance(response.success, bool)
    assert isinstance(response.result, str)
    assert hasattr(response, "error")
    assert hasattr(response, "session_id")


def test_claude_wrapper_instantiation():
    """Test ClaudeWrapper can be instantiated."""
    wrapper = ClaudeWrapper()
    assert wrapper is not None
    assert isinstance(wrapper, ClaudeWrapper)


def test_generate_method_signature():
    """Test generate method exists with correct signature."""
    wrapper = ClaudeWrapper()

    # Test with mock mode (won't actually call Claude)
    response = wrapper.generate(
        prompt="Test prompt", model="claude-sonnet-4-5-20250929"
    )

    assert isinstance(response, ClaudeResponse)
    assert hasattr(response, "success")
    assert hasattr(response, "result")
