"""Behavioral tests for Tasks 014-016: Polish & Quality."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))


def test_templates_exist():
    """Test prompt templates exist."""
    templates_dir = Path("maid_agents/maid_agents/config/templates")
    assert templates_dir.exists()
    assert (templates_dir / "manifest_creation.txt").exists()
    assert (templates_dir / "test_generation.txt").exists()
    assert (templates_dir / "implementation.txt").exists()


def test_all_core_modules_importable():
    """Test all core modules can be imported."""
    from maid_agents.core import orchestrator
    from maid_agents.core import validation_runner
    from maid_agents.core import context_builder
    from maid_agents.claude import cli_wrapper
    from maid_agents.agents import base_agent
    from maid_agents.config import settings

    assert orchestrator is not None
    assert validation_runner is not None
    assert context_builder is not None
    assert cli_wrapper is not None
    assert base_agent is not None
    assert settings is not None
