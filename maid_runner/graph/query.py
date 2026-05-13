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

import re
from enum import Enum
import fnmatch
from typing import Any, Dict, List, Optional

from maid_runner.graph.model import (
    ArtifactNode,
    EdgeType,
    FileNode,
    KnowledgeGraph,
    ManifestNode,
    Node,
    NodeType,
)
from maid_runner.graph.traversal import (
    _dependency_nodes_for_id,
    _dependent_nodes_for_id,
    _find_dependencies,
    _find_dependents,
    _get_affected_files,
    _get_affected_manifests,
    _get_dependency_tree,
    _get_neighbors,
    _is_acyclic,
    analyze_impact as _analyze_impact,
    find_cycles as _find_cycles,
    find_node_by_name as _find_node_by_name,
    find_nodes_by_type as _find_nodes_by_type,
)


def _matching_name_attribute(node: Node, name: str) -> bool:
    return getattr(node, "name", None) == name


def find_nodes_by_type(graph: KnowledgeGraph, node_type: NodeType) -> List[Node]:
    """Find all nodes of a specific type in the graph.

    Args:
        graph: The knowledge graph to search.
        node_type: The type of nodes to find.

    Returns:
        List of nodes matching the specified type.
    """
    return _find_nodes_by_type(graph, node_type)


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
    return _find_node_by_name(graph, name)


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
    return _get_neighbors(graph, node, edge_type)


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
    return _find_dependents(graph, artifact_name)


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
    return _find_dependencies(graph, artifact_name)


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
    return _get_dependency_tree(graph, node, depth, _visited)


def find_cycles(graph: KnowledgeGraph) -> List[List[Node]]:
    """Find all cycles (circular dependencies) in the graph.

    Uses DFS-based cycle detection algorithm with normalized cycle comparison
    to detect duplicate cycles with different starting points.

    Args:
        graph: The knowledge graph to search

    Returns:
        List of cycles, where each cycle is a list of nodes forming the cycle.
        Returns empty list if no cycles found.
    """
    return _find_cycles(graph)


def is_acyclic(graph: KnowledgeGraph) -> bool:
    """Check if the graph has no cycles.

    More efficient than find_cycles when just checking existence.

    Args:
        graph: The knowledge graph to check

    Returns:
        True if the graph has no cycles, False otherwise
    """
    return _is_acyclic(graph)


def get_affected_files(graph: KnowledgeGraph, artifact_name: str) -> List[str]:
    """Find all file paths affected by changes to an artifact.

    Searches for files connected via DEFINES and other file relationships.

    Args:
        graph: The knowledge graph
        artifact_name: Name of the artifact

    Returns:
        List of file path strings that would be affected
    """
    return _get_affected_files(graph, artifact_name)


def get_affected_manifests(graph: KnowledgeGraph, artifact_name: str) -> List[str]:
    """Find all manifest paths affected by changes to an artifact.

    Searches for manifests connected via DECLARES and other relationships.

    Args:
        graph: The knowledge graph
        artifact_name: Name of the artifact

    Returns:
        List of manifest path strings that would be affected
    """
    return _get_affected_manifests(graph, artifact_name)


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
    return _analyze_impact(graph, artifact_name)


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


class QueryIntent:
    """Parsed query intent with type, target, and original query.

    Attributes:
        query_type: The type of query (QueryType enum value).
        target: Optional target artifact or module name being queried.
        original_query: The original query string that was parsed.
    """

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

    _TARGET_PATTERNS = (
        re.compile(r"what\s+defines\s+(\w+)", re.IGNORECASE),
        re.compile(r"what\s+depends\s+on\s+(\w+)", re.IGNORECASE),
        re.compile(r"what\s+does\s+(\w+)\s+depend", re.IGNORECASE),
        re.compile(r"change\s+(\w+)", re.IGNORECASE),
        re.compile(r"module\s+(\w+)", re.IGNORECASE),
    )

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

        for pattern in self._TARGET_PATTERNS:
            match = pattern.search(query)
            if match:
                return match.group(1)

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


class QueryResult:
    """Result of executing a query against the knowledge graph.

    Attributes:
        success: Whether the query executed successfully (bool).
        query_type: The type of query that was executed (QueryType).
        data: The result data - nodes, files, impact dict, etc. (Any).
        message: Human-readable result message (str).
    """

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
        query_type = intent.query_type
        handlers = {
            QueryType.FIND_DEFINITION: self._execute_find_definition,
            QueryType.FIND_DEPENDENTS: self._execute_find_dependents,
            QueryType.FIND_DEPENDENCIES: self._execute_find_dependencies,
            QueryType.FIND_IMPACT: self._execute_find_impact,
            QueryType.FIND_CYCLES: self._execute_find_cycles,
            QueryType.LIST_ARTIFACTS: self._execute_list_artifacts,
        }
        handler = handlers.get(query_type, self._execute_unknown)
        return handler(intent.target, query_type)

    def _execute_unknown(
        self, _target: Optional[str], query_type: QueryType
    ) -> QueryResult:
        """Execute an unsupported query type."""
        return QueryResult(False, query_type, None, "Unknown query type")

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

    def _execute_find_cycles(
        self, _target: Optional[str], query_type: QueryType
    ) -> QueryResult:
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
        node = find_node_by_name(self._graph, name)
        if node and node_type and node.node_type != node_type:
            return self._find_node_by_name_attribute(name, node_type)
        if node:
            return node
        return self._find_node_by_name_attribute(name, node_type)

    def _find_node_by_name_attribute(
        self, name: str, node_type: Optional[NodeType] = None
    ) -> Optional[Node]:
        for node in self._graph.nodes:
            if node_type and node.node_type != node_type:
                continue
            if _matching_name_attribute(node, name):
                return node
        return None

    def find_nodes(
        self, pattern: str, node_type: Optional[NodeType] = None
    ) -> list[Node]:
        """Find nodes matching a glob pattern, optionally filtered by type."""
        results = []
        for node in self._graph.nodes:
            if node_type and node.node_type != node_type:
                continue
            node_name = getattr(node, "name", "") or ""
            if fnmatch.fnmatch(node_name, pattern) or fnmatch.fnmatch(node.id, pattern):
                results.append(node)
        return results

    def get_dependents(self, node_id: str) -> list[Node]:
        """Find all nodes that depend on the given node (reverse dependencies)."""
        return _dependent_nodes_for_id(self._graph, node_id)

    def get_dependencies(self, node_id: str) -> list[Node]:
        """Find all nodes that the given node depends on."""
        return _dependency_nodes_for_id(self._graph, node_id)

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
        cycles = find_cycles(self._graph)
        return [[n.id for n in cycle] for cycle in cycles]

    def is_acyclic(self) -> bool:
        """Check if the graph has no cycles."""
        return is_acyclic(self._graph)

    def dependency_analysis(self, file_path: str) -> dict[str, Any]:
        """Analyze dependencies for a file."""
        file_id = f"file:{file_path}"
        file_node = self._graph.get_node(file_id)

        manifests: list[str] = []
        artifacts: list[str] = []

        if file_node:
            for edge in self._graph.edges:
                if edge.target_id == file_id and edge.edge_type in (
                    EdgeType.CREATES,
                    EdgeType.EDITS,
                    EdgeType.READS,
                ):
                    source = self._graph.get_node(edge.source_id)
                    if source and isinstance(source, ManifestNode):
                        manifests.append(source.id)

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

    def query(self, question: str) -> dict[str, Any]:
        """Parse a natural language question and dispatch to the appropriate method.

        Args:
            question: Natural language query string.

        Returns:
            Dict with 'query_type', 'results', 'summary' fields.
        """
        parser = QueryParser()
        intent = parser.parse(question)
        executor = QueryExecutor(self._graph)
        qr = executor.execute(intent)
        return {
            "query_type": qr.query_type.value,
            "results": qr.data,
            "summary": qr.message,
        }

    def impact_analysis(self, artifact_name: str) -> dict[str, Any]:
        """Analyze the impact of changing an artifact."""
        affected_files = get_affected_files(self._graph, artifact_name)
        affected_manifests = get_affected_manifests(self._graph, artifact_name)

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
