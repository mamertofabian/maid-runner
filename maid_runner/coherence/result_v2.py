"""V2 coherence result types using frozen dataclasses.

Coexists with the v1 result module until Phase 7.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional


class IssueSeverity(str, Enum):
    ERROR = "error"
    WARNING = "warning"
    INFO = "info"


class IssueType(str, Enum):
    DUPLICATE = "duplicate"
    SIGNATURE_CONFLICT = "signature_conflict"
    BOUNDARY_VIOLATION = "boundary_violation"
    NAMING = "naming"
    DEPENDENCY = "dependency"
    PATTERN = "pattern"
    CONSTRAINT = "constraint"


@dataclass(frozen=True)
class CoherenceIssue:
    """A single coherence issue found during analysis."""

    issue_type: IssueType
    severity: IssueSeverity
    message: str
    file: Optional[str] = None
    artifact: Optional[str] = None
    manifests: tuple[str, ...] = ()
    suggestion: Optional[str] = None

    def to_dict(self) -> dict:
        d: dict = {
            "type": self.issue_type.value,
            "severity": self.severity.value,
            "message": self.message,
        }
        if self.file:
            d["file"] = self.file
        if self.artifact:
            d["artifact"] = self.artifact
        if self.manifests:
            d["manifests"] = list(self.manifests)
        if self.suggestion:
            d["suggestion"] = self.suggestion
        return d


@dataclass
class CoherenceResult:
    """Complete result of coherence validation."""

    issues: list[CoherenceIssue] = field(default_factory=list)
    checks_run: list[str] = field(default_factory=list)
    duration_ms: Optional[float] = None

    @property
    def error_count(self) -> int:
        return sum(1 for i in self.issues if i.severity == IssueSeverity.ERROR)

    @property
    def warning_count(self) -> int:
        return sum(1 for i in self.issues if i.severity == IssueSeverity.WARNING)

    @property
    def success(self) -> bool:
        return self.error_count == 0

    def to_dict(self) -> dict:
        return {
            "success": self.success,
            "errors": self.error_count,
            "warnings": self.warning_count,
            "checks_run": self.checks_run,
            "issues": [i.to_dict() for i in self.issues],
            "duration_ms": self.duration_ms,
        }

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), indent=2)
