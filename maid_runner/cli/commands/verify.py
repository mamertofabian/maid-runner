"""CLI handler for 'maid verify' command."""

from __future__ import annotations

import argparse
import re
import subprocess
import time
from pathlib import Path
from typing import Union

from maid_runner.cli.commands._format import format_verify_result, print_error
from maid_runner.core.result import (
    ErrorCode,
    ValidationError,
    Severity,
    VerificationResult,
    VerificationStageResult,
)


_STRICT_WARNING_FAILURE_SINCE = "2026-05-17"
_WARNING_ADVISORY_TASK_TYPES = frozenset({"snapshot", "system-snapshot"})
_ADVISORY_WARNING_CODES = frozenset({ErrorCode.VALIDATOR_NOT_AVAILABLE})
_ADVISORY_CHAIN_WARNING_CODES = frozenset(
    {
        ErrorCode.GRANDFATHERED_SUPERSESSION,
        ErrorCode.IMPRECISE_CREATED_TIMESTAMP,
        ErrorCode.DUPLICATE_UNSEQUENCED_CREATED,
    }
)
_BASE_VALIDATOR_DEFAULT_HOOK_STUBS = frozenset(
    {
        "generate_test_stub",
        "get_test_function_bodies",
        "module_path",
        "resolve_reexport",
    }
)
_STUB_WARNING_FUNCTION_RE = re.compile(r"Function '([^']+)' appears to be a stub")


def cmd_verify(args: argparse.Namespace) -> int:
    try:
        advisory = getattr(args, "advisory", False)
        fail_on_warnings = (
            not advisory
            or getattr(args, "strict", False)
            or getattr(args, "fail_on_warnings", False)
        )
        result = _run_verify(
            manifest_dir=args.manifest_dir,
            project_root=".",
            allow_empty=getattr(args, "allow_empty", False),
            fail_fast=getattr(args, "fail_fast", True),
            check_assertions=True,
            check_stubs=True,
            fail_on_warnings=fail_on_warnings,
            require_worktree_scope=getattr(args, "worktree_scope", False),
            require_changed_scope=getattr(args, "changed_scope", True),
            since=getattr(args, "since", None),
            base_ref=getattr(args, "base_ref", None),
            include_tests=getattr(args, "include_tests", False),
            test_jobs=getattr(args, "test_jobs", 1),
            require_plan_lock=getattr(args, "require_plan_lock", False),
            require_red_evidence=getattr(args, "require_red_evidence", False),
            artifact_coverage=getattr(args, "artifact_coverage", False),
            knockout=getattr(args, "knockout", False),
            knockout_limit=getattr(args, "knockout_limit", None),
            knockout_allow_dirty=getattr(args, "knockout_allow_dirty", False),
        )
        print(format_verify_result(result, json_mode=getattr(args, "json", False)))
        exit_code = 0 if _result_success(result) else 1
        if not _write_sarif_report_if_requested(args, result):
            return 2
        return _finalize_packet(args, exit_code, result)
    except Exception as exc:
        print_error(str(exc), json_mode=getattr(args, "json", False))
        return 2


def _write_sarif_report_if_requested(args, result: VerificationResult) -> bool:
    output_path = getattr(args, "sarif", None)
    if not output_path:
        return True
    try:
        from maid_runner.core.sarif import build_sarif_report, write_sarif_report

        write_sarif_report(build_sarif_report(result), output_path)
        return True
    except Exception as exc:
        print_error(
            f"Failed to write SARIF report at {output_path}: {exc}",
            json_mode=getattr(args, "json", False),
        )
        return False


def _finalize_packet(args, exit_code: int, result: VerificationResult) -> int:
    packet_path = getattr(args, "packet", None)
    if packet_path is None:
        return exit_code

    from maid_runner.core.failure_packet import (
        build_failure_packet,
        clear_failure_packet,
        write_failure_packet,
    )

    if exit_code == 0:
        try:
            clear_failure_packet(packet_path)
        except Exception as exc:
            print_error(
                f"Failed to clear failure packet at {packet_path}: {exc}",
                json_mode=False,
            )
        return exit_code

    try:
        packet = build_failure_packet(
            command=getattr(args, "_maid_argv", ["maid", "verify"]),
            exit_code=exit_code,
            project_root=".",
            validation=result,
        )
        write_failure_packet(packet, packet_path)
    except Exception as exc:
        print_error(
            f"Failed to prepare failure packet at {packet_path}: {exc}",
            json_mode=False,
        )
    return exit_code


def run_verify(
    manifest_dir: str,
    project_root: Union[str, Path],
) -> VerificationResult:
    return _run_verify(
        manifest_dir=manifest_dir,
        project_root=project_root,
        check_assertions=True,
        check_stubs=True,
        fail_on_warnings=True,
    )


def _run_verify(
    *,
    manifest_dir: str,
    project_root: Union[str, Path],
    allow_empty: bool = False,
    fail_fast: bool = True,
    check_assertions: bool = True,
    check_stubs: bool = True,
    fail_on_warnings: bool = True,
    require_worktree_scope: bool = False,
    require_changed_scope: bool = False,
    since: str | None = None,
    base_ref: str | None = None,
    include_tests: bool = False,
    test_jobs: int = 1,
    require_plan_lock: bool = False,
    require_red_evidence: bool = False,
    artifact_coverage: bool = False,
    knockout: bool = False,
    knockout_limit: int | None = None,
    knockout_allow_dirty: bool = False,
) -> VerificationResult:
    from maid_runner.core.chain import (
        _enter_manifest_chain_cache_scope,
        _exit_manifest_chain_cache_scope,
    )

    chain_outermost = _enter_manifest_chain_cache_scope()
    try:
        return _run_verify_cached(
            manifest_dir=manifest_dir,
            project_root=project_root,
            allow_empty=allow_empty,
            fail_fast=fail_fast,
            check_assertions=check_assertions,
            check_stubs=check_stubs,
            fail_on_warnings=fail_on_warnings,
            require_worktree_scope=require_worktree_scope,
            require_changed_scope=require_changed_scope,
            since=since,
            base_ref=base_ref,
            include_tests=include_tests,
            test_jobs=test_jobs,
            require_plan_lock=require_plan_lock,
            require_red_evidence=require_red_evidence,
            artifact_coverage=artifact_coverage,
            knockout=knockout,
            knockout_limit=knockout_limit,
            knockout_allow_dirty=knockout_allow_dirty,
        )
    finally:
        _exit_manifest_chain_cache_scope(chain_outermost)


def _run_verify_cached(
    *,
    manifest_dir: str,
    project_root: Union[str, Path],
    allow_empty: bool = False,
    fail_fast: bool = True,
    check_assertions: bool = True,
    check_stubs: bool = True,
    fail_on_warnings: bool = True,
    require_worktree_scope: bool = False,
    require_changed_scope: bool = False,
    since: str | None = None,
    base_ref: str | None = None,
    include_tests: bool = False,
    test_jobs: int = 1,
    require_plan_lock: bool = False,
    require_red_evidence: bool = False,
    artifact_coverage: bool = False,
    knockout: bool = False,
    knockout_limit: int | None = None,
    knockout_allow_dirty: bool = False,
) -> VerificationResult:
    from maid_runner.core.types import ValidationMode
    from maid_runner.core.validate import ValidationEngine

    started = time.monotonic()
    root = Path(project_root)
    engine = ValidationEngine(project_root=root)
    stages: list[VerificationStageResult] = []

    with engine.validation_cache_scope():
        stages.append(
            _validation_stage(
                "schema",
                engine,
                manifest_dir,
                ValidationMode.SCHEMA,
                project_root=root,
                allow_empty=allow_empty,
                fail_on_warnings=fail_on_warnings,
            )
        )
        if not _should_continue(stages[-1], fail_fast):
            return _verification_result(stages, started)

        stages.append(
            _validation_stage(
                "behavioral",
                engine,
                manifest_dir,
                ValidationMode.BEHAVIORAL,
                project_root=root,
                allow_empty=allow_empty,
                check_assertions=check_assertions,
                fail_on_warnings=fail_on_warnings,
            )
        )
        if not _should_continue(stages[-1], fail_fast):
            return _verification_result(stages, started)

        stages.append(
            _validation_stage(
                "implementation",
                engine,
                manifest_dir,
                ValidationMode.IMPLEMENTATION,
                project_root=root,
                allow_empty=allow_empty,
                check_stubs=check_stubs,
                fail_on_warnings=fail_on_warnings,
            )
        )
        if not _should_continue(stages[-1], fail_fast):
            return _verification_result(stages, started)

        if artifact_coverage:
            stages.append(_artifact_coverage_stage(root, manifest_dir))
            if not _should_continue(stages[-1], fail_fast):
                return _verification_result(stages, started)

        if knockout:
            stages.append(
                _knockout_stage(
                    root,
                    manifest_dir,
                    limit=knockout_limit,
                    allow_dirty=knockout_allow_dirty,
                )
            )
            if not _should_continue(stages[-1], fail_fast):
                return _verification_result(stages, started)

        if _allow_empty_without_active_manifests(root, manifest_dir, allow_empty):
            skip_message = "Skipped because --allow-empty found no active manifests"
            stages.append(_skipped_stage("coherence", skip_message))
            stages.append(_skipped_stage("file_tracking", skip_message))
            if require_worktree_scope:
                stages.append(_worktree_scope_stage(root, manifest_dir, include_tests))
                if not _should_continue(stages[-1], fail_fast):
                    return _verification_result(stages, started)
            elif _git_metadata_available(root):
                stages.append(_skipped_stage("worktree_scope", skip_message))
            if require_changed_scope:
                stages.append(_skipped_stage("changed_scope", skip_message))
            stages.append(_skipped_stage("tests", skip_message))
            return _verification_result(stages, started)

        stages.append(_coherence_stage(root, manifest_dir))
        if not _should_continue(stages[-1], fail_fast):
            return _verification_result(stages, started)

        stages.append(_file_tracking_stage(root, manifest_dir, engine))
        if not _should_continue(stages[-1], fail_fast):
            return _verification_result(stages, started)

        if require_plan_lock or require_red_evidence:
            stages.append(
                _plan_lock_stage(
                    root,
                    manifest_dir,
                    since=since,
                    base_ref=base_ref,
                    require_plan_lock=require_plan_lock,
                    require_red_evidence=require_red_evidence,
                )
            )
            if not _should_continue(stages[-1], fail_fast):
                return _verification_result(stages, started)

        if require_worktree_scope or _git_metadata_available(root):
            stages.append(_worktree_scope_stage(root, manifest_dir, include_tests))
            if not _should_continue(stages[-1], fail_fast):
                return _verification_result(stages, started)

        if require_changed_scope:
            stages.append(
                _changed_scope_stage(root, manifest_dir, since, base_ref, include_tests)
            )
            if not _should_continue(stages[-1], fail_fast):
                return _verification_result(stages, started)

        stages.append(_tests_stage(root, manifest_dir, fail_fast, test_jobs=test_jobs))

        return _verification_result(stages, started)


def _validation_stage(
    name: str,
    engine,
    manifest_dir: str,
    mode,
    *,
    project_root: Path,
    allow_empty: bool,
    check_assertions: bool = False,
    check_stubs: bool = False,
    fail_on_warnings: bool = False,
) -> VerificationStageResult:
    started = time.monotonic()
    try:
        result = engine.validate_all(
            manifest_dir,
            mode=mode,
            allow_empty=allow_empty,
            check_assertions=check_assertions,
            check_stubs=check_stubs,
            fail_on_warnings=False,
        )
        return VerificationStageResult(
            name=name,
            success=result.success
            and not _has_blocking_validation_warnings(
                result,
                project_root=project_root,
                fail_on_warnings=fail_on_warnings,
            ),
            _duration_ms=_elapsed_ms(started),
            _validation=result,
        )
    except Exception as exc:
        return _error_stage(name, started, exc)


def _coherence_stage(root: Path, manifest_dir: str) -> VerificationStageResult:
    started = time.monotonic()
    try:
        from maid_runner.coherence.engine import CoherenceEngine
        from maid_runner.core.chain import get_cached_manifest_chain

        chain = get_cached_manifest_chain(_manifest_dir_path(root, manifest_dir), root)
        result = CoherenceEngine().validate(chain, project_root=root)
        return VerificationStageResult(
            name="coherence",
            success=result.success,
            _duration_ms=_elapsed_ms(started),
            _coherence=result,
        )
    except Exception as exc:
        return _error_stage("coherence", started, exc)


def _file_tracking_stage(
    root: Path,
    manifest_dir: str,
    engine,
) -> VerificationStageResult:
    started = time.monotonic()
    try:
        from maid_runner.core.chain import get_cached_manifest_chain

        chain = get_cached_manifest_chain(_manifest_dir_path(root, manifest_dir), root)
        report = engine.run_file_tracking(chain)
        return VerificationStageResult(
            name="file_tracking",
            success=not report.undeclared and not report.registered,
            _duration_ms=_elapsed_ms(started),
            _file_tracking=report,
        )
    except Exception as exc:
        return _error_stage("file_tracking", started, exc)


def _artifact_coverage_stage(root: Path, manifest_dir: str) -> VerificationStageResult:
    started = time.monotonic()
    try:
        from maid_runner.cli.commands.validate import (
            _run_artifact_coverage_for_manifest_dir,
        )

        report = _run_artifact_coverage_for_manifest_dir(manifest_dir, root)
        return VerificationStageResult(
            name="artifact_coverage",
            success=report.success,
            _duration_ms=_elapsed_ms(started),
            _errors=(report,),
        )
    except Exception as exc:
        return _error_stage("artifact_coverage", started, exc)


def _knockout_stage(
    root: Path,
    manifest_dir: str,
    *,
    limit: int | None,
    allow_dirty: bool,
) -> VerificationStageResult:
    started = time.monotonic()
    try:
        from maid_runner.core.chain import get_cached_manifest_chain
        from maid_runner.core.knockout import KnockoutReport, run_knockout

        chain = get_cached_manifest_chain(_manifest_dir_path(root, manifest_dir), root)
        remaining = limit
        results = []
        errors = []
        for manifest in chain.active_manifests():
            if remaining is not None and remaining <= 0:
                break
            report = run_knockout(
                manifest,
                root,
                limit=remaining,
                allow_dirty=allow_dirty,
            )
            results.extend(report.results)
            errors.extend(report.errors)
            if remaining is not None:
                remaining -= max(len(report.results), len(report.errors))

        report = KnockoutReport(results=tuple(results), errors=tuple(errors))
        return VerificationStageResult(
            name="knockout",
            success=report.success,
            _duration_ms=_elapsed_ms(started),
            _errors=(report,),
        )
    except Exception as exc:
        return _error_stage("knockout", started, exc)


def _plan_lock_stage(
    root: Path,
    manifest_dir: str,
    *,
    since: str | None,
    base_ref: str | None,
    require_plan_lock: bool,
    require_red_evidence: bool,
) -> VerificationStageResult:
    started = time.monotonic()
    try:
        from maid_runner.core.chain import get_cached_manifest_chain
        from maid_runner.core.plan_lock import enforce_plan_locks

        chain = get_cached_manifest_chain(_manifest_dir_path(root, manifest_dir), root)
        changed_paths = _plan_lock_changed_paths(root, chain, since, base_ref)
        errors = enforce_plan_locks(
            chain,
            root,
            require_plan_lock=require_plan_lock,
            require_red_evidence=require_red_evidence,
            changed_paths=changed_paths,
        )
        return VerificationStageResult(
            name="plan_lock",
            success=not errors,
            _duration_ms=_elapsed_ms(started),
            _errors=tuple(errors),
        )
    except Exception as exc:
        return _error_stage("plan_lock", started, exc)


def _plan_lock_changed_paths(
    root: Path,
    chain,
    since: str | None,
    base_ref: str | None,
) -> tuple[str, ...] | None:
    from maid_runner.core.worktree import (
        changed_files,
        changed_files_since,
        resolve_changed_scope_baseline,
    )

    try:
        baseline = resolve_changed_scope_baseline(chain, since=since, base_ref=base_ref)
    except RuntimeError as exc:
        if since or base_ref:
            return None
        error = getattr(exc, "error", None)
        if getattr(error, "code", None) != ErrorCode.CHANGED_SCOPE_BASELINE_REQUIRED:
            return None
        try:
            return changed_files(root)
        except RuntimeError:
            return None

    try:
        return changed_files_since(root, baseline)
    except RuntimeError:
        return None


def _worktree_scope_stage(
    root: Path,
    manifest_dir: str,
    include_tests: bool,
) -> VerificationStageResult:
    started = time.monotonic()
    try:
        from maid_runner.core.chain import get_cached_manifest_chain
        from maid_runner.core.worktree import validate_worktree_scope

        chain = get_cached_manifest_chain(_manifest_dir_path(root, manifest_dir), root)
        errors = validate_worktree_scope(root, chain, include_tests=include_tests)
        return VerificationStageResult(
            name="worktree_scope",
            success=not errors,
            _duration_ms=_elapsed_ms(started),
            _errors=tuple(errors),
        )
    except Exception as exc:
        return _error_stage("worktree_scope", started, exc)


def _changed_scope_stage(
    root: Path,
    manifest_dir: str,
    since: str | None,
    base_ref: str | None,
    include_tests: bool,
) -> VerificationStageResult:
    started = time.monotonic()
    try:
        from maid_runner.core.chain import get_cached_manifest_chain
        from maid_runner.core.worktree import validate_changed_scope

        chain = get_cached_manifest_chain(_manifest_dir_path(root, manifest_dir), root)
        errors = validate_changed_scope(
            root,
            chain,
            since=since,
            base_ref=base_ref,
            include_tests=include_tests,
        )
        return VerificationStageResult(
            name="changed_scope",
            success=not errors,
            _duration_ms=_elapsed_ms(started),
            _errors=tuple(errors),
        )
    except Exception as exc:
        return _error_stage("changed_scope", started, exc)


def _tests_stage(
    root: Path,
    manifest_dir: str,
    fail_fast: bool,
    test_jobs: int = 1,
) -> VerificationStageResult:
    started = time.monotonic()
    try:
        from maid_runner.cli.commands.validate import (
            _validate_command_integrity_for_manifest_dir,
        )
        from maid_runner.core.test_runner import run_tests

        integrity_errors = _validate_command_integrity_for_manifest_dir(
            manifest_dir,
            project_root=root,
        )
        if integrity_errors:
            return VerificationStageResult(
                name="tests",
                success=False,
                _duration_ms=_elapsed_ms(started),
                _errors=tuple(integrity_errors),
            )

        result = run_tests(
            manifest_dir=manifest_dir,
            project_root=root,
            fail_fast=fail_fast,
            jobs=test_jobs,
        )
        return VerificationStageResult(
            name="tests",
            success=result.success,
            _duration_ms=_elapsed_ms(started),
            _tests=result,
        )
    except Exception as exc:
        return _error_stage("tests", started, exc)


def _has_blocking_validation_warnings(
    result,
    *,
    project_root: Path,
    fail_on_warnings: bool,
) -> bool:
    if not fail_on_warnings:
        return False

    for error in getattr(result, "chain_errors", ()):
        if _is_blocking_chain_warning(error, project_root):
            return True

    for validation in getattr(result, "results", ()):
        if not getattr(validation, "warnings", ()):
            continue
        if _validation_warnings_are_blocking(validation, project_root):
            return True

    warnings = getattr(result, "warnings", ())
    if warnings:
        manifest_path = getattr(result, "manifest_path", "")
        return _warnings_are_blocking(warnings, manifest_path, project_root)

    return False


def _is_blocking_chain_warning(error: ValidationError, project_root: Path) -> bool:
    if getattr(error, "severity", None) != Severity.WARNING:
        return False
    if getattr(error, "code", None) in _ADVISORY_CHAIN_WARNING_CODES:
        return False
    location = getattr(error, "location", None)
    manifest_path = getattr(location, "file", "") if location is not None else ""
    return _manifest_warnings_are_blocking(str(manifest_path), project_root)


def _manifest_warnings_are_blocking(manifest_path: str, project_root: Path) -> bool:
    try:
        from maid_runner.core.manifest import load_manifest

        path = Path(manifest_path)
        if not path.is_absolute():
            path = project_root / path
        manifest = load_manifest(path)
    except Exception:
        return True

    if (
        manifest.task_type is not None
        and manifest.task_type.value in _WARNING_ADVISORY_TASK_TYPES
    ):
        return False
    if manifest.created is None:
        return True
    return manifest.created >= _STRICT_WARNING_FAILURE_SINCE


def _validation_warnings_are_blocking(validation, project_root: Path) -> bool:
    return _warnings_are_blocking(
        getattr(validation, "warnings", ()),
        getattr(validation, "manifest_path", ""),
        project_root,
    )


def _warnings_are_blocking(
    warnings,
    manifest_path: str,
    project_root: Path,
) -> bool:
    blocking_warnings = [
        warning for warning in warnings if not _warning_is_advisory(warning)
    ]
    return bool(blocking_warnings) and _manifest_warnings_are_blocking(
        manifest_path,
        project_root,
    )


def _warning_is_advisory(warning) -> bool:
    code = getattr(warning, "code", None)
    if code in _ADVISORY_WARNING_CODES:
        return True
    if code == ErrorCode.STUB_FUNCTION_DETECTED:
        return _is_base_validator_default_hook_stub_warning(warning)
    return False


def _is_base_validator_default_hook_stub_warning(warning) -> bool:
    location = getattr(warning, "location", None)
    location_file = str(getattr(location, "file", "") or "").replace("\\", "/")
    if location_file != "maid_runner/validators/base.py":
        return False

    message = str(getattr(warning, "message", ""))
    match = _STUB_WARNING_FUNCTION_RE.search(message)
    if match is None:
        return False

    default_hook_names = {
        f"BaseValidator.{hook_name}" for hook_name in _BASE_VALIDATOR_DEFAULT_HOOK_STUBS
    }
    return match.group(1) in default_hook_names


def _error_stage(
    name: str,
    started: float,
    exc: Exception,
) -> VerificationStageResult:
    return VerificationStageResult(
        name=name,
        success=False,
        _duration_ms=_elapsed_ms(started),
        _errors=(str(exc),),
    )


def _skipped_stage(name: str, message: str) -> VerificationStageResult:
    return VerificationStageResult(name=name, success=True, _errors=(message,))


def _allow_empty_without_active_manifests(
    root: Path,
    manifest_dir: str,
    allow_empty: bool,
) -> bool:
    if not allow_empty:
        return False

    manifest_path = _manifest_dir_path(root, manifest_dir)
    if not manifest_path.exists():
        return True

    try:
        from maid_runner.core.chain import get_cached_manifest_chain

        chain = get_cached_manifest_chain(manifest_path, root)
        return not chain.active_manifests() and not chain.load_errors
    except Exception:
        return False


def _should_continue(stage: VerificationStageResult, fail_fast: bool) -> bool:
    return stage.success or not fail_fast


def _verification_result(
    stages: list[VerificationStageResult],
    started: float,
) -> VerificationResult:
    return VerificationResult(stages=tuple(stages), duration_ms=_elapsed_ms(started))


def _result_success(result: VerificationResult) -> bool:
    return all(stage.success for stage in result.stages)


def _elapsed_ms(started: float) -> float:
    return (time.monotonic() - started) * 1000


def _manifest_dir_path(root: Path, manifest_dir: str) -> Path:
    path = Path(manifest_dir)
    if path.is_absolute():
        return path
    return root / path


def _git_metadata_available(root: Path) -> bool:
    try:
        result = subprocess.run(
            ["git", "rev-parse", "--is-inside-work-tree"],
            cwd=root,
            capture_output=True,
            text=True,
            timeout=10,
        )
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return False
    return result.returncode == 0 and result.stdout.strip() == "true"
