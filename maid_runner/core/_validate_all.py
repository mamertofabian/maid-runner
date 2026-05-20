"""Batch validation orchestration helpers."""

from __future__ import annotations

import time
from pathlib import Path
from typing import Callable, Union

from maid_runner.core.chain import ManifestChain
from maid_runner.core.result import (
    BatchValidationResult,
    ErrorCode,
    FileTrackingReport,
    Location,
    Severity,
    ValidationError,
    ValidationResult,
)
from maid_runner.core.types import ValidationMode


def _run_validate_all(
    *,
    project_root: Path,
    manifest_dir: Union[str, Path],
    mode: ValidationMode,
    check_file_tracking: bool,
    allow_empty: bool,
    check_stubs: bool,
    check_assertions: bool,
    fail_on_warnings: bool,
    validate_manifest: Callable[..., ValidationResult],
    run_file_tracking: Callable[[ManifestChain], FileTrackingReport],
    chain_factory: Callable[[Path, Path], ManifestChain],
) -> BatchValidationResult:
    start = time.monotonic()
    chain_dir = project_root / manifest_dir

    if not chain_dir.exists():
        if not allow_empty:
            duration = (time.monotonic() - start) * 1000
            return _empty_manifest_set_result(
                chain_dir,
                message=f"Manifest directory not found: {chain_dir}",
                duration_ms=duration,
            )
        return BatchValidationResult(
            results=[],
            total_manifests=0,
            passed=0,
            failed=0,
            skipped=0,
            duration_ms=(time.monotonic() - start) * 1000,
        )

    chain = chain_factory(chain_dir, project_root)

    if mode == ValidationMode.SCHEMA:
        return _validate_schema_manifests(
            chain=chain,
            chain_dir=chain_dir,
            start=start,
            allow_empty=allow_empty,
            check_file_tracking=check_file_tracking,
            fail_on_warnings=fail_on_warnings,
            validate_manifest=validate_manifest,
            run_file_tracking=run_file_tracking,
        )

    return _validate_active_manifests(
        chain=chain,
        chain_dir=chain_dir,
        manifest_dir=manifest_dir,
        start=start,
        mode=mode,
        allow_empty=allow_empty,
        check_file_tracking=check_file_tracking,
        check_stubs=check_stubs,
        check_assertions=check_assertions,
        fail_on_warnings=fail_on_warnings,
        validate_manifest=validate_manifest,
        run_file_tracking=run_file_tracking,
    )


def _validate_schema_manifests(
    *,
    chain: ManifestChain,
    chain_dir: Path,
    start: float,
    allow_empty: bool,
    check_file_tracking: bool,
    fail_on_warnings: bool,
    validate_manifest: Callable[..., ValidationResult],
    run_file_tracking: Callable[[ManifestChain], FileTrackingReport],
) -> BatchValidationResult:
    manifests = chain.all_manifests
    if not manifests and not chain.load_errors and not allow_empty:
        duration = (time.monotonic() - start) * 1000
        return _empty_manifest_set_result(
            chain_dir,
            message=f"No active manifests discovered in {chain_dir}",
            chain_errors=chain.load_errors + chain.inactive_manifest_diagnostics(),
            duration_ms=duration,
        )

    results: list[ValidationResult] = []
    for manifest in manifests:
        result = validate_manifest(
            manifest,
            mode=ValidationMode.SCHEMA,
            fail_on_warnings=fail_on_warnings,
        )
        results.append(result)

    duration = (time.monotonic() - start) * 1000
    passed = sum(1 for result in results if result.success)
    failed = len(results) - passed
    chain_errors = chain.load_errors + chain.inactive_manifest_diagnostics()
    if fail_on_warnings and _has_warning(chain_errors):
        failed += 1
    if check_file_tracking:
        passed, failed = _apply_file_tracking_gate(
            results,
            chain_errors,
            run_file_tracking(chain),
            passed=passed,
            failed=failed,
        )

    return BatchValidationResult(
        results=results,
        total_manifests=len(manifests) + len(chain.load_errors),
        passed=passed,
        failed=failed,
        skipped=0,
        chain_errors=chain_errors,
        duration_ms=duration,
    )


def _validate_active_manifests(
    *,
    chain: ManifestChain,
    chain_dir: Path,
    manifest_dir: Union[str, Path],
    start: float,
    mode: ValidationMode,
    allow_empty: bool,
    check_file_tracking: bool,
    check_stubs: bool,
    check_assertions: bool,
    fail_on_warnings: bool,
    validate_manifest: Callable[..., ValidationResult],
    run_file_tracking: Callable[[ManifestChain], FileTrackingReport],
) -> BatchValidationResult:
    chain_errors = chain.diagnostics()
    active = chain.active_manifests()
    superseded = chain.superseded_manifests()

    if not active and not allow_empty:
        duration = (time.monotonic() - start) * 1000
        return _empty_manifest_set_result(
            chain_dir,
            message=f"No active manifests discovered in {chain_dir}",
            chain_errors=chain_errors,
            duration_ms=duration,
        )

    results: list[ValidationResult] = []
    passed = 0
    failed = 0

    for manifest in active:
        result = validate_manifest(
            manifest,
            mode=mode,
            use_chain=True,
            chain=chain,
            manifest_dir=manifest_dir,
            check_stubs=check_stubs,
            check_assertions=check_assertions,
            fail_on_warnings=fail_on_warnings,
            include_chain_diagnostics=False,
        )
        results.append(result)
        if result.success:
            passed += 1
        else:
            failed += 1

    if fail_on_warnings and _has_warning(chain_errors):
        failed += 1

    if check_file_tracking:
        passed, failed = _apply_file_tracking_gate(
            results,
            chain_errors,
            run_file_tracking(chain),
            passed=passed,
            failed=failed,
        )

    duration = (time.monotonic() - start) * 1000

    return BatchValidationResult(
        results=results,
        total_manifests=len(active) + len(superseded) + len(chain.load_errors),
        passed=passed,
        failed=failed,
        skipped=len(superseded),
        chain_errors=chain_errors,
        duration_ms=duration,
    )


def _has_warning(errors: list[ValidationError]) -> bool:
    return any(error.severity == Severity.WARNING for error in errors)


def _file_tracking_gate_error(
    report: FileTrackingReport,
) -> ValidationError | None:
    parts = []
    if report.undeclared:
        paths = ", ".join(entry.path for entry in report.undeclared)
        parts.append(f"undeclared: {paths}")
    if report.registered:
        paths = ", ".join(entry.path for entry in report.registered)
        parts.append(f"registered: {paths}")
    if not parts:
        return None

    return ValidationError(
        code=ErrorCode.COHERENCE_BOUNDARY_VIOLATION,
        message=f"File tracking gate failed ({'; '.join(parts)})",
        severity=Severity.ERROR,
    )


def _apply_file_tracking_gate(
    results: list[ValidationResult],
    chain_errors: list[ValidationError],
    report: FileTrackingReport,
    *,
    passed: int,
    failed: int,
) -> tuple[int, int]:
    tracking_error = _file_tracking_gate_error(report)
    if tracking_error is None:
        return passed, failed

    if results:
        target = results[0]
        target.file_tracking = report
        target.errors.append(tracking_error)
        if target.success:
            target.success = False
            return passed - 1, failed + 1
        return passed, failed

    chain_errors.append(tracking_error)
    return passed, failed + 1


def _empty_manifest_set_result(
    manifest_dir: Path,
    *,
    message: str,
    chain_errors: list[ValidationError] | None = None,
    duration_ms: float | None = None,
) -> BatchValidationResult:
    errors = list(chain_errors or [])
    errors.append(
        ValidationError(
            code=ErrorCode.EMPTY_MANIFEST_SET,
            message=message,
            location=Location(file=str(manifest_dir)),
            suggestion="Pass --allow-empty only when an empty manifest set is intentional.",
        )
    )
    return BatchValidationResult(
        results=[],
        total_manifests=0,
        passed=0,
        failed=1,
        skipped=0,
        chain_errors=errors,
        duration_ms=duration_ms,
    )
