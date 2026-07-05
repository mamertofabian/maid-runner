"""Severity policies for diagnostics that need path-aware treatment."""

from __future__ import annotations

from pathlib import Path

from maid_runner.core.result import Severity

# Closed, documented set of non-code file extensions where "no validator" is
# expected inventory information rather than a warning about unvalidated source.
_RECOGNIZED_NON_CODE_EXTENSIONS = frozenset(
    {
        ".cfg",
        ".ini",
        ".json",
        ".jsonc",
        ".lock",
        ".markdown",
        ".md",
        ".rst",
        ".toml",
        ".txt",
        ".yaml",
        ".yml",
    }
)

_RECOGNIZED_NON_CODE_FILENAMES = frozenset(
    {
        ".editorconfig",
        ".env.example",
        ".gitattributes",
        ".gitignore",
    }
)


def no_validator_severity(path: str) -> Severity:
    """Return the E307 severity for a declared path with no validator."""
    candidate = Path(path)
    name = candidate.name.lower()
    suffix = candidate.suffix.lower()
    if name in _RECOGNIZED_NON_CODE_FILENAMES:
        return Severity.INFO
    if suffix in _RECOGNIZED_NON_CODE_EXTENSIONS:
        return Severity.INFO
    return Severity.WARNING
