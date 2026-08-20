"""Output formatters for MAID Runner v2 CLI."""

from __future__ import annotations

import json
import sys
from typing import TYPE_CHECKING, Optional

from maid_runner.core.result import (
    BatchTestResult,
    BatchValidationResult,
    FileTrackingReport,
    ValidationResult,
    VerificationResult,
)
from maid_runner.coherence.result import CoherenceResult

if TYPE_CHECKING:
    from maid_runner.core.artifact_coverage import ArtifactCoverageReport
    from maid_runner.core.bootstrap import BootstrapReport
    from maid_runner.core.chain_merge import ChainMergeReport
    from maid_runner.core.chain_merge_apply import ChainMergeApplyResult
    from maid_runner.core.chain_merge_equivalence import MergeEquivalenceResult
    from maid_runner.core.chain_merge_sweep import ChainMergeSweepSummary
    from maid_runner.core.supersession_audit import SupersessionViolation


def print_error(message: str, *, json_mode: bool = False) -> None:
    """Print an error message to stderr, or as JSON to stdout."""
    if json_mode:
        print(json.dumps({"error": message}))
    else:
        print(f"Error: {message}", file=sys.stderr)


def format_manifests_list(
    manifests: list,
    file_path: str,
    *,
    json_mode: bool = False,
    quiet: bool = False,
) -> str:
    if json_mode:
        return json.dumps(
            [
                {"slug": m.slug, "goal": m.goal, "path": m.source_path}
                for m in manifests
            ],
            indent=2,
        )
    if quiet:
        return "\n".join(m.source_path for m in manifests)
    if not manifests:
        return f"No manifests reference '{file_path}'"
    lines = [f"Manifests referencing '{file_path}':"]
    for m in manifests:
        lines.append(f"  {m.slug}: {m.goal}")
    return "\n".join(lines)


def format_validation_result(
    result: ValidationResult,
    *,
    json_mode: bool = False,
    quiet: bool = False,
    test_result: BatchTestResult | None = None,
    tests_requested: bool = False,
    artifact_coverage_report: "ArtifactCoverageReport | None" = None,
) -> str:
    if json_mode:
        if (
            tests_requested
            or test_result is not None
            or artifact_coverage_report is not None
        ):
            tests_success = (
                test_result.success if test_result is not None else not tests_requested
            )
            artifact_coverage_success = (
                artifact_coverage_report.success
                if artifact_coverage_report is not None
                else True
            )
            return json.dumps(
                {
                    "success": (
                        result.success and tests_success and artifact_coverage_success
                    ),
                    "validation": result.to_dict(),
                    "tests": (
                        _test_result_to_dict(test_result)
                        if test_result is not None
                        else None
                    ),
                    "artifact_coverage": (
                        artifact_coverage_report.to_dict()
                        if artifact_coverage_report is not None
                        else None
                    ),
                },
                indent=2,
            )
        return result.to_json()

    if quiet:
        if result.success:
            output = _append_test_result("", test_result, quiet=quiet)
            return _append_artifact_coverage_result(
                output,
                artifact_coverage_report,
                quiet=quiet,
            )
        lines = []
        for err in result.errors:
            lines.append(f"  {err.code.value} {err.message}")
        output = _append_test_result("\n".join(lines), test_result, quiet=quiet)
        return _append_artifact_coverage_result(
            output,
            artifact_coverage_report,
            quiet=quiet,
        )

    lines = []
    symbol = "PASS" if result.success else "FAIL"
    lines.append(f"{symbol} {result.manifest_slug}")
    lines.append(f"  Mode: {result.mode.value}")
    if result.duration_ms is not None:
        lines.append(f"  Duration: {result.duration_ms:.0f}ms")

    if result.errors:
        lines.append(f"  Errors ({len(result.errors)}):")
        for err in result.errors:
            lines.extend(_format_validation_error_lines(err, indent="    "))

    if result.warnings:
        lines.append(f"  Warnings ({len(result.warnings)}):")
        for w in result.warnings:
            lines.extend(_format_validation_error_lines(w, indent="    "))

    output = _append_test_result("\n".join(lines), test_result, quiet=quiet)
    return _append_artifact_coverage_result(
        output,
        artifact_coverage_report,
        quiet=quiet,
    )


def format_batch_result(
    result: BatchValidationResult,
    *,
    json_mode: bool = False,
    quiet: bool = False,
    test_result: BatchTestResult | None = None,
    tests_requested: bool = False,
) -> str:
    if json_mode:
        if tests_requested or test_result is not None:
            return json.dumps(
                {
                    "success": result.success
                    and (test_result.success if test_result is not None else False),
                    "validation": result.to_dict(),
                    "tests": (
                        _test_result_to_dict(test_result)
                        if test_result is not None
                        else None
                    ),
                },
                indent=2,
            )
        return json.dumps(result.to_dict(), indent=2)

    if quiet:
        lines = []
        for err in result.chain_errors:
            lines.append(f"{err.code.value} {err.message}")
        for r in result.results:
            if not r.success:
                lines.append(f"FAIL {r.manifest_slug}")
                for err in r.errors:
                    lines.append(f"  {err.code.value} {err.message}")
        return _append_test_result("\n".join(lines), test_result, quiet=quiet)

    lines = []
    lines.append(f"Validation Results: {result.total_manifests} manifests")
    lines.append(f"  Passed: {result.passed}")
    lines.append(f"  Failed: {result.failed}")
    if result.skipped:
        lines.append(f"  Skipped: {result.skipped} (superseded)")
    if result.duration_ms is not None:
        lines.append(f"  Duration: {result.duration_ms:.0f}ms")

    if result.chain_errors:
        lines.append("")
        lines.append(f"Chain Issues ({len(result.chain_errors)}):")
        for err in result.chain_errors:
            lines.extend(_format_validation_error_lines(err, indent="  "))

    for r in result.results:
        if not r.success:
            lines.append("")
            lines.append(format_validation_result(r))

    return _append_test_result("\n".join(lines), test_result, quiet=quiet)


def format_test_result(
    result: BatchTestResult,
    *,
    verbose: bool = False,
    json_mode: bool = False,
) -> str:
    if json_mode:
        return json.dumps(
            _test_result_to_dict(result, include_failure_output=True), indent=2
        )

    acceptance = result.acceptance_results
    implementation = result.implementation_results

    # When no acceptance tests, use the original format for backward compatibility
    if not acceptance:
        lines = []
        lines.append(f"Test Results: {result.total} commands")
        lines.append(f"  Passed: {result.passed}")
        lines.append(f"  Failed: {result.failed}")
        if result.duration_ms is not None:
            lines.append(f"  Duration: {result.duration_ms:.0f}ms")
        if result.chain_errors:
            lines.append(f"  Chain issues: {len(result.chain_errors)}")
            for err in result.chain_errors:
                lines.append(f"  {err.code.value} {err.message}")
        lines.extend(_format_scheduling_notices(result))

        for r in result.results:
            lines.append(_format_test_command_line(r))
            if verbose and r.stdout:
                for line in r.stdout.strip().splitlines():
                    lines.append(f"    {line}")
            if not r.success and r.stderr:
                for line in r.stderr.strip().splitlines():
                    lines.append(f"    {line}")

        return "\n".join(lines)

    # Two-section format when acceptance tests are present
    lines = []

    lines.append(f"Test Results: {result.total} commands")
    lines.append(f"  Passed: {result.passed}")
    lines.append(f"  Failed: {result.failed}")
    if result.duration_ms is not None:
        lines.append(f"  Duration: {result.duration_ms:.0f}ms")
    if result.chain_errors:
        lines.append(f"  Chain issues: {len(result.chain_errors)}")
        for err in result.chain_errors:
            lines.append(f"  {err.code.value} {err.message}")
    lines.extend(_format_scheduling_notices(result))
    lines.append("")

    acc_passed = sum(1 for r in acceptance if r.success)
    acc_failed = len(acceptance) - acc_passed
    lines.append(f"Acceptance Tests (Stream 1): {len(acceptance)} commands")
    lines.append(f"  Passed: {acc_passed}")
    lines.append(f"  Failed: {acc_failed}")
    for r in acceptance:
        lines.append(_format_test_command_line(r))
        if verbose and r.stdout:
            for line in r.stdout.strip().splitlines():
                lines.append(f"    {line}")
        if not r.success and r.stderr:
            for line in r.stderr.strip().splitlines():
                lines.append(f"    {line}")

    lines.append("")

    imp_passed = sum(1 for r in implementation if r.success)
    imp_failed = len(implementation) - imp_passed
    lines.append(f"Implementation Tests (Stream 3): {len(implementation)} commands")
    lines.append(f"  Passed: {imp_passed}")
    lines.append(f"  Failed: {imp_failed}")
    for r in implementation:
        lines.append(_format_test_command_line(r))
        if verbose and r.stdout:
            for line in r.stdout.strip().splitlines():
                lines.append(f"    {line}")
        if not r.success and r.stderr:
            for line in r.stderr.strip().splitlines():
                lines.append(f"    {line}")

    return "\n".join(lines)


def format_verify_result(
    result: VerificationResult,
    *,
    json_mode: bool = False,
) -> str:
    if json_mode:
        payload: dict = {
            "success": _verification_success(result),
            "stages": [_verify_stage_to_dict(stage) for stage in result.stages],
        }
        if result.duration_ms is not None:
            payload["duration_ms"] = result.duration_ms
        return json.dumps(payload, indent=2)

    status = "PASS" if _verification_success(result) else "FAIL"
    lines = [f"Verify: {status}"]
    if result.duration_ms is not None:
        lines.append(f"  Duration: {result.duration_ms:.0f}ms")

    for stage in result.stages:
        skip_reason = getattr(stage, "skip_reason", None)
        stage_status = (
            "SKIPPED" if skip_reason else ("PASS" if stage.success else "FAIL")
        )
        stage_line = f"  {stage_status} {stage.name}"
        if skip_reason:
            stage_line = f"{stage_line} ({skip_reason})"
        lines.append(stage_line)
        details = _format_verify_stage_details(stage)
        if details:
            lines.extend(f"    {line}" for line in details.splitlines())

    return "\n".join(lines)


def format_verify_summary(
    result: VerificationResult,
    *,
    json_mode: bool = False,
) -> str:
    from maid_runner.core.verify_summary import build_verify_summary

    summary = build_verify_summary(result)
    blocking_stages = [stage for stage in result.stages if not stage.success]

    if json_mode:
        payload: dict = {
            "success": summary.success,
            "findings": {
                "blocking": [_verify_stage_to_dict(stage) for stage in blocking_stages],
                "warnings": [
                    {
                        "code": group.code,
                        "message": group.message,
                        "location": group.location,
                        "count": group.count,
                    }
                    for group in summary.warning_groups
                ],
                "info": [
                    {
                        "code": group.code,
                        "message": group.message,
                        "location": group.location,
                        "count": group.count,
                    }
                    for group in summary.info_groups
                ],
                "recovery": [
                    {
                        "code": group.code,
                        "suggestion": group.suggestion,
                        "manifest_paths": list(group.manifest_paths),
                        "count": group.count,
                    }
                    for group in summary.recovery_groups
                ],
            },
            "warning_blocking_stages": list(summary.warning_blocking_stages),
            "passed_stages": list(summary.passed_stages),
            "skipped_stages": list(summary.skipped_stages),
        }
        if result.duration_ms is not None:
            payload["duration_ms"] = result.duration_ms
        return json.dumps(payload, indent=2)

    status = "PASS" if summary.success else "FAIL"
    warning_unique_count = len(summary.warning_groups)
    info_unique_count = len(summary.info_groups)
    info_fragment = ""
    if summary.raw_info_count:
        info_fragment = (
            f"{info_unique_count} info unique / {summary.raw_info_count} raw, "
        )
    lines = [
        (
            f"VERIFY: {status} "
            f"({len(summary.blocking_stages)} blocking, "
            f"{warning_unique_count} warnings unique / "
            f"{summary.raw_warning_count} raw, "
            f"{info_fragment}"
            f"{len(summary.passed_stages)} passed, "
            f"{len(summary.skipped_stages)} skipped)"
        )
    ]
    if result.duration_ms is not None:
        lines.append(f"  Duration: {result.duration_ms:.0f}ms")

    if blocking_stages:
        lines.append("")
        lines.append(f"BLOCKING ({len(blocking_stages)}):")
        grouped_recovery_suggestions = frozenset(
            group.suggestion for group in summary.recovery_groups
        )
        for stage in blocking_stages:
            lines.append(f"  FAIL {stage.name}")
            details = _format_verify_summary_stage_details(
                stage,
                grouped_recovery_suggestions=grouped_recovery_suggestions,
            )
            if details:
                lines.extend(f"    {line}" for line in details.splitlines())

    if summary.recovery_groups:
        lines.append("")
        noun = "group" if len(summary.recovery_groups) == 1 else "groups"
        lines.append(f"RECOVERY ({len(summary.recovery_groups)} {noun}):")
        for group in summary.recovery_groups:
            manifest_noun = (
                "manifest" if len(group.manifest_paths) == 1 else "manifests"
            )
            lines.append(
                f"  {group.code} x{group.count} across "
                f"{len(group.manifest_paths)} {manifest_noun}"
            )
            lines.append(f"    Manifests: {', '.join(group.manifest_paths)}")
            lines.append(f"    Suggestion: {group.suggestion}")

    if summary.passed_stages:
        lines.append("")
        lines.append(
            f"PASSED ({len(summary.passed_stages)}): {', '.join(summary.passed_stages)}"
        )

    skipped_stages = [
        stage for stage in result.stages if getattr(stage, "skip_reason", None)
    ]
    if skipped_stages:
        lines.append("")
        rendered = ", ".join(
            f"{stage.name} ({getattr(stage, 'skip_reason')})"
            for stage in skipped_stages
        )
        lines.append(f"SKIPPED ({len(skipped_stages)}): {rendered}")

    if summary.warning_groups:
        lines.append("")
        if summary.warning_blocking_stages:
            lines.append(
                "WARNINGS "
                f"(deduplicated {summary.raw_warning_count} -> "
                f"{warning_unique_count}; blocking for: "
                f"{', '.join(summary.warning_blocking_stages)} "
                "under verify policy):"
            )
            lines.append(
                "  Hint: use --advisory as the brownfield escape hatch to report "
                "warnings without failing stages."
            )
        else:
            lines.append(
                "WARNINGS "
                f"(non-blocking, deduplicated {summary.raw_warning_count} -> "
                f"{warning_unique_count}):"
            )
        for group in summary.warning_groups:
            prefix = group.code or "warning"
            lines.append(f"  {prefix} x{group.count} {group.message}")
            if group.location:
                lines.append(f"    {group.location}")

    if summary.info_groups:
        lines.append("")
        lines.append(
            f"INFO (deduplicated {summary.raw_info_count} -> {info_unique_count}):"
        )
        for group in summary.info_groups:
            prefix = group.code or "info"
            lines.append(f"  INFO {prefix} x{group.count} {group.message}")
            if group.location:
                lines.append(f"    {group.location}")

    return "\n".join(lines)


def _append_test_result(
    formatted_validation: str,
    test_result: BatchTestResult | None,
    *,
    quiet: bool,
) -> str:
    if test_result is None:
        return formatted_validation
    if quiet and test_result.success:
        return formatted_validation
    formatted_tests = format_test_result(test_result)
    if not formatted_validation:
        return formatted_tests
    return f"{formatted_validation}\n\n{formatted_tests}"


def _append_artifact_coverage_result(
    formatted_validation: str,
    report,
    *,
    quiet: bool,
) -> str:
    if report is None:
        return formatted_validation
    if quiet and report.success:
        return formatted_validation
    formatted_report = _format_artifact_coverage_report(report)
    if not formatted_validation:
        return formatted_report
    return f"{formatted_validation}\n\n{formatted_report}"


def _format_artifact_coverage_report(report) -> str:
    status = "PASS" if report.success else "FAIL"
    lines = [f"Artifact coverage: {status}"]
    execution = getattr(report, "execution", None)
    if execution is not None:
        lines.append(f"  Execution: {execution.describe()}")
    if getattr(report, "findings", ()):
        lines.append(f"  Findings: {len(report.findings)}")
        for finding in report.findings:
            state = "executed" if finding.executed else "not executed"
            name = finding.artifact_name
            if finding.parent_class:
                name = f"{finding.parent_class}.{name}"
            lines.append(f"  {state}: {name} ({finding.file_path})")
    if getattr(report, "errors", ()):
        lines.append(f"  Errors ({len(report.errors)}):")
        for error in report.errors:
            lines.extend(_format_validation_error_lines(error, indent="    "))
    return "\n".join(lines)


def _format_validation_error_lines(
    error,
    *,
    indent: str,
    include_suggestion: bool = True,
) -> list[str]:
    lines = [f"{indent}{_format_validation_error_summary(error)}"]
    location = _format_validation_error_location(error)
    if location:
        lines.append(f"{indent}  Location: {location}")
    suggestion = getattr(error, "suggestion", None)
    if suggestion and include_suggestion:
        lines.append(f"{indent}  Suggestion: {suggestion}")
    return lines


def _format_validation_error_summary(error) -> str:
    code = getattr(getattr(error, "code", None), "value", None)
    message = getattr(error, "message", None)
    if code and message:
        return f"{code} {message}"
    return str(error)


def _format_validation_error_location(error) -> str:
    location = getattr(error, "location", None)
    if location is None:
        return ""

    file = getattr(location, "file", None)
    if not file:
        return ""

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


def _verification_success(result: VerificationResult) -> bool:
    return all(stage.success for stage in result.stages)


def _verify_stage_to_dict(stage) -> dict:
    data: dict = {
        "name": stage.name,
        "success": stage.success,
    }
    skip_reason = getattr(stage, "skip_reason", None)
    if skip_reason is not None:
        data["skip_reason"] = skip_reason
    duration_ms = getattr(stage, "_duration_ms", None)
    if duration_ms is not None:
        data["duration_ms"] = duration_ms
    details = _verify_stage_details(stage)
    if details:
        data["details"] = details
    return data


def _verify_stage_details(stage) -> dict:
    validation = getattr(stage, "_validation", None)
    if validation is not None:
        return validation.to_dict()

    coherence = getattr(stage, "_coherence", None)
    if coherence is not None:
        return coherence.to_dict()

    file_tracking = getattr(stage, "_file_tracking", None)
    if file_tracking is not None:
        details = {
            "tracked": [e.path for e in file_tracking.tracked],
            "registered": [e.path for e in file_tracking.registered],
            "scope_only": [e.path for e in file_tracking.scope_only],
            "undeclared": [e.path for e in file_tracking.undeclared],
        }
        errors = getattr(stage, "_errors", ())
        if errors:
            details["errors"] = [_verify_error_to_dict(error) for error in errors]
        return details

    tests = getattr(stage, "_tests", None)
    if tests is not None:
        return _test_result_to_dict(tests, include_failure_output=True)

    errors = getattr(stage, "_errors", ())
    knockout_report = _knockout_report_from_errors(errors)
    if knockout_report is not None:
        return knockout_report.to_dict()
    artifact_report = _artifact_coverage_report_from_errors(errors)
    if artifact_report is not None:
        return artifact_report.to_dict()
    if errors:
        return {"errors": [_verify_error_to_dict(error) for error in errors]}

    return {}


def _format_verify_stage_details(stage) -> str:
    validation = getattr(stage, "_validation", None)
    if validation is not None and (
        not stage.success or _validation_has_warnings(validation)
    ):
        return _format_verify_validation_details(validation)

    coherence = getattr(stage, "_coherence", None)
    if coherence is not None and not stage.success:
        return format_coherence_result(coherence)

    file_tracking = getattr(stage, "_file_tracking", None)
    if file_tracking is not None and (not stage.success or file_tracking.scope_only):
        return format_file_tracking(file_tracking)

    tests = getattr(stage, "_tests", None)
    if tests is not None and not stage.success:
        return format_test_result(tests)

    errors = getattr(stage, "_errors", ())
    knockout_report = _knockout_report_from_errors(errors)
    if knockout_report is not None:
        return _format_knockout_report(knockout_report)
    artifact_report = _artifact_coverage_report_from_errors(errors)
    if artifact_report is not None:
        return _format_artifact_coverage_report(artifact_report)
    if errors:
        return "\n".join(_format_verify_error(error) for error in errors)

    return ""


def _format_verify_summary_stage_details(
    stage,
    *,
    grouped_recovery_suggestions: frozenset[str] = frozenset(),
) -> str:
    validation = getattr(stage, "_validation", None)
    if validation is not None and (
        not stage.success or _validation_has_warnings(validation)
    ):
        return _format_verify_summary_validation_details(
            validation,
            grouped_recovery_suggestions=grouped_recovery_suggestions,
        )

    return _format_verify_stage_details(stage)


def _verify_error_to_dict(error) -> dict | str:
    if hasattr(error, "to_dict"):
        return error.to_dict()
    return str(error)


def _artifact_coverage_report_from_errors(errors):
    if len(errors) != 1:
        return None
    report = errors[0]
    if hasattr(report, "findings") and hasattr(report, "errors"):
        return report
    return None


def _knockout_report_from_errors(errors):
    if len(errors) != 1:
        return None
    report = errors[0]
    if hasattr(report, "results") and hasattr(report, "errors"):
        return report
    return None


def _format_knockout_report(report) -> str:
    status = "PASS" if report.success else "FAIL"
    lines = [f"Knockout: {status}"]
    if getattr(report, "results", ()):
        lines.append(f"  Results: {len(report.results)}")
        for result in report.results:
            state = "detected" if result.detected else "not detected"
            name = result.artifact_name
            if result.parent_class:
                name = f"{result.parent_class}.{name}"
            lines.append(
                f"  {state}: {name} ({result.file_path}) "
                f"Duration: {result.duration_ms:.0f}ms"
            )
            proof = getattr(result, "proof", None)
            if proof is not None:
                detector = ", ".join(proof.detecting_nodeids) or "exact command"
                fallback = "yes" if proof.used_exact_fallback else "no"
                lines.append(f"    detector: {detector}")
                lines.append(f"    exact fallback: {fallback}")
                lines.append(
                    "    exits: "
                    f"baseline={proof.baseline_exit_code}, "
                    f"mutant={proof.mutant_exit_code}, "
                    f"restored={proof.restored_exit_code}"
                )
    if getattr(report, "errors", ()):
        lines.append(f"  Errors ({len(report.errors)}):")
        for error in report.errors:
            lines.extend(_format_validation_error_lines(error, indent="    "))
    return "\n".join(lines)


def _format_verify_error(error) -> str:
    if hasattr(error, "code") and hasattr(error, "message"):
        return "\n".join(_format_validation_error_lines(error, indent=""))
    return str(error)


def _format_verify_summary_error(
    error,
    *,
    grouped_recovery_suggestions: frozenset[str],
) -> str:
    if not (hasattr(error, "code") and hasattr(error, "message")):
        return str(error)
    code = getattr(getattr(error, "code", None), "value", None)
    suggestion = getattr(error, "suggestion", None)
    include_suggestion = not (
        code == "E701" and suggestion in grouped_recovery_suggestions
    )
    return "\n".join(
        _format_validation_error_lines(
            error,
            indent="",
            include_suggestion=include_suggestion,
        )
    )


def _format_verify_validation_details(validation) -> str:
    if isinstance(validation, BatchValidationResult):
        return _format_verify_batch_validation_details(validation)
    return _format_verify_single_validation_details(validation)


def _format_verify_summary_validation_details(
    validation,
    *,
    grouped_recovery_suggestions: frozenset[str] = frozenset(),
) -> str:
    if isinstance(validation, BatchValidationResult):
        return _format_verify_summary_batch_validation_details(
            validation,
            grouped_recovery_suggestions=grouped_recovery_suggestions,
        )
    return _format_verify_summary_single_validation_details(
        validation,
        grouped_recovery_suggestions=grouped_recovery_suggestions,
    )


def _format_verify_batch_validation_details(result: BatchValidationResult) -> str:
    lines = []
    for error in result.chain_errors:
        lines.extend(_format_verify_error(error).splitlines())
    for validation in result.results:
        if not validation.success or validation.warnings:
            status = "FAIL" if not validation.success else "WARN"
            lines.append(f"{status} {validation.manifest_slug}")
            lines.extend(
                _format_verify_single_validation_details(validation).splitlines()
            )
    return "\n".join(line for line in lines if line)


def _format_verify_summary_batch_validation_details(
    result: BatchValidationResult,
    *,
    grouped_recovery_suggestions: frozenset[str] = frozenset(),
) -> str:
    lines = []
    warning_count = 0
    warning_manifest_count = 0

    for error in result.chain_errors:
        if _is_warning(error):
            warning_count += 1
        else:
            lines.extend(_format_verify_error(error).splitlines())

    for validation in result.results:
        validation_warning_count = _validation_warning_count(validation)
        if validation_warning_count:
            warning_count += validation_warning_count
            warning_manifest_count += 1

        errors = [
            error
            for error in getattr(validation, "errors", ())
            if not _is_warning(error)
        ]
        if not validation.success and errors:
            lines.append(f"FAIL {validation.manifest_slug}")
            for error in errors:
                lines.extend(
                    f"  {line}"
                    for line in _format_verify_summary_error(
                        error,
                        grouped_recovery_suggestions=grouped_recovery_suggestions,
                    ).splitlines()
                )
        elif not validation.success and not validation_warning_count:
            lines.append(f"FAIL {validation.manifest_slug}")

    if warning_count:
        plural = "" if warning_count == 1 else "s"
        manifest_scope = (
            f" across {warning_manifest_count} manifests"
            if warning_manifest_count
            else ""
        )
        lines.append(
            f"{warning_count} raw validation warning{plural}"
            f"{manifest_scope}; see WARNINGS section below"
        )

    return "\n".join(line for line in lines if line)


def _format_verify_single_validation_details(validation) -> str:
    lines = []
    if not validation.success:
        for error in validation.errors:
            lines.extend(_format_verify_error(error).splitlines())
    for warning in validation.warnings:
        lines.extend(_format_verify_error(warning).splitlines())
    return "\n".join(f"  {line}" for line in lines)


def _format_verify_summary_single_validation_details(
    validation,
    *,
    grouped_recovery_suggestions: frozenset[str] = frozenset(),
) -> str:
    lines = []
    for error in getattr(validation, "errors", ()):
        if not _is_warning(error):
            lines.extend(
                _format_verify_summary_error(
                    error,
                    grouped_recovery_suggestions=grouped_recovery_suggestions,
                ).splitlines()
            )

    warning_count = _validation_warning_count(validation)
    if warning_count:
        plural = "" if warning_count == 1 else "s"
        lines.append(
            f"{warning_count} raw validation warning{plural}; "
            "see WARNINGS section below"
        )

    return "\n".join(f"  {line}" for line in lines)


def _validation_has_warnings(validation) -> bool:
    warnings = getattr(validation, "warnings", None)
    if warnings:
        return True

    results = getattr(validation, "results", ())
    if any(getattr(result, "warnings", ()) for result in results):
        return True

    return any(_is_warning(error) for error in getattr(validation, "chain_errors", ()))


def _validation_warning_count(validation) -> int:
    return sum(
        1 for warning in getattr(validation, "warnings", ()) if _is_warning(warning)
    )


def _is_warning(error) -> bool:
    severity = getattr(error, "severity", None)
    return getattr(severity, "value", severity) == "warning"


def _test_result_to_dict(
    result: BatchTestResult, *, include_failure_output: bool = False
) -> dict:
    return {
        "success": result.success,
        "total": result.total,
        "passed": result.passed,
        "failed": result.failed,
        "duration_ms": result.duration_ms,
        "chain_errors": [e.to_dict() for e in result.chain_errors],
        "scheduling_notices": [
            {
                "command_group": list(notice.command_group),
                "mode": notice.mode,
                "workers": notice.workers,
                "reason": notice.reason,
            }
            for notice in result.scheduling_notices
        ],
        "results": [
            {
                "manifest": r.manifest_slug,
                "command": list(r.command),
                "exit_code": r.exit_code,
                "success": r.success,
                "duration_ms": r.duration_ms,
                "stream": r.stream.value,
                **(
                    {"stdout_tail": r.stdout[-16_384:]}
                    if include_failure_output and not r.success and r.stdout
                    else {}
                ),
                **(
                    {"stderr_tail": r.stderr[-16_384:]}
                    if include_failure_output and not r.success and r.stderr
                    else {}
                ),
            }
            for r in result.results
        ],
    }


def _format_scheduling_notices(result: BatchTestResult) -> list[str]:
    return [
        (
            f"  Scheduling: {notice.mode} workers={notice.workers} "
            f"reason={notice.reason} command={' '.join(notice.command_group)}"
        )
        for notice in result.scheduling_notices
    ]


def _format_test_command_line(result) -> str:
    symbol = "PASS" if result.success else "FAIL"
    suffix = "" if result.success else f" (exit {result.exit_code})"
    return f"  {symbol} [{result.manifest_slug}] {' '.join(result.command)}{suffix}"


def format_file_tracking(
    report: FileTrackingReport,
    *,
    json_mode: bool = False,
    hide_private: bool = False,
) -> str:
    if json_mode:
        return json.dumps(
            {
                "tracked": [e.path for e in report.tracked],
                "registered": [e.path for e in report.registered],
                "scope_only": [e.path for e in report.scope_only],
                "undeclared": [e.path for e in report.undeclared],
            },
            indent=2,
        )

    lines = []
    if report.undeclared:
        lines.append(f"Undeclared ({len(report.undeclared)}):")
        for e in report.undeclared:
            if hide_private and e.path.split("/")[-1].startswith("_"):
                continue
            lines.append(f"  {e.path}")

    if report.registered:
        lines.append(f"Registered ({len(report.registered)}):")
        for e in report.registered:
            issues = ", ".join(e.issues) if e.issues else ""
            lines.append(f"  {e.path}" + (f" ({issues})" if issues else ""))

    if report.scope_only:
        lines.append(f"Scope-only ({len(report.scope_only)}):")
        for e in report.scope_only:
            lines.append(f"  {e.path}")

    if report.tracked:
        lines.append(f"Tracked ({len(report.tracked)}):")
        for e in report.tracked:
            lines.append(f"  {e.path}")

    return "\n".join(lines)


def format_bootstrap_report(
    report: "BootstrapReport",
    *,
    json_mode: bool = False,
    quiet: bool = False,
    verbose: bool = False,
) -> str:
    if json_mode:
        return json.dumps(
            {
                "total_discovered": report.total_discovered,
                "captured": report.captured,
                "skipped": report.skipped,
                "failed": report.failed,
                "excluded": report.excluded,
                "total_artifacts": report.total_artifacts,
                "manifests_dir": report.manifests_dir,
                "duration_ms": report.duration_ms,
                "results": [
                    {
                        "path": r.path,
                        "status": r.status,
                        "artifact_count": r.artifact_count,
                        "error": r.error,
                        "manifest_slug": r.manifest_slug,
                    }
                    for r in report.results
                ],
            },
            indent=2,
        )

    if quiet:
        if report.captured == 0:
            return ""
        return f"{report.captured} files captured ({report.total_artifacts} artifacts)"

    lines = []
    lines.append(f"Bootstrap: {report.total_discovered} source files discovered")
    lines.append(
        f"  Captured:  {report.captured} files ({report.total_artifacts} artifacts)"
    )
    lines.append(f"  Skipped:   {report.skipped} files (already tracked)")
    lines.append(f"  Failed:    {report.failed} files")

    if report.failed > 0:
        for r in report.results:
            if r.status == "failed":
                lines.append(f"    {r.path}: {r.error}")

    lines.append(f"  Excluded:  {report.excluded} files")

    if report.duration_ms is not None:
        lines.append(f"  Duration:  {report.duration_ms:.0f}ms")

    if report.manifests_dir:
        lines.append(f"  Manifests written to: {report.manifests_dir}")

    if verbose:
        lines.append("")
        for r in report.results:
            symbol = {
                "captured": "SNAP",
                "skipped": "SKIP",
                "failed": "FAIL",
                "excluded": "EXCL",
            }.get(r.status, "????")
            detail = ""
            if r.artifact_count:
                detail = f" ({r.artifact_count} artifacts)"
            if r.error:
                detail = f" — {r.error}"
            lines.append(f"  {symbol} {r.path}{detail}")

    return "\n".join(lines)


def format_chain_log(
    manifests: list,
    manifest_dir: str,
    *,
    json_mode: bool = False,
    active_only: bool = False,
) -> str:
    """Format manifest event-log entries for `maid chain log`.

    Args:
        manifests: List of Manifest objects sorted in event order.
        manifest_dir: Path to the manifest directory (for computing
            superseded status).
        json_mode: If True, output a JSON array of entry objects.
        active_only: If True, exclude superseded manifests.
    """
    # Compute superseded slugs so the formatter can mark them.
    superseded_slugs: set[str] = set()
    for m in manifests:
        for slug in m.supersedes:
            superseded_slugs.add(slug)

    if active_only:
        manifests = [m for m in manifests if m.slug not in superseded_slugs]

    if json_mode:
        entries = []
        for m in manifests:
            entries.append(
                {
                    "slug": m.slug,
                    "sequence_number": m.sequence_number,
                    "version_tag": m.version_tag,
                    "goal": m.goal,
                    "created": m.created,
                    "type": m.task_type.value if m.task_type else None,
                    "source_path": m.source_path,
                    "superseded": m.slug in superseded_slugs,
                    "supersedes": list(m.supersedes) if m.supersedes else [],
                }
            )
        return json.dumps(entries, indent=2)

    if not manifests:
        return "(no manifests)"

    # Column widths
    slug_w = max(max(len(m.slug) for m in manifests), 4)
    seq_w = max(
        max(
            len(str(m.sequence_number)) if m.sequence_number is not None else 1
            for m in manifests
        ),
        4,
    )
    created_w = max(max(len(m.created) if m.created else 0 for m in manifests), 7)
    tag_w = max(max(len(m.version_tag) if m.version_tag else 0 for m in manifests), 4)

    lines = []
    header = (
        f"{'SLUG':<{slug_w}}  {'SEQ#':>{seq_w}}  {'CREATED':<{created_w}}  "
        f"{'TAG':<{tag_w}}  {'STATUS':<8}  PATH"
    )
    lines.append(header)
    lines.append("-" * len(header))

    for m in manifests:
        seq_str = str(m.sequence_number) if m.sequence_number is not None else "-"
        created_str = m.created or "-"
        tag_str = m.version_tag or "-"
        status = "SUPERSEDED" if m.slug in superseded_slugs else "active"
        lines.append(
            f"{m.slug:<{slug_w}}  {seq_str:>{seq_w}}  {created_str:<{created_w}}  "
            f"{tag_str:<{tag_w}}  {status:<8}  {m.source_path}"
        )

    return "\n".join(lines)


def format_replay_result(
    result: dict,
    *,
    json_mode: bool = False,
) -> str:
    """Format replay_until() output for `maid chain replay`.

    Args:
        result: Dict mapping file_path -> list[ArtifactSpec].
        json_mode: If True, output JSON with full artifact identity.
    """
    if json_mode:
        data: dict = {}
        for path, artifacts in result.items():
            data[path] = [
                {
                    "kind": a.kind.value,
                    "name": a.name,
                    **({"of": a.of} if a.of else {}),
                    **({"returns": a.returns} if a.returns else {}),
                }
                for a in artifacts
            ]
        return json.dumps(data, indent=2)

    if not result:
        return "(no artifacts)"

    lines: list[str] = []
    for path, artifacts in sorted(result.items()):
        names = [a.name for a in artifacts]
        lines.append(f"{path}: {', '.join(names)}")
    return "\n".join(lines)


def format_chain_merge_report(
    report: "ChainMergeReport",
    *,
    json_mode: bool = False,
) -> str:
    """Format a ChainMergeReport for `maid chain merge`.

    Args:
        report: The read-only report built by build_chain_merge_report.
        json_mode: If True, output a single JSON document.
    """
    acceptance = report.acceptance
    from maid_runner.core.chain_merge import artifact_requires_knockout_detection

    detection_artifact_count = sum(
        artifact_requires_knockout_detection(artifact)
        for artifact in acceptance.required_artifacts
    )
    if json_mode:
        payload = {
            "file_path": report.file_path,
            "verdict": report.verdict.value,
            "active_manifest_count": report.active_manifest_count,
            "superseded_manifest_count": report.superseded_manifest_count,
            "distinct_artifact_count": report.distinct_artifact_count,
            "total_declaration_count": report.total_declaration_count,
            "redundant_declaration_count": report.redundant_declaration_count,
            "blocking_reasons": list(report.blocking_reasons),
            "acceptance": {
                "required_artifacts": list(acceptance.required_artifacts),
                "detection_available": acceptance.detection_available,
                "required_detecting_nodeids": {
                    key: list(nodeids)
                    for key, nodeids in acceptance.required_detecting_nodeids.items()
                },
                "unknown_detection_artifacts": list(
                    acceptance.unknown_detection_artifacts
                ),
                "coverage_available": acceptance.coverage_available,
                "required_covered_artifacts": list(
                    acceptance.required_covered_artifacts
                ),
                "uncovered_coverage_artifacts": list(
                    acceptance.uncovered_coverage_artifacts
                ),
                "unknown_coverage_artifacts": list(
                    acceptance.unknown_coverage_artifacts
                ),
            },
        }
        return json.dumps(payload, indent=2)

    lines = [
        f"{report.file_path}: {report.verdict.value.upper()}",
        f"  active manifests:      {report.active_manifest_count}",
        f"  superseded manifests:  {report.superseded_manifest_count}",
        f"  distinct artifacts:    {report.distinct_artifact_count}",
        f"  total declarations:    {report.total_declaration_count}",
        f"  redundant declarations:{report.redundant_declaration_count}",
    ]
    for reason in report.blocking_reasons:
        lines.append(f"  blocked: {reason}")
    if acceptance.detection_available:
        lines.append(
            f"  detection: recorded for "
            f"{len(acceptance.required_detecting_nodeids)}/"
            f"{detection_artifact_count} artifacts"
        )
    else:
        lines.append("  detection: UNKNOWN (no evidence source)")
    if acceptance.coverage_available:
        lines.append(
            f"  coverage: recorded for "
            f"{len(acceptance.required_covered_artifacts)}/"
            f"{len(acceptance.required_artifacts)} artifacts"
        )
        if acceptance.uncovered_coverage_artifacts:
            lines.append(
                "  coverage E710: " + ", ".join(acceptance.uncovered_coverage_artifacts)
            )
    else:
        lines.append("  coverage: UNKNOWN (no evidence source)")
    return "\n".join(lines)


def format_chain_merge_summary(
    summary: "ChainMergeSweepSummary",
    *,
    json_mode: bool = False,
) -> str:
    """Format a ChainMergeSweepSummary for `maid chain merge --all`."""
    if json_mode:
        payload = {
            "defrag_count": summary.defrag_count,
            "lean_count": summary.lean_count,
            "blocked_count": summary.blocked_count,
            "swept_file_count": summary.swept_file_count,
            "worst_offenders": list(summary.worst_offenders),
        }
        return json.dumps(payload, indent=2)

    lines = [
        f"swept {summary.swept_file_count} file(s): "
        f"{summary.defrag_count} DEFRAG, "
        f"{summary.lean_count} LEAN, "
        f"{summary.blocked_count} BLOCKED",
    ]
    if summary.worst_offenders:
        lines.append("worst offenders (by redundant declarations):")
        for path in summary.worst_offenders:
            lines.append(f"  {path}")
    return "\n".join(lines)


def format_chain_merge_equivalence_result(
    result: "MergeEquivalenceResult",
    *,
    json_mode: bool = False,
) -> str:
    """Format a chain-merge artifact-evidence equivalence result."""
    if json_mode:
        payload = {
            "file_path": result.file_path,
            "success": result.success,
            "detection_regressions": list(result.detection_regressions),
            "coverage_regressions": list(result.coverage_regressions),
            "evidence_regressions": list(result.evidence_regressions),
            "errors": [error.to_dict() for error in result.errors],
        }
        return json.dumps(payload, indent=2)

    if result.success:
        return f"{result.file_path}: EQUIVALENT"

    lines = [f"{result.file_path}: NOT EQUIVALENT"]
    for error in result.errors:
        lines.append(f"  {error.code.value} {error.message}")
    return "\n".join(lines)


def format_chain_merge_apply_result(
    result: "ChainMergeApplyResult",
    *,
    json_mode: bool = False,
) -> str:
    """Format a ChainMergeApplyResult for `maid chain merge --apply`."""
    if json_mode:
        payload = {
            "applied": result.applied,
            "snapshot_path": result.snapshot_path,
            "superseded_slugs": list(result.superseded_slugs),
            "refused_reason": result.refused_reason,
            "missing_artifacts": list(result.missing_artifacts),
        }
        return json.dumps(payload, indent=2)

    if result.applied:
        lines = [
            f"applied: wrote {result.snapshot_path}",
            f"  superseded {len(result.superseded_slugs)} manifest(s): "
            f"{', '.join(result.superseded_slugs)}",
        ]
        return "\n".join(lines)

    lines = [f"refused: {result.refused_reason}"]
    for key in result.missing_artifacts:
        lines.append(f"  missing: {key}")
    return "\n".join(lines)


def format_supersession_audit(
    violations: "list[SupersessionViolation]",
    grandfathered_count: int,
    sealed_at: "Optional[str]" = None,
    json_mode: bool = False,
) -> str:
    """Format supersession-audit results for `maid audit supersessions`.

    Args:
        violations: Non-grandfathered SupersessionViolation entries to surface.
        grandfathered_count: Count of violations exempted by the lock file.
        sealed_at: ISO timestamp the lock file was sealed (if applicable).
        json_mode: When True, emit a machine-readable JSON object.
    """
    if json_mode:
        return json.dumps(
            {
                "violations": [
                    {
                        "superseding_slug": v.superseding_slug,
                        "superseded_slug": v.superseded_slug,
                        "superseding_manifest_path": v.superseding_manifest_path,
                        "file_path": v.file_path,
                        "artifact_key": v.artifact_key,
                        "artifact_name": v.artifact_name,
                        "artifact_kind": v.artifact_kind,
                    }
                    for v in violations
                ],
                "grandfathered_count": grandfathered_count,
                "sealed_at": sealed_at,
            },
            indent=2,
        )

    lines: list[str] = []
    if not violations and grandfathered_count == 0:
        lines.append("Supersession audit: no violations.")
    else:
        lines.append(
            f"Supersession audit: {len(violations)} violation(s), "
            f"{grandfathered_count} grandfathered."
        )

    if grandfathered_count:
        lines.append(
            f"  Grandfathered (sealed lock): {grandfathered_count} artifact(s)"
        )
        if sealed_at:
            lines.append(f"  Sealed at: {sealed_at}")

    if violations:
        lines.append("")
        lines.append("Dropped artifacts:")
        for v in violations:
            lines.append(
                f"  - {v.superseding_slug} drops {v.artifact_name} "
                f"({v.artifact_kind}) at {v.file_path} "
                f"[from {v.superseded_slug}]"
            )

    return "\n".join(lines)


def format_coherence_result(
    result: CoherenceResult,
    *,
    json_mode: bool = False,
) -> str:
    if json_mode:
        return json.dumps(result.to_dict(), indent=2)

    lines = []
    status = "PASS" if result.success else "FAIL"
    lines.append(f"Coherence: {status}")
    lines.append(f"  Checks run: {', '.join(result.checks_run)}")
    lines.append(
        f"  Issues: {result.error_count} errors, {result.warning_count} warnings"
    )
    if result.duration_ms is not None:
        lines.append(f"  Duration: {result.duration_ms:.0f}ms")

    for issue in result.issues:
        sev = issue.severity.value.upper()
        loc = f" [{issue.file}]" if issue.file else ""
        lines.append(f"  {sev}{loc} {issue.message}")

    return "\n".join(lines)
