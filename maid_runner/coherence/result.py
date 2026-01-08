"""
Result types for coherence validation.

This module provides data structures for representing coherence validation
results, including severity levels, issue types, and result containers.
These types are used by all coherence validation checks to report issues
with consistent structure.

Module Organization:
    - IssueSeverity: Enum for severity levels (ERROR, WARNING, INFO)
    - IssueType: Enum for types of coherence issues
    - CoherenceIssue: Dataclass representing a single coherence issue
    - CoherenceResult: Dataclass containing validation results and issue list

Usage:
    from maid_runner.coherence.result import (
        IssueSeverity,
        IssueType,
        CoherenceIssue,
        CoherenceResult,
    )

    issue = CoherenceIssue(
        issue_type=IssueType.DUPLICATE,
        severity=IssueSeverity.ERROR,
        message="Duplicate artifact found",
        suggestion="Remove one of the duplicates",
        location="manifests/task-001.manifest.json",
    )

    result = CoherenceResult(valid=False, issues=[issue])
"""

from dataclasses import dataclass
from enum import Enum
from typing import List, Optional


class IssueSeverity(Enum):
    """Severity levels for coherence issues.

    Defines the importance and urgency of detected coherence issues:
    - ERROR: Critical issues that must be fixed
    - WARNING: Issues that should be addressed but are not blocking
    - INFO: Informational notices and suggestions

    Example:
        severity = IssueSeverity.ERROR
        if severity == IssueSeverity.ERROR:
            print("Critical issue detected")
    """

    ERROR = "error"
    WARNING = "warning"
    INFO = "info"


class IssueType(Enum):
    """Types of coherence issues that can be detected.

    Categorizes different kinds of coherence problems:
    - DUPLICATE: Same artifact declared in multiple manifests
    - SIGNATURE_CONFLICT: Conflicting function/method signatures
    - BOUNDARY_VIOLATION: Cross-boundary access violations
    - NAMING: Naming convention violations
    - DEPENDENCY: Dependency-related issues
    - PATTERN: Pattern usage issues or suggestions
    - CONSTRAINT: Constraint violations

    Example:
        issue_type = IssueType.DUPLICATE
        if issue_type == IssueType.DUPLICATE:
            print("Duplicate artifact found")
    """

    DUPLICATE = "duplicate"
    SIGNATURE_CONFLICT = "signature_conflict"
    BOUNDARY_VIOLATION = "boundary_violation"
    NAMING = "naming"
    DEPENDENCY = "dependency"
    PATTERN = "pattern"
    CONSTRAINT = "constraint"


@dataclass
class CoherenceIssue:
    """Represents a single coherence issue detected during validation.

    Contains all information needed to understand and address a coherence
    issue, including its type, severity, description, and suggested fix.

    Attributes:
        issue_type: The category of coherence issue
        severity: How critical the issue is
        message: Human-readable description of the issue
        suggestion: Recommended action to resolve the issue
        location: Optional file path or location where the issue was found

    Example:
        issue = CoherenceIssue(
            issue_type=IssueType.NAMING,
            severity=IssueSeverity.WARNING,
            message="Function name does not follow snake_case convention",
            suggestion="Rename 'validateManifest' to 'validate_manifest'",
            location="src/validators.py:42",
        )
    """

    issue_type: IssueType
    severity: IssueSeverity
    message: str
    suggestion: str
    location: Optional[str] = None


@dataclass
class CoherenceResult:
    """Container for coherence validation results.

    Aggregates all issues found during coherence validation along with
    the overall validation status. Provides convenient properties for
    counting errors and warnings.

    Attributes:
        valid: Whether the validation passed (no errors)
        issues: List of all coherence issues found

    Properties:
        errors: Count of issues with ERROR severity
        warnings: Count of issues with WARNING severity

    Example:
        result = CoherenceResult(
            valid=False,
            issues=[error_issue, warning_issue],
        )
        print(f"Found {result.errors} errors and {result.warnings} warnings")
    """

    valid: bool
    issues: List[CoherenceIssue]

    @property
    def errors(self) -> int:
        """Return count of ERROR severity issues."""
        return sum(1 for issue in self.issues if issue.severity == IssueSeverity.ERROR)

    @property
    def warnings(self) -> int:
        """Return count of WARNING severity issues."""
        return sum(
            1 for issue in self.issues if issue.severity == IssueSeverity.WARNING
        )
