"""
Test Task-024: Validator distinction between imports and definitions.

Tests the _ArtifactCollector class to ensure it properly distinguishes between:
- Imported classes (dependencies) - should NOT be in found_classes
- Defined classes (artifacts) - should BE in found_classes

These tests USE the _ArtifactCollector class from maid_runner.validators.manifest_validator
to verify that imports are not treated as defined artifacts.
"""

import ast

from maid_runner.validators.manifest_validator import _ArtifactCollector


def test_imported_classes_not_in_found_classes():
    """Test that imported classes are NOT added to found_classes."""
    # Create test code with imports but no class definitions
    test_code = """
from pathlib import Path
from typing import Dict, Any
from maid_runner.validators.manifest_validator import ManifestValidator
"""

    # Parse and analyze with _ArtifactCollector
    tree = ast.parse(test_code)
    collector = _ArtifactCollector()
    collector.visit(tree)

    # Imported classes should NOT be in found_classes
    assert (
        "Path" not in collector.found_classes
    ), "Path import wrongly added to found_classes"
    assert (
        "Dict" not in collector.found_classes
    ), "Dict import wrongly added to found_classes"
    assert (
        "Any" not in collector.found_classes
    ), "Any import wrongly added to found_classes"
    assert (
        "ManifestValidator" not in collector.found_classes
    ), "ManifestValidator import wrongly added to found_classes"


def test_defined_classes_in_found_classes():
    """Test that defined classes ARE added to found_classes."""
    # Create test code with class definitions
    test_code = """
class MyClass:
    pass

class AnotherClass:
    def method(self):
        pass
"""

    # Parse and analyze with _ArtifactCollector
    tree = ast.parse(test_code)
    collector = _ArtifactCollector()
    collector.visit(tree)

    # Defined classes should BE in found_classes
    assert (
        "MyClass" in collector.found_classes
    ), "MyClass definition not in found_classes"
    assert (
        "AnotherClass" in collector.found_classes
    ), "AnotherClass definition not in found_classes"


def test_mixed_imports_and_definitions():
    """Test that imports and definitions are properly distinguished."""
    # Create test code with both imports and definitions
    test_code = """
from pathlib import Path
from typing import Dict, Any

class ConfigLoader:
    def __init__(self, path: Path):
        self.path = path
        self.config: Dict[str, Any] = {}

class DataProcessor:
    pass
"""

    # Parse and analyze with _ArtifactCollector
    tree = ast.parse(test_code)
    collector = _ArtifactCollector()
    collector.visit(tree)

    # Imported classes should NOT be in found_classes
    assert (
        "Path" not in collector.found_classes
    ), "Path import wrongly added to found_classes"
    assert (
        "Dict" not in collector.found_classes
    ), "Dict import wrongly added to found_classes"
    assert (
        "Any" not in collector.found_classes
    ), "Any import wrongly added to found_classes"

    # Defined classes should BE in found_classes
    assert (
        "ConfigLoader" in collector.found_classes
    ), "ConfigLoader definition not in found_classes"
    assert (
        "DataProcessor" in collector.found_classes
    ), "DataProcessor definition not in found_classes"


def test_local_module_imports_not_in_found_classes():
    """Test that imports from local modules are not added to found_classes."""
    # Create test code with local module imports
    test_code = """
from maid_runner.validators.manifest_validator import ManifestValidator, _ArtifactCollector
from maid_runner.types import ManifestData, ArtifactSpec

class MyValidator(ManifestValidator):
    def custom_method(self):
        pass
"""

    # Parse and analyze with _ArtifactCollector
    tree = ast.parse(test_code)
    collector = _ArtifactCollector()
    collector.visit(tree)

    # Imported classes (even from local modules) should NOT be in found_classes
    assert (
        "ManifestValidator" not in collector.found_classes
    ), "ManifestValidator import wrongly added"
    assert (
        "_ArtifactCollector" not in collector.found_classes
    ), "_ArtifactCollector import wrongly added"
    assert (
        "ManifestData" not in collector.found_classes
    ), "ManifestData import wrongly added"
    assert (
        "ArtifactSpec" not in collector.found_classes
    ), "ArtifactSpec import wrongly added"

    # Defined class (that inherits from imported class) should BE in found_classes
    assert (
        "MyValidator" in collector.found_classes
    ), "MyValidator definition not in found_classes"


def test_relative_imports_not_in_found_classes():
    """Test that relative imports are not added to found_classes."""
    # Create test code with relative imports
    test_code = """
from .validators import Validator
from ..types import DataType
from ...utils import Helper

class MyClass:
    pass
"""

    # Parse and analyze with _ArtifactCollector
    tree = ast.parse(test_code)
    collector = _ArtifactCollector()
    collector.visit(tree)

    # Relative imports should NOT be in found_classes
    assert (
        "Validator" not in collector.found_classes
    ), "Validator relative import wrongly added"
    assert (
        "DataType" not in collector.found_classes
    ), "DataType relative import wrongly added"
    assert (
        "Helper" not in collector.found_classes
    ), "Helper relative import wrongly added"

    # Defined class should BE in found_classes
    assert (
        "MyClass" in collector.found_classes
    ), "MyClass definition not in found_classes"


def test_star_imports_not_crash():
    """Test that star imports don't cause issues (they can't be tracked individually)."""
    # Create test code with star imports
    test_code = """
from typing import *

class MyClass:
    pass
"""

    # Parse and analyze with _ArtifactCollector
    tree = ast.parse(test_code)
    collector = _ArtifactCollector()
    collector.visit(tree)

    # Star imports can't be individually tracked, but shouldn't crash
    # And shouldn't add spurious entries to found_classes
    assert (
        "MyClass" in collector.found_classes
    ), "MyClass definition not in found_classes"


def test_aliased_imports_not_in_found_classes():
    """Test that aliased imports are not added to found_classes."""
    # Create test code with aliased imports
    test_code = """
from pathlib import Path as FilePath
from typing import Dict as Dictionary
import json as JSON

class Config:
    pass
"""

    # Parse and analyze with _ArtifactCollector
    tree = ast.parse(test_code)
    collector = _ArtifactCollector()
    collector.visit(tree)

    # Aliased imports should NOT be in found_classes (neither original nor alias names)
    assert "Path" not in collector.found_classes, "Path import wrongly added"
    assert "FilePath" not in collector.found_classes, "FilePath alias wrongly added"
    assert "Dict" not in collector.found_classes, "Dict import wrongly added"
    assert "Dictionary" not in collector.found_classes, "Dictionary alias wrongly added"

    # Defined class should BE in found_classes
    assert "Config" in collector.found_classes, "Config definition not in found_classes"


def test_nested_class_definitions():
    """Test that nested class definitions are properly detected."""
    # Create test code with nested classes
    test_code = """
from typing import Any

class OuterClass:
    class InnerClass:
        pass

    class AnotherInner:
        def method(self):
            pass
"""

    # Parse and analyze with _ArtifactCollector
    tree = ast.parse(test_code)
    collector = _ArtifactCollector()
    collector.visit(tree)

    # Imported type should NOT be in found_classes
    assert "Any" not in collector.found_classes, "Any import wrongly added"

    # All defined classes should BE in found_classes
    assert (
        "OuterClass" in collector.found_classes
    ), "OuterClass definition not in found_classes"
    assert (
        "InnerClass" in collector.found_classes
    ), "InnerClass definition not in found_classes"
    assert (
        "AnotherInner" in collector.found_classes
    ), "AnotherInner definition not in found_classes"


def test_class_with_imported_base():
    """Test that class inheriting from imported class works correctly."""
    # Create test code with inheritance from imported class
    test_code = """
from abc import ABC, abstractmethod

class BaseValidator(ABC):
    @abstractmethod
    def validate(self):
        pass

class ConcreteValidator(BaseValidator):
    def validate(self):
        return True
"""

    # Parse and analyze with _ArtifactCollector
    tree = ast.parse(test_code)
    collector = _ArtifactCollector()
    collector.visit(tree)

    # Imported classes should NOT be in found_classes
    assert "ABC" not in collector.found_classes, "ABC import wrongly added"
    assert (
        "abstractmethod" not in collector.found_classes
    ), "abstractmethod import wrongly added"

    # Defined classes should BE in found_classes
    assert (
        "BaseValidator" in collector.found_classes
    ), "BaseValidator definition not in found_classes"
    assert (
        "ConcreteValidator" in collector.found_classes
    ), "ConcreteValidator definition not in found_classes"


def test_empty_file_no_classes():
    """Test that file with no classes has empty found_classes."""
    # Create test code with no classes
    test_code = """
from typing import Dict
import json

def some_function():
    pass

variable = 42
"""

    # Parse and analyze with _ArtifactCollector
    tree = ast.parse(test_code)
    collector = _ArtifactCollector()
    collector.visit(tree)

    # Should have no classes in found_classes
    assert len(collector.found_classes) == 0, "found_classes should be empty"


def test_regression_function_imports_not_added():
    """Test that imported functions are also not added to found_classes."""
    # Create test code with function imports (they shouldn't go to found_classes anyway)
    test_code = """
from pathlib import Path
from typing import cast
from os import path

class MyClass:
    pass
"""

    # Parse and analyze with _ArtifactCollector
    tree = ast.parse(test_code)
    collector = _ArtifactCollector()
    collector.visit(tree)

    # Only the defined class should be in found_classes
    assert "MyClass" in collector.found_classes
    assert (
        len(collector.found_classes) == 1
    ), f"found_classes should only contain MyClass, got: {collector.found_classes}"
