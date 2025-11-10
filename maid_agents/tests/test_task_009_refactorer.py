"""Behavioral tests for Task-009: Refactorer Agent."""

import pytest
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from maid_agents.agents.refactorer import Refactorer
from maid_agents.claude.cli_wrapper import ClaudeWrapper


def test_refactorer_instantiation():
    """Test Refactorer can be instantiated."""
    claude = ClaudeWrapper(mock_mode=True)
    refactorer = Refactorer(claude)
    assert refactorer is not None
    assert isinstance(refactorer, Refactorer)


def test_refactor_method_signature():
    """Test refactor method exists with correct signature."""
    claude = ClaudeWrapper(mock_mode=True)
    refactorer = Refactorer(claude)

    result = refactorer.refactor(
        manifest_path="maid_agents/manifests/task-001-orchestrator-skeleton.manifest.json"
    )

    assert isinstance(result, dict)
    assert "success" in result or "improvements" in result
