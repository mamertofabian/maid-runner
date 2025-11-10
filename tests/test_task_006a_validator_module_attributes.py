"""
Test Task-006a: Validator module-level attribute detection.

Tests the enhanced _ArtifactCollector class to ensure it properly detects
module-level attributes like type aliases and constants, not just class attributes.

These tests USE the _ArtifactCollector class from maid_runner.validators.manifest_validator
to verify its behavioral enhancement for detecting module-level assignments.
"""

import ast

from maid_runner.validators.manifest_validator import _ArtifactCollector


def test_detects_module_level_type_alias():
    """Test that _ArtifactCollector detects module-level type aliases."""
    # Create test code with type aliases at module level
    test_code = """
from typing import Dict, Any, List

# Module-level type aliases
ManifestData = Dict[str, Any]
FilePath = str
ArtifactList = List[Dict[str, str]]
"""

    # Parse and analyze with _ArtifactCollector
    tree = ast.parse(test_code)
    collector = _ArtifactCollector()
    collector.visit(tree)

    # Module-level attributes should be stored under None key
    assert None in collector.found_attributes, "Module-level attributes not detected"
    assert (
        "ManifestData" in collector.found_attributes[None]
    ), "ManifestData type alias not detected"
    assert (
        "FilePath" in collector.found_attributes[None]
    ), "FilePath type alias not detected"
    assert (
        "ArtifactList" in collector.found_attributes[None]
    ), "ArtifactList type alias not detected"


def test_detects_module_level_constants():
    """Test that _ArtifactCollector detects module-level constants."""
    # Create test code with constants at module level
    test_code = """
# Module-level constants
API_VERSION = "1.2.0"
MAX_RETRIES = 3
DEFAULT_CONFIG = {"timeout": 30, "verify": True}
ERROR_CODES = [404, 500, 503]
"""

    # Parse and analyze with _ArtifactCollector
    tree = ast.parse(test_code)
    collector = _ArtifactCollector()
    collector.visit(tree)

    # Module-level constants should be under None key
    assert None in collector.found_attributes, "Module-level constants not detected"
    assert (
        "API_VERSION" in collector.found_attributes[None]
    ), "API_VERSION constant not detected"
    assert (
        "MAX_RETRIES" in collector.found_attributes[None]
    ), "MAX_RETRIES constant not detected"
    assert (
        "DEFAULT_CONFIG" in collector.found_attributes[None]
    ), "DEFAULT_CONFIG constant not detected"
    assert (
        "ERROR_CODES" in collector.found_attributes[None]
    ), "ERROR_CODES constant not detected"


def test_detects_mixed_module_and_class_attributes():
    """Test that _ArtifactCollector properly categorizes both module and class attributes."""
    # Create test code with both module-level and class-level attributes
    test_code = """
from typing import Dict, Any

# Module-level attributes
ConfigType = Dict[str, Any]
VERSION = "2.0"

class Configuration:
    def __init__(self):
        self.settings = {}
        self.version = VERSION

    def update(self):
        self.last_updated = "now"

# Another module-level constant after class
DEFAULT_CONFIG = Configuration()
"""

    # Parse and analyze with _ArtifactCollector
    tree = ast.parse(test_code)
    collector = _ArtifactCollector()
    collector.visit(tree)

    # Check module-level attributes
    assert None in collector.found_attributes, "Module-level attributes not detected"
    assert (
        "ConfigType" in collector.found_attributes[None]
    ), "ConfigType not detected at module level"
    assert (
        "VERSION" in collector.found_attributes[None]
    ), "VERSION not detected at module level"
    assert (
        "DEFAULT_CONFIG" in collector.found_attributes[None]
    ), "DEFAULT_CONFIG not detected at module level"

    # Check class attributes are still detected properly
    assert (
        "Configuration" in collector.found_attributes
    ), "Class attributes not detected"
    assert (
        "settings" in collector.found_attributes["Configuration"]
    ), "settings attribute not detected"
    assert (
        "version" in collector.found_attributes["Configuration"]
    ), "version attribute not detected"
    assert (
        "last_updated" in collector.found_attributes["Configuration"]
    ), "last_updated attribute not detected"


def test_detects_complex_module_level_assignments():
    """Test that _ArtifactCollector handles various complex assignment patterns."""
    # Create test code with complex assignments
    test_code = """
# Multiple targets in one assignment
A = B = C = 100

# Tuple unpacking assignment
X, Y, Z = (1, 2, 3)

# Augmented assignment (should also be tracked)
TOTAL = 0
TOTAL += 10

# Complex type annotations
from typing import Optional, Union, Callable

Handler = Callable[[str], None]
Result = Union[int, str, None]
OptionalConfig = Optional[Dict[str, Any]]
"""

    # Parse and analyze with _ArtifactCollector
    tree = ast.parse(test_code)
    collector = _ArtifactCollector()
    collector.visit(tree)

    # Check all module-level assignments are detected
    assert None in collector.found_attributes, "Module-level assignments not detected"

    # Multiple target assignment - all should be detected
    assert (
        "A" in collector.found_attributes[None]
    ), "A not detected in multiple assignment"
    assert (
        "B" in collector.found_attributes[None]
    ), "B not detected in multiple assignment"
    assert (
        "C" in collector.found_attributes[None]
    ), "C not detected in multiple assignment"

    # Tuple unpacking - all targets should be detected
    assert "X" in collector.found_attributes[None], "X not detected in tuple unpacking"
    assert "Y" in collector.found_attributes[None], "Y not detected in tuple unpacking"
    assert "Z" in collector.found_attributes[None], "Z not detected in tuple unpacking"

    # Initial assignment (augmented assignments need initial)
    assert "TOTAL" in collector.found_attributes[None], "TOTAL not detected"

    # Complex type aliases
    assert (
        "Handler" in collector.found_attributes[None]
    ), "Handler type alias not detected"
    assert (
        "Result" in collector.found_attributes[None]
    ), "Result type alias not detected"
    assert (
        "OptionalConfig" in collector.found_attributes[None]
    ), "OptionalConfig type alias not detected"


def test_regression_class_attributes_still_work():
    """Regression test: ensure class attribute detection still works after enhancement."""
    # Create test code with only class attributes
    test_code = """
class MyClass:
    class_var = 42  # Class variable

    def __init__(self):
        self.instance_var = "hello"
        self.count = 0

    def method(self):
        self.computed = self.count * 2
        self.status = "active"
"""

    # Parse and analyze with _ArtifactCollector
    tree = ast.parse(test_code)
    collector = _ArtifactCollector()
    collector.visit(tree)

    # All class attributes should still be detected
    assert "MyClass" in collector.found_attributes, "Class not found in attributes dict"

    class_attrs = collector.found_attributes["MyClass"]
    assert "instance_var" in class_attrs, "instance_var not detected"
    assert "count" in class_attrs, "count not detected"
    assert "computed" in class_attrs, "computed not detected"
    assert "status" in class_attrs, "status not detected"

    # Module-level attributes dict might exist but should not interfere
    # with class attribute detection


def test_regression_variable_to_class_tracking():
    """Regression test: ensure variable-to-class instance tracking still works."""
    # Create test code with variable assignments to class instances
    test_code = """
class DataProcessor:
    def __init__(self):
        self.data = []

    def process(self):
        self.result = None

# Variable assignments to track
processor = DataProcessor()
processor.extra_field = "added"

another_proc = DataProcessor()
another_proc.custom_attr = 123
"""

    # Parse and analyze with _ArtifactCollector
    tree = ast.parse(test_code)
    collector = _ArtifactCollector()
    collector.visit(tree)

    # Check that variable-to-class mapping still works
    assert (
        "processor" in collector.variable_to_class
    ), "processor variable not mapped to class"
    assert collector.variable_to_class["processor"] == "DataProcessor"

    assert (
        "another_proc" in collector.variable_to_class
    ), "another_proc variable not mapped to class"
    assert collector.variable_to_class["another_proc"] == "DataProcessor"

    # Check that attributes accessed via variables are still tracked
    assert "DataProcessor" in collector.found_attributes
    attrs = collector.found_attributes["DataProcessor"]
    assert "data" in attrs, "data attribute not detected"
    assert "result" in attrs, "result attribute not detected"
    assert "extra_field" in attrs, "extra_field attribute not detected via variable"
    assert "custom_attr" in attrs, "custom_attr attribute not detected via variable"


def test_module_attributes_in_nested_scopes():
    """Test that only true module-level attributes are detected, not nested ones."""
    # Create test code with assignments in various scopes
    test_code = """
# True module-level
MODULE_CONST = "top"

def function_scope():
    # Not module-level - inside function
    local_var = 100
    return local_var

class ClassScope:
    # Not module-level - class variable
    class_var = 200

    def method_scope(self):
        # Not module-level - inside method
        method_var = 300
        self.instance_var = 400

# Another true module-level after other definitions
ANOTHER_MODULE_VAR = 500
"""

    # Parse and analyze with _ArtifactCollector
    tree = ast.parse(test_code)
    collector = _ArtifactCollector()
    collector.visit(tree)

    # Only true module-level should be under None
    assert None in collector.found_attributes, "Module-level attributes not detected"
    module_attrs = collector.found_attributes[None]

    # Should detect true module-level assignments
    assert "MODULE_CONST" in module_attrs, "MODULE_CONST not detected"
    assert "ANOTHER_MODULE_VAR" in module_attrs, "ANOTHER_MODULE_VAR not detected"

    # Should NOT detect nested assignments as module-level
    assert (
        "local_var" not in module_attrs
    ), "Function local variable wrongly detected as module-level"
    assert (
        "method_var" not in module_attrs
    ), "Method local variable wrongly detected as module-level"
    assert (
        "class_var" not in module_attrs
    ), "Class variable wrongly detected as module-level"

    # Class instance variables should be under the class, not module
    assert "ClassScope" in collector.found_attributes
    assert "instance_var" in collector.found_attributes["ClassScope"]


def test_annotated_module_level_assignments():
    """Test detection of module-level assignments with type annotations."""
    # Create test code with annotated assignments
    test_code = """
from typing import List, Dict, Optional

# Annotated assignments at module level
count: int = 0
names: List[str] = []
config: Optional[Dict[str, Any]] = None

# Annotation without initial value
future_value: str

# Complex annotation
matrix: List[List[int]] = [[1, 2], [3, 4]]
"""

    # Parse and analyze with _ArtifactCollector
    tree = ast.parse(test_code)
    collector = _ArtifactCollector()
    collector.visit(tree)

    # All annotated module-level variables should be detected
    assert (
        None in collector.found_attributes
    ), "Module-level annotated assignments not detected"
    module_attrs = collector.found_attributes[None]

    assert "count" in module_attrs, "Annotated 'count' not detected"
    assert "names" in module_attrs, "Annotated 'names' not detected"
    assert "config" in module_attrs, "Annotated 'config' not detected"
    assert "future_value" in module_attrs, "Annotation-only 'future_value' not detected"
    assert "matrix" in module_attrs, "Complex annotated 'matrix' not detected"


def test_empty_module_has_no_attributes():
    """Test that an empty module or module with only imports has no attributes."""
    # Create test code with only imports and functions
    test_code = """
import os
from typing import Dict

def some_function():
    local = 42
    return local

class EmptyClass:
    pass
"""

    # Parse and analyze with _ArtifactCollector
    tree = ast.parse(test_code)
    collector = _ArtifactCollector()
    collector.visit(tree)

    # Should not have module-level attributes if none exist
    # Or if it exists, it should be empty
    if None in collector.found_attributes:
        assert (
            len(collector.found_attributes[None]) == 0
        ), "Empty module should have no attributes"


def test_real_world_module_attributes():
    """Test detection of real-world pattern: module with type aliases and constants."""
    # Create test code similar to actual manifest_validator.py patterns
    test_code = """
from typing import Dict, Any, Optional, List, Union

# Type aliases (like in actual validator)
ManifestData = Dict[str, Any]
ValidationResult = Dict[str, Union[bool, str, List[str]]]
ArtifactSpec = Dict[str, Any]

# Constants (like in actual validator)
ARTIFACT_KIND_TYPE = "type"
ARTIFACT_KIND_RUNTIME = "runtime"
VALIDATION_MODE_STRICT = "strict"
VALIDATION_MODE_PERMISSIVE = "permissive"

# Module-level variable
_cache: Optional[Dict[str, Any]] = None

class Validator:
    def __init__(self):
        self.errors = []
        self.mode = VALIDATION_MODE_STRICT
"""

    # Parse and analyze with _ArtifactCollector
    tree = ast.parse(test_code)
    collector = _ArtifactCollector()
    collector.visit(tree)

    # Check all module-level items are detected
    assert None in collector.found_attributes, "Module attributes not detected"
    module_attrs = collector.found_attributes[None]

    # Type aliases
    assert "ManifestData" in module_attrs, "ManifestData type alias not detected"
    assert (
        "ValidationResult" in module_attrs
    ), "ValidationResult type alias not detected"
    assert "ArtifactSpec" in module_attrs, "ArtifactSpec type alias not detected"

    # Constants
    assert (
        "ARTIFACT_KIND_TYPE" in module_attrs
    ), "ARTIFACT_KIND_TYPE constant not detected"
    assert (
        "ARTIFACT_KIND_RUNTIME" in module_attrs
    ), "ARTIFACT_KIND_RUNTIME constant not detected"
    assert (
        "VALIDATION_MODE_STRICT" in module_attrs
    ), "VALIDATION_MODE_STRICT constant not detected"
    assert (
        "VALIDATION_MODE_PERMISSIVE" in module_attrs
    ), "VALIDATION_MODE_PERMISSIVE constant not detected"

    # Module variable
    assert "_cache" in module_attrs, "_cache module variable not detected"

    # Class attributes should still work
    assert "Validator" in collector.found_attributes
    assert "errors" in collector.found_attributes["Validator"]
    assert "mode" in collector.found_attributes["Validator"]
