"""V2 Dependency availability check.

Spec: 08-coherence-module.md - coherence/checks/dependency.py
Ported from v1: coherence/checks/dependency_check.py
"""

from __future__ import annotations

from maid_runner.core.types import Manifest
from maid_runner.coherence.result import (
    CoherenceIssue,
    IssueSeverity,
    IssueType,
)
from maid_runner.coherence.checks.base import BaseCheck
from maid_runner.graph.model import KnowledgeGraph


class DependencyCheck(BaseCheck):
    """Verifies that declared dependencies are available.

    Checks:
    - Files in files.read exist in the knowledge graph (tracked by some manifest)
    - Base classes referenced in artifacts exist somewhere in the chain

    Severity: ERROR for missing dependencies.
    """

    @property
    def name(self) -> str:
        return "dependency"

    def run(
        self, graph: KnowledgeGraph, manifests: list[Manifest]
    ) -> list[CoherenceIssue]:
        issues: list[CoherenceIssue] = []

        # Collect all file paths that are created/edited by any manifest
        writable_files: set[str] = set()
        for m in manifests:
            writable_files |= m.all_writable_paths

        for m in manifests:
            # Check read dependencies - must be created/edited by some other manifest
            for read_path in m.files_read:
                if read_path not in writable_files:
                    issues.append(
                        CoherenceIssue(
                            issue_type=IssueType.DEPENDENCY,
                            severity=IssueSeverity.ERROR,
                            message=f"Dependency not found: {read_path}",
                            file=read_path,
                            manifests=(m.slug,),
                            suggestion=(
                                "Create the dependency file first or reorder manifests "
                                "so this file is created before being referenced."
                            ),
                        )
                    )

            # Check base class references
            for fs in m.all_file_specs:
                for art in fs.artifacts:
                    for base in art.bases:
                        base_id = f"artifact:{fs.path}:{base}"
                        if graph.get_node(base_id) is None:
                            # Check if base exists anywhere in graph
                            found = False
                            for node in graph.nodes:
                                if (
                                    hasattr(node, "name")
                                    and getattr(node, "name", None) == base
                                ):
                                    found = True
                                    break
                            if not found:
                                issues.append(
                                    CoherenceIssue(
                                        issue_type=IssueType.DEPENDENCY,
                                        severity=IssueSeverity.WARNING,
                                        message=(
                                            f"Base class '{base}' referenced by "
                                            f"'{art.qualified_name}' not found in chain"
                                        ),
                                        file=fs.path,
                                        artifact=art.qualified_name,
                                        manifests=(m.slug,),
                                        suggestion=(
                                            f"Ensure '{base}' is declared in a manifest"
                                        ),
                                    )
                                )

        return issues
