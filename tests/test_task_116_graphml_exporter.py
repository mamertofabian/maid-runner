"""Behavioral tests for Task 116: GraphML Exporter.

Tests the export_graphml and graph_to_graphml functions which convert a
KnowledgeGraph to GraphML format for interoperability with graph analysis tools.
"""

import xml.etree.ElementTree as ET
from pathlib import Path

from maid_runner.graph.exporters import export_graphml, graph_to_graphml
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


class TestGraphToGraphmlReturnType:
    """Tests for graph_to_graphml return type."""

    def test_returns_string(self) -> None:
        """graph_to_graphml returns a string."""
        graph = KnowledgeGraph()

        result = graph_to_graphml(graph)

        assert isinstance(result, str)

    def test_empty_graph_returns_non_empty_string(self) -> None:
        """graph_to_graphml returns a non-empty string for empty graph."""
        graph = KnowledgeGraph()

        result = graph_to_graphml(graph)

        assert len(result) > 0


class TestGraphToGraphmlXmlValidity:
    """Tests for graph_to_graphml XML validity."""

    def test_output_is_valid_xml(self) -> None:
        """graph_to_graphml output can be parsed as XML."""
        graph = KnowledgeGraph()

        result = graph_to_graphml(graph)

        # Should not raise an exception
        root = ET.fromstring(result)
        assert root is not None

    def test_output_with_nodes_is_valid_xml(self) -> None:
        """graph_to_graphml output with nodes can be parsed as XML."""
        graph = KnowledgeGraph()
        node = Node(id="test-node", node_type=NodeType.FILE)
        graph.add_node(node)

        result = graph_to_graphml(graph)

        root = ET.fromstring(result)
        assert root is not None

    def test_output_with_edges_is_valid_xml(self) -> None:
        """graph_to_graphml output with edges can be parsed as XML."""
        graph = KnowledgeGraph()
        edge = Edge(
            id="edge1",
            edge_type=EdgeType.CREATES,
            source_id="source",
            target_id="target",
        )
        graph.add_edge(edge)

        result = graph_to_graphml(graph)

        root = ET.fromstring(result)
        assert root is not None


class TestGraphToGraphmlStructure:
    """Tests for graph_to_graphml XML structure."""

    def test_root_element_is_graphml(self) -> None:
        """Root element of output is 'graphml'."""
        graph = KnowledgeGraph()

        result = graph_to_graphml(graph)

        root = ET.fromstring(result)
        # Tag may include namespace, so check if it ends with 'graphml'
        assert root.tag.endswith("graphml")

    def test_contains_graphml_namespace(self) -> None:
        """Output contains GraphML namespace."""
        graph = KnowledgeGraph()

        result = graph_to_graphml(graph)

        assert "http://graphml.graphdrawing.org/xmlns" in result

    def test_contains_graph_element(self) -> None:
        """Output contains a graph element."""
        graph = KnowledgeGraph()

        result = graph_to_graphml(graph)

        root = ET.fromstring(result)
        # Find graph element (with or without namespace)
        graph_elements = [elem for elem in root.iter() if elem.tag.endswith("graph")]
        assert len(graph_elements) >= 1

    def test_graph_is_directed(self) -> None:
        """Graph element indicates directed edges."""
        graph = KnowledgeGraph()

        result = graph_to_graphml(graph)

        root = ET.fromstring(result)
        graph_elements = [elem for elem in root.iter() if elem.tag.endswith("graph")]
        assert len(graph_elements) >= 1
        graph_elem = graph_elements[0]
        assert graph_elem.get("edgedefault") == "directed"


class TestGraphToGraphmlKeyDefinitions:
    """Tests for GraphML key definitions."""

    def test_contains_key_definitions(self) -> None:
        """Output contains key definitions for node/edge attributes."""
        graph = KnowledgeGraph()

        result = graph_to_graphml(graph)

        root = ET.fromstring(result)
        key_elements = [elem for elem in root.iter() if elem.tag.endswith("key")]
        assert len(key_elements) > 0

    def test_contains_node_type_key(self) -> None:
        """Output contains a key definition for node_type."""
        graph = KnowledgeGraph()

        result = graph_to_graphml(graph)

        # Check that node_type key is defined
        assert 'attr.name="node_type"' in result or "node_type" in result

    def test_contains_edge_type_key(self) -> None:
        """Output contains a key definition for edge_type."""
        graph = KnowledgeGraph()

        result = graph_to_graphml(graph)

        # Check that edge_type key is defined
        assert 'attr.name="edge_type"' in result or "edge_type" in result


class TestGraphToGraphmlNodes:
    """Tests for graph_to_graphml node serialization."""

    def test_node_appears_as_node_element(self) -> None:
        """Nodes are represented as <node> elements."""
        graph = KnowledgeGraph()
        node = Node(id="test-node", node_type=NodeType.FILE)
        graph.add_node(node)

        result = graph_to_graphml(graph)

        root = ET.fromstring(result)
        node_elements = [elem for elem in root.iter() if elem.tag.endswith("node")]
        assert len(node_elements) >= 1

    def test_node_has_id_attribute(self) -> None:
        """Node elements have an 'id' attribute."""
        graph = KnowledgeGraph()
        node = Node(id="my-node-id", node_type=NodeType.FILE)
        graph.add_node(node)

        result = graph_to_graphml(graph)

        root = ET.fromstring(result)
        node_elements = [elem for elem in root.iter() if elem.tag.endswith("node")]
        assert len(node_elements) >= 1
        assert node_elements[0].get("id") == "my-node-id"

    def test_multiple_nodes_all_present(self) -> None:
        """Multiple nodes all appear in output."""
        graph = KnowledgeGraph()
        node1 = Node(id="node1", node_type=NodeType.FILE)
        node2 = Node(id="node2", node_type=NodeType.MANIFEST)
        node3 = Node(id="node3", node_type=NodeType.ARTIFACT)
        graph.add_node(node1)
        graph.add_node(node2)
        graph.add_node(node3)

        result = graph_to_graphml(graph)

        root = ET.fromstring(result)
        node_elements = [elem for elem in root.iter() if elem.tag.endswith("node")]
        node_ids = [elem.get("id") for elem in node_elements]
        assert "node1" in node_ids
        assert "node2" in node_ids
        assert "node3" in node_ids


class TestGraphToGraphmlNodeTypes:
    """Tests for node type data in GraphML output."""

    def test_node_includes_type_data(self) -> None:
        """Node includes node_type as data element."""
        graph = KnowledgeGraph()
        node = Node(id="test-node", node_type=NodeType.FILE)
        graph.add_node(node)

        result = graph_to_graphml(graph)

        # The node type should appear in the data
        assert "file" in result

    def test_manifest_node_type_in_output(self) -> None:
        """ManifestNode type appears in output."""
        graph = KnowledgeGraph()
        manifest = ManifestNode(
            id="manifest1",
            path="manifests/task-001.manifest.json",
            goal="Test goal",
            task_type="create",
            version="1.0",
        )
        graph.add_node(manifest)

        result = graph_to_graphml(graph)

        assert "manifest" in result

    def test_artifact_node_type_in_output(self) -> None:
        """ArtifactNode type appears in output."""
        graph = KnowledgeGraph()
        artifact = ArtifactNode(
            id="artifact1",
            name="my_function",
            artifact_type="function",
        )
        graph.add_node(artifact)

        result = graph_to_graphml(graph)

        assert "artifact" in result

    def test_module_node_type_in_output(self) -> None:
        """ModuleNode type appears in output."""
        graph = KnowledgeGraph()
        module = ModuleNode(
            id="module1",
            name="utils",
            package="maid_runner",
        )
        graph.add_node(module)

        result = graph_to_graphml(graph)

        assert "module" in result


class TestGraphToGraphmlEdges:
    """Tests for graph_to_graphml edge serialization."""

    def test_edge_appears_as_edge_element(self) -> None:
        """Edges are represented as <edge> elements."""
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

        result = graph_to_graphml(graph)

        root = ET.fromstring(result)
        edge_elements = [elem for elem in root.iter() if elem.tag.endswith("edge")]
        assert len(edge_elements) >= 1

    def test_edge_has_source_attribute(self) -> None:
        """Edge elements have a 'source' attribute."""
        graph = KnowledgeGraph()
        edge = Edge(
            id="edge1",
            edge_type=EdgeType.CREATES,
            source_id="source-node",
            target_id="target-node",
        )
        graph.add_edge(edge)

        result = graph_to_graphml(graph)

        root = ET.fromstring(result)
        edge_elements = [elem for elem in root.iter() if elem.tag.endswith("edge")]
        assert len(edge_elements) >= 1
        assert edge_elements[0].get("source") == "source-node"

    def test_edge_has_target_attribute(self) -> None:
        """Edge elements have a 'target' attribute."""
        graph = KnowledgeGraph()
        edge = Edge(
            id="edge1",
            edge_type=EdgeType.CREATES,
            source_id="source-node",
            target_id="target-node",
        )
        graph.add_edge(edge)

        result = graph_to_graphml(graph)

        root = ET.fromstring(result)
        edge_elements = [elem for elem in root.iter() if elem.tag.endswith("edge")]
        assert len(edge_elements) >= 1
        assert edge_elements[0].get("target") == "target-node"

    def test_multiple_edges_all_present(self) -> None:
        """Multiple edges all appear in output."""
        graph = KnowledgeGraph()
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
        edge3 = Edge(
            id="e3",
            edge_type=EdgeType.SUPERSEDES,
            source_id="m2",
            target_id="m1",
        )
        graph.add_edge(edge1)
        graph.add_edge(edge2)
        graph.add_edge(edge3)

        result = graph_to_graphml(graph)

        root = ET.fromstring(result)
        edge_elements = [elem for elem in root.iter() if elem.tag.endswith("edge")]
        assert len(edge_elements) >= 3


class TestGraphToGraphmlEdgeTypes:
    """Tests for edge type data in GraphML output."""

    def test_edge_includes_type_data(self) -> None:
        """Edge includes edge_type as data element."""
        graph = KnowledgeGraph()
        edge = Edge(
            id="edge1",
            edge_type=EdgeType.CREATES,
            source_id="source",
            target_id="target",
        )
        graph.add_edge(edge)

        result = graph_to_graphml(graph)

        assert "creates" in result

    def test_supersedes_edge_type_in_output(self) -> None:
        """SUPERSEDES edge type appears in output."""
        graph = KnowledgeGraph()
        edge = Edge(
            id="edge1",
            edge_type=EdgeType.SUPERSEDES,
            source_id="m2",
            target_id="m1",
        )
        graph.add_edge(edge)

        result = graph_to_graphml(graph)

        assert "supersedes" in result

    def test_defines_edge_type_in_output(self) -> None:
        """DEFINES edge type appears in output."""
        graph = KnowledgeGraph()
        edge = Edge(
            id="edge1",
            edge_type=EdgeType.DEFINES,
            source_id="file",
            target_id="artifact",
        )
        graph.add_edge(edge)

        result = graph_to_graphml(graph)

        assert "defines" in result

    def test_all_edge_types_serialize_correctly(self) -> None:
        """All EdgeType values serialize to expected string values."""
        graph = KnowledgeGraph()
        edge_type_mapping = {
            EdgeType.SUPERSEDES: "supersedes",
            EdgeType.CREATES: "creates",
            EdgeType.EDITS: "edits",
            EdgeType.READS: "reads",
            EdgeType.DEFINES: "defines",
            EdgeType.DECLARES: "declares",
            EdgeType.CONTAINS: "contains",
            EdgeType.INHERITS: "inherits",
            EdgeType.BELONGS_TO: "belongs_to",
        }

        for i, (edge_type, _) in enumerate(edge_type_mapping.items()):
            edge = Edge(
                id=f"edge{i}",
                edge_type=edge_type,
                source_id="source",
                target_id="target",
            )
            graph.add_edge(edge)

        result = graph_to_graphml(graph)

        for expected_str in edge_type_mapping.values():
            assert expected_str in result


class TestExportGraphml:
    """Tests for export_graphml function."""

    def test_creates_file_at_output_path(self, tmp_path: Path) -> None:
        """export_graphml creates a file at the specified path."""
        graph = KnowledgeGraph()
        output_path = tmp_path / "output.graphml"

        export_graphml(graph, output_path)

        assert output_path.exists()

    def test_file_contains_valid_xml(self, tmp_path: Path) -> None:
        """Exported file contains valid XML."""
        graph = KnowledgeGraph()
        output_path = tmp_path / "output.graphml"

        export_graphml(graph, output_path)

        content = output_path.read_text()
        root = ET.fromstring(content)  # Should not raise
        assert root is not None

    def test_file_contains_graphml_root(self, tmp_path: Path) -> None:
        """Exported file has graphml as root element."""
        graph = KnowledgeGraph()
        output_path = tmp_path / "output.graphml"

        export_graphml(graph, output_path)

        content = output_path.read_text()
        root = ET.fromstring(content)
        assert root.tag.endswith("graphml")

    def test_file_contains_graphml_namespace(self, tmp_path: Path) -> None:
        """Exported file contains GraphML namespace."""
        graph = KnowledgeGraph()
        output_path = tmp_path / "output.graphml"

        export_graphml(graph, output_path)

        content = output_path.read_text()
        assert "http://graphml.graphdrawing.org/xmlns" in content

    def test_exports_graph_with_single_node(self, tmp_path: Path) -> None:
        """Exports a graph with a single node correctly."""
        graph = KnowledgeGraph()
        node = Node(id="test-node", node_type=NodeType.FILE)
        graph.add_node(node)
        output_path = tmp_path / "output.graphml"

        export_graphml(graph, output_path)

        content = output_path.read_text()
        root = ET.fromstring(content)
        node_elements = [elem for elem in root.iter() if elem.tag.endswith("node")]
        assert len(node_elements) >= 1
        assert node_elements[0].get("id") == "test-node"

    def test_exports_graph_with_single_edge(self, tmp_path: Path) -> None:
        """Exports a graph with a single edge correctly."""
        graph = KnowledgeGraph()
        edge = Edge(
            id="test-edge",
            edge_type=EdgeType.CREATES,
            source_id="source",
            target_id="target",
        )
        graph.add_edge(edge)
        output_path = tmp_path / "output.graphml"

        export_graphml(graph, output_path)

        content = output_path.read_text()
        root = ET.fromstring(content)
        edge_elements = [elem for elem in root.iter() if elem.tag.endswith("edge")]
        assert len(edge_elements) >= 1

    def test_exports_complex_graph(self, tmp_path: Path) -> None:
        """Exports a graph with multiple nodes and edges of various types."""
        graph = KnowledgeGraph()

        # Add various node types
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

        output_path = tmp_path / "complex.graphml"

        export_graphml(graph, output_path)

        content = output_path.read_text()
        root = ET.fromstring(content)

        node_elements = [elem for elem in root.iter() if elem.tag.endswith("node")]
        edge_elements = [elem for elem in root.iter() if elem.tag.endswith("edge")]

        assert len(node_elements) == 4
        assert len(edge_elements) == 3

        # Verify node IDs present
        node_ids = [elem.get("id") for elem in node_elements]
        assert "manifest-001" in node_ids
        assert "file-utils" in node_ids
        assert "artifact-helper" in node_ids
        assert "module-utils" in node_ids

    def test_creates_nested_directories(self, tmp_path: Path) -> None:
        """export_graphml creates parent directories if they don't exist."""
        graph = KnowledgeGraph()
        output_path = tmp_path / "nested" / "deep" / "output.graphml"

        export_graphml(graph, output_path)

        assert output_path.exists()

    def test_overwrites_existing_file(self, tmp_path: Path) -> None:
        """export_graphml overwrites an existing file."""
        graph1 = KnowledgeGraph()
        node1 = Node(id="first-node", node_type=NodeType.FILE)
        graph1.add_node(node1)

        graph2 = KnowledgeGraph()
        node2 = Node(id="second-node", node_type=NodeType.MANIFEST)
        graph2.add_node(node2)

        output_path = tmp_path / "output.graphml"

        export_graphml(graph1, output_path)
        export_graphml(graph2, output_path)

        content = output_path.read_text()
        root = ET.fromstring(content)
        node_elements = [elem for elem in root.iter() if elem.tag.endswith("node")]
        node_ids = [elem.get("id") for elem in node_elements]
        assert "second-node" in node_ids
        assert "first-node" not in node_ids

    def test_returns_none(self, tmp_path: Path) -> None:
        """export_graphml returns None."""
        graph = KnowledgeGraph()
        output_path = tmp_path / "output.graphml"

        result = export_graphml(graph, output_path)

        assert result is None


class TestGraphToGraphmlXmlDeclaration:
    """Tests for XML declaration in GraphML output."""

    def test_output_starts_with_xml_declaration(self) -> None:
        """Output starts with XML declaration."""
        graph = KnowledgeGraph()

        result = graph_to_graphml(graph)

        assert result.strip().startswith("<?xml")

    def test_xml_declaration_specifies_encoding(self) -> None:
        """XML declaration specifies UTF-8 encoding."""
        graph = KnowledgeGraph()

        result = graph_to_graphml(graph)

        assert "encoding" in result.lower()


class TestGraphToGraphmlSpecialCharacters:
    """Tests for handling special characters in GraphML output."""

    def test_node_with_special_characters_produces_valid_xml(self) -> None:
        """Node ID with special characters produces valid XML."""
        graph = KnowledgeGraph()
        node = Node(id="path/to/file.py", node_type=NodeType.FILE)
        graph.add_node(node)

        result = graph_to_graphml(graph)

        # Should be parseable
        root = ET.fromstring(result)
        node_elements = [elem for elem in root.iter() if elem.tag.endswith("node")]
        assert len(node_elements) >= 1

    def test_node_with_ampersand_produces_valid_xml(self) -> None:
        """Node with ampersand in attributes produces valid XML."""
        graph = KnowledgeGraph()
        node = Node(
            id="test-node",
            node_type=NodeType.FILE,
            attributes={"desc": "A & B"},
        )
        graph.add_node(node)

        result = graph_to_graphml(graph)

        # Should be parseable (ampersand must be escaped as &amp;)
        root = ET.fromstring(result)
        assert root is not None

    def test_node_with_angle_brackets_produces_valid_xml(self) -> None:
        """Node with angle brackets in attributes produces valid XML."""
        graph = KnowledgeGraph()
        artifact = ArtifactNode(
            id="artifact1",
            name="generic_func",
            artifact_type="function",
            signature="def generic_func(x: List[int]) -> Dict[str, Any]",
        )
        graph.add_node(artifact)

        result = graph_to_graphml(graph)

        # Should be parseable (angle brackets must be escaped)
        root = ET.fromstring(result)
        assert root is not None
