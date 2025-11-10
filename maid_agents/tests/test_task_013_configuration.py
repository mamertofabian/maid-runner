"""Behavioral tests for Task-013: Configuration."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from maid_agents.config.settings import AgentConfig, ClaudeConfig, MAIDConfig


def test_claude_config_instantiation():
    """Test ClaudeConfig can be instantiated."""
    config = ClaudeConfig()
    assert config is not None
    assert isinstance(config, ClaudeConfig)
    assert hasattr(config, "model")


def test_maid_config_instantiation():
    """Test MAIDConfig can be instantiated."""
    config = MAIDConfig()
    assert config is not None
    assert isinstance(config, MAIDConfig)
    assert hasattr(config, "manifest_dir")


def test_agent_config_instantiation():
    """Test AgentConfig can be instantiated."""
    claude_cfg = ClaudeConfig()
    maid_cfg = MAIDConfig()
    config = AgentConfig(claude=claude_cfg, maid=maid_cfg)

    assert config is not None
    assert isinstance(config, AgentConfig)
    assert config.claude is not None
    assert config.maid is not None


def test_agent_config_default_method():
    """Test AgentConfig.default() creates default configuration."""
    config = AgentConfig.default()

    assert isinstance(config, AgentConfig)
    assert isinstance(config.claude, ClaudeConfig)
    assert isinstance(config.maid, MAIDConfig)
