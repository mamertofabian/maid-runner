"""Strict-preview migration delta comparison."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Mapping

from maid_runner.core.artifact_coverage import ArtifactCoverageReport
from maid_runner.core.result import BatchValidationResult, Severity, ValidationError


@dataclass(frozen=True)
class StrictDeltaEntry:
    manifest_path: str
    file: str | None
    code: str
    severity: str
    message: str


@dataclass(frozen=True)
class StrictDeltaReport:
    entries: tuple[StrictDeltaEntry, ...]

    def to_dict(self) -> dict:
        return {"entries": [_entry_to_dict(entry) for entry in self.entries]}


def compute_strict_delta(
    default_result: BatchValidationResult,
    strict_result: BatchValidationResult,
    default_coverage: Mapping[str, ArtifactCoverageReport] | None = None,
    strict_coverage: Mapping[str, ArtifactCoverageReport] | None = None,
) -> StrictDeltaReport:
    default_identities = {
        identity for identity, _entry in _iter_entries(default_result, default_coverage)
    }
    unique_entries: dict[tuple[str, str, str | None], StrictDeltaEntry] = {}
    for identity, entry in _iter_entries(strict_result, strict_coverage):
        if identity in default_identities:
            continue
        unique_entries.setdefault(identity, entry)

    return StrictDeltaReport(
        entries=tuple(
            sorted(
                unique_entries.values(),
                key=lambda entry: (entry.manifest_path, entry.file or "", entry.code),
            )
        )
    )


def _iter_entries(
    result: BatchValidationResult,
    coverage: Mapping[str, ArtifactCoverageReport] | None,
) -> tuple[tuple[tuple[str, str, str | None], StrictDeltaEntry], ...]:
    entries: list[tuple[tuple[str, str, str | None], StrictDeltaEntry]] = []
    for validation in result.results:
        for diagnostic in (*validation.errors, *validation.warnings):
            entry = _entry_from_diagnostic(validation.manifest_path, diagnostic)
            if entry is None:
                continue
            entries.append((_identity(entry), entry))
    for diagnostic in result.chain_errors:
        manifest_path = _chain_manifest_path(diagnostic)
        entry = _entry_from_diagnostic(manifest_path, diagnostic)
        if entry is None:
            continue
        entries.append((_identity(entry), entry))
    for manifest_path, report in (coverage or {}).items():
        for diagnostic in report.errors:
            entry = _entry_from_diagnostic(manifest_path, diagnostic)
            if entry is None:
                continue
            entries.append((_identity(entry), entry))
    return tuple(entries)


def _entry_from_diagnostic(
    manifest_path: str,
    diagnostic: ValidationError,
) -> StrictDeltaEntry | None:
    severity = _enum_value(diagnostic.severity)
    if severity == Severity.INFO.value:
        return None
    return StrictDeltaEntry(
        manifest_path=_stable_path(manifest_path),
        file=_stable_path(diagnostic.location.file) if diagnostic.location else None,
        code=_enum_value(diagnostic.code),
        severity=severity,
        message=diagnostic.message,
    )


def _entry_to_dict(entry: StrictDeltaEntry) -> dict:
    return {
        "manifest_path": entry.manifest_path,
        "file": entry.file,
        "code": entry.code,
        "severity": entry.severity,
        "message": entry.message,
    }


def _identity(entry: StrictDeltaEntry) -> tuple[str, str, str | None]:
    return (entry.code, entry.manifest_path, entry.file)


def _enum_value(value: object) -> str:
    return str(getattr(value, "value", value))


def _chain_manifest_path(diagnostic: ValidationError) -> str:
    if diagnostic.location and diagnostic.location.file.endswith((".yaml", ".yml")):
        return diagnostic.location.file
    return "<manifest-chain>"


def _stable_path(path: str) -> str:
    path_obj = Path(path)
    if not path_obj.is_absolute():
        return path_obj.as_posix()
    try:
        return path_obj.relative_to(Path.cwd()).as_posix()
    except ValueError:
        return path_obj.as_posix()
