"""Architectural constraint validation for coherence checks.

This module enforces configurable architectural constraints loaded from
.maid-constraints.json configuration files. It validates that manifest changes
adhere to defined architectural rules and returns CoherenceIssue with
IssueType.CONSTRAINT for any violations.

Classes:
    ConstraintRule: Class representing a single constraint rule
    ConstraintConfig: Class containing constraint configuration

Functions:
    load_constraint_config: Load constraint configuration from file
    check_architectural_constraints: Main function to check constraints
    _evaluate_constraint: Helper to evaluate a single constraint rule

Usage:
    from maid_runner.coherence.checks.constraint_check import (
        check_architectural_constraints,
        load_constraint_config,
        ConstraintConfig,
        ConstraintRule,
    )

    issues = check_architectural_constraints(
        manifest_data=manifest,
        graph=knowledge_graph,
        config_path=Path(".maid-constraints.json"),
    )
"""

import fnmatch
import json
from pathlib import Path
from typing import Any, Dict, List, Optional

from maid_runner.coherence.result import CoherenceIssue, IssueSeverity, IssueType
from maid_runner.graph.model import KnowledgeGraph


class ConstraintRule:
    """Represents a single architectural constraint rule.

    Defines a constraint that can be checked against manifest files to ensure
    architectural patterns are followed.

    Attributes:
        name: Unique identifier for the rule.
        description: Human-readable description of what the rule enforces.
        pattern: Dictionary containing matching patterns (file_pattern,
            forbidden_imports, etc.).
        severity: Severity level for violations ("error" or "warning").
        suggestion: Recommended action to resolve violations.
    """

    def __init__(
        self,
        name: str,
        description: str,
        pattern: Dict[str, Any],
        severity: str,
        suggestion: str,
    ) -> None:
        """Initialize a ConstraintRule.

        Args:
            name: Unique identifier for the rule.
            description: Human-readable description of what the rule enforces.
            pattern: Dictionary containing matching patterns.
            severity: Severity level for violations ("error" or "warning").
            suggestion: Recommended action to resolve violations.
        """
        self.name = name
        self.description = description
        self.pattern = pattern
        self.severity = severity
        self.suggestion = suggestion


class ConstraintConfig:
    """Configuration for architectural constraint validation.

    Contains all constraint rules and settings for the constraint checker.

    Attributes:
        version: Configuration version string.
        rules: List of ConstraintRule instances to evaluate.
        enabled: Whether constraint checking is enabled.
    """

    def __init__(
        self,
        version: str = "1",
        rules: Optional[List[ConstraintRule]] = None,
        enabled: bool = True,
    ) -> None:
        """Initialize a ConstraintConfig.

        Args:
            version: Configuration version string. Defaults to "1".
            rules: List of ConstraintRule instances. Defaults to empty list.
            enabled: Whether constraint checking is enabled. Defaults to True.
        """
        self.version = version
        self.rules = rules if rules is not None else []
        self.enabled = enabled


def load_constraint_config(config_path: Optional[Path]) -> ConstraintConfig:
    """Load constraint configuration from a JSON file.

    Loads and parses the constraint configuration from the specified path.
    If no path is provided, looks for .maid-constraints.json in the current
    directory. If the file does not exist or cannot be parsed, returns a
    default empty configuration.

    Args:
        config_path: Path to the configuration file, or None to use default.

    Returns:
        ConstraintConfig instance with loaded rules, or default if not found.
    """
    # Determine the config path
    if config_path is None:
        config_path = Path.cwd() / ".maid-constraints.json"

    # Return default if file doesn't exist
    if not config_path.exists():
        return ConstraintConfig()

    # Try to load and parse the config
    try:
        config_data = json.loads(config_path.read_text())
    except (json.JSONDecodeError, OSError):
        return ConstraintConfig()

    # Parse rules into ConstraintRule instances
    rules: List[ConstraintRule] = []
    for rule_data in config_data.get("rules", []):
        rule = ConstraintRule(
            name=rule_data.get("name", ""),
            description=rule_data.get("description", ""),
            pattern=rule_data.get("pattern", {}),
            severity=rule_data.get("severity", "error"),
            suggestion=rule_data.get("suggestion", ""),
        )
        rules.append(rule)

    return ConstraintConfig(
        version=config_data.get("version", "1"),
        rules=rules,
        enabled=config_data.get("enabled", True),
    )


def _evaluate_constraint(
    rule: ConstraintRule,
    manifest_data: dict,
    graph: KnowledgeGraph,
) -> Optional[CoherenceIssue]:
    """Evaluate a single constraint rule against manifest data.

    Checks if the manifest violates the constraint rule by examining file
    patterns and forbidden imports.

    Args:
        rule: The ConstraintRule to evaluate.
        manifest_data: The manifest data dictionary to check.
        graph: The KnowledgeGraph for additional context.

    Returns:
        CoherenceIssue if a violation is found, None otherwise.
    """
    file_pattern = rule.pattern.get("file_pattern")
    if not file_pattern:
        return None

    # Get all files from the manifest
    files_to_check: List[str] = []

    # Gather files from creatableFiles
    creatable = manifest_data.get("creatableFiles")
    if isinstance(creatable, list):
        files_to_check.extend(creatable)

    # Gather files from editableFiles
    editable = manifest_data.get("editableFiles")
    if isinstance(editable, list):
        files_to_check.extend(editable)

    # Check expectedArtifacts file
    expected_artifacts = manifest_data.get("expectedArtifacts")
    if isinstance(expected_artifacts, dict):
        artifact_file = expected_artifacts.get("file")
        if artifact_file and artifact_file not in files_to_check:
            files_to_check.append(artifact_file)

    # Check if any files match the pattern
    matching_files: List[str] = []
    for file_path in files_to_check:
        if fnmatch.fnmatch(file_path, file_pattern):
            matching_files.append(file_path)

    # If no files match the pattern, no violation
    if not matching_files:
        return None

    # Check for forbidden imports constraint
    forbidden_imports = rule.pattern.get("forbidden_imports")
    if forbidden_imports:
        # For now, just flag the constraint violation since the file matches
        # the pattern - actual import checking would require source analysis
        # which is beyond the scope of manifest-level validation
        severity = (
            IssueSeverity.ERROR
            if rule.severity.lower() == "error"
            else IssueSeverity.WARNING
        )

        return CoherenceIssue(
            issue_type=IssueType.CONSTRAINT,
            severity=severity,
            message=rule.description,
            suggestion=rule.suggestion,
            location=matching_files[0],
        )

    return None


def check_architectural_constraints(
    manifest_data: dict,
    graph: KnowledgeGraph,
    config_path: Optional[Path] = None,
) -> List[CoherenceIssue]:
    """Check manifest against configured architectural constraints.

    Loads the constraint configuration and evaluates all enabled rules
    against the provided manifest data.

    Args:
        manifest_data: The manifest data dictionary to check.
        graph: The KnowledgeGraph for additional context.
        config_path: Optional path to the constraint configuration file.
            If None, looks for .maid-constraints.json in current directory.

    Returns:
        List of CoherenceIssue instances for any constraint violations found.
    """
    issues: List[CoherenceIssue] = []

    # Load configuration
    config = load_constraint_config(config_path)

    # Skip if constraints are disabled
    if not config.enabled:
        return issues

    # Evaluate each rule
    for rule in config.rules:
        issue = _evaluate_constraint(rule, manifest_data, graph)
        if issue is not None:
            issues.append(issue)

    return issues
