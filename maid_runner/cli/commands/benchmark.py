"""CLI handler for the 'maid benchmark' command."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from maid_runner.cli.commands._format import print_error
from maid_runner.core.benchmark import format_benchmark_markdown, run_benchmark


def cmd_benchmark(args: argparse.Namespace) -> int:
    try:
        report = run_benchmark(
            project_paths=getattr(args, "projects", None) or ["."],
            command_prefix=getattr(args, "command_prefix", None) or [],
            manifest_dir=args.manifest_dir,
            repeat=args.repeat,
        )
        markdown = format_benchmark_markdown(report)

        json_output = getattr(args, "json_output", None)
        if json_output:
            Path(json_output).write_text(
                json.dumps(report, indent=2) + "\n",
                encoding="utf-8",
            )

        markdown_output = getattr(args, "markdown_output", None)
        if markdown_output:
            Path(markdown_output).write_text(
                markdown if markdown.endswith("\n") else markdown + "\n",
                encoding="utf-8",
            )

        if getattr(args, "json", False):
            print(json.dumps(report, indent=2))
        else:
            print(markdown)

        return 0 if report["success"] else 1
    except Exception as exc:
        print_error(str(exc), json_mode=getattr(args, "json", False))
        return 2
