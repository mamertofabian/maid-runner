"""
Tests for inheritance pattern validation in the manifest validator.

This module tests how the validator handles:
- Single inheritance
- Multiple inheritance
- Qualified base class names (module.ClassName)
- Complex inheritance chains
- Mixin patterns
"""

from pathlib import Path
from validators.manifest_validator import validate_with_ast


def test_multiple_inheritance(tmp_path: Path):
    """Test class inheriting from multiple base classes."""
    code = """
class Base1:
    pass

class Base2:
    pass

class Mixin:
    pass

class Derived(Base1, Base2, Mixin):
    pass

class SingleBase(Base1):
    pass
"""
    test_file = tmp_path / "multiple_inheritance.py"
    test_file.write_text(code)

    manifest = {
        "expectedArtifacts": {
            "contains": [
                {"type": "class", "name": "Base1"},
                {"type": "class", "name": "Base2"},
                {"type": "class", "name": "Mixin"},
                {"type": "class", "name": "Derived", "bases": ["Base1"]},
                {"type": "class", "name": "SingleBase", "bases": ["Base1"]},
            ]
        }
    }
    # Should pass - validates first base class
    validate_with_ast(manifest, str(test_file))

    # Test that any base class in the list validates
    manifest2 = {
        "expectedArtifacts": {
            "contains": [
                {"type": "class", "name": "Base1"},
                {"type": "class", "name": "Base2"},
                {"type": "class", "name": "Mixin"},
                {"type": "class", "name": "Derived", "bases": ["Base2"]},  # Second base
                {"type": "class", "name": "SingleBase", "bases": ["Base1"]},
            ]
        }
    }
    # Should pass - Base2 is in the inheritance list
    validate_with_ast(manifest2, str(test_file))


def test_qualified_base_class_names(tmp_path: Path):
    """Test module.ClassName style base classes."""
    code = """
import models
import services.auth

class MyModel(models.BaseModel):
    pass

class AuthService(services.auth.BaseAuthService):
    pass

class LocalBase:
    pass

class Derived(LocalBase):
    pass
"""
    test_file = tmp_path / "qualified_bases.py"
    test_file.write_text(code)

    manifest = {
        "expectedArtifacts": {
            "contains": [
                {"type": "class", "name": "MyModel", "bases": ["BaseModel"]},
                {"type": "class", "name": "AuthService", "bases": ["BaseAuthService"]},
                {"type": "class", "name": "LocalBase"},
                {"type": "class", "name": "Derived", "bases": ["LocalBase"]},
            ]
        }
    }
    # Should pass - extracts class name from qualified paths
    validate_with_ast(manifest, str(test_file))


def test_complex_inheritance_chain(tmp_path: Path):
    """Test complex inheritance hierarchies."""
    code = """
class A:
    pass

class B:
    pass

class C(A):
    pass

class D(B):
    pass

class E(C, D):
    # Diamond inheritance
    pass

class F(E):
    pass
"""
    test_file = tmp_path / "complex_inheritance.py"
    test_file.write_text(code)

    manifest = {
        "expectedArtifacts": {
            "contains": [
                {"type": "class", "name": "A"},
                {"type": "class", "name": "B"},
                {"type": "class", "name": "C", "bases": ["A"]},
                {"type": "class", "name": "D", "bases": ["B"]},
                {"type": "class", "name": "E", "bases": ["C"]},
                {"type": "class", "name": "F", "bases": ["E"]},
            ]
        }
    }
    # Should pass - complex inheritance validated
    validate_with_ast(manifest, str(test_file))


def test_mixin_pattern(tmp_path: Path):
    """Test common mixin inheritance patterns."""
    code = """
class LoggingMixin:
    pass

class CacheMixin:
    pass

class BaseService:
    pass

class UserService(LoggingMixin, CacheMixin, BaseService):
    pass

class AdminService(LoggingMixin, BaseService):
    pass
"""
    test_file = tmp_path / "mixins.py"
    test_file.write_text(code)

    manifest = {
        "expectedArtifacts": {
            "contains": [
                {"type": "class", "name": "LoggingMixin"},
                {"type": "class", "name": "CacheMixin"},
                {"type": "class", "name": "BaseService"},
                {"type": "class", "name": "UserService", "bases": ["LoggingMixin"]},
                {"type": "class", "name": "AdminService", "bases": ["LoggingMixin"]},
            ]
        }
    }
    # Should pass - mixin pattern validated
    validate_with_ast(manifest, str(test_file))
