"""Result types for MAID Runner v2 validation."""

from __future__ import annotations

import json as _json
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional

from maid_runner.core.types import TestStream, ValidationMode


class ErrorCode(str, Enum):
    FILE_NOT_FOUND = "E001"
    FILE_READ_ERROR = "E002"
    MANIFEST_PARSE_ERROR = "E003"
    SCHEMA_VALIDATION_ERROR = "E004"

    DUPLICATE_FILE = "E100"
    FILE_IN_MULTIPLE_SECTIONS = "E101"
    SUPERSEDED_MANIFEST_NOT_FOUND = "E102"
    CIRCULAR_SUPERSESSION = "E103"
    EMPTY_ARTIFACTS = "E104"
    INVALID_TASK_TYPE = "E105"

    ARTIFACT_NOT_USED_IN_TESTS = "E200"
    TEST_FILE_NOT_FOUND = "E201"
    TEST_FILE_NOT_IN_READONLY = "E202"
    MISSING_ASSERTIONS = "E210"
    NO_TEST_FILES = "E220"

    ARTIFACT_NOT_DEFINED = "E300"
    UNEXPECTED_ARTIFACT = "E301"
    TYPE_MISMATCH = "E302"
    SIGNATURE_MISMATCH = "E303"
    MISSING_RETURN_TYPE = "E304"
    FILE_SHOULD_BE_ABSENT = "E305"
    FILE_SHOULD_BE_PRESENT = "E306"
    VALIDATOR_NOT_AVAILABLE = "E307"
    SOURCE_PARSE_ERROR = "E308"
    STUB_FUNCTION_DETECTED = "E310"
    MISSING_REQUIRED_IMPORT = "E320"

    TEST_FUNCTION_MISSING_IN_CODE = "E600"
    TEST_FUNCTION_BEHAVIOR_MISMATCH = "E610"

    ACCEPTANCE_TEST_FILE_NOT_FOUND = "E500"

    COHERENCE_DUPLICATE = "E400"
    COHERENCE_SIGNATURE_CONFLICT = "E401"
    COHERENCE_BOUNDARY_VIOLATION = "E402"
    COHERENCE_NAMING_VIOLATION = "E403"
    COHERENCE_DEPENDENCY_MISSING = "E404"

    INTERNAL_ERROR = "E900"
    UNSUPPORTED_LANGUAGE = "E901"


class Severity(str, Enum):
    ERROR = "error"
    WARNING = "warning"
    INFO = "info"


@dataclass(frozen=True)
class Location:
    file: str
    line: Optional[int] = None
    column: Optional[int] = None
    end_line: Optional[int] = None
    end_column: Optional[int] = None


@dataclass(frozen=True)
class ValidationError:
    code: ErrorCode
    message: str
    severity: Severity = Severity.ERROR
    location: Optional[Location] = None
    suggestion: Optional[str] = None

    def to_dict(self) -> dict:
        d: dict = {
            "code": self.code.value,
            "message": self.message,
            "severity": self.severity.value,
        }
        if self.location:
            d["location"] = {
                "file": self.location.file,
                "line": self.location.line,
                "column": self.location.column,
            }
        if self.suggestion:
            d["suggestion"] = self.suggestion
        return d


class FileTrackingStatus(str, Enum):
    UNDECLARED = "undeclared"
    REGISTERED = "registered"
    TRACKED = "tracked"


@dataclass(frozen=True)
class FileTrackingEntry:
    path: str
    status: FileTrackingStatus
    manifests: tuple[str, ...] = ()
    issues: tuple[str, ...] = ()


@dataclass(frozen=True)
class FileTrackingReport:
    entries: tuple[FileTrackingEntry, ...]

    @property
    def undeclared(self) -> list[FileTrackingEntry]:
        return [e for e in self.entries if e.status == FileTrackingStatus.UNDECLARED]

    @property
    def registered(self) -> list[FileTrackingEntry]:
        return [e for e in self.entries if e.status == FileTrackingStatus.REGISTERED]

    @property
    def tracked(self) -> list[FileTrackingEntry]:
        return [e for e in self.entries if e.status == FileTrackingStatus.TRACKED]


@dataclass
class ValidationResult:
    success: bool
    manifest_slug: str
    manifest_path: str
    mode: ValidationMode
    errors: list[ValidationError] = field(default_factory=list)
    warnings: list[ValidationError] = field(default_factory=list)
    file_tracking: Optional[FileTrackingReport] = None
    duration_ms: Optional[float] = None

    def to_dict(self) -> dict:
        d: dict = {
            "success": self.success,
            "manifest": self.manifest_slug,
            "manifest_path": self.manifest_path,
            "mode": self.mode.value,
            "errors": [e.to_dict() for e in self.errors],
            "warnings": [w.to_dict() for w in self.warnings],
        }
        if self.file_tracking:
            d["file_tracking"] = {
                "undeclared": [e.path for e in self.file_tracking.undeclared],
                "registered": [e.path for e in self.file_tracking.registered],
                "tracked": [e.path for e in self.file_tracking.tracked],
            }
        if self.duration_ms is not None:
            d["duration_ms"] = self.duration_ms
        return d

    def to_json(self) -> str:
        return _json.dumps(self.to_dict(), indent=2)


@dataclass
class BatchValidationResult:
    results: list[ValidationResult]
    total_manifests: int
    passed: int
    failed: int
    skipped: int
    chain_errors: list[ValidationError] = field(default_factory=list)
    duration_ms: Optional[float] = None

    @property
    def success(self) -> bool:
        return self.failed == 0 and not any(
            e.severity == Severity.ERROR for e in self.chain_errors
        )

    def to_dict(self) -> dict:
        return {
            "success": self.success,
            "total": self.total_manifests,
            "passed": self.passed,
            "failed": self.failed,
            "skipped": self.skipped,
            "chain_errors": [e.to_dict() for e in self.chain_errors],
            "results": [r.to_dict() for r in self.results],
            "duration_ms": self.duration_ms,
        }


@dataclass
class TestRunResult:
    manifest_slug: str
    command: tuple[str, ...]
    exit_code: int
    stdout: str
    stderr: str
    duration_ms: float
    stream: TestStream = TestStream.IMPLEMENTATION

    @property
    def success(self) -> bool:
        return self.exit_code == 0


@dataclass
class BatchTestResult:
    results: list[TestRunResult]
    total: int
    passed: int
    failed: int
    chain_errors: list[ValidationError] = field(default_factory=list)
    duration_ms: Optional[float] = None

    @property
    def success(self) -> bool:
        return self.failed == 0 and not any(
            e.severity == Severity.ERROR for e in self.chain_errors
        )

    @property
    def acceptance_results(self) -> list[TestRunResult]:
        return [r for r in self.results if r.stream == TestStream.ACCEPTANCE]

    @property
    def implementation_results(self) -> list[TestRunResult]:
        return [r for r in self.results if r.stream == TestStream.IMPLEMENTATION]
