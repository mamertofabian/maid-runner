"""Tests for maid_runner.validators.python - PythonValidator.

Golden test cases from 15-golden-tests.md section 4.
"""

import ast
import os

import pytest

from maid_runner.core.types import ArtifactKind
from maid_runner.validators._python_implementation import (
    collect_implementation_artifacts as collect_python_implementation_artifacts,
)
from maid_runner.validators.python import (
    PythonValidator,
    _BehavioralCollector,
    clear_python_ast_cache,
    get_cached_python_ast,
)


@pytest.fixture()
def validator():
    return PythonValidator()


@pytest.fixture(autouse=True)
def clear_python_ast_cache_between_tests():
    clear_python_ast_cache()
    yield
    clear_python_ast_cache()


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


def _count_ast_parse_calls(monkeypatch):
    real_parse = ast.parse
    calls = []

    def counting_parse(source, filename="<unknown>", mode="exec", *args, **kwargs):
        calls.append((source, filename, mode))
        return real_parse(
            source,
            filename=filename,
            mode=mode,
            *args,
            **kwargs,
        )

    monkeypatch.setattr(ast, "parse", counting_parse)
    return calls


def _artifact_signature(artifacts):
    return [
        (
            artifact.kind.value,
            artifact.name,
            artifact.of,
            tuple((arg.name, arg.type, arg.default) for arg in artifact.args),
            artifact.returns,
            artifact.is_async,
            artifact.bases,
            artifact.type_parameters,
            artifact.type_annotation,
            artifact.is_stub,
            artifact.line,
            artifact.column,
            artifact.module_path,
            artifact.import_source,
            artifact.alias_of,
            artifact.reference_context,
        )
        for artifact in artifacts
    ]


def _collection_result_signature(result):
    return (
        result.language,
        result.file_path,
        _artifact_signature(result.artifacts),
        result.errors,
    )


def _direct_python_artifact_baseline(source, file_path):
    tree = ast.parse(source, filename=str(file_path))
    implementation = collect_python_implementation_artifacts(tree, str(file_path))
    behavioral_collector = _BehavioralCollector(file_path=str(file_path))
    behavioral_collector.scan_imports(tree)
    behavioral_collector.visit(tree)
    return (
        _artifact_signature(implementation),
        _artifact_signature(behavioral_collector.artifacts),
    )


def test_get_cached_python_ast_returns_same_tree_within_invocation(
    tmp_path, monkeypatch
):
    source_path = tmp_path / "shared.py"
    source_path.write_text("def shared() -> int:\n    return 1\n")
    calls = _count_ast_parse_calls(monkeypatch)

    first_tree, first_source = get_cached_python_ast(source_path)
    second_tree, second_source = get_cached_python_ast(source_path)

    assert second_tree is first_tree
    assert first_source == second_source == source_path.read_text()
    assert len(calls) == 1


def test_get_cached_python_ast_invalidates_on_mtime_change(tmp_path, monkeypatch):
    source_path = tmp_path / "shared.py"
    source_path.write_text("def shared() -> int:\n    return 1\n")
    calls = _count_ast_parse_calls(monkeypatch)

    first_tree, _ = get_cached_python_ast(source_path)
    source_path.write_text("def shared() -> int:\n    return 2\n")
    stat = source_path.stat()
    os.utime(
        source_path,
        ns=(stat.st_atime_ns, stat.st_mtime_ns + 1_000_000),
    )
    second_tree, _ = get_cached_python_ast(source_path)

    assert second_tree is not first_tree
    assert len(calls) == 2


def test_collect_implementation_and_behavioral_artifacts_share_one_parse(
    tmp_path, monkeypatch, validator
):
    assert isinstance(validator, PythonValidator)
    source_path = tmp_path / "shared.py"
    source = """from package.service import Service

def build_user(name: str) -> str:
    return Service().normalize(name)

def test_build_user():
    assert build_user("Ada") == "Ada"
"""
    source_path.write_text(source)
    baseline_implementation, baseline_behavioral = _direct_python_artifact_baseline(
        source,
        source_path,
    )
    clear_python_ast_cache()
    calls = _count_ast_parse_calls(monkeypatch)

    implementation = validator.collect_implementation_artifacts(source, source_path)
    behavioral = validator.collect_behavioral_artifacts(source, source_path)

    assert len(calls) == 1
    assert _artifact_signature(implementation.artifacts) == baseline_implementation
    assert _artifact_signature(behavioral.artifacts) == baseline_behavioral


def test_get_test_function_bodies_reuses_cached_python_ast(
    tmp_path, monkeypatch, validator
):
    assert isinstance(validator, PythonValidator)
    source_path = tmp_path / "test_shared.py"
    source = """from package.service import build_user

def test_build_user():
    result = build_user("Ada")
    assert result == "Ada"
"""
    source_path.write_text(source)
    calls = _count_ast_parse_calls(monkeypatch)

    behavioral = validator.collect_behavioral_artifacts(source, source_path)
    bodies = validator.get_test_function_bodies(source, source_path)

    assert len(calls) == 1
    assert "build_user" in [artifact.name for artifact in behavioral.artifacts]
    assert bodies == {
        "test_build_user": (
            'def test_build_user():\n    result = build_user("Ada")\n'
            '    assert result == "Ada"\n'
        )
    }


def test_collect_results_match_uncached_baseline(tmp_path, validator):
    assert isinstance(validator, PythonValidator)
    source_path = tmp_path / "shared.py"
    source = """from package.service import Service

class UserService:
    def build_user(self, name: str) -> str:
        return Service().normalize(name)

def test_build_user():
    service = UserService()
    assert service.build_user("Ada") == "Ada"
"""
    source_path.write_text(source)
    baseline_implementation, baseline_behavioral = _direct_python_artifact_baseline(
        source,
        source_path,
    )
    clear_python_ast_cache()

    implementation = validator.collect_implementation_artifacts(source, source_path)
    behavioral = validator.collect_behavioral_artifacts(source, source_path)

    assert _artifact_signature(implementation.artifacts) == baseline_implementation
    assert _artifact_signature(behavioral.artifacts) == baseline_behavioral


def test_python_validator_collection_results_match_pre_refactor_shape(
    tmp_path, validator
):
    assert isinstance(validator, PythonValidator)
    source_path = tmp_path / "service.py"
    source = """from package.service import normalize

class UserService:
    def build_user(self, name: str) -> str:
        return normalize(name)

def test_build_user():
    service = UserService()
    assert service.build_user("Ada") == "Ada"
"""
    source_path.write_text(source)
    baseline_implementation, baseline_behavioral = _direct_python_artifact_baseline(
        source,
        source_path,
    )

    implementation = validator.collect_implementation_artifacts(source, source_path)
    behavioral = validator.collect_behavioral_artifacts(source, source_path)

    assert _collection_result_signature(implementation) == (
        "python",
        str(source_path),
        baseline_implementation,
        [],
    )
    assert _collection_result_signature(behavioral) == (
        "python",
        str(source_path),
        baseline_behavioral,
        [],
    )

    broken_path = tmp_path / "broken.py"
    broken_source = "def broken(:\n    pass\n"
    try:
        ast.parse(broken_source, filename=str(broken_path))
    except SyntaxError as exc:
        expected_errors = [f"Syntax error: {exc}"]
    else:
        raise AssertionError("broken_source must stay syntactically invalid")

    broken_implementation = validator.collect_implementation_artifacts(
        broken_source,
        broken_path,
    )
    broken_behavioral = validator.collect_behavioral_artifacts(
        broken_source,
        broken_path,
    )

    assert _collection_result_signature(broken_implementation) == (
        "python",
        str(broken_path),
        [],
        expected_errors,
    )
    assert _collection_result_signature(broken_behavioral) == (
        "python",
        str(broken_path),
        [],
        expected_errors,
    )


def test_clear_python_ast_cache_drops_all_entries(tmp_path, monkeypatch):
    first_path = tmp_path / "first.py"
    second_path = tmp_path / "second.py"
    first_path.write_text("def first() -> int:\n    return 1\n")
    second_path.write_text("def second() -> int:\n    return 2\n")
    calls = _count_ast_parse_calls(monkeypatch)

    get_cached_python_ast(first_path)
    get_cached_python_ast(second_path)
    clear_python_ast_cache()
    get_cached_python_ast(first_path)
    get_cached_python_ast(second_path)

    assert len(calls) == 4


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


class TestPackageReexports:
    def test_init_reexport_all_caps_constant_as_attribute(self, validator):
        source = "from maid_runner.graph.model import MANIFEST_PREFIX, NodeType\n"
        result = validator.collect_implementation_artifacts(source, "__init__.py")

        prefix = _find(result.artifacts, "MANIFEST_PREFIX")
        node_type = _find(result.artifacts, "NodeType")

        assert prefix is not None
        assert prefix.kind == ArtifactKind.ATTRIBUTE
        assert node_type is not None
        assert node_type.kind == ArtifactKind.CLASS


class TestPythonBehavioralReferences:
    def test_behavioral_references_preserve_same_name_from_different_import_sources(
        self, validator
    ):
        source = """
from pkg.internal import Thing
from pkg import Thing

def test_barrel_and_internal_exports():
    assert Thing is not None
"""

        result = validator.collect_behavioral_artifacts(source, "tests/test_api.py")

        assert PythonValidator is not None
        thing_sources = {
            artifact.import_source
            for artifact in result.artifacts
            if artifact.name == "Thing" and artifact.import_source is not None
        }
        assert thing_sources == {"pkg.internal", "pkg"}


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


class TestBehavioralAttributeAccess:
    """Tests that dot-notation attribute access is collected by _BehavioralCollector."""

    def test_visit_Attribute_collects_attr_name(self):
        """Direct test: _BehavioralCollector.visit_Attribute extracts attr field."""
        import ast

        from maid_runner.validators.python import _BehavioralCollector

        collector = _BehavioralCollector()
        node = ast.parse("obj.some_attr", mode="eval").body
        collector.visit_Attribute(node)
        names = [a.name for a in collector.artifacts]
        assert "some_attr" in names

    def test_simple_attribute_access(self, validator):
        source = """obj = get_thing()
result = obj.some_attr
"""
        result = validator.collect_behavioral_artifacts(source, "test_attr.py")
        names = [a.name for a in result.artifacts]
        assert "some_attr" in names

    def test_nested_attribute_access(self, validator):
        source = """result = obj.some_attr.nested
"""
        result = validator.collect_behavioral_artifacts(source, "test_attr.py")
        names = [a.name for a in result.artifacts]
        assert "some_attr" in names
        assert "nested" in names

    def test_attribute_in_assertion(self, validator):
        source = """from mymod import Report

def test_report():
    report = Report()
    assert report.captured == 2
    assert report.total_artifacts == 5
"""
        result = validator.collect_behavioral_artifacts(source, "test_report.py")
        names = [a.name for a in result.artifacts]
        assert "captured" in names
        assert "total_artifacts" in names

    def test_attribute_deduplication(self, validator):
        source = """x = obj.name
y = other.name
"""
        result = validator.collect_behavioral_artifacts(source, "test_dedup.py")
        name_count = sum(1 for a in result.artifacts if a.name == "name")
        assert name_count == 1


class TestBehavioralKeywordArgs:
    """Tests that keyword argument names in calls are collected."""

    def test_keyword_arg_in_constructor(self, validator):
        source = """report = Report(captured=5, failed=0)
"""
        result = validator.collect_behavioral_artifacts(source, "test_kwarg.py")
        names = [a.name for a in result.artifacts]
        assert "captured" in names
        assert "failed" in names

    def test_keyword_arg_in_function_call(self, validator):
        source = """result = process(timeout=30, retries=3)
"""
        result = validator.collect_behavioral_artifacts(source, "test_kwarg.py")
        names = [a.name for a in result.artifacts]
        assert "timeout" in names
        assert "retries" in names

    def test_double_star_kwargs_skipped(self, validator):
        source = """data = {"x": 1}
result = Foo(**data)
"""
        result = validator.collect_behavioral_artifacts(source, "test_kwarg.py")
        names = [a.name for a in result.artifacts]
        # **data should not produce a None artifact
        assert None not in names

    def test_visit_Call_collects_keyword_args(self):
        """Direct test: visit_Call extracts keyword argument names."""
        import ast

        from maid_runner.validators.python import _BehavioralCollector

        collector = _BehavioralCollector()
        tree = ast.parse("Foo(bar=1, baz=2)")
        call_node = tree.body[0].value
        collector.visit_Call(call_node)
        names = [a.name for a in collector.artifacts]
        assert "bar" in names
        assert "baz" in names


class TestImplementationReexport:
    """Tests that PythonValidator detects re-exported names via ImportFrom."""

    def test_barrel_and_internal_exports(self, validator):
        """Public validator entry point extracts named re-exports in __init__.py."""
        result = validator.collect_implementation_artifacts(
            "from .sub import MyClass, my_func\n",
            "__init__.py",
        )
        names = {a.name for a in result.artifacts}
        assert "MyClass" in names
        assert "my_func" in names

    def test_reexport_kind_inference(self, validator):
        source = "from .sub import MyClass, my_func\n"
        result = validator.collect_implementation_artifacts(source, "__init__.py")
        my_class = _find(result.artifacts, "MyClass")
        my_func = _find(result.artifacts, "my_func")
        assert my_class is not None
        assert my_class.kind == ArtifactKind.CLASS
        assert my_func is not None
        assert my_func.kind == ArtifactKind.FUNCTION

    def test_reexport_alias(self, validator):
        source = "from .module import OriginalName as AliasName\n"
        result = validator.collect_implementation_artifacts(source, "__init__.py")
        alias = _find(result.artifacts, "AliasName")
        original = _find(result.artifacts, "OriginalName")
        assert alias is not None
        assert original is None

    def test_star_import_skipped(self, validator):
        source = "from .module import *\n"
        result = validator.collect_implementation_artifacts(source, "__init__.py")
        assert len(result.artifacts) == 0

    def test_import_inside_class_not_collected(self, validator):
        source = """class Foo:
    from .bar import baz
"""
        result = validator.collect_implementation_artifacts(source, "__init__.py")
        baz = _find(result.artifacts, "baz")
        assert baz is None

    def test_non_init_file_skips_reexports(self, validator):
        source = "from .sub import MyClass\n"
        result = validator.collect_implementation_artifacts(source, "regular.py")
        assert _find(result.artifacts, "MyClass") is None

    def test_reexport_with_existing_definitions(self, validator):
        source = """from .sub import ReExported

def local_func():
    return True
"""
        result = validator.collect_implementation_artifacts(source, "__init__.py")
        reexported = _find(result.artifacts, "ReExported")
        local = _find(result.artifacts, "local_func")
        assert reexported is not None
        assert local is not None


class TestStubDetection:
    """Tests for is_stub detection on Python functions."""

    def test_pass_is_stub(self, validator):
        source = "def foo():\n    pass\n"
        result = validator.collect_implementation_artifacts(source, "test.py")
        a = _find(result.artifacts, "foo")
        assert a is not None
        assert a.is_stub is True

    def test_ellipsis_is_stub(self, validator):
        source = "def foo():\n    ...\n"
        result = validator.collect_implementation_artifacts(source, "test.py")
        a = _find(result.artifacts, "foo")
        assert a.is_stub is True

    def test_raise_not_implemented_is_stub(self, validator):
        source = 'def foo():\n    raise NotImplementedError("TODO")\n'
        result = validator.collect_implementation_artifacts(source, "test.py")
        a = _find(result.artifacts, "foo")
        assert a.is_stub is True

    def test_raise_not_implemented_bare_is_stub(self, validator):
        source = "def foo():\n    raise NotImplementedError\n"
        result = validator.collect_implementation_artifacts(source, "test.py")
        a = _find(result.artifacts, "foo")
        assert a.is_stub is True

    def test_return_none_is_stub(self, validator):
        source = "def foo():\n    return None\n"
        result = validator.collect_implementation_artifacts(source, "test.py")
        a = _find(result.artifacts, "foo")
        assert a.is_stub is True

    def test_return_literal_is_stub(self, validator):
        source = 'def foo():\n    return ""\n'
        result = validator.collect_implementation_artifacts(source, "test.py")
        a = _find(result.artifacts, "foo")
        assert a.is_stub is True

    def test_return_zero_is_stub(self, validator):
        source = "def foo():\n    return 0\n"
        result = validator.collect_implementation_artifacts(source, "test.py")
        a = _find(result.artifacts, "foo")
        assert a.is_stub is True

    def test_return_empty_dict_is_stub(self, validator):
        source = "def foo():\n    return {}\n"
        result = validator.collect_implementation_artifacts(source, "test.py")
        a = _find(result.artifacts, "foo")
        assert a.is_stub is True

    def test_return_empty_list_is_stub(self, validator):
        source = "def foo():\n    return []\n"
        result = validator.collect_implementation_artifacts(source, "test.py")
        a = _find(result.artifacts, "foo")
        assert a.is_stub is True

    def test_docstring_then_pass_is_stub(self, validator):
        source = 'def foo():\n    """Docstring."""\n    pass\n'
        result = validator.collect_implementation_artifacts(source, "test.py")
        a = _find(result.artifacts, "foo")
        assert a.is_stub is True

    def test_docstring_only_is_stub(self, validator):
        source = 'def foo():\n    """Docstring only."""\n'
        result = validator.collect_implementation_artifacts(source, "test.py")
        a = _find(result.artifacts, "foo")
        assert a.is_stub is True

    def test_real_function_is_not_stub(self, validator):
        source = "def greet(name: str) -> str:\n    return f'Hello, {name}!'\n"
        result = validator.collect_implementation_artifacts(source, "test.py")
        a = _find(result.artifacts, "greet")
        assert a.is_stub is False

    def test_multi_statement_is_not_stub(self, validator):
        source = "def foo():\n    x = 1\n    return x + 1\n"
        result = validator.collect_implementation_artifacts(source, "test.py")
        a = _find(result.artifacts, "foo")
        assert a.is_stub is False

    def test_method_stub_detected(self, validator):
        source = "class Foo:\n    def bar(self):\n        pass\n"
        result = validator.collect_implementation_artifacts(source, "test.py")
        a = _find(result.artifacts, "bar", kind=ArtifactKind.METHOD)
        assert a is not None
        assert a.is_stub is True

    def test_async_stub_detected(self, validator):
        source = "async def fetch():\n    pass\n"
        result = validator.collect_implementation_artifacts(source, "test.py")
        a = _find(result.artifacts, "fetch")
        assert a.is_stub is True

    def test_class_not_affected(self, validator):
        source = "class Foo:\n    pass\n"
        result = validator.collect_implementation_artifacts(source, "test.py")
        a = _find(result.artifacts, "Foo")
        assert a is not None
        # Classes don't have is_stub (always False by default)
        assert a.is_stub is False


class TestPythonBehavioralErrorHandling:
    def test_syntax_error_returns_empty_result(self, validator):
        """Invalid Python syntax should return empty collection, not crash."""
        result = validator.collect_behavioral_artifacts("def broken(:\n", "test.py")
        assert result.artifacts == []
        assert len(result.errors) >= 1

    def test_syntax_error_in_implementation_returns_empty(self, validator):
        """Implementation collection on invalid syntax returns empty with errors."""
        result = validator.collect_implementation_artifacts("class :\n", "test.py")
        assert result.artifacts == []
        assert len(result.errors) >= 1


class TestPythonTupleUnpackingAttributes:
    def test_tuple_unpacking_module_level(self, validator):
        """Tuple unpacking at module level collects each name as attribute."""
        source = "x, y = get_coords()\n"
        result = validator.collect_implementation_artifacts(source, "test.py")
        x = _find(result.artifacts, "x")
        y = _find(result.artifacts, "y")
        assert x is not None
        assert x.kind == ArtifactKind.ATTRIBUTE
        assert y is not None
        assert y.kind == ArtifactKind.ATTRIBUTE


class TestPythonDottedImports:
    def test_dotted_import_collected(self, validator):
        """from a.b.c import D should be collected."""
        source = "from maid_runner.core.types import Manifest\nManifest()\n"
        result = validator.collect_behavioral_artifacts(source, "test.py")
        names = {a.name for a in result.artifacts}
        assert "Manifest" in names

    def test_plain_import_collected(self, validator):
        """import os collects 'os' as reference."""
        source = "import os\nos.path.exists('/')\n"
        result = validator.collect_behavioral_artifacts(source, "test.py")
        names = {a.name for a in result.artifacts}
        assert "os" in names

    def test_aliased_import_uses_alias(self, validator):
        """from x import Y as Z collects Z, not Y."""
        source = "from pathlib import Path as P\nP('.')\n"
        result = validator.collect_behavioral_artifacts(source, "test.py")
        names = {a.name for a in result.artifacts}
        assert "P" in names
