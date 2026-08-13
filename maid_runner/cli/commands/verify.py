"""CLI handler for 'maid verify' command."""

from __future__ import annotations

import argparse
import json
import subprocess
import time
from collections.abc import Iterable, Sequence
from dataclasses import replace
from pathlib import Path
from typing import TYPE_CHECKING, Union

from maid_runner.cli.commands._format import (
    format_verify_result,
    format_verify_summary,
    print_error,
)
from maid_runner.core.result import (
    ErrorCode,
    Location,
    ValidationError,
    Severity,
    VerificationResult,
    VerificationStageResult,
)

if TYPE_CHECKING:
    from maid_runner.core.knockout import KnockoutReport
    from maid_runner.core.runtime_evidence import (
        RuntimeEvidenceBundle,
        RuntimeEvidenceRun,
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


def cmd_verify(args: argparse.Namespace) -> int:
    json_mode = getattr(args, "json", False)
    profile_report: str | None = None
    try:
        from maid_runner.core.verify_profiles import apply_verify_profile

        profile_report = apply_verify_profile(args)
        if profile_report and not json_mode:
            # Printed before any early return so a failing run still discloses
            # which gates the profile set. In JSON mode the report is injected
            # into the payload instead, to keep stdout a single document.
            print(profile_report)

        advisory = getattr(args, "advisory", False)
        strict_preview = getattr(args, "strict_preview", False)
        if strict_preview and advisory:
            print_error(
                _attribute_to_profile(
                    "--strict-preview and --advisory request contradictory gate sets",
                    report=profile_report,
                    json_mode=json_mode,
                ),
                json_mode=json_mode,
            )
            return 2
        fail_on_warnings = (
            not advisory
            or getattr(args, "strict", False)
            or getattr(args, "fail_on_warnings", False)
            or strict_preview
        )
        from maid_runner.core.config import load_config

        execution_config = load_config(".").test_execution
        jobs_explicit = getattr(args, "test_jobs_explicit", None)
        test_jobs = (
            execution_config.command_jobs
            if jobs_explicit is False
            else getattr(args, "test_jobs", 1)
        )
        workers_explicit = getattr(args, "pytest_workers_explicit", None)
        pytest_workers = (
            None if workers_explicit is False else getattr(args, "pytest_workers", None)
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
            changed_scope_explicit=getattr(args, "changed_scope_explicit", False),
            since=getattr(args, "since", None),
            base_ref=getattr(args, "base_ref", None),
            file_tracking_scope=getattr(args, "file_tracking_scope", "repository"),
            fail_on_scope_only=getattr(args, "fail_on_scope_only", False),
            include_tests=getattr(args, "include_tests", False),
            test_jobs=test_jobs,
            pytest_workers=pytest_workers,
            test_scope=getattr(args, "test_scope", "repository"),
            require_plan_lock=getattr(args, "require_plan_lock", False),
            require_red_evidence=getattr(args, "require_red_evidence", False),
            plan_lock_scope=getattr(args, "plan_lock_scope", "repository"),
            artifact_coverage=getattr(args, "artifact_coverage", False)
            or strict_preview,
            knockout=getattr(args, "knockout", False),
            knockout_limit=getattr(args, "knockout_limit", None),
            knockout_allow_dirty=getattr(args, "knockout_allow_dirty", False),
            no_cache=getattr(args, "no_cache", False),
        )
        delivery_provenance = None
        delivered_ref = getattr(args, "delivered", None)
        attestation_path = getattr(args, "attestation", None)
        if delivered_ref is not None or attestation_path is not None:
            delivery_stage, delivery_provenance = _delivery_attestation_stage(
                delivered_ref=delivered_ref,
                attestation_path=attestation_path,
                project_root=Path("."),
            )
            result = VerificationResult(
                stages=(*result.stages, delivery_stage),
                duration_ms=result.duration_ms,
            )
        formatter = (
            format_verify_summary
            if getattr(args, "summary", False)
            else format_verify_result
        )
        output = _mark_profile_output(
            _mark_strict_preview_output(
                formatter(result, json_mode=json_mode),
                enabled=strict_preview,
                json_mode=json_mode,
            ),
            report=profile_report,
            json_mode=json_mode,
        )
        if json_mode and delivery_provenance is not None:
            payload = json.loads(output) if output else {}
            payload["delivery_provenance"] = delivery_provenance
            output = json.dumps(payload, indent=2)
        print(output)
        exit_code = 0 if _result_success(result) else 1
        if not _write_sarif_report_if_requested(args, result):
            return 2
        return _finalize_packet(args, exit_code, result)
    except Exception as exc:
        print_error(
            _attribute_to_profile(str(exc), report=profile_report, json_mode=json_mode),
            json_mode=json_mode,
        )
        return 2


def _delivery_attestation_stage(
    *,
    delivered_ref: str | None,
    attestation_path: str | None,
    project_root: Path,
) -> tuple[VerificationStageResult, dict | None]:
    from maid_runner.core.delivery_attestation import (
        render_provenance_record,
        verify_delivered_attestation,
    )

    started = time.monotonic()
    if delivered_ref is None or attestation_path is None:
        error = ValidationError(
            code=ErrorCode.DELIVERY_ATTESTATION_INVALID,
            message="--delivered and --attestation must be supplied together",
            severity=Severity.ERROR,
            suggestion=(
                "Supply a named destination branch and a provenance record "
                "generated from the validated commit."
            ),
        )
        return (
            VerificationStageResult(
                name="delivery_attestation",
                success=False,
                _duration_ms=_elapsed_ms(started),
                _errors=(error,),
            ),
            None,
        )

    proof_path = Path(attestation_path)
    try:
        attestation = json.loads(
            proof_path.read_bytes().decode("utf-8"),
            object_pairs_hook=_reject_duplicate_json_keys,
            parse_constant=_reject_nonstandard_json_constant,
        )
    except (OSError, UnicodeError, json.JSONDecodeError, ValueError) as exc:
        error = ValidationError(
            code=ErrorCode.DELIVERY_ATTESTATION_INVALID,
            message=f"delivery attestation is unreadable at {proof_path}: {exc}",
            severity=Severity.ERROR,
            location=Location(file=str(proof_path)),
            suggestion=(
                "Regenerate the delivery attestation from the clean committed "
                "tree that passed verification."
            ),
        )
        return (
            VerificationStageResult(
                name="delivery_attestation",
                success=False,
                _duration_ms=_elapsed_ms(started),
                _errors=(error,),
            ),
            None,
        )

    verification = verify_delivered_attestation(
        attestation,
        project_root,
        delivered_ref,
    )
    errors = tuple(
        ValidationError(
            code=ErrorCode(item["code"]),
            message=item["message"],
            severity=Severity.ERROR,
            location=Location(file=str(proof_path)),
            suggestion=(
                "Regenerate the attestation from the validated commit."
                if item["code"] == ErrorCode.DELIVERY_ATTESTATION_INVALID.value
                else "Inspect the covered path changes and destination branch."
            ),
        )
        for item in verification["errors"]
    )
    provenance = None
    try:
        provenance = json.loads(render_provenance_record(attestation, verification))
    except ValueError:
        pass
    return (
        VerificationStageResult(
            name="delivery_attestation",
            success=verification["success"],
            _duration_ms=_elapsed_ms(started),
            _errors=errors,
        ),
        provenance,
    )


def _reject_duplicate_json_keys(
    pairs: list[tuple[str, object]],
) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"duplicate JSON key in delivery attestation: {key}")
        result[key] = value
    return result


def _reject_nonstandard_json_constant(value: str) -> object:
    raise ValueError(f"non-standard JSON constant in delivery attestation: {value}")


def _attribute_to_profile(
    message: str,
    *,
    report: str | None,
    json_mode: bool,
) -> str:
    """Attribute an error to the profile that set the flags involved.

    Failures are the path where a reader most needs to know a flag came from a
    profile rather than their own command line. Non-JSON runs already printed
    the report before the gates, so only JSON needs it folded into the message.
    """
    if not report or not json_mode:
        return message
    return f"{message} ({report})"


def _mark_strict_preview_output(
    output: str,
    *,
    enabled: bool,
    json_mode: bool,
) -> str:
    if not enabled:
        return output
    if json_mode:
        payload = json.loads(output) if output else {}
        payload["strict_preview"] = True
        return json.dumps(payload, indent=2)
    if not output:
        return "[strict-preview]"
    return f"[strict-preview] {output}"


def _mark_profile_output(
    output: str,
    *,
    report: str | None,
    json_mode: bool,
) -> str:
    if not report:
        return output
    if json_mode:
        payload = json.loads(output) if output else {}
        payload["profile"] = report
        return json.dumps(payload, indent=2)
    # Non-JSON runs already printed the report ahead of the gates.
    return output


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
            return 2
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
    fail_on_scope_only: bool = False,
) -> VerificationResult:
    return _run_verify(
        manifest_dir=manifest_dir,
        project_root=project_root,
        check_assertions=True,
        check_stubs=True,
        fail_on_warnings=True,
        fail_on_scope_only=fail_on_scope_only,
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
    changed_scope_explicit: bool = False,
    since: str | None = None,
    base_ref: str | None = None,
    file_tracking_scope: str = "repository",
    fail_on_scope_only: bool = False,
    include_tests: bool = False,
    test_jobs: int = 1,
    pytest_workers: Union[int, str, None] = None,
    test_scope: str = "repository",
    require_plan_lock: bool = False,
    require_red_evidence: bool = False,
    plan_lock_scope: str = "repository",
    artifact_coverage: bool = False,
    knockout: bool = False,
    knockout_limit: int | None = None,
    knockout_allow_dirty: bool = False,
    no_cache: bool = False,
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
            changed_scope_explicit=changed_scope_explicit,
            since=since,
            base_ref=base_ref,
            file_tracking_scope=file_tracking_scope,
            fail_on_scope_only=fail_on_scope_only,
            include_tests=include_tests,
            test_jobs=test_jobs,
            pytest_workers=pytest_workers,
            test_scope=test_scope,
            require_plan_lock=require_plan_lock,
            require_red_evidence=require_red_evidence,
            plan_lock_scope=plan_lock_scope,
            artifact_coverage=artifact_coverage,
            knockout=knockout,
            knockout_limit=knockout_limit,
            knockout_allow_dirty=knockout_allow_dirty,
            no_cache=no_cache,
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
    changed_scope_explicit: bool = False,
    since: str | None = None,
    base_ref: str | None = None,
    file_tracking_scope: str = "repository",
    fail_on_scope_only: bool = False,
    include_tests: bool = False,
    test_jobs: int = 1,
    pytest_workers: int | str | None = None,
    test_scope: str = "repository",
    require_plan_lock: bool = False,
    require_red_evidence: bool = False,
    plan_lock_scope: str = "repository",
    artifact_coverage: bool = False,
    knockout: bool = False,
    knockout_limit: int | None = None,
    knockout_allow_dirty: bool = False,
    no_cache: bool = False,
) -> VerificationResult:
    from maid_runner.core.types import ValidationMode
    from maid_runner.core.validate import ValidationEngine

    started = time.monotonic()
    root = Path(project_root)
    engine = ValidationEngine(project_root=root)
    stages: list[VerificationStageResult] = []
    evidence: RuntimeEvidenceBundle | None = None
    evidence_run: RuntimeEvidenceRun | None = None

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

        test_manifest_paths = None
        test_scope_widening: list[ValidationError] = []
        if _should_scope_tests_to_task(
            test_scope=test_scope,
            file_tracking_scope=file_tracking_scope,
            plan_lock_scope=plan_lock_scope,
        ):
            test_manifest_paths = _task_scoped_test_manifest_paths(
                root,
                manifest_dir,
                since,
                base_ref,
                widening=test_scope_widening,
            )

        if artifact_coverage:
            coverage_started = time.monotonic()
            try:
                cached_report = None
                if not no_cache:
                    cached_report = _load_artifact_coverage_cache(
                        root,
                        pytest_workers=pytest_workers,
                        manifest_paths=test_manifest_paths,
                    )
                if cached_report is not None:
                    coverage_stage = VerificationStageResult(
                        name="artifact_coverage",
                        success=cached_report.success,
                        _duration_ms=_elapsed_ms(coverage_started),
                        _errors=(cached_report,),
                    )
                else:
                    evidence_run = _collect_artifact_coverage_evidence_run(
                        root,
                        manifest_dir,
                        test_jobs=test_jobs,
                        pytest_workers=pytest_workers,
                        manifest_paths=test_manifest_paths,
                    )
                    evidence = None if evidence_run is None else evidence_run.evidence
                    coverage_stage = _artifact_coverage_stage(
                        root,
                        manifest_dir,
                        evidence=evidence,
                        manifest_paths=test_manifest_paths,
                    )
                    coverage_stage = replace(
                        coverage_stage,
                        _duration_ms=_elapsed_ms(coverage_started),
                    )
                    live_report = _coverage_report_from_stage(coverage_stage)
                    if live_report is not None and not no_cache:
                        _store_artifact_coverage_cache(
                            root,
                            live_report,
                            pytest_workers=pytest_workers,
                            manifest_paths=test_manifest_paths,
                        )
            except Exception as exc:
                coverage_stage = _error_stage(
                    "artifact_coverage", coverage_started, exc
                )
            stages.append(coverage_stage)
            if not _should_continue(stages[-1], fail_fast):
                return _verification_result(stages, started)

        if knockout:
            stages.append(
                _knockout_stage(
                    root,
                    manifest_dir,
                    limit=knockout_limit,
                    allow_dirty=knockout_allow_dirty,
                    evidence=evidence,
                    manifest_paths=test_manifest_paths,
                    no_cache=no_cache,
                )
            )
            if not _should_continue(stages[-1], fail_fast):
                return _verification_result(stages, started)

        reuse_ordinary_tests = _should_reuse_ordinary_tests(
            evidence_run,
            _knockout_report_from_stage(stages[-1]) if knockout else None,
            root,
            manifest_dir,
            pytest_workers,
        )

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

        stages.append(
            _file_tracking_stage(
                root,
                manifest_dir,
                engine,
                scope=file_tracking_scope,
                fail_on_scope_only=fail_on_scope_only,
                since=since,
                base_ref=base_ref,
            )
        )
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
                    plan_lock_scope=plan_lock_scope,
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
                _changed_scope_stage(
                    root,
                    manifest_dir,
                    since,
                    base_ref,
                    include_tests,
                    allow_clean_tree_skip=(
                        not changed_scope_explicit
                        and since is None
                        and base_ref is None
                    ),
                )
            )
            if not _should_continue(stages[-1], fail_fast):
                return _verification_result(stages, started)

        tests_stage = _tests_stage(
            root,
            manifest_dir,
            fail_fast,
            test_jobs=test_jobs,
            pytest_workers=pytest_workers,
            manifest_paths=test_manifest_paths,
            evidence_run=evidence_run,
            reuse_ordinary_tests=reuse_ordinary_tests,
        )
        if test_scope_widening:
            if tests_stage._tests is not None:
                tests_stage = replace(
                    tests_stage,
                    _tests=replace(
                        tests_stage._tests,
                        chain_errors=[
                            *tests_stage._tests.chain_errors,
                            *test_scope_widening,
                        ],
                    ),
                )
            else:
                tests_stage = replace(
                    tests_stage,
                    _errors=(*tests_stage._errors, *test_scope_widening),
                )
        stages.append(tests_stage)

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
    *,
    scope: str = "repository",
    fail_on_scope_only: bool = False,
    since: str | None = None,
    base_ref: str | None = None,
) -> VerificationStageResult:
    started = time.monotonic()
    try:
        from maid_runner.core.chain import get_cached_manifest_chain
        from maid_runner.core._file_tracking import filter_file_tracking_report
        from maid_runner.core.worktree import (
            changed_files_since,
            resolve_changed_scope_baseline,
        )

        chain = get_cached_manifest_chain(_manifest_dir_path(root, manifest_dir), root)
        report = engine.run_file_tracking(chain)
        if scope == "task":
            try:
                baseline = resolve_changed_scope_baseline(
                    chain, since=since, base_ref=base_ref
                )
                task_paths = changed_files_since(root, baseline)
            except RuntimeError as exc:
                error = getattr(exc, "error", None)
                if error is None:
                    error = ValidationError(
                        code=ErrorCode.FILE_READ_ERROR,
                        message=str(exc),
                        severity=Severity.ERROR,
                    )
                return VerificationStageResult(
                    name="file_tracking",
                    success=False,
                    _duration_ms=_elapsed_ms(started),
                    _errors=(error,),
                )
            report = filter_file_tracking_report(report, task_paths)
        scope_error = None
        if fail_on_scope_only and report.scope_only:
            paths = ", ".join(entry.path for entry in report.scope_only)
            scope_error = ValidationError(
                code=ErrorCode.COHERENCE_BOUNDARY_VIOLATION,
                message=f"File tracking gate failed (scope-only: {paths})",
                severity=Severity.ERROR,
            )
        return VerificationStageResult(
            name="file_tracking",
            success=(
                not report.undeclared and not report.registered and scope_error is None
            ),
            _duration_ms=_elapsed_ms(started),
            _file_tracking=report,
            _errors=(scope_error,) if scope_error is not None else (),
        )
    except Exception as exc:
        return _error_stage("file_tracking", started, exc)


def _artifact_coverage_cache_key(
    root: Path,
    *,
    pytest_workers: int | str | None,
    manifest_paths: Sequence[str] | None,
) -> str:
    import hashlib

    from maid_runner import __version__
    from maid_runner.core.config import load_config
    from maid_runner.core.runtime_evidence import (
        _content_digest,
        _environment_identity,
    )

    environment = _environment_identity(("python", "-m", "pytest"), root)
    payload = {
        "content_digest": _content_digest(root),
        "runner_version": __version__,
        "evidence_mode": load_config(root).artifact_coverage.evidence_mode,
        "pytest_workers": pytest_workers,
        "manifest_paths": None if manifest_paths is None else list(manifest_paths),
        "environment": {
            "resolved_command_prefix": list(environment.resolved_command_prefix),
            "working_directory": environment.working_directory,
            "python_identity": environment.python_identity,
            "pytest_version": environment.pytest_version,
            "coverage_version": environment.coverage_version,
            "xdist_version": environment.xdist_version,
            "configuration_digest": environment.configuration_digest,
            "dependency_digest": environment.dependency_digest,
            "effective_environment_digest": environment.effective_environment_digest,
        },
    }
    return hashlib.sha256(
        json.dumps(payload, sort_keys=True, default=str).encode()
    ).hexdigest()


def _artifact_coverage_cache_path(root: Path, cache_key: str) -> Path:
    return (
        root / ".maid" / "cache" / "artifact-coverage-evidence-v1" / f"{cache_key}.json"
    )


def _coverage_report_from_stage(stage: VerificationStageResult):
    for item in stage._errors:
        if hasattr(item, "findings") and hasattr(item, "to_dict"):
            return item
    return None


def _load_artifact_coverage_cache(
    root: Path,
    *,
    pytest_workers: int | str | None,
    manifest_paths: Sequence[str] | None,
):
    path = _artifact_coverage_cache_path(
        root,
        _artifact_coverage_cache_key(
            root,
            pytest_workers=pytest_workers,
            manifest_paths=manifest_paths,
        ),
    )
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    if not isinstance(payload, dict):
        return None
    return _artifact_coverage_report_from_cache(payload)


def _store_artifact_coverage_cache(
    root: Path,
    report,
    *,
    pytest_workers: int | str | None,
    manifest_paths: Sequence[str] | None,
) -> None:
    path = _artifact_coverage_cache_path(
        root,
        _artifact_coverage_cache_key(
            root,
            pytest_workers=pytest_workers,
            manifest_paths=manifest_paths,
        ),
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(report.to_dict(), indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def _artifact_coverage_report_from_cache(payload: dict):
    from maid_runner.core.artifact_coverage import (
        ArtifactCoverageExecutionSummary,
        ArtifactCoverageFinding,
        ArtifactCoverageReport,
    )

    findings = tuple(
        ArtifactCoverageFinding(
            artifact_name=item["artifact_name"],
            artifact_kind=item["artifact_kind"],
            parent_class=item.get("parent_class"),
            file_path=item["file_path"],
            executed=bool(item["executed"]),
        )
        for item in payload.get("findings", ())
        if isinstance(item, dict)
    )
    errors = tuple(
        _validation_error_from_cache(item)
        for item in payload.get("errors", ())
        if isinstance(item, dict)
    )
    execution = None
    raw_execution = payload.get("execution")
    if isinstance(raw_execution, dict):
        execution = ArtifactCoverageExecutionSummary(
            command_count=int(raw_execution["command_count"]),
            isolated_count=int(raw_execution["isolated_count"]),
            serial_count=int(raw_execution["serial_count"]),
            lane_count=int(raw_execution["lane_count"]),
        )
    return ArtifactCoverageReport(
        findings=findings,
        errors=errors,
        execution=execution,
        provenance=payload.get("provenance"),
        cache_hit=True,
    )


def _validation_error_from_cache(payload: dict) -> ValidationError:
    location = None
    raw_location = payload.get("location")
    if isinstance(raw_location, dict) and raw_location.get("file"):
        location = Location(
            file=str(raw_location["file"]),
            line=raw_location.get("line"),
            column=raw_location.get("column"),
        )
    return ValidationError(
        code=ErrorCode(payload["code"]),
        message=str(payload.get("message", "")),
        severity=Severity(payload.get("severity", Severity.ERROR.value)),
        location=location,
        suggestion=payload.get("suggestion"),
    )


def _collect_artifact_coverage_evidence(
    root: Path,
    manifest_dir: str,
    test_jobs: int = 1,
    pytest_workers: Union[int, str, None] = None,
    manifest_paths: Sequence[str] | None = None,
) -> RuntimeEvidenceBundle | None:
    """Collect grouped coverage evidence, or select the complete legacy path."""
    run = _collect_artifact_coverage_evidence_run(
        root,
        manifest_dir,
        test_jobs=test_jobs,
        pytest_workers=pytest_workers,
        manifest_paths=manifest_paths,
    )
    return None if run is None else run.evidence


def _collect_artifact_coverage_evidence_run(
    root: Path,
    manifest_dir: str,
    test_jobs: int = 1,
    pytest_workers: Union[int, str, None] = None,
    manifest_paths: Sequence[str] | None = None,
) -> RuntimeEvidenceRun | None:
    """Collect grouped coverage evidence, or select the complete legacy path."""
    del test_jobs
    try:
        from maid_runner.core.artifact_coverage import _coverage_targets
        from maid_runner.core.chain import get_cached_manifest_chain
        from maid_runner.core.runtime_evidence import (
            _content_digest,
            collect_runtime_evidence,
            grouped_evidence_preflight,
        )
        from maid_runner.core.config import load_config

        evidence_mode = load_config(root).artifact_coverage.evidence_mode
        if not grouped_evidence_preflight(root, evidence_mode):
            return None
        chain = get_cached_manifest_chain(_manifest_dir_path(root, manifest_dir), root)
        active = chain.active_manifests()
        if manifest_paths is not None:
            wanted = {Path(path).as_posix() for path in manifest_paths}
            active = tuple(
                manifest
                for manifest in active
                if manifest.source_path in wanted
                or Path(manifest.source_path).as_posix() in wanted
            )
        coverage_manifests = tuple(
            manifest for manifest in active if _coverage_targets(manifest, root)
        )
        if not coverage_manifests:
            return None
        pre_execution_digest = _content_digest(root)
    except Exception:
        return None

    try:
        run = collect_runtime_evidence(
            coverage_manifests,
            root,
            pytest_workers=pytest_workers,
        )
    except Exception as collection_error:
        # Evidence is an optimization only. The exact legacy coverage stage is
        # safe only when preparation left the project bytes unchanged.
        try:
            failed_collection_digest = _content_digest(root)
        except Exception as digest_error:
            raise RuntimeError(
                "Artifact coverage evidence preparation failed and the current "
                "project content identity could not be verified"
            ) from digest_error
        if failed_collection_digest != pre_execution_digest:
            raise RuntimeError(
                "Artifact coverage evidence preparation changed project content; "
                "the pre-execution coverage baseline cannot be replayed safely"
            ) from collection_error
        return None

    try:
        post_execution_digest = _content_digest(root)
    except Exception as exc:
        raise RuntimeError(
            "Artifact coverage evidence changed project state and its current "
            "content identity could not be verified"
        ) from exc
    if post_execution_digest != pre_execution_digest:
        raise RuntimeError(
            "Artifact coverage evidence command changed project content; the "
            "pre-execution coverage baseline cannot be replayed safely"
        )
    return run


def _artifact_coverage_stage(
    root: Path,
    manifest_dir: str,
    evidence: RuntimeEvidenceBundle | None = None,
    manifest_paths: Sequence[str] | None = None,
) -> VerificationStageResult:
    started = time.monotonic()
    try:
        from maid_runner.cli.commands.validate import (
            _merge_artifact_coverage_reports,
            _run_artifact_coverage_by_manifest,
        )

        report = _merge_artifact_coverage_reports(
            _run_artifact_coverage_by_manifest(
                manifest_dir,
                root,
                evidence=evidence,
                manifest_paths=manifest_paths,
            ).values()
        )
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
    evidence: RuntimeEvidenceBundle | None = None,
    manifest_paths: Sequence[str] | None = None,
    no_cache: bool = False,
) -> VerificationStageResult:
    started = time.monotonic()
    try:
        from maid_runner.core.chain import get_cached_manifest_chain
        from maid_runner.core.knockout import (
            KnockoutReport,
            run_knockout_batch,
        )
        from maid_runner.core.config import load_config

        chain = get_cached_manifest_chain(_manifest_dir_path(root, manifest_dir), root)
        config = load_config(root)
        selected = chain.active_manifests()
        if manifest_paths is not None:
            wanted = {Path(path).as_posix() for path in manifest_paths}
            selected = tuple(
                manifest
                for manifest in selected
                if manifest.source_path in wanted
                or Path(manifest.source_path).as_posix() in wanted
            )
        results = []
        errors = []
        reports = run_knockout_batch(
            selected,
            root,
            evidence=evidence,
            limit=limit,
            allow_dirty=allow_dirty,
            jobs=config.knockout_execution.jobs,
            max_processes=config.test_execution.max_processes,
            no_cache=no_cache,
        )
        for report in reports.values():
            results.extend(report.results)
            errors.extend(report.errors)

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
    plan_lock_scope: str,
) -> VerificationStageResult:
    started = time.monotonic()
    try:
        from maid_runner.core.chain import get_cached_manifest_chain
        from maid_runner.core.plan_lock import enforce_plan_locks

        chain = get_cached_manifest_chain(_manifest_dir_path(root, manifest_dir), root)
        widening: list[ValidationError] = []
        changed_paths = _plan_lock_changed_paths(
            root, chain, since, base_ref, widening=widening
        )
        errors = enforce_plan_locks(
            chain,
            root,
            require_plan_lock=require_plan_lock,
            require_red_evidence=require_red_evidence,
            changed_paths=changed_paths,
            plan_lock_scope=plan_lock_scope,
        )
        findings = [*widening, *errors]
        blocking = [
            finding
            for finding in findings
            if getattr(finding, "severity", Severity.ERROR) == Severity.ERROR
        ]
        return VerificationStageResult(
            name="plan_lock",
            success=not blocking,
            _duration_ms=_elapsed_ms(started),
            _errors=tuple(findings),
        )
    except Exception as exc:
        return _error_stage("plan_lock", started, exc)


def _plan_lock_changed_paths(
    root: Path,
    chain,
    since: str | None,
    base_ref: str | None,
    *,
    widening: "list[ValidationError] | None" = None,
) -> tuple[str, ...] | None:
    """Resolve the plan-lock task window, disclosing any widening to full scope.

    Returning None means "enforce every active manifest". That fail-closed
    escalation is deliberate (067-07), but it must never be silent: each path
    that returns None records a PLAN_LOCK_SCOPE_WIDENED warning naming the
    cause, so the resulting findings are actionable instead of an
    unattributable storm.
    """
    from maid_runner.core.worktree import (
        changed_files,
        changed_files_since,
        describe_changed_scope_baselines,
        resolve_changed_scope_baseline,
    )

    def _widened(detail: str, suggestion: str) -> None:
        if widening is None:
            return
        widening.append(
            ValidationError(
                code=ErrorCode.PLAN_LOCK_SCOPE_WIDENED,
                message=(
                    "PLAN_LOCK_SCOPE_WIDENED: plan-lock enforcement widened from "
                    "the task window to every active manifest because "
                    f"{detail}"
                ),
                severity=Severity.WARNING,
                suggestion=suggestion,
            )
        )

    try:
        baseline = resolve_changed_scope_baseline(chain, since=since, base_ref=base_ref)
    except RuntimeError as exc:
        if since or base_ref:
            _widened(
                f"the requested baseline could not be resolved: {exc}",
                "Pass a baseline this checkout can resolve.",
            )
            return None
        error = getattr(exc, "error", None)
        if getattr(error, "code", None) != ErrorCode.CHANGED_SCOPE_BASELINE_REQUIRED:
            _widened(
                _baseline_conflict_detail(chain, exc, describe_changed_scope_baselines),
                "Make the listed manifests agree on metadata.maid_task_base, or "
                "pass --since/--base-ref for this run.",
            )
            return None
        try:
            return changed_files(root)
        except RuntimeError as fallback_exc:
            _widened(
                f"the working tree could not be read: {fallback_exc}",
                "Restore git metadata so verify can scope to the current task.",
            )
            return None

    try:
        return changed_files_since(root, baseline)
    except RuntimeError as exc:
        _widened(
            f"baseline '{baseline.commitish}' could not be compared: {exc}",
            "Pass a baseline commit this checkout contains.",
        )
        return None


def _should_scope_tests_to_task(
    *,
    test_scope: str = "repository",
    file_tracking_scope: str = "repository",
    plan_lock_scope: str = "repository",
) -> bool:
    return (
        test_scope == "task"
        or file_tracking_scope == "task"
        or plan_lock_scope == "task"
    )


def _task_scoped_test_manifest_paths(
    root: Path,
    manifest_dir: str,
    since: str | None,
    base_ref: str | None,
    *,
    widening: "list[ValidationError] | None" = None,
) -> tuple[str, ...] | None:
    from maid_runner.core.chain import get_cached_manifest_chain

    chain = get_cached_manifest_chain(_manifest_dir_path(root, manifest_dir), root)
    selection_widening: list[ValidationError] = []
    changed_paths = _plan_lock_changed_paths(
        root,
        chain,
        since,
        base_ref,
        widening=selection_widening,
    )
    if widening is not None:
        widening.extend(
            replace(
                finding,
                message=finding.message.replace(
                    "plan-lock enforcement", "tests-stage selection"
                ),
            )
            for finding in selection_widening
        )
    if changed_paths is None:
        return None

    changed = {_project_relative_path(path, root) for path in changed_paths}
    return tuple(
        manifest.source_path
        for manifest in chain.active_manifests()
        if _project_relative_path(manifest.source_path, root) in changed
    )


def _project_relative_path(path: str | Path, root: Path) -> str:
    candidate = Path(path)
    if candidate.is_absolute():
        try:
            candidate = candidate.relative_to(root.resolve())
        except ValueError:
            pass
    return candidate.as_posix()


def _baseline_conflict_detail(chain, exc: Exception, describe) -> str:
    """Name the manifests whose disagreement blocked baseline resolution."""
    try:
        declarations = describe(chain)
    except Exception as describe_exc:
        # Disclose the degraded message rather than quietly dropping to the
        # generic one; this helper exists to end silent fallbacks.
        return f"{exc} (manifest declarations unavailable: {describe_exc})"
    if not declarations:
        return str(exc)
    listed = ", ".join(
        f"{entry.manifest_path} declares {entry.commitish}" for entry in declarations
    )
    return f"{exc} ({listed})"


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
    *,
    allow_clean_tree_skip: bool,
) -> VerificationStageResult:
    started = time.monotonic()
    try:
        from maid_runner.core.chain import get_cached_manifest_chain
        from maid_runner.core.worktree import evaluate_changed_scope

        chain = get_cached_manifest_chain(_manifest_dir_path(root, manifest_dir), root)
        decision = evaluate_changed_scope(
            root,
            chain,
            since=since,
            base_ref=base_ref,
            include_tests=include_tests,
            allow_clean_tree_skip=allow_clean_tree_skip,
        )
        return VerificationStageResult(
            name="changed_scope",
            success=not decision.errors,
            skip_reason=decision.skip_reason,
            _duration_ms=_elapsed_ms(started),
            _errors=tuple(decision.errors),
        )
    except Exception as exc:
        return _error_stage("changed_scope", started, exc)


def _knockout_report_from_stage(stage: VerificationStageResult):
    from maid_runner.core.knockout import KnockoutReport

    for item in stage._errors:
        if isinstance(item, KnockoutReport):
            return item
    return None


def _should_reuse_ordinary_tests(
    evidence_run: RuntimeEvidenceRun | None,
    knockout_report: KnockoutReport | None,
    root: Path,
    manifest_dir: str,
    pytest_workers: int | str | None,
) -> bool:
    if evidence_run is None or knockout_report is None:
        return False
    if not knockout_report.results:
        return False
    if evidence_run.evidence.completeness.missing_worker_ids:
        return False
    from maid_runner.core.chain import get_cached_manifest_chain
    from maid_runner.core.runtime_evidence import runtime_evidence_is_current

    chain = get_cached_manifest_chain(_manifest_dir_path(root, manifest_dir), root)
    wanted = {item.identity.manifest_path for item in evidence_run.evidence.commands}
    manifests = tuple(
        manifest
        for manifest in chain.active_manifests()
        if manifest.source_path in wanted
    )
    return runtime_evidence_is_current(
        evidence_run.evidence,
        manifests,
        root,
        pytest_workers,
    )


def _partition_reused_test_commands(active, evidence_run: RuntimeEvidenceRun):
    from maid_runner.core.result import TestRunResult
    from maid_runner.core.test_runner import _collect_test_command_streams

    _, implementation_commands = _collect_test_command_streams(active)
    by_key = {
        (tuple(item.identity.command), item.identity.manifest_path): item
        for item in evidence_run.evidence.commands
    }
    path_by_slug = {manifest.slug: manifest.source_path for manifest in active}
    reused = []
    residual = []
    for command, slug in implementation_commands:
        item = by_key.get((tuple(command), path_by_slug.get(slug, "")))
        if item is None:
            residual.append((command, slug))
            continue
        reused.append(
            TestRunResult(
                manifest_slug=slug,
                command=tuple(command),
                exit_code=item.result.returncode,
                stdout=item.result.stdout,
                stderr=item.result.stderr,
                duration_ms=0.0,
            )
        )
    return reused, residual


def _tests_result_from_reused_evidence(
    active,
    evidence_run: RuntimeEvidenceRun,
    root: Path,
    fail_fast: bool,
    test_jobs: int,
    pytest_workers: int | str | None,
    chain_errors,
):
    from maid_runner.core.result import BatchTestResult
    from maid_runner.core.test_runner import _run_implementation_commands

    reused, residual = _partition_reused_test_commands(active, evidence_run)
    scheduling_notices = []
    passed = sum(item.success for item in reused)
    failed = len(reused) - passed
    results = list(reused)
    if residual:
        extra, extra_passed, extra_failed, early = _run_implementation_commands(
            residual,
            root,
            None,
            fail_fast,
            list(chain_errors),
            results,
            passed,
            failed,
            jobs=test_jobs,
            pytest_workers=pytest_workers,
            scheduling_notices=scheduling_notices,
        )
        if early is not None:
            return early
        results, passed, failed = extra, extra_passed, extra_failed
    return BatchTestResult(
        results=results,
        total=len(results),
        passed=passed,
        failed=failed,
        chain_errors=list(chain_errors),
        scheduling_notices=tuple(scheduling_notices),
    )


def _tests_stage(
    root: Path,
    manifest_dir: str,
    fail_fast: bool,
    test_jobs: int = 1,
    manifest_paths: Iterable[str | Path] | None = None,
    pytest_workers: int | str | None = None,
    evidence_run: RuntimeEvidenceRun | None = None,
    reuse_ordinary_tests: bool = False,
) -> VerificationStageResult:
    started = time.monotonic()
    try:
        from maid_runner.cli.commands.validate import (
            _validate_command_integrity_for_manifest_dir,
        )
        from maid_runner.core.test_runner import (
            _collect_test_command_streams,
            _run_implementation_commands,
            _validate_manifest_test_command_integrity,
            run_tests,
        )

        if manifest_paths is None:
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

            if reuse_ordinary_tests and evidence_run is not None:
                from maid_runner.core.chain import get_cached_manifest_chain

                chain = get_cached_manifest_chain(
                    _manifest_dir_path(root, manifest_dir), root
                )
                result = _tests_result_from_reused_evidence(
                    chain.active_manifests(),
                    evidence_run,
                    root,
                    fail_fast,
                    test_jobs,
                    pytest_workers,
                    chain.diagnostics(),
                )
            else:
                result = run_tests(
                    manifest_dir=manifest_dir,
                    project_root=root,
                    fail_fast=fail_fast,
                    jobs=test_jobs,
                    pytest_workers=pytest_workers,
                )
        else:
            from maid_runner.core.chain import get_cached_manifest_chain
            from maid_runner.core.result import BatchTestResult

            chain = get_cached_manifest_chain(
                _manifest_dir_path(root, manifest_dir), root
            )
            chain_errors = chain.diagnostics()
            if any(error.severity == Severity.ERROR for error in chain_errors):
                result = BatchTestResult(
                    results=[],
                    total=0,
                    passed=0,
                    failed=0,
                    chain_errors=chain_errors,
                )
                return VerificationStageResult(
                    name="tests",
                    success=result.success,
                    _duration_ms=_elapsed_ms(started),
                    _tests=result,
                )
            selected = {_project_relative_path(path, root) for path in manifest_paths}
            active = [
                manifest
                for manifest in chain.active_manifests()
                if _project_relative_path(manifest.source_path, root) in selected
            ]
            integrity_errors = _validate_manifest_test_command_integrity(active, root)
            if integrity_errors:
                return VerificationStageResult(
                    name="tests",
                    success=False,
                    _duration_ms=_elapsed_ms(started),
                    _errors=tuple([*chain_errors, *integrity_errors]),
                )
            if reuse_ordinary_tests and evidence_run is not None:
                result = _tests_result_from_reused_evidence(
                    active,
                    evidence_run,
                    root,
                    fail_fast,
                    test_jobs,
                    pytest_workers,
                    chain_errors,
                )
            else:
                _, implementation_commands = _collect_test_command_streams(active)
                scheduling_notices = []
                results, passed, failed, early_result = _run_implementation_commands(
                    implementation_commands,
                    root,
                    None,
                    fail_fast,
                    list(chain_errors),
                    [],
                    0,
                    0,
                    jobs=test_jobs,
                    pytest_workers=pytest_workers,
                    scheduling_notices=scheduling_notices,
                )
                result = early_result
                if result is None:
                    result = BatchTestResult(
                        results=results,
                        total=len(results),
                        passed=passed,
                        failed=failed,
                        chain_errors=list(chain_errors),
                        scheduling_notices=tuple(scheduling_notices),
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
        warning
        for warning in warnings
        if getattr(warning, "severity", None) == Severity.WARNING
        and not _warning_is_advisory(warning)
    ]
    return bool(blocking_warnings) and _manifest_warnings_are_blocking(
        manifest_path,
        project_root,
    )


def _warning_is_advisory(warning) -> bool:
    code = getattr(warning, "code", None)
    if code in _ADVISORY_WARNING_CODES:
        return True
    return False


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
