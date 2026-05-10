#!/usr/bin/env python3
"""Automate fresh-session Claude Code runs for maid-runner MAID drafts."""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import threading
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


_ROOT = Path(__file__).resolve().parents[1]
_DRAFT_DIR = _ROOT / "manifests" / "drafts"
_DEFAULT_LOG_ROOT = _ROOT / ".claude-automation" / "runs"
_DEFAULT_MAX_PASSES = 100
_DEFAULT_BATCH_SIZE = 1
_DEFAULT_MODEL = "sonnet"
_DEFAULT_EFFORT = "medium"
_DEFAULT_PERMISSION_MODE = "auto"
_AUTOMATION_STATUSES = {"READY", "NEEDS_CHANGES", "BLOCKED", "NO_DRAFTS"}
_EFFORTS = {"low", "medium", "high", "xhigh", "max"}
_PERMISSION_MODES = {
    "default",
    "acceptEdits",
    "bypassPermissions",
    "dontAsk",
    "plan",
    "auto",
}
_COLOR_MODES = {"auto", "always", "never"}
_ANSI_RESET = "\033[0m"
_ANSI_COLORS = {
    "system": "\033[2;37m",
    "assistant": "\033[36m",
    "result": "\033[32m",
    "error": "\033[31m",
}

_IMPLEMENTATION_PROMPT = """Use the maid-runner-draft-implement skill to continue implementing MAID draft manifests in this repo. If that skill is not listed in the session's available skills, read .claude/skills/maid-runner-draft-implement/SKILL.md and follow it before editing.

Automation reporting requirements:
- Keep doing the skill's validation and review loop until the pass is genuinely
  ready, blocked, or there are no implementable draft manifests.
- Use the Agent tool for a read-only review subagent with
  subagent_type="maid-implementation-reviewer". Pass the manifest path,
  changed files, current diff summary, and validation output explicitly instead
  of relying on hidden conversation context.
- When READY, include a commit packet for the outer automation script:
  AUTOMATION_COMMIT_MESSAGE: <conventional commit message>
  AUTOMATION_COMMIT_FILES:
  - <path>
  - <path>
  Include every changed tracked, deleted, and untracked file that belongs in
  the commit.
- End your final message with exactly one status line:
  AUTOMATION_STATUS: READY
  AUTOMATION_STATUS: NEEDS_CHANGES
  AUTOMATION_STATUS: BLOCKED
  AUTOMATION_STATUS: NO_DRAFTS
- Use READY only when the implementation is ready to merge and the next user
  action should be `commit`.
"""


@dataclass(frozen=True)
class ClaudeRunResult:
    """Captured result paths and metadata for one Claude Code pass."""

    args: list[str]
    returncode: int
    session_id: str | None
    final_message: str
    stdout_jsonl_path: Path
    stderr_path: Path
    final_message_path: Path


@dataclass(frozen=True)
class CommitPacket:
    """Parsed READY commit message and exact file list."""

    message: str
    files: list[str]


def find_implementable_drafts(draft_dir: Path = _DRAFT_DIR) -> list[Path]:
    """Return non-epic draft MAID manifests that remain to be implemented."""
    if not draft_dir.exists():
        return []
    return sorted(path for path in draft_dir.glob("*.manifest.yaml") if path.is_file())


def build_implementation_command(
    claude: str,
    selected_drafts: list[Path],
    model: str = _DEFAULT_MODEL,
    effort: str = _DEFAULT_EFFORT,
    permission_mode: str = _DEFAULT_PERMISSION_MODE,
) -> list[str]:
    """Build a fresh `claude -p --verbose --output-format stream-json` command."""
    return [
        claude,
        "-p",
        "--verbose",
        "--output-format",
        "stream-json",
        "--permission-mode",
        permission_mode,
        "--model",
        model,
        "--effort",
        effort,
        _implementation_prompt(selected_drafts),
    ]


def render_claude_stream_event(
    event: dict[str, Any],
    state: dict[str, Any],
    color_enabled: bool = False,
) -> str:
    """Render documented Claude Code stream-json events as terminal progress."""
    event_type = event.get("type")

    if event_type == "system":
        subtype = event.get("subtype", "event")
        if subtype == "init":
            session_id = event.get("session_id")
            if isinstance(session_id, str):
                state["session_id"] = session_id
                label = _label("[system]", "system", color_enabled=color_enabled)
                return f"{label} init session={session_id}\n"
        if isinstance(subtype, str) and subtype.startswith("task_"):
            return _render_task_system_event(event, color_enabled=color_enabled)
        label = _label("[system]", "system", color_enabled=color_enabled)
        return f"{label} {subtype}\n"

    if event_type == "assistant":
        text = _extract_assistant_text(event.get("message"))
        if not text:
            return ""
        state["last_assistant_text"] = text.rstrip()
        label = _label("[assistant]", "assistant", color_enabled=color_enabled)
        return f"\n{label}\n{text.rstrip()}\n"

    if event_type == "result":
        result = event.get("result")
        if isinstance(result, str):
            state["final_message"] = result.rstrip()
        subtype = event.get("subtype", "result")
        label = _label("[result]", "result", color_enabled=color_enabled)
        return f"{label} {subtype}\n"

    if event_type == "error":
        message = event.get("message") or event.get("error") or event
        label = _label("[error]", "error", color_enabled=color_enabled)
        return f"{label} {message}\n"

    return ""


def parse_automation_status(final_message: str) -> str | None:
    """Extract the final AUTOMATION_STATUS marker from Claude Code output."""
    matches = re.findall(r"(?im)^AUTOMATION_STATUS:\s*([A-Z_]+)\s*$", final_message)
    for match in reversed(matches):
        if match in _AUTOMATION_STATUSES:
            return match
    return None


def parse_commit_packet(final_message: str) -> CommitPacket | None:
    """Extract a commit message and explicit file list from a READY message."""
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


def git_status_short() -> str:
    """Return `git status --short` output for worktree preflight."""
    process = subprocess.run(
        ["git", "status", "--short"],
        cwd=_ROOT,
        text=True,
        capture_output=True,
        check=False,
    )
    if process.returncode != 0:
        raise RuntimeError(process.stderr.strip() or "git status failed")
    return process.stdout


def stage_commit_packet_files(files: list[str]) -> int:
    """Stage the exact existing or tracked-deleted files named by a packet."""
    existing_files: list[str] = []
    tracked_missing_files: list[str] = []
    skipped_missing_files: list[str] = []
    invalid_files: list[str] = []

    for path in files:
        if not _is_repo_relative_file_path(path):
            invalid_files.append(path)
            continue
        absolute_path = _ROOT / path
        if absolute_path.exists():
            if absolute_path.is_file():
                existing_files.append(path)
            else:
                invalid_files.append(path)
        elif _git_path_is_tracked(path):
            tracked_missing_files.append(path)
        else:
            skipped_missing_files.append(path)

    if invalid_files:
        print("Refusing invalid commit packet file paths:", file=sys.stderr)
        for path in invalid_files:
            print(f"  - {path}", file=sys.stderr)
        return 1

    if skipped_missing_files:
        print("Skipping missing untracked commit packet files:")
        for path in skipped_missing_files:
            print(f"  - {path}")

    if existing_files:
        add_existing = _run_git(["add", "--", *existing_files])
        if add_existing.returncode != 0:
            return add_existing.returncode

    if tracked_missing_files:
        add_missing = _run_git(["add", "-A", "--", *tracked_missing_files])
        if add_missing.returncode != 0:
            return add_missing.returncode

    return 0


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


def commit_ready_changes(packet: CommitPacket) -> int:
    """Stage and commit a READY packet after approval or opt-in auto-commit."""
    print("Staging commit packet files:")
    for path in packet.files:
        print(f"  - {path}")

    stage_returncode = stage_commit_packet_files(packet.files)
    if stage_returncode != 0:
        return stage_returncode

    commit = _run_git(["commit", "-m", packet.message])
    return commit.returncode


def run_claude_stream_command(
    args: list[str],
    stdout_jsonl_path: Path,
    stderr_path: Path,
    final_message_path: Path,
    color_enabled: bool = False,
) -> ClaudeRunResult:
    """Run one Claude Code stream-json session while saving output."""
    stdout_jsonl_path.parent.mkdir(parents=True, exist_ok=True)
    stderr_path.parent.mkdir(parents=True, exist_ok=True)
    final_message_path.parent.mkdir(parents=True, exist_ok=True)

    render_state: dict[str, Any] = {}

    process = subprocess.Popen(
        args,
        cwd=_ROOT,
        env=_automation_env(),
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        bufsize=1,
    )

    def read_stdout() -> None:
        assert process.stdout is not None
        with stdout_jsonl_path.open("w", encoding="utf-8") as log_file:
            for line in process.stdout:
                log_file.write(line)
                log_file.flush()
                try:
                    event = json.loads(line)
                except json.JSONDecodeError:
                    rendered = line
                else:
                    rendered = render_claude_stream_event(
                        event,
                        render_state,
                        color_enabled=color_enabled,
                    )
                if rendered:
                    sys.stdout.write(rendered)
                    sys.stdout.flush()

    def read_stderr() -> None:
        assert process.stderr is not None
        with stderr_path.open("w", encoding="utf-8") as log_file:
            for chunk in iter(lambda: process.stderr.read(1), ""):
                log_file.write(chunk)
                log_file.flush()
                sys.stderr.write(chunk)
                sys.stderr.flush()

    stdout_thread = threading.Thread(target=read_stdout)
    stderr_thread = threading.Thread(target=read_stderr)
    stdout_thread.start()
    stderr_thread.start()
    returncode = process.wait()
    stdout_thread.join()
    stderr_thread.join()

    final_message = _final_message_from_state(render_state)
    final_message_path.write_text(final_message, encoding="utf-8")

    return ClaudeRunResult(
        args=args,
        returncode=returncode,
        session_id=render_state.get("session_id"),
        final_message=final_message,
        stdout_jsonl_path=stdout_jsonl_path,
        stderr_path=stderr_path,
        final_message_path=final_message_path,
    )


def run_loop(args: argparse.Namespace) -> int:
    """Run fresh Claude Code passes until drafts are done, blocked, or capped."""
    if args.dry_run:
        return _dry_run(args)

    log_dir = _resolve_log_dir(args.log_dir)
    color_enabled = _should_color(args.color)
    max_passes = 1 if args.once else args.max_passes
    batch_size = getattr(args, "batch_size", _DEFAULT_BATCH_SIZE)
    log_dir.mkdir(parents=True, exist_ok=True)

    for pass_number in range(1, max_passes + 1):
        status_output = git_status_short()
        if _is_worktree_dirty(status_output):
            print(
                "Refusing to start a new Claude Code implementation pass because the worktree is dirty.",
                file=sys.stderr,
            )
            print(status_output.rstrip(), file=sys.stderr)
            return 2

        drafts = find_implementable_drafts()
        if not drafts:
            print("No implementable draft manifests remain.")
            return 0

        print(f"\n=== Claude Code MAID pass {pass_number}/{max_passes} ===")
        print(f"Remaining draft child manifests: {len(drafts)}")
        selected_drafts = drafts[:batch_size]
        print(f"Selected draft manifests this pass: {len(selected_drafts)}")
        for draft in selected_drafts:
            print(f"  - {_rel(draft)}")

        implement_jsonl, implement_stderr, implement_final = _pass_paths(
            log_dir,
            pass_number,
            "implement",
        )
        implementation = run_claude_stream_command(
            build_implementation_command(
                claude=args.claude,
                selected_drafts=selected_drafts,
                model=args.model,
                effort=args.effort,
                permission_mode=args.permission_mode,
            ),
            stdout_jsonl_path=implement_jsonl,
            stderr_path=implement_stderr,
            final_message_path=implement_final,
            color_enabled=color_enabled,
        )
        implementation_status = parse_automation_status(implementation.final_message)
        _print_run_summary(implementation, implementation_status)

        if implementation.returncode != 0:
            return implementation.returncode
        if implementation_status == "NO_DRAFTS":
            return 0
        if implementation_status != "READY":
            print(
                "Implementation pass did not report AUTOMATION_STATUS: READY; stopping for manual review.",
                file=sys.stderr,
            )
            return 1

        commit_packet = parse_commit_packet(implementation.final_message)
        if commit_packet is None:
            print(
                "Implementation pass is READY but did not include a valid AUTOMATION_COMMIT_MESSAGE and AUTOMATION_COMMIT_FILES packet.",
                file=sys.stderr,
            )
            return 1
        post_run_status = git_status_short()
        commit_packet = _include_matching_promoted_draft_deletions(
            commit_packet,
            post_run_status,
        )
        unselected_paths = _unselected_draft_scope_paths(
            commit_packet,
            selected_drafts,
            post_run_status,
        )
        if unselected_paths:
            print(
                "READY packet exceeded the selected draft manifest scope; refusing to commit.",
                file=sys.stderr,
            )
            print("Selected draft manifest(s):", file=sys.stderr)
            for draft in selected_drafts:
                print(f"  - {_rel(draft)}", file=sys.stderr)
            print("Unselected promoted/deleted draft path(s):", file=sys.stderr)
            for path in unselected_paths:
                print(f"  - {path}", file=sys.stderr)
            return 1

        if getattr(args, "auto_commit", False):
            print("Auto-commit enabled; committing READY packet without prompting.")
        elif not ask_commit_approval(pass_number, implementation_status):
            print(
                "Commit was not approved; stopping with changes left for manual review."
            )
            return 0

        commit_returncode = commit_ready_changes(commit_packet)
        if commit_returncode != 0:
            return commit_returncode

        post_commit_status = git_status_short()
        if _is_worktree_dirty(post_commit_status):
            print(
                "Commit step finished, but the worktree is still dirty; stopping.",
                file=sys.stderr,
            )
            print(post_commit_status.rstrip(), file=sys.stderr)
            return 1

    print(f"Reached max pass count ({max_passes}); stopping.")
    return 0


def build_parser() -> argparse.ArgumentParser:
    """Build the command-line parser for the Claude Code MAID draft loop."""
    parser = argparse.ArgumentParser(
        description="Run fresh-session Claude Code MAID draft passes",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""Examples:
  uv run python tools/claude_maid_loop.py --once
  npm run maid:claude-loop -- --once
  npm run maid:claude-loop -- --auto-commit
  npm run maid:claude-loop -- --dry-run

When running through npm, put script arguments after `--`; otherwise npm
handles flags such as `--once` as npm CLI options instead of forwarding them.

Each READY pass uses typed commit approval unless `--auto-commit` is passed.
""",
    )
    parser.add_argument(
        "--once",
        action="store_true",
        help="Run only one implementation pass",
    )
    parser.add_argument(
        "--max-passes",
        type=int,
        default=_DEFAULT_MAX_PASSES,
        help=f"Maximum fresh Claude Code sessions to run (default: {_DEFAULT_MAX_PASSES})",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print current status and planned command without invoking Claude Code",
    )
    parser.add_argument(
        "--auto-commit",
        action="store_true",
        help="Commit each READY packet without prompting for interactive approval",
    )
    parser.add_argument(
        "--batch-size",
        type=int,
        default=_DEFAULT_BATCH_SIZE,
        help=(
            "Number of sorted draft manifests to allow in one agent pass "
            f"(default: {_DEFAULT_BATCH_SIZE})"
        ),
    )
    parser.add_argument("--log-dir", help="Directory for JSONL and final-message logs")
    parser.add_argument("--claude", default="claude", help="Claude executable path")
    parser.add_argument(
        "--color",
        choices=sorted(_COLOR_MODES),
        default="auto",
        help="Colorize rendered terminal output (default: auto)",
    )
    parser.add_argument(
        "--model",
        default=_DEFAULT_MODEL,
        help=f"Claude model to use (default: {_DEFAULT_MODEL})",
    )
    parser.add_argument(
        "--effort",
        default=_DEFAULT_EFFORT,
        choices=sorted(_EFFORTS),
        help=f"Claude thinking effort (default: {_DEFAULT_EFFORT})",
    )
    parser.add_argument(
        "--permission-mode",
        default=_DEFAULT_PERMISSION_MODE,
        choices=sorted(_PERMISSION_MODES),
        help=f"Claude permission mode (default: {_DEFAULT_PERMISSION_MODE})",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    """CLI entrypoint for the Claude Code MAID draft loop."""
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.max_passes <= 0:
        parser.error("--max-passes must be positive")
    if args.batch_size <= 0:
        parser.error("--batch-size must be positive")
    return run_loop(args)


def _now_stamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def _rel(path: Path) -> str:
    try:
        return path.resolve().relative_to(_ROOT).as_posix()
    except ValueError:
        return str(path)


def _automation_env() -> dict[str, str]:
    env = os.environ.copy()
    env.setdefault("UV_CACHE_DIR", str(_ROOT / ".claude-automation" / "uv-cache"))
    return env


def _implementation_prompt(selected_drafts: list[Path]) -> str:
    if selected_drafts:
        selected_lines = "\n".join(f"- {_rel(draft)}" for draft in selected_drafts)
    else:
        selected_lines = "- <none>"

    return (
        _IMPLEMENTATION_PROMPT
        + f"""

Selected draft manifest(s) for this pass:
{selected_lines}

Selected-scope requirements:
- Implement only the selected draft manifest(s) listed above in this pass.
- Do not promote, edit, delete, or implement any other `manifests/drafts/*.manifest.yaml` draft manifest.
- Do not create `manifests/<unselected>.manifest.yaml` files for unselected drafts.
- If the selected draft cannot be implemented without a different draft first,
  report BLOCKED or NEEDS_CHANGES instead of expanding scope.
"""
    )


def _extract_assistant_text(message: object) -> str:
    if not isinstance(message, dict):
        return ""
    content = message.get("content")
    if not isinstance(content, list):
        return ""

    parts: list[str] = []
    for block in content:
        if not isinstance(block, dict):
            continue
        if block.get("type") == "text" and isinstance(block.get("text"), str):
            parts.append(block["text"])
    return "".join(parts)


def _final_message_from_state(state: dict[str, Any]) -> str:
    final_message = state.get("final_message")
    if isinstance(final_message, str):
        return final_message
    last_assistant_text = state.get("last_assistant_text")
    if isinstance(last_assistant_text, str):
        return last_assistant_text
    return ""


def _render_task_system_event(
    event: dict[str, Any],
    *,
    color_enabled: bool,
) -> str:
    subtype = event.get("subtype", "event")
    label = _label("[system]", "system", color_enabled=color_enabled)
    parts = [label, str(subtype)]

    status = _string_field(event, "status")
    if status:
        parts.append(status)

    task_type = _string_field(event, "task_type")
    if task_type:
        parts.append(task_type)

    description = _string_field(event, "description") or _string_field(
        event,
        "summary",
    )
    if description:
        parts.append(description)

    last_tool = _string_field(event, "last_tool_name")
    if last_tool:
        parts.append(f"tool={last_tool}")

    output_file = _string_field(event, "output_file")
    if output_file:
        parts.append(f"output={output_file}")

    parts.extend(_format_task_usage(event.get("usage")))
    return " ".join(parts) + "\n"


def _string_field(event: dict[str, Any], field: str) -> str | None:
    value = event.get(field)
    if isinstance(value, str) and value:
        return value
    return None


def _format_task_usage(usage: object) -> list[str]:
    if not isinstance(usage, dict):
        return []

    parts: list[str] = []
    tool_uses = usage.get("tool_uses")
    if isinstance(tool_uses, int | float):
        parts.append(f"tools={tool_uses:g}")

    total_tokens = usage.get("total_tokens")
    if isinstance(total_tokens, int | float):
        parts.append(f"tokens={total_tokens:g}")

    duration_ms = usage.get("duration_ms")
    if isinstance(duration_ms, int | float):
        parts.append(f"elapsed={duration_ms / 1000:.1f}s")

    return parts


def _colorize(text: str, color: str, *, enabled: bool) -> str:
    if not enabled:
        return text
    return f"{_ANSI_COLORS[color]}{text}{_ANSI_RESET}"


def _label(text: str, color: str, *, color_enabled: bool) -> str:
    return _colorize(text, color, enabled=color_enabled)


def _should_color(mode: str) -> bool:
    if mode == "always":
        return True
    if mode == "never":
        return False
    return sys.stdout.isatty()


def _is_worktree_dirty(status_output: str) -> bool:
    return bool(status_output.strip())


def _run_git(args: list[str]) -> subprocess.CompletedProcess[str]:
    process = subprocess.run(
        ["git", *args],
        cwd=_ROOT,
        text=True,
        capture_output=True,
        check=False,
    )
    if process.stdout:
        sys.stdout.write(process.stdout)
    if process.stderr:
        sys.stderr.write(process.stderr)
    return process


def _git_path_is_tracked(path: str) -> bool:
    process = subprocess.run(
        ["git", "ls-files", "--error-unmatch", "--", path],
        cwd=_ROOT,
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


def _include_matching_promoted_draft_deletions(
    packet: CommitPacket,
    status_output: str,
) -> CommitPacket:
    files = list(packet.files)
    file_set = set(files)
    deleted_paths = _deleted_status_paths(status_output)

    for path in packet.files:
        promoted = Path(path)
        if (
            len(promoted.parts) != 2
            or promoted.parts[0] != "manifests"
            or not promoted.name.endswith(".manifest.yaml")
        ):
            continue
        draft_path = f"manifests/drafts/{promoted.name}"
        if draft_path in deleted_paths and draft_path not in file_set:
            files.append(draft_path)
            file_set.add(draft_path)

    return CommitPacket(message=packet.message, files=files)


def _unselected_draft_scope_paths(
    packet: CommitPacket,
    selected_drafts: list[Path],
    status_output: str,
) -> list[str]:
    selected_names = {Path(draft).name for draft in selected_drafts}
    status_by_path = _status_paths(status_output)
    candidates = list(packet.files)
    candidates.extend(path for path in status_by_path if path not in candidates)

    unselected_paths: list[str] = []
    for path in candidates:
        if _is_unselected_draft_manifest_path(path, selected_names):
            unselected_paths.append(path)
            continue
        if _is_unselected_promoted_manifest_path(
            path,
            selected_names,
            status_by_path.get(path, set()),
        ):
            unselected_paths.append(path)

    return unselected_paths


def _is_unselected_draft_manifest_path(path: str, selected_names: set[str]) -> bool:
    parts = Path(path).parts
    return (
        len(parts) == 3
        and parts[0] == "manifests"
        and parts[1] == "drafts"
        and parts[2].endswith(".manifest.yaml")
        and parts[2] not in selected_names
    )


def _is_unselected_promoted_manifest_path(
    path: str,
    selected_names: set[str],
    statuses: set[str],
) -> bool:
    parts = Path(path).parts
    return (
        len(parts) == 2
        and parts[0] == "manifests"
        and parts[1].endswith(".manifest.yaml")
        and parts[1] not in selected_names
        and _status_is_new_or_renamed(statuses)
    )


def _status_is_new_or_renamed(statuses: set[str]) -> bool:
    return any(
        status == "??" or "A" in status or "R" in status or "C" in status
        for status in statuses
    )


def _deleted_status_paths(status_output: str) -> set[str]:
    return {
        path
        for path, statuses in _status_paths(status_output).items()
        if any(status in {" D", "D "} for status in statuses)
    }


def _status_paths(status_output: str) -> dict[str, set[str]]:
    status_by_path: dict[str, set[str]] = {}
    for line in status_output.splitlines():
        if len(line) < 4:
            continue
        status = line[:2]
        raw_path = line[3:].strip()
        if not raw_path:
            continue
        for path in _split_status_path(status, raw_path):
            status_by_path.setdefault(path, set()).add(status)
    return status_by_path


def _split_status_path(status: str, raw_path: str) -> list[str]:
    if " -> " not in raw_path:
        return [raw_path]
    before, after = raw_path.split(" -> ", 1)
    if "R" in status:
        return [before.strip(), after.strip()]
    return [after.strip()]


def _resolve_log_dir(value: str | None) -> Path:
    if value:
        path = Path(value)
        if not path.is_absolute():
            path = _ROOT / path
        return path
    return _DEFAULT_LOG_ROOT / _now_stamp()


def _pass_paths(log_dir: Path, pass_number: int, phase: str) -> tuple[Path, Path, Path]:
    prefix = f"pass-{pass_number:03d}-{phase}"
    return (
        log_dir / f"{prefix}.jsonl",
        log_dir / f"{prefix}.stderr.log",
        log_dir / f"{prefix}.final.md",
    )


def _print_run_summary(result: ClaudeRunResult, status: str | None) -> None:
    print("\nClaude Code run summary:")
    print(f"  exit: {result.returncode}")
    print(f"  session: {result.session_id or 'unknown'}")
    print(f"  status: {status or 'missing'}")
    print(f"  jsonl: {_rel(result.stdout_jsonl_path)}")
    print(f"  stderr: {_rel(result.stderr_path)}")
    print(f"  final: {_rel(result.final_message_path)}")


def _dry_run(args: argparse.Namespace) -> int:
    drafts = find_implementable_drafts()
    status = git_status_short()
    log_dir = _resolve_log_dir(args.log_dir)
    batch_size = getattr(args, "batch_size", _DEFAULT_BATCH_SIZE)
    selected_drafts = drafts[:batch_size]

    print(f"Draft child manifests: {len(drafts)}")
    for draft in drafts[:10]:
        print(f"  - {_rel(draft)}")
    if len(drafts) > 10:
        print(f"  ... {len(drafts) - 10} more")
    print(f"Selected draft manifests this pass: {len(selected_drafts)}")
    for draft in selected_drafts:
        print(f"  - {_rel(draft)}")
    print(f"Worktree dirty: {'yes' if _is_worktree_dirty(status) else 'no'}")
    print("Implementation command:")
    print("Model: " + args.model)
    print("Effort: " + args.effort)
    print("Permission mode: " + args.permission_mode)
    print(
        "Commit approval: "
        + (
            "auto-commit enabled"
            if getattr(args, "auto_commit", False)
            else "typed approval required for every READY pass"
        )
    )
    print(
        "  "
        + " ".join(
            build_implementation_command(
                claude=args.claude,
                selected_drafts=selected_drafts,
                model=args.model,
                effort=args.effort,
                permission_mode=args.permission_mode,
            )
        )
    )
    print(f"Logs would be written under: {_rel(log_dir)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
