"""Developer Agent - Phase 3: Implements code to pass tests."""

import json
from typing import Dict, Any

from maid_agents.agents.base_agent import BaseAgent
from maid_agents.claude.cli_wrapper import ClaudeWrapper


class Developer(BaseAgent):
    """Agent that implements code to make tests pass."""

    def __init__(self, claude: ClaudeWrapper):
        """Initialize developer agent.

        Args:
            claude: Claude wrapper for AI generation
        """
        super().__init__()
        self.claude = claude

    def execute(self) -> dict:
        """Execute implementation.

        Returns:
            Dict with implementation results
        """
        return {"status": "ready", "agent": "Developer"}

    def implement(self, manifest_path: str, test_errors: str = "") -> dict:
        """Implement code to pass tests.

        Args:
            manifest_path: Path to manifest file
            test_errors: Optional test error output to fix

        Returns:
            Dict with implementation status
        """
        # Load manifest
        try:
            with open(manifest_path) as f:
                manifest_data = json.load(f)
        except FileNotFoundError:
            return {
                "success": False,
                "error": f"Manifest not found: {manifest_path}",
                "files_modified": []
            }

        # Build prompt for Claude
        prompt = self._build_implementation_prompt(manifest_data, test_errors)

        # Generate implementation using Claude
        response = self.claude.generate(prompt)

        if not response.success:
            return {
                "success": False,
                "error": response.error,
                "files_modified": []
            }

        # Extract files to modify from manifest
        files_to_modify = (
            manifest_data.get("creatableFiles", []) +
            manifest_data.get("editableFiles", [])
        )

        return {
            "success": True,
            "files_modified": files_to_modify,
            "code": response.result,
            "error": None
        }

    def _build_implementation_prompt(self, manifest_data: Dict[str, Any], test_errors: str) -> str:
        """Build prompt for Claude to generate implementation.

        Args:
            manifest_data: Parsed manifest data
            test_errors: Test error output if any

        Returns:
            Formatted prompt string
        """
        goal = manifest_data.get("goal", "")
        artifacts = manifest_data.get("expectedArtifacts", {})

        error_section = f"\nTEST FAILURES:\n{test_errors}\n" if test_errors else ""

        return f"""You are a MAID Developer implementing code to pass tests.

GOAL: {goal}
{error_section}
Implement code that:
1. Makes all tests pass
2. Matches manifest artifact signatures exactly
3. Handles errors appropriately

Output implementation code.
"""
