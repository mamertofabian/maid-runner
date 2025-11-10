"""Test Designer Agent - Phase 2: Creates behavioral tests from manifests."""

import json
from typing import Dict, Any

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
                "test_code": None,
            }
        except json.JSONDecodeError as e:
            return {
                "success": False,
                "error": f"Invalid manifest JSON: {e}",
                "test_paths": [],
                "test_code": None,
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
                "test_code": None,
            }

        # Extract Python code from response (may be wrapped in markdown)
        try:
            test_code = self._extract_code_from_response(response.result)

            # Extract test file path from manifest
            test_files = manifest_data.get("readonlyFiles", [])
            test_paths = [f for f in test_files if "test_" in f]

            return {
                "success": True,
                "test_paths": test_paths,
                "test_code": test_code,
                "error": None,
            }
        except Exception as e:
            return {
                "success": False,
                "error": f"Failed to extract test code: {e}. Response preview: {response.result[:200]}",
                "test_paths": [],
                "test_code": None,
            }

    def _extract_code_from_response(self, response: str) -> str:
        """Extract Python code from Claude response, handling markdown code fences.

        Args:
            response: Raw response from Claude

        Returns:
            Extracted Python code string
        """
        import re

        # Try to find Python code within markdown code fences
        # Pattern: ```python ... ``` or ``` ... ```
        python_block_pattern = r"```(?:python)?\s*\n(.*?)\n```"
        matches = re.findall(python_block_pattern, response, re.DOTALL)

        if matches:
            # Return the first Python code block found
            return matches[0].strip()

        # If no code fence, try to find import/def/class statements
        # This suggests it's already raw Python
        if (
            "import " in response
            or "def " in response
            or "class " in response
            or "@" in response
        ):
            return response.strip()

        # If nothing found, return original (may be raw Python without markers)
        return response.strip()

    def _build_test_prompt(
        self, manifest_data: Dict[str, Any], manifest_path: str
    ) -> str:
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

        # Get file paths for import statements
        target_file = artifacts.get("file", "")

        return f"""You are a Python test code generator. Your ONLY job is to output valid Python pytest code. Do NOT write explanations.

TASK: Generate behavioral tests for MAID manifest: {manifest_path}

GOAL: {goal}

EXPECTED ARTIFACTS TO TEST:
{artifacts_summary}

REQUIREMENTS:
1. Import from: {target_file} (convert path to import statement)
2. CALL/USE each declared artifact (not just check existence)
3. Exercise ALL parameters from manifest signatures
4. Validate return types with isinstance() or assert
5. Follow pytest conventions (test_* functions)
6. Add proper docstrings to each test

CRITICAL: Your response must be ONLY raw Python code. No markdown, no explanations, no code fences.

Example test structure:
\"\"\"Behavioral tests for {goal}.\"\"\"

import pytest
from path.to.module import ClassName, function_name

def test_artifact_instantiation():
    \"\"\"Test artifact can be instantiated/called.\"\"\"
    instance = ClassName()
    assert instance is not None

def test_artifact_method_signature():
    \"\"\"Test method exists with correct signature.\"\"\"
    instance = ClassName()
    result = instance.method(param1="value", param2=123)
    assert isinstance(result, dict)
"""

    def _summarize_artifacts(self, artifacts: Dict[str, Any]) -> str:
        """Summarize artifacts for prompt with detailed signatures.

        Args:
            artifacts: expectedArtifacts from manifest

        Returns:
            Human-readable summary with full signatures
        """
        if not artifacts:
            return "No artifacts specified"

        file_path = artifacts.get("file", "unknown")
        contains = artifacts.get("contains", [])

        lines = [f"File: {file_path}", ""]

        for artifact in contains:
            artifact_type = artifact.get("type", "unknown")
            name = artifact.get("name", "unnamed")

            if artifact_type == "function":
                # Format function signature
                args = artifact.get("args", [])
                returns = artifact.get("returns", "None")
                class_name = artifact.get("class")

                args_str = ", ".join(
                    [f"{a['name']}: {a.get('type', 'Any')}" for a in args]
                )

                if class_name:
                    lines.append(
                        f"  - Method: {class_name}.{name}({args_str}) -> {returns}"
                    )
                else:
                    lines.append(f"  - Function: {name}({args_str}) -> {returns}")

            elif artifact_type == "class":
                # Format class with bases
                bases = artifact.get("bases", [])
                bases_str = f"({', '.join(bases)})" if bases else ""
                lines.append(f"  - Class: {name}{bases_str}")

            elif artifact_type == "attribute":
                # Format attribute
                attr_type = artifact.get("attributeType", "Any")
                class_name = artifact.get("class")
                if class_name:
                    lines.append(f"  - Attribute: {class_name}.{name}: {attr_type}")
                else:
                    lines.append(f"  - Attribute: {name}: {attr_type}")

            else:
                lines.append(f"  - {artifact_type}: {name}")

        return "\n".join(lines)
