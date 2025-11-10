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
            Dict with refactoring status, improvements list, and refactored code
        """
        # Load manifest
        try:
            with open(manifest_path) as f:
                manifest_data = json.load(f)
        except FileNotFoundError:
            return {
                "success": False,
                "error": f"Manifest not found: {manifest_path}",
                "improvements": [],
            }
        except json.JSONDecodeError as e:
            return {
                "success": False,
                "error": f"Invalid JSON in manifest: {e}",
                "improvements": [],
            }

        # Get target files to refactor
        files_to_refactor = manifest_data.get("editableFiles", []) + manifest_data.get(
            "creatableFiles", []
        )

        if not files_to_refactor:
            return {
                "success": False,
                "error": "No files to refactor in manifest",
                "improvements": [],
            }

        # Load current code from target files
        file_contents = self._load_file_contents(files_to_refactor)

        # Build prompt for Claude
        prompt = self._build_refactor_prompt(manifest_data, file_contents)

        # Generate refactoring suggestions using Claude
        response = self.claude.generate(prompt)

        if not response.success:
            return {"success": False, "error": response.error, "improvements": []}

        # Parse improvements from response
        improvements = self._extract_improvements(response.result)

        return {
            "success": True,
            "improvements": improvements,
            "refactored_code": response.result,
            "files_affected": files_to_refactor,
            "error": None,
        }

    def _load_file_contents(self, file_paths: list) -> Dict[str, str]:
        """Load contents of files to be refactored.

        Args:
            file_paths: List of file paths to load

        Returns:
            Dict mapping file paths to their contents
        """
        contents = {}
        for file_path in file_paths:
            try:
                with open(file_path) as f:
                    contents[file_path] = f.read()
            except FileNotFoundError:
                contents[file_path] = f"# File not found: {file_path}"
        return contents

    def _extract_improvements(self, response: str) -> list:
        """Extract list of improvements from Claude's response.

        Args:
            response: Claude's refactoring response

        Returns:
            List of improvement descriptions
        """
        # Simple extraction: look for bullet points or numbered lists
        improvements = []
        for line in response.split("\n"):
            line = line.strip()
            # Match lines starting with -, *, or numbers
            if (
                line.startswith("-")
                or line.startswith("*")
                or (len(line) > 2 and line[0].isdigit() and line[1] in ".)")
            ):
                improvement = line.lstrip("-*0123456789.) ").strip()
                if improvement:
                    improvements.append(improvement)

        # If no structured improvements found, provide generic response
        if not improvements:
            improvements = ["Code quality improvements applied"]

        return improvements

    def _build_refactor_prompt(
        self, manifest_data: Dict[str, Any], file_contents: Dict[str, str]
    ) -> str:
        """Build prompt for Claude to refactor code.

        Args:
            manifest_data: Parsed manifest data
            file_contents: Dict of file paths to their contents

        Returns:
            Formatted prompt string
        """
        goal = manifest_data.get("goal", "")

        # Build file context section
        files_section = "\n\n".join(
            [
                f"File: {path}\n```python\n{content}\n```"
                for path, content in file_contents.items()
            ]
        )

        return f"""You are a code refactoring expert. Your task is to improve code quality while maintaining all functionality and tests.

GOAL: {goal}

CURRENT CODE:
{files_section}

REFACTORING REQUIREMENTS:
1. **Maintain Public API**: All artifacts in the manifest must remain unchanged:
   - Function signatures must stay the same
   - Class names and inheritance must stay the same
   - Public method signatures must stay the same

2. **Apply Clean Code Principles**:
   - Improve readability and clarity
   - Extract complex logic into well-named helper methods
   - Reduce code duplication (DRY principle)
   - Improve variable and function naming
   - Add docstrings where missing or improve existing ones
   - Simplify complex conditionals
   - Remove dead code or unnecessary comments

3. **Maintain Tests**: All existing tests must continue to pass

4. **Preserve Behavior**: The refactored code must have identical behavior

OUTPUT FORMAT:
First, list the improvements you're making as bullet points:
- Improvement 1
- Improvement 2
- etc.

Then provide the refactored code.

Begin your refactoring analysis and improvements:
"""
