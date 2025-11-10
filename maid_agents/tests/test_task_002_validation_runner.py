"""
Behavioral tests for Task-002: ValidationRunner.

Tests the ValidationRunner class that wraps maid-runner CLI calls.
"""

import sys
from pathlib import Path

# Add maid_agents package to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from maid_agents.core.validation_runner import ValidationRunner, ValidationResult


def test_validation_result_creation():
    """Test ValidationResult can be instantiated."""
    result = ValidationResult(
        success=True, stdout="Validation passed", stderr="", errors=[]
    )

    assert isinstance(result.success, bool)
    assert isinstance(result.stdout, str)
    assert isinstance(result.stderr, str)
    assert isinstance(result.errors, list)


def test_validation_runner_instantiation():
    """Test ValidationRunner can be instantiated."""
    runner = ValidationRunner()
    assert runner is not None
    assert isinstance(runner, ValidationRunner)


def test_validate_manifest_method():
    """Test validate_manifest method exists and has correct signature."""
    runner = ValidationRunner()

    # Create a test manifest path
    manifest_path = "maid_agents/manifests/task-001-orchestrator-skeleton.manifest.json"

    # Call the method
    result = runner.validate_manifest(manifest_path, use_chain=False)

    # Validate return type
    assert isinstance(result, ValidationResult)
    assert hasattr(result, "success")
    assert hasattr(result, "stdout")
    assert hasattr(result, "stderr")


def test_validate_manifest_with_chain():
    """Test validate_manifest with use_chain=True."""
    runner = ValidationRunner()

    manifest_path = "maid_agents/manifests/task-001-orchestrator-skeleton.manifest.json"
    result = runner.validate_manifest(manifest_path, use_chain=True)

    assert isinstance(result, ValidationResult)


def test_run_behavioral_tests_method():
    """Test run_behavioral_tests method exists and has correct signature."""
    runner = ValidationRunner()

    manifest_path = "maid_agents/manifests/task-001-orchestrator-skeleton.manifest.json"

    # Call the method
    result = runner.run_behavioral_tests(manifest_path)

    # Validate return type
    assert isinstance(result, ValidationResult)
    assert hasattr(result, "success")
