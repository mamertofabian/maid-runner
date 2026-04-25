"""V2 Signature conflict detection.

Spec: 08-coherence-module.md - coherence/checks/signature.py
"""

from __future__ import annotations

from maid_runner.core.types import ArtifactSpec, Manifest
from maid_runner.coherence.result import (
    CoherenceIssue,
    IssueSeverity,
    IssueType,
)
from maid_runner.coherence.checks.base import BaseCheck
from maid_runner.graph.model import KnowledgeGraph


class SignatureCheck(BaseCheck):
    """Detects conflicting function/method signatures across manifests.

    When multiple manifests declare the same function name but with
    different argument lists or return types, this is likely a conflict.

    Severity: WARNING for conflicting signatures in active manifests.
    """

    @property
    def name(self) -> str:
        return "signature"

    def run(
        self, graph: KnowledgeGraph, manifests: list[Manifest], **kwargs: object
    ) -> list[CoherenceIssue]:
        issues: list[CoherenceIssue] = []

        # Group artifacts by (file, qualified_name)
        artifacts_by_key: dict[tuple[str, str], list[tuple[str, ArtifactSpec]]] = {}
        for m in manifests:
            for fs in m.all_file_specs:
                for art in fs.artifacts:
                    key = (fs.path, art.qualified_name)
                    artifacts_by_key.setdefault(key, []).append((m.slug, art))

        for (file_path, qname), entries in artifacts_by_key.items():
            if len(entries) <= 1:
                continue

            for i in range(len(entries)):
                for j in range(i + 1, len(entries)):
                    slug_a, art_a = entries[i]
                    slug_b, art_b = entries[j]
                    if not _signatures_match(art_a, art_b):
                        issues.append(
                            CoherenceIssue(
                                issue_type=IssueType.SIGNATURE_CONFLICT,
                                severity=IssueSeverity.WARNING,
                                message=(
                                    f"Conflicting signatures for '{qname}' "
                                    f"in '{file_path}' between {slug_a} and {slug_b}"
                                ),
                                file=file_path,
                                artifact=qname,
                                manifests=(slug_a, slug_b),
                                suggestion="Align signatures or create superseding manifest",
                            )
                        )

        return issues


def _signatures_match(a: ArtifactSpec, b: ArtifactSpec) -> bool:
    """Compare two artifact signatures for compatibility."""
    if a.args and b.args and a.args != b.args:
        return False
    if a.returns and b.returns and a.returns != b.returns:
        return False
    return True
