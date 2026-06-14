"""Failure packet construction for retry-capable MAID gates."""

from __future__ import annotations

import json
import platform
import re
from pathlib import Path
from typing import Union

from maid_runner import __version__
from maid_runner.core.diagnostics_registry import render_next_action
from maid_runner.core.manifest import load_manifest
from maid_runner.core.result import (
    BatchTestResult,
    BatchValidationResult,
    FileTrackingEntry,
    FileTrackingStatus,
    Severity,
    ValidationError,
    ValidationResult,
    ErrorCode,
    Location,
    VerificationResult,
)
from maid_runner.core.types import FileSpec, Manifest

_OUTPUT_TAIL_LINES = 50
_ARTIFACT_RE = re.compile(r"Artifact '([^']+)'")
_FUNCTION_RE = re.compile(r"Function '([^']+)'")


def build_failure_packet(
    command: list[str],
    exit_code: int,
    project_root: Union[str, Path],
    validation: "BatchValidationResult | ValidationResult | VerificationResult",
    test_results: BatchTestResult | None = None,
) -> dict:
    root = Path(project_root).resolve()
    tests = _test_results_from_validation(validation, test_results)
    diagnostics = [
        *_diagnostics_from_validation(validation),
        *_diagnostics_from_test_results(test_results),
    ]
    failed_manifest_paths = _failed_manifest_paths(validation, tests, diagnostics)

    return {
        "packet_version": 1,
        "command": list(command),
        "exit_code": exit_code,
        "project_root": str(root),
        "manifest": _manifest_entries(failed_manifest_paths, root),
        "diagnostics": _diagnostic_entries(diagnostics, failed_manifest_paths),
        "test_output": _test_output_entries(tests),
        "environment": {
            "maid_version": __version__,
            "python_version": platform.python_version(),
        },
    }


def write_failure_packet(packet: dict, path: Union[str, Path]) -> None:
    packet_path = Path(path)
    packet_path.parent.mkdir(parents=True, exist_ok=True)
    packet_path.write_text(json.dumps(packet, indent=2, sort_keys=True) + "\n")


def clear_failure_packet(path: Union[str, Path]) -> bool:
    packet_path = Path(path)
    if not packet_path.exists():
        return False
    if not packet_path.is_file():
        return False
    packet_path.unlink()
    return True


def _failed_manifest_paths(
    validation: "BatchValidationResult | ValidationResult | VerificationResult",
    test_results: list,
    diagnostics: list[tuple[ValidationError, str]],
) -> list[str]:
    paths: set[str] = set()
    slug_paths = _manifest_paths_by_slug(validation)
    for result in _failed_validation_results(validation):
        paths.add(result.manifest_path)
    for result in test_results:
        if result.success:
            continue
        manifest_path = slug_paths.get(result.manifest_slug)
        if manifest_path is not None:
            paths.add(manifest_path)
    for error, manifest_path in diagnostics:
        if manifest_path:
            paths.add(manifest_path)
            continue
        diagnostic_path = _manifest_path_from_error(error)
        if diagnostic_path:
            paths.add(diagnostic_path)
    return sorted(paths)


def _manifest_paths_by_slug(
    validation: "BatchValidationResult | ValidationResult | VerificationResult",
) -> dict[str, str]:
    return {
        result.manifest_slug: result.manifest_path
        for result in _validation_results(validation)
    }


def _failed_validation_results(
    validation: "BatchValidationResult | ValidationResult | VerificationResult",
) -> list[ValidationResult]:
    if isinstance(validation, ValidationResult):
        return [validation] if not validation.success else []
    if isinstance(validation, BatchValidationResult):
        return [result for result in validation.results if not result.success]

    results: list[ValidationResult] = []
    for stage in validation.stages:
        stage_validation = getattr(stage, "_validation", None)
        if isinstance(stage_validation, ValidationResult):
            if not stage_validation.success or (
                not stage.success and stage_validation.warnings
            ):
                results.append(stage_validation)
        elif isinstance(stage_validation, BatchValidationResult):
            for result in stage_validation.results:
                if not result.success or (not stage.success and result.warnings):
                    results.append(result)
    return results


def _validation_results(
    validation: "BatchValidationResult | ValidationResult | VerificationResult",
) -> list[ValidationResult]:
    if isinstance(validation, ValidationResult):
        return [validation]
    if isinstance(validation, BatchValidationResult):
        return list(validation.results)
    results: list[ValidationResult] = []
    for stage in validation.stages:
        stage_validation = getattr(stage, "_validation", None)
        if isinstance(stage_validation, ValidationResult):
            results.append(stage_validation)
        elif isinstance(stage_validation, BatchValidationResult):
            results.extend(stage_validation.results)
    return results


def _diagnostics_from_validation(
    validation: "BatchValidationResult | ValidationResult | VerificationResult",
) -> list[tuple[ValidationError, str]]:
    diagnostics: list[tuple[ValidationError, str]] = []
    if isinstance(validation, VerificationResult):
        for stage in validation.stages:
            stage_validation = getattr(stage, "_validation", None)
            if stage_validation is not None:
                diagnostics.extend(_diagnostics_from_validation(stage_validation))
            coherence = getattr(stage, "_coherence", None)
            if coherence is not None:
                diagnostics.extend(_diagnostics_from_coherence(coherence))
            file_tracking = getattr(stage, "_file_tracking", None)
            if file_tracking is not None:
                diagnostics.extend(_diagnostics_from_file_tracking(file_tracking))
            for error in getattr(stage, "_errors", ()):
                if isinstance(error, ValidationError):
                    diagnostics.append((error, _manifest_path_from_error(error)))
        return diagnostics

    if isinstance(validation, BatchValidationResult):
        diagnostics.extend(
            (error, _manifest_path_from_error(error))
            for error in validation.chain_errors
        )
        for result in sorted(validation.results, key=lambda item: item.manifest_path):
            diagnostics.extend((error, result.manifest_path) for error in result.errors)
            diagnostics.extend(
                (warning, result.manifest_path) for warning in result.warnings
            )
        return diagnostics

    diagnostics.extend((error, validation.manifest_path) for error in validation.errors)
    diagnostics.extend(
        (warning, validation.manifest_path) for warning in validation.warnings
    )
    return diagnostics


def _diagnostics_from_test_results(
    test_results: BatchTestResult | None,
) -> list[tuple[ValidationError, str]]:
    if test_results is None:
        return []
    return [
        (error, _manifest_path_from_error(error)) for error in test_results.chain_errors
    ]


def _diagnostics_from_coherence(coherence) -> list[tuple[ValidationError, str]]:
    diagnostics: list[tuple[ValidationError, str]] = []
    for issue in getattr(coherence, "issues", ()):
        manifest_path = _coherence_issue_manifest_path(issue)
        diagnostics.append(
            (
                ValidationError(
                    code=_coherence_issue_code(issue),
                    message=getattr(issue, "message", str(issue)),
                    severity=_coherence_issue_severity(issue),
                    location=(
                        Location(file=getattr(issue, "file"))
                        if getattr(issue, "file", None)
                        else None
                    ),
                    suggestion=getattr(issue, "suggestion", None),
                ),
                manifest_path,
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


def _coherence_issue_manifest_path(issue) -> str:
    manifests = tuple(getattr(issue, "manifests", ()) or ())
    if not manifests:
        return ""
    first = manifests[0]
    if first.endswith((".manifest.yaml", ".manifest.yml", ".manifest.json")):
        return first
    return f"manifests/{first}.manifest.yaml"


def _diagnostics_from_file_tracking(report) -> list[tuple[ValidationError, str]]:
    diagnostics: list[tuple[ValidationError, str]] = []
    for entry in getattr(report, "entries", ()):
        if not isinstance(entry, FileTrackingEntry):
            continue
        if entry.status not in {
            FileTrackingStatus.UNDECLARED,
            FileTrackingStatus.REGISTERED,
        }:
            continue
        diagnostics.append(
            (
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
                ),
                "",
            )
        )
    return diagnostics


def _manifest_path_from_error(error: ValidationError) -> str:
    location = error.location
    if location is None:
        return ""
    file = str(location.file)
    if ".manifest." in file:
        return file
    return ""


def _test_results_from_validation(
    validation: BatchValidationResult | ValidationResult | VerificationResult,
    test_results: BatchTestResult | None,
) -> list:
    results = list(test_results.results) if test_results is not None else []
    if isinstance(validation, VerificationResult):
        for stage in validation.stages:
            tests = getattr(stage, "_tests", None)
            if tests is not None:
                results.extend(tests.results)
    return results


def _manifest_entries(manifest_paths: list[str], project_root: Path) -> list[dict]:
    entries = []
    for path in manifest_paths:
        try:
            manifest = load_manifest(path)
        except Exception:
            entries.append(_fallback_manifest_entry(path, project_root))
            continue
        entries.append(_manifest_entry(manifest, project_root))
    return entries


def _fallback_manifest_entry(path: str, project_root: Path) -> dict:
    return {
        "path": _display_manifest_path(path, project_root),
        "goal": None,
        "type": None,
        "declared_files": [],
        "validate": [],
    }


def _manifest_entry(manifest: Manifest, project_root: Path) -> dict:
    return {
        "path": _display_manifest_path(manifest.source_path, project_root),
        "goal": manifest.goal,
        "type": manifest.task_type.value if manifest.task_type else None,
        "declared_files": _declared_file_entries(manifest),
        "validate": [" ".join(command) for command in manifest.validate_commands],
    }


def _declared_file_entries(manifest: Manifest) -> list[dict]:
    entries: list[dict] = []
    for section, specs in (
        ("create", manifest.files_create),
        ("edit", manifest.files_edit),
        ("snapshot", manifest.files_snapshot),
    ):
        for spec in specs:
            entries.append(_file_spec_entry(section, spec))
    for path in manifest.files_read:
        entries.append({"section": "read", "path": path, "artifacts": []})
    for spec in manifest.files_delete:
        entries.append({"section": "delete", "path": spec.path, "artifacts": []})
    return sorted(entries, key=lambda item: (item["path"], item["section"]))


def _file_spec_entry(section: str, spec: FileSpec) -> dict:
    return {
        "section": section,
        "path": spec.path,
        "artifacts": sorted(artifact.qualified_name for artifact in spec.artifacts),
    }


def _diagnostic_entries(
    diagnostics: list[tuple[ValidationError, str]],
    manifest_paths: list[str],
) -> list[dict]:
    del manifest_paths
    return [
        _diagnostic_entry(error, manifest_path)
        for error, manifest_path in sorted(diagnostics, key=_diagnostic_sort_key)
    ]


def _diagnostic_entry(error: ValidationError, manifest_path: str) -> dict:
    location = error.location
    file = location.file if location else None
    artifact = _artifact_from_message(error.message)
    command = _command_from_message(error.message)
    values = {
        "file": file or "",
        "test": file or "",
        "artifact": artifact,
        "command": command,
        "manifest": manifest_path,
    }
    try:
        next_action = render_next_action(error.code.value, values)
    except (KeyError, ValueError):
        next_action = None

    return {
        "code": error.code.value,
        "message": error.message,
        "file": file,
        "line": location.line if location else None,
        "suggestion": error.suggestion,
        "next_action": next_action,
    }


def _diagnostic_sort_key(item: tuple[ValidationError, str]) -> tuple:
    error, manifest_path = item
    location = error.location
    return (
        manifest_path,
        location.file if location else "",
        location.line if location and location.line is not None else -1,
        error.code.value,
        error.message,
        error.severity.value if isinstance(error.severity, Severity) else "",
    )


def _artifact_from_message(message: str) -> str:
    for pattern in (_ARTIFACT_RE, _FUNCTION_RE):
        match = pattern.search(message)
        if match:
            return match.group(1)
    return ""


def _command_from_message(message: str) -> str:
    if "`" not in message:
        return ""
    parts = message.split("`")
    return parts[1] if len(parts) > 1 else ""


def _test_output_entries(results: list) -> list[dict]:
    entries = []
    for result in results:
        if result.success:
            continue
        combined = "\n".join(part for part in (result.stdout, result.stderr) if part)
        entries.append(
            {
                "manifest": result.manifest_slug,
                "command": " ".join(result.command),
                "exit_code": result.exit_code,
                "output_tail": _tail_lines(combined),
            }
        )
    return sorted(entries, key=lambda item: (item["manifest"], item["command"]))


def _tail_lines(output: str) -> str:
    lines = output.splitlines()
    return "\n".join(lines[-_OUTPUT_TAIL_LINES:])


def _display_manifest_path(path: str, project_root: Path) -> str:
    manifest_path = Path(path)
    try:
        return str(manifest_path.resolve().relative_to(project_root))
    except ValueError:
        return str(manifest_path)
