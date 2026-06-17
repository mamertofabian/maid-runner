"""SARIF 2.1.0 serialization for MAID validation results."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Union

from maid_runner import __version__
from maid_runner.core.diagnostics_registry import all_rules
from maid_runner.core.result import (
    BatchValidationResult,
    ErrorCode,
    FileTrackingEntry,
    FileTrackingStatus,
    Location,
    Severity,
    ValidationError,
    ValidationResult,
    VerificationResult,
)


def sarif_level_for_severity(severity: Severity) -> str:
    if severity == Severity.ERROR:
        return "error"
    if severity == Severity.WARNING:
        return "warning"
    return "note"


def build_sarif_report(
    result: Union[ValidationResult, BatchValidationResult, VerificationResult],
) -> dict:
    diagnostics = sorted(
        _diagnostics_from_result(result),
        key=_diagnostic_sort_key,
    )
    rules_by_code = {rule.code: rule for rule in all_rules()}
    referenced_codes = {diagnostic.code.value for diagnostic in diagnostics}
    rules = [
        _sarif_rule(rules_by_code[code])
        for code in sorted(referenced_codes)
        if code in rules_by_code
    ]

    return {
        "$schema": (
            "https://docs.oasis-open.org/sarif/sarif/v2.1.0/os/schemas/"
            "sarif-schema-2.1.0.json"
        ),
        "version": "2.1.0",
        "runs": [
            {
                "tool": {
                    "driver": {
                        "name": "maid-runner",
                        "semanticVersion": __version__,
                        "rules": rules,
                    }
                },
                "results": [_sarif_result(diagnostic) for diagnostic in diagnostics],
            }
        ],
    }


def write_sarif_report(report: dict, output_path: Union[str, Path]) -> None:
    path = Path(output_path)
    path.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")


def _diagnostics_from_result(
    result: ValidationResult | BatchValidationResult | VerificationResult,
) -> list[ValidationError]:
    if isinstance(result, VerificationResult):
        diagnostics: list[ValidationError] = []
        for stage in result.stages:
            validation = getattr(stage, "_validation", None)
            if validation is not None:
                diagnostics.extend(_diagnostics_from_result(validation))
            coherence = getattr(stage, "_coherence", None)
            if coherence is not None:
                diagnostics.extend(_diagnostics_from_coherence(coherence))
            file_tracking = getattr(stage, "_file_tracking", None)
            if file_tracking is not None:
                diagnostics.extend(_diagnostics_from_file_tracking(file_tracking))
            diagnostics.extend(
                error
                for error in getattr(stage, "_errors", ())
                if isinstance(error, ValidationError)
            )
            for report in getattr(stage, "_errors", ()):
                diagnostics.extend(_diagnostics_from_report_object(report))
        return diagnostics

    if isinstance(result, BatchValidationResult):
        diagnostics = list(result.chain_errors)
        for validation in result.results:
            diagnostics.extend(validation.errors)
            diagnostics.extend(validation.warnings)
        return diagnostics

    return [*result.errors, *result.warnings]


def _diagnostics_from_coherence(coherence) -> list[ValidationError]:
    diagnostics = []
    for issue in getattr(coherence, "issues", ()):
        file = getattr(issue, "file", None)
        diagnostics.append(
            ValidationError(
                code=_coherence_issue_code(issue),
                message=getattr(issue, "message", str(issue)),
                severity=_coherence_issue_severity(issue),
                location=Location(file=file) if file else None,
                suggestion=getattr(issue, "suggestion", None),
            )
        )
    return diagnostics


def _coherence_issue_code(issue) -> ErrorCode:
    issue_type = getattr(getattr(issue, "issue_type", None), "value", "")
    return {
        "duplicate": ErrorCode.COHERENCE_DUPLICATE,
        "signature_conflict": ErrorCode.COHERENCE_SIGNATURE_CONFLICT,
        "boundary_violation": ErrorCode.COHERENCE_BOUNDARY_VIOLATION,
        "naming": ErrorCode.COHERENCE_NAMING_VIOLATION,
        "dependency": ErrorCode.COHERENCE_DEPENDENCY_MISSING,
    }.get(issue_type, ErrorCode.COHERENCE_BOUNDARY_VIOLATION)


def _coherence_issue_severity(issue) -> Severity:
    severity = getattr(getattr(issue, "severity", None), "value", "")
    if severity == Severity.WARNING.value:
        return Severity.WARNING
    if severity == Severity.INFO.value:
        return Severity.INFO
    return Severity.ERROR


def _diagnostics_from_file_tracking(report) -> list[ValidationError]:
    diagnostics = []
    for entry in getattr(report, "entries", ()):
        if not isinstance(entry, FileTrackingEntry):
            continue
        if entry.status not in {
            FileTrackingStatus.UNDECLARED,
            FileTrackingStatus.REGISTERED,
        }:
            continue
        diagnostics.append(
            ValidationError(
                code=ErrorCode.CHANGED_FILE_OUTSIDE_MANIFEST_SCOPE,
                message=(
                    f"File tracking reported {entry.status.value} file: "
                    f"{entry.path}"
                ),
                severity=Severity.ERROR,
                location=Location(file=entry.path),
                suggestion=(
                    "Declare the file in an active manifest or remove the "
                    "untracked production change."
                ),
            )
        )
    return diagnostics


def _diagnostics_from_report_object(report) -> list[ValidationError]:
    return [
        error
        for error in getattr(report, "errors", ())
        if isinstance(error, ValidationError)
    ]


def _diagnostic_sort_key(diagnostic: ValidationError) -> tuple[str, int, str, str]:
    location = diagnostic.location
    file = "" if location is None else str(location.file or "")
    line = 0 if location is None or location.line is None else location.line
    return (file, line, diagnostic.code.value, diagnostic.message)


def _sarif_rule(rule) -> dict:
    return {
        "id": rule.code,
        "name": rule.code,
        "shortDescription": {"text": rule.short_description},
        "fullDescription": {"text": rule.description},
        "helpUri": rule.help_uri,
        "defaultConfiguration": {
            "level": sarif_level_for_severity(Severity(rule.default_severity))
        },
    }


def _sarif_result(diagnostic: ValidationError) -> dict:
    result = {
        "ruleId": diagnostic.code.value,
        "level": sarif_level_for_severity(diagnostic.severity),
        "message": {"text": _message_text(diagnostic)},
    }
    location = _sarif_location(diagnostic.location)
    if location is not None:
        result["locations"] = [location]
    return result


def _message_text(diagnostic: ValidationError) -> str:
    if diagnostic.suggestion:
        return f"{diagnostic.message}\n\nSuggestion: {diagnostic.suggestion}"
    return diagnostic.message


def _sarif_location(location: Location | None) -> dict | None:
    if location is None or not location.file:
        return None

    physical_location: dict = {
        "artifactLocation": {"uri": str(location.file)},
    }
    region = _sarif_region(location)
    if region:
        physical_location["region"] = region
    return {"physicalLocation": physical_location}


def _sarif_region(location: Location) -> dict:
    region = {}
    if location.line is not None:
        region["startLine"] = location.line
    if location.column is not None:
        region["startColumn"] = location.column
    if location.end_line is not None:
        region["endLine"] = location.end_line
    if location.end_column is not None:
        region["endColumn"] = location.end_column
    return region
