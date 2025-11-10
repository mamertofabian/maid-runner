"""Refactorer Agent - Phase 3.5: Improves code quality while maintaining compliance."""

import json
from typing import Dict, Any

from maid_agents.agents.base_agent import BaseAgent
from maid_agents.claude.cli_wrapper import ClaudeWrapper


class Refactorer(BaseAgent):
    """Agent that refactors code while maintaining manifest compliance."""

    def __init__(self, claude: ClaudeWrapper):
        """Initialize refactorer agent.

        Args:
            claude: Claude wrapper for AI generation
        """
        super().__init__()
        self.claude = claude

    def execute(self) -> dict:
        """Execute refactoring.

        Returns:
            Dict with refactoring results
        """
        return {"status": "ready", "agent": "Refactorer"}

    def refactor(self, manifest_path: str) -> dict:
        """Refactor code while maintaining tests and manifest compliance.

        Args:
            manifest_path: Path to manifest file

        Returns:
            Dict with refactoring status
        """
        # Load manifest
        try:
            with open(manifest_path) as f:
                manifest_data = json.load(f)
        except FileNotFoundError:
            return {
                "success": False,
                "error": f"Manifest not found: {manifest_path}",
                "improvements": []
            }

        # Build prompt for Claude
        prompt = self._build_refactor_prompt(manifest_data)

        # Generate refactored code using Claude
        response = self.claude.generate(prompt)

        if not response.success:
            return {
                "success": False,
                "error": response.error,
                "improvements": []
            }

        return {
            "success": True,
            "improvements": ["Code quality improved"],
            "refactored_code": response.result,
            "error": None
        }

    def _build_refactor_prompt(self, manifest_data: Dict[str, Any]) -> str:
        """Build prompt for Claude to refactor code.

        Args:
            manifest_data: Parsed manifest data

        Returns:
            Formatted prompt string
        """
        goal = manifest_data.get("goal", "")

        return f"""You are a MAID Refactorer improving code quality.

GOAL: {goal}

Refactor code while:
1. Maintaining all tests passing
2. Preserving manifest compliance
3. Applying clean code principles

Output refactored code.
"""
