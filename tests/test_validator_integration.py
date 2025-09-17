import pytest
import json
from pathlib import Path
from validators.manifest_validator import validate_schema, validate_with_ast

# Define paths to our REAL project files
SCHEMA_PATH = Path("validators/schemas/manifest.schema.json")
TASK_001_MANIFEST_PATH = Path("manifests/task-001.nanifest.json")
TASK_002_MANIFEST_PATH = Path("manifests/task-002.manifest.json")

def test_task_001_manifest_is_valid_against_schema():
    """
    Tests that our real manifest for the schema validator conforms to the schema.
    """
    with open(TASK_001_MANIFEST_PATH, "r") as f:
        manifest_data = json.load(f)

    # This should pass without raising an error
    validate_schema(manifest_data, str(SCHEMA_PATH))

def test_task_001_manifest_is_aligned_with_its_test_file():
    """
    Tests that the task-001 manifest is aligned with its test file,
    verifying that validate_schema function is actually tested.
    """
    with open(TASK_001_MANIFEST_PATH, "r") as f:
        manifest_data = json.load(f)

    # Get the test file path from the manifest
    test_file_to_check = manifest_data["readonlyFiles"][0]  # Should be "tests/test_manifest_validator.py"

    assert Path(test_file_to_check).exists()

    # This should pass without raising an AlignmentError
    validate_with_ast(manifest_data, test_file_to_check)

def test_task_002_manifest_is_valid_against_schema():
    """
    Tests that our real manifest for the AST validator conforms to the schema.
    """
    with open(TASK_002_MANIFEST_PATH, "r") as f:
        manifest_data = json.load(f)
    
    # This should pass without raising an error
    validate_schema(manifest_data, str(SCHEMA_PATH))

def test_task_002_manifest_is_aligned_with_its_test_file():
    """
    Tests that our real manifest for the AST validator is aligned with its own
    test file using the AST validator itself. This is the self-hosting test.
    """
    with open(TASK_002_MANIFEST_PATH, "r") as f:
        manifest_data = json.load(f)
        
    # Get the test file path directly from the manifest
    # Assumes the test is run from the project root directory
    test_file_to_check = manifest_data["readonlyFiles"][0] # Should be "tests/test_ast_validator.py"
    
    assert Path(test_file_to_check).exists()

    # This should pass without raising an AlignmentError
    validate_with_ast(manifest_data, test_file_to_check)