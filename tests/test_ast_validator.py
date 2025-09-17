# tests/test_ast_validator.py
import pytest
from pathlib import Path
from validators.manifest_validator import validate_with_ast, AlignmentError

# We'll use a more complex dummy file now
DUMMY_TEST_CODE = """
import pytest
from my_app.models import User, Product

def test_user_creation():
    # Using a standard variable name
    user = User(name="Alice", user_id=123)
    assert user.name == "Alice"

def test_admin_user_creation():
    # Using a different variable name for the SAME class
    admin_user = User(name="Bob", user_id=456)
    assert admin_user.user_id == 456

def test_product_creation():
    # Using a completely different class
    item = Product(sku="abc", price=99.99)
    assert item.sku == "abc"
"""

def test_ast_validation_passes_when_aligned(tmp_path: Path):
    """Tests that a correctly aligned manifest passes."""
    test_file = tmp_path / "test_complex.py"
    test_file.write_text(DUMMY_TEST_CODE)

    aligned_manifest = {
        "expectedArtifacts": { "contains": [
            {"type": "class", "name": "User"},
            {"type": "class", "name": "Product"},
            {"type": "attribute", "name": "name", "class": "User"},
            {"type": "attribute", "name": "user_id", "class": "User"},
            {"type": "attribute", "name": "sku", "class": "Product"}
        ]}
    }
    # Should not raise an error
    validate_with_ast(aligned_manifest, str(test_file))

def test_ast_validation_fails_on_missing_attribute(tmp_path: Path):
    """Tests that a misaligned manifest (missing attribute) fails."""
    test_file = tmp_path / "test_complex.py"
    test_file.write_text(DUMMY_TEST_CODE)

    misaligned_manifest = {
        "expectedArtifacts": { "contains": [
            {"type": "class", "name": "User"},
            # The 'email' attribute is NOT in the test code
            {"type": "attribute", "name": "email", "class": "User"}
        ]}
    }
    with pytest.raises(AlignmentError, match="Artifact 'email' not found"):
        validate_with_ast(misaligned_manifest, str(test_file))

def test_ast_validation_fails_on_missing_class(tmp_path: Path):
    """Tests that a misaligned manifest (missing class) fails."""
    test_file = tmp_path / "test_complex.py"
    test_file.write_text(DUMMY_TEST_CODE)

    misaligned_manifest = {
        "expectedArtifacts": { "contains": [
            # The 'Order' class is NOT in the test code
            {"type": "class", "name": "Order"}
        ]}
    }
    with pytest.raises(AlignmentError, match="Artifact 'Order' not found"):
        validate_with_ast(misaligned_manifest, str(test_file))
