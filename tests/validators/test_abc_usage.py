"""Tests for abstract base class usage detection in behavioral validation.

These tests verify that the validator correctly detects when abstract base classes
are "used" in behavioral tests through patterns like:
- Using as a base class
- isinstance checks
- issubclass checks
- hasattr checks
"""

from pathlib import Path
from maid_runner.validators.manifest_validator import validate_with_ast


def test_detects_class_used_as_base_class(tmp_path: Path):
    """Test that validator detects when a class is used as a base class."""
    code = """
from abc import ABC

class BaseClass(ABC):
    pass

class ConcreteClass(BaseClass):
    pass

def test_something():
    obj = ConcreteClass()
    assert obj is not None
"""
    test_file = tmp_path / "test_base_class.py"
    test_file.write_text(code)

    manifest = {
        "expectedArtifacts": {
            "contains": [
                {"type": "class", "name": "BaseClass"},
                {"type": "class", "name": "ConcreteClass"},
            ]
        }
    }
    # Should pass - BaseClass is used as a base class for ConcreteClass
    validate_with_ast(manifest, str(test_file), validation_mode="behavioral")


def test_detects_class_used_in_isinstance(tmp_path: Path):
    """Test that validator detects when a class is used in isinstance check."""
    code = """
class MyClass:
    pass

class SubClass(MyClass):
    pass

def test_isinstance_check():
    obj = SubClass()
    assert isinstance(obj, MyClass)
"""
    test_file = tmp_path / "test_isinstance.py"
    test_file.write_text(code)

    manifest = {
        "expectedArtifacts": {
            "contains": [
                {"type": "class", "name": "MyClass"},
                {"type": "class", "name": "SubClass"},
            ]
        }
    }
    # Should pass - MyClass is used in isinstance check
    validate_with_ast(manifest, str(test_file), validation_mode="behavioral")


def test_detects_class_used_in_issubclass(tmp_path: Path):
    """Test that validator detects when a class is used in issubclass check."""
    code = """
class ParentClass:
    pass

class ChildClass(ParentClass):
    pass

def test_issubclass_check():
    assert issubclass(ChildClass, ParentClass)
"""
    test_file = tmp_path / "test_issubclass.py"
    test_file.write_text(code)

    manifest = {
        "expectedArtifacts": {
            "contains": [
                {"type": "class", "name": "ParentClass"},
                {"type": "class", "name": "ChildClass"},
            ]
        }
    }
    # Should pass - ParentClass is used in issubclass check
    validate_with_ast(manifest, str(test_file), validation_mode="behavioral")


def test_detects_class_used_in_hasattr(tmp_path: Path):
    """Test that validator detects when a class is used in hasattr check."""
    code = """
class MyClass:
    @staticmethod
    def my_method():
        pass

def test_hasattr_check():
    assert hasattr(MyClass, 'my_method')
"""
    test_file = tmp_path / "test_hasattr.py"
    test_file.write_text(code)

    manifest = {
        "expectedArtifacts": {
            "contains": [
                {"type": "class", "name": "MyClass"},
            ]
        }
    }
    # Should pass - MyClass is used in hasattr check
    validate_with_ast(manifest, str(test_file), validation_mode="behavioral")


def test_detects_class_assigned_to_variable(tmp_path: Path):
    """Test that validator detects when a class is assigned to a variable and used."""
    code = """
class BaseClass:
    pass

class ConcreteClass(BaseClass):
    pass

def test_class_variable():
    base_ref = BaseClass
    obj = ConcreteClass()
    assert issubclass(type(obj), base_ref)
"""
    test_file = tmp_path / "test_class_variable.py"
    test_file.write_text(code)

    manifest = {
        "expectedArtifacts": {
            "contains": [
                {"type": "class", "name": "BaseClass"},
                {"type": "class", "name": "ConcreteClass"},
            ]
        }
    }
    # Should pass - BaseClass is assigned to variable and used
    validate_with_ast(manifest, str(test_file), validation_mode="behavioral")


def test_abstract_base_class_pattern(tmp_path: Path):
    """Test the real-world ABC pattern from Task-005."""
    code = """
from abc import ABC, abstractmethod

class BaseAgent(ABC):
    @abstractmethod
    def execute(self) -> dict:
        pass

class ConcreteAgent(BaseAgent):
    def execute(self) -> dict:
        return {"status": "success"}

def test_base_agent_can_be_subclassed():
    agent = ConcreteAgent()
    assert isinstance(agent, BaseAgent)

    base_agent_ref = BaseAgent
    assert issubclass(type(agent), base_agent_ref)

def test_execute_method():
    agent = ConcreteAgent()
    result = agent.execute()
    assert isinstance(result, dict)
    assert hasattr(BaseAgent, 'execute')
"""
    test_file = tmp_path / "test_abc_pattern.py"
    test_file.write_text(code)

    manifest = {
        "expectedArtifacts": {
            "contains": [
                {"type": "class", "name": "BaseAgent"},
                {"type": "function", "name": "execute", "class": "BaseAgent"},
            ]
        }
    }
    # Should pass - BaseAgent is used in multiple ways typical of ABCs
    validate_with_ast(manifest, str(test_file), validation_mode="behavioral")
