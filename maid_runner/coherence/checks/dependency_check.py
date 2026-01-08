"""Dependency availability check for coherence validation.

This module verifies that dependencies declared in a manifest's readonlyFiles
exist in the knowledge graph. Missing dependencies indicate that a manifest
references files that are not yet tracked, which could lead to broken builds
or missing functionality.

Functions:
    check_dependency_availability: Main check function returning CoherenceIssues
    _get_required_dependencies: Extract readonlyFiles from manifest data
    _check_dependency_exists: Verify a dependency exists in the graph
"""

from typing import List

from maid_runner.coherence.result import CoherenceIssue, IssueType, IssueSeverity
from maid_runner.graph.model import KnowledgeGraph


def check_dependency_availability(
    manifest_data: dict, graph: KnowledgeGraph
) -> List[CoherenceIssue]:
    """Check that all dependencies in manifest's readonlyFiles exist in the graph.

    Verifies that each file listed in the manifest's readonlyFiles field has
    a corresponding FILE node in the knowledge graph. Missing dependencies
    are reported as CoherenceIssue with ERROR severity.

    Args:
        manifest_data: The manifest data dictionary containing readonlyFiles.
        graph: The KnowledgeGraph to check for dependency existence.

    Returns:
        List of CoherenceIssue for each missing dependency. Empty list if
        all dependencies exist.

    Example:
        manifest = {"readonlyFiles": ["src/utils.py", "src/types.py"]}
        issues = check_dependency_availability(manifest, graph)
        for issue in issues:
            print(f"Missing: {issue.message}")
    """
    issues: List[CoherenceIssue] = []

    dependencies = _get_required_dependencies(manifest_data)

    for dependency in dependencies:
        if not _check_dependency_exists(dependency, graph):
            issue = CoherenceIssue(
                issue_type=IssueType.DEPENDENCY,
                severity=IssueSeverity.ERROR,
                message=f"Dependency not found: {dependency}",
                suggestion=(
                    "Create the dependency file first or reorder manifests "
                    "so this file is created before being referenced."
                ),
                location=dependency,
            )
            issues.append(issue)

    return issues


def _get_required_dependencies(manifest_data: dict) -> List[str]:
    """Extract the list of required dependencies from manifest data.

    Retrieves the readonlyFiles field from the manifest, which lists
    files that the manifest depends on but does not modify.

    Args:
        manifest_data: The manifest data dictionary.

    Returns:
        List of file paths from readonlyFiles. Returns empty list if
        readonlyFiles is missing, None, or empty.

    Example:
        manifest = {"readonlyFiles": ["src/utils.py"]}
        deps = _get_required_dependencies(manifest)
        # deps == ["src/utils.py"]
    """
    readonly_files = manifest_data.get("readonlyFiles")

    if readonly_files is None:
        return []

    if not isinstance(readonly_files, list):
        return []

    return readonly_files


def _check_dependency_exists(dependency: str, graph: KnowledgeGraph) -> bool:
    """Check if a dependency file exists in the knowledge graph.

    Queries the graph for a FILE node with the given path. File nodes
    are identified by the "file:" prefix followed by the file path.

    Args:
        dependency: The file path to check for existence.
        graph: The KnowledgeGraph to query.

    Returns:
        True if a FILE node with the given path exists, False otherwise.

    Example:
        exists = _check_dependency_exists("src/utils.py", graph)
        if not exists:
            print("Dependency missing!")
    """
    node_id = f"file:{dependency}"
    node = graph.get_node(node_id)
    return node is not None
