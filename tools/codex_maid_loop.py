#!/usr/bin/env python3
"""Automate fresh-session Codex runs for maid-runner MAID drafts."""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import threading
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

try:
    from tools.maid_loop_core import (
        CommitPacket as _CoreCommitPacket,
        ask_commit_approval as _core_ask_commit_approval,
        commit_ready_changes as _core_commit_ready_changes,
        find_implementable_drafts as _core_find_implementable_drafts,
        git_status_short as _core_git_status_short,
        parse_automation_status as _core_parse_automation_status,
        parse_commit_packet as _core_parse_commit_packet,
        run_bounded_retry_loop,
        stage_commit_packet_files as _core_stage_commit_packet_files,
    )
except ModuleNotFoundError:
    from maid_loop_core import (  # type: ignore[no-redef]
        CommitPacket as _CoreCommitPacket,
        ask_commit_approval as _core_ask_commit_approval,
        commit_ready_changes as _core_commit_ready_changes,
        find_implementable_drafts as _core_find_implementable_drafts,
        git_status_short as _core_git_status_short,
        parse_automation_status as _core_parse_automation_status,
        parse_commit_packet as _core_parse_commit_packet,
        run_bounded_retry_loop,
        stage_commit_packet_files as _core_stage_commit_packet_files,
    )


_ROOT = Path(__file__).resolve().parents[1]
_DRAFT_DIR = _ROOT / "manifests" / "drafts"
_DEFAULT_LOG_ROOT = _ROOT / ".codex-automation" / "runs"
_DEFAULT_PACKET_PATH = _ROOT / ".maid" / "last-failure-packet.json"
_DEFAULT_MAX_PASSES = 100
_DEFAULT_BATCH_SIZE = 1
_DEFAULT_MODEL = "gpt-5.5"
_DEFAULT_REASONING_EFFORT = "medium"
_APPROVAL_POLICY = "on-request"
_APPROVALS_REVIEWER = "auto_review"
_REASONING_EFFORTS = {"minimal", "low", "medium", "high", "xhigh"}
_COLOR_MODES = {"auto", "always", "never"}
_ANSI_RESET = "\033[0m"
_ANSI_COLORS = {
    "thread": "\033[2;37m",
    "turn": "\033[32m",
    "assistant": "\033[36m",
    "reasoning": "\033[35m",
    "command": "\033[33m",
    "files": "\033[34m",
    "plan": "\033[36m",
    "error": "\033[31m",
}

_IMPLEMENTATION_PROMPT = """Use the maid-runner-draft-implement skill to continue implementing MAID draft manifests in this repo. If that skill is not listed in the session's available skills, read .codex/skills/maid-runner-draft-implement/SKILL.md and follow it before editing.

Automation reporting requirements:
- Keep doing the skill's validation and review loop until the pass is genuinely
  ready, blocked, or there are no implementable draft manifests.
- When spawning a read-only reviewer subagent, use fork_context=false,
  agent_type=explorer, and leave reviewer model and reasoning effort unset so
  they inherit from the main agent. Pass the review packet explicitly instead
  of forking the full implementation history. If explorer is unavailable, omit
  agent_type and use the default agent with the same explicit read-only review
  packet.
- After each reviewer subagent result is consumed, call close_agent for that
  reviewer thread before spawning or reusing another reviewer.
- Capture Outcome after implementation review and before final handoff: update
  the promoted manifest with an evidence-backed `outcome:` section before
  reporting READY or emitting a commit packet. Do not report AUTOMATION_STATUS: READY when Outcome is missing unless the final message states a concrete not-applicable or blocked reason.
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
class CodexRunResult:
    """Captured result paths and metadata for one Codex exec pass."""

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


class _LoopAbort(Exception):
    def __init__(self, returncode: int) -> None:
        self.returncode = returncode


def find_implementable_drafts(draft_dir: Path = _DRAFT_DIR) -> list[Path]:
    """Return non-epic draft MAID manifests that remain to be implemented."""
    return _core_find_implementable_drafts(draft_dir)


def parse_automation_status(final_message: str) -> str | None:
    """Extract the final AUTOMATION_STATUS marker from the last Codex message."""
    return _core_parse_automation_status(final_message)


def parse_commit_packet(final_message: str) -> CommitPacket | None:
    """Extract a commit message and explicit file list from a READY final message."""
    packet = _core_parse_commit_packet(final_message)
    if packet is None:
        return None
    return CommitPacket(message=packet.message, files=packet.files)


def build_implementation_command(
    codex: str,
    final_message_path: Path,
    selected_drafts: list[Path],
    model: str = _DEFAULT_MODEL,
    reasoning_effort: str = _DEFAULT_REASONING_EFFORT,
    failure_packet: dict[str, Any] | None = None,
) -> list[str]:
    """Build a fresh `codex exec --json` command for one implementation pass."""
    return [
        codex,
        "--ask-for-approval",
        _APPROVAL_POLICY,
        "-c",
        f'approvals_reviewer="{_APPROVALS_REVIEWER}"',
        "exec",
        "--model",
        model,
        "-c",
        f"model_reasoning_effort={reasoning_effort}",
        "--cd",
        str(_ROOT),
        "--sandbox",
        "workspace-write",
        "--json",
        "--output-last-message",
        str(final_message_path),
        _implementation_prompt(selected_drafts, failure_packet=failure_packet),
    ]


def render_codex_json_event(
    event: dict[str, Any],
    state: dict[str, Any],
    color_enabled: bool = False,
) -> str:
    """Render a documented Codex JSONL event as concise terminal progress."""
    event_type = event.get("type")

    if event_type == "thread.started":
        thread_id = event.get("thread_id")
        if isinstance(thread_id, str):
            state["session_id"] = thread_id
            return f"{_label('[thread]', 'thread', color_enabled=color_enabled)} {thread_id}\n"
        return f"{_label('[thread]', 'thread', color_enabled=color_enabled)} started\n"

    if event_type == "turn.started":
        return f"{_label('[turn]', 'turn', color_enabled=color_enabled)} started\n"

    if event_type == "turn.completed":
        usage = event.get("usage")
        if isinstance(usage, dict):
            input_tokens = usage.get("input_tokens")
            output_tokens = usage.get("output_tokens")
            label = _label("[turn]", "turn", color_enabled=color_enabled)
            return f"{label} completed input={input_tokens} output={output_tokens}\n"
        return f"{_label('[turn]', 'turn', color_enabled=color_enabled)} completed\n"

    if event_type == "turn.failed":
        label = _label("[turn]", "error", color_enabled=color_enabled)
        return f"{label} failed {_compact_json(event)}\n"

    if event_type == "error":
        message = event.get("message") or event.get("error") or event
        return f"{_label('[error]', 'error', color_enabled=color_enabled)} {message}\n"

    if event_type not in {"item.started", "item.completed"}:
        return ""

    item = event.get("item")
    if not isinstance(item, dict):
        return ""

    item_type = item.get("type", "item")
    status = "started" if event_type == "item.started" else "completed"

    if item_type == "agent_message":
        text = item.get("text")
        if isinstance(text, str) and text:
            label = _label("[assistant]", "assistant", color_enabled=color_enabled)
            return f"\n{label}\n{text.rstrip()}\n"
        return ""

    if item_type == "reasoning":
        text = item.get("text") or item.get("summary")
        label = _label("[reasoning]", "reasoning", color_enabled=color_enabled)
        if isinstance(text, str) and text:
            return f"\n{label}\n{text.rstrip()}\n"
        return f"{label} {status}\n"

    if item_type == "command_execution":
        command = item.get("command", "")
        exit_code = item.get("exit_code")
        suffix = f" exit={exit_code}" if exit_code is not None else ""
        label = _label(f"[command:{status}]", "command", color_enabled=color_enabled)
        return f"{label} {command}{suffix}\n"

    if item_type in {"file_change", "file_changes"}:
        label = _label(f"[files:{status}]", "files", color_enabled=color_enabled)
        return f"{label} {_compact_json(item)}\n"

    if item_type == "plan_update":
        label = _label(f"[plan:{status}]", "plan", color_enabled=color_enabled)
        return f"{label} {_compact_json(item)}\n"

    if status == "completed":
        return f"[{item_type}] completed\n"
    return ""


def git_status_short() -> str:
    """Return `git status --short` output for worktree preflight."""
    return _core_git_status_short(_ROOT)


def stage_commit_packet_files(files: list[str]) -> int:
    """Stage the exact existing or tracked-deleted files named by a READY packet."""
    return _core_stage_commit_packet_files(files, _ROOT)


def ask_commit_approval(pass_number: int, status: str) -> bool:
    """Require a per-pass typed approval before committing a READY packet."""
    return _core_ask_commit_approval(pass_number, status)


def commit_ready_changes(packet: CommitPacket) -> int:
    """Stage and commit a READY packet after explicit approval."""
    core_packet = _CoreCommitPacket(message=packet.message, files=packet.files)
    return _core_commit_ready_changes(core_packet, _ROOT)


def run_codex_json_command(
    args: list[str],
    stdout_jsonl_path: Path,
    stderr_path: Path,
    final_message_path: Path,
    color_enabled: bool,
) -> CodexRunResult:
    """Run one Codex JSON session while saving and rendering its output."""
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
                    rendered = render_codex_json_event(
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

    return CodexRunResult(
        args=args,
        returncode=returncode,
        session_id=render_state.get("session_id"),
        final_message=_read_final_message(final_message_path),
        stdout_jsonl_path=stdout_jsonl_path,
        stderr_path=stderr_path,
        final_message_path=final_message_path,
    )


def run_loop(args: argparse.Namespace) -> int:
    """Run fresh Codex passes until drafts are done, blocked, or max passes is reached."""
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
                "Refusing to start a new Codex implementation pass because the worktree is dirty.",
                file=sys.stderr,
            )
            print(status_output.rstrip(), file=sys.stderr)
            return 2

        drafts = find_implementable_drafts()
        if not drafts:
            print("No implementable draft manifests remain.")
            return 0

        print(f"\n=== Codex MAID pass {pass_number}/{max_passes} ===")
        print(f"Remaining draft child manifests: {len(drafts)}")
        selected_drafts = drafts[:batch_size]
        print(f"Selected draft manifests this pass: {len(selected_drafts)}")
        for draft in selected_drafts:
            print(f"  - {_rel(draft)}")

        _clear_stale_packet(_DEFAULT_PACKET_PATH)
        latest: dict[str, CodexRunResult | str | None] = {}
        attempt_index = 0

        def run_gate() -> int:
            if "implementation" not in latest:
                return 1
            return _run_packet_gate(_DEFAULT_PACKET_PATH)

        def run_attempt(failure_packet: dict | None) -> str:
            nonlocal attempt_index
            attempt_index += 1
            implement_jsonl, implement_stderr, implement_final = _pass_paths(
                log_dir,
                pass_number,
                f"implement-{attempt_index:02d}",
            )
            implementation = run_codex_json_command(
                build_implementation_command(
                    codex=args.codex,
                    final_message_path=implement_final,
                    selected_drafts=selected_drafts,
                    model=args.model,
                    reasoning_effort=args.reasoning_effort,
                    failure_packet=failure_packet,
                ),
                stdout_jsonl_path=implement_jsonl,
                stderr_path=implement_stderr,
                final_message_path=implement_final,
                color_enabled=color_enabled,
            )
            implementation_status = parse_automation_status(
                implementation.final_message
            )
            latest["implementation"] = implementation
            latest["status"] = implementation_status
            _print_run_summary(implementation, implementation_status)

            if implementation.returncode != 0:
                raise _LoopAbort(implementation.returncode)
            if implementation_status == "NO_DRAFTS":
                raise _LoopAbort(0)
            if implementation_status != "READY":
                print(
                    "Implementation pass did not report AUTOMATION_STATUS: READY; stopping for manual review.",
                    file=sys.stderr,
                )
                raise _LoopAbort(1)
            return f"AUTOMATION_STATUS: {implementation_status}"

        try:
            retry_result = run_bounded_retry_loop(
                run_gate=run_gate,
                run_attempt=run_attempt,
                packet_path=_DEFAULT_PACKET_PATH,
            )
        except _LoopAbort as exc:
            return exc.returncode
        if retry_result.escalated:
            return 1

        implementation = latest.get("implementation")
        implementation_status = latest.get("status")
        if not isinstance(implementation, CodexRunResult):
            return 0

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

        missing_packet_paths = _missing_commit_packet_status_paths(
            commit_packet,
            post_run_status,
        )
        if missing_packet_paths:
            print(
                "READY packet did not include every changed worktree path; refusing to commit.",
                file=sys.stderr,
            )
            print("Missing changed path(s):", file=sys.stderr)
            for path in missing_packet_paths:
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
    """Build the command-line parser for the Codex MAID draft loop."""
    parser = argparse.ArgumentParser(
        description="Run fresh-session Codex MAID draft implementation passes",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""Examples:
  uv run python tools/codex_maid_loop.py --once
  npm run maid:codex-loop -- --once
  npm run maid:codex-loop -- --auto-commit
  npm run maid:codex-loop -- --dry-run

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
        help=(
            "Maximum draft implementation passes to run; each pass may make "
            f"bounded retry attempts (default: {_DEFAULT_MAX_PASSES})"
        ),
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print current status and planned command without invoking Codex",
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
    parser.add_argument("--codex", default="codex", help="Codex executable path")
    parser.add_argument(
        "--color",
        choices=sorted(_COLOR_MODES),
        default="auto",
        help="Colorize rendered terminal output (default: auto)",
    )
    parser.add_argument(
        "--model",
        default=_DEFAULT_MODEL,
        help=f"Codex model to use (default: {_DEFAULT_MODEL})",
    )
    parser.add_argument(
        "--reasoning-effort",
        default=_DEFAULT_REASONING_EFFORT,
        choices=sorted(_REASONING_EFFORTS),
        help=f"Codex reasoning effort (default: {_DEFAULT_REASONING_EFFORT})",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    """CLI entrypoint for the Codex MAID draft loop."""
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
    env.setdefault("UV_CACHE_DIR", str(_ROOT / ".codex-automation" / "uv-cache"))
    return env


def _implementation_prompt(
    selected_drafts: list[Path],
    failure_packet: dict[str, Any] | None = None,
) -> str:
    if selected_drafts:
        selected_lines = "\n".join(f"- {_rel(draft)}" for draft in selected_drafts)
    else:
        selected_lines = "- <none>"

    packet_section = ""
    if failure_packet is not None:
        packet_section = (
            "\nFailure packet for this retry attempt:\n"
            "```json\n"
            + json.dumps(failure_packet, indent=2, sort_keys=True)
            + "\n```\n"
        )

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
{packet_section}
"""
    )


def _compact_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=True, sort_keys=True)


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


def _run_packet_gate(packet_path: Path = _DEFAULT_PACKET_PATH) -> int:
    process = subprocess.run(
        [
            "uv",
            "run",
            "maid",
            "verify",
            "--require-plan-lock",
            "--require-red-evidence",
            "--since",
            "HEAD",
            "--packet",
            str(packet_path),
        ],
        cwd=_ROOT,
        text=True,
        capture_output=True,
        check=False,
    )
    if process.stdout:
        sys.stdout.write(process.stdout)
    if process.stderr:
        sys.stderr.write(process.stderr)
    return process.returncode


def _clear_stale_packet(packet_path: Path) -> None:
    try:
        packet_path.unlink()
    except FileNotFoundError:
        return
    except OSError as exc:
        print(f"Warning: could not remove stale failure packet {packet_path}: {exc}")


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


def _missing_commit_packet_status_paths(
    packet: CommitPacket,
    status_output: str,
) -> list[str]:
    packet_paths = set(packet.files)
    return [path for path in _status_paths(status_output) if path not in packet_paths]


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


def _read_final_message(path: Path) -> str:
    if not path.exists():
        return ""
    return path.read_text(encoding="utf-8")


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


def _print_run_summary(result: CodexRunResult, status: str | None) -> None:
    print("\nCodex run summary:")
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
    implementation_final = log_dir / "pass-001-implement.final.md"
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
    print("Reasoning effort: " + args.reasoning_effort)
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
                codex=args.codex,
                final_message_path=implementation_final,
                selected_drafts=selected_drafts,
                model=args.model,
                reasoning_effort=args.reasoning_effort,
            )
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
