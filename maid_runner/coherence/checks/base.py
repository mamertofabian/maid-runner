"""V2 BaseCheck ABC and check registry.

Spec: 08-coherence-module.md - coherence/checks/base.py
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Optional

from maid_runner.core.types import Manifest
from maid_runner.coherence.result import CoherenceIssue
from maid_runner.graph.model import KnowledgeGraph


class BaseCheck(ABC):
    """Abstract base for coherence checks.

    Each check analyzes the knowledge graph for a specific type of
    architectural issue. Checks are stateless and independent.
    """

    @property
    @abstractmethod
    def name(self) -> str:
        """Human-readable name for this check."""

    @abstractmethod
    def run(
        self, graph: KnowledgeGraph, manifests: list[Manifest]
    ) -> list[CoherenceIssue]:
        """Execute the check and return any issues found."""


def get_default_check_classes() -> list[type[BaseCheck]]:
    """Return all default v2 check classes (lazy import to avoid cycles)."""
    from maid_runner.coherence.checks.duplicate import DuplicateCheck
    from maid_runner.coherence.checks.signature import SignatureCheck
    from maid_runner.coherence.checks.naming import NamingCheck
    from maid_runner.coherence.checks.boundary import ModuleBoundaryCheck
    from maid_runner.coherence.checks.dependency import DependencyCheck
    from maid_runner.coherence.checks.pattern import PatternCheck
    from maid_runner.coherence.checks.constraint import ConstraintCheck

    return [
        DuplicateCheck,
        SignatureCheck,
        NamingCheck,
        ModuleBoundaryCheck,
        DependencyCheck,
        PatternCheck,
        ConstraintCheck,
    ]


def get_checks(
    enabled: Optional[list[str]] = None,
    disabled: Optional[list[str]] = None,
) -> list[BaseCheck]:
    """Get check instances, optionally filtering by name."""
    instances = [cls() for cls in get_default_check_classes()]

    if enabled is not None:
        instances = [c for c in instances if c.name in enabled]
    if disabled is not None:
        instances = [c for c in instances if c.name not in disabled]

    return instances
