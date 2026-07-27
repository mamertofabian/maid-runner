"""Summary accounting for findings nested inside stage report objects.

`_artifact_coverage_stage` and `_knockout_stage` store a single report object in
`VerificationStageResult._errors`; the ValidationErrors live in that report's own
`errors` tuple. These tests pin that such nested findings are counted and
labelled exactly like direct ones, without changing any stage's pass/fail rule.
"""

from __future__ import annotations

from maid_runner.core.artifact_coverage import ArtifactCoverageReport
from maid_runner.core.knockout import KnockoutReport
from maid_runner.core.result import (
    ErrorCode,
    Location,
    Severity,
    ValidationError,
    VerificationResult,
    VerificationStageResult,
)


def _finding(
    *,
    code: ErrorCode = ErrorCode.VALIDATOR_NOT_AVAILABLE,
    message: str = "coverage.py missing",
    severity: Severity = Severity.WARNING,
    file: str = "maid_runner/core/artifact_coverage.py",
    line: int = 61,
) -> ValidationError:
    return ValidationError(
        code=code,
        message=message,
        severity=severity,
        location=Location(file=file, line=line),
    )


def _coverage_stage(
    *errors: ValidationError,
    name: str = "artifact_coverage",
    direct: tuple[object, ...] = (),
) -> VerificationStageResult:
    report = ArtifactCoverageReport(findings=(), errors=tuple(errors))
    return VerificationStageResult(
        name=name,
        success=report.success,
        _duration_ms=1.0,
        _errors=(*direct, report),
    )


def _result(stage: VerificationStageResult) -> VerificationResult:
    return VerificationResult(stages=(stage,))


def test_nested_report_warning_is_counted_in_summary_warning_groups() -> None:
    from maid_runner.core.verify_summary import build_verify_summary

    stage = _coverage_stage(_finding())

    summary = build_verify_summary(_result(stage))

    assert summary.raw_warning_count == 1
    assert len(summary.warning_groups) == 1
    assert summary.warning_groups[0].code == "E307"
    assert summary.warning_groups[0].message == "coverage.py missing"


def test_nested_report_info_is_counted_in_summary_info_groups() -> None:
    from maid_runner.core.verify_summary import build_verify_summary

    stage = _coverage_stage(_finding(severity=Severity.INFO))

    summary = build_verify_summary(_result(stage))

    assert summary.raw_info_count == 1
    assert len(summary.info_groups) == 1
    assert summary.info_groups[0].code == "E307"


def test_stage_failing_only_on_nested_warning_is_labeled_warning_driven() -> None:
    from maid_runner.core.verify_summary import build_verify_summary

    stage = _coverage_stage(_finding(), _finding(message="second gate unavailable"))

    summary = build_verify_summary(_result(stage))

    assert summary.warning_blocking_stages == ("artifact_coverage",)


def test_nested_error_keeps_stage_out_of_warning_blocking_stages() -> None:
    from maid_runner.core.verify_summary import build_verify_summary

    stage = _coverage_stage(
        _finding(severity=Severity.ERROR, message="artifact missing"),
        _finding(),
    )

    summary = build_verify_summary(_result(stage))

    assert summary.blocking_stages == ("artifact_coverage",)
    assert summary.warning_blocking_stages == ()


def test_warning_only_report_still_fails_its_stage() -> None:
    from maid_runner.core.verify_summary import build_verify_summary

    stage = _coverage_stage(_finding())

    summary = build_verify_summary(_result(stage))

    assert summary.blocking_stages == ("artifact_coverage",)
    assert summary.success is False


def test_direct_and_nested_findings_are_each_counted_once() -> None:
    from maid_runner.core.verify_summary import build_verify_summary

    stage = _coverage_stage(
        _finding(message="nested coverage warning"),
        direct=(_finding(message="direct stage warning"),),
    )

    summary = build_verify_summary(_result(stage))

    assert summary.raw_warning_count == 2
    assert {group.message for group in summary.warning_groups} == {
        "direct stage warning",
        "nested coverage warning",
    }


def test_knockout_report_nested_findings_are_collected() -> None:
    from maid_runner.core.verify_summary import build_verify_summary

    report = KnockoutReport(results=(), errors=(_finding(message="knockout skipped"),))
    stage = VerificationStageResult(
        name="knockout",
        success=report.success,
        _duration_ms=1.0,
        _errors=(report,),
    )

    summary = build_verify_summary(_result(stage))

    assert summary.raw_warning_count == 1
    assert summary.warning_groups[0].message == "knockout skipped"
    assert summary.warning_blocking_stages == ("knockout",)


def test_plain_string_stage_errors_are_still_ignored() -> None:
    from maid_runner.core.verify_summary import build_verify_summary

    stage = VerificationStageResult(
        name="tests",
        success=False,
        _duration_ms=1.0,
        _errors=("Stage raised RuntimeError: boom",),
    )

    summary = build_verify_summary(_result(stage))

    assert summary.warning_groups == ()
    assert summary.info_groups == ()
    assert summary.raw_warning_count == 0
    assert summary.warning_blocking_stages == ()
