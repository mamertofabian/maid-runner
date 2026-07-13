"""CLI adapter for trustworthy pgTAP red-phase exit semantics."""

from __future__ import annotations

import argparse
import re
import subprocess
import sys

from maid_runner.cli.commands._format import print_error


_PGTAP_NOT_OK = re.compile(r"^\s*not ok\s+[0-9]+\s+-", re.MULTILINE)
_PGTAP_FAILURE_SUMMARY = re.compile(
    r"^\s*psql:[^\n]*:\s+ERROR:\s+pgTAP failures:\s*$",
    re.MULTILINE,
)
_PSQL_EARLY_EXIT_LONG_OPTIONS = ("--help", "--list", "--version")
_PSQL_SHORT_OPTIONS_WITH_VALUES = frozenset("cdfvLoFPRThpU")


def cmd_pgtap(args: argparse.Namespace) -> int:
    """Run file-backed pgTAP through psql with MAID-safe exit semantics."""
    psql_args = list(args.psql_args)
    if psql_args and psql_args[0] == "--":
        psql_args = psql_args[1:]

    error = _invocation_error(psql_args)
    if error is not None:
        print_error(error)
        return 2

    command = [
        args.psql,
        "-X",
        "-v",
        "ON_ERROR_STOP=1",
        *psql_args,
    ]
    try:
        result = subprocess.run(command, capture_output=True, text=True)
    except OSError as exc:
        print_error(f"Unable to start psql for pgTAP: {exc}")
        return 2

    sys.stdout.write(result.stdout)
    sys.stderr.write(result.stderr)

    if result.returncode == 0:
        return 0

    if result.returncode == 3 and _has_pgtap_failure_marker(
        result.stdout, result.stderr
    ):
        _print_result_diagnostic(
            "MAID pgTAP: pgTAP assertion failure detected from psql exit 3",
            result.stderr,
        )
        return 1

    _print_result_diagnostic(
        "MAID pgTAP: "
        f"psql exit {result.returncode} is invalid red-phase evidence "
        "without an anchored pgTAP failure marker",
        result.stderr,
    )
    return 2


def _invocation_error(psql_args: list[str]) -> str | None:
    if not _has_file_target(psql_args):
        return "maid pgtap requires a non-empty -f/--file SQL test target"
    if _has_early_exit_option(psql_args):
        return "maid pgtap rejects psql help, version, and list early-exit options"
    if _overrides_on_error_stop(psql_args):
        return "maid pgtap controls ON_ERROR_STOP; remove the caller override"
    return None


def _has_file_target(psql_args: list[str]) -> bool:
    for index, value in enumerate(psql_args):
        if value == "--file":
            return index + 1 < len(psql_args) and bool(psql_args[index + 1])
        if value.startswith("--file="):
            return bool(value.removeprefix("--file="))
        if not value.startswith("-") or value.startswith("--"):
            continue
        short_options = value[1:]
        for option_index, short_option in enumerate(short_options):
            if short_option == "f":
                attached_target = short_options[option_index + 1 :]
                return bool(attached_target) or (
                    index + 1 < len(psql_args) and bool(psql_args[index + 1])
                )
            if short_option in _PSQL_SHORT_OPTIONS_WITH_VALUES:
                break
    return False


def _overrides_on_error_stop(psql_args: list[str]) -> bool:
    return any("ON_ERROR_STOP" in value.upper() for value in psql_args)


def _has_early_exit_option(psql_args: list[str]) -> bool:
    for value in psql_args:
        option = value.split("=", 1)[0]
        if option.startswith("--") and len(option) > 2:
            if any(
                full_option.startswith(option)
                for full_option in _PSQL_EARLY_EXIT_LONG_OPTIONS
            ):
                return True
            continue
        if not option.startswith("-") or option.startswith("--"):
            continue
        for short_option in option[1:]:
            if short_option in {"?", "V", "l"}:
                return True
            if short_option in _PSQL_SHORT_OPTIONS_WITH_VALUES:
                break
    return False


def _has_pgtap_failure_marker(stdout: str, stderr: str) -> bool:
    return bool(_PGTAP_NOT_OK.search(stdout) or _PGTAP_FAILURE_SUMMARY.search(stderr))


def _print_result_diagnostic(message: str, stderr: str) -> None:
    if stderr and not stderr.endswith("\n"):
        sys.stderr.write("\n")
    print(message, file=sys.stderr)
