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
    """Test that local module imports with uppercase names are tracked as classes."""
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
                {"type": "class", "name": "User"},
                {"type": "class", "name": "Product"},
                {"type": "class", "name": "OrderService"},
                {"type": "class", "name": "AlignmentError"},
                {"type": "class", "name": "MyClass"},
                {"type": "function", "name": "process"},
            ]
        }
    }
    # Should pass - local uppercase imports are tracked as classes
    validate_with_ast(manifest, str(test_file))


def test_relative_imports(tmp_path: Path):
    """Test relative imports at various levels."""
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
                {"type": "class", "name": "DatabaseConnection"},
                {"type": "class", "name": "ConfigManager"},
                {"type": "class", "name": "Logger"},
                {"type": "function", "name": "setup"},
            ]
        }
    }
    # Should pass - relative imports with uppercase names are tracked
    validate_with_ast(manifest, str(test_file))


def test_mixed_case_imports(tmp_path: Path):
    """Test that only uppercase-starting names are treated as classes."""
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
                {"type": "class", "name": "User"},
                {"type": "class", "name": "CONSTANTS"},
                {"type": "class", "name": "OrderProcessor"},
                {"type": "function", "name": "main"},
                # user_factory, process_order, _private should NOT be tracked as classes
            ]
        }
    }
    # Should pass - only uppercase names are tracked as classes
    validate_with_ast(manifest, str(test_file))
