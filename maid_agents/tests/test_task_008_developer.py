"""Behavioral tests for Task-008: Developer Agent."""

import pytest
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
        test_errors=""
    )

    assert isinstance(result, dict)
    assert "success" in result or "files_modified" in result
