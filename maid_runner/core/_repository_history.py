"""Repository-wide Git history collection for coverage recommendations."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
import re
import subprocess
from typing import Collection


@dataclass(frozen=True)
class _HistoryMetrics:
    commits_90: int = 0
    commits_365: int = 0
    lines_365: int = 0
    active_months: int = 0
    days_since_change: int | None = None
    confidence: str = "high"
    evidence: tuple[str, ...] = ()


@dataclass(frozen=True)
class _RepositoryHistory:
    repository_head: str | None
    metrics: dict[str, _HistoryMetrics]
    warnings: tuple[str, ...] = ()


def _build_repository_history(
    project_root: Path,
    paths: Collection[str],
) -> _RepositoryHistory:
    normalized = {str(path).replace("\\", "/") for path in paths}
    empty = {path: _HistoryMetrics() for path in normalized}
    head = _git_text(project_root, ("rev-parse", "HEAD"))
    shallow_text = _git_text(project_root, ("rev-parse", "--is-shallow-repository"))
    shallow = shallow_text == "true"

    try:
        result = subprocess.run(
            [
                "git",
                "log",
                "--numstat",
                "--find-renames",
                "--date=unix",
                "--format=commit:%H%x09%ct",
                "--since=365.days",
                "--",
                ".",
            ],
            cwd=project_root,
            capture_output=True,
            text=True,
            timeout=30,
        )
    except (FileNotFoundError, subprocess.TimeoutExpired) as exc:
        warning = f"Git history unavailable: {exc}"
        unknown = {
            path: _HistoryMetrics(
                confidence="low",
                evidence=(warning,),
            )
            for path in normalized
        }
        return _RepositoryHistory(head or None, unknown, (warning,))

    if result.returncode != 0:
        detail = (result.stderr or result.stdout).strip()
        warning = f"Git history unavailable: {detail or 'git log failed'}"
        unknown = {
            path: _HistoryMetrics(
                confidence="low",
                evidence=(warning,),
            )
            for path in normalized
        }
        return _RepositoryHistory(head or None, unknown, (warning,))

    now = datetime.now(timezone.utc)
    by_path: dict[str, dict[str, object]] = {
        path: {
            "commits_90": set(),
            "commits_365": set(),
            "lines": 0,
            "months": set(),
            "latest": None,
            "binary": False,
        }
        for path in normalized
    }
    aliases: dict[str, str] = {}
    current_commit = ""
    current_timestamp: int | None = None

    for line in result.stdout.splitlines():
        if line.startswith("commit:"):
            fields = line.removeprefix("commit:").split("\t", 1)
            current_commit = fields[0]
            try:
                current_timestamp = int(fields[1])
            except (IndexError, ValueError):
                current_timestamp = None
            continue
        fields = line.split("\t", 2)
        if len(fields) != 3 or not current_commit:
            continue
        old_path, changed_path = _rename_paths(fields[2])
        current_path = aliases.get(changed_path, changed_path)
        if old_path is not None:
            aliases[old_path] = current_path
        if current_path not in by_path or current_timestamp is None:
            continue

        record = by_path[current_path]
        timestamp = datetime.fromtimestamp(current_timestamp, tz=timezone.utc)
        age_days = max((now - timestamp).days, 0)
        commits_365 = record["commits_365"]
        assert isinstance(commits_365, set)
        commits_365.add(current_commit)
        if age_days <= 90:
            commits_90 = record["commits_90"]
            assert isinstance(commits_90, set)
            commits_90.add(current_commit)
        months = record["months"]
        assert isinstance(months, set)
        months.add((timestamp.year, timestamp.month))
        latest = record["latest"]
        if latest is None or current_timestamp > latest:
            record["latest"] = current_timestamp
        if fields[0] == "-" or fields[1] == "-":
            record["binary"] = True
        else:
            try:
                record["lines"] = int(record["lines"]) + int(fields[0]) + int(fields[1])
            except ValueError:
                record["binary"] = True

    metrics: dict[str, _HistoryMetrics] = {}
    for path, record in by_path.items():
        evidence: list[str] = []
        confidence = "high"
        if shallow:
            confidence = "low"
            evidence.append("Git repository is shallow; older history may be absent")
        if bool(record["binary"]):
            confidence = "low"
            evidence.append("Binary numstat entries omit changed-line counts")
        latest = record["latest"]
        days_since = (
            max(
                (now - datetime.fromtimestamp(int(latest), tz=timezone.utc)).days,
                0,
            )
            if latest is not None
            else None
        )
        metrics[path] = _HistoryMetrics(
            commits_90=len(record["commits_90"]),
            commits_365=len(record["commits_365"]),
            lines_365=int(record["lines"]),
            active_months=len(record["months"]),
            days_since_change=days_since,
            confidence=confidence,
            evidence=tuple(evidence),
        )

    return _RepositoryHistory(head or None, metrics or empty)


def _git_text(project_root: Path, argv: tuple[str, ...]) -> str:
    try:
        result = subprocess.run(
            ["git", *argv],
            cwd=project_root,
            capture_output=True,
            text=True,
            timeout=10,
        )
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return ""
    if result.returncode != 0:
        return ""
    return result.stdout.strip()


_BRACED_RENAME = re.compile(r"^(.*)\{([^{}]+) => ([^{}]+)\}(.*)$")


def _rename_paths(raw: str) -> tuple[str | None, str]:
    path = raw.replace("\\", "/")
    match = _BRACED_RENAME.match(path)
    if match:
        prefix, old, new, suffix = match.groups()
        return f"{prefix}{old}{suffix}", f"{prefix}{new}{suffix}"
    if " => " in path:
        old, new = path.split(" => ", 1)
        return old, new
    return None, path
