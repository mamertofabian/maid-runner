"""V2-compatible graph query interface using v2 types.

Provides the GraphQuery class that wraps the existing query functions
with a cleaner OO interface using v2 Manifest/ManifestChain types.
"""

from __future__ import annotations

import fnmatch
from typing import Any, Optional

from maid_runner.graph.model import (
    ArtifactNode,
    EdgeType,
    FileNode,
    KnowledgeGraph,
    ManifestNode,
    Node,
    NodeType,
)
from maid_runner.graph.query import (
    find_cycles as _find_cycles,
    find_node_by_name as _find_node_by_name,
    get_affected_files as _get_affected_files,
    get_affected_manifests as _get_affected_manifests,
    is_acyclic as _is_acyclic,
)


class GraphQuery:
    """Query interface for the knowledge graph.

    Provides high-level analysis operations built on graph traversal.
    """

    def __init__(self, graph: KnowledgeGraph):
        self._graph = graph

    def find_node(
        self, name: str, node_type: Optional[NodeType] = None
    ) -> Optional[Node]:
        """Find a node by name, optionally filtered by type."""
        node = _find_node_by_name(self._graph, name)
        if node and node_type and node.node_type != node_type:
            # Try searching by attribute name for specific types
            for n in self._graph.nodes:
                if n.node_type != node_type:
                    continue
                if hasattr(n, "name") and n.name == name:
                    return n
            return None
        if node:
            return node

        # Fallback: search in node attributes
        for n in self._graph.nodes:
            if node_type and n.node_type != node_type:
                continue
            if hasattr(n, "name") and n.name == name:
                return n
        return None

    def find_nodes(
        self, pattern: str, node_type: Optional[NodeType] = None
    ) -> list[Node]:
        """Find nodes matching a glob pattern, optionally filtered by type."""
        results = []
        for node in self._graph.nodes:
            if node_type and node.node_type != node_type:
                continue
            # Match against node name or id
            node_name = getattr(node, "name", "") or ""
            if fnmatch.fnmatch(node_name, pattern) or fnmatch.fnmatch(node.id, pattern):
                results.append(node)
        return results

    def get_dependents(self, node_id: str) -> list[Node]:
        """Find all nodes that depend on the given node (reverse dependencies)."""
        dependents = []
        for edge in self._graph.edges:
            if edge.target_id == node_id:
                source = self._graph.get_node(edge.source_id)
                if source and source not in dependents:
                    dependents.append(source)
        return dependents

    def get_dependencies(self, node_id: str) -> list[Node]:
        """Find all nodes that the given node depends on."""
        deps = []
        for edge in self._graph.edges:
            if edge.source_id == node_id:
                target = self._graph.get_node(edge.target_id)
                if target and target not in deps:
                    deps.append(target)
            # Also include reverse containment/defines
            if edge.target_id == node_id and edge.edge_type in (
                EdgeType.CONTAINS,
                EdgeType.DEFINES,
            ):
                parent = self._graph.get_node(edge.source_id)
                if parent and parent not in deps:
                    deps.append(parent)
        return deps

    def get_transitive_dependents(self, node_id: str) -> list[Node]:
        """Find all transitive dependents (full impact set)."""
        visited: set[str] = set()
        result: list[Node] = []
        stack = [node_id]

        while stack:
            current = stack.pop()
            for edge in self._graph.edges:
                if edge.target_id == current and edge.source_id not in visited:
                    visited.add(edge.source_id)
                    node = self._graph.get_node(edge.source_id)
                    if node:
                        result.append(node)
                        stack.append(edge.source_id)

        return result

    def find_cycles(self) -> list[list[str]]:
        """Detect cycles in the graph. Returns list of cycle paths."""
        cycles = _find_cycles(self._graph)
        return [[n.id for n in cycle] for cycle in cycles]

    def is_acyclic(self) -> bool:
        """Check if the graph has no cycles."""
        return _is_acyclic(self._graph)

    def dependency_analysis(self, file_path: str) -> dict[str, Any]:
        """Analyze dependencies for a file."""
        file_id = f"file:{file_path}"
        file_node = self._graph.get_node(file_id)

        manifests = []
        artifacts = []

        if file_node:
            # Find manifests that reference this file
            for edge in self._graph.edges:
                if edge.target_id == file_id and edge.edge_type in (
                    EdgeType.CREATES,
                    EdgeType.EDITS,
                    EdgeType.READS,
                ):
                    source = self._graph.get_node(edge.source_id)
                    if source and isinstance(source, ManifestNode):
                        manifests.append(source.id)

                # Find artifacts defined in this file
                if edge.source_id == file_id and edge.edge_type == EdgeType.DEFINES:
                    target = self._graph.get_node(edge.target_id)
                    if target and isinstance(target, ArtifactNode):
                        artifacts.append(target.name)

        return {
            "file": file_path,
            "manifests": manifests,
            "artifacts": artifacts,
            "depends_on": [],
            "depended_by": [],
        }

    def impact_analysis(self, artifact_name: str) -> dict[str, Any]:
        """Analyze the impact of changing an artifact."""
        affected_files = _get_affected_files(self._graph, artifact_name)
        affected_manifests = _get_affected_manifests(self._graph, artifact_name)

        # Find the artifact node
        artifact_node = None
        for n in self._graph.nodes:
            if isinstance(n, ArtifactNode) and n.name == artifact_name:
                artifact_node = n
                break

        defined_in = None
        if artifact_node:
            for edge in self._graph.edges:
                if (
                    edge.target_id == artifact_node.id
                    and edge.edge_type == EdgeType.DEFINES
                ):
                    source = self._graph.get_node(edge.source_id)
                    if source and isinstance(source, FileNode):
                        defined_in = source.path
                        break

        return {
            "artifact": artifact_name,
            "defined_in": defined_in,
            "manifests": affected_manifests,
            "direct_dependents": affected_files,
            "transitive_impact": [],
        }
