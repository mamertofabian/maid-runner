from __future__ import annotations

import json
from pathlib import Path

import jsonschema

from maid_runner.core.diagnostics_registry import get_rule
from maid_runner.core.artifact_coverage import ArtifactCoverageReport
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
from maid_runner.core.sarif import (
    build_sarif_report,
    sarif_level_for_severity,
    write_sarif_report,
)
from maid_runner.core.types import ValidationMode


SARIF_SCHEMA_PATH = Path("tests/fixtures/sarif/sarif-schema-2.1.0.json")


def _validate_schema(report: dict) -> None:
    schema = json.loads(SARIF_SCHEMA_PATH.read_text())
    jsonschema.validate(report, schema)


def _validation_error(
    *,
    code: ErrorCode = ErrorCode.ARTIFACT_NOT_DEFINED,
    message: str = "Artifact is missing",
    severity: Severity = Severity.ERROR,
    file: str | None = "src/demo.py",
    line: int | None = 5,
    suggestion: str | None = "Implement the declared artifact.",
) -> ValidationError:
    location = None if file is None else Location(file=file, line=line)
    return ValidationError(
        code=code,
        message=message,
        severity=severity,
        location=location,
        suggestion=suggestion,
    )


def _validation_result(
    errors: list[ValidationError] | None = None,
    warnings: list[ValidationError] | None = None,
) -> ValidationResult:
    return ValidationResult(
        success=not errors,
        manifest_slug="demo",
        manifest_path="manifests/demo.manifest.yaml",
        mode=ValidationMode.IMPLEMENTATION,
        errors=errors or [],
        warnings=warnings or [],
    )


def test_sarif_level_for_severity_maps_internal_severities() -> None:
    assert sarif_level_for_severity(Severity.ERROR) == "error"
    assert sarif_level_for_severity(Severity.WARNING) == "warning"
    assert sarif_level_for_severity(Severity.INFO) == "note"


def test_build_sarif_report_emits_schema_valid_rules_and_results() -> None:
    diagnostic = _validation_error()
    report = build_sarif_report(_validation_result(errors=[diagnostic]))

    _validate_schema(report)

    run = report["runs"][0]
    rule = next(
        rule
        for rule in run["tool"]["driver"]["rules"]
        if rule["id"] == diagnostic.code.value
    )
    registry_rule = get_rule(diagnostic.code)
    result = run["results"][0]

    assert report["version"] == "2.1.0"
    assert run["tool"]["driver"]["name"] == "maid-runner"
    assert rule["shortDescription"]["text"] == registry_rule.short_description
    assert rule["fullDescription"]["text"] == registry_rule.description
    assert rule["helpUri"] == registry_rule.help_uri
    assert result["ruleId"] == diagnostic.code.value
    assert result["level"] == "error"
    assert result["message"]["text"] == (
        "Artifact is missing\n\nSuggestion: Implement the declared artifact."
    )
    assert result["locations"][0]["physicalLocation"] == {
        "artifactLocation": {"uri": "src/demo.py"},
        "region": {"startLine": 5},
    }
    assert "invocations" not in run


def test_build_sarif_report_handles_empty_results() -> None:
    report = build_sarif_report(_validation_result())

    _validate_schema(report)

    assert report["runs"][0]["results"] == []


def test_build_sarif_report_sorts_results_by_location_then_code() -> None:
    first = _validation_error(
        code=ErrorCode.FILE_NOT_FOUND,
        message="No file location",
        file=None,
        line=None,
    )
    second = _validation_error(
        code=ErrorCode.ARTIFACT_NOT_DEFINED,
        message="Later code at same line",
        file="src/a.py",
        line=2,
    )
    third = _validation_error(
        code=ErrorCode.FILE_NOT_FOUND,
        message="Earlier code at same line",
        file="src/a.py",
        line=2,
    )
    fourth = _validation_error(
        code=ErrorCode.SCHEMA_VALIDATION_ERROR,
        message="Later file",
        file="src/b.py",
        line=1,
    )
    batch = BatchValidationResult(
        results=[_validation_result(errors=[second, fourth, third, first])],
        total_manifests=1,
        passed=0,
        failed=1,
        skipped=0,
    )

    report = build_sarif_report(batch)

    assert [result["ruleId"] for result in report["runs"][0]["results"]] == [
        "E001",
        "E001",
        "E300",
        "E004",
    ]


def test_build_sarif_report_maps_warning_and_info_to_sarif_levels() -> None:
    warning = _validation_error(
        code=ErrorCode.MISSING_RETURN_TYPE,
        message="Missing return type",
        severity=Severity.WARNING,
    )
    info = _validation_error(
        code=ErrorCode.GRANDFATHERED_SUPERSESSION,
        message="Grandfathered supersession",
        severity=Severity.INFO,
    )

    report = build_sarif_report(_validation_result(warnings=[info, warning]))

    levels_by_rule_id = {
        result["ruleId"]: result["level"] for result in report["runs"][0]["results"]
    }
    assert levels_by_rule_id["E304"] == "warning"
    assert levels_by_rule_id["E111"] == "note"


def test_build_sarif_report_flattens_verify_stage_diagnostics() -> None:
    validation_error = _validation_error(
        code=ErrorCode.ARTIFACT_NOT_DEFINED,
        message="Validation failed",
        file="src/validation.py",
        line=7,
    )
    stage_error = _validation_error(
        code=ErrorCode.CHANGED_FILE_OUTSIDE_MANIFEST_SCOPE,
        message="Changed file is out of scope",
        file="src/changed.py",
        line=None,
    )
    verify_result = VerificationResult(
        stages=(
            VerificationStageResult(
                name="validation",
                success=False,
                _validation=_validation_result(errors=[validation_error]),
            ),
            VerificationStageResult(
                name="changed_scope",
                success=False,
                _errors=(stage_error,),
            ),
        )
    )

    report = build_sarif_report(verify_result)

    _validate_schema(report)

    assert [result["ruleId"] for result in report["runs"][0]["results"]] == [
        "E114",
        "E300",
    ]


def test_build_sarif_report_includes_verify_report_object_errors() -> None:
    artifact_error = _validation_error(
        code=ErrorCode.ARTIFACT_NOT_EXECUTED_BY_TESTS,
        message="Artifact was not executed",
        file="src/coverage.py",
        line=12,
    )
    verify_result = VerificationResult(
        stages=(
            VerificationStageResult(
                name="artifact_coverage",
                success=False,
                _errors=(
                    ArtifactCoverageReport(findings=(), errors=(artifact_error,)),
                ),
            ),
        )
    )

    report = build_sarif_report(verify_result)

    _validate_schema(report)

    result = report["runs"][0]["results"][0]
    assert result["ruleId"] == "E710"
    assert result["message"]["text"].startswith("Artifact was not executed")
    assert result["locations"][0]["physicalLocation"]["artifactLocation"] == {
        "uri": "src/coverage.py"
    }


def test_write_sarif_report_is_byte_stable(tmp_path: Path) -> None:
    report = build_sarif_report(_validation_result(errors=[_validation_error()]))
    first = tmp_path / "first.sarif"
    second = tmp_path / "second.sarif"

    write_sarif_report(report, first)
    write_sarif_report(report, second)

    assert first.read_bytes() == second.read_bytes()
    assert first.read_text().endswith("\n")
