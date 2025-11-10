"""Behavioral tests for Tasks 006-009: Specialized Agents."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from maid_agents.agents.manifest_architect import ManifestArchitect
from maid_agents.agents.test_designer import TestDesigner
from maid_agents.agents.developer import Developer
from maid_agents.agents.refactorer import Refactorer
from maid_agents.claude.cli_wrapper import ClaudeWrapper


def test_manifest_architect_instantiation():
    """Test ManifestArchitect can be instantiated."""
    claude = ClaudeWrapper(mock_mode=True)
    agent = ManifestArchitect(claude)
    assert agent is not None


def test_test_designer_instantiation():
    """Test TestDesigner can be instantiated."""
    claude = ClaudeWrapper(mock_mode=True)
    agent = TestDesigner(claude)
    assert agent is not None


def test_developer_instantiation():
    """Test Developer can be instantiated."""
    claude = ClaudeWrapper(mock_mode=True)
    agent = Developer(claude)
    assert agent is not None


def test_refactorer_instantiation():
    """Test Refactorer can be instantiated."""
    claude = ClaudeWrapper(mock_mode=True)
    agent = Refactorer(claude)
    assert agent is not None
