"""Test Designer Agent - Phase 2: Creates behavioral tests from manifests."""

import json
from pathlib import Path
from typing import Dict, Any, List

from maid_agents.agents.base_agent import BaseAgent
from maid_agents.claude.cli_wrapper import ClaudeWrapper


class TestDesigner(BaseAgent):
    """Agent that creates behavioral tests from manifests."""

    def __init__(self, claude: ClaudeWrapper):
        """Initialize test designer.

        Args:
            claude: Claude wrapper for AI generation
        """
        super().__init__()
        self.claude = claude

    def execute(self) -> dict:
        """Execute test generation.

        Returns:
            Dict with test generation results
        """
        return {"status": "ready", "agent": "TestDesigner"}

    def create_tests(self, manifest_path: str) -> dict:
        """Create behavioral tests from manifest.

        Args:
            manifest_path: Path to manifest file

        Returns:
            Dict with test file paths and success status
        """
        # Load manifest
        try:
            with open(manifest_path) as f:
                manifest_data = json.load(f)
        except FileNotFoundError:
            return {
                "success": False,
                "error": f"Manifest not found: {manifest_path}",
                "test_paths": [],
                "test_code": None
            }
        except json.JSONDecodeError as e:
            return {
                "success": False,
                "error": f"Invalid manifest JSON: {e}",
                "test_paths": [],
                "test_code": None
            }

        # Build prompt for Claude
        prompt = self._build_test_prompt(manifest_data, manifest_path)

        # Generate tests using Claude
        response = self.claude.generate(prompt)

        if not response.success:
            return {
                "success": False,
                "error": response.error,
                "test_paths": [],
                "test_code": None
            }

        # Extract test file path from manifest
        test_files = manifest_data.get("readonlyFiles", [])
        test_paths = [f for f in test_files if "test_" in f]

        return {
            "success": True,
            "test_paths": test_paths,
            "test_code": response.result,
            "error": None
        }

    def _build_test_prompt(self, manifest_data: Dict[str, Any], manifest_path: str) -> str:
        """Build prompt for Claude to generate tests.

        Args:
            manifest_data: Parsed manifest data
            manifest_path: Path to manifest file

        Returns:
            Formatted prompt string
        """
        goal = manifest_data.get("goal", "")
        artifacts = manifest_data.get("expectedArtifacts", {})
        artifacts_summary = self._summarize_artifacts(artifacts)

        return f"""You are a MAID Test Designer creating behavioral tests for:

MANIFEST: {manifest_path}
GOAL: {goal}

Expected artifacts to test:
{artifacts_summary}

Create behavioral tests that:
1. CALL/USE each declared artifact (not just check existence)
2. Exercise all parameters from manifest
3. Validate return types with isinstance()
4. Follow pytest conventions

CRITICAL:
- Tests must FAIL initially (red phase)
- Every artifact in manifest must be exercised
- Use realistic scenarios, not artificial assertions

Output Python test code following pytest conventions.
"""

    def _summarize_artifacts(self, artifacts: Dict[str, Any]) -> str:
        """Summarize artifacts for prompt.

        Args:
            artifacts: expectedArtifacts from manifest

        Returns:
            Human-readable summary
        """
        if not artifacts:
            return "No artifacts specified"

        file_path = artifacts.get("file", "unknown")
        contains = artifacts.get("contains", [])

        lines = [f"File: {file_path}"]
        for artifact in contains:
            artifact_type = artifact.get("type", "unknown")
            name = artifact.get("name", "unnamed")
            lines.append(f"  - {artifact_type}: {name}")

        return "\n".join(lines)
