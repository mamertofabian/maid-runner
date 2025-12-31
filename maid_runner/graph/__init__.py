"""Graph module for the Knowledge Graph Builder.

This module provides data structures for representing the MAID codebase
as a knowledge graph with nodes and edges.
"""

from maid_runner.graph.model import (
    NodeType,
    Node,
    ManifestNode,
    FileNode,
    ArtifactNode,
    ModuleNode,
    EdgeType,
    Edge,
    KnowledgeGraph,
    MANIFEST_PREFIX,
    FILE_PREFIX,
    ARTIFACT_PREFIX,
    MODULE_PREFIX,
    EDGE_PREFIX,
)
from maid_runner.graph.exporters import (
    export_json,
    export_dot,
    export_graphml,
    graph_to_dict,
    graph_to_dot,
    graph_to_graphml,
)
from maid_runner.graph.builder import (
    load_manifest,
    load_manifests,
    create_manifest_node,
    create_file_node,
    create_artifact_node,
    create_module_node,
    create_supersedes_edges,
    create_file_edges,
    create_artifact_edges,
    KnowledgeGraphBuilder,
)
from maid_runner.graph.query import (
    find_nodes_by_type,
    find_node_by_name,
    get_neighbors,
    find_dependents,
    find_dependencies,
    get_dependency_tree,
    find_cycles,
    is_acyclic,
    get_affected_files,
    get_affected_manifests,
    analyze_impact,
    QueryType,
    QueryIntent,
    QueryParser,
    QueryResult,
    QueryExecutor,
)

# Explicit re-exports for MAID validation
# These assignments make imported names visible as module-level attributes
KnowledgeGraph = KnowledgeGraph
export_json = export_json
export_dot = export_dot
export_graphml = export_graphml
graph_to_dict = graph_to_dict
graph_to_dot = graph_to_dot
graph_to_graphml = graph_to_graphml

__all__ = [
    "NodeType",
    "Node",
    "ManifestNode",
    "FileNode",
    "ArtifactNode",
    "ModuleNode",
    "EdgeType",
    "Edge",
    "KnowledgeGraph",
    "MANIFEST_PREFIX",
    "FILE_PREFIX",
    "ARTIFACT_PREFIX",
    "MODULE_PREFIX",
    "EDGE_PREFIX",
    "export_json",
    "export_dot",
    "export_graphml",
    "graph_to_dict",
    "graph_to_dot",
    "graph_to_graphml",
    "load_manifest",
    "load_manifests",
    "create_manifest_node",
    "create_file_node",
    "create_artifact_node",
    "create_module_node",
    "create_supersedes_edges",
    "create_file_edges",
    "create_artifact_edges",
    "KnowledgeGraphBuilder",
    "find_nodes_by_type",
    "find_node_by_name",
    "get_neighbors",
    "find_dependents",
    "find_dependencies",
    "get_dependency_tree",
    "find_cycles",
    "is_acyclic",
    "get_affected_files",
    "get_affected_manifests",
    "analyze_impact",
    "QueryType",
    "QueryIntent",
    "QueryParser",
    "QueryResult",
    "QueryExecutor",
]
