"""CoherenceEngine for cross-manifest validation.

Spec: 08-coherence-module.md - coherence/engine.py
"""

from __future__ import annotations

import time
from typing import Optional, Sequence, Union

from maid_runner.core.types import Manifest
from maid_runner.coherence.checks.base import BaseCheck, get_checks
from maid_runner.coherence.result import CoherenceResult, IssueSeverity
from maid_runner.graph.builder import GraphBuilder
from maid_runner.graph.model import KnowledgeGraph


class CoherenceEngine:
    """Orchestrates coherence validation.

    Builds knowledge graph, runs configured checks, aggregates results.

    Usage:
        engine = CoherenceEngine()
        result = engine.validate(chain)          # ManifestChain
        result = engine.validate(manifest_list)  # list[Manifest]
    """

    def __init__(self, checks: Optional[list[BaseCheck]] = None):
        """Initialize with optional custom check list.

        Args:
            checks: Checks to run. Defaults to all registered checks.
        """
        self._checks = checks if checks is not None else get_checks()

    def validate(
        self,
        manifests: Union[Sequence[Manifest], object],
        *,
        graph: Optional[KnowledgeGraph] = None,
    ) -> CoherenceResult:
        """Run all configured coherence checks.

        Args:
            manifests: ManifestChain or list/sequence of Manifest objects.
                       If it has an active_manifests() method, that is called.
            graph: Pre-built graph (optional; built from manifests if not provided).

        Returns:
            CoherenceResult with aggregated issues from all checks.
        """
        manifest_list: list[Manifest]
        if hasattr(manifests, "active_manifests"):
            manifest_list = manifests.active_manifests()  # type: ignore[union-attr]
        elif isinstance(manifests, list):
            manifest_list = manifests
        else:
            manifest_list = list(manifests)  # type: ignore[call-overload]

        if graph is None:
            graph = GraphBuilder().build_from_manifests(manifest_list)

        start = time.monotonic()
        all_issues = []
        checks_run = []

        for check in self._checks:
            issues = check.run(graph, manifest_list)
            all_issues.extend(issues)
            checks_run.append(check.name)

        duration = (time.monotonic() - start) * 1000

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
        all_manifests: Union[Sequence[Manifest], object],
        *,
        graph: Optional[KnowledgeGraph] = None,
    ) -> CoherenceResult:
        """Run coherence checks focused on a single manifest.

        Only reports issues related to the specified manifest.
        """
        result = self.validate(all_manifests, graph=graph)

        relevant = [
            i for i in result.issues if not i.manifests or manifest.slug in i.manifests
        ]

        return CoherenceResult(
            issues=relevant,
            checks_run=result.checks_run,
            duration_ms=result.duration_ms,
        )
