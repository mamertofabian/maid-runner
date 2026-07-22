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

_VALIDATOR_AUDIT_COMMAND = "maid validators"
_VALIDATOR_PLUGIN_GUIDE = "docs/validator-plugin-authoring.md"


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


def no_validator_guidance() -> str:
    """Return guidance for discovering externally provided validators."""
    return (
        f"Run `{_VALIDATOR_AUDIT_COMMAND}` to inspect registered validators; "
        "an external validator plugin may provide this language. See "
        f"`{_VALIDATOR_PLUGIN_GUIDE}`."
    )
