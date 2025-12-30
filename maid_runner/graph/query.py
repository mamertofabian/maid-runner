"""Query module for traversing and searching the knowledge graph.

This module provides functions for finding and navigating nodes in the
knowledge graph:
- find_nodes_by_type: Find all nodes matching a specific node type
- find_node_by_name: Search for a node by name or identifier
- get_neighbors: Get all nodes connected to a given node
- find_cycles: Find all cycles (circular dependencies) in the graph
- is_acyclic: Check if the graph has no cycles

Query parsing capabilities:
- QueryType: Enum of query types (FIND_DEFINITION, FIND_DEPENDENTS, etc.)
- QueryIntent: Dataclass representing a parsed query
- QueryParser: Parser for natural language-style queries
"""

from dataclasses import dataclass
from enum import Enum
import re
from typing import Any, Dict, List, Optional, Set

from maid_runner.graph.model import (
    KnowledgeGraph,
    Node,
    NodeType,
    EdgeType,
    ManifestNode,
    FileNode,
    ArtifactNode,
    ModuleNode,
)


def find_nodes_by_type(graph: KnowledgeGraph, node_type: NodeType) -> List[Node]:
    """Find all nodes of a specific type in the graph.

    Args:
        graph: The knowledge graph to search.
        node_type: The type of nodes to find.

    Returns:
        List of nodes matching the specified type.
    """
    return [node for node in graph.nodes if node.node_type == node_type]


def find_node_by_name(graph: KnowledgeGraph, name: str) -> Optional[Node]:
    """Find a node by name or identifier.

    Searches for nodes by checking:
    - Node id
    - ManifestNode path
    - FileNode path
    - ArtifactNode name
    - ModuleNode name

    Args:
        graph: The knowledge graph to search.
        name: The name/identifier to search for.

    Returns:
        The first matching node, or None if not found.
    """
    for node in graph.nodes:
        # Check node id
        if node.id == name:
            return node

        # Check type-specific name fields
        if isinstance(node, ManifestNode) and node.path == name:
            return node
        if isinstance(node, FileNode) and node.path == name:
            return node
        if isinstance(node, ArtifactNode) and node.name == name:
            return node
        if isinstance(node, ModuleNode) and node.name == name:
            return node

    return None


def get_neighbors(
    graph: KnowledgeGraph,
    node: Node,
    edge_type: Optional[EdgeType] = None,
) -> List[Node]:
    """Get all nodes connected to the given node.

    Finds neighbors via both outgoing and incoming edges.

    Args:
        graph: The knowledge graph.
        node: The node to find neighbors for.
        edge_type: Optional edge type to filter by.

    Returns:
        List of connected nodes.
    """
    neighbor_ids: set[str] = set()

    for edge in graph.edges:
        # Check if edge matches type filter
        if edge_type is not None and edge.edge_type != edge_type:
            continue

        # Check outgoing edges (node is source)
        if edge.source_id == node.id:
            neighbor_ids.add(edge.target_id)

        # Check incoming edges (node is target)
        if edge.target_id == node.id:
            neighbor_ids.add(edge.source_id)

    # Resolve node IDs to actual nodes
    neighbors: List[Node] = []
    for neighbor_id in neighbor_ids:
        neighbor_node = graph.get_node(neighbor_id)
        if neighbor_node:
            neighbors.append(neighbor_node)

    return neighbors


def find_dependents(graph: KnowledgeGraph, artifact_name: str) -> List[Node]:
    """Find all nodes that depend on (use) the named artifact.

    Searches for nodes connected to the artifact via dependency edges:
    - Manifests that DECLARE the artifact
    - Files that DEFINE the artifact
    - Other artifacts that reference it

    Args:
        graph: The knowledge graph to search.
        artifact_name: Name of the artifact to find dependents for.

    Returns:
        List of nodes that depend on the artifact.
    """
    # First find the artifact node
    artifact_node = find_node_by_name(graph, artifact_name)
    if not artifact_node:
        return []

    dependents: List[Node] = []
    for edge in graph.edges:
        # Find edges where artifact is the target (something points to it)
        if edge.target_id == artifact_node.id:
            source_node = graph.get_node(edge.source_id)
            if source_node and source_node not in dependents:
                dependents.append(source_node)

    return dependents


def find_dependencies(graph: KnowledgeGraph, artifact_name: str) -> List[Node]:
    """Find all nodes that the named artifact depends on.

    Searches for nodes the artifact references via:
    - CONTAINS edges (parent class)
    - File it belongs to
    - Other relationships

    Args:
        graph: The knowledge graph to search.
        artifact_name: Name of the artifact to find dependencies for.

    Returns:
        List of nodes that the artifact depends on.
    """
    # First find the artifact node
    artifact_node = find_node_by_name(graph, artifact_name)
    if not artifact_node:
        return []

    dependencies: List[Node] = []
    for edge in graph.edges:
        # Find edges where artifact is the source (it points to something)
        if edge.source_id == artifact_node.id:
            target_node = graph.get_node(edge.target_id)
            if target_node and target_node not in dependencies:
                dependencies.append(target_node)

        # Also check CONTAINS and DEFINES edges where artifact is the target
        # (has parent class or is defined in a file)
        if edge.target_id == artifact_node.id and edge.edge_type in (
            EdgeType.CONTAINS,
            EdgeType.DEFINES,
        ):
            parent_node = graph.get_node(edge.source_id)
            if parent_node and parent_node not in dependencies:
                dependencies.append(parent_node)

    return dependencies


def get_dependency_tree(
    graph: KnowledgeGraph,
    node: Node,
    depth: int = -1,
    _visited: Optional[set] = None,
) -> Dict[str, Any]:
    """Build a tree of dependencies for a node.

    Args:
        graph: The knowledge graph.
        node: The starting node.
        depth: Maximum depth to traverse (-1 for unlimited).
        _visited: Internal set to track visited nodes (prevents cycles).

    Returns:
        Dict with node info and nested dependencies:
        {
            "id": str,
            "type": str,
            "dependencies": [...]  # nested trees
        }
    """
    if _visited is None:
        _visited = set()

    # Build basic node info
    result: Dict[str, Any] = {
        "id": node.id,
        "type": node.node_type.value,
        "dependencies": [],
    }

    # If at depth limit or already visited, return without dependencies
    if depth == 0 or node.id in _visited:
        return result

    _visited.add(node.id)

    # Get direct dependencies (nodes this node points to)
    next_depth = depth - 1 if depth > 0 else -1

    for edge in graph.edges:
        if edge.source_id == node.id:
            dep_node = graph.get_node(edge.target_id)
            if dep_node and dep_node.id not in _visited:
                dep_tree = get_dependency_tree(
                    graph, dep_node, next_depth, _visited.copy()
                )
                result["dependencies"].append(dep_tree)

    return result


def find_cycles(graph: KnowledgeGraph) -> List[List[Node]]:
    """Find all cycles (circular dependencies) in the graph.

    Uses DFS-based cycle detection algorithm.

    Args:
        graph: The knowledge graph to search

    Returns:
        List of cycles, where each cycle is a list of nodes forming the cycle.
        Returns empty list if no cycles found.
    """
    cycles: List[List[Node]] = []
    visited: Set[str] = set()
    rec_stack: Set[str] = set()

    # Build adjacency list for efficiency
    adjacency: Dict[str, List[str]] = {}
    for node in graph.nodes:
        adjacency[node.id] = []
    for edge in graph.edges:
        if edge.source_id in adjacency:
            adjacency[edge.source_id].append(edge.target_id)

    def _dfs(node_id: str, path: List[str]) -> None:
        visited.add(node_id)
        rec_stack.add(node_id)
        path.append(node_id)

        for neighbor_id in adjacency.get(node_id, []):
            if neighbor_id not in visited:
                _dfs(neighbor_id, path)
            elif neighbor_id in rec_stack:
                # Found a cycle - extract it from path
                cycle_start = path.index(neighbor_id)
                cycle_ids = path[cycle_start:]
                cycle_nodes = [
                    graph.get_node(nid) for nid in cycle_ids if graph.get_node(nid)
                ]
                if cycle_nodes and cycle_nodes not in cycles:
                    cycles.append(cycle_nodes)

        path.pop()
        rec_stack.remove(node_id)

    for node in graph.nodes:
        if node.id not in visited:
            _dfs(node.id, [])

    return cycles


def is_acyclic(graph: KnowledgeGraph) -> bool:
    """Check if the graph has no cycles.

    More efficient than find_cycles when just checking existence.

    Args:
        graph: The knowledge graph to check

    Returns:
        True if the graph has no cycles, False otherwise
    """
    visited: Set[str] = set()
    rec_stack: Set[str] = set()

    # Build adjacency list
    adjacency: Dict[str, List[str]] = {}
    for node in graph.nodes:
        adjacency[node.id] = []
    for edge in graph.edges:
        if edge.source_id in adjacency:
            adjacency[edge.source_id].append(edge.target_id)

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
        if node.id not in visited:
            if _has_cycle(node.id):
                return False

    return True


def get_affected_files(graph: KnowledgeGraph, artifact_name: str) -> List[str]:
    """Find all file paths affected by changes to an artifact.

    Searches for files connected via DEFINES and other file relationships.

    Args:
        graph: The knowledge graph
        artifact_name: Name of the artifact

    Returns:
        List of file path strings that would be affected
    """
    artifact_node = find_node_by_name(graph, artifact_name)
    if not artifact_node:
        return []

    affected_files: List[str] = []

    for edge in graph.edges:
        # Files that DEFINE this artifact
        if edge.edge_type == EdgeType.DEFINES and edge.target_id == artifact_node.id:
            source_node = graph.get_node(edge.source_id)
            if source_node and isinstance(source_node, FileNode):
                if source_node.path not in affected_files:
                    affected_files.append(source_node.path)

    return affected_files


def get_affected_manifests(graph: KnowledgeGraph, artifact_name: str) -> List[str]:
    """Find all manifest paths affected by changes to an artifact.

    Searches for manifests connected via DECLARES and other relationships.

    Args:
        graph: The knowledge graph
        artifact_name: Name of the artifact

    Returns:
        List of manifest path strings that would be affected
    """
    artifact_node = find_node_by_name(graph, artifact_name)
    if not artifact_node:
        return []

    affected_manifests: List[str] = []

    for edge in graph.edges:
        # Manifests that DECLARE this artifact
        if edge.edge_type == EdgeType.DECLARES and edge.target_id == artifact_node.id:
            source_node = graph.get_node(edge.source_id)
            if source_node and isinstance(source_node, ManifestNode):
                if source_node.path not in affected_manifests:
                    affected_manifests.append(source_node.path)

    return affected_manifests


def analyze_impact(graph: KnowledgeGraph, artifact_name: str) -> Dict[str, Any]:
    """Analyze the impact of changing an artifact.

    Computes affected files, manifests, other artifacts, and total impact.

    Args:
        graph: The knowledge graph
        artifact_name: Name of the artifact to analyze

    Returns:
        Dict with keys:
        - affected_files: List of file paths
        - affected_manifests: List of manifest paths
        - affected_artifacts: List of artifact names that depend on this one
        - total_impact_count: Total number of affected items
    """
    affected_files = get_affected_files(graph, artifact_name)
    affected_manifests = get_affected_manifests(graph, artifact_name)

    # Find artifacts that depend on this one (via CONTAINS or other edges)
    artifact_node = find_node_by_name(graph, artifact_name)
    affected_artifacts: List[str] = []

    if artifact_node:
        dependents = find_dependents(graph, artifact_name)
        for dep in dependents:
            if isinstance(dep, ArtifactNode) and dep.name not in affected_artifacts:
                affected_artifacts.append(dep.name)

    total_count = len(affected_files) + len(affected_manifests) + len(affected_artifacts)

    return {
        "affected_files": affected_files,
        "affected_manifests": affected_manifests,
        "affected_artifacts": affected_artifacts,
        "total_impact_count": total_count,
    }


class QueryType(Enum):
    """Types of queries supported by the query parser.

    Values:
        FIND_DEFINITION: What defines X?
        FIND_DEPENDENTS: What depends on X?
        FIND_DEPENDENCIES: What does X depend on?
        FIND_IMPACT: What would break if I change X?
        FIND_CYCLES: Find circular dependencies
        LIST_ARTIFACTS: Show all artifacts in module X
    """

    FIND_DEFINITION = "find_definition"
    FIND_DEPENDENTS = "find_dependents"
    FIND_DEPENDENCIES = "find_dependencies"
    FIND_IMPACT = "find_impact"
    FIND_CYCLES = "find_cycles"
    LIST_ARTIFACTS = "list_artifacts"


@dataclass
class QueryIntent:
    """Parsed query intent with type, target, and original query.

    Attributes:
        query_type: The type of query (QueryType enum value).
        target: Optional target artifact or module name being queried.
        original_query: The original query string that was parsed.
    """

    query_type: QueryType
    target: Optional[str]
    original_query: str

    def __init__(
        self,
        query_type: QueryType,
        target: Optional[str],
        original_query: str,
    ) -> None:
        """Initialize a QueryIntent.

        Args:
            query_type: The type of query.
            target: Optional target artifact/module name.
            original_query: The original query string.
        """
        self.query_type = query_type
        self.target = target
        self.original_query = original_query


class QueryParser:
    """Parser for natural language-style graph queries.

    Converts query strings into structured QueryIntent objects.
    """

    def parse(self, query: str) -> QueryIntent:
        """Parse a query string into a QueryIntent.

        Args:
            query: The natural language query string

        Returns:
            QueryIntent with parsed type and target
        """
        query_type = self._determine_query_type(query)
        target = self._extract_target(query)
        return QueryIntent(
            query_type=query_type,
            target=target,
            original_query=query,
        )

    def _extract_target(self, query: str) -> Optional[str]:
        """Extract the target name from a query.

        Looks for patterns like:
        - "What defines X?"
        - "What depends on X?"
        - "module X"
        - Quoted strings

        Args:
            query: The query string

        Returns:
            The target name, or None if not found
        """
        # Try quoted target first
        quoted_match = re.search(r'["\']([^"\']+)["\']', query)
        if quoted_match:
            return quoted_match.group(1)

        # Pattern: "What defines X?"
        defines_match = re.search(r"what\s+defines\s+(\w+)", query, re.IGNORECASE)
        if defines_match:
            return defines_match.group(1)

        # Pattern: "What depends on X?"
        depends_match = re.search(r"what\s+depends\s+on\s+(\w+)", query, re.IGNORECASE)
        if depends_match:
            return depends_match.group(1)

        # Pattern: "What does X depend on?"
        depend_on_match = re.search(
            r"what\s+does\s+(\w+)\s+depend", query, re.IGNORECASE
        )
        if depend_on_match:
            return depend_on_match.group(1)

        # Pattern: "change X" or "break if I change X"
        change_match = re.search(r"change\s+(\w+)", query, re.IGNORECASE)
        if change_match:
            return change_match.group(1)

        # Pattern: "module X" or "in module X"
        module_match = re.search(r"module\s+(\w+)", query, re.IGNORECASE)
        if module_match:
            return module_match.group(1)

        return None

    def _determine_query_type(self, query: str) -> QueryType:
        """Determine the type of query from the query string.

        Args:
            query: The query string

        Returns:
            The QueryType for this query
        """
        query_lower = query.lower()

        if "defines" in query_lower or "defined" in query_lower:
            return QueryType.FIND_DEFINITION

        if "depends on" in query_lower and "what" in query_lower:
            return QueryType.FIND_DEPENDENTS

        # Check cycles before dependencies (since "circular dependencies" contains "dependencies")
        if "cycle" in query_lower or "circular" in query_lower:
            return QueryType.FIND_CYCLES

        if "depend on" in query_lower or "dependencies" in query_lower:
            return QueryType.FIND_DEPENDENCIES

        if "break" in query_lower or "impact" in query_lower or "affect" in query_lower:
            return QueryType.FIND_IMPACT

        if (
            "artifact" in query_lower
            or "module" in query_lower
            or "show" in query_lower
        ):
            return QueryType.LIST_ARTIFACTS

        # Default to find definition
        return QueryType.FIND_DEFINITION


@dataclass
class QueryResult:
    """Result of executing a query against the knowledge graph.

    Attributes:
        success: Whether the query executed successfully (bool).
        query_type: The type of query that was executed (QueryType).
        data: The result data - nodes, files, impact dict, etc. (Any).
        message: Human-readable result message (str).
    """

    success: bool
    query_type: QueryType
    data: Any
    message: str

    def __init__(
        self,
        success: bool,
        query_type: QueryType,
        data: Any,
        message: str,
    ) -> None:
        """Initialize a QueryResult.

        Args:
            success: Whether the query executed successfully.
            query_type: The type of query that was executed.
            data: The result data.
            message: Human-readable result message.
        """
        self.success = success
        self.query_type = query_type
        self.data = data
        self.message = message


class QueryExecutor:
    """Executor class that runs parsed QueryIntent objects against a KnowledgeGraph.

    Executes parsed queries against a knowledge graph and returns QueryResult objects.
    Routes to appropriate query functions based on QueryType.
    """

    def __init__(self, graph: KnowledgeGraph) -> None:
        """Initialize the QueryExecutor with a KnowledgeGraph instance.

        Args:
            graph: The knowledge graph to query.
        """
        self.graph = graph

    def execute(self, intent: QueryIntent) -> QueryResult:
        """Execute a parsed query intent and return the result.

        Routes to appropriate query function based on QueryType.

        Args:
            intent: The parsed query intent.

        Returns:
            QueryResult with success status, data, and message.
        """
        target = intent.target
        query_type = intent.query_type

        if query_type == QueryType.FIND_DEFINITION:
            return self._execute_find_definition(target, query_type)
        elif query_type == QueryType.FIND_DEPENDENTS:
            return self._execute_find_dependents(target, query_type)
        elif query_type == QueryType.FIND_DEPENDENCIES:
            return self._execute_find_dependencies(target, query_type)
        elif query_type == QueryType.FIND_IMPACT:
            return self._execute_find_impact(target, query_type)
        elif query_type == QueryType.FIND_CYCLES:
            return self._execute_find_cycles(query_type)
        elif query_type == QueryType.LIST_ARTIFACTS:
            return self._execute_list_artifacts(target, query_type)

        return QueryResult(
            success=False,
            query_type=query_type,
            data=None,
            message="Unknown query type",
        )

    def _execute_find_definition(
        self, target: Optional[str], query_type: QueryType
    ) -> QueryResult:
        """Execute a FIND_DEFINITION query."""
        if not target:
            return QueryResult(False, query_type, None, "No target specified")

        node = find_node_by_name(self.graph, target)
        if node:
            dependents = find_dependents(self.graph, target)
            return QueryResult(
                True,
                query_type,
                {"node": node, "defined_by": dependents},
                f"Found definition for '{target}'",
            )
        return QueryResult(False, query_type, None, f"'{target}' not found")

    def _execute_find_dependents(
        self, target: Optional[str], query_type: QueryType
    ) -> QueryResult:
        """Execute a FIND_DEPENDENTS query."""
        if not target:
            return QueryResult(False, query_type, [], "No target specified")

        node = find_node_by_name(self.graph, target)
        if not node:
            return QueryResult(False, query_type, [], f"'{target}' not found")

        dependents = find_dependents(self.graph, target)
        return QueryResult(
            True,
            query_type,
            dependents,
            f"Found {len(dependents)} dependent(s) for '{target}'",
        )

    def _execute_find_dependencies(
        self, target: Optional[str], query_type: QueryType
    ) -> QueryResult:
        """Execute a FIND_DEPENDENCIES query."""
        if not target:
            return QueryResult(False, query_type, [], "No target specified")

        node = find_node_by_name(self.graph, target)
        if not node:
            return QueryResult(False, query_type, [], f"'{target}' not found")

        dependencies = find_dependencies(self.graph, target)
        return QueryResult(
            True,
            query_type,
            dependencies,
            f"Found {len(dependencies)} dependenc(ies) for '{target}'",
        )

    def _execute_find_impact(
        self, target: Optional[str], query_type: QueryType
    ) -> QueryResult:
        """Execute a FIND_IMPACT query."""
        if not target:
            return QueryResult(False, query_type, {}, "No target specified")

        node = find_node_by_name(self.graph, target)
        if not node:
            return QueryResult(False, query_type, {}, f"'{target}' not found")

        impact = analyze_impact(self.graph, target)
        return QueryResult(
            True,
            query_type,
            impact,
            f"Impact analysis for '{target}': {impact['total_impact_count']} items affected",
        )

    def _execute_find_cycles(self, query_type: QueryType) -> QueryResult:
        """Execute a FIND_CYCLES query."""
        cycles = find_cycles(self.graph)
        if cycles:
            return QueryResult(
                True, query_type, cycles, f"Found {len(cycles)} cycle(s)"
            )
        return QueryResult(True, query_type, [], "No cycles found")

    def _execute_list_artifacts(
        self, target: Optional[str], query_type: QueryType
    ) -> QueryResult:
        """Execute a LIST_ARTIFACTS query."""
        artifacts = find_nodes_by_type(self.graph, NodeType.ARTIFACT)

        # Filter by module if target specified
        if target:
            artifacts = [
                a
                for a in artifacts
                if hasattr(a, "name") and target.lower() in a.id.lower()
            ]

        return QueryResult(
            True, query_type, artifacts, f"Found {len(artifacts)} artifact(s)"
        )
