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
    """Registry of language validators.

    Validators register themselves when their module is imported.
    The registry provides lookup by file extension.
    """

    _validators: dict[str, type[BaseValidator]] = {}
    _instances: dict[str, BaseValidator] = {}

    @classmethod
    def register(cls, validator_class: type[BaseValidator]) -> None:
        """Register a validator for its supported extensions."""
        for ext in validator_class.supported_extensions():
            cls._validators[ext] = validator_class

    @classmethod
    def get(cls, file_path: Union[str, Path]) -> BaseValidator:
        """Get a validator instance for the given file.

        Raises:
            UnsupportedLanguageError: If no validator registered for extension.
        """
        ext = Path(file_path).suffix
        if ext not in cls._validators:
            raise UnsupportedLanguageError(ext)
        if ext not in cls._instances:
            cls._instances[ext] = cls._validators[ext]()
        return cls._instances[ext]

    @classmethod
    def has_validator(cls, file_path: Union[str, Path]) -> bool:
        """Check if a validator is available for the given file."""
        return Path(file_path).suffix in cls._validators

    @classmethod
    def has_validator_for_extension(cls, ext: str) -> bool:
        """Check if a validator is registered for an extension."""
        return ext in cls._validators

    @classmethod
    def supported_extensions(cls) -> set[str]:
        """All file extensions with registered validators."""
        return set(cls._validators.keys())

    @classmethod
    def clear(cls) -> None:
        """Clear all registrations. Used in testing."""
        cls._validators.clear()
        cls._instances.clear()


def auto_register() -> None:
    """Auto-register all built-in validators.

    Python is always available. TypeScript and Svelte are conditional.
    """
    from maid_runner.validators.python import PythonValidator

    ValidatorRegistry.register(PythonValidator)

    try:
        from maid_runner.validators.typescript import TypeScriptValidator

        ValidatorRegistry.register(TypeScriptValidator)
    except ImportError:
        pass

    try:
        from maid_runner.validators.svelte import SvelteValidator

        ValidatorRegistry.register(SvelteValidator)
    except ImportError:
        pass
