"""V2 Dependency availability check.

Spec: 08-coherence-module.md - coherence/checks/dependency.py
Ported from v1: coherence/checks/dependency_check.py
"""

from __future__ import annotations

from pathlib import Path

from maid_runner.core.types import Manifest
from maid_runner.coherence.result import (
    CoherenceIssue,
    IssueSeverity,
    IssueType,
)
from maid_runner.coherence.checks.base import BaseCheck
from maid_runner.graph.model import KnowledgeGraph

_EXTERNAL_BASES = {
    "ABC",
    "Enum",
    "Exception",
    "BaseException",
    "object",
    "str",
    "int",
    "float",
    "bool",
    "bytes",
}


class DependencyCheck(BaseCheck):
    """Verifies that declared dependencies are available.

    Checks:
    - Files in files.read exist in the knowledge graph (tracked by some manifest)
      or on disk (when project_root is provided)
    - Base classes referenced in artifacts exist somewhere in the chain

    Severity: WARNING for missing dependencies.
    """

    @property
    def name(self) -> str:
        return "dependency"

    def run(
        self, graph: KnowledgeGraph, manifests: list[Manifest], **kwargs: object
    ) -> list[CoherenceIssue]:
        issues: list[CoherenceIssue] = []
        _root = kwargs.get("project_root")
        project_root = Path(_root) if isinstance(_root, (str, Path)) else None

        # Collect all file paths that are created/edited by any manifest
        writable_files: set[str] = set()
        for m in manifests:
            writable_files |= m.all_writable_paths

        for m in manifests:
            # Check read dependencies - must be created/edited by some other manifest
            # OR exist on disk (when project_root is provided)
            for read_path in m.files_read:
                if read_path not in writable_files:
                    # Filesystem fallback: if file exists on disk, not a real problem
                    if project_root is not None and (project_root / read_path).exists():
                        continue
                    issues.append(
                        CoherenceIssue(
                            issue_type=IssueType.DEPENDENCY,
                            severity=IssueSeverity.WARNING,
                            message=f"Dependency not found: {read_path}",
                            file=read_path,
                            manifests=(m.slug,),
                            suggestion=(
                                "This file is referenced as a dependency but not created by any manifest "
                                "and not found on disk. Create a manifest for it or remove the reference."
                            ),
                        )
                    )

            # Check base class references
            for fs in m.all_file_specs:
                for art in fs.artifacts:
                    for base in art.bases:
                        if _is_external_base(base):
                            continue

                        base_id = f"artifact:{fs.path}:class:{base}"
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


def _is_external_base(base: str) -> bool:
    return base in _EXTERNAL_BASES or "." in base
