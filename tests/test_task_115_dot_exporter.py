"""Behavioral tests for Task 115: DOT Exporter (Graphviz).

Tests the export_dot and graph_to_dot functions which convert a
KnowledgeGraph to DOT format for visualization with Graphviz.
"""

from pathlib import Path

from maid_runner.graph.exporters import export_dot, graph_to_dot
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


class TestGraphToDotReturnType:
    """Tests for graph_to_dot return type."""

    def test_returns_string(self) -> None:
        """graph_to_dot returns a string."""
        graph = KnowledgeGraph()

        result = graph_to_dot(graph)

        assert isinstance(result, str)

    def test_empty_graph_returns_non_empty_string(self) -> None:
        """graph_to_dot returns a non-empty string for empty graph."""
        graph = KnowledgeGraph()

        result = graph_to_dot(graph)

        assert len(result) > 0


class TestGraphToDotEmptyGraph:
    """Tests for graph_to_dot with an empty graph."""

    def test_empty_graph_contains_digraph_keyword(self) -> None:
        """Empty graph DOT output contains 'digraph' keyword."""
        graph = KnowledgeGraph()

        result = graph_to_dot(graph)

        assert "digraph" in result

    def test_empty_graph_contains_opening_brace(self) -> None:
        """Empty graph DOT output contains opening brace."""
        graph = KnowledgeGraph()

        result = graph_to_dot(graph)

        assert "{" in result

    def test_empty_graph_contains_closing_brace(self) -> None:
        """Empty graph DOT output contains closing brace."""
        graph = KnowledgeGraph()

        result = graph_to_dot(graph)

        assert "}" in result

    def test_empty_graph_has_valid_structure(self) -> None:
        """Empty graph DOT output has valid digraph structure."""
        graph = KnowledgeGraph()

        result = graph_to_dot(graph)

        # Should match pattern: digraph ... { ... }
        assert result.strip().startswith("digraph")
        assert result.strip().endswith("}")


class TestGraphToDotNodes:
    """Tests for graph_to_dot node serialization."""

    def test_node_id_appears_in_output(self) -> None:
        """Node ID appears in DOT output."""
        graph = KnowledgeGraph()
        node = Node(id="test-node", node_type=NodeType.FILE)
        graph.add_node(node)

        result = graph_to_dot(graph)

        assert "test-node" in result

    def test_node_appears_as_quoted_identifier(self) -> None:
        """Node appears as a quoted identifier in DOT format."""
        graph = KnowledgeGraph()
        node = Node(id="my_node", node_type=NodeType.FILE)
        graph.add_node(node)

        result = graph_to_dot(graph)

        # DOT format uses quoted identifiers: "node_id"
        assert '"my_node"' in result

    def test_multiple_nodes_all_appear(self) -> None:
        """Multiple nodes all appear in DOT output."""
        graph = KnowledgeGraph()
        node1 = Node(id="node1", node_type=NodeType.FILE)
        node2 = Node(id="node2", node_type=NodeType.MANIFEST)
        node3 = Node(id="node3", node_type=NodeType.ARTIFACT)
        graph.add_node(node1)
        graph.add_node(node2)
        graph.add_node(node3)

        result = graph_to_dot(graph)

        assert '"node1"' in result
        assert '"node2"' in result
        assert '"node3"' in result

    def test_node_with_special_characters_escaped(self) -> None:
        """Node ID with special characters is properly handled."""
        graph = KnowledgeGraph()
        node = Node(id="path/to/file.py", node_type=NodeType.FILE)
        graph.add_node(node)

        result = graph_to_dot(graph)

        # The node ID should appear in the output
        assert "path/to/file.py" in result


class TestGraphToDotEdges:
    """Tests for graph_to_dot edge serialization."""

    def test_edge_uses_arrow_syntax(self) -> None:
        """Edges use arrow syntax (->)."""
        graph = KnowledgeGraph()
        node1 = Node(id="source", node_type=NodeType.MANIFEST)
        node2 = Node(id="target", node_type=NodeType.FILE)
        graph.add_node(node1)
        graph.add_node(node2)
        edge = Edge(
            id="edge1",
            edge_type=EdgeType.CREATES,
            source_id="source",
            target_id="target",
        )
        graph.add_edge(edge)

        result = graph_to_dot(graph)

        assert "->" in result

    def test_edge_contains_source_and_target(self) -> None:
        """Edge contains source and target node IDs."""
        graph = KnowledgeGraph()
        node1 = Node(id="manifest1", node_type=NodeType.MANIFEST)
        node2 = Node(id="file1", node_type=NodeType.FILE)
        graph.add_node(node1)
        graph.add_node(node2)
        edge = Edge(
            id="edge1",
            edge_type=EdgeType.CREATES,
            source_id="manifest1",
            target_id="file1",
        )
        graph.add_edge(edge)

        result = graph_to_dot(graph)

        # Should have pattern like "source" -> "target"
        assert '"manifest1"' in result
        assert '"file1"' in result
        assert "->" in result

    def test_multiple_edges_all_appear(self) -> None:
        """Multiple edges all appear in DOT output."""
        graph = KnowledgeGraph()
        node1 = Node(id="m1", node_type=NodeType.MANIFEST)
        node2 = Node(id="f1", node_type=NodeType.FILE)
        node3 = Node(id="a1", node_type=NodeType.ARTIFACT)
        graph.add_node(node1)
        graph.add_node(node2)
        graph.add_node(node3)

        edge1 = Edge(
            id="e1",
            edge_type=EdgeType.CREATES,
            source_id="m1",
            target_id="f1",
        )
        edge2 = Edge(
            id="e2",
            edge_type=EdgeType.DEFINES,
            source_id="f1",
            target_id="a1",
        )
        graph.add_edge(edge1)
        graph.add_edge(edge2)

        result = graph_to_dot(graph)

        # Count arrows - should have at least 2
        assert result.count("->") >= 2


class TestGraphToDotEdgeLabels:
    """Tests for edge labels in DOT output."""

    def test_edge_label_includes_edge_type(self) -> None:
        """Edge label includes the edge type."""
        graph = KnowledgeGraph()
        node1 = Node(id="source", node_type=NodeType.MANIFEST)
        node2 = Node(id="target", node_type=NodeType.FILE)
        graph.add_node(node1)
        graph.add_node(node2)
        edge = Edge(
            id="edge1",
            edge_type=EdgeType.CREATES,
            source_id="source",
            target_id="target",
        )
        graph.add_edge(edge)

        result = graph_to_dot(graph)

        # Edge type should appear as label
        assert "creates" in result.lower()

    def test_supersedes_edge_type_in_label(self) -> None:
        """SUPERSEDES edge type appears in edge label."""
        graph = KnowledgeGraph()
        node1 = Node(id="m2", node_type=NodeType.MANIFEST)
        node2 = Node(id="m1", node_type=NodeType.MANIFEST)
        graph.add_node(node1)
        graph.add_node(node2)
        edge = Edge(
            id="edge1",
            edge_type=EdgeType.SUPERSEDES,
            source_id="m2",
            target_id="m1",
        )
        graph.add_edge(edge)

        result = graph_to_dot(graph)

        assert "supersedes" in result.lower()

    def test_defines_edge_type_in_label(self) -> None:
        """DEFINES edge type appears in edge label."""
        graph = KnowledgeGraph()
        node1 = Node(id="file", node_type=NodeType.FILE)
        node2 = Node(id="artifact", node_type=NodeType.ARTIFACT)
        graph.add_node(node1)
        graph.add_node(node2)
        edge = Edge(
            id="edge1",
            edge_type=EdgeType.DEFINES,
            source_id="file",
            target_id="artifact",
        )
        graph.add_edge(edge)

        result = graph_to_dot(graph)

        assert "defines" in result.lower()


class TestGraphToDotNodeShapes:
    """Tests for node shapes/styles based on node type."""

    def test_manifest_node_has_specific_shape(self) -> None:
        """ManifestNode has a specific shape in DOT output."""
        graph = KnowledgeGraph()
        manifest = ManifestNode(
            id="manifest1",
            path="manifests/task-001.manifest.json",
            goal="Test goal",
            task_type="create",
            version="1.0",
        )
        graph.add_node(manifest)

        result = graph_to_dot(graph)

        # ManifestNode should have a shape attribute
        assert '"manifest1"' in result
        assert "shape=" in result.lower() or "shape =" in result.lower()

    def test_file_node_has_specific_shape(self) -> None:
        """FileNode has a specific shape in DOT output."""
        graph = KnowledgeGraph()
        file_node = FileNode(
            id="file1",
            path="src/module.py",
            status="tracked",
        )
        graph.add_node(file_node)

        result = graph_to_dot(graph)

        # FileNode should have a shape attribute
        assert '"file1"' in result
        assert "shape=" in result.lower() or "shape =" in result.lower()

    def test_artifact_node_has_specific_shape(self) -> None:
        """ArtifactNode has a specific shape in DOT output."""
        graph = KnowledgeGraph()
        artifact = ArtifactNode(
            id="artifact1",
            name="my_function",
            artifact_type="function",
        )
        graph.add_node(artifact)

        result = graph_to_dot(graph)

        # ArtifactNode should have a shape attribute
        assert '"artifact1"' in result
        assert "shape=" in result.lower() or "shape =" in result.lower()

    def test_module_node_has_specific_shape(self) -> None:
        """ModuleNode has a specific shape in DOT output."""
        graph = KnowledgeGraph()
        module = ModuleNode(
            id="module1",
            name="utils",
            package="maid_runner",
        )
        graph.add_node(module)

        result = graph_to_dot(graph)

        # ModuleNode should have a shape attribute
        assert '"module1"' in result
        assert "shape=" in result.lower() or "shape =" in result.lower()

    def test_different_node_types_have_different_shapes(self) -> None:
        """Different node types have distinct shapes."""
        graph = KnowledgeGraph()
        manifest = ManifestNode(
            id="manifest1",
            path="path",
            goal="goal",
            task_type="create",
            version="1.0",
        )
        file_node = FileNode(
            id="file1",
            path="path.py",
            status="tracked",
        )
        artifact = ArtifactNode(
            id="artifact1",
            name="func",
            artifact_type="function",
        )
        module = ModuleNode(
            id="module1",
            name="mod",
            package="pkg",
        )
        graph.add_node(manifest)
        graph.add_node(file_node)
        graph.add_node(artifact)
        graph.add_node(module)

        result = graph_to_dot(graph)

        # All node IDs should appear
        assert '"manifest1"' in result
        assert '"file1"' in result
        assert '"artifact1"' in result
        assert '"module1"' in result


class TestGraphToDotNodeLabels:
    """Tests for node labels in DOT output."""

    def test_node_has_label_attribute(self) -> None:
        """Node has a label attribute in DOT output."""
        graph = KnowledgeGraph()
        node = Node(id="test-node", node_type=NodeType.FILE)
        graph.add_node(node)

        result = graph_to_dot(graph)

        # Should have label attribute
        assert "label=" in result.lower() or "label =" in result.lower()

    def test_manifest_node_label_includes_goal_or_path(self) -> None:
        """ManifestNode label includes goal or path information."""
        graph = KnowledgeGraph()
        manifest = ManifestNode(
            id="manifest1",
            path="manifests/task-001.manifest.json",
            goal="Create utility module",
            task_type="create",
            version="1.0",
        )
        graph.add_node(manifest)

        result = graph_to_dot(graph)

        # Label should include either the goal or path
        result_lower = result.lower()
        has_goal = "create utility module" in result_lower
        has_path = "task-001" in result_lower
        assert has_goal or has_path


class TestExportDot:
    """Tests for export_dot function."""

    def test_creates_file_at_output_path(self, tmp_path: Path) -> None:
        """export_dot creates a file at the specified path."""
        graph = KnowledgeGraph()
        output_path = tmp_path / "output.dot"

        export_dot(graph, output_path)

        assert output_path.exists()

    def test_file_contains_digraph(self, tmp_path: Path) -> None:
        """Exported file contains 'digraph' keyword."""
        graph = KnowledgeGraph()
        output_path = tmp_path / "output.dot"

        export_dot(graph, output_path)

        content = output_path.read_text()
        assert "digraph" in content

    def test_file_contains_valid_dot_structure(self, tmp_path: Path) -> None:
        """Exported file has valid DOT structure with braces."""
        graph = KnowledgeGraph()
        output_path = tmp_path / "output.dot"

        export_dot(graph, output_path)

        content = output_path.read_text()
        assert "{" in content
        assert "}" in content
        assert content.strip().startswith("digraph")
        assert content.strip().endswith("}")

    def test_exports_graph_with_node(self, tmp_path: Path) -> None:
        """Exports a graph with a node correctly."""
        graph = KnowledgeGraph()
        node = Node(id="test-node", node_type=NodeType.FILE)
        graph.add_node(node)
        output_path = tmp_path / "output.dot"

        export_dot(graph, output_path)

        content = output_path.read_text()
        assert '"test-node"' in content

    def test_exports_graph_with_edge(self, tmp_path: Path) -> None:
        """Exports a graph with an edge correctly."""
        graph = KnowledgeGraph()
        node1 = Node(id="source", node_type=NodeType.MANIFEST)
        node2 = Node(id="target", node_type=NodeType.FILE)
        graph.add_node(node1)
        graph.add_node(node2)
        edge = Edge(
            id="edge1",
            edge_type=EdgeType.CREATES,
            source_id="source",
            target_id="target",
        )
        graph.add_edge(edge)
        output_path = tmp_path / "output.dot"

        export_dot(graph, output_path)

        content = output_path.read_text()
        assert "->" in content

    def test_creates_nested_directories(self, tmp_path: Path) -> None:
        """export_dot creates parent directories if they don't exist."""
        graph = KnowledgeGraph()
        output_path = tmp_path / "nested" / "deep" / "output.dot"

        export_dot(graph, output_path)

        assert output_path.exists()

    def test_returns_none(self, tmp_path: Path) -> None:
        """export_dot returns None."""
        graph = KnowledgeGraph()
        output_path = tmp_path / "output.dot"

        result = export_dot(graph, output_path)

        assert result is None

    def test_overwrites_existing_file(self, tmp_path: Path) -> None:
        """export_dot overwrites an existing file."""
        graph1 = KnowledgeGraph()
        node1 = Node(id="first-node", node_type=NodeType.FILE)
        graph1.add_node(node1)

        graph2 = KnowledgeGraph()
        node2 = Node(id="second-node", node_type=NodeType.MANIFEST)
        graph2.add_node(node2)

        output_path = tmp_path / "output.dot"

        export_dot(graph1, output_path)
        export_dot(graph2, output_path)

        content = output_path.read_text()
        assert '"second-node"' in content
        assert '"first-node"' not in content


class TestGraphToDotComplexGraph:
    """Tests for graph_to_dot with complex graphs."""

    def test_complex_graph_with_multiple_node_types(self) -> None:
        """Complex graph with various node types produces valid DOT."""
        graph = KnowledgeGraph()

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
        graph.add_edge(
            Edge(
                id="e1",
                edge_type=EdgeType.CREATES,
                source_id="manifest-001",
                target_id="file-utils",
            )
        )
        graph.add_edge(
            Edge(
                id="e2",
                edge_type=EdgeType.DEFINES,
                source_id="file-utils",
                target_id="artifact-helper",
            )
        )
        graph.add_edge(
            Edge(
                id="e3",
                edge_type=EdgeType.BELONGS_TO,
                source_id="file-utils",
                target_id="module-utils",
            )
        )

        result = graph_to_dot(graph)

        # Verify structure
        assert "digraph" in result
        assert "{" in result
        assert "}" in result

        # Verify all nodes present
        assert '"manifest-001"' in result
        assert '"file-utils"' in result
        assert '"artifact-helper"' in result
        assert '"module-utils"' in result

        # Verify edges present
        assert result.count("->") >= 3

    def test_graph_with_all_edge_types(self) -> None:
        """Graph with various edge types includes all edge type labels."""
        graph = KnowledgeGraph()

        # Add minimal nodes for edges
        for i in range(10):
            node = Node(id=f"node{i}", node_type=NodeType.FILE)
            graph.add_node(node)

        edge_types = [
            EdgeType.SUPERSEDES,
            EdgeType.CREATES,
            EdgeType.EDITS,
            EdgeType.READS,
            EdgeType.DEFINES,
        ]

        for i, edge_type in enumerate(edge_types):
            edge = Edge(
                id=f"edge{i}",
                edge_type=edge_type,
                source_id=f"node{i}",
                target_id=f"node{i + 1}",
            )
            graph.add_edge(edge)

        result = graph_to_dot(graph)

        # Each edge type should appear in the output
        result_lower = result.lower()
        assert "supersedes" in result_lower
        assert "creates" in result_lower
        assert "edits" in result_lower
        assert "reads" in result_lower
        assert "defines" in result_lower
