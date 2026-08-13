"""CLI handler for 'maid validate' command."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import TYPE_CHECKING

from maid_runner.cli.commands._format import (
    _format_artifact_coverage_report,
    format_batch_result,
    format_coherence_result,
    format_validation_result,
    print_error,
)
from maid_runner.core.diagnostic_policy import warning_is_advisory

if TYPE_CHECKING:
    from maid_runner.coherence.result import CoherenceResult
    from maid_runner.core.artifact_coverage import ArtifactCoverageReport
    from maid_runner.core.result import BatchTestResult, ValidationError
    from maid_runner.core.runtime_evidence import RuntimeEvidenceBundle


def cmd_validate(args: argparse.Namespace) -> int:
    if (
        getattr(args, "manifest_path", None)
        and getattr(args, "file_tracking", False)
        and not getattr(args, "watch_all", False)
    ):
        print_error(
            "--file-tracking is only supported for directory-wide validation",
            json_mode=getattr(args, "json", False),
        )
        return _finalize_packet(args, 2, None, None)

    if args.watch or args.watch_all:
        return _run_watch(args)

    if args.coherence_only:
        return _run_coherence_only(args)

    if getattr(args, "strict_delta", False):
        return _run_strict_delta(args)

    from maid_runner.core.types import ValidationMode
    from maid_runner.core.validate import ValidationEngine
    from maid_runner.core._test_command_execution import _inherited_strict_validation

    mode = ValidationMode(args.mode)
    engine = ValidationEngine(project_root=".")
    check_assertions, check_stubs, fail_on_warnings = _strict_options(args)
    strict_preview = getattr(args, "strict_preview", False)
    artifact_coverage_requested = (
        getattr(args, "artifact_coverage", False) or strict_preview
    ) and not _inherited_strict_validation()

    try:
        if args.manifest_path:
            result = engine.validate(
                args.manifest_path,
                mode=mode,
                use_chain=not args.no_chain,
                manifest_dir=args.manifest_dir,
                check_assertions=check_assertions,
                check_stubs=check_stubs,
                fail_on_warnings=fail_on_warnings,
            )
            test_result = None
            if result.success and getattr(args, "worktree_scope", False):
                _apply_worktree_scope_to_result(result, args)
            if result.success and getattr(args, "changed_scope", False):
                _apply_changed_scope_to_result(result, args)
            if result.success and getattr(args, "run_tests", False):
                test_result = run_validate_commands_for_result(args.manifest_path)
            artifact_coverage_report = None
            if result.success and artifact_coverage_requested:
                artifact_coverage_report = _run_artifact_coverage_for_manifest_path(
                    args.manifest_path,
                    Path("."),
                    strict_context=strict_preview,
                )
            quiet = args.quiet and not _warnings_are_blocking(
                result.warnings, fail_on_warnings=fail_on_warnings
            )
            output = format_validation_result(
                result,
                json_mode=args.json,
                quiet=quiet,
                test_result=test_result,
                tests_requested=getattr(args, "run_tests", False),
                artifact_coverage_report=artifact_coverage_report,
            )
            if not (args.coherence and result.success and args.json):
                output = _mark_strict_preview_output(
                    output,
                    enabled=strict_preview,
                    json_mode=args.json,
                )
                if output:
                    print(output)

            if args.coherence and result.success:
                coherence = run_coherence(args.manifest_dir, args.json)
                if args.json:
                    print(
                        _mark_strict_preview_output(
                            _format_validation_with_coherence_json(output, coherence),
                            enabled=strict_preview,
                            json_mode=True,
                        )
                    )
                else:
                    _print_coherence_result(coherence, json_mode=args.json)
                if not coherence.success:
                    verification_result = _verification_packet_result(
                        result, coherence=coherence
                    )
                    if not _write_sarif_report_if_requested(args, verification_result):
                        return _finalize_packet(args, 2, None, None)
                    return _finalize_packet(
                        args,
                        1,
                        verification_result,
                        test_result,
                    )

            tests_success = test_result is None or test_result.success
            artifact_coverage_success = (
                artifact_coverage_report is None or artifact_coverage_report.success
            )
            exit_code = (
                0
                if result.success and tests_success and artifact_coverage_success
                else 1
            )
            if not _write_sarif_report_if_requested(args, result):
                return _finalize_packet(args, 2, None, None)
            return _finalize_packet(args, exit_code, result, test_result)
        else:
            batch = engine.validate_all(
                args.manifest_dir,
                mode=mode,
                allow_empty=getattr(args, "allow_empty", False),
                check_file_tracking=getattr(args, "file_tracking", False),
                check_assertions=check_assertions,
                check_stubs=check_stubs,
                fail_on_warnings=fail_on_warnings,
            )
            if batch.success and getattr(args, "worktree_scope", False):
                _apply_worktree_scope_to_batch(batch, args)
            if batch.success and getattr(args, "changed_scope", False):
                _apply_changed_scope_to_batch(batch, args)
            quiet = args.quiet and not _has_warning_failure(
                batch, fail_on_warnings=fail_on_warnings
            )
            test_result = None
            if batch.success and getattr(args, "run_tests", False):
                test_result = _run_validate_commands_for_batch(args.manifest_dir)
            artifact_coverage_report = None
            if batch.success and artifact_coverage_requested:
                artifact_coverage_report = _run_artifact_coverage_for_manifest_dir(
                    args.manifest_dir,
                    Path("."),
                    strict_context=strict_preview,
                )
            output = format_batch_result(
                batch,
                json_mode=args.json,
                quiet=quiet,
                test_result=test_result,
                tests_requested=getattr(args, "run_tests", False),
            )
            output = _append_artifact_coverage_output(
                output,
                artifact_coverage_report,
                json_mode=args.json,
                quiet=quiet,
            )
            if not (args.coherence and batch.success and args.json):
                output = _mark_strict_preview_output(
                    output,
                    enabled=strict_preview,
                    json_mode=args.json,
                )
                print(output)

            if args.coherence and batch.success:
                coherence = run_coherence(args.manifest_dir, args.json)
                if args.json:
                    print(
                        _mark_strict_preview_output(
                            _format_validation_with_coherence_json(output, coherence),
                            enabled=strict_preview,
                            json_mode=True,
                        )
                    )
                else:
                    _print_coherence_result(coherence, json_mode=args.json)
                if not coherence.success:
                    verification_result = _verification_packet_result(
                        batch, coherence=coherence
                    )
                    if not _write_sarif_report_if_requested(args, verification_result):
                        return _finalize_packet(args, 2, None, None)
                    return _finalize_packet(
                        args,
                        1,
                        verification_result,
                        test_result,
                    )

            tests_success = test_result is None or test_result.success
            artifact_coverage_success = (
                artifact_coverage_report is None or artifact_coverage_report.success
            )
            exit_code = (
                0
                if batch.success and tests_success and artifact_coverage_success
                else 1
            )
            if not _write_sarif_report_if_requested(args, batch):
                return _finalize_packet(args, 2, None, None)
            return _finalize_packet(args, exit_code, batch, test_result)
    except Exception as e:
        print_error(str(e), json_mode=args.json)
        return _finalize_packet(args, 2, None, None)


def _write_sarif_report_if_requested(args, result) -> bool:
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


def _finalize_packet(args, exit_code: int, validation, test_result) -> int:
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
    if exit_code != 1 or validation is None:
        return exit_code

    try:
        packet = build_failure_packet(
            command=getattr(args, "_maid_argv", ["maid", "validate"]),
            exit_code=exit_code,
            project_root=Path("."),
            validation=validation,
            test_results=test_result,
        )
        write_failure_packet(packet, packet_path)
    except Exception as exc:
        print_error(
            f"Failed to prepare failure packet at {packet_path}: {exc}",
            json_mode=False,
        )
    return exit_code


def _verification_packet_result(validation=None, *, coherence=None):
    from maid_runner.core.result import VerificationResult, VerificationStageResult

    stages = []
    if validation is not None:
        stages.append(
            VerificationStageResult(
                name="validation",
                success=getattr(validation, "success", False),
                _validation=validation,
            )
        )
    if coherence is not None:
        stages.append(
            VerificationStageResult(
                name="coherence",
                success=getattr(coherence, "success", False),
                _coherence=coherence,
            )
        )
    return VerificationResult(stages=tuple(stages))


def run_validate_commands_for_result(
    manifest_path: str,
    fail_fast: bool = False,
) -> BatchTestResult:
    """Run a validated manifest's validate commands through the shared runner."""
    from pathlib import Path

    from maid_runner.core._validation_test_artifacts import (
        validate_manifest_test_commands,
    )
    from maid_runner.core.manifest import load_manifest, validate_manifest_paths
    from maid_runner.core.result import BatchTestResult
    from maid_runner.core.test_runner import run_manifest_tests

    manifest = load_manifest(manifest_path)
    integrity_errors = validate_manifest_paths(manifest, Path("."))
    if not integrity_errors:
        integrity_errors = validate_manifest_test_commands(manifest, Path("."))
    if integrity_errors:
        return BatchTestResult(
            results=[],
            total=0,
            passed=0,
            failed=0,
            chain_errors=integrity_errors,
        )

    return run_manifest_tests(manifest_path, fail_fast=fail_fast)


def _run_artifact_coverage_for_manifest_path(
    manifest_path: str,
    project_root: Path,
    *,
    strict_context: bool = False,
):
    from maid_runner.core.artifact_coverage import run_artifact_coverage
    from maid_runner.core._test_command_execution import (
        _strict_validation_test_environment,
    )
    from maid_runner.core.manifest import load_manifest

    with _strict_validation_test_environment(strict_context):
        return run_artifact_coverage(load_manifest(manifest_path), project_root)


def _run_artifact_coverage_for_manifest_dir(
    manifest_dir: str,
    project_root: Path,
    *,
    strict_context: bool = False,
):
    from maid_runner.core.artifact_coverage import ArtifactCoverageReport

    reports = _run_artifact_coverage_by_manifest(
        manifest_dir,
        project_root,
        strict_context=strict_context,
    ).values()
    findings = []
    errors = []
    for report in reports:
        findings.extend(report.findings)
        errors.extend(report.errors)
    return ArtifactCoverageReport(findings=tuple(findings), errors=tuple(errors))


def _run_artifact_coverage_by_manifest(
    manifest_dir: str,
    project_root: Path,
    *,
    strict_context: bool = False,
    evidence: RuntimeEvidenceBundle | None = None,
) -> dict[str, ArtifactCoverageReport]:
    from maid_runner.core.chain import get_cached_manifest_chain
    from maid_runner.core.artifact_coverage import (
        ArtifactCoverageReport,
        _coverage_targets,
        evaluate_artifact_coverage_from_evidence,
        run_artifact_coverage_batch,
    )
    from maid_runner.core._test_command_execution import (
        _strict_validation_test_environment,
    )
    from maid_runner.core.result import ErrorCode, Severity, ValidationError
    from maid_runner.core.config import load_config

    chain = get_cached_manifest_chain(project_root / manifest_dir, project_root)
    active = chain.active_manifests()
    config = load_config(project_root)
    with _strict_validation_test_environment(strict_context):
        if evidence is None:
            return run_artifact_coverage_batch(active, project_root)
        evidence_manifest_paths = {
            command.identity.manifest_path for command in evidence.commands
        }
        targets_by_manifest = {
            manifest.source_path: _coverage_targets(manifest, project_root)
            for manifest in active
        }
        coverage_manifests = tuple(
            manifest
            for manifest in active
            if targets_by_manifest[manifest.source_path]
            or manifest.source_path in evidence_manifest_paths
        )
        evaluated = dict(
            evaluate_artifact_coverage_from_evidence(
                coverage_manifests,
                project_root,
                evidence,
                fallback_jobs=config.artifact_coverage.fallback_jobs,
                max_processes=config.test_execution.max_processes,
            ).reports
        )
        for manifest in coverage_manifests:
            if (
                manifest.source_path in evidence_manifest_paths
                and not targets_by_manifest[manifest.source_path]
            ):
                evaluated[manifest.source_path] = ArtifactCoverageReport(
                    findings=(),
                    errors=(
                        ValidationError(
                            code=ErrorCode.FILE_READ_ERROR,
                            message=(
                                "Artifact coverage target disappeared during "
                                f"evidence execution for {manifest.source_path}"
                            ),
                            severity=Severity.ERROR,
                        ),
                    ),
                )
        return {
            manifest.source_path: evaluated.get(
                manifest.source_path,
                ArtifactCoverageReport(findings=(), errors=()),
            )
            for manifest in active
        }


def _merge_artifact_coverage_reports(reports):
    from maid_runner.core.artifact_coverage import ArtifactCoverageReport

    findings = []
    errors = []
    for report in reports:
        findings.extend(report.findings)
        errors.extend(report.errors)
    return ArtifactCoverageReport(findings=tuple(findings), errors=tuple(errors))


def _append_artifact_coverage_output(
    output: str,
    report,
    *,
    json_mode: bool,
    quiet: bool,
) -> str:
    if report is None:
        return output
    if json_mode:
        payload = json.loads(output)
        payload["success"] = bool(payload.get("success")) and report.success
        payload["artifact_coverage"] = report.to_dict()
        return json.dumps(payload, indent=2)
    if quiet and report.success:
        return output
    formatted = _format_artifact_coverage_report(report)
    if not output:
        return formatted
    return f"{output}\n\n{formatted}"


def _run_strict_delta(args: argparse.Namespace) -> int:
    from maid_runner.core._test_command_execution import _inherited_strict_validation
    from maid_runner.core.strict_delta import compute_strict_delta
    from maid_runner.core.types import ValidationMode
    from maid_runner.core.validate import ValidationEngine

    mode = ValidationMode(args.mode)
    engine = ValidationEngine(project_root=".")
    default_args = _copy_args(args, strict_preview=False)
    strict_args = _copy_args(args, strict_preview=True)
    default_check_assertions, default_check_stubs, default_fail_on_warnings = (
        _strict_options(default_args)
    )
    strict_check_assertions, strict_check_stubs, strict_fail_on_warnings = (
        _strict_options(strict_args)
    )
    coverage_boundary_active = _inherited_strict_validation()

    try:
        if args.manifest_path:
            default_result = engine.validate(
                args.manifest_path,
                mode=mode,
                use_chain=not args.no_chain,
                manifest_dir=args.manifest_dir,
                check_assertions=default_check_assertions,
                check_stubs=default_check_stubs,
                fail_on_warnings=default_fail_on_warnings,
            )
            strict_result = engine.validate(
                args.manifest_path,
                mode=mode,
                use_chain=not args.no_chain,
                manifest_dir=args.manifest_dir,
                check_assertions=strict_check_assertions,
                check_stubs=strict_check_stubs,
                fail_on_warnings=strict_fail_on_warnings,
            )
            test_result = None
            if default_result.success and getattr(args, "worktree_scope", False):
                _apply_worktree_scope_to_result(default_result, args)
            if default_result.success and getattr(args, "changed_scope", False):
                _apply_changed_scope_to_result(default_result, args)
            if default_result.success and getattr(args, "run_tests", False):
                test_result = run_validate_commands_for_result(args.manifest_path)

            default_coverage_report = None
            default_coverage = None
            if (
                default_result.success
                and getattr(args, "artifact_coverage", False)
                and not coverage_boundary_active
            ):
                default_coverage_report = _run_artifact_coverage_for_manifest_path(
                    args.manifest_path,
                    Path("."),
                )
                default_coverage = {
                    default_result.manifest_path: default_coverage_report
                }

            strict_coverage = None
            if strict_result.success and not coverage_boundary_active:
                strict_coverage_report = _run_artifact_coverage_for_manifest_path(
                    args.manifest_path,
                    Path("."),
                    strict_context=True,
                )
                strict_coverage = {strict_result.manifest_path: strict_coverage_report}

            report = compute_strict_delta(
                _batch_from_single(default_result),
                _batch_from_single(strict_result),
                default_coverage=default_coverage,
                strict_coverage=strict_coverage,
            )
            quiet = args.quiet and not _has_warning_failure(
                _batch_from_single(default_result),
                fail_on_warnings=default_fail_on_warnings,
            )
            output = format_validation_result(
                default_result,
                json_mode=args.json,
                quiet=quiet,
                test_result=test_result,
                tests_requested=getattr(args, "run_tests", False),
                artifact_coverage_report=default_coverage_report,
            )
            output = _append_strict_delta_output(
                output,
                report,
                json_mode=args.json,
                quiet=quiet,
            )
            if output:
                print(output)

            tests_success = test_result is None or test_result.success
            artifact_coverage_success = (
                default_coverage_report is None or default_coverage_report.success
            )
            exit_code = (
                0
                if default_result.success
                and tests_success
                and artifact_coverage_success
                else 1
            )
            if not _write_sarif_report_if_requested(args, default_result):
                return _finalize_packet(args, 2, None, None)
            return _finalize_packet(args, exit_code, default_result, test_result)

        default_batch = engine.validate_all(
            args.manifest_dir,
            mode=mode,
            allow_empty=getattr(args, "allow_empty", False),
            check_file_tracking=getattr(args, "file_tracking", False),
            check_assertions=default_check_assertions,
            check_stubs=default_check_stubs,
            fail_on_warnings=default_fail_on_warnings,
        )
        strict_batch = engine.validate_all(
            args.manifest_dir,
            mode=mode,
            allow_empty=getattr(args, "allow_empty", False),
            check_file_tracking=getattr(args, "file_tracking", False),
            check_assertions=strict_check_assertions,
            check_stubs=strict_check_stubs,
            fail_on_warnings=strict_fail_on_warnings,
        )
        if default_batch.success and getattr(args, "worktree_scope", False):
            _apply_worktree_scope_to_batch(default_batch, args)
        if default_batch.success and getattr(args, "changed_scope", False):
            _apply_changed_scope_to_batch(default_batch, args)

        test_result = None
        if default_batch.success and getattr(args, "run_tests", False):
            test_result = _run_validate_commands_for_batch(args.manifest_dir)

        default_coverage_report = None
        default_coverage = None
        if (
            default_batch.success
            and getattr(args, "artifact_coverage", False)
            and not coverage_boundary_active
        ):
            default_coverage = _run_artifact_coverage_by_manifest(
                args.manifest_dir,
                Path("."),
            )
            default_coverage_report = _merge_artifact_coverage_reports(
                default_coverage.values()
            )

        strict_coverage = None
        if strict_batch.success and not coverage_boundary_active:
            strict_coverage = _run_artifact_coverage_by_manifest(
                args.manifest_dir,
                Path("."),
                strict_context=True,
            )

        report = compute_strict_delta(
            default_batch,
            strict_batch,
            default_coverage=default_coverage,
            strict_coverage=strict_coverage,
        )
        quiet = args.quiet and not _has_warning_failure(
            default_batch,
            fail_on_warnings=default_fail_on_warnings,
        )
        output = format_batch_result(
            default_batch,
            json_mode=args.json,
            quiet=quiet,
            test_result=test_result,
            tests_requested=getattr(args, "run_tests", False),
        )
        output = _append_artifact_coverage_output(
            output,
            default_coverage_report,
            json_mode=args.json,
            quiet=quiet,
        )
        output = _append_strict_delta_output(
            output,
            report,
            json_mode=args.json,
            quiet=quiet,
        )
        print(output)

        tests_success = test_result is None or test_result.success
        artifact_coverage_success = (
            default_coverage_report is None or default_coverage_report.success
        )
        exit_code = (
            0
            if default_batch.success and tests_success and artifact_coverage_success
            else 1
        )
        if not _write_sarif_report_if_requested(args, default_batch):
            return _finalize_packet(args, 2, None, None)
        return _finalize_packet(args, exit_code, default_batch, test_result)
    except Exception as e:
        print_error(str(e), json_mode=args.json)
        return _finalize_packet(args, 2, None, None)


def _copy_args(args: argparse.Namespace, **overrides: object) -> argparse.Namespace:
    values = vars(args).copy()
    values.update(overrides)
    return argparse.Namespace(**values)


def _batch_from_single(result):
    from maid_runner.core.result import BatchValidationResult

    return BatchValidationResult(
        results=[result],
        total_manifests=1,
        passed=1 if result.success else 0,
        failed=0 if result.success else 1,
        skipped=0,
    )


def _append_strict_delta_output(
    output: str,
    report,
    *,
    json_mode: bool,
    quiet: bool,
) -> str:
    if json_mode:
        payload = json.loads(output) if output else {}
        payload["strict_delta"] = report.to_dict()["entries"]
        return json.dumps(payload, indent=2)
    formatted = _format_strict_delta_report(report)
    if quiet and not report.entries:
        return output
    if not output:
        return formatted
    return f"{output}\n\n{formatted}"


def _format_strict_delta_report(report) -> str:
    count = len(report.entries)
    lines = [f"Strict Delta: {count} strict-only diagnostics"]
    current_manifest = None
    current_file = None
    for entry in report.entries:
        if entry.manifest_path != current_manifest:
            current_manifest = entry.manifest_path
            current_file = None
            lines.append(f"  {entry.manifest_path}")
        file_label = entry.file or "<manifest>"
        if file_label != current_file:
            current_file = file_label
            lines.append(f"    {file_label}")
        lines.append(f"      {entry.code} [{entry.severity}] {entry.message}")
    return "\n".join(lines)


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


def _run_validate_commands_for_batch(
    manifest_dir: str,
    fail_fast: bool = False,
) -> BatchTestResult:
    """Run active manifest validate commands through the shared runner."""
    from pathlib import Path

    from maid_runner.core.result import BatchTestResult
    from maid_runner.core.test_runner import run_tests

    integrity_errors = _validate_command_integrity_for_manifest_dir(
        manifest_dir,
        project_root=Path("."),
    )
    if integrity_errors:
        return BatchTestResult(
            results=[],
            total=0,
            passed=0,
            failed=0,
            chain_errors=integrity_errors,
        )

    return run_tests(manifest_dir=manifest_dir, fail_fast=fail_fast)


def _validate_command_integrity_for_manifest_dir(
    manifest_dir: str,
    *,
    project_root,
) -> list[ValidationError]:
    from maid_runner.core._validation_test_artifacts import (
        validate_manifest_test_commands,
    )
    from maid_runner.core.chain import get_cached_manifest_chain
    from maid_runner.core.manifest import validate_manifest_paths
    from maid_runner.core.result import Severity

    chain = get_cached_manifest_chain(project_root / manifest_dir, project_root)
    chain_errors = chain.diagnostics()
    if any(error.severity == Severity.ERROR for error in chain_errors):
        return chain_errors

    errors = []
    for manifest in chain.active_manifests():
        path_errors = validate_manifest_paths(manifest, project_root)
        if path_errors:
            errors.extend(path_errors)
            continue
        errors.extend(validate_manifest_test_commands(manifest, project_root))
    return errors


def _run_coherence_only(args: argparse.Namespace) -> int:
    """Run only coherence checks, no structural validation."""
    try:
        result = run_coherence(args.manifest_dir, args.json)
        print(
            _mark_strict_preview_output(
                format_coherence_result(result, json_mode=args.json),
                enabled=getattr(args, "strict_preview", False),
                json_mode=args.json,
            )
        )
        exit_code = 0 if result.success else 1
        verification_result = _verification_packet_result(coherence=result)
        if not _write_sarif_report_if_requested(args, verification_result):
            return _finalize_packet(args, 2, None, None)
        return _finalize_packet(
            args,
            exit_code,
            verification_result,
            None,
        )
    except Exception as e:
        print_error(str(e), json_mode=args.json)
        return 2


def run_coherence(manifest_dir: str, json_mode: bool) -> "CoherenceResult":
    """Run coherence checks and return the result."""
    from pathlib import Path

    from maid_runner.coherence.engine import CoherenceEngine
    from maid_runner.core.chain import ManifestChain

    del json_mode
    chain = ManifestChain(manifest_dir)
    engine = CoherenceEngine()
    result = engine.validate(chain, project_root=Path.cwd())
    return result


def _print_coherence_result(result: "CoherenceResult", *, json_mode: bool) -> None:
    """Print coherence output after structural validation output."""
    print()
    print(format_coherence_result(result, json_mode=json_mode))


def _format_validation_with_coherence_json(
    validation_json: str,
    coherence: "CoherenceResult",
) -> str:
    """Combine validation and coherence results into one JSON document."""
    payload = json.loads(validation_json)
    if "validation" not in payload:
        payload = {
            "success": payload["success"],
            "validation": payload,
        }
    payload["coherence"] = coherence.to_dict()
    payload["success"] = bool(payload["success"] and coherence.success)
    return json.dumps(payload, indent=2)


def _strict_options(args: argparse.Namespace) -> tuple[bool, bool, bool]:
    from maid_runner.core._test_command_execution import _inherited_strict_validation

    strict = (
        getattr(args, "strict", False)
        or getattr(args, "strict_preview", False)
        or _inherited_strict_validation()
    )
    check_assertions = getattr(args, "check_assertions", False) or strict
    check_stubs = getattr(args, "check_stubs", False) or strict
    fail_on_warnings = getattr(args, "fail_on_warnings", False) or strict
    return check_assertions, check_stubs, fail_on_warnings


def _has_warning_failure(batch, *, fail_on_warnings: bool) -> bool:
    if not fail_on_warnings:
        return False
    if any(
        _warnings_are_blocking(result.warnings, fail_on_warnings=True)
        for result in batch.results
    ):
        return True
    return _warnings_are_blocking(batch.chain_errors, fail_on_warnings=True)


def _warnings_are_blocking(warnings, *, fail_on_warnings: bool) -> bool:
    if not fail_on_warnings:
        return False
    return any(
        warning.severity.value == "warning" and not warning_is_advisory(warning)
        for warning in warnings
    )


def _run_watch(args: argparse.Namespace) -> int:
    """Run validation in watch mode."""
    try:
        from watchdog.observers import Observer
        from watchdog.events import FileSystemEventHandler
    except ImportError:
        print(
            "Error: Watch mode requires watchdog. "
            "Install with: pip install maid-runner[watch]",
            file=sys.stderr,
        )
        return 2

    import time

    class _Handler(FileSystemEventHandler):
        def __init__(self) -> None:
            self.triggered = False

        def on_modified(self, event) -> None:  # type: ignore[override]
            if not event.is_directory and event.src_path.endswith(
                (".py", ".ts", ".tsx", ".svelte", ".yaml", ".json")
            ):
                self.triggered = True

    handler = _Handler()
    observer = Observer()

    # Determine paths to watch
    from pathlib import Path

    watch_paths = [Path(args.manifest_dir)]
    if args.manifest_path and not args.watch_all:
        # Single-manifest watch: also watch files referenced by the manifest
        try:
            from maid_runner.core.manifest import load_manifest

            m = load_manifest(args.manifest_path)
            for fs in m.all_file_specs:
                p = Path(fs.path).parent
                if p.exists():
                    watch_paths.append(p)
        except Exception:
            pass
    else:
        # Watch-all: watch common source directories
        for d in [Path("maid_runner"), Path("src"), Path(".")]:
            if d.is_dir():
                watch_paths.append(d)
                break

    for p in watch_paths:
        if p.exists():
            observer.schedule(handler, str(p), recursive=True)

    observer.start()
    print("Watching for changes... (Ctrl+C to stop)")

    try:
        # Initial run
        _run_validation_pass(args)
        while True:
            time.sleep(0.5)
            if handler.triggered:
                handler.triggered = False
                time.sleep(0.2)  # Debounce
                print("\n--- Change detected, re-validating ---\n")
                _run_validation_pass(args)
    except KeyboardInterrupt:
        observer.stop()
        print("\nStopped watching.")
    observer.join()
    return 0


def _run_validation_pass(args: argparse.Namespace) -> None:
    """Run a single validation pass (used by watch mode)."""
    from maid_runner.core.types import ValidationMode
    from maid_runner.core.validate import ValidationEngine

    mode = ValidationMode(args.mode)
    engine = ValidationEngine(project_root=".")
    check_assertions, check_stubs, fail_on_warnings = _strict_options(args)

    try:
        if args.manifest_path and not args.watch_all:
            result = engine.validate(
                args.manifest_path,
                mode=mode,
                use_chain=not args.no_chain,
                manifest_dir=args.manifest_dir,
                check_assertions=check_assertions,
                check_stubs=check_stubs,
                fail_on_warnings=fail_on_warnings,
            )
            if result.success and getattr(args, "worktree_scope", False):
                _apply_worktree_scope_to_result(result, args)
            if result.success and getattr(args, "changed_scope", False):
                _apply_changed_scope_to_result(result, args)
            quiet = args.quiet and not _warnings_are_blocking(
                result.warnings, fail_on_warnings=fail_on_warnings
            )
            output = format_validation_result(result, json_mode=args.json, quiet=quiet)
            if output:
                print(output)
        else:
            batch = engine.validate_all(
                args.manifest_dir,
                mode=mode,
                allow_empty=getattr(args, "allow_empty", False),
                check_file_tracking=getattr(args, "file_tracking", False),
                check_assertions=check_assertions,
                check_stubs=check_stubs,
                fail_on_warnings=fail_on_warnings,
            )
            if batch.success and getattr(args, "worktree_scope", False):
                _apply_worktree_scope_to_batch(batch, args)
            if batch.success and getattr(args, "changed_scope", False):
                _apply_changed_scope_to_batch(batch, args)
            quiet = args.quiet and not _has_warning_failure(
                batch, fail_on_warnings=fail_on_warnings
            )
            print(format_batch_result(batch, json_mode=args.json, quiet=quiet))
    except Exception as e:
        print_error(str(e), json_mode=args.json)


def _apply_worktree_scope_to_result(result, args: argparse.Namespace) -> None:
    errors = _run_worktree_scope(args)
    if not errors:
        return
    result.errors.extend(errors)
    result.success = False


def _apply_worktree_scope_to_batch(batch, args: argparse.Namespace) -> None:
    errors = _run_worktree_scope(args)
    if not errors:
        return

    if batch.results:
        target = batch.results[0]
        target.errors.extend(errors)
        if target.success:
            target.success = False
            batch.passed = max(0, batch.passed - 1)
            batch.failed += 1
        return

    batch.chain_errors.extend(errors)
    batch.failed += 1


def _apply_changed_scope_to_result(result, args: argparse.Namespace) -> None:
    errors = _run_changed_scope(args)
    if not errors:
        return
    result.errors.extend(errors)
    result.success = False


def _apply_changed_scope_to_batch(batch, args: argparse.Namespace) -> None:
    errors = _run_changed_scope(args)
    if not errors:
        return

    if batch.results:
        target = batch.results[0]
        target.errors.extend(errors)
        if target.success:
            target.success = False
            batch.passed = max(0, batch.passed - 1)
            batch.failed += 1
        return

    batch.chain_errors.extend(errors)
    batch.failed += 1


def _run_worktree_scope(args: argparse.Namespace) -> "list[ValidationError]":
    from maid_runner.core.chain import ManifestChain
    from maid_runner.core.result import ErrorCode, Severity, ValidationError
    from maid_runner.core.worktree import validate_worktree_scope

    try:
        chain = _scope_chain(args, ManifestChain)
        return validate_worktree_scope(
            ".",
            chain,
            include_tests=getattr(args, "include_tests", False),
        )
    except Exception as exc:
        return [
            ValidationError(
                code=ErrorCode.FILE_READ_ERROR,
                message=f"Worktree scope gate failed: {exc}",
                severity=Severity.ERROR,
            )
        ]


def _run_changed_scope(args: argparse.Namespace) -> "list[ValidationError]":
    from maid_runner.core.chain import ManifestChain
    from maid_runner.core.result import ErrorCode, Severity, ValidationError
    from maid_runner.core.worktree import validate_changed_scope

    try:
        chain = _scope_chain(args, ManifestChain)
        return validate_changed_scope(
            ".",
            chain,
            since=getattr(args, "since", None),
            base_ref=getattr(args, "base_ref", None),
            include_tests=getattr(args, "include_tests", False),
        )
    except Exception as exc:
        return [
            ValidationError(
                code=ErrorCode.FILE_READ_ERROR,
                message=f"Changed-scope gate failed: {exc}",
                severity=Severity.ERROR,
            )
        ]


def _scope_chain(args: argparse.Namespace, chain_type) -> object:
    if not getattr(args, "manifest_path", None):
        return chain_type(args.manifest_dir, ".")

    from maid_runner.core.manifest import load_manifest

    return _SingleManifestScope(load_manifest(args.manifest_path))


class _SingleManifestScope:
    def __init__(self, manifest) -> None:
        self._manifest = manifest

    def active_manifests(self) -> list:
        return [self._manifest]
