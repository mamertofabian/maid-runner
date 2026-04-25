"""V2 Duplicate artifact detection.

Spec: 08-coherence-module.md - coherence/checks/duplicate.py
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


class DuplicateCheck(BaseCheck):
    """Detects artifacts declared in multiple non-superseding manifests.

    Flags:
    - Same artifact name declared in different manifests for the same file
    - Excludes superseded manifest pairs

    Severity: WARNING for same-file duplicates.
    """

    @property
    def name(self) -> str:
        return "duplicate"

    def run(
        self, graph: KnowledgeGraph, manifests: list[Manifest], **kwargs: object
    ) -> list[CoherenceIssue]:
        issues: list[CoherenceIssue] = []

        # Build supersession set
        superseded_by: dict[str, str] = {}
        for m in manifests:
            for slug in m.supersedes:
                superseded_by[slug] = m.slug

        # Group artifact declarations by (file, artifact_name)
        declarations: dict[tuple[str, str], list[tuple[str, ArtifactSpec]]] = {}
        for m in manifests:
            for fs in m.all_file_specs:
                for art in fs.artifacts:
                    key = (fs.path, art.qualified_name)
                    declarations.setdefault(key, []).append((m.slug, art))

        for (file_path, art_name), entries in declarations.items():
            if len(entries) <= 1:
                continue

            # Filter out superseded pairs
            active_entries = []
            slugs = [slug for slug, _art in entries]
            for slug, art in entries:
                if slug not in superseded_by:
                    active_entries.append((slug, art))
                elif superseded_by[slug] not in slugs:
                    active_entries.append((slug, art))

            if len(active_entries) > 1 and not _compatible_redeclarations(
                [art for _slug, art in active_entries]
            ):
                active_slugs = [slug for slug, _art in active_entries]
                issues.append(
                    CoherenceIssue(
                        issue_type=IssueType.DUPLICATE,
                        severity=IssueSeverity.WARNING,
                        message=(
                            f"Artifact '{art_name}' in '{file_path}' "
                            f"declared in multiple manifests: {', '.join(active_slugs)}"
                        ),
                        file=file_path,
                        artifact=art_name,
                        manifests=tuple(active_slugs),
                        suggestion="Supersede one manifest or merge declarations",
                    )
                )

        return issues


def _compatible_redeclarations(artifacts: list[ArtifactSpec]) -> bool:
    first = artifacts[0]
    return all(
        art.kind == first.kind
        and (not art.args or not first.args or art.args == first.args)
        and (not art.returns or not first.returns or art.returns == first.returns)
        and (not art.bases or not first.bases or art.bases == first.bases)
        for art in artifacts[1:]
    )
