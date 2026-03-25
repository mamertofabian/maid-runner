"""Tests for maid_runner.validators.registry - ValidatorRegistry."""

import pytest

from maid_runner.validators.base import BaseValidator, CollectionResult
from maid_runner.validators.registry import (
    UnsupportedLanguageError,
    ValidatorRegistry,
    auto_register,
)


class _TestValidator(BaseValidator):
    @classmethod
    def supported_extensions(cls) -> tuple[str, ...]:
        return (".test",)

    def collect_implementation_artifacts(self, source, file_path):
        return CollectionResult(artifacts=[], language="test", file_path=str(file_path))

    def collect_behavioral_artifacts(self, source, file_path):
        return CollectionResult(artifacts=[], language="test", file_path=str(file_path))


class TestValidatorRegistry:
    def setup_method(self):
        ValidatorRegistry.clear()

    def test_register_and_get(self):
        ValidatorRegistry.register(_TestValidator)
        v = ValidatorRegistry.get("file.test")
        assert isinstance(v, _TestValidator)

    def test_get_caches_instances(self):
        ValidatorRegistry.register(_TestValidator)
        v1 = ValidatorRegistry.get("file.test")
        v2 = ValidatorRegistry.get("other.test")
        assert v1 is v2

    def test_get_unsupported_raises(self):
        with pytest.raises(UnsupportedLanguageError):
            ValidatorRegistry.get("file.xyz")

    def test_has_validator(self):
        ValidatorRegistry.register(_TestValidator)
        assert ValidatorRegistry.has_validator("file.test") is True
        assert ValidatorRegistry.has_validator("file.xyz") is False

    def test_has_validator_for_extension(self):
        ValidatorRegistry.register(_TestValidator)
        assert ValidatorRegistry.has_validator_for_extension(".test") is True
        assert ValidatorRegistry.has_validator_for_extension(".xyz") is False

    def test_supported_extensions(self):
        ValidatorRegistry.register(_TestValidator)
        exts = ValidatorRegistry.supported_extensions()
        assert ".test" in exts

    def test_clear(self):
        ValidatorRegistry.register(_TestValidator)
        assert ValidatorRegistry.has_validator_for_extension(".test") is True
        ValidatorRegistry.clear()
        assert ValidatorRegistry.has_validator_for_extension(".test") is False

    def test_auto_register_includes_python(self):
        auto_register()
        assert ValidatorRegistry.has_validator_for_extension(".py") is True
