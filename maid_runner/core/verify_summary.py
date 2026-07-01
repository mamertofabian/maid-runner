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
    passed_stages: tuple[str, ...]
    warning_groups: tuple[VerifyWarningGroup, ...]
    raw_warning_count: int


def build_verify_summary(result: VerificationResult) -> VerifySummary:
    warning_counts: dict[tuple[Optional[str], Optional[str], str], int] = {}
    ordered_keys: list[tuple[Optional[str], Optional[str], str]] = []

    for warning in _iter_validation_warnings(result):
        key = (_error_code(warning), _render_location(warning), warning.message)
        if key not in warning_counts:
            ordered_keys.append(key)
            warning_counts[key] = 0
        warning_counts[key] += 1

    warning_groups = tuple(
        VerifyWarningGroup(
            code=code,
            location=location,
            message=message,
            count=warning_counts[(code, location, message)],
        )
        for code, location, message in ordered_keys
    )

    return VerifySummary(
        success=all(stage.success for stage in result.stages),
        blocking_stages=tuple(
            stage.name for stage in result.stages if not stage.success
        ),
        passed_stages=tuple(stage.name for stage in result.stages if stage.success),
        warning_groups=warning_groups,
        raw_warning_count=sum(warning_counts.values()),
    )


def _iter_validation_warnings(result: VerificationResult):
    for stage in result.stages:
        validation = getattr(stage, "_validation", None)
        if validation is None:
            continue

        for warning in getattr(validation, "warnings", ()):
            if _is_warning(warning):
                yield warning

        for warning in getattr(validation, "chain_errors", ()):
            if _is_warning(warning):
                yield warning

        for item in getattr(validation, "results", ()):
            for warning in getattr(item, "warnings", ()):
                if _is_warning(warning):
                    yield warning


def _is_warning(error: ValidationError) -> bool:
    severity = getattr(error, "severity", None)
    return getattr(severity, "value", severity) == Severity.WARNING.value


def _error_code(error: ValidationError) -> Optional[str]:
    code = getattr(error, "code", None)
    value = getattr(code, "value", code)
    if value is None:
        return None
    return str(value)


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
