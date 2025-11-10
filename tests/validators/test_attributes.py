"""
Tests for variable tracking and attribute collection in the manifest validator.

This module tests how the validator tracks:
- Variable assignments to class instances
- Attribute access through variables
- Multiple variables referring to the same class
- Chained assignments
- Unknown variable handling
"""

import pytest
import sys
from pathlib import Path

# Add parent directories to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from maid_runner.validators.manifest_validator import validate_with_ast, AlignmentError


def test_variable_to_class_tracking(tmp_path: Path):
    """Test that variable assignments to class instances are tracked."""
    code = """
class User:
    def __init__(self):
        self.name = ""
        self.email = ""

def test_function():
    user = User()
    user.name = "Alice"
    user.email = "alice@example.com"
    user.age = 25
"""
    test_file = tmp_path / "variable_tracking.py"
    test_file.write_text(code)

    manifest = {
        "expectedArtifacts": {
            "contains": [
                {"type": "class", "name": "User"},
                {"type": "function", "name": "test_function"},
                {"type": "attribute", "name": "name", "class": "User"},
                {"type": "attribute", "name": "email", "class": "User"},
                {"type": "attribute", "name": "age", "class": "User"},
            ]
        }
    }
    # Should pass - attributes accessed through variable are tracked
    validate_with_ast(manifest, str(test_file))


def test_attribute_collection_through_variables(tmp_path: Path):
    """Test attribute access through different variable names."""
    code = """
class Product:
    pass

def process():
    item = Product()
    item.sku = "ABC123"
    item.price = 99.99

    product = Product()
    product.name = "Widget"
    product.stock = 100
"""
    test_file = tmp_path / "attributes.py"
    test_file.write_text(code)

    manifest = {
        "expectedArtifacts": {
            "contains": [
                {"type": "class", "name": "Product"},
                {"type": "function", "name": "process"},
                {"type": "attribute", "name": "sku", "class": "Product"},
                {"type": "attribute", "name": "price", "class": "Product"},
                {"type": "attribute", "name": "name", "class": "Product"},
                {"type": "attribute", "name": "stock", "class": "Product"},
            ]
        }
    }
    # Should pass - attributes from different variable names are tracked
    validate_with_ast(manifest, str(test_file))


def test_multiple_variables_same_class(tmp_path: Path):
    """Test multiple variable names referring to the same class."""
    code = """
class Database:
    pass

def setup():
    db1 = Database()
    db1.connection = "conn1"

    db2 = Database()
    db2.pool_size = 10

    primary_db = Database()
    primary_db.host = "localhost"
"""
    test_file = tmp_path / "multiple_vars.py"
    test_file.write_text(code)

    manifest = {
        "expectedArtifacts": {
            "contains": [
                {"type": "class", "name": "Database"},
                {"type": "function", "name": "setup"},
                {"type": "attribute", "name": "connection", "class": "Database"},
                {"type": "attribute", "name": "pool_size", "class": "Database"},
                {"type": "attribute", "name": "host", "class": "Database"},
            ]
        }
    }
    # Should pass - all attributes are associated with Database class
    validate_with_ast(manifest, str(test_file))


def test_chained_assignments(tmp_path: Path):
    """Test chained variable assignments (x = y = Class())."""
    code = """
class Cache:
    pass

def init():
    cache1 = cache2 = Cache()
    cache1.size = 100
    cache2.ttl = 3600
"""
    test_file = tmp_path / "chained.py"
    test_file.write_text(code)

    manifest = {
        "expectedArtifacts": {
            "contains": [
                {"type": "class", "name": "Cache"},
                {"type": "function", "name": "init"},
                {"type": "attribute", "name": "size", "class": "Cache"},
                {"type": "attribute", "name": "ttl", "class": "Cache"},
            ]
        }
    }
    # Should pass - chained assignments track both variables
    validate_with_ast(manifest, str(test_file))


def test_attribute_on_unknown_variable(tmp_path: Path):
    """Test that attributes on unknown variables are ignored."""
    code = """
class MyClass:
    pass

def process():
    known = MyClass()
    known.valid_attr = "tracked"

    # unknown_var is not assigned to any class
    unknown_var.ignored_attr = "not tracked"
"""
    test_file = tmp_path / "unknown_var.py"
    test_file.write_text(code)

    manifest = {
        "expectedArtifacts": {
            "contains": [
                {"type": "class", "name": "MyClass"},
                {"type": "function", "name": "process"},
                {"type": "attribute", "name": "valid_attr", "class": "MyClass"},
                # ignored_attr should NOT be tracked
            ]
        }
    }
    # Should pass - attributes on unknown variables are ignored
    validate_with_ast(manifest, str(test_file))


def test_missing_attribute_raises_alignment_error(tmp_path: Path):
    """Test that AlignmentError is raised when expected attribute is missing."""
    code = """
class User:
    def __init__(self):
        self.name = ""
        self.email = ""
"""
    test_file = tmp_path / "missing_attr.py"
    test_file.write_text(code)

    manifest = {
        "expectedArtifacts": {
            "contains": [
                {"type": "class", "name": "User"},
                {"type": "attribute", "name": "name", "class": "User"},
                {"type": "attribute", "name": "email", "class": "User"},
                {
                    "type": "attribute",
                    "name": "age",
                    "class": "User",
                },  # This doesn't exist
            ]
        }
    }

    # Should raise AlignmentError for missing attribute
    with pytest.raises(AlignmentError, match="age"):
        validate_with_ast(manifest, str(test_file))

    # Also verify AlignmentError is properly instantiated
    error = AlignmentError("Test message")
    assert isinstance(error, AlignmentError)
    assert isinstance(error, Exception)
