"""Module boundary validation for coherence checks.

This module validates that artifacts stay within appropriate module boundaries
based on file paths. For example, it detects if a 'controllers' module is
directly accessing a 'data' module, suggesting the need for a service layer.
Returns CoherenceIssue with IssueType.BOUNDARY_VIOLATION for any violations found.

Functions:
    check_module_boundaries: Main function that validates module boundary compliance
    _extract_module_from_path: Helper to extract module name from file path
    _detect_boundary_violation: Helper to detect if modules violate boundary rules

Usage:
    from maid_runner.coherence.checks.module_boundary import check_module_boundaries
    from maid_runner.graph.model import KnowledgeGraph

    issues = check_module_boundaries(
        manifest_data=manifest,
        graph=knowledge_graph,
    )
"""

from pathlib import Path
from typing import Dict, List, Optional

from maid_runner.coherence.result import CoherenceIssue, IssueSeverity, IssueType
from maid_runner.graph.model import KnowledgeGraph


# Known bad patterns: source_module -> target_module
# These represent direct access that should go through an intermediate layer
_BOUNDARY_VIOLATION_PATTERNS: Dict[str, List[str]] = {
    "controllers": ["data"],  # Controllers should use services, not data directly
    "cli": ["data"],  # CLI should use services, not data directly
}


def check_module_boundaries(
    manifest_data: dict,
    graph: KnowledgeGraph,
) -> List[CoherenceIssue]:
    """Validate module boundary compliance for a manifest.

    Examines the manifest's expectedArtifacts and checks if the target file's
    module violates any known boundary patterns. Uses the KnowledgeGraph to
    examine cross-module dependencies.

    Args:
        manifest_data: The manifest data dictionary to check.
        graph: The KnowledgeGraph for examining module relationships.

    Returns:
        List of CoherenceIssue instances for any boundary violations found.
    """
    issues: List[CoherenceIssue] = []

    # Get expectedArtifacts from manifest
    expected_artifacts = manifest_data.get("expectedArtifacts")
    if expected_artifacts is None:
        return issues

    # Extract target file path
    target_file = expected_artifacts.get("file")
    if not target_file:
        return issues

    # Get the module for the target file
    source_module = _extract_module_from_path(target_file)
    if not source_module:
        return issues

    # Get the contains list
    contains = expected_artifacts.get("contains", [])
    if not contains:
        return issues

    # Check each artifact for potential boundary violations
    for artifact in contains:
        artifact_name = artifact.get("name", "")

        # Check artifact arguments for type hints that might indicate cross-module access
        args = artifact.get("args", [])
        for arg in args:
            arg_type = arg.get("type", "")
            if arg_type:
                # Attempt to detect target module from type hint
                # For example, if an argument has type "UserRepository",
                # and the source module is "controllers", this might be a violation
                violation = _detect_boundary_violation_from_type(
                    source_module=source_module,
                    type_hint=arg_type,
                    artifact_name=artifact_name,
                    graph=graph,
                )
                if violation is not None:
                    issues.append(violation)

    return issues


def _extract_module_from_path(file_path: str) -> str:
    """Extract module name from a file path.

    Returns the immediate parent directory name as the module.
    For example, 'src/auth/service.py' returns 'auth'.

    Args:
        file_path: The file path to extract the module from.

    Returns:
        The module name (parent directory name), or empty string if not determinable.
    """
    if not file_path:
        return ""

    path = Path(file_path)

    # Get the parent directory
    parent = path.parent

    # Handle edge cases
    if not parent or str(parent) == "." or str(parent) == "":
        return ""

    # Return the immediate parent directory name
    return parent.name


def _detect_boundary_violation(
    source_module: str,
    target_module: str,
    artifact_name: str,
) -> Optional[CoherenceIssue]:
    """Detect if there's a boundary violation between modules.

    Checks if the source module accessing the target module violates
    any known architectural boundary patterns.

    Args:
        source_module: The module where the artifact is being defined.
        target_module: The module being accessed.
        artifact_name: The name of the artifact involved.

    Returns:
        CoherenceIssue if a violation is detected, None otherwise.
    """
    # Return None if modules are the same
    if source_module == target_module:
        return None

    # Return None for empty modules
    if not source_module or not target_module:
        return None

    # Check if this is a known bad pattern
    forbidden_targets = _BOUNDARY_VIOLATION_PATTERNS.get(source_module, [])
    if target_module in forbidden_targets:
        return CoherenceIssue(
            issue_type=IssueType.BOUNDARY_VIOLATION,
            severity=IssueSeverity.WARNING,
            message=(
                f"Module '{source_module}' directly accesses module '{target_module}' "
                f"in artifact '{artifact_name}'. This violates module boundary rules."
            ),
            suggestion=(
                f"Consider using an intermediate service layer. '{source_module}' "
                f"should access '{target_module}' through a services module."
            ),
            location=f"{source_module} -> {target_module}",
        )

    return None


def _detect_boundary_violation_from_type(
    source_module: str,
    type_hint: str,
    artifact_name: str,
    graph: KnowledgeGraph,
) -> Optional[CoherenceIssue]:
    """Detect boundary violations from type hints in artifact arguments.

    Examines type hints to determine if they reference artifacts from
    modules that shouldn't be directly accessed.

    Args:
        source_module: The module where the artifact is being defined.
        type_hint: The type hint string from an argument.
        artifact_name: The name of the artifact involved.
        graph: The KnowledgeGraph for module lookups.

    Returns:
        CoherenceIssue if a violation is detected, None otherwise.
    """
    # Check graph for artifacts matching the type hint
    # Look for artifact nodes whose name matches the type_hint
    for node in graph.nodes:
        if hasattr(node, "name") and hasattr(node, "artifact_type"):
            if node.name == type_hint:
                # Found a matching artifact, now find its module
                # Look for edges connecting this artifact to a file
                edges = graph.get_edges(node.id)
                for edge in edges:
                    target_node = graph.get_node(edge.target_id)
                    if target_node is not None and hasattr(target_node, "path"):
                        target_file_path = target_node.path
                        target_module = _extract_module_from_path(target_file_path)

                        # Check for boundary violation
                        violation = _detect_boundary_violation(
                            source_module=source_module,
                            target_module=target_module,
                            artifact_name=artifact_name,
                        )
                        if violation is not None:
                            return violation

    # If type hint contains "Repository" and source is controllers/cli,
    # assume it's from data module (heuristic for common naming conventions)
    if "Repository" in type_hint:
        violation = _detect_boundary_violation(
            source_module=source_module,
            target_module="data",
            artifact_name=artifact_name,
        )
        if violation is not None:
            return violation

    return None
