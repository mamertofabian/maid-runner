from __future__ import annotations

import json

from maid_runner.cli.commands._format import format_verify_summary
from maid_runner.core.result import (
    BatchValidationResult,
    ErrorCode,
    Location,
    Severity,
    ValidationError,
    ValidationResult,
    VerificationResult,
    VerificationStageResult,
)
from maid_runner.core.types import ValidationMode
from maid_runner.core.verify_summary import build_verify_summary


def _warning(
    *,
    code: ErrorCode = ErrorCode.MISSING_ASSERTIONS,
    message: str = "Test has no assertions",
    file: str = "tests/test_gate.py",
    line: int = 3,
) -> ValidationError:
    return ValidationError(
        code=code,
        message=message,
        severity=Severity.WARNING,
        location=Location(file=file, line=line),
    )


def _error(
    *,
    code: ErrorCode = ErrorCode.FILE_NOT_FOUND,
    message: str = "File not found",
    file: str = "missing.py",
    line: int = 1,
) -> ValidationError:
    return ValidationError(
        code=code,
        message=message,
        severity=Severity.ERROR,
        location=Location(file=file, line=line),
    )


def _validation(
    slug: str,
    *,
    success: bool,
    warnings: list[ValidationError] | None = None,
    errors: list[ValidationError] | None = None,
) -> ValidationResult:
    return ValidationResult(
        success=success,
        manifest_slug=slug,
        manifest_path=f"manifests/{slug}.manifest.yaml",
        mode=ValidationMode.BEHAVIORAL,
        errors=list(errors or []),
        warnings=list(warnings or []),
    )


def _batch(
    validations: list[ValidationResult],
    *,
    chain_errors: list[ValidationError] | None = None,
) -> BatchValidationResult:
    failed = sum(1 for validation in validations if not validation.success)
    return BatchValidationResult(
        results=validations,
        total_manifests=len(validations),
        passed=len(validations) - failed,
        failed=failed,
        skipped=0,
        chain_errors=list(chain_errors or []),
    )


def _warning_driven_result() -> VerificationResult:
    repeated = _warning()
    return VerificationResult(
        stages=(
            VerificationStageResult(name="schema", success=True),
            VerificationStageResult(
                name="behavioral",
                success=False,
                _validation=_batch(
                    [
                        _validation(
                            "warning-only-1",
                            success=False,
                            warnings=[repeated],
                        ),
                        _validation(
                            "warning-only-2",
                            success=False,
                            warnings=[repeated],
                        ),
                    ]
                ),
            ),
            VerificationStageResult(name="implementation", success=True),
        )
    )


def test_warning_driven_failure_label_states_blocking_policy() -> None:
    result = _warning_driven_result()

    summary = build_verify_summary(result)
    output = format_verify_summary(result)

    assert summary.warning_blocking_stages == ("behavioral",)
    warning_header = next(
        line for line in output.splitlines() if line.startswith("WARNINGS")
    )
    assert "non-blocking" not in warning_header
    assert "deduplicated 2 -> 1" in warning_header
    assert "blocking for: behavioral" in warning_header
    assert "under verify policy" in warning_header


def test_error_driven_failure_keeps_non_blocking_label() -> None:
    warning = _warning()
    result = VerificationResult(
        stages=(
            VerificationStageResult(
                name="behavioral",
                success=False,
                _validation=_batch(
                    [
                        _validation(
                            "error-and-warning",
                            success=False,
                            errors=[_error()],
                            warnings=[warning],
                        )
                    ]
                ),
            ),
        )
    )

    summary = build_verify_summary(result)
    output = format_verify_summary(result)

    assert summary.warning_blocking_stages == ()
    assert "WARNINGS (non-blocking, deduplicated 1 -> 1):" in output


def test_warning_blocking_label_mentions_advisory_escape_hatch() -> None:
    output = format_verify_summary(_warning_driven_result())

    assert "--advisory" in output
    assert "brownfield" in output
    assert "warnings" in output


def test_build_summary_partitions_warning_blocking_stages() -> None:
    warning = _warning()
    result = VerificationResult(
        stages=(
            VerificationStageResult(name="schema", success=True),
            VerificationStageResult(
                name="behavioral",
                success=False,
                _validation=_batch(
                    [
                        _validation(
                            "warning-only",
                            success=False,
                            warnings=[warning],
                        )
                    ]
                ),
            ),
            VerificationStageResult(
                name="implementation",
                success=False,
                _validation=_batch(
                    [
                        _validation(
                            "error-driven",
                            success=False,
                            errors=[_error()],
                            warnings=[warning],
                        )
                    ]
                ),
            ),
            VerificationStageResult(
                name="file_tracking",
                success=False,
                _errors=(_error(message="Undeclared file"),),
            ),
            VerificationStageResult(name="tests", success=True),
        )
    )

    summary = build_verify_summary(result)

    assert summary.warning_blocking_stages == ("behavioral",)
    assert summary.blocking_stages == (
        "behavioral",
        "implementation",
        "file_tracking",
    )
    assert summary.passed_stages == ("schema", "tests")


def test_summary_json_reports_warning_blocking_stages() -> None:
    payload = json.loads(
        format_verify_summary(_warning_driven_result(), json_mode=True)
    )

    assert payload["warning_blocking_stages"] == ["behavioral"]
    assert payload["findings"]["warnings"] == [
        {
            "code": "E210",
            "message": "Test has no assertions",
            "location": "tests/test_gate.py:3",
            "count": 2,
        }
    ]
