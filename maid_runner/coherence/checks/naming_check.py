"""Naming convention compliance check for coherence validation.

This module validates that new artifacts follow established naming patterns
in the codebase. It extracts naming patterns from existing codebase artifacts
and validates that new artifacts follow similar conventions. Returns
CoherenceIssue with IssueType.NAMING for any naming violations.

Functions:
    check_naming_conventions: Main function that validates naming conventions
    _extract_naming_patterns: Helper to extract patterns from existing artifacts
    _validate_artifact_name: Helper to validate a single artifact name

Usage:
    from maid_runner.coherence.checks.naming_check import check_naming_conventions

    issues = check_naming_conventions(
        manifest_data=manifest,
        system_artifacts=aggregated_artifacts,
    )
"""

from typing import Dict, List, Optional

from maid_runner.coherence.result import CoherenceIssue, IssueSeverity, IssueType


# Common function prefixes to detect patterns
_FUNCTION_PREFIXES = ["get_", "fetch_", "create_", "validate_"]

# Common class suffixes to detect patterns
_CLASS_SUFFIXES = ["Service", "Repository", "Validator", "Handler"]

# Minimum occurrences needed to establish a pattern
_MIN_PATTERN_OCCURRENCES = 2


def check_naming_conventions(
    manifest_data: dict,
    system_artifacts: List[Dict],
) -> List[CoherenceIssue]:
    """Validate that artifact names follow established naming conventions.

    Extracts naming patterns from existing system artifacts and validates
    that each artifact in the manifest follows these conventions. Returns
    a list of CoherenceIssue with IssueType.NAMING for any violations.

    Args:
        manifest_data: The manifest data dictionary to check.
        system_artifacts: List of artifacts aggregated from all existing manifests.
            Each artifact is a dict with "name", "type", and "file" keys.

    Returns:
        List of CoherenceIssue instances for any naming convention violations.
    """
    issues: List[CoherenceIssue] = []

    # Get expectedArtifacts from manifest
    expected_artifacts = manifest_data.get("expectedArtifacts")
    if expected_artifacts is None:
        return issues

    # Get the contains list
    contains = expected_artifacts.get("contains", [])
    if not contains:
        return issues

    # Extract naming patterns from system artifacts
    patterns = _extract_naming_patterns(system_artifacts)

    # If no patterns were extracted, we cannot detect violations
    if not patterns:
        return issues

    # Validate each artifact's name
    for artifact in contains:
        artifact_name = artifact.get("name")
        artifact_type = artifact.get("type")

        # Skip if missing name or type
        if not artifact_name or not artifact_type:
            continue

        # Validate the artifact name
        issue = _validate_artifact_name(
            name=artifact_name,
            artifact_type=artifact_type,
            patterns=patterns,
        )

        if issue is not None:
            issues.append(issue)

    return issues


def _extract_naming_patterns(
    system_artifacts: List[Dict],
) -> Dict[str, List[str]]:
    """Extract naming patterns from existing artifacts.

    Analyzes artifact names to find common prefixes for functions and
    common suffixes for classes. A pattern is only included if it appears
    at least _MIN_PATTERN_OCCURRENCES times.

    Args:
        system_artifacts: List of existing artifacts, each with "name",
            "type", and "file" keys.

    Returns:
        Dict mapping artifact types to list of patterns found.
        Example: {"function": ["get_*", "fetch_*"], "class": ["*Service"]}
    """
    patterns: Dict[str, List[str]] = {}

    if not system_artifacts:
        return patterns

    # Group artifacts by type
    artifacts_by_type: Dict[str, List[str]] = {}
    for artifact in system_artifacts:
        artifact_type = artifact.get("type")
        artifact_name = artifact.get("name")

        if not artifact_type or not artifact_name:
            continue

        if artifact_type not in artifacts_by_type:
            artifacts_by_type[artifact_type] = []
        artifacts_by_type[artifact_type].append(artifact_name)

    # Extract function prefix patterns
    if "function" in artifacts_by_type:
        function_names = artifacts_by_type["function"]
        function_patterns = _extract_prefix_patterns(function_names)
        if function_patterns:
            patterns["function"] = function_patterns

    # Extract class suffix patterns
    if "class" in artifacts_by_type:
        class_names = artifacts_by_type["class"]
        class_patterns = _extract_suffix_patterns(class_names)
        if class_patterns:
            patterns["class"] = class_patterns

    return patterns


def _extract_prefix_patterns(names: List[str]) -> List[str]:
    """Extract common prefix patterns from a list of names.

    Args:
        names: List of artifact names to analyze.

    Returns:
        List of prefix patterns like ["get_*", "fetch_*"].
    """
    prefix_counts: Dict[str, int] = {}

    for name in names:
        for prefix in _FUNCTION_PREFIXES:
            if name.startswith(prefix):
                pattern = f"{prefix}*"
                prefix_counts[pattern] = prefix_counts.get(pattern, 0) + 1
                break

    # Only return patterns that appear at least MIN_PATTERN_OCCURRENCES times
    return [
        pattern
        for pattern, count in prefix_counts.items()
        if count >= _MIN_PATTERN_OCCURRENCES
    ]


def _extract_suffix_patterns(names: List[str]) -> List[str]:
    """Extract common suffix patterns from a list of names.

    Args:
        names: List of artifact names to analyze.

    Returns:
        List of suffix patterns like ["*Service", "*Repository"].
    """
    suffix_counts: Dict[str, int] = {}

    for name in names:
        for suffix in _CLASS_SUFFIXES:
            if name.endswith(suffix):
                pattern = f"*{suffix}"
                suffix_counts[pattern] = suffix_counts.get(pattern, 0) + 1
                break

    # Only return patterns that appear at least MIN_PATTERN_OCCURRENCES times
    return [
        pattern
        for pattern, count in suffix_counts.items()
        if count >= _MIN_PATTERN_OCCURRENCES
    ]


def _validate_artifact_name(
    name: str,
    artifact_type: str,
    patterns: Dict[str, List[str]],
) -> Optional[CoherenceIssue]:
    """Validate a single artifact name against established patterns.

    Checks if the artifact name matches any of the established patterns
    for its type. If no patterns exist for the type, returns None (no
    violation). If the name doesn't match any pattern, returns a
    CoherenceIssue.

    Args:
        name: The artifact name to validate.
        artifact_type: The type of the artifact (function, class, etc.).
        patterns: Dict mapping artifact types to list of patterns.

    Returns:
        CoherenceIssue if the name violates conventions, None otherwise.
    """
    # If no patterns exist for this type, cannot determine violation
    if artifact_type not in patterns:
        return None

    type_patterns = patterns[artifact_type]
    if not type_patterns:
        return None

    # Check if name matches any pattern
    for pattern in type_patterns:
        if _matches_pattern(name, pattern):
            return None

    # Name doesn't match any pattern - create an issue
    pattern_list = ", ".join(type_patterns)
    return CoherenceIssue(
        issue_type=IssueType.NAMING,
        severity=IssueSeverity.WARNING,
        message=(
            f"Artifact '{name}' does not follow established naming patterns. "
            f"Expected patterns for {artifact_type}: {pattern_list}"
        ),
        suggestion=(
            f"Consider renaming '{name}' to match one of the established patterns: "
            f"{pattern_list}"
        ),
        location=None,
    )


def _matches_pattern(name: str, pattern: str) -> bool:
    """Check if a name matches a wildcard pattern.

    Supports simple wildcard patterns:
    - "prefix_*" matches names starting with "prefix_"
    - "*suffix" matches names ending with "suffix"

    Args:
        name: The name to check.
        pattern: The pattern with wildcard (*).

    Returns:
        True if the name matches the pattern, False otherwise.
    """
    if pattern.startswith("*"):
        # Suffix pattern like "*Service"
        suffix = pattern[1:]
        return name.endswith(suffix)
    elif pattern.endswith("*"):
        # Prefix pattern like "get_*"
        prefix = pattern[:-1]
        return name.startswith(prefix)
    else:
        # Exact match
        return name == pattern
