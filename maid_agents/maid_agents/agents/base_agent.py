"""Base Agent - Abstract base class for all MAID agents."""

from abc import ABC, abstractmethod
from typing import Dict, Any


class BaseAgent(ABC):
    """Abstract base class for all MAID agents."""

    def __init__(self):
        """Initialize base agent."""
        pass

    @abstractmethod
    def execute(self) -> Dict[str, Any]:
        """Execute agent logic.

        Returns:
            Dict with execution results
        """
        pass
