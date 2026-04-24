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
    def test_register_and_get(self):
        registry = ValidatorRegistry()
        registry.register(_TestValidator)
        v = registry.get("file.test")
        assert isinstance(v, _TestValidator)

    def test_instance_isolation(self):
        first = ValidatorRegistry()
        second = ValidatorRegistry()
        first.register(_TestValidator)
        assert first.has_validator("file.test") is True
        assert second.has_validator("file.test") is False

    def test_get_caches_instances(self):
        registry = ValidatorRegistry()
        registry.register(_TestValidator)
        v1 = registry.get("file.test")
        v2 = registry.get("other.test")
        assert v1 is v2

    def test_get_unsupported_raises(self):
        registry = ValidatorRegistry()
        with pytest.raises(UnsupportedLanguageError) as exc_info:
            registry.get("file.xyz")
        assert exc_info.value.extension == ".xyz"

    def test_clone_copies_registered_validators(self):
        registry = ValidatorRegistry()
        registry.register(_TestValidator)

        clone = registry.clone()

        assert clone is not registry
        assert clone.has_validator_for_extension(".test") is True

    def test_has_validator(self):
        registry = ValidatorRegistry()
        registry.register(_TestValidator)
        assert registry.has_validator("file.test") is True
        assert registry.has_validator("file.xyz") is False

    def test_has_validator_for_extension(self):
        registry = ValidatorRegistry()
        registry.register(_TestValidator)
        assert registry.has_validator_for_extension(".test") is True
        assert registry.has_validator_for_extension(".xyz") is False

    def test_supported_extensions(self):
        registry = ValidatorRegistry()
        registry.register(_TestValidator)
        exts = registry.supported_extensions()
        assert ".test" in exts

    def test_clear(self):
        registry = ValidatorRegistry()
        registry.register(_TestValidator)
        assert registry.has_validator_for_extension(".test") is True
        registry.clear()
        assert registry.has_validator_for_extension(".test") is False

    def test_auto_register_includes_python(self):
        registry = ValidatorRegistry()
        auto_register(registry)
        assert registry.has_validator_for_extension(".py") is True

    def test_with_builtin_validators_returns_isolated_registry(self):
        registry = ValidatorRegistry.with_builtin_validators()
        assert registry.has_validator_for_extension(".py") is True
        registry.register(_TestValidator)
        assert registry.has_validator_for_extension(".test") is True

    def test_builtin_registries_are_independent(self):
        first = ValidatorRegistry.with_builtin_validators()
        second = ValidatorRegistry.with_builtin_validators()
        first.register(_TestValidator)
        assert first.has_validator_for_extension(".test") is True
        assert second.has_validator_for_extension(".test") is False
