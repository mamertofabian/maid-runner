"""Behavioral tests for Tasks 010-013: Integration & CLI."""

import sys
import subprocess
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from maid_agents.config.settings import AgentConfig, ClaudeConfig, MAIDConfig


def test_agent_config_creation():
    """Test AgentConfig can be created."""
    config = AgentConfig.default()
    assert config is not None
    assert isinstance(config.claude, ClaudeConfig)
    assert isinstance(config.maid, MAIDConfig)


def test_cli_help():
    """Test CLI --help works."""
    result = subprocess.run(
        ["python", "-m", "maid_agents.cli.main", "--help"],
        capture_output=True,
        text=True,
        cwd="maid_agents",
    )
    assert "ccmaid" in result.stdout.lower() or result.returncode == 0
