"""Manifest Architect Agent - Phase 1: Creates manifests from goals."""

import json
from pathlib import Path
from typing import Dict, Any

from maid_agents.agents.base_agent import BaseAgent
from maid_agents.claude.cli_wrapper import ClaudeWrapper


class ManifestArchitect(BaseAgent):
    """Agent that creates MAID manifests from high-level goals."""

    def __init__(self, claude: ClaudeWrapper):
        """Initialize manifest architect.

        Args:
            claude: Claude wrapper for AI generation
        """
        super().__init__()
        self.claude = claude

    def execute(self) -> dict:
        """Execute manifest creation.

        Returns:
            Dict with manifest creation results
        """
        return {"status": "ready", "agent": "ManifestArchitect"}

    def create_manifest(self, goal: str, task_number: int) -> dict:
        """Create manifest from goal description.

        Args:
            goal: High-level goal description
            task_number: Task number for manifest naming

        Returns:
            Dict with manifest data and path
        """
        # Build prompt for Claude
        prompt = self._build_manifest_prompt(goal, task_number)

        # Generate manifest using Claude
        response = self.claude.generate(prompt)

        if not response.success:
            return {
                "success": False,
                "error": response.error,
                "manifest_path": None,
                "manifest_data": None
            }

        # Parse response as JSON manifest
        try:
            manifest_data = json.loads(response.result)
            manifest_path = f"manifests/task-{task_number:03d}.manifest.json"

            return {
                "success": True,
                "manifest_path": manifest_path,
                "manifest_data": manifest_data,
                "error": None
            }
        except json.JSONDecodeError as e:
            return {
                "success": False,
                "error": f"Failed to parse manifest JSON: {e}",
                "manifest_path": None,
                "manifest_data": None
            }

    def _build_manifest_prompt(self, goal: str, task_number: int) -> str:
        """Build prompt for Claude to generate manifest.

        Args:
            goal: High-level goal description
            task_number: Task number

        Returns:
            Formatted prompt string
        """
        return f"""You are a MAID Manifest Architect creating task-{task_number:03d}.

GOAL: {goal}

Create a MAID v1.2 manifest that:
1. Determines task type (create/edit/refactor)
2. Lists files to touch (creatableFiles vs editableFiles)
3. Declares ALL public artifacts with precise signatures
4. Specifies validation command (pytest path)

CRITICAL:
- Be atomic: touch minimal files
- Be explicit: declare all public APIs
- Be testable: artifacts must be verifiable in tests

Output ONLY valid JSON matching the manifest schema.

Example structure:
{{
  "goal": "{goal}",
  "taskType": "create",
  "creatableFiles": ["path/to/new/file.py"],
  "readonlyFiles": ["tests/test_file.py"],
  "expectedArtifacts": {{
    "file": "path/to/new/file.py",
    "contains": [
      {{
        "type": "class",
        "name": "ClassName"
      }},
      {{
        "type": "function",
        "name": "function_name",
        "class": "ClassName",
        "args": [{{"name": "param", "type": "str"}}],
        "returns": "ReturnType"
      }}
    ]
  }},
  "validationCommand": ["pytest", "tests/test_file.py", "-v"]
}}
"""
