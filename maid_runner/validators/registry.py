"""Validator registry for MAID Runner v2."""

from __future__ import annotations

from pathlib import Path
from typing import Union

from maid_runner.validators.base import BaseValidator


class UnsupportedLanguageError(Exception):
    """No validator available for a file extension."""

    def __init__(self, extension: str):
        self.extension = extension
        super().__init__(
            f"No validator for '{extension}' files. "
            f"Install optional dependencies? (e.g., maid-runner[typescript])"
        )


class ValidatorRegistry:
    """Instance-scoped registry of language validators."""

    def __init__(self) -> None:
        self._validators: dict[str, type[BaseValidator]] = {}
        self._instances: dict[str, BaseValidator] = {}

    @classmethod
    def with_builtin_validators(cls) -> ValidatorRegistry:
        registry = cls()
        auto_register(registry)
        return registry

    def clone(self) -> ValidatorRegistry:
        clone = type(self)()
        clone._validators = dict(self._validators)
        return clone

    def register(self, validator_class: type[BaseValidator]) -> None:
        """Register a validator for its supported extensions."""
        for ext in validator_class.supported_extensions():
            self._validators[ext] = validator_class
            self._instances.pop(ext, None)

    def get(self, file_path: Union[str, Path]) -> BaseValidator:
        """Get a validator instance for the given file."""
        ext = Path(file_path).suffix
        if ext not in self._validators:
            raise UnsupportedLanguageError(ext)
        if ext not in self._instances:
            self._instances[ext] = self._validators[ext]()
        return self._instances[ext]

    def has_validator(self, file_path: Union[str, Path]) -> bool:
        """Check if a validator is available for the given file."""
        return Path(file_path).suffix in self._validators

    def has_validator_for_extension(self, ext: str) -> bool:
        """Check if a validator is registered for an extension."""
        return ext in self._validators

    def supported_extensions(self) -> set[str]:
        """All file extensions with registered validators."""
        return set(self._validators.keys())

    def clear(self) -> None:
        """Clear all registrations."""
        self._validators.clear()
        self._instances.clear()


def auto_register(registry: ValidatorRegistry) -> ValidatorRegistry:
    """Auto-register all built-in validators into the provided registry."""
    from maid_runner.validators.python import PythonValidator

    registry.register(PythonValidator)

    try:
        from maid_runner.validators.typescript import TypeScriptValidator

        registry.register(TypeScriptValidator)
    except ImportError:
        pass

    try:
        from maid_runner.validators.svelte import SvelteValidator

        registry.register(SvelteValidator)
    except ImportError:
        pass

    return registry
