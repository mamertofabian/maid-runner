#!/usr/bin/env python3
"""Refresh the website's MAID in practice numbers from real command runs.

Runs `maid validate`, the full pytest suite, and `maid test`, then rewrites
website/data/practice-stats.json and the numbers and "as of" date mirrored in
website/index.html. Nothing is written unless every run passes and parses, so
a failing run never publishes "passing" numbers.

Usage:
    uv run python scripts/update_practice_stats.py
"""

from __future__ import annotations

import copy
import json
import os
import re
import subprocess
import sys
from collections.abc import Callable
from datetime import date
from pathlib import Path

_VALIDATE_COMMAND = ["uv", "run", "maid", "validate"]
_PYTEST_COMMAND = ["uv", "run", "python", "-m", "pytest", "tests/", "-q", "-n", "auto"]
_MAID_TEST_COMMAND = ["uv", "run", "maid", "test"]

_MONTHS = (
    "January",
    "February",
    "March",
    "April",
    "May",
    "June",
    "July",
    "August",
    "September",
    "October",
    "November",
    "December",
)

_REFRESHED_PROJECT = "maidRunner"

_STAT_RE = re.compile(r'(data-stat="([\w]+)\.([\w]+)">)([^<]*)(<)')
_DATE_RE = re.compile(
    r'(<time data-stat-date="(\w+)" datetime=")[\d-]+(">)[^<]*(</time>)'
)


def _int_after(pattern: str, output: str, what: str) -> int:
    match = re.search(pattern, output)
    if not match:
        raise ValueError(f"No {what} found in command output")
    return int(match.group(1))


def parse_validated_manifest_count(output: str) -> int:
    """Total manifests from `maid validate`; refuses runs with failures."""
    block = re.search(
        r"Validation Results:\s*(\d+)\s+manifests\s*\n\s*Passed:\s*\d+\s*\n\s*Failed:\s*(\d+)",
        output,
    )
    if not block:
        raise ValueError("No maid validate results summary found in command output")
    total, failed = (int(value) for value in block.groups())
    if failed:
        raise ValueError(f"maid validate reported {failed} failing manifests")
    return total


def parse_pytest_passed_count(output: str) -> int:
    """Passed count from the final pytest summary; refuses failures and errors."""
    # The summary is the last line made only of "N outcome" counts ending in
    # "in N.Ns"; failure messages and stderr lines may mention "N passed" too.
    summaries = re.findall(
        r"^=*\s*(\d+ [a-z]+(?:, \d+ [a-z]+)*) in [\d.]+s\b.*$",
        output,
        re.MULTILINE,
    )
    if not summaries:
        raise ValueError("No pytest summary found in command output")
    counts = summaries[-1]
    if re.search(r"\b\d+ (failed|errors?)\b", counts):
        raise ValueError(f"pytest run did not pass cleanly: {counts}")
    passed = re.search(r"(\d+) passed\b", counts)
    if not passed:
        raise ValueError(f"pytest summary has no passed count: {counts}")
    return int(passed.group(1))


def parse_maid_test_command_count(output: str) -> int:
    """Command total from the top `Test Results` block of `maid test`."""
    block = re.search(
        r"Test Results:\s*(\d+)\s+commands\s*\n\s*Passed:\s*(\d+)\s*\n\s*Failed:\s*(\d+)",
        output,
    )
    if not block:
        raise ValueError("No maid test results summary found in command output")
    total, passed, failed = (int(value) for value in block.groups())
    if failed or passed != total:
        raise ValueError(f"maid test did not pass cleanly: {passed}/{total} passed")
    return total


def collect_maid_runner_counts(run: Callable[[list[str]], str]) -> dict[str, int]:
    """Run each evidence command once and parse its counts."""
    return {
        "manifests": parse_validated_manifest_count(run(_VALIDATE_COMMAND)),
        "tests": parse_pytest_passed_count(run(_PYTEST_COMMAND)),
        "maidCommandGroups": parse_maid_test_command_count(run(_MAID_TEST_COMMAND)),
    }


def refresh_practice_stats(stats: dict, counts: dict[str, int], today: date) -> dict:
    """Return a copy with the MAID Runner counts and date replaced."""
    refreshed = copy.deepcopy(stats)
    refreshed["maidRunner"] = {"updatedAt": today.isoformat(), **counts}
    return refreshed


def _display_date(day: date) -> str:
    return f"{_MONTHS[day.month - 1]} {day.day}, {day.year}"


def render_practice_stats_html(html: str, stats: dict) -> str:
    """Rewrite data-stat values and data-stat-date times from the stats."""

    def stat(match: re.Match[str]) -> str:
        project, key = match.group(2), match.group(3)
        if key not in stats.get(project, {}) or key == "updatedAt":
            raise KeyError(f"{project}.{key}")
        return f"{match.group(1)}{stats[project][key]}{match.group(5)}"

    def stamp(match: re.Match[str]) -> str:
        updated = stats[match.group(2)]["updatedAt"]
        shown = _display_date(date.fromisoformat(updated))
        return f"{match.group(1)}{updated}{match.group(3)}{shown}{match.group(4)}"

    rendered, stat_count = _STAT_RE.subn(stat, html)
    rendered, _date_count = _DATE_RE.subn(stamp, rendered)

    # The refreshed project must be fully mirrored, or the page would keep old
    # numbers or an old date beside a new JSON file.
    refreshed = stats.get(_REFRESHED_PROJECT, {})
    expected = {
        f"{_REFRESHED_PROJECT}.{key}" for key in refreshed if key != "updatedAt"
    }
    found = {f"{match.group(2)}.{match.group(3)}" for match in _STAT_RE.finditer(html)}
    dated = {match.group(2) for match in _DATE_RE.finditer(html)}
    missing = sorted(expected - found)
    if refreshed and _REFRESHED_PROJECT not in dated:
        missing.append(f"{_REFRESHED_PROJECT} date")
    if missing:
        raise ValueError(f"Page is missing mirrored practice stats: {missing}")
    return rendered


def run_command(command: list[str]) -> str:
    """Run a command, returning stdout and stderr; raise on a nonzero exit."""
    completed = subprocess.run(command, capture_output=True, text=True, check=False)
    output = completed.stdout + completed.stderr
    if completed.returncode != 0:
        # Summaries print first (maid test) or last (pytest); show both ends.
        lines = output.splitlines()
        excerpt = lines if len(lines) <= 30 else [*lines[:10], "...", *lines[-20:]]
        raise RuntimeError(
            f"{' '.join(command)} exited with {completed.returncode}:\n"
            + "\n".join(excerpt)
        )
    return output


def update_practice_stats(
    website_dir: Path, run: Callable[[list[str]], str], today: date
) -> dict:
    """Refresh the stats JSON and its HTML mirror; write only if all runs pass."""
    stats_path = website_dir / "data" / "practice-stats.json"
    page_path = website_dir / "index.html"
    stats = json.loads(stats_path.read_text(encoding="utf-8"))

    refreshed = refresh_practice_stats(stats, collect_maid_runner_counts(run), today)
    page = render_practice_stats_html(page_path.read_text(encoding="utf-8"), refreshed)

    # Stage both files, then swap them in. This keeps the window in which the
    # JSON and the page disagree to two renames; it is not a cross-file atomic
    # write, and the published-page test catches any mismatch.
    staged = []
    try:
        for path, content in (
            (stats_path, json.dumps(refreshed, indent=2) + "\n"),
            (page_path, page),
        ):
            temporary = path.with_name(f".{path.name}.tmp")
            temporary.write_text(content, encoding="utf-8")
            staged.append((temporary, path))
        for temporary, path in staged:
            os.replace(temporary, path)
    finally:
        for temporary, _path in staged:
            temporary.unlink(missing_ok=True)
    return refreshed


def _main() -> int:
    # The evidence commands use repository-relative paths.
    root = Path(__file__).resolve().parents[1]
    os.chdir(root)
    website = root / "website"
    refreshed = update_practice_stats(website, run_command, date.today())
    print(json.dumps(refreshed["maidRunner"], indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(_main())
