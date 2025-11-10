"""Validation Runner - Wraps maid-runner CLI calls."""

import json
import subprocess
from dataclasses import dataclass
from typing import List


@dataclass
class ValidationResult:
    """Result of validation operation."""

    success: bool
    stdout: str
    stderr: str
    errors: List[str]


class ValidationRunner:
    """Wraps maid-runner CLI for validation operations."""

    def __init__(self):
        """Initialize validation runner."""
        pass

    def validate_manifest(
        self, manifest_path: str, use_chain: bool = False
    ) -> ValidationResult:
        """Run manifest validation using maid-runner.

        Args:
            manifest_path: Path to manifest file
            use_chain: Whether to use manifest chain validation

        Returns:
            ValidationResult with status and output
        """
        cmd = ["maid", "validate", manifest_path]
        if use_chain:
            cmd.append("--use-manifest-chain")

        try:
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=300)

            return ValidationResult(
                success=result.returncode == 0,
                stdout=result.stdout,
                stderr=result.stderr,
                errors=(
                    self._parse_errors(result.stderr) if result.returncode != 0 else []
                ),
            )
        except subprocess.TimeoutExpired:
            return ValidationResult(
                success=False,
                stdout="",
                stderr="Validation timed out",
                errors=["Timeout"],
            )
        except Exception as e:
            return ValidationResult(
                success=False, stdout="", stderr=str(e), errors=[str(e)]
            )

    def run_behavioral_tests(self, manifest_path: str) -> ValidationResult:
        """Execute pytest for behavioral tests.

        Args:
            manifest_path: Path to manifest file

        Returns:
            ValidationResult with test execution status
        """
        # Load manifest to get validation command
        try:
            with open(manifest_path) as f:
                manifest = json.load(f)

            validation_cmd = manifest.get("validationCommand", [])
            if not validation_cmd:
                return ValidationResult(
                    success=False,
                    stdout="",
                    stderr="No validationCommand in manifest",
                    errors=["Missing validationCommand"],
                )

            result = subprocess.run(
                validation_cmd, capture_output=True, text=True, timeout=300
            )

            return ValidationResult(
                success=result.returncode == 0,
                stdout=result.stdout,
                stderr=result.stderr,
                errors=(
                    self._parse_test_failures(result.stdout)
                    if result.returncode != 0
                    else []
                ),
            )
        except FileNotFoundError:
            return ValidationResult(
                success=False,
                stdout="",
                stderr=f"Manifest not found: {manifest_path}",
                errors=["File not found"],
            )
        except Exception as e:
            return ValidationResult(
                success=False, stdout="", stderr=str(e), errors=[str(e)]
            )

    def _parse_errors(self, stderr: str) -> List[str]:
        """Parse error messages from stderr."""
        # Simple implementation - extract error lines
        errors = []
        for line in stderr.split("\n"):
            if "error" in line.lower() or "✗" in line:
                errors.append(line.strip())
        return errors

    def _parse_test_failures(self, output: str) -> List[str]:
        """Parse test failure messages from pytest output."""
        failures = []
        for line in output.split("\n"):
            if "FAILED" in line or "ERROR" in line:
                failures.append(line.strip())
        return failures
