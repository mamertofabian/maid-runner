"""Coherence checks package - exports all check classes."""

from maid_runner.coherence.checks.base import BaseCheck, get_checks
from maid_runner.coherence.checks.duplicate import DuplicateCheck
from maid_runner.coherence.checks.signature import SignatureCheck
from maid_runner.coherence.checks.naming import NamingCheck
from maid_runner.coherence.checks.boundary import ModuleBoundaryCheck
from maid_runner.coherence.checks.dependency import DependencyCheck
from maid_runner.coherence.checks.pattern import PatternCheck
from maid_runner.coherence.checks.constraint import (
    ConstraintCheck,
    ConstraintConfig,
    ConstraintRule,
)

__all__ = [
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
