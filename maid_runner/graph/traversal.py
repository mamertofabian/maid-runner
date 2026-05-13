"""Traversal and impact helpers for the knowledge graph."""

from typing import Any, Dict, List, Optional, Set

from maid_runner.graph.model import (
    ArtifactNode,
    EdgeType,
    FileNode,
    KnowledgeGraph,
    ManifestNode,
    ModuleNode,
    Node,
    NodeType,
)


def _append_unique(nodes: List[Node], node: Node) -> None:
    """Append a graph node only once while preserving traversal order."""
    if node not in nodes:
        nodes.append(node)


def _node_matches_name(node: Node, name: str) -> bool:
    if node.id == name:
        return True
    if isinstance(node, ManifestNode):
        return node.path == name
    if isinstance(node, FileNode):
        return node.path == name
    if isinstance(node, ArtifactNode):
        return node.name == name
    if isinstance(node, ModuleNode):
        return node.name == name
    return False


def _build_adjacency(graph: KnowledgeGraph) -> Dict[str, List[str]]:
    adjacency: Dict[str, List[str]] = {node.id: [] for node in graph.nodes}
    for edge in graph.edges:
        if edge.source_id in adjacency:
            adjacency[edge.source_id].append(edge.target_id)
    return adjacency


def _dependent_nodes_for_id(graph: KnowledgeGraph, node_id: str) -> List[Node]:
    dependents: List[Node] = []
    for edge in graph.edges:
        if edge.target_id == node_id:
            source_node = graph.get_node(edge.source_id)
            if source_node:
                _append_unique(dependents, source_node)
    return dependents


def _dependency_nodes_for_id(graph: KnowledgeGraph, node_id: str) -> List[Node]:
    dependencies: List[Node] = []
    for edge in graph.edges:
        if edge.source_id == node_id:
            target_node = graph.get_node(edge.target_id)
            if target_node:
                _append_unique(dependencies, target_node)

        if edge.target_id == node_id and edge.edge_type in (
            EdgeType.CONTAINS,
            EdgeType.DEFINES,
        ):
            parent_node = graph.get_node(edge.source_id)
            if parent_node:
                _append_unique(dependencies, parent_node)
    return dependencies


def find_nodes_by_type(graph: KnowledgeGraph, node_type: NodeType) -> List[Node]:
    """Find all nodes of a specific type in the graph."""
    return [node for node in graph.nodes if node.node_type == node_type]


def find_node_by_name(graph: KnowledgeGraph, name: str) -> Optional[Node]:
    """Find a node by name or identifier."""
    for node in graph.nodes:
        if _node_matches_name(node, name):
            return node

    return None


def _get_neighbors(
    graph: KnowledgeGraph,
    node: Node,
    edge_type: Optional[EdgeType] = None,
) -> List[Node]:
    """Get all nodes connected to the given node."""
    neighbor_ids: set[str] = set()

    for edge in graph.edges:
        if edge_type is not None and edge.edge_type != edge_type:
            continue

        if edge.source_id == node.id:
            neighbor_ids.add(edge.target_id)

        if edge.target_id == node.id:
            neighbor_ids.add(edge.source_id)

    neighbors: List[Node] = []
    for neighbor_id in neighbor_ids:
        neighbor_node = graph.get_node(neighbor_id)
        if neighbor_node:
            neighbors.append(neighbor_node)

    return neighbors


def _find_dependents(graph: KnowledgeGraph, artifact_name: str) -> List[Node]:
    """Find all nodes that depend on the named artifact."""
    artifact_node = find_node_by_name(graph, artifact_name)
    if not artifact_node:
        return []

    return _dependent_nodes_for_id(graph, artifact_node.id)


def _find_dependencies(graph: KnowledgeGraph, artifact_name: str) -> List[Node]:
    """Find all nodes the named artifact depends on."""
    artifact_node = find_node_by_name(graph, artifact_name)
    if not artifact_node:
        return []

    return _dependency_nodes_for_id(graph, artifact_node.id)


def _get_dependency_tree(
    graph: KnowledgeGraph,
    node: Node,
    depth: int = -1,
    _visited: Optional[set] = None,
) -> Dict[str, Any]:
    """Build a tree of dependencies for a node."""
    if _visited is None:
        _visited = set()

    result: Dict[str, Any] = {
        "id": node.id,
        "type": node.node_type.value,
        "dependencies": [],
    }

    if depth == 0 or node.id in _visited:
        return result

    _visited.add(node.id)
    next_depth = depth - 1 if depth > 0 else -1

    for edge in graph.edges:
        if edge.source_id == node.id:
            dep_node = graph.get_node(edge.target_id)
            if dep_node and dep_node.id not in _visited:
                dep_tree = _get_dependency_tree(
                    graph, dep_node, next_depth, _visited.copy()
                )
                result["dependencies"].append(dep_tree)

    return result


def _normalize_cycle(cycle_ids: List[str]) -> tuple:
    """Normalize a cycle by rotating to start with the smallest ID."""
    if not cycle_ids:
        return tuple()
    min_idx = cycle_ids.index(min(cycle_ids))
    rotated = cycle_ids[min_idx:] + cycle_ids[:min_idx]
    return tuple(rotated)


def find_cycles(graph: KnowledgeGraph) -> List[List[Node]]:
    """Find all cycles in the graph."""
    cycles: List[List[Node]] = []
    seen_cycles: Set[tuple] = set()
    visited: Set[str] = set()
    rec_stack: Set[str] = set()

    adjacency = _build_adjacency(graph)

    def _dfs(node_id: str, path: List[str]) -> None:
        visited.add(node_id)
        rec_stack.add(node_id)
        path.append(node_id)

        for neighbor_id in adjacency.get(node_id, []):
            if neighbor_id not in visited:
                _dfs(neighbor_id, path)
            elif neighbor_id in rec_stack:
                cycle_start = path.index(neighbor_id)
                cycle_ids = path[cycle_start:]
                normalized = _normalize_cycle(cycle_ids)
                if normalized not in seen_cycles:
                    seen_cycles.add(normalized)
                    cycle_nodes_raw = [graph.get_node(nid) for nid in cycle_ids]
                    cycle_nodes = [n for n in cycle_nodes_raw if n is not None]
                    if cycle_nodes:
                        cycles.append(cycle_nodes)

        path.pop()
        rec_stack.remove(node_id)

    for node in graph.nodes:
        if node.id not in visited:
            _dfs(node.id, [])

    return cycles


def _is_acyclic(graph: KnowledgeGraph) -> bool:
    """Check if the graph has no cycles."""
    visited: Set[str] = set()
    rec_stack: Set[str] = set()

    adjacency = _build_adjacency(graph)

    def _has_cycle(node_id: str) -> bool:
        visited.add(node_id)
        rec_stack.add(node_id)

        for neighbor_id in adjacency.get(node_id, []):
            if neighbor_id not in visited:
                if _has_cycle(neighbor_id):
                    return True
            elif neighbor_id in rec_stack:
                return True

        rec_stack.remove(node_id)
        return False

    for node in graph.nodes:
        if node.id not in visited and _has_cycle(node.id):
            return False

    return True


def _get_affected_files(graph: KnowledgeGraph, artifact_name: str) -> List[str]:
    """Find all file paths affected by changes to an artifact."""
    artifact_node = find_node_by_name(graph, artifact_name)
    if not artifact_node:
        return []

    affected_files: List[str] = []

    for edge in graph.edges:
        if edge.edge_type == EdgeType.DEFINES and edge.target_id == artifact_node.id:
            source_node = graph.get_node(edge.source_id)
            if source_node and isinstance(source_node, FileNode):
                if source_node.path not in affected_files:
                    affected_files.append(source_node.path)

    return affected_files


def _get_affected_manifests(graph: KnowledgeGraph, artifact_name: str) -> List[str]:
    """Find all manifest paths affected by changes to an artifact."""
    artifact_node = find_node_by_name(graph, artifact_name)
    if not artifact_node:
        return []

    affected_manifests: List[str] = []

    for edge in graph.edges:
        if edge.edge_type == EdgeType.DECLARES and edge.target_id == artifact_node.id:
            source_node = graph.get_node(edge.source_id)
            if source_node and isinstance(source_node, ManifestNode):
                if source_node.path not in affected_manifests:
                    affected_manifests.append(source_node.path)

    return affected_manifests


def analyze_impact(graph: KnowledgeGraph, artifact_name: str) -> Dict[str, Any]:
    """Analyze the impact of changing an artifact."""
    affected_files = _get_affected_files(graph, artifact_name)
    affected_manifests = _get_affected_manifests(graph, artifact_name)

    artifact_node = find_node_by_name(graph, artifact_name)
    affected_artifacts: List[str] = []

    if artifact_node:
        dependents = _find_dependents(graph, artifact_name)
        for dep in dependents:
            if isinstance(dep, ArtifactNode) and dep.name not in affected_artifacts:
                affected_artifacts.append(dep.name)

    total_count = (
        len(affected_files) + len(affected_manifests) + len(affected_artifacts)
    )

    return {
        "affected_files": affected_files,
        "affected_manifests": affected_manifests,
        "affected_artifacts": affected_artifacts,
        "total_impact_count": total_count,
    }
