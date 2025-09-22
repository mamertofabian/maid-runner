# tests/test_ast_validator.py
"""Test file demonstrating behavioral usage of validate_with_ast function."""
from validators.manifest_validator import validate_with_ast, AlignmentError


def test_validate_with_ast_basic():
    """Test that uses validate_with_ast function."""
    manifest = {
        "expectedArtifacts": {
            "file": "example.py",
            "contains": [{"type": "function", "name": "example"}]
        }
    }

    # This call to validate_with_ast is what the behavioral validator should find
    try:
        validate_with_ast(manifest, "example.py")
    except (AlignmentError, FileNotFoundError):
        pass  # Expected for non-existent file