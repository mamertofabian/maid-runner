"""Output formatters for MAID Runner v2 CLI."""

from __future__ import annotations

import json
import sys
from typing import TYPE_CHECKING

from maid_runner.core.result import (
    BatchTestResult,
    BatchValidationResult,
    FileTrackingReport,
    ValidationResult,
)
from maid_runner.coherence.result import CoherenceResult

if TYPE_CHECKING:
    pass


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
) -> str:
    if json_mode:
        return result.to_json()

    if quiet:
        if result.success:
            return ""
        lines = []
        for err in result.errors:
            lines.append(f"  {err.code.value} {err.message}")
        return "\n".join(lines)

    lines = []
    symbol = "PASS" if result.success else "FAIL"
    lines.append(f"{symbol} {result.manifest_slug}")
    lines.append(f"  Mode: {result.mode.value}")
    if result.duration_ms is not None:
        lines.append(f"  Duration: {result.duration_ms:.0f}ms")

    if result.errors:
        lines.append(f"  Errors ({len(result.errors)}):")
        for err in result.errors:
            lines.append(f"    {err.code.value} {err.message}")

    if result.warnings:
        lines.append(f"  Warnings ({len(result.warnings)}):")
        for w in result.warnings:
            lines.append(f"    {w.code.value} {w.message}")

    return "\n".join(lines)


def format_batch_result(
    result: BatchValidationResult,
    *,
    json_mode: bool = False,
    quiet: bool = False,
) -> str:
    if json_mode:
        return json.dumps(result.to_dict(), indent=2)

    if quiet:
        lines = []
        for r in result.results:
            if not r.success:
                lines.append(f"FAIL {r.manifest_slug}")
                for err in r.errors:
                    lines.append(f"  {err.code.value} {err.message}")
        return "\n".join(lines)

    lines = []
    lines.append(f"Validation Results: {result.total_manifests} manifests")
    lines.append(f"  Passed: {result.passed}")
    lines.append(f"  Failed: {result.failed}")
    if result.skipped:
        lines.append(f"  Skipped: {result.skipped} (superseded)")
    if result.duration_ms is not None:
        lines.append(f"  Duration: {result.duration_ms:.0f}ms")

    for r in result.results:
        if not r.success:
            lines.append("")
            lines.append(format_validation_result(r))

    return "\n".join(lines)


def format_test_result(
    result: BatchTestResult,
    *,
    verbose: bool = False,
    json_mode: bool = False,
) -> str:
    if json_mode:
        return json.dumps(
            {
                "success": result.success,
                "total": result.total,
                "passed": result.passed,
                "failed": result.failed,
                "duration_ms": result.duration_ms,
                "results": [
                    {
                        "manifest": r.manifest_slug,
                        "command": list(r.command),
                        "exit_code": r.exit_code,
                        "success": r.success,
                        "duration_ms": r.duration_ms,
                    }
                    for r in result.results
                ],
            },
            indent=2,
        )

    lines = []
    lines.append(f"Test Results: {result.total} commands")
    lines.append(f"  Passed: {result.passed}")
    lines.append(f"  Failed: {result.failed}")
    if result.duration_ms is not None:
        lines.append(f"  Duration: {result.duration_ms:.0f}ms")

    for r in result.results:
        symbol = "PASS" if r.success else "FAIL"
        lines.append(f"  {symbol} [{r.manifest_slug}] {' '.join(r.command)}")
        if verbose and r.stdout:
            for line in r.stdout.strip().splitlines():
                lines.append(f"    {line}")
        if not r.success and r.stderr:
            for line in r.stderr.strip().splitlines():
                lines.append(f"    {line}")

    return "\n".join(lines)


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

    if report.tracked:
        lines.append(f"Tracked ({len(report.tracked)}):")
        for e in report.tracked:
            lines.append(f"  {e.path}")

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
