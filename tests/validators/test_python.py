"""Tests for maid_runner.validators.python - PythonValidator.

Golden test cases from 15-golden-tests.md section 4.
"""

import pytest

from maid_runner.core.types import ArtifactKind
from maid_runner.validators.python import PythonValidator


@pytest.fixture()
def validator():
    return PythonValidator()


def _find(artifacts, name, kind=None, of=None):
    """Helper to find an artifact by name and optionally kind/of."""
    for a in artifacts:
        if a.name == name:
            if kind is not None and a.kind != kind:
                continue
            if of is not None and a.of != of:
                continue
            return a
    return None


class TestBasicClass:
    """Golden test 4.1."""

    def test_class_detected(self, validator):
        source = "class UserService:\n    pass\n"
        result = validator.collect_implementation_artifacts(source, "test.py")
        a = _find(result.artifacts, "UserService")
        assert a is not None
        assert a.kind == ArtifactKind.CLASS
        assert a.of is None


class TestClassWithBases:
    """Golden test 4.2."""

    def test_bases_extracted(self, validator):
        source = "from abc import ABC\nclass UserService(ABC):\n    pass\n"
        result = validator.collect_implementation_artifacts(source, "test.py")
        a = _find(result.artifacts, "UserService")
        assert a is not None
        assert "ABC" in a.bases


class TestMethodWithSelfFiltered:
    """Golden test 4.3."""

    def test_self_not_in_args(self, validator):
        source = """class Foo:
    def bar(self, x: int, y: str = "hello") -> bool:
        pass
"""
        result = validator.collect_implementation_artifacts(source, "test.py")
        bar = _find(result.artifacts, "bar", kind=ArtifactKind.METHOD)
        assert bar is not None
        assert bar.of == "Foo"
        arg_names = [a.name for a in bar.args]
        assert "self" not in arg_names
        assert arg_names == ["x", "y"]
        assert bar.args[0].type == "int"
        assert bar.args[1].type == "str"
        assert bar.args[1].default == "'hello'"
        assert bar.returns == "bool"


class TestClassmethodClsFiltered:
    """Golden test 4.4."""

    def test_cls_not_in_args(self, validator):
        source = """class Foo:
    @classmethod
    def create(cls, data: dict) -> "Foo":
        pass
"""
        result = validator.collect_implementation_artifacts(source, "test.py")
        create = _find(result.artifacts, "create", kind=ArtifactKind.METHOD)
        assert create is not None
        arg_names = [a.name for a in create.args]
        assert "cls" not in arg_names
        assert arg_names == ["data"]
        assert create.returns == "Foo"


class TestStaticMethod:
    """Golden test 4.5."""

    def test_no_self_cls_filtering(self, validator):
        source = """class Foo:
    @staticmethod
    def helper(x: int) -> str:
        pass
"""
        result = validator.collect_implementation_artifacts(source, "test.py")
        helper = _find(result.artifacts, "helper", kind=ArtifactKind.METHOD)
        assert helper is not None
        assert helper.of == "Foo"
        assert len(helper.args) == 1
        assert helper.args[0].name == "x"


class TestAsyncFunction:
    """Golden test 4.6."""

    def test_async_detected(self, validator):
        source = "async def fetch_data(url: str) -> dict:\n    pass\n"
        result = validator.collect_implementation_artifacts(source, "test.py")
        a = _find(result.artifacts, "fetch_data")
        assert a is not None
        assert a.kind == ArtifactKind.FUNCTION
        assert a.is_async is True
        assert a.args[0].name == "url"
        assert a.returns == "dict"


class TestModuleLevelAttribute:
    """Golden test 4.7."""

    def test_annotated_attribute(self, validator):
        source = "MAX_RETRIES: int = 3\n"
        result = validator.collect_implementation_artifacts(source, "test.py")
        a = _find(result.artifacts, "MAX_RETRIES")
        assert a is not None
        assert a.kind == ArtifactKind.ATTRIBUTE
        assert a.of is None
        assert a.type_annotation == "int"


class TestClassAttributeInInit:
    """Golden test 4.8."""

    def test_self_attributes(self, validator):
        source = """class Config:
    def __init__(self):
        self.debug = False
        self.port = 8080
"""
        result = validator.collect_implementation_artifacts(source, "test.py")
        debug = _find(result.artifacts, "debug", of="Config")
        port = _find(result.artifacts, "port", of="Config")
        assert debug is not None
        assert debug.kind == ArtifactKind.ATTRIBUTE
        assert debug.of == "Config"
        assert port is not None
        assert port.of == "Config"


class TestPropertyAsAttribute:
    """Golden test 4.9."""

    def test_property_treated_as_attribute(self, validator):
        source = """class User:
    @property
    def full_name(self) -> str:
        return f"{self.first} {self.last}"
"""
        result = validator.collect_implementation_artifacts(source, "test.py")
        a = _find(result.artifacts, "full_name", of="User")
        assert a is not None
        assert a.kind == ArtifactKind.ATTRIBUTE


class TestPrivateMembers:
    """Golden test 4.10."""

    def test_all_collected_with_privacy(self, validator):
        source = """class Foo:
    def public_method(self): pass
    def _private_method(self): pass
    def __dunder_method(self): pass
"""
        result = validator.collect_implementation_artifacts(source, "test.py")
        pub = _find(result.artifacts, "public_method", of="Foo")
        priv = _find(result.artifacts, "_private_method", of="Foo")
        dunder = _find(result.artifacts, "__dunder_method", of="Foo")
        assert pub is not None and pub.is_private is False
        assert priv is not None and priv.is_private is True
        assert dunder is not None and dunder.is_private is True


class TestEnumClass:
    """Golden test 4.11."""

    def test_enum_class_with_members(self, validator):
        source = """from enum import Enum
class Color(Enum):
    RED = 1
    GREEN = 2
"""
        result = validator.collect_implementation_artifacts(source, "test.py")
        color = _find(result.artifacts, "Color")
        assert color is not None
        assert color.kind == ArtifactKind.CLASS
        assert "Enum" in color.bases

        red = _find(result.artifacts, "RED", of="Color")
        green = _find(result.artifacts, "GREEN", of="Color")
        assert red is not None and red.kind == ArtifactKind.ATTRIBUTE
        assert green is not None and green.kind == ArtifactKind.ATTRIBUTE


class TestGenericClass:
    """Golden test 4.12."""

    def test_generic_base(self, validator):
        source = """from typing import Generic, TypeVar
T = TypeVar('T')
class Container(Generic[T]):
    pass
"""
        result = validator.collect_implementation_artifacts(source, "test.py")
        container = _find(result.artifacts, "Container")
        assert container is not None
        assert any("Generic" in b for b in container.bases)


class TestSupportedExtensions:
    def test_python_extensions(self):
        assert PythonValidator.supported_extensions() == (".py",)

    def test_can_validate(self, validator):
        assert validator.can_validate("src/app.py") is True
        assert validator.can_validate("src/app.ts") is False


class TestModuleLevelFunction:
    def test_module_function(self, validator):
        source = "def greet(name: str) -> str:\n    return f'Hello, {name}!'\n"
        result = validator.collect_implementation_artifacts(source, "test.py")
        a = _find(result.artifacts, "greet")
        assert a is not None
        assert a.kind == ArtifactKind.FUNCTION
        assert a.of is None
        assert a.returns == "str"


class TestBehavioralCollection:
    def test_collects_references(self, validator):
        source = """from src.greet import greet

def test_greet():
    assert greet("World") == "Hello, World!"
"""
        result = validator.collect_behavioral_artifacts(source, "test_greet.py")
        names = [a.name for a in result.artifacts]
        assert "greet" in names
