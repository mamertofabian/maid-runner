"""Behavioral tests for Task 108: Basic Graph Traversal.

Tests for the graph query functions:
- find_nodes_by_type: Find all nodes matching a specific type
- find_node_by_name: Search for a node by name
- get_neighbors: Get connected nodes, optionally filtered by edge type
"""

import pytest

from maid_runner.graph.model import (
    ArtifactNode,
    Edge,
    EdgeType,
    FileNode,
    KnowledgeGraph,
    ManifestNode,
    ModuleNode,
    Node,
    NodeType,
)
from maid_runner.graph.query import (
    find_node_by_name,
    find_nodes_by_type,
    get_neighbors,
)


# =============================================================================
# Fixtures
# =============================================================================


@pytest.fixture
def empty_graph() -> KnowledgeGraph:
    """Create an empty knowledge graph."""
    return KnowledgeGraph()


@pytest.fixture
def graph_with_manifest_nodes() -> KnowledgeGraph:
    """Create a graph with multiple manifest nodes."""
    graph = KnowledgeGraph()

    manifest1 = ManifestNode(
        id="manifest-001",
        path="manifests/task-001.manifest.json",
        goal="Create initial module",
        task_type="create",
        version="1.0",
    )
    manifest2 = ManifestNode(
        id="manifest-002",
        path="manifests/task-002.manifest.json",
        goal="Edit existing module",
        task_type="edit",
        version="1.0",
    )
    manifest3 = ManifestNode(
        id="manifest-003",
        path="manifests/task-003.manifest.json",
        goal="Refactor module",
        task_type="refactor",
        version="1.0",
    )

    graph.add_node(manifest1)
    graph.add_node(manifest2)
    graph.add_node(manifest3)

    return graph


@pytest.fixture
def graph_with_file_nodes() -> KnowledgeGraph:
    """Create a graph with multiple file nodes."""
    graph = KnowledgeGraph()

    file1 = FileNode(
        id="file-001",
        path="src/module.py",
        status="tracked",
    )
    file2 = FileNode(
        id="file-002",
        path="src/utils.py",
        status="tracked",
    )
    file3 = FileNode(
        id="file-003",
        path="tests/test_module.py",
        status="registered",
    )

    graph.add_node(file1)
    graph.add_node(file2)
    graph.add_node(file3)

    return graph


@pytest.fixture
def graph_with_artifact_nodes() -> KnowledgeGraph:
    """Create a graph with multiple artifact nodes."""
    graph = KnowledgeGraph()

    artifact1 = ArtifactNode(
        id="artifact-001",
        name="my_function",
        artifact_type="function",
        signature="def my_function(x: int) -> str",
    )
    artifact2 = ArtifactNode(
        id="artifact-002",
        name="MyClass",
        artifact_type="class",
    )
    artifact3 = ArtifactNode(
        id="artifact-003",
        name="my_method",
        artifact_type="function",
        parent_class="MyClass",
        signature="def my_method(self) -> None",
    )

    graph.add_node(artifact1)
    graph.add_node(artifact2)
    graph.add_node(artifact3)

    return graph


@pytest.fixture
def graph_with_module_nodes() -> KnowledgeGraph:
    """Create a graph with multiple module nodes."""
    graph = KnowledgeGraph()

    module1 = ModuleNode(
        id="module-001",
        name="main_module",
        package="mypackage",
    )
    module2 = ModuleNode(
        id="module-002",
        name="utils",
        package="mypackage.helpers",
    )

    graph.add_node(module1)
    graph.add_node(module2)

    return graph


@pytest.fixture
def mixed_graph() -> KnowledgeGraph:
    """Create a graph with all node types."""
    graph = KnowledgeGraph()

    # Add manifest nodes
    manifest1 = ManifestNode(
        id="manifest-001",
        path="manifests/task-001.manifest.json",
        goal="Create module",
        task_type="create",
        version="1.0",
    )
    manifest2 = ManifestNode(
        id="manifest-002",
        path="manifests/task-002.manifest.json",
        goal="Edit module",
        task_type="edit",
        version="1.0",
    )

    # Add file nodes
    file1 = FileNode(
        id="file-001",
        path="src/module.py",
        status="tracked",
    )
    file2 = FileNode(
        id="file-002",
        path="src/utils.py",
        status="tracked",
    )

    # Add artifact nodes
    artifact1 = ArtifactNode(
        id="artifact-001",
        name="my_function",
        artifact_type="function",
    )

    # Add module nodes
    module1 = ModuleNode(
        id="module-001",
        name="main_module",
        package="mypackage",
    )

    graph.add_node(manifest1)
    graph.add_node(manifest2)
    graph.add_node(file1)
    graph.add_node(file2)
    graph.add_node(artifact1)
    graph.add_node(module1)

    return graph


@pytest.fixture
def connected_graph() -> KnowledgeGraph:
    """Create a graph with nodes connected by edges."""
    graph = KnowledgeGraph()

    # Create nodes
    manifest = ManifestNode(
        id="manifest-001",
        path="manifests/task-001.manifest.json",
        goal="Create module",
        task_type="create",
        version="1.0",
    )
    file1 = FileNode(
        id="file-001",
        path="src/module.py",
        status="tracked",
    )
    file2 = FileNode(
        id="file-002",
        path="src/utils.py",
        status="tracked",
    )
    artifact1 = ArtifactNode(
        id="artifact-001",
        name="my_function",
        artifact_type="function",
    )
    artifact2 = ArtifactNode(
        id="artifact-002",
        name="helper_function",
        artifact_type="function",
    )

    graph.add_node(manifest)
    graph.add_node(file1)
    graph.add_node(file2)
    graph.add_node(artifact1)
    graph.add_node(artifact2)

    # Create edges
    # manifest CREATES file1
    edge1 = Edge(
        id="edge-001",
        edge_type=EdgeType.CREATES,
        source_id="manifest-001",
        target_id="file-001",
    )
    # file1 DEFINES artifact1
    edge2 = Edge(
        id="edge-002",
        edge_type=EdgeType.DEFINES,
        source_id="file-001",
        target_id="artifact-001",
    )
    # file1 DEFINES artifact2
    edge3 = Edge(
        id="edge-003",
        edge_type=EdgeType.DEFINES,
        source_id="file-001",
        target_id="artifact-002",
    )
    # manifest READS file2
    edge4 = Edge(
        id="edge-004",
        edge_type=EdgeType.READS,
        source_id="manifest-001",
        target_id="file-002",
    )

    graph.add_edge(edge1)
    graph.add_edge(edge2)
    graph.add_edge(edge3)
    graph.add_edge(edge4)

    return graph


@pytest.fixture
def graph_with_supersedes() -> KnowledgeGraph:
    """Create a graph with manifests that supersede each other."""
    graph = KnowledgeGraph()

    manifest1 = ManifestNode(
        id="manifest-001",
        path="manifests/task-001.manifest.json",
        goal="Initial feature",
        task_type="create",
        version="1.0",
    )
    manifest2 = ManifestNode(
        id="manifest-002",
        path="manifests/task-002.manifest.json",
        goal="Updated feature",
        task_type="edit",
        version="1.0",
    )
    manifest3 = ManifestNode(
        id="manifest-003",
        path="manifests/task-003.manifest.json",
        goal="Refactored feature",
        task_type="refactor",
        version="1.0",
    )

    graph.add_node(manifest1)
    graph.add_node(manifest2)
    graph.add_node(manifest3)

    # manifest2 SUPERSEDES manifest1
    edge1 = Edge(
        id="edge-001",
        edge_type=EdgeType.SUPERSEDES,
        source_id="manifest-002",
        target_id="manifest-001",
    )
    # manifest3 SUPERSEDES manifest2
    edge2 = Edge(
        id="edge-002",
        edge_type=EdgeType.SUPERSEDES,
        source_id="manifest-003",
        target_id="manifest-002",
    )

    graph.add_edge(edge1)
    graph.add_edge(edge2)

    return graph


# =============================================================================
# Tests for find_nodes_by_type
# =============================================================================


class TestFindNodesByType:
    """Tests for the find_nodes_by_type function."""

    def test_returns_list_of_nodes(self, mixed_graph: KnowledgeGraph) -> None:
        """Test that find_nodes_by_type returns a list."""
        result = find_nodes_by_type(mixed_graph, NodeType.MANIFEST)

        assert isinstance(result, list)

    def test_finds_all_manifest_type_nodes(
        self, graph_with_manifest_nodes: KnowledgeGraph
    ) -> None:
        """Test finding all MANIFEST type nodes."""
        result = find_nodes_by_type(graph_with_manifest_nodes, NodeType.MANIFEST)

        assert len(result) == 3
        assert all(node.node_type == NodeType.MANIFEST for node in result)

    def test_finds_all_file_type_nodes(
        self, graph_with_file_nodes: KnowledgeGraph
    ) -> None:
        """Test finding all FILE type nodes."""
        result = find_nodes_by_type(graph_with_file_nodes, NodeType.FILE)

        assert len(result) == 3
        assert all(node.node_type == NodeType.FILE for node in result)

    def test_finds_all_artifact_type_nodes(
        self, graph_with_artifact_nodes: KnowledgeGraph
    ) -> None:
        """Test finding all ARTIFACT type nodes."""
        result = find_nodes_by_type(graph_with_artifact_nodes, NodeType.ARTIFACT)

        assert len(result) == 3
        assert all(node.node_type == NodeType.ARTIFACT for node in result)

    def test_finds_all_module_type_nodes(
        self, graph_with_module_nodes: KnowledgeGraph
    ) -> None:
        """Test finding all MODULE type nodes."""
        result = find_nodes_by_type(graph_with_module_nodes, NodeType.MODULE)

        assert len(result) == 2
        assert all(node.node_type == NodeType.MODULE for node in result)

    def test_returns_empty_list_for_type_with_no_matches(
        self, graph_with_manifest_nodes: KnowledgeGraph
    ) -> None:
        """Test returns empty list when no nodes match the type."""
        result = find_nodes_by_type(graph_with_manifest_nodes, NodeType.ARTIFACT)

        assert result == []

    def test_works_with_empty_graph(self, empty_graph: KnowledgeGraph) -> None:
        """Test that find_nodes_by_type works with an empty graph."""
        result = find_nodes_by_type(empty_graph, NodeType.MANIFEST)

        assert result == []

    def test_filters_correctly_in_mixed_graph(
        self, mixed_graph: KnowledgeGraph
    ) -> None:
        """Test correct filtering when graph has multiple node types."""
        manifest_nodes = find_nodes_by_type(mixed_graph, NodeType.MANIFEST)
        file_nodes = find_nodes_by_type(mixed_graph, NodeType.FILE)
        artifact_nodes = find_nodes_by_type(mixed_graph, NodeType.ARTIFACT)
        module_nodes = find_nodes_by_type(mixed_graph, NodeType.MODULE)

        assert len(manifest_nodes) == 2
        assert len(file_nodes) == 2
        assert len(artifact_nodes) == 1
        assert len(module_nodes) == 1


# =============================================================================
# Tests for find_node_by_name
# =============================================================================


class TestFindNodeByName:
    """Tests for the find_node_by_name function."""

    def test_returns_node_when_found(self, mixed_graph: KnowledgeGraph) -> None:
        """Test that find_node_by_name returns a Node when found."""
        result = find_node_by_name(mixed_graph, "manifest-001")

        assert result is not None
        assert isinstance(result, Node)

    def test_returns_none_when_not_found(self, mixed_graph: KnowledgeGraph) -> None:
        """Test returns None when no node matches."""
        result = find_node_by_name(mixed_graph, "nonexistent-node")

        assert result is None

    def test_finds_node_by_id(self, mixed_graph: KnowledgeGraph) -> None:
        """Test finding a node by its id."""
        result = find_node_by_name(mixed_graph, "file-001")

        assert result is not None
        assert result.id == "file-001"

    def test_finds_manifest_node_by_path(
        self, graph_with_manifest_nodes: KnowledgeGraph
    ) -> None:
        """Test finding ManifestNode by path."""
        result = find_node_by_name(
            graph_with_manifest_nodes, "manifests/task-002.manifest.json"
        )

        assert result is not None
        assert isinstance(result, ManifestNode)
        assert result.path == "manifests/task-002.manifest.json"

    def test_finds_file_node_by_path(
        self, graph_with_file_nodes: KnowledgeGraph
    ) -> None:
        """Test finding FileNode by path."""
        result = find_node_by_name(graph_with_file_nodes, "src/module.py")

        assert result is not None
        assert isinstance(result, FileNode)
        assert result.path == "src/module.py"

    def test_finds_artifact_node_by_name(
        self, graph_with_artifact_nodes: KnowledgeGraph
    ) -> None:
        """Test finding ArtifactNode by name."""
        result = find_node_by_name(graph_with_artifact_nodes, "my_function")

        assert result is not None
        assert isinstance(result, ArtifactNode)
        assert result.name == "my_function"

    def test_finds_module_node_by_name(
        self, graph_with_module_nodes: KnowledgeGraph
    ) -> None:
        """Test finding ModuleNode by name."""
        result = find_node_by_name(graph_with_module_nodes, "main_module")

        assert result is not None
        assert isinstance(result, ModuleNode)
        assert result.name == "main_module"

    def test_returns_none_for_empty_graph(self, empty_graph: KnowledgeGraph) -> None:
        """Test that find_node_by_name returns None for empty graph."""
        result = find_node_by_name(empty_graph, "any-name")

        assert result is None


# =============================================================================
# Tests for get_neighbors
# =============================================================================


class TestGetNeighbors:
    """Tests for the get_neighbors function."""

    def test_returns_list_of_connected_nodes(
        self, connected_graph: KnowledgeGraph
    ) -> None:
        """Test that get_neighbors returns a list of nodes."""
        file_node = connected_graph.get_node("file-001")
        assert file_node is not None

        result = get_neighbors(connected_graph, file_node)

        assert isinstance(result, list)
        assert len(result) > 0

    def test_returns_empty_list_for_node_with_no_edges(
        self, mixed_graph: KnowledgeGraph
    ) -> None:
        """Test returns empty list for isolated node."""
        node = mixed_graph.get_node("artifact-001")
        assert node is not None

        result = get_neighbors(mixed_graph, node)

        assert result == []

    def test_includes_nodes_from_outgoing_edges(
        self, connected_graph: KnowledgeGraph
    ) -> None:
        """Test that neighbors include nodes from outgoing edges."""
        manifest = connected_graph.get_node("manifest-001")
        assert manifest is not None

        result = get_neighbors(connected_graph, manifest)

        # manifest-001 has outgoing edges to file-001 (CREATES) and file-002 (READS)
        neighbor_ids = [n.id for n in result]
        assert "file-001" in neighbor_ids
        assert "file-002" in neighbor_ids

    def test_includes_nodes_from_incoming_edges(
        self, connected_graph: KnowledgeGraph
    ) -> None:
        """Test that neighbors include nodes from incoming edges."""
        file_node = connected_graph.get_node("file-001")
        assert file_node is not None

        result = get_neighbors(connected_graph, file_node)

        # file-001 has incoming edge from manifest-001 (CREATES)
        # and outgoing edges to artifact-001 and artifact-002 (DEFINES)
        neighbor_ids = [n.id for n in result]
        assert "manifest-001" in neighbor_ids

    def test_filters_by_edge_type_when_specified(
        self, connected_graph: KnowledgeGraph
    ) -> None:
        """Test filtering neighbors by edge type."""
        manifest = connected_graph.get_node("manifest-001")
        assert manifest is not None

        # Get only CREATES neighbors
        result = get_neighbors(connected_graph, manifest, edge_type=EdgeType.CREATES)

        neighbor_ids = [n.id for n in result]
        assert "file-001" in neighbor_ids
        assert "file-002" not in neighbor_ids  # file-002 is via READS edge

    def test_returns_all_neighbors_when_edge_type_is_none(
        self, connected_graph: KnowledgeGraph
    ) -> None:
        """Test returns all neighbors when edge_type is None."""
        manifest = connected_graph.get_node("manifest-001")
        assert manifest is not None

        result = get_neighbors(connected_graph, manifest, edge_type=None)

        neighbor_ids = [n.id for n in result]
        assert "file-001" in neighbor_ids
        assert "file-002" in neighbor_ids

    def test_works_with_supersedes_edge_type(
        self, graph_with_supersedes: KnowledgeGraph
    ) -> None:
        """Test get_neighbors works with SUPERSEDES edge type."""
        manifest2 = graph_with_supersedes.get_node("manifest-002")
        assert manifest2 is not None

        # manifest-002 supersedes manifest-001, and is superseded by manifest-003
        result = get_neighbors(
            graph_with_supersedes, manifest2, edge_type=EdgeType.SUPERSEDES
        )

        neighbor_ids = [n.id for n in result]
        # Should include both the one it supersedes and the one that supersedes it
        assert "manifest-001" in neighbor_ids or "manifest-003" in neighbor_ids

    def test_works_with_defines_edge_type(
        self, connected_graph: KnowledgeGraph
    ) -> None:
        """Test get_neighbors works with DEFINES edge type."""
        file_node = connected_graph.get_node("file-001")
        assert file_node is not None

        result = get_neighbors(connected_graph, file_node, edge_type=EdgeType.DEFINES)

        neighbor_ids = [n.id for n in result]
        assert "artifact-001" in neighbor_ids
        assert "artifact-002" in neighbor_ids

    def test_works_with_creates_edge_type(
        self, connected_graph: KnowledgeGraph
    ) -> None:
        """Test get_neighbors works with CREATES edge type."""
        manifest = connected_graph.get_node("manifest-001")
        assert manifest is not None

        result = get_neighbors(connected_graph, manifest, edge_type=EdgeType.CREATES)

        neighbor_ids = [n.id for n in result]
        assert "file-001" in neighbor_ids

    def test_works_with_reads_edge_type(self, connected_graph: KnowledgeGraph) -> None:
        """Test get_neighbors works with READS edge type."""
        manifest = connected_graph.get_node("manifest-001")
        assert manifest is not None

        result = get_neighbors(connected_graph, manifest, edge_type=EdgeType.READS)

        neighbor_ids = [n.id for n in result]
        assert "file-002" in neighbor_ids

    def test_returns_empty_list_for_unmatched_edge_type(
        self, connected_graph: KnowledgeGraph
    ) -> None:
        """Test returns empty list when no edges match the specified type."""
        manifest = connected_graph.get_node("manifest-001")
        assert manifest is not None

        # manifest-001 has no INHERITS edges
        result = get_neighbors(connected_graph, manifest, edge_type=EdgeType.INHERITS)

        assert result == []

    def test_works_with_empty_graph(self, empty_graph: KnowledgeGraph) -> None:
        """Test get_neighbors with a standalone node not in graph."""
        # Create a node that's not connected to anything
        standalone_node = Node(
            id="standalone",
            node_type=NodeType.FILE,
        )
        empty_graph.add_node(standalone_node)

        result = get_neighbors(empty_graph, standalone_node)

        assert result == []
