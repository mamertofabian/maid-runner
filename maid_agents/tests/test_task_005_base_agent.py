"""Behavioral tests for Task-005: BaseAgent."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from maid_agents.agents.base_agent import BaseAgent


class ConcreteAgent(BaseAgent):
    """Concrete implementation for testing."""

    def execute(self) -> dict:
        return {"status": "success"}


def test_base_agent_can_be_subclassed():
    """Test BaseAgent can be subclassed."""
    # Explicitly use BaseAgent as a type
    agent = ConcreteAgent()
    assert isinstance(agent, BaseAgent)

    # Verify it's truly a BaseAgent instance
    base_agent_ref = BaseAgent
    assert issubclass(type(agent), base_agent_ref)


def test_execute_method():
    """Test execute method can be called."""
    agent = ConcreteAgent()

    # Call execute method - this calls BaseAgent's abstract execute
    result = agent.execute()
    assert isinstance(result, dict)

    # Verify the method exists on BaseAgent interface
    assert hasattr(BaseAgent, "execute")

    # Verify it's callable
    assert callable(getattr(agent, "execute"))
