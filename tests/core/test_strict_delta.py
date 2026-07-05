from __future__ import annotations

from pathlib import Path

from maid_runner.core.artifact_coverage import ArtifactCoverageReport
from maid_runner.core.result import (
    BatchValidationResult,
    ErrorCode,
    Location,
    Severity,
    ValidationError,
    ValidationResult,
)
from maid_runner.core.types import ValidationMode


def test_compute_strict_delta_excludes_shared_diagnostics_and_sorts_entries() -> None:
    from maid_runner.core.strict_delta import (
        StrictDeltaEntry,
        StrictDeltaReport,
        compute_strict_delta,
    )

    shared = _error(
        ErrorCode.ARTIFACT_NOT_DEFINED,
        "Declared artifact is missing",
        "src/shared.py",
    )
    strict_file = _error(
        ErrorCode.MISSING_ASSERTIONS,
        "test_without_assertions has no assertions",
        "tests/test_alpha.py",
    )
    strict_manifest = _error(
        ErrorCode.STUB_FUNCTION_DETECTED,
        "Declared artifact uses a stub body",
        None,
    )
    strict_info = _error(
        ErrorCode.VALIDATOR_NOT_AVAILABLE,
        "Optional validator unavailable",
        "src/info.py",
        severity=Severity.INFO,
    )
    strict_coverage = _error(
        ErrorCode.ARTIFACT_NOT_EXECUTED_BY_TESTS,
        "No body line of declared artifact 'target' was executed by tests",
        "src/coverage.py",
    )

    default_result = _batch(
        _validation("manifests/beta.manifest.yaml", errors=(shared,))
    )
    strict_result = _batch(
        _validation(
            "manifests/beta.manifest.yaml",
            errors=(shared, strict_info, strict_file, strict_manifest),
        )
    )

    report = compute_strict_delta(
        default_result,
        strict_result,
        strict_coverage={
            "manifests/alpha.manifest.yaml": ArtifactCoverageReport(
                findings=(),
                errors=(strict_coverage,),
            )
        },
    )

    assert isinstance(report, StrictDeltaReport)
    assert report.entries == (
        StrictDeltaEntry(
            manifest_path="manifests/alpha.manifest.yaml",
            file="src/coverage.py",
            code="E710",
            severity="error",
            message="No body line of declared artifact 'target' was executed by tests",
        ),
        StrictDeltaEntry(
            manifest_path="manifests/beta.manifest.yaml",
            file=None,
            code="E310",
            severity="error",
            message="Declared artifact uses a stub body",
        ),
        StrictDeltaEntry(
            manifest_path="manifests/beta.manifest.yaml",
            file="tests/test_alpha.py",
            code="E210",
            severity="error",
            message="test_without_assertions has no assertions",
        ),
    )
    assert report.to_dict() == {
        "entries": [
            {
                "manifest_path": "manifests/alpha.manifest.yaml",
                "file": "src/coverage.py",
                "code": "E710",
                "severity": "error",
                "message": (
                    "No body line of declared artifact 'target' was executed by tests"
                ),
            },
            {
                "manifest_path": "manifests/beta.manifest.yaml",
                "file": None,
                "code": "E310",
                "severity": "error",
                "message": "Declared artifact uses a stub body",
            },
            {
                "manifest_path": "manifests/beta.manifest.yaml",
                "file": "tests/test_alpha.py",
                "code": "E210",
                "severity": "error",
                "message": "test_without_assertions has no assertions",
            },
        ]
    }


def test_compute_strict_delta_uses_code_manifest_and_location_identity() -> None:
    from maid_runner.core.strict_delta import compute_strict_delta

    default_error = _error(
        ErrorCode.MISSING_ASSERTIONS,
        "old message",
        "tests/test_target.py",
    )
    strict_error_same_identity = _error(
        ErrorCode.MISSING_ASSERTIONS,
        "new message",
        "tests/test_target.py",
    )
    strict_error_different_file = _error(
        ErrorCode.MISSING_ASSERTIONS,
        "new file",
        "tests/test_other.py",
    )

    report = compute_strict_delta(
        _batch(_validation("manifests/task.manifest.yaml", errors=(default_error,))),
        _batch(
            _validation(
                "manifests/task.manifest.yaml",
                errors=(strict_error_same_identity, strict_error_different_file),
            )
        ),
    )

    assert [entry.file for entry in report.entries] == ["tests/test_other.py"]
    assert report.entries[0].message == "new file"


def test_compute_strict_delta_returns_explicit_empty_report_for_clean_delta() -> None:
    from maid_runner.core.strict_delta import compute_strict_delta

    report = compute_strict_delta(
        _batch(_validation("manifests/clean.manifest.yaml")),
        _batch(_validation("manifests/clean.manifest.yaml")),
    )

    assert report.entries == ()
    assert report.to_dict() == {"entries": []}


def _validation(
    manifest_path: str,
    *,
    errors: tuple[ValidationError, ...] = (),
    warnings: tuple[ValidationError, ...] = (),
) -> ValidationResult:
    return ValidationResult(
        success=not errors,
        manifest_slug=Path(manifest_path).stem.replace(".manifest", ""),
        manifest_path=manifest_path,
        mode=ValidationMode.IMPLEMENTATION,
        errors=list(errors),
        warnings=list(warnings),
    )


def _batch(*results: ValidationResult) -> BatchValidationResult:
    failed = sum(1 for result in results if not result.success)
    return BatchValidationResult(
        results=list(results),
        total_manifests=len(results),
        passed=len(results) - failed,
        failed=failed,
        skipped=0,
    )


def _error(
    code: ErrorCode,
    message: str,
    file_path: str | None,
    *,
    severity: Severity = Severity.ERROR,
) -> ValidationError:
    return ValidationError(
        code=code,
        message=message,
        severity=severity,
        location=Location(file=file_path) if file_path is not None else None,
    )
