"""Behavioral tests for Task 103: KnowledgeGraph container class.

Tests the KnowledgeGraph class which provides storage and retrieval
methods for nodes and edges in the knowledge graph.
"""

from maid_runner.graph.model import (
    KnowledgeGraph,
    Node,
    NodeType,
    ManifestNode,
    FileNode,
    ArtifactNode,
    ModuleNode,
    Edge,
    EdgeType,
)


class TestKnowledgeGraphInit:
    """Tests for KnowledgeGraph.__init__."""

    def test_init_creates_empty_graph(self) -> None:
        """KnowledgeGraph initializes with no nodes or edges."""
        graph = KnowledgeGraph()

        assert graph.node_count == 0
        assert graph.edge_count == 0

    def test_init_nodes_property_returns_empty_list(self) -> None:
        """Empty graph returns empty list for nodes property."""
        graph = KnowledgeGraph()

        assert graph.nodes == []

    def test_init_edges_property_returns_empty_list(self) -> None:
        """Empty graph returns empty list for edges property."""
        graph = KnowledgeGraph()

        assert graph.edges == []


class TestKnowledgeGraphAddNode:
    """Tests for KnowledgeGraph.add_node."""

    def test_add_node_increases_node_count(self) -> None:
        """Adding a node increments the node count."""
        graph = KnowledgeGraph()
        node = Node(id="node1", node_type=NodeType.FILE)

        graph.add_node(node)

        assert graph.node_count == 1

    def test_add_node_makes_node_retrievable(self) -> None:
        """Added node can be retrieved from nodes property."""
        graph = KnowledgeGraph()
        node = Node(id="node1", node_type=NodeType.FILE)

        graph.add_node(node)

        assert node in graph.nodes

    def test_add_multiple_nodes(self) -> None:
        """Multiple nodes can be added to the graph."""
        graph = KnowledgeGraph()
        node1 = Node(id="node1", node_type=NodeType.FILE)
        node2 = Node(id="node2", node_type=NodeType.MANIFEST)
        node3 = Node(id="node3", node_type=NodeType.ARTIFACT)

        graph.add_node(node1)
        graph.add_node(node2)
        graph.add_node(node3)

        assert graph.node_count == 3
        assert node1 in graph.nodes
        assert node2 in graph.nodes
        assert node3 in graph.nodes

    def test_add_manifest_node(self) -> None:
        """ManifestNode can be added to the graph."""
        graph = KnowledgeGraph()
        manifest = ManifestNode(
            id="manifest1",
            path="manifests/task-001.manifest.json",
            goal="Test goal",
            task_type="create",
            version="1.0",
        )

        graph.add_node(manifest)

        assert graph.node_count == 1
        assert manifest in graph.nodes

    def test_add_file_node(self) -> None:
        """FileNode can be added to the graph."""
        graph = KnowledgeGraph()
        file_node = FileNode(
            id="file1",
            path="src/module.py",
            status="tracked",
        )

        graph.add_node(file_node)

        assert graph.node_count == 1
        assert file_node in graph.nodes

    def test_add_artifact_node(self) -> None:
        """ArtifactNode can be added to the graph."""
        graph = KnowledgeGraph()
        artifact = ArtifactNode(
            id="artifact1",
            name="my_function",
            artifact_type="function",
            signature="def my_function(x: int) -> str",
        )

        graph.add_node(artifact)

        assert graph.node_count == 1
        assert artifact in graph.nodes

    def test_add_module_node(self) -> None:
        """ModuleNode can be added to the graph."""
        graph = KnowledgeGraph()
        module = ModuleNode(
            id="module1",
            name="utils",
            package="maid_runner",
        )

        graph.add_node(module)

        assert graph.node_count == 1
        assert module in graph.nodes


class TestKnowledgeGraphAddEdge:
    """Tests for KnowledgeGraph.add_edge."""

    def test_add_edge_increases_edge_count(self) -> None:
        """Adding an edge increments the edge count."""
        graph = KnowledgeGraph()
        edge = Edge(
            id="edge1",
            edge_type=EdgeType.CREATES,
            source_id="manifest1",
            target_id="file1",
        )

        graph.add_edge(edge)

        assert graph.edge_count == 1

    def test_add_edge_makes_edge_retrievable(self) -> None:
        """Added edge can be retrieved from edges property."""
        graph = KnowledgeGraph()
        edge = Edge(
            id="edge1",
            edge_type=EdgeType.CREATES,
            source_id="manifest1",
            target_id="file1",
        )

        graph.add_edge(edge)

        assert edge in graph.edges

    def test_add_multiple_edges(self) -> None:
        """Multiple edges can be added to the graph."""
        graph = KnowledgeGraph()
        edge1 = Edge(
            id="edge1",
            edge_type=EdgeType.CREATES,
            source_id="manifest1",
            target_id="file1",
        )
        edge2 = Edge(
            id="edge2",
            edge_type=EdgeType.EDITS,
            source_id="manifest2",
            target_id="file1",
        )
        edge3 = Edge(
            id="edge3",
            edge_type=EdgeType.SUPERSEDES,
            source_id="manifest2",
            target_id="manifest1",
        )

        graph.add_edge(edge1)
        graph.add_edge(edge2)
        graph.add_edge(edge3)

        assert graph.edge_count == 3
        assert edge1 in graph.edges
        assert edge2 in graph.edges
        assert edge3 in graph.edges

    def test_add_edges_with_various_edge_types(self) -> None:
        """Edges of different EdgeType values can be added."""
        graph = KnowledgeGraph()
        edge_types_to_test = [
            EdgeType.SUPERSEDES,
            EdgeType.CREATES,
            EdgeType.EDITS,
            EdgeType.READS,
            EdgeType.DEFINES,
            EdgeType.DECLARES,
            EdgeType.CONTAINS,
            EdgeType.INHERITS,
            EdgeType.BELONGS_TO,
        ]

        for i, edge_type in enumerate(edge_types_to_test):
            edge = Edge(
                id=f"edge{i}",
                edge_type=edge_type,
                source_id="source",
                target_id="target",
            )
            graph.add_edge(edge)

        assert graph.edge_count == len(edge_types_to_test)


class TestKnowledgeGraphGetNode:
    """Tests for KnowledgeGraph.get_node."""

    def test_get_node_returns_node_by_id(self) -> None:
        """Retrieves a node by its ID."""
        graph = KnowledgeGraph()
        node = Node(id="node1", node_type=NodeType.FILE)
        graph.add_node(node)

        result = graph.get_node("node1")

        assert result is node

    def test_get_node_returns_none_for_missing_id(self) -> None:
        """Returns None when node ID does not exist."""
        graph = KnowledgeGraph()
        node = Node(id="node1", node_type=NodeType.FILE)
        graph.add_node(node)

        result = graph.get_node("nonexistent")

        assert result is None

    def test_get_node_from_empty_graph_returns_none(self) -> None:
        """Returns None when getting from an empty graph."""
        graph = KnowledgeGraph()

        result = graph.get_node("any_id")

        assert result is None

    def test_get_node_retrieves_correct_node_among_many(self) -> None:
        """Retrieves the correct node when multiple exist."""
        graph = KnowledgeGraph()
        node1 = Node(id="node1", node_type=NodeType.FILE)
        node2 = ManifestNode(
            id="node2",
            path="path",
            goal="goal",
            task_type="create",
            version="1.0",
        )
        node3 = FileNode(id="node3", path="file.py", status="tracked")
        graph.add_node(node1)
        graph.add_node(node2)
        graph.add_node(node3)

        result = graph.get_node("node2")

        assert result is node2

    def test_get_node_returns_manifest_node_type(self) -> None:
        """Retrieves ManifestNode with correct type."""
        graph = KnowledgeGraph()
        manifest = ManifestNode(
            id="manifest1",
            path="manifest.json",
            goal="Test",
            task_type="edit",
            version="1.0",
        )
        graph.add_node(manifest)

        result = graph.get_node("manifest1")

        assert isinstance(result, ManifestNode)
        assert result.path == "manifest.json"


class TestKnowledgeGraphGetEdges:
    """Tests for KnowledgeGraph.get_edges."""

    def test_get_edges_returns_edges_for_source_node(self) -> None:
        """Returns edges where the node is the source."""
        graph = KnowledgeGraph()
        edge1 = Edge(
            id="edge1",
            edge_type=EdgeType.CREATES,
            source_id="manifest1",
            target_id="file1",
        )
        edge2 = Edge(
            id="edge2",
            edge_type=EdgeType.EDITS,
            source_id="manifest1",
            target_id="file2",
        )
        graph.add_edge(edge1)
        graph.add_edge(edge2)

        result = graph.get_edges("manifest1", None)

        assert len(result) == 2
        assert edge1 in result
        assert edge2 in result

    def test_get_edges_returns_edges_for_target_node(self) -> None:
        """Returns edges where the node is the target."""
        graph = KnowledgeGraph()
        edge1 = Edge(
            id="edge1",
            edge_type=EdgeType.CREATES,
            source_id="manifest1",
            target_id="file1",
        )
        edge2 = Edge(
            id="edge2",
            edge_type=EdgeType.EDITS,
            source_id="manifest2",
            target_id="file1",
        )
        graph.add_edge(edge1)
        graph.add_edge(edge2)

        result = graph.get_edges("file1", None)

        assert len(result) == 2
        assert edge1 in result
        assert edge2 in result

    def test_get_edges_returns_empty_list_for_node_with_no_edges(self) -> None:
        """Returns empty list when node has no edges."""
        graph = KnowledgeGraph()
        edge = Edge(
            id="edge1",
            edge_type=EdgeType.CREATES,
            source_id="manifest1",
            target_id="file1",
        )
        graph.add_edge(edge)

        result = graph.get_edges("unconnected_node", None)

        assert result == []

    def test_get_edges_filters_by_edge_type(self) -> None:
        """Filters edges by edge_type when specified."""
        graph = KnowledgeGraph()
        creates_edge = Edge(
            id="edge1",
            edge_type=EdgeType.CREATES,
            source_id="manifest1",
            target_id="file1",
        )
        edits_edge = Edge(
            id="edge2",
            edge_type=EdgeType.EDITS,
            source_id="manifest1",
            target_id="file2",
        )
        supersedes_edge = Edge(
            id="edge3",
            edge_type=EdgeType.SUPERSEDES,
            source_id="manifest1",
            target_id="manifest0",
        )
        graph.add_edge(creates_edge)
        graph.add_edge(edits_edge)
        graph.add_edge(supersedes_edge)

        result = graph.get_edges("manifest1", EdgeType.CREATES)

        assert len(result) == 1
        assert creates_edge in result
        assert edits_edge not in result

    def test_get_edges_with_edge_type_filter_returns_empty_for_no_match(self) -> None:
        """Returns empty list when edge_type filter has no matches."""
        graph = KnowledgeGraph()
        edge = Edge(
            id="edge1",
            edge_type=EdgeType.CREATES,
            source_id="manifest1",
            target_id="file1",
        )
        graph.add_edge(edge)

        result = graph.get_edges("manifest1", EdgeType.INHERITS)

        assert result == []

    def test_get_edges_from_empty_graph(self) -> None:
        """Returns empty list when graph has no edges."""
        graph = KnowledgeGraph()

        result = graph.get_edges("any_node", None)

        assert result == []


class TestKnowledgeGraphNodesProperty:
    """Tests for KnowledgeGraph.nodes property."""

    def test_nodes_returns_all_added_nodes(self) -> None:
        """nodes property returns all nodes added to the graph."""
        graph = KnowledgeGraph()
        node1 = Node(id="n1", node_type=NodeType.FILE)
        node2 = Node(id="n2", node_type=NodeType.MANIFEST)
        graph.add_node(node1)
        graph.add_node(node2)

        nodes = graph.nodes

        assert len(nodes) == 2
        assert node1 in nodes
        assert node2 in nodes

    def test_nodes_returns_list_type(self) -> None:
        """nodes property returns a list."""
        graph = KnowledgeGraph()
        node = Node(id="n1", node_type=NodeType.FILE)
        graph.add_node(node)

        nodes = graph.nodes

        assert isinstance(nodes, list)


class TestKnowledgeGraphEdgesProperty:
    """Tests for KnowledgeGraph.edges property."""

    def test_edges_returns_all_added_edges(self) -> None:
        """edges property returns all edges added to the graph."""
        graph = KnowledgeGraph()
        edge1 = Edge(
            id="e1",
            edge_type=EdgeType.CREATES,
            source_id="s1",
            target_id="t1",
        )
        edge2 = Edge(
            id="e2",
            edge_type=EdgeType.EDITS,
            source_id="s2",
            target_id="t2",
        )
        graph.add_edge(edge1)
        graph.add_edge(edge2)

        edges = graph.edges

        assert len(edges) == 2
        assert edge1 in edges
        assert edge2 in edges

    def test_edges_returns_list_type(self) -> None:
        """edges property returns a list."""
        graph = KnowledgeGraph()
        edge = Edge(
            id="e1",
            edge_type=EdgeType.CREATES,
            source_id="s1",
            target_id="t1",
        )
        graph.add_edge(edge)

        edges = graph.edges

        assert isinstance(edges, list)


class TestKnowledgeGraphNodeCountProperty:
    """Tests for KnowledgeGraph.node_count property."""

    def test_node_count_zero_for_empty_graph(self) -> None:
        """node_count is 0 for newly created graph."""
        graph = KnowledgeGraph()

        assert graph.node_count == 0

    def test_node_count_increments_with_additions(self) -> None:
        """node_count increases as nodes are added."""
        graph = KnowledgeGraph()
        assert graph.node_count == 0

        graph.add_node(Node(id="n1", node_type=NodeType.FILE))
        assert graph.node_count == 1

        graph.add_node(Node(id="n2", node_type=NodeType.MANIFEST))
        assert graph.node_count == 2

    def test_node_count_returns_int(self) -> None:
        """node_count returns an integer."""
        graph = KnowledgeGraph()

        assert isinstance(graph.node_count, int)


class TestKnowledgeGraphEdgeCountProperty:
    """Tests for KnowledgeGraph.edge_count property."""

    def test_edge_count_zero_for_empty_graph(self) -> None:
        """edge_count is 0 for newly created graph."""
        graph = KnowledgeGraph()

        assert graph.edge_count == 0

    def test_edge_count_increments_with_additions(self) -> None:
        """edge_count increases as edges are added."""
        graph = KnowledgeGraph()
        assert graph.edge_count == 0

        graph.add_edge(
            Edge(id="e1", edge_type=EdgeType.CREATES, source_id="s1", target_id="t1")
        )
        assert graph.edge_count == 1

        graph.add_edge(
            Edge(id="e2", edge_type=EdgeType.EDITS, source_id="s2", target_id="t2")
        )
        assert graph.edge_count == 2

    def test_edge_count_returns_int(self) -> None:
        """edge_count returns an integer."""
        graph = KnowledgeGraph()

        assert isinstance(graph.edge_count, int)


class TestKnowledgeGraphIntegration:
    """Integration tests for KnowledgeGraph with various node and edge types."""

    def test_full_graph_workflow(self) -> None:
        """Tests a complete workflow with multiple node and edge types."""
        graph = KnowledgeGraph()

        # Add nodes of different types
        manifest = ManifestNode(
            id="manifest-001",
            path="manifests/task-001.manifest.json",
            goal="Create utility module",
            task_type="create",
            version="1.0",
        )
        file_node = FileNode(
            id="file-utils",
            path="src/utils.py",
            status="tracked",
        )
        artifact = ArtifactNode(
            id="artifact-helper",
            name="helper_function",
            artifact_type="function",
            signature="def helper_function(x: int) -> str",
        )
        module = ModuleNode(
            id="module-utils",
            name="utils",
            package="src",
        )

        graph.add_node(manifest)
        graph.add_node(file_node)
        graph.add_node(artifact)
        graph.add_node(module)

        # Add edges
        creates_edge = Edge(
            id="e1",
            edge_type=EdgeType.CREATES,
            source_id="manifest-001",
            target_id="file-utils",
        )
        defines_edge = Edge(
            id="e2",
            edge_type=EdgeType.DEFINES,
            source_id="file-utils",
            target_id="artifact-helper",
        )
        belongs_edge = Edge(
            id="e3",
            edge_type=EdgeType.BELONGS_TO,
            source_id="file-utils",
            target_id="module-utils",
        )

        graph.add_edge(creates_edge)
        graph.add_edge(defines_edge)
        graph.add_edge(belongs_edge)

        # Verify counts
        assert graph.node_count == 4
        assert graph.edge_count == 3

        # Verify node retrieval
        retrieved_manifest = graph.get_node("manifest-001")
        assert retrieved_manifest is manifest
        assert isinstance(retrieved_manifest, ManifestNode)

        # Verify edge retrieval
        manifest_edges = graph.get_edges("manifest-001", None)
        assert len(manifest_edges) == 1
        assert creates_edge in manifest_edges

        file_edges = graph.get_edges("file-utils", None)
        assert len(file_edges) == 3  # creates, defines, belongs_to

        # Verify filtered edge retrieval
        defines_edges = graph.get_edges("file-utils", EdgeType.DEFINES)
        assert len(defines_edges) == 1
        assert defines_edge in defines_edges

    def test_nodes_and_edges_independent(self) -> None:
        """Nodes and edges can be added independently."""
        graph = KnowledgeGraph()

        # Add edges without adding nodes (graph doesn't enforce referential integrity)
        edge = Edge(
            id="e1",
            edge_type=EdgeType.CREATES,
            source_id="nonexistent_source",
            target_id="nonexistent_target",
        )
        graph.add_edge(edge)

        assert graph.node_count == 0
        assert graph.edge_count == 1
        assert edge in graph.edges
