"""Pattern consistency check for coherence validation.

This module validates that artifacts follow established architectural patterns
(Repository, Service, Handler, etc.) based on patterns detected in the knowledge
graph. It returns CoherenceIssue with IssueType.PATTERN for any pattern
consistency violations found.

Functions:
    check_pattern_consistency: Main function that validates pattern consistency
    _detect_patterns: Helper to detect patterns from the knowledge graph
    _validate_pattern_usage: Helper to validate manifest artifacts against patterns

Usage:
    from maid_runner.coherence.checks.pattern_check import check_pattern_consistency

    issues = check_pattern_consistency(
        manifest_data=manifest,
        graph=knowledge_graph,
    )
"""

from typing import Any, Dict, List

from maid_runner.coherence.result import CoherenceIssue, IssueSeverity, IssueType
from maid_runner.graph.model import KnowledgeGraph, NodeType


# Pattern suffixes and their expected module locations
_PATTERN_DEFINITIONS = {
    "Repository": {
        "suffix": "Repository",
        "module": "repositories",
    },
    "Service": {
        "suffix": "Service",
        "module": "services",
    },
    "Handler": {
        "suffix": "Handler",
        "module": "handlers",
    },
}


def check_pattern_consistency(
    manifest_data: dict,
    graph: KnowledgeGraph,
) -> List[CoherenceIssue]:
    """Validate that artifacts follow established architectural patterns.

    Detects patterns from the knowledge graph and validates that each artifact
    in the manifest follows the established patterns. Returns a list of
    CoherenceIssue with IssueType.PATTERN for any violations.

    Args:
        manifest_data: The manifest data dictionary to check.
        graph: The KnowledgeGraph containing existing artifacts and patterns.

    Returns:
        List of CoherenceIssue instances for any pattern violations.
    """
    issues: List[CoherenceIssue] = []

    # Handle None or empty manifest
    if not manifest_data:
        return issues

    # Detect patterns from the graph
    patterns = _detect_patterns(graph=graph)

    # If no patterns detected, no violations possible
    if not patterns:
        return issues

    # Validate pattern usage
    issues = _validate_pattern_usage(
        manifest_data=manifest_data,
        patterns=patterns,
    )

    return issues


def _detect_patterns(graph: KnowledgeGraph) -> Dict[str, Any]:
    """Detect architectural patterns from the knowledge graph.

    Scans artifact nodes in the graph to detect naming patterns like:
    - "Repository": classes ending in "Repository"
    - "Service": classes ending in "Service"
    - "Handler": classes ending in "Handler"

    Args:
        graph: The KnowledgeGraph to scan for patterns.

    Returns:
        Dict containing detected pattern information. Keys are pattern names
        (e.g., "Repository", "Service"), values contain pattern details.
    """
    patterns: Dict[str, Any] = {}

    # Scan all nodes for artifact nodes with class type
    for node in graph.nodes:
        if node.node_type != NodeType.ARTIFACT:
            continue

        # Check if the artifact is a class
        artifact_type = getattr(node, "artifact_type", None)
        if artifact_type != "class":
            continue

        # Get the artifact name
        name = getattr(node, "name", None)
        if not name:
            continue

        # Check for pattern suffixes
        for pattern_name, pattern_def in _PATTERN_DEFINITIONS.items():
            suffix = pattern_def["suffix"]
            if name.endswith(suffix):
                # Record this pattern
                if pattern_name not in patterns:
                    patterns[pattern_name] = {
                        "suffix": suffix,
                        "module": pattern_def["module"],
                        "classes": [],
                    }
                patterns[pattern_name]["classes"].append(name)

    return patterns


def _validate_pattern_usage(
    manifest_data: dict,
    patterns: Dict[str, Any],
) -> List[CoherenceIssue]:
    """Validate that manifest artifacts follow detected patterns.

    Checks each artifact in the manifest against detected patterns:
    - For Repository classes: should be in repositories module
    - For Service classes: should be in services module
    - For Handler classes: should be in handlers module

    Also checks if classes in pattern modules follow the naming convention.

    Args:
        manifest_data: The manifest data dictionary to check.
        patterns: Dict of detected patterns from _detect_patterns.

    Returns:
        List of CoherenceIssue instances for pattern violations.
    """
    issues: List[CoherenceIssue] = []

    # Handle empty patterns
    if not patterns:
        return issues

    # Get expectedArtifacts from manifest
    expected_artifacts = manifest_data.get("expectedArtifacts")
    if expected_artifacts is None:
        return issues

    # Get the file path and contains list
    file_path = expected_artifacts.get("file", "")
    contains = expected_artifacts.get("contains")
    if not contains:
        return issues

    # Validate each artifact
    for artifact in contains:
        # Skip if not a dict
        if not isinstance(artifact, dict):
            continue

        artifact_name = artifact.get("name")
        artifact_type = artifact.get("type")

        # Skip if missing name or type
        if not artifact_name or not artifact_type:
            continue

        # Only check classes
        if artifact_type != "class":
            continue

        # Check for pattern violations
        issue = _check_class_pattern(
            class_name=artifact_name,
            file_path=file_path,
            patterns=patterns,
        )
        if issue is not None:
            issues.append(issue)

    return issues


def _check_class_pattern(
    class_name: str,
    file_path: str,
    patterns: Dict[str, Any],
) -> CoherenceIssue | None:
    """Check if a class follows pattern conventions.

    Validates:
    1. If class name ends with a pattern suffix, it should be in the correct module
    2. If class is in a pattern module, it should follow the naming convention

    Args:
        class_name: The name of the class to check.
        file_path: The file path where the class is defined.
        patterns: Dict of detected patterns.

    Returns:
        CoherenceIssue if a violation is detected, None otherwise.
    """
    # Check 1: If class name ends with pattern suffix, verify module location
    for pattern_name, pattern_info in patterns.items():
        suffix = pattern_info.get("suffix", "")
        expected_module = pattern_info.get("module", "")

        if class_name.endswith(suffix):
            # Class follows the naming pattern - check if in correct module
            if expected_module and expected_module not in file_path:
                return CoherenceIssue(
                    issue_type=IssueType.PATTERN,
                    severity=IssueSeverity.WARNING,
                    message=(
                        f"Class '{class_name}' follows the {pattern_name} pattern "
                        f"but is not in the '{expected_module}' module. "
                        f"Found in: {file_path}"
                    ),
                    suggestion=(
                        f"Consider moving '{class_name}' to a file in the "
                        f"'{expected_module}' module to follow the {pattern_name} pattern."
                    ),
                    location=file_path,
                )

    # Check 2: If class is in a pattern module, verify naming convention
    for pattern_name, pattern_info in patterns.items():
        suffix = pattern_info.get("suffix", "")
        expected_module = pattern_info.get("module", "")

        if expected_module and expected_module in file_path:
            # Class is in a pattern module - check naming
            if not class_name.endswith(suffix) and not class_name.startswith("_"):
                return CoherenceIssue(
                    issue_type=IssueType.PATTERN,
                    severity=IssueSeverity.WARNING,
                    message=(
                        f"Class '{class_name}' is in the '{expected_module}' module "
                        f"but does not follow the {pattern_name} naming convention "
                        f"(expected suffix: '{suffix}')."
                    ),
                    suggestion=(
                        f"Consider renaming '{class_name}' to '{class_name}{suffix}' "
                        f"to follow the {pattern_name} pattern, or move it to a "
                        f"different module."
                    ),
                    location=file_path,
                )

    return None
