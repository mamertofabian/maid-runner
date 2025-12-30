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

__all__ = [
    "NodeType",
    "Node",
    "ManifestNode",
    "FileNode",
    "ArtifactNode",
    "ModuleNode",
    "EdgeType",
    "Edge",
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
]
