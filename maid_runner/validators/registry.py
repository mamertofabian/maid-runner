"""Validator registry for MAID Runner v2."""

from __future__ import annotations

from dataclasses import dataclass
import importlib.metadata as importlib_metadata
import os
from pathlib import Path
from typing import Union

from maid_runner.core.result import ErrorCode, Severity, ValidationError
from maid_runner.validators.base import BaseValidator

_VALIDATOR_ENTRY_POINT_GROUP = "maid_runner.validators"
_VALIDATOR_PLUGIN_DISABLE_ENV = "MAID_DISABLE_VALIDATOR_PLUGINS"


@dataclass(frozen=True)
class ValidatorRecord:
    """Inspectable record of a built-in, active, or skipped validator."""

    name: str
    extensions: tuple[str, ...]
    source: str
    status: str
    detail: str | None = None


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
        self._validator_records: list[ValidatorRecord] = []
        self._plugin_diagnostics: list[ValidationError] = []
        self._extension_sources: dict[str, str] = {}

    @classmethod
    def with_builtin_validators(cls) -> ValidatorRegistry:
        registry = cls()
        auto_register(registry)
        registry._discover_entry_point_validators()
        return registry

    def clone(self) -> ValidatorRegistry:
        clone = type(self)()
        clone._validators = dict(self._validators)
        clone._validator_records = list(self._validator_records)
        clone._plugin_diagnostics = list(self._plugin_diagnostics)
        clone._extension_sources = dict(self._extension_sources)
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
        self._validator_records.clear()
        self._plugin_diagnostics.clear()
        self._extension_sources.clear()

    def validator_records(self) -> "tuple[ValidatorRecord, ...]":
        """Deterministically ordered records for built-ins and plugins."""
        return tuple(self._validator_records)

    def plugin_diagnostics(self) -> list[ValidationError]:
        """Plugin load and conflict diagnostics as warning ValidationErrors."""
        return list(self._plugin_diagnostics)

    def _register_builtin(self, validator_class: type[BaseValidator]) -> None:
        self.register(validator_class)
        extensions = tuple(validator_class.supported_extensions())
        for ext in extensions:
            self._extension_sources[ext] = "builtin"
        self._validator_records.append(
            ValidatorRecord(
                name=validator_class.__name__,
                extensions=extensions,
                source="builtin",
                status="active",
            )
        )

    def _discover_entry_point_validators(self) -> None:
        entry_points = _validator_entry_points()
        if os.environ.get(_VALIDATOR_PLUGIN_DISABLE_ENV) == "1":
            self._validator_records.extend(
                ValidatorRecord(
                    name=entry_point.name,
                    extensions=(),
                    source=_entry_point_source(entry_point),
                    status="disabled",
                    detail=f"disabled by {_VALIDATOR_PLUGIN_DISABLE_ENV}=1",
                )
                for entry_point in entry_points
            )
            return

        for entry_point in entry_points:
            self._load_entry_point_validator(entry_point)

    def _load_entry_point_validator(self, entry_point) -> None:
        source = _entry_point_source(entry_point)
        try:
            validator_class = entry_point.load()
            if not isinstance(validator_class, type) or not issubclass(
                validator_class, BaseValidator
            ):
                raise TypeError(
                    "entry point did not resolve to a BaseValidator subclass"
                )
            extensions = tuple(validator_class.supported_extensions())
        except Exception as exc:
            message = f"Validator plugin '{source}' failed to load: {exc}"
            self._validator_records.append(
                ValidatorRecord(
                    name=entry_point.name,
                    extensions=(),
                    source=source,
                    status="error",
                    detail=str(exc),
                )
            )
            self._plugin_diagnostics.append(
                ValidationError(
                    code=ErrorCode.VALIDATOR_PLUGIN_LOAD_FAILURE,
                    message=message,
                    severity=Severity.WARNING,
                )
            )
            return

        conflicting = tuple(ext for ext in extensions if ext in self._validators)
        for ext in extensions:
            if ext in self._validators:
                continue
            self._validators[ext] = validator_class
            self._instances.pop(ext, None)
            self._extension_sources[ext] = source

        if conflicting:
            detail = f"conflicting extensions: {', '.join(conflicting)}"
            self._plugin_diagnostics.append(
                ValidationError(
                    code=ErrorCode.VALIDATOR_PLUGIN_CONFLICT,
                    message=_conflict_message(
                        source, conflicting, self._extension_sources
                    ),
                    severity=Severity.WARNING,
                )
            )
            status = "conflict"
        else:
            detail = None
            status = "active"

        self._validator_records.append(
            ValidatorRecord(
                name=entry_point.name,
                extensions=extensions,
                source=source,
                status=status,
                detail=detail,
            )
        )


def auto_register(registry: ValidatorRegistry) -> ValidatorRegistry:
    """Auto-register all built-in validators into the provided registry."""
    from maid_runner.validators.python import PythonValidator

    registry._register_builtin(PythonValidator)

    try:
        from maid_runner.validators.typescript import TypeScriptValidator

        registry._register_builtin(TypeScriptValidator)
    except ImportError:
        pass

    try:
        from maid_runner.validators.svelte import SvelteValidator

        registry._register_builtin(SvelteValidator)
    except ImportError:
        pass

    return registry


def _validator_entry_points() -> tuple:
    try:
        entry_points = importlib_metadata.entry_points(
            group=_VALIDATOR_ENTRY_POINT_GROUP
        )
    except TypeError:
        entry_points = importlib_metadata.entry_points()
        if hasattr(entry_points, "select"):
            entry_points = entry_points.select(group=_VALIDATOR_ENTRY_POINT_GROUP)
        elif isinstance(entry_points, dict):
            entry_points = entry_points.get(_VALIDATOR_ENTRY_POINT_GROUP, ())
        else:
            entry_points = (
                entry_point
                for entry_point in entry_points
                if getattr(entry_point, "group", None) == _VALIDATOR_ENTRY_POINT_GROUP
            )

    return tuple(
        sorted(
            entry_points,
            key=lambda entry_point: (
                _distribution_name(entry_point).casefold(),
                entry_point.name.casefold(),
            ),
        )
    )


def _entry_point_source(entry_point) -> str:
    name = _distribution_name(entry_point)
    version = getattr(getattr(entry_point, "dist", None), "version", None)
    if version:
        return f"{name} {version}"
    return name


def _distribution_name(entry_point) -> str:
    dist = getattr(entry_point, "dist", None)
    name = getattr(dist, "name", None)
    if name:
        return str(name)

    metadata = getattr(dist, "metadata", None)
    if metadata:
        try:
            metadata_name = metadata["Name"]
        except (KeyError, TypeError):
            metadata_name = None
        if metadata_name:
            return str(metadata_name)

    return str(getattr(entry_point, "name", "unknown"))


def _conflict_message(
    source: str,
    conflicting_extensions: tuple[str, ...],
    extension_sources: dict[str, str],
) -> str:
    conflicts = ", ".join(
        f"{ext} already claimed by {extension_sources.get(ext, 'another validator')}"
        for ext in conflicting_extensions
    )
    return f"Validator plugin '{source}' conflicts on {conflicts}"
