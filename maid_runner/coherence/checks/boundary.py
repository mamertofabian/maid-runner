"""V2 Module boundary violation check.

Spec: 08-coherence-module.md - coherence/checks/boundary.py
Ported from v1: coherence/checks/module_boundary.py
"""

from __future__ import annotations

from pathlib import Path
from typing import Optional

from maid_runner.core.types import Manifest
from maid_runner.coherence.result import (
    CoherenceIssue,
    IssueSeverity,
    IssueType,
)
from maid_runner.coherence.checks.base import BaseCheck
from maid_runner.graph.model import (
    ArtifactNode,
    FileNode,
    KnowledgeGraph,
)

# Known bad patterns: source_module -> forbidden target modules
_BOUNDARY_VIOLATION_PATTERNS: dict[str, list[str]] = {
    "controllers": ["data"],
    "cli": ["data"],
}


class ModuleBoundaryCheck(BaseCheck):
    """Detects violations of module encapsulation.

    Checks that manifests don't declare artifacts that reach into
    private internals of other modules.

    Rules:
    - Files starting with _ are module-private
    - Artifacts in private files shouldn't be referenced by external manifests
    - Cross-module access patterns are flagged (e.g. controllers -> data)

    Severity: WARNING for potential boundary violations.
    """

    @property
    def name(self) -> str:
        return "boundary"

    def run(
        self, graph: KnowledgeGraph, manifests: list[Manifest], **kwargs: object
    ) -> list[CoherenceIssue]:
        issues: list[CoherenceIssue] = []

        for m in manifests:
            for fs in m.all_file_specs:
                source_module = _extract_module_from_path(fs.path)
                if not source_module:
                    continue

                for art in fs.artifacts:
                    # Check type hints in arguments for cross-module access
                    for arg in art.args:
                        if arg.type:
                            issue = _detect_boundary_violation_from_type(
                                source_module=source_module,
                                type_hint=arg.type,
                                artifact_name=art.qualified_name,
                                graph=graph,
                            )
                            if issue:
                                issues.append(issue)

                    # Check base classes for cross-module access
                    for base in art.bases:
                        issue = _detect_boundary_violation_from_type(
                            source_module=source_module,
                            type_hint=base,
                            artifact_name=art.qualified_name,
                            graph=graph,
                        )
                        if issue:
                            issues.append(issue)

            # Check if manifest references private files from other modules
            for read_path in m.files_read:
                fname = Path(read_path).name
                if fname.startswith("_") and fname != "__init__.py":
                    read_module = _extract_module_from_path(read_path)
                    for fs in m.all_file_specs:
                        src_module = _extract_module_from_path(fs.path)
                        if src_module and read_module and src_module != read_module:
                            issues.append(
                                CoherenceIssue(
                                    issue_type=IssueType.BOUNDARY_VIOLATION,
                                    severity=IssueSeverity.WARNING,
                                    message=(
                                        f"Manifest '{m.slug}' accesses private file "
                                        f"'{read_path}' in module '{read_module}'"
                                    ),
                                    file=read_path,
                                    manifests=(m.slug,),
                                    suggestion=(
                                        f"Use public API from '{read_module}/__init__.py'"
                                    ),
                                )
                            )
                            break  # one issue per read path

        return issues


def _extract_module_from_path(file_path: str) -> str:
    """Extract module name from file path (immediate parent dir)."""
    if not file_path:
        return ""
    parent = Path(file_path).parent
    if not parent or str(parent) in (".", ""):
        return ""
    return parent.name


def _detect_boundary_violation(
    source_module: str,
    target_module: str,
    artifact_name: str,
) -> Optional[CoherenceIssue]:
    if source_module == target_module or not source_module or not target_module:
        return None

    forbidden_targets = _BOUNDARY_VIOLATION_PATTERNS.get(source_module, [])
    if target_module in forbidden_targets:
        return CoherenceIssue(
            issue_type=IssueType.BOUNDARY_VIOLATION,
            severity=IssueSeverity.WARNING,
            message=(
                f"Module '{source_module}' directly accesses module '{target_module}' "
                f"in artifact '{artifact_name}'. This violates module boundary rules."
            ),
            file=f"{source_module} -> {target_module}",
            suggestion=(
                f"Consider using an intermediate service layer. '{source_module}' "
                f"should access '{target_module}' through a services module."
            ),
        )
    return None


def _detect_boundary_violation_from_type(
    source_module: str,
    type_hint: str,
    artifact_name: str,
    graph: KnowledgeGraph,
) -> Optional[CoherenceIssue]:
    """Detect boundary violations from type hints."""
    # Check graph for artifacts matching the type hint
    for node in graph.nodes:
        if isinstance(node, ArtifactNode) and node.name == type_hint:
            edges = graph.get_edges(node.id)
            for edge in edges:
                target_node = graph.get_node(edge.target_id)
                if isinstance(target_node, FileNode):
                    target_module = _extract_module_from_path(target_node.path)
                    violation = _detect_boundary_violation(
                        source_module, target_module, artifact_name
                    )
                    if violation:
                        return violation

    # Heuristic: "Repository" types likely in "data" module
    if "Repository" in type_hint:
        return _detect_boundary_violation(source_module, "data", artifact_name)

    return None
