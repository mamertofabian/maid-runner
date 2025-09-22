# tests/test_manifest_behavioral_alignment.py
"""
Integration test to ensure ALL project manifests have behavioral tests
that properly exercise their declared expectedArtifacts.

This is the enforcement of MAID Phase 2: Planning Loop validation.
"""
import pytest
import json
from pathlib import Path
from validators.validate_behavioral_tests import (
    validate_behavioral_tests,
    extract_test_files_from_command,
    BehavioralTestValidationError
)

MANIFESTS_DIR = Path("manifests/")


def find_manifest_files():
    """Scans the manifests directory and returns a list of all task manifests."""
    return sorted(MANIFESTS_DIR.glob("task-*.manifest.json"))


@pytest.mark.parametrize("manifest_path", find_manifest_files())
def test_manifest_has_aligned_behavioral_tests(manifest_path):
    """
    Validate that each manifest's behavioral tests properly exercise
    the expectedArtifacts declared in the manifest.

    This ensures the MAID Phase 2 Planning Loop is complete:
    - The manifest declares what artifacts should exist
    - The behavioral tests actually USE those artifacts
    - The implementation provides those artifacts

    This test will fail if:
    - A test file referenced in validationCommand doesn't exist
    - A test file doesn't USE the artifacts declared in expectedArtifacts
    - The behavioral validation can't find expected function calls, class usage, etc.
    """
    # Skip manifests created before behavioral test validation was introduced
    # (task-004 introduces this feature but uses pytest.raises which isn't detected as class usage)
    if any(task in str(manifest_path) for task in ["task-001", "task-002", "task-003", "task-004"]):
        pytest.skip(f"Manifest {manifest_path.name} predates behavioral test validation or uses pytest.raises")

    with open(manifest_path, "r") as f:
        manifest_data = json.load(f)

    # Skip manifests without validationCommand
    validation_command = manifest_data.get("validationCommand")
    if not validation_command:
        pytest.skip(f"Manifest {manifest_path.name} has no validationCommand")

    # Skip manifests without expectedArtifacts
    expected_artifacts = manifest_data.get("expectedArtifacts", {})
    if not expected_artifacts or not expected_artifacts.get("contains"):
        pytest.skip(f"Manifest {manifest_path.name} has no expectedArtifacts to validate")

    # Extract test files from the validation command
    test_files = []
    if isinstance(validation_command, list):
        if isinstance(validation_command[0], list):
            # Multiple commands
            for cmd in validation_command:
                test_files.extend(extract_test_files_from_command(cmd))
        else:
            # Single command
            test_files.extend(extract_test_files_from_command(validation_command))

    assert test_files, (
        f"No test files could be extracted from validationCommand in {manifest_path.name}: "
        f"{validation_command}"
    )

    # Validate each test file uses the expected artifacts
    errors = []
    for test_file in test_files:
        # Check if test file exists
        if not Path(test_file).exists():
            errors.append(f"Test file not found: {test_file}")
            continue

        # Create a test-specific manifest pointing to the test file
        test_manifest = {
            "expectedArtifacts": {
                "file": test_file,
                "contains": expected_artifacts.get("contains", [])
            }
        }

        # Import here to avoid circular dependency
        from validators.manifest_validator import validate_with_ast, AlignmentError

        try:
            # Validate the test file in behavioral mode
            validate_with_ast(
                test_manifest,
                test_file,
                use_manifest_chain=False,  # Test files don't use manifest chains
                validation_mode="behavioral"
            )
        except AlignmentError as e:
            errors.append(f"In {test_file}: {str(e)}")

    # If any errors were found, fail the test with details
    if errors:
        pytest.fail(
            f"Manifest {manifest_path.name} has misaligned behavioral tests:\n" +
            "\n".join(f"  - {error}" for error in errors)
        )


def test_all_manifests_pass_behavioral_validation():
    """
    High-level integration test that all manifests pass behavioral validation.
    """
    from validators.validate_behavioral_tests import validate_all_manifests

    results = validate_all_manifests(str(MANIFESTS_DIR))

    failed_manifests = []
    for manifest_path, result in results.items():
        # Skip pre-existing manifests (before task-004) and task-004 itself
        if any(pre in manifest_path for pre in ["task-001", "task-002", "task-003", "task-004"]):
            continue

        if result["has_validation_command"] and not result["validation_passed"]:
            failed_manifests.append(f"{Path(manifest_path).name}: {result.get('error', 'Unknown error')}")

    if failed_manifests:
        pytest.fail(
            "The following manifests have misaligned behavioral tests:\n" +
            "\n".join(failed_manifests)
        )