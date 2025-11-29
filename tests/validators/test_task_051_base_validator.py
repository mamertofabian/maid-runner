"""Tests for Task-051: BaseValidator abstract class."""

import pytest
from abc import ABC
from maid_runner.validators.base_validator import BaseValidator, ArtifactCollection


class TestArtifactCollection:
    """Test ArtifactCollection class exists and can be instantiated."""

    def test_artifact_collection_exists(self):
        """ArtifactCollection class should exist."""
        assert ArtifactCollection is not None

    def test_artifact_collection_can_be_created(self):
        """ArtifactCollection should be instantiable."""
        collection = ArtifactCollection()
        assert collection is not None


class TestBaseValidator:
    """Test BaseValidator abstract class."""

    def test_base_validator_exists(self):
        """BaseValidator class should exist."""
        assert BaseValidator is not None

    def test_base_validator_is_abstract(self):
        """BaseValidator should inherit from ABC."""
        assert issubclass(BaseValidator, ABC)

    def test_base_validator_cannot_be_instantiated(self):
        """BaseValidator should not be directly instantiable."""
        with pytest.raises(TypeError):
            BaseValidator()

    def test_base_validator_has_collect_artifacts_method(self):
        """BaseValidator should define collect_artifacts abstract method."""
        assert hasattr(BaseValidator, "collect_artifacts")

    def test_base_validator_has_supports_file_method(self):
        """BaseValidator should define supports_file abstract method."""
        assert hasattr(BaseValidator, "supports_file")

    def test_concrete_implementation_can_be_created(self):
        """A concrete implementation of BaseValidator should be instantiable."""

        class ConcreteValidator(BaseValidator):
            def collect_artifacts(self, file_path: str, validation_mode: str) -> dict:
                return {}

            def supports_file(self, file_path: str) -> bool:
                return True

        validator = ConcreteValidator()
        assert validator is not None
        assert isinstance(validator, BaseValidator)

    def test_concrete_validator_collect_artifacts(self):
        """Concrete validator's collect_artifacts should be callable."""

        class ConcreteValidator(BaseValidator):
            def collect_artifacts(self, file_path: str, validation_mode: str) -> dict:
                return {"classes": set(), "functions": {}}

            def supports_file(self, file_path: str) -> bool:
                return True

        validator = ConcreteValidator()
        result = validator.collect_artifacts("test.py", "implementation")
        assert isinstance(result, dict)

    def test_concrete_validator_supports_file(self):
        """Concrete validator's supports_file should be callable."""

        class ConcreteValidator(BaseValidator):
            def collect_artifacts(self, file_path: str, validation_mode: str) -> dict:
                return {}

            def supports_file(self, file_path: str) -> bool:
                return file_path.endswith(".py")

        validator = ConcreteValidator()
        assert validator.supports_file("test.py") is True
        assert validator.supports_file("test.ts") is False
