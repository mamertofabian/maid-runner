"""CLI handler for 'maid graph' command."""

from __future__ import annotations

import argparse
import json
import sys


def cmd_graph(args: argparse.Namespace) -> int:
    if not hasattr(args, "graph_command") or not args.graph_command:
        print("Usage: maid graph {query,export,analyze} ...", file=sys.stderr)
        return 2

    from maid_runner.graph.api import (
        analyze_file_dependencies,
        build_graph_from_manifest_dir,
        export_graph,
        query_graph,
    )

    graph = build_graph_from_manifest_dir(args.manifest_dir)

    if args.graph_command == "query":
        result = query_graph(graph, args.question)
        if args.json:
            print(json.dumps(result, indent=2, sort_keys=True))
        else:
            print(result["summary"])
        return 0 if result["success"] else 1

    if args.graph_command == "export":
        content = export_graph(graph, args.format, output_path=args.output)
        if args.output:
            print(f"Wrote graph export to {args.output}")
        else:
            print(content)
        return 0

    if args.graph_command == "analyze":
        result = analyze_file_dependencies(graph, args.file_path)
        if args.json:
            print(json.dumps(result, indent=2, sort_keys=True))
        else:
            print(f"{result['file']}: {len(result['artifacts'])} artifact(s)")
        return 0

    print(f"Unknown graph command: {args.graph_command}", file=sys.stderr)
    return 2
