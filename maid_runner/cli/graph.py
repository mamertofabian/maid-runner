"""CLI command handler for graph operations.

This module provides command handlers for the graph subcommand of the MAID CLI.
It supports querying the knowledge graph, exporting to various formats, and
running graph analysis.

Functions:
    run_graph_command: Entry point that routes to handlers based on args
    handle_query: Execute a query against the knowledge graph
    handle_export: Export the knowledge graph to a file
    handle_analysis: Run graph analysis (cycles, stats)
"""

import argparse
from pathlib import Path

from maid_runner.graph.builder import KnowledgeGraphBuilder
from maid_runner.graph.query import QueryParser, QueryExecutor, find_cycles
from maid_runner.graph.exporters import export_json, export_dot, export_graphml


def run_graph_command(args: argparse.Namespace) -> int:
    """Entry point that routes to handlers based on subcommand.

    Examines args.subcommand to determine which handler to invoke:
    - "query" -> handle_query
    - "export" -> handle_export
    - "analysis" -> handle_analysis

    Args:
        args: Parsed command-line arguments with subcommand attribute.

    Returns:
        Exit code: 0 on success, 1 on error.
    """
    try:
        subcommand = getattr(args, "subcommand", None)

        if subcommand == "query":
            handle_query(args.query, Path(args.manifest_dir))
            return 0
        elif subcommand == "export":
            handle_export(args.format, Path(args.output), Path(args.manifest_dir))
            return 0
        elif subcommand == "analysis":
            handle_analysis(args.analysis_type, Path(args.manifest_dir))
            return 0
        else:
            print(f"Unknown subcommand: {subcommand}")
            return 1
    except Exception as e:
        print(f"Error: {e}")
        return 1


def handle_query(query: str, manifest_dir: Path) -> None:
    """Execute a query against the knowledge graph.

    Builds the knowledge graph from manifests in the directory, parses the
    query string, executes it, and prints results to stdout.

    Args:
        query: Natural language query string (e.g., "What defines X?")
        manifest_dir: Path to the directory containing manifest files.

    Returns:
        None
    """
    # Build the knowledge graph
    builder = KnowledgeGraphBuilder(manifest_dir)
    graph = builder.build()

    # Check for empty graph
    if graph.node_count == 0:
        print("No manifests found in directory.")
        return

    # Parse and execute the query
    parser = QueryParser()
    intent = parser.parse(query)

    executor = QueryExecutor(graph)
    result = executor.execute(intent)

    # Print results
    print(f"Query: {query}")
    print(f"Result: {result.message}")

    if result.data:
        if isinstance(result.data, list):
            for item in result.data:
                if hasattr(item, "id"):
                    print(f"  - {item.id}")
                else:
                    print(f"  - {item}")
        elif isinstance(result.data, dict):
            for key, value in result.data.items():
                print(f"  {key}: {value}")


def handle_export(format: str, output: Path, manifest_dir: Path) -> None:
    """Export the knowledge graph to a file.

    Builds the knowledge graph and exports it to the specified format.
    Supported formats: json, dot, graphml.

    Args:
        format: Output format (json, dot, or graphml).
        output: Path where the output file will be written.
        manifest_dir: Path to the directory containing manifest files.

    Returns:
        None

    Raises:
        ValueError: If format is not supported.
    """
    # Build the knowledge graph
    builder = KnowledgeGraphBuilder(manifest_dir)
    graph = builder.build()

    # Create output directory if needed
    output.parent.mkdir(parents=True, exist_ok=True)

    # Export based on format
    if format == "json":
        export_json(graph, output)
    elif format == "dot":
        export_dot(graph, output)
    elif format == "graphml":
        export_graphml(graph, output)
    else:
        raise ValueError(f"Unsupported export format: {format}")

    print(f"Graph exported to {output}")


def handle_analysis(analysis_type: str, manifest_dir: Path) -> None:
    """Run graph analysis.

    Builds the knowledge graph and runs the specified analysis type.
    Supported types: find-cycles, show-stats.

    Args:
        analysis_type: Type of analysis to run (find-cycles or show-stats).
        manifest_dir: Path to the directory containing manifest files.

    Returns:
        None

    Raises:
        ValueError: If analysis_type is not supported.
    """
    # Build the knowledge graph
    builder = KnowledgeGraphBuilder(manifest_dir)
    graph = builder.build()

    if analysis_type == "find-cycles":
        cycles = find_cycles(graph)
        if cycles:
            print(f"Found {len(cycles)} cycle(s):")
            for i, cycle in enumerate(cycles, 1):
                cycle_ids = " -> ".join(node.id for node in cycle)
                print(f"  Cycle {i}: {cycle_ids}")
        else:
            print("No cycles found in the graph.")

    elif analysis_type == "show-stats":
        print("Graph Statistics:")
        print(f"  Total nodes: {graph.node_count}")
        print(f"  Total edges: {graph.edge_count}")

        # Count nodes by type
        type_counts = {}
        for node in graph.nodes:
            type_name = node.node_type.value
            type_counts[type_name] = type_counts.get(type_name, 0) + 1

        print("  Node types:")
        for type_name, count in sorted(type_counts.items()):
            print(f"    {type_name}: {count}")

    else:
        raise ValueError(f"Unsupported analysis type: {analysis_type}")
