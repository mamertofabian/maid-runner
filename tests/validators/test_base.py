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
