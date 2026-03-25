"""V2 CoherenceEngine using v2 Manifest/ManifestChain types.

Spec: 08-coherence-module.md - coherence/engine.py
Coexists with the v1 CoherenceValidator (coherence/validator.py) until Phase 7.
"""

from __future__ import annotations

import time
from typing import Optional

from maid_runner.core.types import Manifest
from maid_runner.coherence.checks.base import BaseCheck, get_checks
from maid_runner.coherence.result_v2 import CoherenceResult, IssueSeverity
from maid_runner.graph.builder_v2 import GraphBuilder
from maid_runner.graph.model import KnowledgeGraph


class CoherenceEngine:
    """Orchestrates coherence validation.

    Builds knowledge graph, runs configured checks, aggregates results.

    Usage:
        engine = CoherenceEngine()
        result = engine.validate(chain.active_manifests())
    """

    def __init__(self, checks: Optional[list[BaseCheck]] = None):
        """Initialize with optional custom check list.

        Args:
            checks: Checks to run. Defaults to all registered checks.
        """
        self._checks = checks if checks is not None else get_checks()

    def validate(
        self,
        manifests: list[Manifest],
        *,
        graph: Optional[KnowledgeGraph] = None,
    ) -> CoherenceResult:
        """Run all configured coherence checks.

        Args:
            manifests: List of manifests to validate.
            graph: Pre-built graph (optional; built from manifests if not provided).

        Returns:
            CoherenceResult with aggregated issues from all checks.
        """
        if graph is None:
            graph = GraphBuilder().build_from_manifests(manifests)

        start = time.monotonic()
        all_issues = []
        checks_run = []

        for check in self._checks:
            issues = check.run(graph, manifests)
            all_issues.extend(issues)
            checks_run.append(check.name)

        duration = (time.monotonic() - start) * 1000

        # Sort: errors first, then by file, then by type
        all_issues.sort(
            key=lambda i: (
                (
                    0
                    if i.severity == IssueSeverity.ERROR
                    else (1 if i.severity == IssueSeverity.WARNING else 2)
                ),
                i.file or "",
                i.issue_type.value,
            )
        )

        return CoherenceResult(
            issues=all_issues,
            checks_run=checks_run,
            duration_ms=duration,
        )

    def validate_single(
        self,
        manifest: Manifest,
        all_manifests: list[Manifest],
        *,
        graph: Optional[KnowledgeGraph] = None,
    ) -> CoherenceResult:
        """Run coherence checks focused on a single manifest.

        Only reports issues related to the specified manifest.
        """
        result = self.validate(all_manifests, graph=graph)

        # Filter to only issues involving this manifest
        relevant = [
            i for i in result.issues if not i.manifests or manifest.slug in i.manifests
        ]

        return CoherenceResult(
            issues=relevant,
            checks_run=result.checks_run,
            duration_ms=result.duration_ms,
        )
