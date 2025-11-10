"""Configuration settings for MAID Agents."""

from dataclasses import dataclass


@dataclass
class ClaudeConfig:
    """Claude Code configuration."""

    model: str = "claude-sonnet-4-5-20250929"
    timeout: int = 300
    temperature: float = 0.0


@dataclass
class MAIDConfig:
    """MAID Agent configuration."""

    manifest_dir: str = "manifests"
    test_dir: str = "tests"
    max_planning_iterations: int = 10
    max_implementation_iterations: int = 20
    use_manifest_chain: bool = True


@dataclass
class AgentConfig:
    """Combined agent configuration."""

    claude: ClaudeConfig
    maid: MAIDConfig

    @classmethod
    def default(cls) -> "AgentConfig":
        """Create default configuration.

        Returns:
            AgentConfig with default settings
        """
        return cls(claude=ClaudeConfig(), maid=MAIDConfig())
