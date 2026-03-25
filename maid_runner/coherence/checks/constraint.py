"""V2 Architectural constraint check.

Spec: 08-coherence-module.md - coherence/checks/constraint.py
Ported from v1: coherence/checks/constraint_check.py
"""

from __future__ import annotations

import fnmatch
import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional

from maid_runner.core.types import Manifest
from maid_runner.coherence.result_v2 import (
    CoherenceIssue,
    IssueSeverity,
    IssueType,
)
from maid_runner.coherence.checks.base import BaseCheck
from maid_runner.graph.model import KnowledgeGraph


@dataclass(frozen=True)
class ConstraintRule:
    """A single architectural constraint rule."""

    name: str
    description: str
    pattern: dict[str, Any] = field(default_factory=dict)
    severity: str = "error"
    suggestion: str = ""


@dataclass
class ConstraintConfig:
    """Configuration for architectural constraint validation."""

    version: str = "1"
    rules: list[ConstraintRule] = field(default_factory=list)
    enabled: bool = True


def load_constraint_config(config_path: Optional[Path] = None) -> ConstraintConfig:
    """Load constraint configuration from a JSON or YAML file."""
    if config_path is None:
        config_path = Path.cwd() / ".maid-constraints.json"

    if not config_path.exists():
        return ConstraintConfig()

    try:
        config_data = json.loads(config_path.read_text())
    except (json.JSONDecodeError, OSError):
        return ConstraintConfig()

    rules = []
    for rule_data in config_data.get("rules", []):
        rules.append(
            ConstraintRule(
                name=rule_data.get("name", ""),
                description=rule_data.get("description", ""),
                pattern=rule_data.get("pattern", {}),
                severity=rule_data.get("severity", "error"),
                suggestion=rule_data.get("suggestion", ""),
            )
        )

    return ConstraintConfig(
        version=config_data.get("version", "1"),
        rules=rules,
        enabled=config_data.get("enabled", True),
    )


class ConstraintCheck(BaseCheck):
    """Enforces custom architectural constraints.

    Reads constraints from .maid-constraints.json if present.
    Evaluates file_pattern + forbidden_imports rules against manifests.

    Severity: Configurable per constraint.
    """

    def __init__(self, config_path: Optional[Path] = None):
        self._config_path = config_path

    @property
    def name(self) -> str:
        return "constraint"

    def run(
        self, graph: KnowledgeGraph, manifests: list[Manifest]
    ) -> list[CoherenceIssue]:
        config = load_constraint_config(self._config_path)
        if not config.enabled:
            return []

        issues: list[CoherenceIssue] = []
        for rule in config.rules:
            for m in manifests:
                issue = _evaluate_constraint(rule, m)
                if issue:
                    issues.append(issue)

        return issues


def _evaluate_constraint(
    rule: ConstraintRule, manifest: Manifest
) -> Optional[CoherenceIssue]:
    """Evaluate a single constraint rule against a manifest."""
    file_pattern = rule.pattern.get("file_pattern")
    if not file_pattern:
        return None

    # Collect all files from the manifest
    files_to_check: list[str] = []
    for fs in manifest.all_file_specs:
        files_to_check.append(fs.path)
    files_to_check.extend(manifest.files_read)

    # Check if any files match the pattern
    matching_files = [f for f in files_to_check if fnmatch.fnmatch(f, file_pattern)]
    if not matching_files:
        return None

    # Check for forbidden imports constraint
    forbidden_imports = rule.pattern.get("forbidden_imports")
    if forbidden_imports:
        severity = (
            IssueSeverity.ERROR
            if rule.severity.lower() == "error"
            else IssueSeverity.WARNING
        )
        return CoherenceIssue(
            issue_type=IssueType.CONSTRAINT,
            severity=severity,
            message=rule.description,
            file=matching_files[0],
            manifests=(manifest.slug,),
            suggestion=rule.suggestion,
        )

    # Check max_artifacts_per_file constraint
    max_artifacts = rule.pattern.get("max_artifacts_per_file")
    if max_artifacts is not None:
        for fs in manifest.all_file_specs:
            if (
                fnmatch.fnmatch(fs.path, file_pattern)
                and len(fs.artifacts) > max_artifacts
            ):
                severity = (
                    IssueSeverity.ERROR
                    if rule.severity.lower() == "error"
                    else IssueSeverity.WARNING
                )
                return CoherenceIssue(
                    issue_type=IssueType.CONSTRAINT,
                    severity=severity,
                    message=(
                        f"File '{fs.path}' has {len(fs.artifacts)} artifacts, "
                        f"exceeding limit of {max_artifacts}"
                    ),
                    file=fs.path,
                    manifests=(manifest.slug,),
                    suggestion=rule.suggestion or "Split into smaller modules",
                )

    return None
