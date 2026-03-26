"""Tests for maid_runner.core.result - all result types."""

import json

import pytest

from maid_runner.core.result import (
    BatchTestResult,
    BatchValidationResult,
    ErrorCode,
    FileTrackingEntry,
    FileTrackingReport,
    FileTrackingStatus,
    Location,
    Severity,
    TestRunResult,
    ValidationError,
    ValidationResult,
)
from maid_runner.core.types import ValidationMode


class TestErrorCode:
    def test_file_errors(self):
        assert ErrorCode.FILE_NOT_FOUND == "E001"
        assert ErrorCode.FILE_READ_ERROR == "E002"
        assert ErrorCode.MANIFEST_PARSE_ERROR == "E003"
        assert ErrorCode.SCHEMA_VALIDATION_ERROR == "E004"

    def test_semantic_errors(self):
        assert ErrorCode.DUPLICATE_FILE == "E100"
        assert ErrorCode.CIRCULAR_SUPERSESSION == "E103"

    def test_behavioral_errors(self):
        assert ErrorCode.ARTIFACT_NOT_USED_IN_TESTS == "E200"

    def test_implementation_errors(self):
        assert ErrorCode.ARTIFACT_NOT_DEFINED == "E300"
        assert ErrorCode.UNEXPECTED_ARTIFACT == "E301"
        assert ErrorCode.TYPE_MISMATCH == "E302"
        assert ErrorCode.FILE_SHOULD_BE_ABSENT == "E305"

    def test_is_string_enum(self):
        assert isinstance(ErrorCode.FILE_NOT_FOUND, str)
        assert ErrorCode("E001") == ErrorCode.FILE_NOT_FOUND


class TestSeverity:
    def test_values(self):
        assert Severity.ERROR == "error"
        assert Severity.WARNING == "warning"
        assert Severity.INFO == "info"


class TestLocation:
    def test_basic(self):
        loc = Location(file="src/app.py", line=42)
        assert loc.file == "src/app.py"
        assert loc.line == 42
        assert loc.column is None

    def test_full(self):
        loc = Location(file="src/app.py", line=10, column=5, end_line=12, end_column=1)
        assert loc.end_line == 12
        assert loc.end_column == 1

    def test_frozen(self):
        loc = Location(file="src/app.py")
        with pytest.raises(AttributeError):
            loc.file = "other.py"  # type: ignore[misc]


class TestValidationError:
    def test_basic(self):
        err = ValidationError(
            code=ErrorCode.ARTIFACT_NOT_DEFINED,
            message="Artifact 'greet' not defined in src/greet.py",
        )
        assert err.code == ErrorCode.ARTIFACT_NOT_DEFINED
        assert err.severity == Severity.ERROR
        assert err.location is None
        assert err.suggestion is None

    def test_with_location(self):
        err = ValidationError(
            code=ErrorCode.TYPE_MISMATCH,
            message="Type mismatch",
            location=Location(file="src/calc.py", line=5),
        )
        assert err.location is not None
        assert err.location.file == "src/calc.py"

    def test_to_dict_minimal(self):
        err = ValidationError(
            code=ErrorCode.ARTIFACT_NOT_DEFINED,
            message="Missing artifact",
        )
        d = err.to_dict()
        assert d["code"] == "E300"
        assert d["message"] == "Missing artifact"
        assert d["severity"] == "error"
        assert "location" not in d
        assert "suggestion" not in d

    def test_to_dict_with_location(self):
        err = ValidationError(
            code=ErrorCode.TYPE_MISMATCH,
            message="Type mismatch",
            location=Location(file="src/calc.py", line=5, column=10),
        )
        d = err.to_dict()
        assert d["location"]["file"] == "src/calc.py"
        assert d["location"]["line"] == 5
        assert d["location"]["column"] == 10

    def test_to_dict_with_suggestion(self):
        err = ValidationError(
            code=ErrorCode.ARTIFACT_NOT_DEFINED,
            message="Missing",
            suggestion="Add the function to the file",
        )
        d = err.to_dict()
        assert d["suggestion"] == "Add the function to the file"

    def test_frozen(self):
        err = ValidationError(code=ErrorCode.INTERNAL_ERROR, message="bad")
        with pytest.raises(AttributeError):
            err.message = "worse"  # type: ignore[misc]


class TestFileTrackingStatus:
    def test_values(self):
        assert FileTrackingStatus.UNDECLARED == "undeclared"
        assert FileTrackingStatus.REGISTERED == "registered"
        assert FileTrackingStatus.TRACKED == "tracked"


class TestFileTrackingEntry:
    def test_basic(self):
        entry = FileTrackingEntry(
            path="src/app.py",
            status=FileTrackingStatus.TRACKED,
            manifests=("add-auth",),
        )
        assert entry.path == "src/app.py"
        assert entry.manifests == ("add-auth",)
        assert entry.issues == ()

    def test_with_issues(self):
        entry = FileTrackingEntry(
            path="src/old.py",
            status=FileTrackingStatus.REGISTERED,
            issues=("No artifacts declared",),
        )
        assert len(entry.issues) == 1


class TestFileTrackingReport:
    @pytest.fixture()
    def report(self):
        return FileTrackingReport(
            entries=(
                FileTrackingEntry(
                    path="src/a.py",
                    status=FileTrackingStatus.TRACKED,
                    manifests=("add-a",),
                ),
                FileTrackingEntry(
                    path="src/b.py",
                    status=FileTrackingStatus.REGISTERED,
                    manifests=("snapshot-b",),
                    issues=("No artifacts",),
                ),
                FileTrackingEntry(
                    path="src/c.py",
                    status=FileTrackingStatus.UNDECLARED,
                ),
            )
        )

    def test_undeclared(self, report):
        assert len(report.undeclared) == 1
        assert report.undeclared[0].path == "src/c.py"

    def test_registered(self, report):
        assert len(report.registered) == 1
        assert report.registered[0].path == "src/b.py"

    def test_tracked(self, report):
        assert len(report.tracked) == 1
        assert report.tracked[0].path == "src/a.py"


class TestValidationResult:
    def test_success(self):
        result = ValidationResult(
            success=True,
            manifest_slug="add-greet",
            manifest_path="/manifests/add-greet.manifest.yaml",
            mode=ValidationMode.IMPLEMENTATION,
        )
        assert result.success is True
        assert result.errors == []
        assert result.warnings == []

    def test_failure(self):
        result = ValidationResult(
            success=False,
            manifest_slug="add-greet",
            manifest_path="/test.yaml",
            mode=ValidationMode.IMPLEMENTATION,
            errors=[
                ValidationError(
                    code=ErrorCode.ARTIFACT_NOT_DEFINED,
                    message="Missing greet",
                )
            ],
        )
        assert result.success is False
        assert len(result.errors) == 1

    def test_to_dict(self):
        result = ValidationResult(
            success=True,
            manifest_slug="add-greet",
            manifest_path="/test.yaml",
            mode=ValidationMode.BEHAVIORAL,
            duration_ms=42.5,
        )
        d = result.to_dict()
        assert d["success"] is True
        assert d["manifest"] == "add-greet"
        assert d["mode"] == "behavioral"
        assert d["errors"] == []
        assert d["warnings"] == []
        assert d["duration_ms"] == 42.5

    def test_to_dict_with_file_tracking(self):
        report = FileTrackingReport(
            entries=(
                FileTrackingEntry(
                    path="src/a.py",
                    status=FileTrackingStatus.TRACKED,
                ),
                FileTrackingEntry(
                    path="src/b.py",
                    status=FileTrackingStatus.UNDECLARED,
                ),
            )
        )
        result = ValidationResult(
            success=True,
            manifest_slug="test",
            manifest_path="/test.yaml",
            mode=ValidationMode.IMPLEMENTATION,
            file_tracking=report,
        )
        d = result.to_dict()
        assert d["file_tracking"]["tracked"] == ["src/a.py"]
        assert d["file_tracking"]["undeclared"] == ["src/b.py"]

    def test_to_json(self):
        result = ValidationResult(
            success=True,
            manifest_slug="test",
            manifest_path="/test.yaml",
            mode=ValidationMode.IMPLEMENTATION,
        )
        j = result.to_json()
        parsed = json.loads(j)
        assert parsed["success"] is True

    def test_to_dict_no_duration(self):
        result = ValidationResult(
            success=True,
            manifest_slug="test",
            manifest_path="/test.yaml",
            mode=ValidationMode.IMPLEMENTATION,
        )
        d = result.to_dict()
        assert "duration_ms" not in d


class TestBatchValidationResult:
    def test_success_property(self):
        batch = BatchValidationResult(
            results=[],
            total_manifests=2,
            passed=2,
            failed=0,
            skipped=0,
        )
        assert batch.success is True

    def test_failure_property(self):
        batch = BatchValidationResult(
            results=[],
            total_manifests=2,
            passed=1,
            failed=1,
            skipped=0,
        )
        assert batch.success is False

    def test_to_dict(self):
        batch = BatchValidationResult(
            results=[],
            total_manifests=3,
            passed=2,
            failed=0,
            skipped=1,
            duration_ms=100.0,
        )
        d = batch.to_dict()
        assert d["success"] is True
        assert d["total"] == 3
        assert d["passed"] == 2
        assert d["skipped"] == 1
        assert d["duration_ms"] == 100.0


class TestTestRunResult:
    def test_success(self):
        r = TestRunResult(
            manifest_slug="add-greet",
            command=("pytest", "tests/test_greet.py", "-v"),
            exit_code=0,
            stdout="1 passed",
            stderr="",
            duration_ms=500.0,
        )
        assert r.success is True

    def test_failure(self):
        r = TestRunResult(
            manifest_slug="add-greet",
            command=("pytest", "tests/test_greet.py"),
            exit_code=1,
            stdout="",
            stderr="FAILED",
            duration_ms=200.0,
        )
        assert r.success is False


class TestBatchTestResult:
    def test_success(self):
        batch = BatchTestResult(results=[], total=2, passed=2, failed=0)
        assert batch.success is True

    def test_failure(self):
        batch = BatchTestResult(results=[], total=2, passed=1, failed=1)
        assert batch.success is False
