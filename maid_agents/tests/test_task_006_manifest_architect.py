"""
Behavioral tests for Task-006: ManifestArchitect Agent.

Tests the ManifestArchitect agent that creates MAID manifests from goals.
"""

import pytest
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from maid_agents.agents.manifest_architect import ManifestArchitect
from maid_agents.claude.cli_wrapper import ClaudeWrapper


def test_manifest_architect_instantiation():
    """Test ManifestArchitect can be instantiated with ClaudeWrapper."""
    claude = ClaudeWrapper(mock_mode=True)
    architect = ManifestArchitect(claude)

    assert architect is not None
    assert isinstance(architect, ManifestArchitect)
    assert architect.claude is not None


def test_create_manifest_method_signature():
    """Test create_manifest method exists with correct signature."""
    claude = ClaudeWrapper(mock_mode=True)
    architect = ManifestArchitect(claude)

    # Call with goal and task_number
    result = architect.create_manifest(
        goal="Create a new feature",
        task_number=42
    )

    assert isinstance(result, dict)
    assert "success" in result or "manifest_path" in result or "manifest_data" in result


def test_create_manifest_returns_dict_with_status():
    """Test create_manifest returns dict with status information."""
    claude = ClaudeWrapper(mock_mode=True)
    architect = ManifestArchitect(claude)

    result = architect.create_manifest(
        goal="Add user authentication",
        task_number=10
    )

    assert isinstance(result, dict)
    # Should have some indication of success/failure
    assert len(result) > 0


def test_execute_method_inherited_from_base():
    """Test execute method is available from BaseAgent."""
    claude = ClaudeWrapper(mock_mode=True)
    architect = ManifestArchitect(claude)

    result = architect.execute()

    assert isinstance(result, dict)
