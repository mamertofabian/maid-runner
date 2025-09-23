import pytest
import json
import sys
from pathlib import Path

# Add parent directory to path to import modules
sys.path.insert(0, str(Path(__file__).parent.parent))

from validators.manifest_validator import validate_schema, validate_with_ast
from validate_manifest import extract_test_files_from_command, validate_behavioral_tests

SCHEMA_PATH = Path("validators/schemas/manifest.schema.json")
MANIFESTS_DIR = Path("manifests/")


def find_manifest_files():
    """Scans the manifests directory and returns a list of all task manifests."""
    return sorted(MANIFESTS_DIR.glob("task-*.manifest.json"))


# Pytest will automatically run this test for every file found by the find_manifest_files function
@pytest.mark.parametrize("manifest_path", find_manifest_files())
def test_manifest_is_structurally_sound_and_aligned(manifest_path, caplog):
    """
    A single, data-driven test that validates any given manifest.
    It performs both schema and AST alignment validation.
    """
    import logging
    caplog.set_level(logging.INFO)

    # Log the manifest being tested
    manifest_name = manifest_path.name
    print(f"\n{'='*80}")
    print(f"VALIDATING: {manifest_name}")
    print(f"{'='*80}")

    with open(manifest_path, "r") as f:
        manifest_data = json.load(f)

    goal = manifest_data.get("goal", "No goal specified")
    print(f"Goal: {goal[:100]}..." if len(goal) > 100 else f"Goal: {goal}")

    # 1. Validate the manifest's own structure
    print(f"\n[Step 1] Validating manifest structure...")
    validate_schema(manifest_data, str(SCHEMA_PATH))
    print(f"         ✓ Manifest structure valid")

    # 2. Validate the manifest against its behavioral test (validationCommand)
    validation_command = manifest_data.get("validationCommand", [])
    if validation_command:
        test_files = extract_test_files_from_command(validation_command)
        if test_files:
            print(f"\n[Step 2] Validating behavioral tests...")
            print(f"         Command: {' '.join(validation_command)}")
            print(f"         Test files: {', '.join(test_files)}")

            # ALL manifests should pass behavioral validation - no exceptions
            validate_behavioral_tests(manifest_data, test_files, use_manifest_chain=False)
            print(f"         ✓ Behavioral tests properly exercise declared artifacts")
        else:
            print(f"         ⚠ No test files extracted from command")
    else:
        print(f"\n[Step 2] No validation command - skipping behavioral test validation")

    # 3. Validate the manifest against its implementation code using the merging validator
    implementation_file = manifest_data["expectedArtifacts"]["file"]
    print(f"\n[Step 3] Validating implementation...")
    print(f"         File: {implementation_file}")

    assert Path(
        implementation_file
    ).exists(), f"Implementation file {implementation_file} not found."

    # The validator now uses the manifest's own history to check it
    validate_with_ast(manifest_data, implementation_file, use_manifest_chain=True)

    # Check expected artifacts for details
    artifacts = manifest_data["expectedArtifacts"].get("contains", [])
    artifact_types = {}
    for artifact in artifacts:
        artifact_type = artifact.get("type", "unknown")
        artifact_types[artifact_type] = artifact_types.get(artifact_type, 0) + 1

    artifacts_summary = ", ".join([f"{count} {type}(s)" for type, count in artifact_types.items()])
    print(f"         ✓ Implementation contains: {artifacts_summary if artifacts_summary else 'no specific artifacts'}")
    print(f"\n✅ PASSED: {manifest_name}")
