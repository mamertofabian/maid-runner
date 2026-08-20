"""Coherence validation package - exports all coherence validation components."""

from __future__ import annotations as _annotations

from typing import Optional as _Optional

from maid_runner.coherence.result import (
    CoherenceIssue,
    CoherenceResult,
    IssueSeverity,
    IssueType,
)
from maid_runner.coherence.engine import CoherenceEngine
from maid_runner.coherence.checks import (
    BaseCheck,
    get_checks as _get_checks,
    DuplicateCheck,
    SignatureCheck,
    NamingCheck,
    ModuleBoundaryCheck,
    DependencyCheck,
    PatternCheck,
    ConstraintCheck,
    ConstraintConfig,
    ConstraintRule,
)


def get_checks(
    enabled: Optional[list[str]] = None,  # noqa: F821
    disabled: Optional[list[str]] = None,  # noqa: F821
) -> list[BaseCheck]:
    """Return coherence checks, optionally filtered by name."""
    return _get_checks(enabled=enabled, disabled=disabled)


get_checks.__annotations__.update(
    enabled=_Optional[list[str]],
    disabled=_Optional[list[str]],
)

__all__ = [
    # Result types
    "CoherenceIssue",
    "CoherenceResult",
    "IssueSeverity",
    "IssueType",
    # Engine
    "CoherenceEngine",
    # Checks
    "BaseCheck",
    "get_checks",
    "DuplicateCheck",
    "SignatureCheck",
    "NamingCheck",
    "ModuleBoundaryCheck",
    "DependencyCheck",
    "PatternCheck",
    "ConstraintCheck",
    "ConstraintConfig",
    "ConstraintRule",
]
