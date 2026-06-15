"""Shared helpers for packet-aware MAID agent retry loops."""

from __future__ import annotations

import json
import re
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Union

_AUTOMATION_STATUSES = {"READY", "NEEDS_CHANGES", "BLOCKED", "NO_DRAFTS"}


@dataclass(frozen=True)
class CommitPacket:
    """Parsed READY commit message and exact file list."""

    message: str
    files: list[str]


@dataclass(frozen=True)
class RetryLoopResult:
    """Outcome of one bounded packet-consuming retry loop run."""

    attempts: int
    success: bool
    escalated: bool
    final_packet: dict | None


def find_implementable_drafts(draft_dir: Path) -> list[Path]:
    """Return non-epic draft MAID manifests that remain to be implemented."""
    if not draft_dir.exists():
        return []
    return sorted(path for path in draft_dir.glob("*.manifest.yaml") if path.is_file())


def parse_automation_status(final_message: str) -> str | None:
    """Extract the final AUTOMATION_STATUS marker from an agent final message."""
    matches = re.findall(r"(?im)^AUTOMATION_STATUS:\s*([A-Z_]+)\s*$", final_message)
    for match in reversed(matches):
        if match in _AUTOMATION_STATUSES:
            return match
    return None


def parse_commit_packet(final_message: str) -> CommitPacket | None:
    """Extract the last complete READY commit packet from an agent final message."""
    packets: list[CommitPacket] = []
    lines = final_message.splitlines()
    index = 0

    while index < len(lines):
        line = lines[index]
        message_match = re.match(
            r"(?i)^AUTOMATION_COMMIT_MESSAGE:\s*(.+?)\s*$",
            line,
        )
        if message_match is None:
            index += 1
            continue

        message = message_match.group(1).strip()
        index += 1
        while index < len(lines) and not re.match(
            r"(?i)^AUTOMATION_COMMIT_(?:MESSAGE|FILES):",
            lines[index],
        ):
            index += 1

        if index >= len(lines) or not re.match(
            r"(?i)^AUTOMATION_COMMIT_FILES:",
            lines[index],
        ):
            continue

        index += 1
        files: list[str] = []
        while index < len(lines):
            stripped = lines[index].strip()
            if not stripped.startswith("- "):
                break
            path = stripped[2:].strip()
            if path:
                files.append(path)
            index += 1

        if message and files:
            packets.append(CommitPacket(message=message, files=files))

    if not packets:
        return None
    return packets[-1]


def git_status_short(root: Path) -> str:
    """Return `git status --short` output for worktree preflight."""
    process = subprocess.run(
        ["git", "status", "--short"],
        cwd=root,
        text=True,
        capture_output=True,
        check=False,
    )
    if process.returncode != 0:
        raise RuntimeError(process.stderr.strip() or "git status failed")
    return process.stdout


def stage_commit_packet_files(files: list[str], root: Path) -> int:
    """Stage exact existing or tracked-deleted files named by a READY packet."""
    existing_files: list[str] = []
    tracked_missing_files: list[str] = []
    missing_untracked_files: list[str] = []
    invalid_files: list[str] = []

    for path in files:
        if not _is_repo_relative_file_path(path):
            invalid_files.append(path)
            continue
        absolute_path = root / path
        if absolute_path.exists():
            if absolute_path.is_file():
                existing_files.append(path)
            else:
                invalid_files.append(path)
        elif _git_path_is_tracked(path, root):
            tracked_missing_files.append(path)
        else:
            missing_untracked_files.append(path)

    if invalid_files or missing_untracked_files:
        print("Refusing invalid commit packet file paths:", file=sys.stderr)
        for path in invalid_files:
            print(f"  - {path}", file=sys.stderr)
        for path in missing_untracked_files:
            print(f"  - {path}", file=sys.stderr)
        return 1

    if existing_files:
        add_existing = _run_git(["add", "--", *existing_files], root)
        if add_existing.returncode != 0:
            return add_existing.returncode

    if tracked_missing_files:
        add_missing = _run_git(["add", "-A", "--", *tracked_missing_files], root)
        if add_missing.returncode != 0:
            return add_missing.returncode

    return 0


def commit_ready_changes(packet: CommitPacket, root: Path) -> int:
    """Stage and commit a READY packet after approval."""
    print("Staging commit packet files:")
    for path in packet.files:
        print(f"  - {path}")

    stage_returncode = stage_commit_packet_files(packet.files, root)
    if stage_returncode != 0:
        return stage_returncode

    commit = _run_git(["commit", "-m", packet.message], root)
    return commit.returncode


def ask_commit_approval(pass_number: int, status: str) -> bool:
    """Require a per-pass typed approval before committing a READY packet."""
    if not sys.stdin.isatty():
        print(
            f"Pass {pass_number} reached {status}, but commit approval requires an interactive terminal.",
            file=sys.stderr,
        )
        return False
    answer = input(
        f"Pass {pass_number} is {status}. Type 'commit' to approve this commit: "
    )
    return answer.strip().lower() == "commit"


def read_failure_packet(path: Union[str, Path]) -> dict | None:
    """Read a failure packet JSON file, returning None when it is unavailable."""
    packet_path = Path(path)
    try:
        value = json.loads(packet_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    if not isinstance(value, dict):
        return None
    return value


def run_bounded_retry_loop(
    run_gate: Callable[[], int],
    run_attempt: Callable[[dict | None], str],
    packet_path: Union[str, Path],
    max_attempts: int = 5,
) -> RetryLoopResult:
    """Run the documented packet-consuming gate/attempt loop."""
    if run_gate() == 0:
        return RetryLoopResult(
            attempts=0,
            success=True,
            escalated=False,
            final_packet=None,
        )

    final_packet: dict | None = None
    attempts = max(0, max_attempts)
    for attempt_number in range(1, attempts + 1):
        packet = read_failure_packet(packet_path)
        final_packet = packet
        outcome = run_attempt(packet)
        print(f"attempt {attempt_number}: {outcome}")

        if run_gate() == 0:
            return RetryLoopResult(
                attempts=attempt_number,
                success=True,
                escalated=False,
                final_packet=final_packet,
            )
        final_packet = read_failure_packet(packet_path)

    print(f"Escalating to human after {attempts} failed attempts.")
    print(f"Final failure packet path: {Path(packet_path)}")
    if final_packet is not None:
        print(json.dumps(final_packet, indent=2, sort_keys=True))
    return RetryLoopResult(
        attempts=attempts,
        success=False,
        escalated=True,
        final_packet=final_packet,
    )


def _run_git(args: list[str], root: Path) -> subprocess.CompletedProcess[str]:
    process = subprocess.run(
        ["git", *args],
        cwd=root,
        text=True,
        capture_output=True,
        check=False,
    )
    if process.stdout:
        sys.stdout.write(process.stdout)
    if process.stderr:
        sys.stderr.write(process.stderr)
    return process


def _git_path_is_tracked(path: str, root: Path) -> bool:
    process = subprocess.run(
        ["git", "ls-files", "--error-unmatch", "--", path],
        cwd=root,
        text=True,
        capture_output=True,
        check=False,
    )
    return process.returncode == 0


def _is_repo_relative_file_path(path: str) -> bool:
    candidate = Path(path)
    if candidate.is_absolute():
        return False
    return path not in {"", "."} and ".." not in candidate.parts
