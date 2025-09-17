# tests/test_ast_validator.py
import pytest
import json
from pathlib import Path
from validators.manifest_validator import validate_with_ast, AlignmentError

# A dummy test file that our validator will analyze.
DUMMY_TEST_CODE = """
import pytest
from my_app.models import User

def test_user_creation():
    user = User(name="Alice", user_id=123)
    assert user.name == "Alice"
    assert user.user_id == 123
"""

def test_ast_validation_passes_when_aligned(tmp_path: Path):
    """
    Tests that validation succeeds when the manifest artifacts are present in the test code.
    """
    # 1. Create a temporary directory and the dummy test file.
    test_file = tmp_path / "test_user.py"
    test_file.write_text(DUMMY_TEST_CODE)

    # 2. This manifest is correctly aligned with the code above.
    aligned_manifest = {
        "expectedArtifacts": {
            "file": "my_app/models.py",
            "contains": [
                {"type": "class", "name": "User"},
                {"type": "attribute", "name": "name", "class": "User"},
                {"type": "attribute", "name": "user_id", "class": "User"}
            ]
        }
    }

    # 3. The function should run without raising an error.
    validate_with_ast(aligned_manifest, str(test_file))

def test_ast_validation_fails_when_misaligned(tmp_path: Path):
    """
    Tests that validation raises an AlignmentError when an artifact is missing.
    """
    # 1. Create the same dummy test file.
    test_file = tmp_path / "test_user.py"
    test_file.write_text(DUMMY_TEST_CODE)

    # 2. This manifest is MISALIGNED. It expects an 'email' attribute
    #    that is NOT mentioned in the test code.
    misaligned_manifest = {
        "expectedArtifacts": {
            "file": "my_app/models.py",
            "contains": [
                {"type": "class", "name": "User"},
                {"type": "attribute", "name": "name", "class": "User"},
                {"type": "attribute", "name": "email", "class": "User"} # This is the problem
            ]
        }
    }

    # 3. Assert that our custom AlignmentError is raised.
    with pytest.raises(AlignmentError, match="Artifact 'email' not found"):
        validate_with_ast(misaligned_manifest, str(test_file))