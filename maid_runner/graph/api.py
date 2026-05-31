"""Runner-owned graph API helpers for CLI and external automation."""

from __future__ import annotations

import json
from collections import Counter
from pathlib import Path
from typing import Any

from maid_runner.core.chain import ManifestChain
from maid_runner.graph.builder import GraphBuilder
from maid_runner.graph.exporters import graph_to_dot, graph_to_graphml
from maid_runner.graph.model import (
    ArtifactNode,
    Edge,
    FileNode,
    KnowledgeGraph,
    ManifestNode,
    ModuleNode,
    Node,
)
from maid_runner.graph.query import GraphQuery, QueryExecutor, QueryParser


def build_graph_from_manifest_dir(
    manifest_dir: str | Path = "manifests/",
    project_root: str | Path = ".",
) -> KnowledgeGraph:
    """Build a knowledge graph from the active manifest chain."""
    root = Path(project_root)
    manifest_path = Path(manifest_dir)
    if not manifest_path.is_absolute():
        manifest_path = root / manifest_path

    chain = ManifestChain(manifest_path, project_root=str(root))
    load_errors = chain.load_errors
    if load_errors:
        details = "; ".join(
            f"{error.location.file}: {error.message}" for error in load_errors
        )
        raise ValueError(f"Failed to load graph manifests: {details}")
    return GraphBuilder().build(chain)


def graph_stats(graph: KnowledgeGraph) -> dict[str, Any]:
    """Return deterministic summary counts for a graph."""
    node_types = Counter(node.node_type.value for node in graph.nodes)
    edge_types = Counter(edge.edge_type.value for edge in graph.edges)
    return {
        "nodes": graph.node_count,
        "edges": graph.edge_count,
        "node_types": dict(sorted(node_types.items())),
        "edge_types": dict(sorted(edge_types.items())),
    }


def query_graph(graph: KnowledgeGraph, question: str) -> dict[str, Any]:
    """Execute a graph query and return JSON-serializable results."""
    intent = QueryParser().parse(question)
    result = QueryExecutor(graph).execute(intent)
    return {
        "success": result.success,
        "query": intent.original_query,
        "query_type": result.query_type.value,
        "target": intent.target,
        "summary": result.message,
        "results": _serialize_value(result.data),
        "stats": graph_stats(graph),
    }


def analyze_file_dependencies(graph: KnowledgeGraph, file_path: str) -> dict[str, Any]:
    """Analyze manifest and artifact relationships for a file."""
    analysis = GraphQuery(graph).dependency_analysis(file_path)
    return {
        "file": analysis["file"],
        "manifests": sorted(analysis["manifests"]),
        "artifacts": sorted(analysis["artifacts"]),
        "depends_on": sorted(analysis["depends_on"]),
        "depended_by": sorted(analysis["depended_by"]),
        "stats": graph_stats(graph),
    }


def serialize_graph(graph: KnowledgeGraph, export_format: str) -> str:
    """Serialize a graph to a supported textual export format."""
    normalized_format = export_format.lower()
    if normalized_format == "json":
        return json.dumps(_graph_to_deterministic_dict(graph), indent=2, sort_keys=True)
    if normalized_format == "dot":
        return graph_to_dot(graph)
    if normalized_format == "graphml":
        return graph_to_graphml(graph)
    raise ValueError(f"Unsupported graph export format: {export_format}")


def export_graph(
    graph: KnowledgeGraph,
    export_format: str,
    output_path: "str | Path | None" = None,
) -> str:
    """Serialize and optionally write a graph export."""
    content = serialize_graph(graph, export_format)
    if output_path is not None:
        path = Path(output_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
    return content


def _graph_to_deterministic_dict(graph: KnowledgeGraph) -> dict[str, Any]:
    nodes = [_node_to_dict(node) for node in sorted(graph.nodes, key=lambda n: n.id)]
    sorted_edges = sorted(
        graph.edges,
        key=lambda edge: (edge.source_id, edge.target_id, edge.edge_type.value),
    )
    edges = [_edge_to_dict(index, edge) for index, edge in enumerate(sorted_edges, 1)]
    return {"stats": graph_stats(graph), "nodes": nodes, "edges": edges}


def _node_to_dict(node: Node) -> dict[str, Any]:
    result: dict[str, Any] = {
        "id": node.id,
        "type": node.node_type.value,
        "attributes": dict(sorted(node.attributes.items())),
    }
    if isinstance(node, ManifestNode):
        result.update(
            {
                "path": node.path,
                "goal": node.goal,
                "task_type": node.task_type,
                "version": node.version,
            }
        )
    elif isinstance(node, FileNode):
        result.update({"path": node.path, "status": node.status})
    elif isinstance(node, ArtifactNode):
        result.update(
            {
                "name": node.name,
                "artifact_type": node.artifact_type,
                "signature": node.signature,
                "parent_class": node.parent_class,
            }
        )
    elif isinstance(node, ModuleNode):
        result.update({"name": node.name, "package": node.package})
    return result


def _edge_to_dict(index: int, edge: Edge) -> dict[str, Any]:
    return {
        "id": f"edge:{index:04d}",
        "source": edge.source_id,
        "target": edge.target_id,
        "type": edge.edge_type.value,
        "attributes": dict(sorted(edge.attributes.items())),
    }


def _serialize_value(value: Any) -> Any:
    if isinstance(value, Node):
        return _node_to_dict(value)
    if isinstance(value, Edge):
        return {
            "source": value.source_id,
            "target": value.target_id,
            "type": value.edge_type.value,
            "attributes": dict(sorted(value.attributes.items())),
        }
    if isinstance(value, list):
        return [_serialize_value(item) for item in value]
    if isinstance(value, tuple):
        return [_serialize_value(item) for item in value]
    if isinstance(value, dict):
        return {str(key): _serialize_value(item) for key, item in sorted(value.items())}
    return value
