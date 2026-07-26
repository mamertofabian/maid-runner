"""Summary view helpers for MAID verify results."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from maid_runner.core.result import (
    Severity,
    ValidationError,
    VerificationResult,
)


@dataclass(frozen=True)
class VerifyWarningGroup:
    code: Optional[str]
    message: str
    location: Optional[str]
    count: int


@dataclass(frozen=True)
class VerifySummary:
    success: bool
    blocking_stages: tuple[str, ...]
    warning_blocking_stages: tuple[str, ...]
    passed_stages: tuple[str, ...]
    skipped_stages: tuple[str, ...]
    warning_groups: tuple[VerifyWarningGroup, ...]
    info_groups: tuple[VerifyWarningGroup, ...]
    raw_warning_count: int
    raw_info_count: int


def build_verify_summary(result: VerificationResult) -> VerifySummary:
    warning_counts: dict[tuple[Optional[str], Optional[str], str], int] = {}
    ordered_keys: list[tuple[Optional[str], Optional[str], str]] = []

    for warning in _iter_validation_warnings(result):
        key = (_error_code(warning), _render_location(warning), warning.message)
        if key not in warning_counts:
            ordered_keys.append(key)
            warning_counts[key] = 0
        warning_counts[key] += 1

    info_counts: dict[Optional[str], int] = {}
    ordered_info_codes: list[Optional[str]] = []
    for info in _iter_validation_infos(result):
        code = _error_code(info)
        if code not in info_counts:
            ordered_info_codes.append(code)
            info_counts[code] = 0
        info_counts[code] += 1

    warning_groups = tuple(
        VerifyWarningGroup(
            code=code,
            location=location,
            message=message,
            count=warning_counts[(code, location, message)],
        )
        for code, location, message in ordered_keys
    )
    info_groups = tuple(
        VerifyWarningGroup(
            code=code,
            location=None,
            message=_info_group_message(code, info_counts[code]),
            count=info_counts[code],
        )
        for code in ordered_info_codes
    )

    return VerifySummary(
        success=all(stage.success for stage in result.stages),
        blocking_stages=tuple(
            stage.name for stage in result.stages if not stage.success
        ),
        warning_blocking_stages=tuple(
            stage.name
            for stage in result.stages
            if not stage.success and _stage_is_warning_driven(stage)
        ),
        passed_stages=tuple(
            stage.name
            for stage in result.stages
            if stage.success and getattr(stage, "skip_reason", None) is None
        ),
        skipped_stages=tuple(
            stage.name
            for stage in result.stages
            if getattr(stage, "skip_reason", None) is not None
        ),
        warning_groups=warning_groups,
        info_groups=info_groups,
        raw_warning_count=sum(warning_counts.values()),
        raw_info_count=sum(info_counts.values()),
    )


def _iter_validation_warnings(result: VerificationResult):
    for stage in result.stages:
        for finding in _iter_stage_findings(stage):
            if _is_warning(finding):
                yield finding


def _iter_validation_infos(result: VerificationResult):
    for stage in result.stages:
        for finding in _iter_stage_findings(stage):
            if _is_info(finding):
                yield finding


def _stage_is_warning_driven(stage) -> bool:
    saw_warning = False

    for finding in _iter_stage_findings(stage):
        if _is_error(finding):
            return False
        if _is_warning(finding):
            saw_warning = True

    return saw_warning


def _iter_stage_findings(stage):
    validation = getattr(stage, "_validation", None)
    if validation is not None:
        yield from _iter_validation_findings(validation)

    for error in getattr(stage, "_errors", ()):
        yield error


def _iter_validation_findings(validation):
    yield from getattr(validation, "errors", ())
    yield from getattr(validation, "warnings", ())
    yield from getattr(validation, "chain_errors", ())

    for item in getattr(validation, "results", ()):
        yield from getattr(item, "errors", ())
        yield from getattr(item, "warnings", ())


def _is_warning(error: ValidationError) -> bool:
    severity = getattr(error, "severity", None)
    return getattr(severity, "value", severity) == Severity.WARNING.value


def _is_info(error: ValidationError) -> bool:
    severity = getattr(error, "severity", None)
    return getattr(severity, "value", severity) == Severity.INFO.value


def _is_error(error) -> bool:
    severity = getattr(error, "severity", None)
    if severity is None:
        return True
    return getattr(severity, "value", severity) == Severity.ERROR.value


def _error_code(error: ValidationError) -> Optional[str]:
    code = getattr(error, "code", None)
    value = getattr(code, "value", code)
    if value is None:
        return None
    return str(value)


def _info_group_message(code: Optional[str], count: int) -> str:
    if code == "E307":
        plural = "" if count == 1 else "s"
        return f"no validator available for {count} declared non-code file{plural}"
    plural = "" if count == 1 else "s"
    return f"{count} informational diagnostic{plural}"


def _render_location(error: ValidationError) -> Optional[str]:
    location = getattr(error, "location", None)
    if location is None:
        return None

    file = getattr(location, "file", None)
    if not file:
        return None

    rendered = str(file)
    line = getattr(location, "line", None)
    column = getattr(location, "column", None)
    end_line = getattr(location, "end_line", None)
    end_column = getattr(location, "end_column", None)

    if line is not None:
        rendered = f"{rendered}:{line}"
        if column is not None:
            rendered = f"{rendered}:{column}"

    if end_line is not None:
        rendered = f"{rendered}-{end_line}"
        if end_column is not None:
            rendered = f"{rendered}:{end_column}"

    return rendered
