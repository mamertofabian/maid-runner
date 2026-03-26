"""CLI handler for 'maid graph' command."""

from __future__ import annotations

import argparse
import importlib.util
import sys


def cmd_graph(args: argparse.Namespace) -> int:
    if not hasattr(args, "graph_command") or not args.graph_command:
        print("Usage: maid graph {query,export,analyze} ...", file=sys.stderr)
        return 2

    if importlib.util.find_spec("maid_runner.graph") is None:
        print(
            "Error: Graph module not available. "
            "This feature will be available in Phase 5.",
            file=sys.stderr,
        )
        return 2

    print("Error: Graph commands not yet implemented.", file=sys.stderr)
    return 2
