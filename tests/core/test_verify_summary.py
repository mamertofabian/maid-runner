from __future__ import annotations

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


def _validation(
    *,
    slug: str = "gate",
    success: bool = True,
    warnings: list[ValidationError] | None = None,
) -> ValidationResult:
    return ValidationResult(
        success=success,
        manifest_slug=slug,
        manifest_path=f"manifests/{slug}.manifest.yaml",
        mode=ValidationMode.BEHAVIORAL,
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


def test_build_summary_deduplicates_repeated_warnings() -> None:
    from maid_runner.core.verify_summary import (
        VerifySummary,
        VerifyWarningGroup,
        build_verify_summary,
    )

    repeated = _warning()
    result = VerificationResult(
        stages=(
            VerificationStageResult(
                name="behavioral",
                success=True,
                _validation=_batch(
                    [
                        _validation(slug="first", warnings=[repeated]),
                        _validation(slug="second", warnings=[repeated]),
                        _validation(slug="third", warnings=[repeated]),
                    ]
                ),
            ),
        )
    )

    summary: VerifySummary = build_verify_summary(result)

    assert isinstance(summary, VerifySummary)
    assert summary.raw_warning_count == 3
    assert summary.warning_groups == (
        VerifyWarningGroup(
            code="E210",
            location="tests/test_gate.py:3",
            message="Test has no assertions",
            count=3,
        ),
    )


def test_build_summary_keeps_distinct_locations_separate() -> None:
    from maid_runner.core.verify_summary import VerifySummary, build_verify_summary

    result = VerificationResult(
        stages=(
            VerificationStageResult(
                name="behavioral",
                success=True,
                _validation=_batch(
                    [
                        _validation(
                            slug="first",
                            warnings=[_warning(file="tests/test_first.py", line=4)],
                        ),
                        _validation(
                            slug="second",
                            warnings=[_warning(file="tests/test_second.py", line=9)],
                        ),
                    ]
                ),
            ),
        )
    )

    summary = build_verify_summary(result)

    assert isinstance(summary, VerifySummary)
    assert summary.raw_warning_count == 2
    assert [group.location for group in summary.warning_groups] == [
        "tests/test_first.py:4",
        "tests/test_second.py:9",
    ]
    assert [group.count for group in summary.warning_groups] == [1, 1]


def test_build_summary_partitions_blocking_and_passed_stages() -> None:
    from maid_runner.core.verify_summary import VerifySummary, build_verify_summary

    result = VerificationResult(
        stages=(
            VerificationStageResult(name="schema", success=True),
            VerificationStageResult(name="behavioral", success=False),
            VerificationStageResult(name="tests", success=True),
        )
    )

    summary = build_verify_summary(result)

    assert isinstance(summary, VerifySummary)
    assert summary.success is False
    assert summary.blocking_stages == ("behavioral",)
    assert summary.passed_stages == ("schema", "tests")


def test_build_summary_keeps_warning_groups_from_failed_validation_stage() -> None:
    from maid_runner.core.verify_summary import VerifySummary, build_verify_summary

    result = VerificationResult(
        stages=(
            VerificationStageResult(
                name="behavioral",
                success=False,
                _validation=_batch(
                    [_validation(slug="advisory", warnings=[_warning()])]
                ),
            ),
        )
    )

    summary = build_verify_summary(result)

    assert isinstance(summary, VerifySummary)
    assert summary.success is False
    assert summary.blocking_stages == ("behavioral",)
    assert summary.raw_warning_count == 1
    assert [
        (group.code, group.location, group.count) for group in summary.warning_groups
    ] == [("E210", "tests/test_gate.py:3", 1)]


def test_build_summary_reports_no_warnings_for_clean_result() -> None:
    from maid_runner.core.verify_summary import VerifySummary, build_verify_summary

    result = VerificationResult(
        stages=(
            VerificationStageResult(name="schema", success=True),
            VerificationStageResult(
                name="behavioral",
                success=True,
                _validation=_batch([_validation()]),
            ),
        )
    )

    summary = build_verify_summary(result)

    assert isinstance(summary, VerifySummary)
    assert summary.success is True
    assert summary.raw_warning_count == 0
    assert summary.warning_groups == ()
