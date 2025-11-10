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
                "files_modified": [],
            }

        # Build prompt for Claude
        prompt = self._build_implementation_prompt(manifest_data, test_errors)

        # Generate implementation using Claude
        response = self.claude.generate(prompt)

        if not response.success:
            return {"success": False, "error": response.error, "files_modified": []}

        # Extract code from response (may be wrapped in markdown)
        code = self._extract_code_from_response(response.result)

        # Extract files to modify from manifest
        files_to_modify = manifest_data.get("creatableFiles", []) + manifest_data.get(
            "editableFiles", []
        )

        return {
            "success": True,
            "files_modified": files_to_modify,
            "code": code,
            "error": None,
        }

    def _extract_code_from_response(self, response: str) -> str:
        """Extract code from Claude response, handling markdown code fences.

        Args:
            response: Raw response from Claude

        Returns:
            Extracted code string
        """
        import re

        # Try to find code within markdown code fences
        # Pattern: ```python ... ``` or ``` ... ```
        code_block_pattern = r"```(?:python)?\s*\n(.*?)\n```"
        matches = re.findall(code_block_pattern, response, re.DOTALL)

        if matches:
            # Return the first/largest code block found
            return max(matches, key=len).strip()

        # If no code fence, return the whole response
        return response.strip()

    def _build_implementation_prompt(
        self, manifest_data: Dict[str, Any], test_errors: str
    ) -> str:
        """Build prompt for Claude to generate implementation.

        Args:
            manifest_data: Parsed manifest data
            test_errors: Test error output if any

        Returns:
            Formatted prompt string
        """
        goal = manifest_data.get("goal", "")
        artifacts = manifest_data.get("expectedArtifacts", {})
        file_to_create = artifacts.get("file", "")

        # Build artifact list for context
        artifact_list = []
        for artifact in artifacts.get("contains", []):
            if artifact["type"] == "function":
                args_str = ", ".join(
                    [f"{a['name']}: {a['type']}" for a in artifact.get("args", [])]
                )
                returns = artifact.get("returns", "None")
                if "class" in artifact:
                    artifact_list.append(
                        f"  - Method: {artifact['class']}.{artifact['name']}({args_str}) -> {returns}"
                    )
                else:
                    artifact_list.append(
                        f"  - Function: {artifact['name']}({args_str}) -> {returns}"
                    )
            elif artifact["type"] == "class":
                bases = artifact.get("bases", [])
                bases_str = f"({', '.join(bases)})" if bases else ""
                artifact_list.append(f"  - Class: {artifact['name']}{bases_str}")
            elif artifact["type"] == "attribute":
                if "class" in artifact:
                    artifact_list.append(
                        f"  - Attribute: {artifact['class']}.{artifact['name']}"
                    )
                else:
                    artifact_list.append(f"  - Attribute: {artifact['name']}")

        artifacts_section = (
            "\n".join(artifact_list) if artifact_list else "  (none specified)"
        )
        error_section = f"\nTEST FAILURES:\n{test_errors}\n" if test_errors else ""

        return f"""You are a Python code generator. Your ONLY job is to output Python code. Do NOT write explanations unless in code comments.

TASK: Implement code for the following specification

GOAL: {goal}

FILE: {file_to_create}

REQUIRED ARTIFACTS:
{artifacts_section}
{error_section}
REQUIREMENTS:
1. Make all tests pass
2. Match the artifact signatures EXACTLY as specified
3. Handle errors appropriately
4. Follow Python best practices
5. Include docstrings for public APIs

CRITICAL: Output ONLY the Python code. You may use markdown code fences (```python) but minimize explanatory text.

Example output format:
```python
# Your implementation here
def example_function(param: str) -> bool:
    \"\"\"Docstring here.\"\"\"
    # Implementation
    return True
```
"""
