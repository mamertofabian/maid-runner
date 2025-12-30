"""Graph data structures for the Knowledge Graph Builder.

This module defines the core node and edge types used to represent elements of
the MAID codebase as a knowledge graph.

Node Types:
- NodeType: Enum defining the available node categories
- Node: Base dataclass with common attributes
- ManifestNode: Represents a MAID manifest file
- FileNode: Represents a tracked source file
- ArtifactNode: Represents a code artifact (function, class, etc.)
- ModuleNode: Represents a Python module

Edge Types:
- EdgeType: Enum defining relationship types between nodes
- Edge: Dataclass representing a directed edge between nodes
"""

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional


class NodeType(Enum):
    """Enumeration of graph node types.

    Defines the categories of nodes that can exist in the knowledge graph:
    - MANIFEST: A MAID manifest file
    - FILE: A tracked source file
    - ARTIFACT: A code artifact (function, class, attribute)
    - MODULE: A Python module
    """

    MANIFEST = "manifest"
    FILE = "file"
    ARTIFACT = "artifact"
    MODULE = "module"


@dataclass
class Node:
    """Base class for all graph nodes.

    Attributes:
        id: Unique identifier for the node.
        node_type: The type of this node (from NodeType enum).
        attributes: Additional metadata as key-value pairs.
    """

    id: str
    node_type: NodeType
    attributes: Dict[str, Any] = field(default_factory=dict)

    def __init__(
        self,
        id: str,
        node_type: NodeType,
        attributes: Optional[Dict[str, Any]] = None,
    ) -> None:
        """Initialize a Node.

        Args:
            id: Unique identifier for the node.
            node_type: The type of this node.
            attributes: Optional additional metadata.
        """
        self.id = id
        self.node_type = node_type
        self.attributes = attributes if attributes is not None else {}


@dataclass
class ManifestNode(Node):
    """Node representing a MAID manifest file.

    Attributes:
        id: Unique identifier for the node (inherited).
        node_type: Always NodeType.MANIFEST (auto-set).
        attributes: Additional metadata (inherited).
        path: File path to the manifest.
        goal: Goal description from the manifest.
        task_type: Task type (create, edit, refactor, snapshot).
        version: Manifest version string.
    """

    path: str = ""
    goal: str = ""
    task_type: str = ""
    version: str = ""

    def __init__(
        self,
        id: str,
        path: str,
        goal: str,
        task_type: str,
        version: str,
        attributes: Optional[Dict[str, Any]] = None,
    ) -> None:
        """Initialize a ManifestNode.

        Args:
            id: Unique identifier for the node.
            path: File path to the manifest.
            goal: Goal description from the manifest.
            task_type: Task type (create, edit, refactor, snapshot).
            version: Manifest version string.
            attributes: Optional additional metadata.
        """
        super().__init__(
            id=id,
            node_type=NodeType.MANIFEST,
            attributes=attributes if attributes is not None else {},
        )
        self.path = path
        self.goal = goal
        self.task_type = task_type
        self.version = version


@dataclass
class FileNode(Node):
    """Node representing a tracked file.

    Attributes:
        id: Unique identifier for the node (inherited).
        node_type: Always NodeType.FILE (auto-set).
        attributes: Additional metadata (inherited).
        path: File path.
        status: File status (e.g., tracked, untracked, registered).
    """

    path: str = ""
    status: str = ""

    def __init__(
        self,
        id: str,
        path: str,
        status: str,
        attributes: Optional[Dict[str, Any]] = None,
    ) -> None:
        """Initialize a FileNode.

        Args:
            id: Unique identifier for the node.
            path: File path.
            status: File status (e.g., tracked, untracked).
            attributes: Optional additional metadata.
        """
        super().__init__(
            id=id,
            node_type=NodeType.FILE,
            attributes=attributes if attributes is not None else {},
        )
        self.path = path
        self.status = status


@dataclass
class ArtifactNode(Node):
    """Node representing a code artifact.

    Represents functions, classes, attributes, and other code elements.

    Attributes:
        id: Unique identifier for the node (inherited).
        node_type: Always NodeType.ARTIFACT (auto-set).
        attributes: Additional metadata (inherited).
        name: Name of the artifact.
        artifact_type: Type of artifact (function, class, attribute).
        signature: Optional function/method signature.
        parent_class: Optional parent class for methods/attributes.
    """

    name: str = ""
    artifact_type: str = ""
    signature: Optional[str] = None
    parent_class: Optional[str] = None

    def __init__(
        self,
        id: str,
        name: str,
        artifact_type: str,
        signature: Optional[str] = None,
        parent_class: Optional[str] = None,
        attributes: Optional[Dict[str, Any]] = None,
    ) -> None:
        """Initialize an ArtifactNode.

        Args:
            id: Unique identifier for the node.
            name: Name of the artifact.
            artifact_type: Type of artifact (function, class, attribute).
            signature: Optional function/method signature.
            parent_class: Optional parent class for methods/attributes.
            attributes: Optional additional metadata.
        """
        super().__init__(
            id=id,
            node_type=NodeType.ARTIFACT,
            attributes=attributes if attributes is not None else {},
        )
        self.name = name
        self.artifact_type = artifact_type
        self.signature = signature
        self.parent_class = parent_class


@dataclass
class ModuleNode(Node):
    """Node representing a Python module.

    Attributes:
        id: Unique identifier for the node (inherited).
        node_type: Always NodeType.MODULE (auto-set).
        attributes: Additional metadata (inherited).
        name: Module name.
        package: Package name the module belongs to.
    """

    name: str = ""
    package: Optional[str] = None

    def __init__(
        self,
        id: str,
        name: str,
        package: Optional[str],
        attributes: Optional[Dict[str, Any]] = None,
    ) -> None:
        """Initialize a ModuleNode.

        Args:
            id: Unique identifier for the node.
            name: Module name.
            package: Package name the module belongs to.
            attributes: Optional additional metadata.
        """
        super().__init__(
            id=id,
            node_type=NodeType.MODULE,
            attributes=attributes if attributes is not None else {},
        )
        self.name = name
        self.package = package


class EdgeType(Enum):
    """Enumeration of graph edge types.

    Defines the types of relationships that can exist between nodes
    in the knowledge graph:
    - SUPERSEDES: One manifest replacing another
    - CREATES: A manifest creating a file
    - EDITS: A manifest editing a file
    - READS: A manifest reading/depending on a file
    - DEFINES: A file defining an artifact
    - DECLARES: A manifest declaring an artifact
    - CONTAINS: A parent containing a child element
    - INHERITS: Class inheritance relationship
    - BELONGS_TO: Entity membership relationship
    """

    SUPERSEDES = "supersedes"
    CREATES = "creates"
    EDITS = "edits"
    READS = "reads"
    DEFINES = "defines"
    DECLARES = "declares"
    CONTAINS = "contains"
    INHERITS = "inherits"
    BELONGS_TO = "belongs_to"


@dataclass
class Edge:
    """Dataclass representing a graph edge.

    Represents a directed relationship between two nodes in the knowledge graph.

    Attributes:
        id: Unique identifier for the edge.
        edge_type: The type of relationship (from EdgeType enum).
        source_id: ID of the source node.
        target_id: ID of the target node.
        attributes: Additional metadata as key-value pairs.
    """

    id: str
    edge_type: EdgeType
    source_id: str
    target_id: str
    attributes: Dict[str, Any] = field(default_factory=dict)

    def __init__(
        self,
        id: str,
        edge_type: EdgeType,
        source_id: str,
        target_id: str,
        attributes: Optional[Dict[str, Any]] = None,
    ) -> None:
        """Initialize an Edge.

        Args:
            id: Unique identifier for the edge.
            edge_type: The type of relationship.
            source_id: ID of the source node.
            target_id: ID of the target node.
            attributes: Optional additional metadata.
        """
        self.id = id
        self.edge_type = edge_type
        self.source_id = source_id
        self.target_id = target_id
        self.attributes = attributes if attributes is not None else {}


class KnowledgeGraph:
    """Container class for managing nodes and edges in a knowledge graph."""

    def __init__(self) -> None:
        """Initialize an empty knowledge graph."""
        self._nodes: Dict[str, Node] = {}  # node_id -> Node
        self._edges: List[Edge] = []

    def add_node(self, node: Node) -> None:
        """Add a node to the graph.

        Args:
            node: The node to add to the graph.
        """
        self._nodes[node.id] = node

    def add_edge(self, edge: Edge) -> None:
        """Add an edge to the graph.

        Args:
            edge: The edge to add to the graph.
        """
        self._edges.append(edge)

    def get_node(self, node_id: str) -> Optional[Node]:
        """Retrieve a node by its ID.

        Args:
            node_id: The unique identifier of the node to retrieve.

        Returns:
            The node if found, None otherwise.
        """
        return self._nodes.get(node_id)

    def get_edges(self, node_id: str, edge_type: Optional[EdgeType] = None) -> List[Edge]:
        """Get edges for a node, optionally filtered by edge type.

        Args:
            node_id: The ID of the node to get edges for.
            edge_type: Optional edge type to filter by.

        Returns:
            List of edges connected to the specified node.
        """
        result = [
            e for e in self._edges if e.source_id == node_id or e.target_id == node_id
        ]
        if edge_type is not None:
            result = [e for e in result if e.edge_type == edge_type]
        return result

    @property
    def nodes(self) -> List[Node]:
        """Return all nodes in the graph.

        Returns:
            List of all nodes in the graph.
        """
        return list(self._nodes.values())

    @property
    def edges(self) -> List[Edge]:
        """Return all edges in the graph.

        Returns:
            List of all edges in the graph.
        """
        return list(self._edges)

    @property
    def node_count(self) -> int:
        """Return the number of nodes in the graph.

        Returns:
            The count of nodes in the graph.
        """
        return len(self._nodes)

    @property
    def edge_count(self) -> int:
        """Return the number of edges in the graph.

        Returns:
            The count of edges in the graph.
        """
        return len(self._edges)
