"""
Tests for import statement handling in the manifest validator.

This module tests how the validator processes various import patterns:
- Regular imports (import os)
- From imports (from module import Class)
- Relative imports (from . import Class)
- Local vs external module distinction
- Uppercase class name detection
"""

from pathlib import Path
from maid_runner.validators.manifest_validator import validate_with_ast


def test_import_regular_modules(tmp_path: Path):
    """Test that regular imports (import os) are not tracked as artifacts."""
    code = """
import os
import sys
import json

def process_data():
    return os.getcwd()
"""
    test_file = tmp_path / "imports.py"
    test_file.write_text(code)

    manifest = {
        "expectedArtifacts": {
            "contains": [
                {"type": "function", "name": "process_data"}
                # os, sys, json should NOT be tracked
            ]
        }
    }
    # Should pass - regular imports are not tracked
    validate_with_ast(manifest, str(test_file))


def test_import_from_external_modules(tmp_path: Path):
    """Test that imports from external modules are excluded."""
    code = """
from pathlib import Path
from typing import List, Dict
from collections import defaultdict
from datetime import datetime

def process_data():
    pass
"""
    test_file = tmp_path / "external_imports.py"
    test_file.write_text(code)

    manifest = {
        "expectedArtifacts": {
            "contains": [
                {"type": "function", "name": "process_data"}
                # Path, List, Dict, defaultdict, datetime should NOT be tracked
            ]
        }
    }
    # Should pass - external module imports are excluded
    validate_with_ast(manifest, str(test_file))


def test_import_from_local_modules(tmp_path: Path):
    """Test that local module imports are NOT tracked as defined classes."""
    code = """
from .models import User, Product
from ..services import OrderService
from maid_runner.validators import AlignmentError

class MyClass:
    pass

def process():
    pass
"""
    test_file = tmp_path / "local_imports.py"
    test_file.write_text(code)

    manifest = {
        "expectedArtifacts": {
            "contains": [
                # Imported classes should NOT be in manifest (they're dependencies)
                # {"type": "class", "name": "User"},  # IMPORTED, not defined
                # {"type": "class", "name": "Product"},  # IMPORTED, not defined
                # {"type": "class", "name": "OrderService"},  # IMPORTED, not defined
                # {"type": "class", "name": "AlignmentError"},  # IMPORTED, not defined
                {"type": "class", "name": "MyClass"},  # DEFINED in this file
                {"type": "function", "name": "process"},  # DEFINED in this file
            ]
        }
    }
    # Should pass - only defined artifacts are tracked, not imports
    validate_with_ast(manifest, str(test_file))


def test_relative_imports(tmp_path: Path):
    """Test that relative imports are NOT tracked as defined classes."""
    code = """
from . import DatabaseConnection
from .. import ConfigManager
from ...utils import Logger

def setup():
    pass
"""
    test_file = tmp_path / "relative_imports.py"
    test_file.write_text(code)

    manifest = {
        "expectedArtifacts": {
            "contains": [
                # Relative imports should NOT be in manifest (they're dependencies)
                # {"type": "class", "name": "DatabaseConnection"},  # IMPORTED
                # {"type": "class", "name": "ConfigManager"},  # IMPORTED
                # {"type": "class", "name": "Logger"},  # IMPORTED
                {"type": "function", "name": "setup"},  # DEFINED in this file
            ]
        }
    }
    # Should pass - only defined artifacts are tracked, not imports
    validate_with_ast(manifest, str(test_file))


def test_mixed_case_imports(tmp_path: Path):
    """Test that imports are NOT tracked as defined classes regardless of case."""
    code = """
from .models import User, user_factory, CONSTANTS, _private
from ..services import process_order, OrderProcessor

def main():
    pass
"""
    test_file = tmp_path / "mixed_imports.py"
    test_file.write_text(code)

    manifest = {
        "expectedArtifacts": {
            "contains": [
                # All imports should be excluded (regardless of case)
                # {"type": "class", "name": "User"},  # IMPORTED
                # {"type": "class", "name": "CONSTANTS"},  # IMPORTED
                # {"type": "class", "name": "OrderProcessor"},  # IMPORTED
                {"type": "function", "name": "main"},  # DEFINED in this file
                # user_factory, process_order, _private are not classes anyway
            ]
        }
    }
    # Should pass - imports are not tracked, only defined artifacts
    validate_with_ast(manifest, str(test_file))


def test_enum_import_not_tracked_as_local_class(tmp_path: Path):
    """Test that enum.Enum imports are not tracked as local classes."""
    code = """
from enum import Enum

class Status(Enum):
    ACTIVE = 1
    INACTIVE = 2

def get_status():
    return Status.ACTIVE
"""
    test_file = tmp_path / "enum_test.py"
    test_file.write_text(code)

    manifest = {
        "expectedArtifacts": {
            "contains": [
                {"type": "class", "name": "Status"},
                {"type": "function", "name": "get_status"},
                # Enum should NOT be tracked as a local class
            ]
        }
    }
    # Should pass - enum.Enum is a stdlib import, not a local class
    validate_with_ast(manifest, str(test_file))
