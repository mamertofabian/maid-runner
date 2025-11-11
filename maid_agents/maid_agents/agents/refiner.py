"""Refiner Agent - Phase 2 Quality Gate: Improves manifest and test quality."""

import json
import re
from pathlib import Path
from typing import Dict, Any

from maid_agents.agents.base_agent import BaseAgent
from maid_agents.claude.cli_wrapper import ClaudeWrapper


class Refiner(BaseAgent):
    """Agent that refines manifests and tests based on user refinement goals."""

    def __init__(self, claude: ClaudeWrapper):
        """Initialize refiner agent.

        Args:
            claude: Claude wrapper for AI generation
        """
        super().__init__()
        self.claude = claude

    def execute(self) -> dict:
        """Execute refinement.

        Returns:
            Dict with refinement results
        """
        return {"status": "ready", "agent": "Refiner"}

    def refine(
        self, manifest_path: str, refinement_goal: str, validation_feedback: str = ""
    ) -> dict:
        """Refine manifest and tests based on user goal and validation feedback.

        Args:
            manifest_path: Path to manifest file
            refinement_goal: User's refinement objectives
            validation_feedback: Error messages from previous validation iteration

        Returns:
            Dict with refined manifest data, test code, improvements list, and error
        """
        # Load manifest
        try:
            with open(manifest_path) as f:
                manifest_data = json.load(f)
        except FileNotFoundError:
            return {
                "success": False,
                "error": f"Manifest not found: {manifest_path}",
                "manifest_data": {},
                "test_code": {},
                "improvements": [],
            }
        except json.JSONDecodeError as e:
            return {
                "success": False,
                "error": f"Invalid JSON in manifest: {e}",
                "manifest_data": {},
                "test_code": {},
                "improvements": [],
            }

        # Load test files
        test_files = manifest_data.get("readonlyFiles", [])
        test_contents = self._load_test_files(test_files)

        if not test_contents:
            return {
                "success": False,
                "error": "No test files found in manifest readonlyFiles",
                "manifest_data": {},
                "test_code": {},
                "improvements": [],
            }

        # Build prompt for Claude
        prompt = self._build_refine_prompt(
            manifest_data, test_contents, refinement_goal, validation_feedback
        )

        # Generate refined manifest and tests using Claude
        response = self.claude.generate(prompt)

        if not response.success:
            return {
                "success": False,
                "error": response.error,
                "manifest_data": {},
                "test_code": {},
                "improvements": [],
            }

        # Parse response to extract refined manifest and tests
        try:
            improvements = self._extract_improvements(response.result)
            refined_manifest = self._parse_refined_manifest(response.result)
            refined_tests = self._parse_refined_tests(response.result)

            return {
                "success": True,
                "manifest_data": refined_manifest,
                "test_code": refined_tests,
                "improvements": improvements,
                "error": None,
            }
        except Exception as e:
            return {
                "success": False,
                "error": f"Failed to parse Claude's response: {e}",
                "manifest_data": {},
                "test_code": {},
                "improvements": [],
            }

    def _load_test_files(self, test_file_paths: list) -> Dict[str, str]:
        """Load contents of test files.

        Args:
            test_file_paths: List of test file paths

        Returns:
            Dict mapping file paths to their contents
        """
        contents = {}
        for file_path in test_file_paths:
            # Only load test files (not other readonly files)
            if "test" not in Path(file_path).name.lower():
                continue

            try:
                with open(file_path) as f:
                    contents[file_path] = f.read()
            except FileNotFoundError:
                # Test file might not exist yet if it's a new task
                contents[file_path] = ""

        return contents

    def _extract_improvements(self, response: str) -> list:
        """Extract list of improvements from Claude's response.

        Args:
            response: Claude's refinement response

        Returns:
            List of improvement descriptions
        """
        improvements = []
        in_improvements_section = False

        for line in response.split("\n"):
            line = line.strip()

            # Detect improvements section
            if "## Improvements" in line or "## improvements" in line.lower():
                in_improvements_section = True
                continue

            # Stop at next section
            if in_improvements_section and line.startswith("##"):
                break

            # Extract bullet points in improvements section
            if in_improvements_section and (
                line.startswith("-")
                or line.startswith("*")
                or (len(line) > 2 and line[0].isdigit() and line[1] in ".)")
            ):
                improvement = line.lstrip("-*0123456789.) ").strip()
                if improvement:
                    improvements.append(improvement)

        # If no structured improvements found, provide generic response
        if not improvements:
            improvements = ["Manifest and test quality improvements applied"]

        return improvements

    def _parse_refined_manifest(self, response: str) -> dict:
        """Parse refined manifest JSON from Claude's response.

        Args:
            response: Claude's refinement response

        Returns:
            Parsed manifest dict

        Raises:
            ValueError: If manifest JSON cannot be extracted
        """
        # Look for JSON code block after "## Refined Manifest:"
        pattern = r"## Refined Manifest:?\s*```json\s*(.*?)\s*```"
        match = re.search(pattern, response, re.DOTALL | re.IGNORECASE)

        if not match:
            raise ValueError("Could not find refined manifest JSON in response")

        json_str = match.group(1)
        return json.loads(json_str)

    def _parse_refined_tests(self, response: str) -> Dict[str, str]:
        """Parse refined test code from Claude's response.

        Args:
            response: Claude's refinement response

        Returns:
            Dict mapping test file paths to refined code

        Raises:
            ValueError: If test code cannot be extracted
        """
        # Look for Python code block after "## Refined Tests"
        # Format: ## Refined Tests (path/to/test.py):
        pattern = r"## Refined Tests.*?\((.*?)\):?\s*```python\s*(.*?)\s*```"
        match = re.search(pattern, response, re.DOTALL | re.IGNORECASE)

        if not match:
            raise ValueError("Could not find refined test code in response")

        test_path = match.group(1).strip()
        test_code = match.group(2)

        return {test_path: test_code}

    def _build_refine_prompt(
        self,
        manifest_data: Dict[str, Any],
        test_contents: Dict[str, str],
        refinement_goal: str,
        validation_feedback: str,
    ) -> str:
        """Build prompt for Claude to refine manifest and tests.

        Args:
            manifest_data: Current manifest data
            test_contents: Dict of test file paths to contents
            refinement_goal: User's refinement objectives
            validation_feedback: Validation errors from previous iteration

        Returns:
            Formatted prompt string
        """
        # Build test files section
        tests_section = "\n\n".join(
            [
                f"File: {path}\n```python\n{content}\n```"
                for path, content in test_contents.items()
            ]
        )

        feedback_section = ""
        if validation_feedback:
            feedback_section = f"""
VALIDATION FEEDBACK FROM PREVIOUS ITERATION:
{validation_feedback}

CRITICAL: Fix all validation errors from the feedback above.
"""

        return f"""You are a MAID manifest and test refinement expert. Your task is to improve manifest and test quality based on user goals and fix validation errors.

USER REFINEMENT GOAL:
{refinement_goal}

CURRENT MANIFEST:
```json
{json.dumps(manifest_data, indent=2)}
```

CURRENT TESTS:
{tests_section}
{feedback_section}
REFINEMENT REQUIREMENTS:

1. **Manifest Completeness**:
   - Ensure all public APIs are declared as artifacts
   - Proper file categorization (creatableFiles vs editableFiles)
   - Include all required artifact details (args, returns, types)

2. **Test Comprehensiveness**:
   - Add edge cases beyond bare minimum
   - Include error condition tests
   - Test integration scenarios
   - Ensure full coverage of all declared artifacts

3. **Test Quality**:
   - Use behavioral tests (actually call methods, don't just check existence)
   - Meaningful assertions that verify behavior
   - Clear, descriptive test names
   - Proper test isolation

4. **Clarity and Documentation**:
   - Improve goal descriptions
   - Better artifact descriptions
   - Clear test docstrings

5. **MAID Compliance**:
   - Maintain proper manifest structure
   - Ensure structural + behavioral validation will pass
   - Tests MUST USE all declared artifacts

OUTPUT FORMAT:
## Improvements Made:
- Improvement 1
- Improvement 2

## Refined Manifest:
```json
{{
  "goal": "...",
  ...
}}
```

## Refined Tests ({list(test_contents.keys())[0] if test_contents else 'test_file.py'}):
```python
# Refined test code
```

Begin your refinement analysis and improvements:
"""
