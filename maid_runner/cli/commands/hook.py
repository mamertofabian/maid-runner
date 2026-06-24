"""CLI handler for `maid hook` subcommands."""

from __future__ import annotations

import argparse
from dataclasses import asdict
import json
import sys

from maid_runner.core.active_task import resolve_active_manifest
from maid_runner.core.scope_check import ScopeCheckDecision, scope_check_path


def cmd_hook(args: argparse.Namespace) -> int:
    subcommand = getattr(args, "hook_command", None)
    if subcommand != "scope-check":
        decision = ScopeCheckDecision(
            decision="allow",
            reason="internal-error: unknown-hook-subcommand",
            active_manifest=None,
        )
        print(json.dumps(asdict(decision)))
        return 1

    active_manifest = None
    try:
        candidate_path = _candidate_path(args)
        active_manifest = resolve_active_manifest()
        decision = scope_check_path(
            candidate_path,
            active_manifest,
            strict=getattr(args, "strict", False),
        )
    except Exception as exc:
        decision = ScopeCheckDecision(
            decision="deny" if getattr(args, "strict", False) else "allow",
            reason=f"internal-error: {type(exc).__name__}: {exc}",
            active_manifest=active_manifest,
        )
        print(json.dumps(asdict(decision)))
        return 1

    print(json.dumps(asdict(decision)))
    if decision.reason.startswith("internal-error:"):
        return 1
    return 0 if decision.decision == "allow" else 2


def _candidate_path(args: argparse.Namespace) -> str:
    if getattr(args, "stdin", False):
        payload = json.loads(sys.stdin.read())
        path = _stdin_payload_path(payload)
        if not isinstance(path, str) or not path:
            raise ValueError("stdin JSON object must contain a non-empty path field")
        return path

    path = getattr(args, "path", None)
    if not isinstance(path, str) or not path:
        raise ValueError("--path is required unless --stdin is used")
    return path


def _stdin_payload_path(payload: object) -> object:
    if not isinstance(payload, dict):
        return None
    path = payload.get("path")
    if path:
        return path
    tool_input = payload.get("tool_input")
    if isinstance(tool_input, dict):
        return tool_input.get("file_path")
    return None
