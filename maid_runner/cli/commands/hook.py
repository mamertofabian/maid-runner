"""CLI handler for `maid hook` subcommands."""

from __future__ import annotations

import argparse
from dataclasses import asdict
import json
import sys

from maid_runner.core.active_task import resolve_active_manifest
from maid_runner.core.scope_check import ScopeCheckDecision, scope_check_path


_VALID_HOOK_FORMATS = frozenset({"default", "antigravity"})
_ANTIGRAVITY_ARG_PATH_KEYS = ("Path", "TargetFile", "path", "file_path")


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

    strict = bool(getattr(args, "strict", False))
    raw_format = getattr(args, "format", "default")
    output_format = "default" if raw_format is None else raw_format
    if not isinstance(output_format, str) or output_format not in _VALID_HOOK_FORMATS:
        decision = ScopeCheckDecision(
            decision="deny" if strict else "allow",
            reason=f"internal-error: ValueError: unsupported hook format: {output_format!r}",
            active_manifest=None,
        )
        print(json.dumps(asdict(decision)))
        return 1

    active_manifest = None
    try:
        candidate_path, project_root = _resolve_hook_inputs(args)
        active_manifest = resolve_active_manifest(project_root)
        decision = scope_check_path(
            candidate_path,
            active_manifest,
            project_root=project_root,
            strict=strict,
        )
    except Exception as exc:
        decision = ScopeCheckDecision(
            decision="deny" if strict else "allow",
            reason=f"internal-error: {type(exc).__name__}: {exc}",
            active_manifest=active_manifest,
        )
        print(_serialize_decision(decision, output_format))
        return 0 if output_format == "antigravity" else 1

    print(_serialize_decision(decision, output_format))
    if output_format == "antigravity":
        return 0
    if decision.reason.startswith("internal-error:"):
        return 1
    return 0 if decision.decision == "allow" else 2


def _serialize_decision(decision: ScopeCheckDecision, output_format: str) -> str:
    if output_format == "antigravity":
        return json.dumps(
            {
                "decision": decision.decision,
                "reason": decision.reason,
            }
        )
    return json.dumps(asdict(decision))


def _resolve_hook_inputs(args: argparse.Namespace) -> tuple[str, str]:
    if getattr(args, "stdin", False):
        payload = json.loads(sys.stdin.read())
        path = _stdin_payload_path(payload)
        if not isinstance(path, str) or not path:
            raise ValueError("stdin JSON object must contain a non-empty path field")
        project_root = _stdin_project_root(payload)
        return path, project_root

    path = getattr(args, "path", None)
    if not isinstance(path, str) or not path:
        raise ValueError("--path is required unless --stdin is used")
    return path, "."


def _stdin_project_root(payload: object) -> str:
    if not isinstance(payload, dict) or "cwd" not in payload or payload["cwd"] is None:
        return "."
    cwd = payload["cwd"]
    if not isinstance(cwd, str) or not cwd.strip():
        raise ValueError("stdin JSON object cwd field must be a non-empty string")
    return cwd


def _stdin_payload_path(payload: object) -> object:
    if not isinstance(payload, dict):
        return None
    if "path" in payload and payload["path"] is not None:
        return payload["path"]
    tool_input = payload.get("tool_input")
    if isinstance(tool_input, dict) and "file_path" in tool_input:
        if tool_input["file_path"] is not None:
            return tool_input["file_path"]
    tool_call = payload.get("toolCall")
    if isinstance(tool_call, dict):
        tool_args = tool_call.get("args")
        if isinstance(tool_args, dict):
            for key in _ANTIGRAVITY_ARG_PATH_KEYS:
                if key in tool_args and tool_args[key] is not None:
                    return tool_args[key]
    return None
