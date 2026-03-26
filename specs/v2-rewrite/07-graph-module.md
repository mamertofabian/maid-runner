# MAID Runner v2 - Knowledge Graph Module

**References:** [01-architecture.md](01-architecture.md), [03-data-types.md](03-data-types.md), [04-core-manifest.md](04-core-manifest.md)

## Module Location

- `maid_runner/graph/__init__.py` - Re-exports
- `maid_runner/graph/model.py` - Node types, Edge types, KnowledgeGraph
- `maid_runner/graph/builder.py` - GraphBuilder
- `maid_runner/graph/query.py` - GraphQuery
- `maid_runner/graph/export.py` - JSON, DOT, GraphML exporters

## Purpose

The knowledge graph builds a queryable semantic model of the manifest ecosystem. It represents manifests, files, artifacts, and modules as nodes connected by typed edges. This enables:

- "What manifests affect file X?"
- "What would break if I change artifact Y?"
- "Are there circular dependencies?"
- "Show the dependency tree for module Z"

## Data Types (`graph/model.py`)

### NodeType (Enum)

```python
class NodeType(str, Enum):
    MANIFEST = "manifest"
    FILE = "file"
    ARTIFACT = "artifact"
    MODULE = "module"
```

### EdgeType (Enum)

```python
class EdgeType(str, Enum):
    SUPERSEDES = "supersedes"       # Manifest -> Manifest
    CREATES = "creates"             # Manifest -> File
    EDITS = "edits"                 # Manifest -> File
    READS = "reads"                 # Manifest -> File
    DELETES = "deletes"             # Manifest -> File
    DEFINES = "defines"             # File -> Artifact
    DECLARES = "declares"           # Manifest -> Artifact
    CONTAINS = "contains"           # Module -> File, File -> Artifact
    BELONGS_TO = "belongs_to"       # File -> Module, Artifact -> File
    INHERITS = "inherits"           # Class -> Class (via bases)
```

### Node (Dataclass)

```python
@dataclass(frozen=True)
class Node:
    """A node in the knowledge graph."""
    id: str                          # Unique identifier
    node_type: NodeType
    name: str                        # Display name
    metadata: dict = field(default_factory=dict)  # Arbitrary metadata

    # Type-specific fields populated by builder:
    # ManifestNode: goal, task_type, created, supersedes
    # FileNode: language, path
    # ArtifactNode: kind, of, args, returns
    # ModuleNode: path (directory path)
```

### Edge (Dataclass)

```python
@dataclass(frozen=True)
class Edge:
    """A directed edge in the knowledge graph."""
    source: str                      # Source node ID
    target: str                      # Target node ID
    edge_type: EdgeType
    metadata: dict = field(default_factory=dict)
```

### KnowledgeGraph (Class)

```python
class KnowledgeGraph:
    """In-memory directed graph with O(1) edge lookups.

    Uses adjacency lists for efficient traversal.
    Thread-safe for read operations after construction.
    """

    def __init__(self):
        self._nodes: dict[str, Node] = {}
        self._outgoing: dict[str, list[Edge]] = {}   # node_id -> outgoing edges
        self._incoming: dict[str, list[Edge]] = {}    # node_id -> incoming edges

    def add_node(self, node: Node) -> None:
        """Add a node. Raises ValueError if ID already exists."""

    def add_edge(self, edge: Edge) -> None:
        """Add a directed edge. Both source and target must exist."""

    def get_node(self, node_id: str) -> Node | None:
        """Get node by ID, or None."""

    def get_nodes(self, node_type: NodeType | None = None) -> list[Node]:
        """Get all nodes, optionally filtered by type."""

    def get_edges(self, edge_type: EdgeType | None = None) -> list[Edge]:
        """Get all edges, optionally filtered by type."""

    def outgoing_edges(self, node_id: str, edge_type: EdgeType | None = None) -> list[Edge]:
        """Get outgoing edges from a node."""

    def incoming_edges(self, node_id: str, edge_type: EdgeType | None = None) -> list[Edge]:
        """Get incoming edges to a node."""

    def neighbors(self, node_id: str, edge_type: EdgeType | None = None) -> list[Node]:
        """Get nodes connected by outgoing edges."""

    @property
    def node_count(self) -> int:
        return len(self._nodes)

    @property
    def edge_count(self) -> int:
        return sum(len(edges) for edges in self._outgoing.values())
```

## GraphBuilder (`graph/builder.py`)

```python
class GraphBuilder:
    """Constructs a KnowledgeGraph from a ManifestChain.

    Usage:
        chain = ManifestChain("manifests/")
        builder = GraphBuilder()
        graph = builder.build(chain)
    """

    def build(self, chain: ManifestChain) -> KnowledgeGraph:
        """Build complete knowledge graph from manifest chain.

        Creates nodes for:
        - Each active manifest
        - Each referenced file
        - Each declared artifact
        - Each module (derived from file paths)

        Creates edges for:
        - Supersession relationships
        - File operations (creates, edits, reads, deletes)
        - Artifact definitions and declarations
        - Module containment
        - Inheritance relationships
        """

    def build_from_manifests(self, manifests: list[Manifest]) -> KnowledgeGraph:
        """Build graph from explicit manifest list (no chain resolution)."""
```

### Node ID Conventions

```
Manifest nodes:  "manifest:{slug}"         e.g. "manifest:add-jwt-auth"
File nodes:      "file:{path}"             e.g. "file:src/auth/service.py"
Artifact nodes:  "artifact:{path}:{name}"  e.g. "artifact:src/auth/service.py:AuthService"
Module nodes:    "module:{dir_path}"        e.g. "module:src/auth"
```

### Build Algorithm

```
For each active manifest in chain:
    1. Create manifest node
    2. For each superseded slug: create SUPERSEDES edge (if target manifest exists)
    3. For each file in files.create: create file node + CREATES edge
    4. For each file in files.edit: create file node + EDITS edge
    5. For each file in files.read: create file node + READS edge
    6. For each file in files.delete: create file node + DELETES edge
    7. For each artifact in each file:
        a. Create artifact node
        b. Create DECLARES edge (manifest -> artifact)
        c. Create DEFINES edge (file -> artifact)
        d. Create BELONGS_TO edge (artifact -> file)
        e. If artifact has bases, create INHERITS edges
    8. Derive module from file path, create module node + CONTAINS edge
```

## GraphQuery (`graph/query.py`)

```python
class GraphQuery:
    """Query interface for the knowledge graph.

    Provides high-level analysis operations built on graph traversal.
    """

    def __init__(self, graph: KnowledgeGraph):
        self._graph = graph

    # --- Node Search ---

    def find_node(self, name: str, node_type: NodeType | None = None) -> Node | None:
        """Find a node by name, optionally filtered by type."""

    def find_nodes(self, pattern: str, node_type: NodeType | None = None) -> list[Node]:
        """Find nodes matching a pattern (supports glob-style wildcards)."""

    # --- Traversal ---

    def get_dependents(self, node_id: str) -> list[Node]:
        """Find all nodes that depend on the given node (reverse dependencies)."""

    def get_dependencies(self, node_id: str) -> list[Node]:
        """Find all nodes that the given node depends on."""

    def get_transitive_dependents(self, node_id: str) -> list[Node]:
        """Find all transitive dependents (full impact set)."""

    # --- Analysis ---

    def find_cycles(self) -> list[list[str]]:
        """Detect cycles in the graph. Returns list of cycle paths."""

    def is_acyclic(self) -> bool:
        """Check if the graph has no cycles."""

    def dependency_analysis(self, file_path: str) -> dict:
        """Analyze dependencies for a file.

        Returns:
            {
                "file": file_path,
                "manifests": [...],      # Manifests that reference this file
                "artifacts": [...],      # Artifacts defined in this file
                "depends_on": [...],     # Files this file depends on
                "depended_by": [...],    # Files that depend on this file
            }
        """

    def impact_analysis(self, artifact_name: str) -> dict:
        """Analyze the impact of changing an artifact.

        Returns:
            {
                "artifact": artifact_name,
                "defined_in": file_path,
                "manifests": [...],          # Manifests declaring this artifact
                "direct_dependents": [...],  # Directly affected artifacts
                "transitive_impact": [...],  # All transitively affected nodes
            }
        """

    # --- Natural Language Query ---

    def query(self, question: str) -> dict:
        """Parse a natural language question and execute it.

        Supports queries like:
        - "What defines AuthService?"
        - "What depends on service.py?"
        - "Show impact of changing login()"
        - "Find circular dependencies"

        Returns:
            Result dict with 'query_type', 'results', 'summary' fields.
        """
```

### Query Parser

```python
class QueryParser:
    """Parses natural language queries into structured intents."""

    class QueryIntent(Enum):
        FIND_DEFINITION = "find_definition"
        FIND_DEPENDENTS = "find_dependents"
        FIND_USAGES = "find_usages"
        ANALYZE_IMPACT = "analyze_impact"
        FIND_CYCLES = "find_cycles"
        LIST_ARTIFACTS = "list_artifacts"
        LIST_MANIFESTS = "list_manifests"

    def parse(self, question: str) -> tuple[QueryIntent, dict]:
        """Parse question into intent and parameters.

        Uses keyword matching:
        - "defines", "definition" -> FIND_DEFINITION
        - "depends", "dependents" -> FIND_DEPENDENTS
        - "uses", "usages", "references" -> FIND_USAGES
        - "impact", "affect" -> ANALYZE_IMPACT
        - "cycle", "circular" -> FIND_CYCLES
        """
```

## Exporters (`graph/export.py`)

```python
def export_json(graph: KnowledgeGraph) -> str:
    """Export graph as JSON.

    Format:
    {
        "nodes": [{"id": "...", "type": "...", "name": "...", "metadata": {...}}],
        "edges": [{"source": "...", "target": "...", "type": "...", "metadata": {...}}]
    }
    """


def export_dot(graph: KnowledgeGraph, *, cluster_by: str = "module") -> str:
    """Export graph as Graphviz DOT format.

    Args:
        cluster_by: Grouping strategy - "module", "manifest", or "none".

    Returns DOT string renderable with `dot -Tpng graph.dot -o graph.png`.
    """


def export_graphml(graph: KnowledgeGraph) -> str:
    """Export graph as GraphML XML format.

    Compatible with yEd, Gephi, and other graph visualization tools.
    """
```

## Integration with Core

The graph module depends on `core/` for manifest loading and chain resolution. It does NOT depend on `validators/` or `cli/`.

```python
# Typical usage
from maid_runner.core.chain import ManifestChain
from maid_runner.graph import GraphBuilder, GraphQuery, export_json

chain = ManifestChain("manifests/")
graph = GraphBuilder().build(chain)
query = GraphQuery(graph)

# Find what would break if we change AuthService
impact = query.impact_analysis("AuthService")

# Export for visualization
print(export_dot(graph))
```
