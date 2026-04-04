"""Tests for maid_runner.validators.base - BaseValidator ABC and data types."""

import pytest

from maid_runner.validators.base import (
    BaseValidator,
    CollectionResult,
    FoundArtifact,
)
from maid_runner.core.types import ArtifactKind


class TestFoundArtifact:
    def test_basic(self):
        fa = FoundArtifact(kind=ArtifactKind.FUNCTION, name="greet")
        assert fa.kind == ArtifactKind.FUNCTION
        assert fa.name == "greet"
        assert fa.of is None
        assert fa.args == ()
        assert fa.is_private is False

    def test_private_underscore(self):
        fa = FoundArtifact(kind=ArtifactKind.FUNCTION, name="_helper")
        assert fa.is_private is True

    def test_private_dunder(self):
        fa = FoundArtifact(kind=ArtifactKind.METHOD, name="__init__", of="Foo")
        assert fa.is_private is True

    def test_private_hash_prefix(self):
        """ES private fields (#name) are private."""
        fa = FoundArtifact(kind=ArtifactKind.METHOD, name="#secret", of="Foo")
        assert fa.is_private is True

    def test_private_inherited_from_underscore_parent(self):
        """Members of _-prefixed types inherit privacy."""
        fa = FoundArtifact(
            kind=ArtifactKind.ATTRIBUTE, name="headers", of="_AuthRequest"
        )
        assert fa.is_private is True

    def test_private_inherited_from_hash_parent(self):
        """Members of #-prefixed types inherit privacy."""
        fa = FoundArtifact(kind=ArtifactKind.METHOD, name="validate", of="#Internal")
        assert fa.is_private is True

    def test_not_private_public_parent(self):
        """Members of public types are not private."""
        fa = FoundArtifact(
            kind=ArtifactKind.ATTRIBUTE, name="status", of="AuthResponse"
        )
        assert fa.is_private is False

    def test_qualified_name(self):
        fa = FoundArtifact(kind=ArtifactKind.METHOD, name="login", of="AuthService")
        assert fa.qualified_name == "AuthService.login"

    def test_merge_key_method(self):
        fa = FoundArtifact(kind=ArtifactKind.METHOD, name="login", of="AuthService")
        assert fa.merge_key() == "AuthService.login"

    def test_merge_key_function(self):
        fa = FoundArtifact(kind=ArtifactKind.FUNCTION, name="greet")
        assert fa.merge_key() == "greet"

    def test_with_line_info(self):
        fa = FoundArtifact(kind=ArtifactKind.CLASS, name="Foo", line=10, column=0)
        assert fa.line == 10
        assert fa.column == 0

    def test_frozen(self):
        fa = FoundArtifact(kind=ArtifactKind.CLASS, name="Foo")
        with pytest.raises(AttributeError):
            fa.name = "Bar"  # type: ignore[misc]


class TestCollectionResult:
    def test_basic(self):
        result = CollectionResult(
            artifacts=[
                FoundArtifact(kind=ArtifactKind.FUNCTION, name="greet"),
            ],
            language="python",
            file_path="src/greet.py",
        )
        assert len(result.artifacts) == 1
        assert result.language == "python"
        assert result.errors == []

    def test_with_errors(self):
        result = CollectionResult(
            artifacts=[],
            language="python",
            file_path="src/bad.py",
            errors=["Syntax error at line 5"],
        )
        assert len(result.errors) == 1


class TestBaseValidator:
    def test_cannot_instantiate_directly(self):
        with pytest.raises(TypeError):
            BaseValidator()  # type: ignore[abstract]

    def test_concrete_implementation(self):
        class MockValidator(BaseValidator):
            @classmethod
            def supported_extensions(cls) -> tuple[str, ...]:
                return (".mock",)

            def collect_implementation_artifacts(self, source, file_path):
                return CollectionResult(
                    artifacts=[], language="mock", file_path=str(file_path)
                )

            def collect_behavioral_artifacts(self, source, file_path):
                return CollectionResult(
                    artifacts=[], language="mock", file_path=str(file_path)
                )

        v = MockValidator()
        assert v.can_validate("test.mock") is True
        assert v.can_validate("test.py") is False

    def test_generate_test_stub_default(self):
        class MockValidator(BaseValidator):
            @classmethod
            def supported_extensions(cls) -> tuple[str, ...]:
                return (".mock",)

            def collect_implementation_artifacts(self, source, file_path):
                return CollectionResult(
                    artifacts=[], language="mock", file_path=str(file_path)
                )

            def collect_behavioral_artifacts(self, source, file_path):
                return CollectionResult(
                    artifacts=[], language="mock", file_path=str(file_path)
                )

        v = MockValidator()
        assert v.generate_test_stub([], "test.mock") == ""


class TestGenerateSnapshot:
    def test_returns_list_of_artifact_dicts(self, tmp_path):
        """generate_snapshot should return list of artifact dicts from source."""
        from maid_runner.validators.python import PythonValidator

        source = "def example_func(x: int) -> str:\n    return str(x)\n"
        path = "src/example.py"
        validator = PythonValidator()
        result = validator.generate_snapshot(source, path)
        assert isinstance(result, list)
        assert len(result) >= 1
        assert result[0]["name"] == "example_func"
        assert result[0]["kind"] == "function"

    def test_excludes_private_artifacts(self):
        """generate_snapshot should exclude private (underscore-prefixed) artifacts."""
        from maid_runner.validators.python import PythonValidator

        source = "def public_fn():\n    return 1\n\ndef _private_fn():\n    pass\n"
        validator = PythonValidator()
        result = validator.generate_snapshot(source, "test.py")
        names = [d["name"] for d in result]
        assert "public_fn" in names
        assert "_private_fn" not in names

    def test_empty_source_returns_empty_list(self):
        """generate_snapshot on empty source returns empty list."""
        from maid_runner.validators.python import PythonValidator

        validator = PythonValidator()
        result = validator.generate_snapshot("", "test.py")
        assert result == []


class TestArtifactToDict:
    def test_basic_function(self):
        """Function artifact converts to dict with kind and name."""
        from maid_runner.validators.python import PythonValidator

        source = "def hello():\n    pass\n"
        result = PythonValidator().generate_snapshot(source, "test.py")
        found = [d for d in result if d["name"] == "hello"]
        assert found
        assert found[0]["kind"] == "function"

    def test_method_includes_of_field(self):
        """Method artifact includes 'of' field for parent class."""
        from maid_runner.validators.python import PythonValidator

        source = "class Foo:\n    def bar(self):\n        pass\n"
        result = PythonValidator().generate_snapshot(source, "test.py")
        bar = [d for d in result if d["name"] == "bar"]
        assert bar
        assert bar[0]["of"] == "Foo"

    def test_function_with_args(self):
        """Function with args includes args list."""
        from maid_runner.validators.python import PythonValidator

        source = "def add(a: int, b: int) -> int:\n    return a + b\n"
        result = PythonValidator().generate_snapshot(source, "test.py")
        add_fn = [d for d in result if d["name"] == "add"]
        assert add_fn
        assert "args" in add_fn[0]

    def test_function_with_returns(self):
        """Function with return type includes returns field."""
        from maid_runner.validators.python import PythonValidator

        source = "def greet(name: str) -> str:\n    return f'Hello, {name}!'\n"
        result = PythonValidator().generate_snapshot(source, "test.py")
        greet = [d for d in result if d["name"] == "greet"]
        assert greet
        assert greet[0]["returns"] == "str"

    def test_async_function(self):
        """Async function includes is_async field."""
        from maid_runner.validators.python import PythonValidator

        source = "async def fetch():\n    pass\n"
        result = PythonValidator().generate_snapshot(source, "test.py")
        fetch = [d for d in result if d["name"] == "fetch"]
        assert fetch
        assert fetch[0].get("async") is True

    def test_class_with_bases(self):
        """Class with bases includes bases field."""
        from maid_runner.validators.python import PythonValidator

        source = "class MyError(Exception):\n    pass\n"
        result = PythonValidator().generate_snapshot(source, "test.py")
        cls = [d for d in result if d["name"] == "MyError"]
        assert cls
        assert "bases" in cls[0]

    def test_annotated_attribute_includes_type(self):
        """Annotated attribute includes type field."""
        from maid_runner.validators.python import PythonValidator

        source = "MAX_RETRIES: int = 3\n"
        result = PythonValidator().generate_snapshot(source, "test.py")
        attr = [d for d in result if d["name"] == "MAX_RETRIES"]
        assert attr
        assert attr[0]["type"] == "int"
