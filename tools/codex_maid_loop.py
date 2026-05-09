#!/usr/bin/env python3
"""Automate fresh-session Codex runs for maid-runner MAID drafts."""

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
_DEFAULT_LOG_ROOT = _ROOT / ".codex-automation" / "runs"
_DEFAULT_MAX_PASSES = 100
_DEFAULT_MODEL = "gpt-5.5"
_DEFAULT_REASONING_EFFORT = "medium"
_APPROVAL_POLICY = "on-request"
_APPROVALS_REVIEWER = "auto_review"
_AUTOMATION_STATUSES = {"READY", "NEEDS_CHANGES", "BLOCKED", "NO_DRAFTS"}
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
  agent_type=explorer, model gpt-5.5, and reasoning_effort=medium. Pass the
  review packet explicitly instead of forking the full implementation history.
  If explorer is unavailable, omit agent_type and use the default agent with
  the same explicit read-only review packet.
- After each reviewer subagent result is consumed, call close_agent for that
  reviewer thread before spawning or reusing another reviewer.
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


def find_implementable_drafts(draft_dir: Path = _DRAFT_DIR) -> list[Path]:
    """Return non-epic draft MAID manifests that remain to be implemented."""
    if not draft_dir.exists():
        return []
    return sorted(path for path in draft_dir.glob("*.manifest.yaml") if path.is_file())


def build_implementation_command(
    codex: str,
    final_message_path: Path,
    model: str = _DEFAULT_MODEL,
    reasoning_effort: str = _DEFAULT_REASONING_EFFORT,
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
        _IMPLEMENTATION_PROMPT,
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


def parse_automation_status(final_message: str) -> str | None:
    """Extract the final AUTOMATION_STATUS marker from the last Codex message."""
    matches = re.findall(r"(?im)^AUTOMATION_STATUS:\s*([A-Z_]+)\s*$", final_message)
    for match in reversed(matches):
        if match in _AUTOMATION_STATUSES:
            return match
    return None


def parse_commit_packet(final_message: str) -> CommitPacket | None:
    """Extract a commit message and explicit file list from a READY final message."""
    message_matches = re.findall(
        r"(?im)^AUTOMATION_COMMIT_MESSAGE:\s*(.+?)\s*$",
        final_message,
    )
    if not message_matches:
        return None

    files_match = re.search(
        r"(?im)^AUTOMATION_COMMIT_FILES:[^\n]*\n"
        r"(?P<files>(?:^[ \t]*-[ \t]+[^\n]+\n?)*)",
        final_message,
    )
    if not files_match:
        return None

    files: list[str] = []
    for line in files_match.group("files").splitlines():
        stripped = line.strip()
        if not stripped.startswith("- "):
            continue
        path = stripped[2:].strip()
        if path:
            files.append(path)

    if not files:
        return None

    return CommitPacket(message=message_matches[-1].strip(), files=files)


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
    """Stage the exact existing or tracked-deleted files named by a READY packet."""
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
    """Stage and commit a READY packet after explicit approval."""
    print("Staging commit packet files:")
    for path in packet.files:
        print(f"  - {path}")

    stage_returncode = stage_commit_packet_files(packet.files)
    if stage_returncode != 0:
        return stage_returncode

    commit = _run_git(["commit", "-m", packet.message])
    return commit.returncode


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

        implement_jsonl, implement_stderr, implement_final = _pass_paths(
            log_dir,
            pass_number,
            "implement",
        )
        implementation = run_codex_json_command(
            build_implementation_command(
                codex=args.codex,
                final_message_path=implement_final,
                model=args.model,
                reasoning_effort=args.reasoning_effort,
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

        if not ask_commit_approval(pass_number, implementation_status):
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
  npm run maid:codex-loop -- --dry-run

When running through npm, put script arguments after `--`; otherwise npm
handles flags such as `--once` as npm CLI options instead of forwarding them.

Each READY pass still requires a fresh typed commit approval.
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
        help=f"Maximum fresh Codex sessions to run (default: {_DEFAULT_MAX_PASSES})",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print current status and planned command without invoking Codex",
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

    print(f"Draft child manifests: {len(drafts)}")
    for draft in drafts[:10]:
        print(f"  - {_rel(draft)}")
    if len(drafts) > 10:
        print(f"  ... {len(drafts) - 10} more")
    print(f"Worktree dirty: {'yes' if _is_worktree_dirty(status) else 'no'}")
    print("Implementation command:")
    print("Model: " + args.model)
    print("Reasoning effort: " + args.reasoning_effort)
    print("Commit approval: typed approval required for every READY pass")
    print(
        "  "
        + " ".join(
            build_implementation_command(
                codex=args.codex,
                final_message_path=implementation_final,
                model=args.model,
                reasoning_effort=args.reasoning_effort,
            )
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
