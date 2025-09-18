import pytest
import json
from pathlib import Path
from validators.manifest_validator import validate_schema, validate_with_ast

SCHEMA_PATH = Path("validators/schemas/manifest.schema.json")
MANIFESTS_DIR = Path("manifests/")


def find_manifest_files():
    """Scans the manifests directory and returns a list of all task manifests."""
    return sorted(MANIFESTS_DIR.glob("task-*.manifest.json"))


# Pytest will automatically run this test for every file found by the find_manifest_files function
@pytest.mark.parametrize("manifest_path", find_manifest_files())
def test_manifest_is_structurally_sound_and_aligned(manifest_path):
    """
    A single, data-driven test that validates any given manifest.
    It performs both schema and AST alignment validation.
    """
    with open(manifest_path, "r") as f:
        manifest_data = json.load(f)

    # 1. Validate the manifest's own structure
    validate_schema(manifest_data, str(SCHEMA_PATH))

    # 2. Validate the manifest against its implementation code using the merging validator
    implementation_file = manifest_data["expectedArtifacts"]["file"]
    assert Path(
        implementation_file
    ).exists(), f"Implementation file {implementation_file} not found."

    # The validator now uses the manifest's own history to check it
    validate_with_ast(manifest_data, implementation_file, use_manifest_chain=True)
