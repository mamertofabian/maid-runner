"""
Behavioral tests for Task-007: TestDesigner Agent.

Tests the TestDesigner agent that creates behavioral tests from manifests.
"""

import pytest
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from maid_agents.agents.test_designer import TestDesigner
from maid_agents.claude.cli_wrapper import ClaudeWrapper


def test_test_designer_instantiation():
    """Test TestDesigner can be instantiated with ClaudeWrapper."""
    claude = ClaudeWrapper(mock_mode=True)
    designer = TestDesigner(claude)

    assert designer is not None
    assert isinstance(designer, TestDesigner)
    assert designer.claude is not None


def test_create_tests_method_signature():
    """Test create_tests method exists with correct signature."""
    claude = ClaudeWrapper(mock_mode=True)
    designer = TestDesigner(claude)

    # Use an existing manifest
    manifest_path = "maid_agents/manifests/task-001-orchestrator-skeleton.manifest.json"

    result = designer.create_tests(manifest_path=manifest_path)

    assert isinstance(result, dict)
    assert "success" in result or "test_paths" in result or "test_code" in result


def test_create_tests_returns_dict_with_status():
    """Test create_tests returns dict with status information."""
    claude = ClaudeWrapper(mock_mode=True)
    designer = TestDesigner(claude)

    result = designer.create_tests(
        manifest_path="maid_agents/manifests/task-002-validation-runner.manifest.json"
    )

    assert isinstance(result, dict)
    assert len(result) > 0


def test_execute_method_inherited_from_base():
    """Test execute method is available from BaseAgent."""
    claude = ClaudeWrapper(mock_mode=True)
    designer = TestDesigner(claude)

    result = designer.execute()

    assert isinstance(result, dict)
