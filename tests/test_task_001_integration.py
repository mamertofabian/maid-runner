import json
from pathlib import Path
from validators.manifest_validator import validate_schema, validate_with_ast

# Define paths to our REAL project files
SCHEMA_PATH = Path("validators/schemas/manifest.schema.json")
TASK_001_MANIFEST_PATH = Path("manifests/task-001.nanifest.json")


def test_task_001_manifest_is_valid_against_schema():
    """
    Tests that our real manifest for the schema validator conforms to the schema.
    """
    with open(TASK_001_MANIFEST_PATH, "r") as f:
        manifest_data = json.load(f)

    # This should pass without raising an error
    validate_schema(manifest_data, str(SCHEMA_PATH))


def test_task_001_manifest_is_aligned_with_its_implementation():
    """
    Tests that the task-001 manifest is aligned with its implementation file,
    verifying that validate_schema function has the expected signature.
    Note: This test validates the specific artifacts that task-001 was responsible for creating.
    """
    with open(TASK_001_MANIFEST_PATH, "r") as f:
        manifest_data = json.load(f)

    # Get the implementation file path from the manifest
    implementation_file = manifest_data["expectedArtifacts"][
        "file"
    ]  # Should be "validators/manifest_validator.py"

    assert Path(implementation_file).exists()

    # This should pass without raising an AlignmentError
    # Note: Since this was a "creatableFiles" task, it should have created the complete file
    # Use manifest chain to validate against cumulative state
    validate_with_ast(manifest_data, implementation_file, use_manifest_chain=True)
