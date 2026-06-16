"""CLI handler for `maid task` subcommands."""

from __future__ import annotations

import argparse
import json

from maid_runner.cli.commands._format import print_error
from maid_runner.core.active_task import (
    ActiveTaskError,
    get_active_manifest_status,
    start_active_task,
    stop_active_task,
)


def cmd_task(args: argparse.Namespace) -> int:
    subcommand = getattr(args, "task_command", None)
    if subcommand == "start":
        return _cmd_task_start(args)
    if subcommand == "stop":
        return _cmd_task_stop()
    if subcommand == "status":
        return _cmd_task_status(args)

    print_error("Unknown or missing task subcommand")
    return 2


def _cmd_task_start(args: argparse.Namespace) -> int:
    try:
        stored_path = start_active_task(args.manifest_path)
    except ActiveTaskError as exc:
        print_error(str(exc))
        return 2
    print(f"Active task: {stored_path}")
    return 0


def _cmd_task_stop() -> int:
    removed = stop_active_task()
    if removed:
        print("Stopped active task")
    else:
        print("No active task to stop")
    return 0


def _cmd_task_status(args: argparse.Namespace) -> int:
    status = get_active_manifest_status()
    if getattr(args, "json", False):
        print(
            json.dumps(
                {
                    "active_manifest": status.path,
                    "source": status.source,
                }
            )
        )
        return 0

    if status.path is None:
        print("No active task")
    elif status.source == "env":
        print(f"Active task: {status.path} (source: MAID_ACTIVE_MANIFEST)")
    else:
        print(f"Active task: {status.path} (source: .maid/active-manifest)")
    return 0
