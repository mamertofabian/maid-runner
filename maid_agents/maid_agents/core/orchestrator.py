"""MAID Orchestrator - Coordinates the MAID workflow phases.

This module provides the core orchestration logic for executing the MAID workflow.
"""

import json
import logging
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Optional

from maid_agents.agents.manifest_architect import ManifestArchitect
from maid_agents.agents.refiner import Refiner
from maid_agents.agents.test_designer import TestDesigner
from maid_agents.claude.cli_wrapper import ClaudeWrapper
from maid_agents.core.validation_runner import ValidationRunner

logger = logging.getLogger(__name__)

# Maximum file size for generated code (1MB)
MAX_FILE_SIZE = 1_000_000


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
        dry_run: bool = False,
    ):
        """Initialize orchestrator.

        Args:
            claude: Claude wrapper (creates default if None)
            manifest_architect: Manifest architect agent (creates default if None)
            test_designer: Test designer agent (creates default if None)
            validation_runner: Validation runner (creates default if None)
            dry_run: If True, skip all file write operations (for testing)
        """
        self._state = WorkflowState.INIT
        self.dry_run = dry_run

        # Create default Claude wrapper if not provided
        if claude is None:
            if dry_run:
                # In dry_run mode, mock is appropriate for testing
                claude = ClaudeWrapper(mock_mode=True)
                logger.info(
                    "🧪 TEST MODE: Using mock Claude wrapper (dry_run=True). "
                    "No real API calls will be made."
                )
            else:
                # In production mode, require explicit Claude instance
                raise ValueError(
                    "Production mode requires explicit Claude instance. "
                    "Pass a ClaudeWrapper with mock_mode=False to __init__(), "
                    "or use dry_run=True for testing without API calls."
                )

        # Store Claude wrapper for use by dynamically created agents
        self.claude = claude

        # Create agents with provided or default Claude wrapper
        self.manifest_architect = manifest_architect or ManifestArchitect(claude)
        self.test_designer = test_designer or TestDesigner(claude)
        self.validation_runner = validation_runner or ValidationRunner()

    def _validate_safe_path(self, path: str) -> Path:
        """Validate that a path is safe and within the project directory.

        Args:
            path: Path string to validate

        Returns:
            Resolved Path object

        Raises:
            ValueError: If path is outside project directory
        """
        resolved_path = Path(path).resolve()
        project_dir = Path.cwd().resolve()

        try:
            # Check if the path is relative to the project directory
            resolved_path.relative_to(project_dir)
            return resolved_path
        except ValueError:
            raise ValueError(
                f"Path '{path}' is outside project directory. "
                f"Only paths within {project_dir} are allowed."
            )

    def run_full_workflow(self, goal: str) -> WorkflowResult:
        """Execute complete MAID workflow from goal to integration.

        Args:
            goal: High-level goal description

        Returns:
            WorkflowResult with status and manifest path
        """
        # Phase 1-2: Planning Loop (manifest + tests)
        planning_result = self.run_planning_loop(goal=goal)

        if not planning_result["success"]:
            return WorkflowResult(
                success=False,
                manifest_path="",
                message=f"Planning failed: {planning_result['error']}",
            )

        manifest_path = planning_result["manifest_path"]

        # Phase 3: Implementation Loop (code generation)
        impl_result = self.run_implementation_loop(manifest_path=manifest_path)

        if not impl_result["success"]:
            return WorkflowResult(
                success=False,
                manifest_path=manifest_path,
                message=f"Implementation failed: {impl_result['error']}",
            )

        # Success! Workflow complete
        return WorkflowResult(
            success=True,
            manifest_path=manifest_path,
            message=f"Workflow complete! Manifest: {manifest_path}",
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

            # Save manifest to disk (skip in dry_run mode)
            manifest_file = Path(manifest_path)
            if not self.dry_run:
                try:
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

            # Save test files to disk (skip in dry_run mode)
            if not self.dry_run:
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

        # Validate path before using it in subprocess
        try:
            validated_path = self._validate_safe_path(manifest_path)
        except ValueError as e:
            return {"success": False, "error": str(e)}

        # Run maid validate with behavioral mode
        # This validates tests USE artifacts without requiring implementation to exist
        cmd = [
            "maid",
            "validate",
            str(validated_path),
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

        # Step 1: Run tests initially (should fail - red phase of TDD)
        test_result = self.validation_runner.run_behavioral_tests(manifest_path)
        test_errors = test_result.stderr if not test_result.success else ""

        iteration = 0
        last_error = None

        while iteration < max_iterations:
            iteration += 1

            # Step 2: Generate code using Developer agent
            # Pass test errors from previous iteration (if any)
            from maid_agents.agents.developer import Developer

            developer = Developer(self.claude)
            impl_result = developer.implement(
                manifest_path=manifest_path, test_errors=test_errors
            )

            if not impl_result["success"]:
                last_error = f"Code generation failed: {impl_result['error']}"
                continue

            # Step 3: Write generated code to files
            generated_code = impl_result.get("code", "")
            files_modified = impl_result.get("files_modified", [])

            if not generated_code:
                last_error = "No code generated"
                continue

            if not files_modified:
                last_error = "No files to modify"
                continue

            # Write code to the target file(s) (skip in dry_run mode)
            # Developer returns single code block for the primary file
            if not self.dry_run:
                try:
                    # Check file size before writing
                    if len(generated_code) > MAX_FILE_SIZE:
                        last_error = (
                            f"Generated code exceeds maximum file size "
                            f"({len(generated_code)} > {MAX_FILE_SIZE} bytes)"
                        )
                        continue

                    # Validate path before writing
                    target_file = self._validate_safe_path(files_modified[0])
                    target_file.parent.mkdir(parents=True, exist_ok=True)

                    with open(target_file, "w") as f:
                        f.write(generated_code)

                except ValueError as e:
                    last_error = f"Invalid path {files_modified[0]}: {e}"
                    continue
                except Exception as e:
                    last_error = f"Failed to write code to {files_modified[0]}: {e}"
                    continue

            # Step 4: Run tests again
            test_result = self.validation_runner.run_behavioral_tests(manifest_path)

            if test_result.success:
                # Tests pass! Now validate manifest compliance
                validation_result = self.validation_runner.validate_manifest(
                    manifest_path, use_chain=True
                )

                if validation_result.success:
                    # Success! Tests pass and manifest validates
                    return {
                        "success": True,
                        "iterations": iteration,
                        "files_modified": files_modified,
                        "error": None,
                    }
                else:
                    # Tests pass but manifest validation fails
                    last_error = (
                        f"Manifest validation failed: {validation_result.stderr}"
                    )
                    continue
            else:
                # Tests still failing - extract errors for next iteration
                test_errors = f"{test_result.stdout}\n{test_result.stderr}"
                last_error = f"Tests failed: {'; '.join(test_result.errors)}"
                continue

        # Max iterations reached without success
        return {
            "success": False,
            "iterations": iteration,
            "error": f"Implementation loop failed after {max_iterations} iterations. Last error: {last_error}",
        }

    def run_refinement_loop(
        self, manifest_path: str, refinement_goal: str, max_iterations: int = 5
    ) -> dict:
        """Execute refinement loop: refine manifest and tests with validation.

        Args:
            manifest_path: Path to manifest file to refine
            refinement_goal: User's refinement objectives/goals
            max_iterations: Maximum refinement iterations

        Returns:
            Dict with refinement loop results
        """
        # Lazy-initialize refiner if needed
        if not hasattr(self, "refiner"):
            self.refiner = Refiner(self.claude)

        iteration = 0
        last_error = ""

        while iteration < max_iterations:
            iteration += 1

            # Step 1: Refine manifest and tests
            refine_result = self.refiner.refine(
                manifest_path=manifest_path,
                refinement_goal=refinement_goal,
                validation_feedback=last_error,
            )

            if not refine_result["success"]:
                last_error = f"Refinement failed: {refine_result['error']}"
                continue

            manifest_data = refine_result["manifest_data"]
            test_code_dict = refine_result["test_code"]

            # Step 2: Write refined files to disk (skip in dry_run mode)
            if not self.dry_run:
                try:
                    # Write manifest
                    manifest_file = Path(manifest_path)
                    manifest_file.parent.mkdir(parents=True, exist_ok=True)
                    with open(manifest_file, "w") as f:
                        json.dump(manifest_data, f, indent=2)

                    # Write test files
                    for test_path, test_code in test_code_dict.items():
                        test_file = Path(test_path)
                        test_file.parent.mkdir(parents=True, exist_ok=True)
                        with open(test_file, "w") as f:
                            f.write(test_code)

                except Exception as e:
                    last_error = f"Failed to write refined files: {e}"
                    continue

            # Step 3: Structural validation
            validation_result = self.validation_runner.validate_manifest(
                manifest_path, use_chain=True
            )

            if not validation_result.success:
                last_error = f"Structural validation failed: {validation_result.stderr}"
                continue

            # Step 4: Behavioral test validation
            behavioral_result = self._validate_behavioral_tests(manifest_path)

            if behavioral_result["success"]:
                # Refinement complete - both validations pass!
                return {
                    "success": True,
                    "iterations": iteration,
                    "improvements": refine_result.get("improvements", []),
                    "error": None,
                }
            else:
                # Behavioral validation failed - provide feedback for next iteration
                last_error = behavioral_result["output"]
                continue

        # Max iterations reached without success
        return {
            "success": False,
            "iterations": iteration,
            "error": f"Refinement loop failed after {max_iterations} iterations. Last error: {last_error}",
        }

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
