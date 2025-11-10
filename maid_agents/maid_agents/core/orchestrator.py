"""MAID Orchestrator - Coordinates the MAID workflow phases.

This module provides the core orchestration logic for executing the MAID workflow.
"""

import json
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Optional

from maid_agents.agents.manifest_architect import ManifestArchitect
from maid_agents.agents.test_designer import TestDesigner
from maid_agents.claude.cli_wrapper import ClaudeWrapper
from maid_agents.core.validation_runner import ValidationRunner


class WorkflowState(Enum):
    """Workflow state machine states."""

    INIT = "init"
    PLANNING = "planning"
    IMPLEMENTING = "implementing"
    REFACTORING = "refactoring"
    COMPLETE = "complete"
    FAILED = "failed"


@dataclass
class WorkflowResult:
    """Result of workflow execution."""

    success: bool
    manifest_path: str
    message: str


class MAIDOrchestrator:
    """Orchestrates the complete MAID workflow."""

    def __init__(
        self,
        claude: Optional[ClaudeWrapper] = None,
        manifest_architect: Optional[ManifestArchitect] = None,
        test_designer: Optional[TestDesigner] = None,
        validation_runner: Optional[ValidationRunner] = None,
    ):
        """Initialize orchestrator.

        Args:
            claude: Claude wrapper (creates default if None)
            manifest_architect: Manifest architect agent (creates default if None)
            test_designer: Test designer agent (creates default if None)
            validation_runner: Validation runner (creates default if None)
        """
        self._state = WorkflowState.INIT

        # Create default Claude wrapper if not provided
        if claude is None:
            claude = ClaudeWrapper(mock_mode=True)

        # Create agents with provided or default Claude wrapper
        self.manifest_architect = manifest_architect or ManifestArchitect(claude)
        self.test_designer = test_designer or TestDesigner(claude)
        self.validation_runner = validation_runner or ValidationRunner()

    def run_full_workflow(self, goal: str) -> WorkflowResult:
        """Execute complete MAID workflow from goal to integration.

        Args:
            goal: High-level goal description

        Returns:
            WorkflowResult with status and manifest path
        """
        # TODO: Implement workflow execution
        return WorkflowResult(
            success=False, manifest_path="", message="Not implemented"
        )

    def get_workflow_state(self) -> WorkflowState:
        """Get current workflow state.

        Returns:
            Current WorkflowState
        """
        return self._state

    def run_planning_loop(self, goal: str, max_iterations: int = 10) -> dict:
        """Execute planning loop: manifest creation + test generation with validation.

        Args:
            goal: High-level goal description
            max_iterations: Maximum planning iterations

        Returns:
            Dict with planning loop results
        """
        self._state = WorkflowState.PLANNING

        # Determine next task number by counting existing manifests
        task_number = self._get_next_task_number()

        iteration = 0
        last_error = None

        while iteration < max_iterations:
            iteration += 1

            # Step 1: Create manifest using ManifestArchitect
            manifest_result = self.manifest_architect.create_manifest(
                goal=goal, task_number=task_number
            )

            if not manifest_result["success"]:
                last_error = f"Manifest creation failed: {manifest_result['error']}"
                continue

            manifest_path = manifest_result["manifest_path"]
            manifest_data = manifest_result["manifest_data"]

            # Save manifest to disk
            try:
                manifest_file = Path(manifest_path)
                manifest_file.parent.mkdir(parents=True, exist_ok=True)
                with open(manifest_file, "w") as f:
                    json.dump(manifest_data, f, indent=2)
            except Exception as e:
                last_error = f"Failed to save manifest: {e}"
                continue

            # Step 2: Create tests using TestDesigner
            test_result = self.test_designer.create_tests(
                manifest_path=str(manifest_file)
            )

            if not test_result["success"]:
                last_error = f"Test generation failed: {test_result['error']}"
                continue

            test_paths = test_result["test_paths"]
            test_code = test_result["test_code"]

            # Save test files to disk
            try:
                for test_path in test_paths:
                    test_file = Path(test_path)
                    test_file.parent.mkdir(parents=True, exist_ok=True)
                    with open(test_file, "w") as f:
                        f.write(test_code)
            except Exception as e:
                last_error = f"Failed to save test files: {e}"
                continue

            # Step 3: Run behavioral validation
            # Validate that tests USE the declared artifacts (behavioral mode)
            # With the validator fix, this now works without implementation file existing
            validation_result = self._validate_behavioral_tests(
                manifest_path=str(manifest_file)
            )

            if validation_result["success"]:
                # Planning loop succeeded!
                return {
                    "success": True,
                    "manifest_path": str(manifest_file),
                    "test_paths": [str(p) for p in test_paths],
                    "iterations": iteration,
                    "error": None,
                }
            else:
                # Validation failed - prepare error feedback for next iteration
                last_error = (
                    f"Behavioral validation failed: {validation_result['error']}"
                )
                continue

        # Max iterations reached without success
        return {
            "success": False,
            "manifest_path": None,
            "test_paths": [],
            "iterations": iteration,
            "error": f"Planning loop failed after {max_iterations} iterations. Last error: {last_error}",
        }

    def _validate_behavioral_tests(self, manifest_path: str) -> dict:
        """Run behavioral validation on tests to ensure they USE declared artifacts.

        Args:
            manifest_path: Path to manifest file

        Returns:
            Dict with success status and error message
        """
        import subprocess

        # Run maid validate with behavioral mode
        # This validates tests USE artifacts without requiring implementation to exist
        cmd = [
            "maid",
            "validate",
            manifest_path,
            "--validation-mode",
            "behavioral",
            "--use-manifest-chain",
        ]

        try:
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=60)

            if result.returncode == 0:
                return {"success": True, "error": None}
            else:
                return {
                    "success": False,
                    "error": f"{result.stderr}\n{result.stdout}",
                }
        except subprocess.TimeoutExpired:
            return {"success": False, "error": "Behavioral validation timed out"}
        except Exception as e:
            return {"success": False, "error": f"Validation error: {e}"}

    def _get_next_task_number(self) -> int:
        """Determine next task number by counting existing manifests.

        Returns:
            Next available task number
        """
        manifests_dir = Path("manifests")
        if not manifests_dir.exists():
            return 1

        # Find all task-*.manifest.json files
        manifest_files = list(manifests_dir.glob("task-*.manifest.json"))

        if not manifest_files:
            return 1

        # Extract task numbers and find max
        task_numbers = []
        for manifest_file in manifest_files:
            # Extract number from filename like "task-042.manifest.json"
            try:
                num_str = manifest_file.stem.split("-")[1].split(".")[0]
                task_numbers.append(int(num_str))
            except (IndexError, ValueError):
                continue

        return max(task_numbers) + 1 if task_numbers else 1

    def run_implementation_loop(
        self, manifest_path: str, max_iterations: int = 20
    ) -> dict:
        """Execute implementation loop: code generation until tests pass.

        Args:
            manifest_path: Path to manifest file
            max_iterations: Maximum implementation iterations

        Returns:
            Dict with implementation loop results
        """
        self._state = WorkflowState.IMPLEMENTING

        # TODO: Implement full implementation loop
        # 1. Run tests (should fail initially - red phase)
        # 2. Generate code using Developer agent
        # 3. Run tests again
        # 4. If failed, extract errors and iterate
        # 5. Validate manifest compliance

        return {"success": False, "iterations": 0, "error": "Not yet implemented"}

    def _handle_error(self, error: Exception) -> dict:
        """Handle errors during workflow execution.

        Args:
            error: Exception that occurred

        Returns:
            Dict with error information
        """
        error_type = type(error).__name__
        error_message = str(error)

        return {
            "error": error_message,
            "error_type": error_type,
            "message": f"{error_type}: {error_message}",
        }
