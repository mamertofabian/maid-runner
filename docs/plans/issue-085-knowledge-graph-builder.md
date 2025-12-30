# Implementation Plan: Manifest Knowledge Graph Builder (Issue #85)

## Overview

This plan outlines the MAID-compliant implementation of a Knowledge Graph Builder that creates a queryable graph from manifest chains representing the complete system architecture.

**Issue:** #85 - Manifest Knowledge Graph Builder
**Base Branch:** `dev`
**Feature Branch:** `claude/plan-knowledge-graph-builder-Yo0ch`
**Starting Task Number:** 101 (dev branch has task-100 as latest)

## Dependencies

- **Issue #84 (System-Wide Manifest Snapshot):** ✅ COMPLETE - Available in `maid_runner/cli/snapshot_system.py`

## Architecture Design

### Module Structure

```
maid_runner/
├── graph/                           # NEW PACKAGE
│   ├── __init__.py                 # Public API exports
│   ├── model.py                    # Graph data model (nodes, edges, types)
│   ├── builder.py                  # KnowledgeGraphBuilder class
│   ├── query.py                    # Query engine for graph traversal
│   └── exporters.py                # Export to JSON, DOT, GraphML
├── cli/
│   └── graph.py                    # NEW: CLI command handler
```

### Graph Data Model

#### Node Types
| Node Type | Description | Key Attributes |
|-----------|-------------|----------------|
| `Manifest` | A task manifest file | path, goal, taskType, version |
| `File` | A source code file | path, status (tracked/registered/undeclared) |
| `Artifact` | Code artifact (class/function/attribute) | name, type, signature |
| `Module` | Python module (derived from file path) | name, package |

#### Edge Types
| Edge Type | From → To | Description |
|-----------|-----------|-------------|
| `SUPERSEDES` | Manifest → Manifest | Obsoletes previous manifest |
| `CREATES` | Manifest → File | Declares file creation |
| `EDITS` | Manifest → File | Declares file modification |
| `READS` | Manifest → File | Declares file dependency |
| `DEFINES` | File → Artifact | File defines the artifact |
| `DECLARES` | Manifest → Artifact | Manifest declares expected artifact |
| `CONTAINS` | Artifact → Artifact | Class contains method/attribute |
| `INHERITS` | Artifact → Artifact | Class inheritance relationship |
| `BELONGS_TO` | File → Module | File is part of module |

### Query Capabilities

The query engine supports natural language-style queries:
- `"What defines artifact X?"` → Find file and manifest that define X
- `"What depends on artifact Y?"` → Find files/manifests that use Y
- `"Show all artifacts in module Z"` → List artifacts in module
- `"What would break if I change X?"` → Impact analysis
- `"Find circular dependencies"` → Cycle detection
- `"Show supersedes chain for manifest M"` → Manifest lineage

### CLI Interface

```bash
# Build and query the graph
uv run maid graph "What depends on ManifestValidator?"
uv run maid graph "Show artifacts in maid_runner.validators"
uv run maid graph "What would break if I change validate_schema?"

# Export the graph
uv run maid graph --export graph.json
uv run maid graph --export graph.dot --format dot
uv run maid graph --export graph.graphml --format graphml

# Analysis commands
uv run maid graph --find-cycles
uv run maid graph --show-stats
```

## Implementation Tasks (MAID Manifests)

### Phase 1: Core Data Model

#### Task 101: Graph Node Types
**Goal:** Define graph node data structures
**File:** `maid_runner/graph/model.py`
**Artifacts:**
- `class NodeType(Enum)` - Enumeration of node types
- `class Node` - Base node dataclass with id, type, attributes
- `class ManifestNode(Node)` - Manifest-specific node
- `class FileNode(Node)` - File-specific node
- `class ArtifactNode(Node)` - Artifact-specific node
- `class ModuleNode(Node)` - Module-specific node

#### Task 102: Graph Edge Types
**Goal:** Define graph edge data structures
**File:** `maid_runner/graph/model.py`
**Artifacts:**
- `class EdgeType(Enum)` - Enumeration of edge types
- `class Edge` - Edge dataclass with source, target, type, attributes

#### Task 103: Knowledge Graph Container
**Goal:** Define the main graph container with node/edge storage
**File:** `maid_runner/graph/model.py`
**Artifacts:**
- `class KnowledgeGraph` - Main graph container
  - `add_node(node: Node)` - Add node to graph
  - `add_edge(edge: Edge)` - Add edge to graph
  - `get_node(node_id: str)` - Retrieve node by ID
  - `get_edges(node_id: str, edge_type: EdgeType)` - Get edges for node
  - `nodes` property - All nodes
  - `edges` property - All edges

### Phase 2: Graph Builder

#### Task 104: Manifest Loader
**Goal:** Load and parse manifests for graph building
**File:** `maid_runner/graph/builder.py`
**Artifacts:**
- `function load_manifests(manifest_dir: Path) -> List[Dict]` - Load all active manifests
- Uses existing `discover_active_manifests()` from snapshot_system

#### Task 105: Node Factory
**Goal:** Create graph nodes from manifest data
**File:** `maid_runner/graph/builder.py`
**Artifacts:**
- `function create_manifest_node(manifest_data: Dict, path: Path) -> ManifestNode`
- `function create_file_node(file_path: str) -> FileNode`
- `function create_artifact_node(artifact: Dict, file_path: str) -> ArtifactNode`
- `function create_module_node(file_path: str) -> ModuleNode`

#### Task 106: Edge Factory
**Goal:** Create graph edges from manifest relationships
**File:** `maid_runner/graph/builder.py`
**Artifacts:**
- `function create_supersedes_edges(manifest: Dict, manifest_node: ManifestNode) -> List[Edge]`
- `function create_file_edges(manifest: Dict, manifest_node: ManifestNode) -> List[Edge]`
- `function create_artifact_edges(artifacts: Dict, file_node: FileNode) -> List[Edge]`

#### Task 107: Knowledge Graph Builder Class
**Goal:** Main builder that orchestrates graph construction
**File:** `maid_runner/graph/builder.py`
**Artifacts:**
- `class KnowledgeGraphBuilder`
  - `__init__(manifest_dir: Path)`
  - `build() -> KnowledgeGraph` - Build complete graph
  - `_process_manifest(manifest_data: Dict, path: Path)` - Process single manifest
  - `_extract_artifacts(manifest_data: Dict)` - Extract artifact relationships

### Phase 3: Query Engine

#### Task 108: Basic Graph Traversal
**Goal:** Implement core graph traversal algorithms
**File:** `maid_runner/graph/query.py`
**Artifacts:**
- `function find_nodes_by_type(graph: KnowledgeGraph, node_type: NodeType) -> List[Node]`
- `function find_node_by_name(graph: KnowledgeGraph, name: str) -> Optional[Node]`
- `function get_neighbors(graph: KnowledgeGraph, node: Node, edge_type: EdgeType) -> List[Node]`

#### Task 109: Dependency Analysis
**Goal:** Implement dependency tracking queries
**File:** `maid_runner/graph/query.py`
**Artifacts:**
- `function find_dependents(graph: KnowledgeGraph, artifact_name: str) -> List[Node]`
- `function find_dependencies(graph: KnowledgeGraph, artifact_name: str) -> List[Node]`
- `function get_dependency_tree(graph: KnowledgeGraph, node: Node, depth: int) -> Dict`

#### Task 110: Cycle Detection
**Goal:** Implement circular dependency detection
**File:** `maid_runner/graph/query.py`
**Artifacts:**
- `function find_cycles(graph: KnowledgeGraph) -> List[List[Node]]`
- `function is_acyclic(graph: KnowledgeGraph) -> bool`

#### Task 111: Impact Analysis
**Goal:** Implement change impact analysis
**File:** `maid_runner/graph/query.py`
**Artifacts:**
- `function analyze_impact(graph: KnowledgeGraph, artifact_name: str) -> Dict`
- `function get_affected_files(graph: KnowledgeGraph, artifact_name: str) -> List[str]`
- `function get_affected_manifests(graph: KnowledgeGraph, artifact_name: str) -> List[str]`

#### Task 112: Query Parser
**Goal:** Parse natural language-style queries
**File:** `maid_runner/graph/query.py`
**Artifacts:**
- `class QueryParser`
  - `parse(query: str) -> QueryIntent`
  - `_extract_target(query: str) -> str`
  - `_determine_query_type(query: str) -> QueryType`
- `class QueryIntent` - Parsed query representation
- `class QueryType(Enum)` - Query type enumeration

#### Task 113: Query Executor
**Goal:** Execute parsed queries against the graph
**File:** `maid_runner/graph/query.py`
**Artifacts:**
- `class QueryExecutor`
  - `__init__(graph: KnowledgeGraph)`
  - `execute(intent: QueryIntent) -> QueryResult`
- `class QueryResult` - Query result container

### Phase 4: Export Formats

#### Task 114: JSON Exporter
**Goal:** Export graph to JSON format
**File:** `maid_runner/graph/exporters.py`
**Artifacts:**
- `function export_json(graph: KnowledgeGraph, output_path: Path) -> None`
- `function graph_to_dict(graph: KnowledgeGraph) -> Dict`

#### Task 115: DOT Exporter (Graphviz)
**Goal:** Export graph to DOT format for visualization
**File:** `maid_runner/graph/exporters.py`
**Artifacts:**
- `function export_dot(graph: KnowledgeGraph, output_path: Path) -> None`
- `function graph_to_dot(graph: KnowledgeGraph) -> str`

#### Task 116: GraphML Exporter
**Goal:** Export graph to GraphML format
**File:** `maid_runner/graph/exporters.py`
**Artifacts:**
- `function export_graphml(graph: KnowledgeGraph, output_path: Path) -> None`
- `function graph_to_graphml(graph: KnowledgeGraph) -> str`

### Phase 5: CLI Integration

#### Task 117: Graph CLI Command Handler
**Goal:** Implement CLI command for graph operations
**File:** `maid_runner/cli/graph.py`
**Artifacts:**
- `function run_graph_command(args: argparse.Namespace) -> int`
- `function handle_query(query: str, manifest_dir: Path) -> None`
- `function handle_export(format: str, output: Path, manifest_dir: Path) -> None`
- `function handle_analysis(analysis_type: str, manifest_dir: Path) -> None`

#### Task 118: CLI Main Integration
**Goal:** Add graph subcommand to main CLI
**File:** `maid_runner/cli/main.py`
**Artifacts:**
- Add `graph` subparser with appropriate arguments
- Route to `run_graph_command`

### Phase 6: Public API & Package Init

#### Task 119: Graph Package Init
**Goal:** Export public API from graph package
**File:** `maid_runner/graph/__init__.py`
**Artifacts:**
- Export: `KnowledgeGraph`, `KnowledgeGraphBuilder`, `Node`, `Edge`, `NodeType`, `EdgeType`
- Export: `QueryParser`, `QueryExecutor`, `QueryResult`
- Export: `export_json`, `export_dot`, `export_graphml`

#### Task 120: Main Package Integration
**Goal:** Add graph exports to main package
**File:** `maid_runner/__init__.py`
**Artifacts:**
- Add graph-related exports to public API

## Performance Requirements

| Metric | Target |
|--------|--------|
| Query response time | < 1 second |
| Manifest capacity | 10,000+ manifests |
| Memory usage | < 1GB for large codebases |

### Performance Strategy
- In-memory graph storage with lazy loading
- Indexed lookups by node ID and name
- Cached traversal results for repeated queries
- Efficient edge storage using adjacency lists

## Test Strategy

Each task includes behavioral tests following MAID methodology:

### Test Coverage Target: >85%

### Test Categories
1. **Unit Tests:** Each class/function has focused tests
2. **Integration Tests:** Builder + Query + Export workflows
3. **Performance Tests:** Large graph handling (1000+ manifests)
4. **Edge Cases:** Empty graphs, malformed manifests, cycles

### Example Test Structure
```
tests/
├── test_task_101_graph_nodes.py
├── test_task_102_graph_edges.py
├── test_task_103_knowledge_graph.py
├── test_task_104_manifest_loader.py
├── test_task_105_node_factory.py
├── test_task_106_edge_factory.py
├── test_task_107_graph_builder.py
├── test_task_108_basic_traversal.py
├── test_task_109_dependency_analysis.py
├── test_task_110_cycle_detection.py
├── test_task_111_impact_analysis.py
├── test_task_112_query_parser.py
├── test_task_113_query_executor.py
├── test_task_114_json_exporter.py
├── test_task_115_dot_exporter.py
├── test_task_116_graphml_exporter.py
├── test_task_117_graph_cli.py
├── test_task_118_cli_integration.py
├── test_task_119_graph_package.py
├── test_task_120_main_package.py
```

## Implementation Order

```
Phase 1: Core Data Model (Tasks 101-103)
    ↓
Phase 2: Graph Builder (Tasks 104-107)
    ↓
Phase 3: Query Engine (Tasks 108-113)
    ↓
Phase 4: Export Formats (Tasks 114-116)
    ↓
Phase 5: CLI Integration (Tasks 117-118)
    ↓
Phase 6: Public API (Tasks 119-120)
```

## Risk Mitigation

| Risk | Mitigation |
|------|------------|
| Performance with large graphs | Use efficient data structures, lazy loading |
| Query parsing complexity | Start with structured queries, add NL later |
| Memory pressure | Implement pagination, streaming exports |
| Circular dependency detection | Use proven DFS-based algorithms |

## Acceptance Criteria Checklist

- [ ] Graph built from all active manifests
- [ ] All relationship types (supersedes, creates, edits, reads, defines, contains, inherits) tracked
- [ ] Query API implemented with natural language support
- [ ] CLI command `maid graph` working
- [ ] Export formats (JSON, DOT, GraphML) supported
- [ ] Performance < 1 second for complex queries
- [ ] Integration with system snapshot (uses snapshot_system.py discovery)
- [ ] Test coverage > 85%
- [ ] Documentation complete

## Next Steps

1. Review and approve this plan
2. Create feature branch from `dev`
3. Begin Phase 1: Task 101 (Graph Node Types)
4. Follow MAID workflow for each task:
   - Create manifest
   - Write behavioral tests
   - Validate behavioral mode
   - Implement code
   - Validate implementation mode
   - Run tests
   - Refactor if needed
