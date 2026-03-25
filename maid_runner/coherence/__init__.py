"""Coherence validation package - exports all coherence validation components."""

from maid_runner.coherence.result import (
    CoherenceIssue,
    CoherenceResult,
    IssueSeverity,
    IssueType,
)
from maid_runner.coherence.engine import CoherenceEngine
from maid_runner.coherence.checks import (
    BaseCheck,
    get_checks,
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
