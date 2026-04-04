"""Tests for graph exporter module - DOT and GraphML export functions."""

import xml.etree.ElementTree as ET

import pytest

from maid_runner.graph.exporters import (
    _escape_dot_string,
    _get_node_label,
    _get_node_shape,
    export_dot,
    export_graphml,
    graph_to_dot,
    graph_to_graphml,
)
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


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def empty_graph():
    """An empty KnowledgeGraph with no nodes or edges."""
    return KnowledgeGraph()


@pytest.fixture
def single_node_graph():
    """A graph containing a single file node."""
    graph = KnowledgeGraph()
    graph.add_node(FileNode(id="f1", path="src/auth.py", status="tracked"))
    return graph


@pytest.fixture
def graph_with_edges():
    """A graph with manifest, file, and artifact nodes connected by edges."""
    graph = KnowledgeGraph()
    manifest = ManifestNode(
        id="m1",
        path="manifests/add-auth.manifest.yaml",
        goal="Add authentication",
        task_type="feature",
        version="2",
    )
    file_node = FileNode(id="f1", path="src/auth.py", status="tracked")
    artifact = ArtifactNode(id="a1", name="login", artifact_type="function")
    graph.add_node(manifest)
    graph.add_node(file_node)
    graph.add_node(artifact)
    graph.add_edge(
        Edge(id="e1", edge_type=EdgeType.CREATES, source_id="m1", target_id="f1")
    )
    graph.add_edge(
        Edge(id="e2", edge_type=EdgeType.DEFINES, source_id="f1", target_id="a1")
    )
    return graph


# ---------------------------------------------------------------------------
# TestGraphToDot
# ---------------------------------------------------------------------------


class TestGraphToDot:
    def test_empty_graph_produces_valid_dot(self, empty_graph):
        """An empty graph produces a valid DOT structure with no node/edge lines."""
        result = graph_to_dot(empty_graph)
        assert result.startswith("digraph G {")
        assert result.strip().endswith("}")
        # Only the opening and closing lines, nothing in between
        lines = result.strip().split("\n")
        assert len(lines) == 2

    def test_single_node_graph(self, single_node_graph):
        """A graph with one node produces DOT with exactly one node declaration."""
        result = graph_to_dot(single_node_graph)
        assert result.startswith("digraph G {")
        assert result.strip().endswith("}")
        lines = [line.strip() for line in result.strip().split("\n")]
        # Opening line, one node line, closing line
        assert len(lines) == 3
        assert '"f1"' in lines[1]
        assert "shape=ellipse" in lines[1]

    def test_graph_with_edges(self, graph_with_edges):
        """A graph with nodes and edges produces both node and edge declarations."""
        result = graph_to_dot(graph_with_edges)
        assert result.startswith("digraph G {")
        assert result.strip().endswith("}")
        # 3 nodes + 2 edges + opening + closing = 7 lines
        lines = [line.strip() for line in result.strip().split("\n")]
        assert len(lines) == 7
        # Check edges are present
        assert any("->" in line for line in lines)

    def test_manifest_node_uses_box_shape(self):
        """A ManifestNode is rendered with shape=box in DOT output."""
        graph = KnowledgeGraph()
        graph.add_node(
            ManifestNode(
                id="m1",
                path="manifests/x.yaml",
                goal="Do X",
                task_type="feature",
                version="2",
            )
        )
        result = graph_to_dot(graph)
        assert "shape=box" in result

    def test_file_node_uses_ellipse_shape(self):
        """A FileNode is rendered with shape=ellipse in DOT output."""
        graph = KnowledgeGraph()
        graph.add_node(FileNode(id="f1", path="src/auth.py", status="tracked"))
        result = graph_to_dot(graph)
        assert "shape=ellipse" in result

    def test_artifact_node_uses_diamond_shape(self):
        """An ArtifactNode is rendered with shape=diamond in DOT output."""
        graph = KnowledgeGraph()
        graph.add_node(ArtifactNode(id="a1", name="login", artifact_type="function"))
        result = graph_to_dot(graph)
        assert "shape=diamond" in result

    def test_module_node_uses_hexagon_shape(self):
        """A ModuleNode is rendered with shape=hexagon in DOT output."""
        graph = KnowledgeGraph()
        graph.add_node(ModuleNode(id="mod1", name="auth", package="src"))
        result = graph_to_dot(graph)
        assert "shape=hexagon" in result

    def test_manifest_node_label_shows_goal(self):
        """A ManifestNode with a goal uses the goal as its label."""
        graph = KnowledgeGraph()
        graph.add_node(
            ManifestNode(
                id="m1",
                path="manifests/x.yaml",
                goal="Add authentication",
                task_type="feature",
                version="2",
            )
        )
        result = graph_to_dot(graph)
        assert 'label="Add authentication"' in result

    def test_manifest_node_without_goal_shows_path(self):
        """A ManifestNode with an empty goal falls back to path as label."""
        graph = KnowledgeGraph()
        graph.add_node(
            ManifestNode(
                id="m1",
                path="manifests/x.yaml",
                goal="",
                task_type="feature",
                version="2",
            )
        )
        result = graph_to_dot(graph)
        assert 'label="manifests/x.yaml"' in result

    def test_file_node_label_shows_path(self):
        """A FileNode uses its path as the label."""
        graph = KnowledgeGraph()
        graph.add_node(FileNode(id="f1", path="src/auth.py", status="tracked"))
        result = graph_to_dot(graph)
        assert 'label="src/auth.py"' in result

    def test_artifact_node_label_shows_name(self):
        """An ArtifactNode uses its name as the label."""
        graph = KnowledgeGraph()
        graph.add_node(ArtifactNode(id="a1", name="login", artifact_type="function"))
        result = graph_to_dot(graph)
        assert 'label="login"' in result

    def test_module_node_label_shows_name(self):
        """A ModuleNode uses its name as the label."""
        graph = KnowledgeGraph()
        graph.add_node(ModuleNode(id="mod1", name="auth", package="src"))
        result = graph_to_dot(graph)
        assert 'label="auth"' in result

    def test_generic_node_label_shows_id(self):
        """A plain Node (not a specialized subclass) uses its id as the label."""
        graph = KnowledgeGraph()
        graph.add_node(Node(id="generic1", node_type=NodeType.FILE))
        result = graph_to_dot(graph)
        assert 'label="generic1"' in result

    def test_special_characters_are_escaped(self):
        """Quotes and backslashes in node labels are escaped in DOT output."""
        graph = KnowledgeGraph()
        graph.add_node(
            ManifestNode(
                id="m1",
                path="manifests/x.yaml",
                goal='Say "hello" with \\n',
                task_type="feature",
                version="2",
            )
        )
        result = graph_to_dot(graph)
        # The goal string should have quotes escaped
        assert '\\"hello\\"' in result
        # Backslash should be escaped
        assert "\\\\\\\\" in result or "\\\\n" in result

    def test_edge_label_shows_edge_type(self, graph_with_edges):
        """Edges include their EdgeType value as the label."""
        result = graph_to_dot(graph_with_edges)
        assert 'label="creates"' in result
        assert 'label="defines"' in result

    def test_edge_format_uses_arrow(self, graph_with_edges):
        """Edges use the '->' arrow syntax in DOT format."""
        result = graph_to_dot(graph_with_edges)
        lines = result.strip().split("\n")
        edge_lines = [line for line in lines if "->" in line]
        assert len(edge_lines) == 2
        for line in edge_lines:
            assert "->" in line
            assert line.strip().endswith(";")


# ---------------------------------------------------------------------------
# TestExportDot
# ---------------------------------------------------------------------------


class TestExportDot:
    def test_creates_file(self, tmp_path, graph_with_edges):
        """export_dot writes a DOT file to the specified path."""
        output = tmp_path / "graph.dot"
        export_dot(graph_with_edges, output)
        assert output.exists()
        assert output.stat().st_size > 0

    def test_creates_parent_directories(self, tmp_path, graph_with_edges):
        """export_dot creates intermediate directories if they do not exist."""
        output = tmp_path / "deep" / "nested" / "dir" / "graph.dot"
        export_dot(graph_with_edges, output)
        assert output.exists()

    def test_file_contains_valid_dot(self, tmp_path, graph_with_edges):
        """The written file contains valid DOT format content."""
        output = tmp_path / "graph.dot"
        export_dot(graph_with_edges, output)
        content = output.read_text(encoding="utf-8")
        assert content.startswith("digraph G {")
        assert content.strip().endswith("}")
        # Verify nodes and edges are present
        assert '"m1"' in content
        assert '"f1"' in content
        assert "->" in content


# ---------------------------------------------------------------------------
# TestGraphToGraphml
# ---------------------------------------------------------------------------


class TestGraphToGraphml:
    def test_empty_graph_produces_valid_xml(self, empty_graph):
        """An empty graph produces well-formed XML with no node or edge elements."""
        result = graph_to_graphml(empty_graph)
        # Should parse without error
        root = ET.fromstring(result.split("\n", 1)[1])
        ns = "http://graphml.graphdrawing.org/xmlns"
        graph_elem = root.find(f"{{{ns}}}graph")
        assert graph_elem is not None
        nodes = graph_elem.findall(f"{{{ns}}}node")
        edges = graph_elem.findall(f"{{{ns}}}edge")
        assert len(nodes) == 0
        assert len(edges) == 0

    def test_graph_with_nodes_and_edges(self, graph_with_edges):
        """A graph with nodes and edges produces corresponding XML elements."""
        result = graph_to_graphml(graph_with_edges)
        root = ET.fromstring(result.split("\n", 1)[1])
        ns = "http://graphml.graphdrawing.org/xmlns"
        graph_elem = root.find(f"{{{ns}}}graph")
        nodes = graph_elem.findall(f"{{{ns}}}node")
        edges = graph_elem.findall(f"{{{ns}}}edge")
        assert len(nodes) == 3
        assert len(edges) == 2

    def test_xml_has_declaration(self, empty_graph):
        """The GraphML output begins with an XML declaration."""
        result = graph_to_graphml(empty_graph)
        assert result.startswith('<?xml version="1.0" encoding="UTF-8"?>')

    def test_node_types_are_included(self, graph_with_edges):
        """Each node element contains a data element with its node_type value."""
        result = graph_to_graphml(graph_with_edges)
        root = ET.fromstring(result.split("\n", 1)[1])
        ns = "http://graphml.graphdrawing.org/xmlns"
        graph_elem = root.find(f"{{{ns}}}graph")
        nodes = graph_elem.findall(f"{{{ns}}}node")
        node_types = set()
        for node in nodes:
            data = node.find(f"{{{ns}}}data[@key='node_type']")
            assert data is not None
            node_types.add(data.text)
        assert "manifest" in node_types
        assert "file" in node_types
        assert "artifact" in node_types

    def test_edge_types_are_included(self, graph_with_edges):
        """Each edge element contains a data element with its edge_type value."""
        result = graph_to_graphml(graph_with_edges)
        root = ET.fromstring(result.split("\n", 1)[1])
        ns = "http://graphml.graphdrawing.org/xmlns"
        graph_elem = root.find(f"{{{ns}}}graph")
        edges = graph_elem.findall(f"{{{ns}}}edge")
        edge_types = set()
        for edge in edges:
            data = edge.find(f"{{{ns}}}data[@key='edge_type']")
            assert data is not None
            edge_types.add(data.text)
        assert "creates" in edge_types
        assert "defines" in edge_types

    def test_graphml_namespace(self, empty_graph):
        """The root graphml element uses the standard GraphML namespace."""
        result = graph_to_graphml(empty_graph)
        root = ET.fromstring(result.split("\n", 1)[1])
        assert (
            root.tag == "{http://graphml.graphdrawing.org/xmlns}graphml"
            or root.get("xmlns") == "http://graphml.graphdrawing.org/xmlns"
        )

    def test_graph_is_directed(self, empty_graph):
        """The graph element has edgedefault='directed'."""
        result = graph_to_graphml(empty_graph)
        root = ET.fromstring(result.split("\n", 1)[1])
        ns = "http://graphml.graphdrawing.org/xmlns"
        graph_elem = root.find(f"{{{ns}}}graph")
        assert graph_elem.get("edgedefault") == "directed"

    def test_key_definitions_present(self, empty_graph):
        """The GraphML output defines key elements for node_type and edge_type."""
        result = graph_to_graphml(empty_graph)
        root = ET.fromstring(result.split("\n", 1)[1])
        ns = "http://graphml.graphdrawing.org/xmlns"
        keys = root.findall(f"{{{ns}}}key")
        key_ids = {k.get("id") for k in keys}
        assert "node_type" in key_ids
        assert "edge_type" in key_ids

    def test_node_ids_match_graph_nodes(self, graph_with_edges):
        """Node id attributes in XML match the node ids from the graph."""
        result = graph_to_graphml(graph_with_edges)
        root = ET.fromstring(result.split("\n", 1)[1])
        ns = "http://graphml.graphdrawing.org/xmlns"
        graph_elem = root.find(f"{{{ns}}}graph")
        xml_node_ids = {n.get("id") for n in graph_elem.findall(f"{{{ns}}}node")}
        assert xml_node_ids == {"m1", "f1", "a1"}

    def test_edge_source_target_match(self, graph_with_edges):
        """Edge source and target attributes match the original edge endpoints."""
        result = graph_to_graphml(graph_with_edges)
        root = ET.fromstring(result.split("\n", 1)[1])
        ns = "http://graphml.graphdrawing.org/xmlns"
        graph_elem = root.find(f"{{{ns}}}graph")
        edges = graph_elem.findall(f"{{{ns}}}edge")
        edge_pairs = {(e.get("source"), e.get("target")) for e in edges}
        assert ("m1", "f1") in edge_pairs
        assert ("f1", "a1") in edge_pairs


# ---------------------------------------------------------------------------
# TestExportGraphml
# ---------------------------------------------------------------------------


class TestExportGraphml:
    def test_creates_file(self, tmp_path, graph_with_edges):
        """export_graphml writes a GraphML file to the specified path."""
        output = tmp_path / "graph.graphml"
        export_graphml(graph_with_edges, output)
        assert output.exists()
        assert output.stat().st_size > 0

    def test_creates_parent_directories(self, tmp_path, graph_with_edges):
        """export_graphml creates intermediate directories if they do not exist."""
        output = tmp_path / "deep" / "nested" / "dir" / "graph.graphml"
        export_graphml(graph_with_edges, output)
        assert output.exists()

    def test_file_contains_valid_xml(self, tmp_path, graph_with_edges):
        """The written file contains valid, parseable XML with GraphML structure."""
        output = tmp_path / "graph.graphml"
        export_graphml(graph_with_edges, output)
        content = output.read_text(encoding="utf-8")
        assert content.startswith('<?xml version="1.0" encoding="UTF-8"?>')
        # Parse the XML body (skip declaration line)
        xml_body = content.split("\n", 1)[1]
        root = ET.fromstring(xml_body)
        ns = "http://graphml.graphdrawing.org/xmlns"
        graph_elem = root.find(f"{{{ns}}}graph")
        assert graph_elem is not None
        nodes = graph_elem.findall(f"{{{ns}}}node")
        assert len(nodes) == 3


# ---------------------------------------------------------------------------
# TestEscapeDotString
# ---------------------------------------------------------------------------


class TestEscapeDotString:
    def test_escapes_quotes(self):
        """Double quotes in a string are escaped with a backslash."""
        result = _escape_dot_string('say "hello"')
        assert result == 'say \\"hello\\"'

    def test_escapes_backslashes(self):
        """Backslashes in a string are escaped (doubled)."""
        result = _escape_dot_string("path\\to\\file")
        assert result == "path\\\\to\\\\file"

    def test_plain_string_unchanged(self):
        """A string with no special characters passes through unchanged."""
        result = _escape_dot_string("plain text")
        assert result == "plain text"

    def test_both_quotes_and_backslashes(self):
        """A string with both quotes and backslashes escapes both correctly."""
        result = _escape_dot_string('a \\ b "c"')
        assert result == 'a \\\\ b \\"c\\"'

    def test_empty_string(self):
        """An empty string remains empty after escaping."""
        result = _escape_dot_string("")
        assert result == ""

    def test_only_backslash(self):
        """A single backslash is doubled."""
        result = _escape_dot_string("\\")
        assert result == "\\\\"

    def test_only_quote(self):
        """A single double-quote is escaped."""
        result = _escape_dot_string('"')
        assert result == '\\"'


# ---------------------------------------------------------------------------
# TestGetNodeShape
# ---------------------------------------------------------------------------


class TestGetNodeShape:
    def test_manifest_returns_box(self):
        node = ManifestNode(
            id="m1",
            path="manifests/x.yaml",
            goal="X",
            task_type="feature",
            version="2",
        )
        assert _get_node_shape(node) == "box"

    def test_file_returns_ellipse(self):
        node = FileNode(id="f1", path="src/f.py", status="tracked")
        assert _get_node_shape(node) == "ellipse"

    def test_artifact_returns_diamond(self):
        node = ArtifactNode(id="a1", name="fn", artifact_type="function")
        assert _get_node_shape(node) == "diamond"

    def test_module_returns_hexagon(self):
        node = ModuleNode(id="mod1", name="auth", package="src")
        assert _get_node_shape(node) == "hexagon"

    def test_unknown_node_type_defaults_to_ellipse(self):
        """A generic Node with an unrecognized type falls back to ellipse."""
        node = Node(id="x1", node_type=NodeType.FILE)
        assert _get_node_shape(node) == "ellipse"


# ---------------------------------------------------------------------------
# TestGetNodeLabel
# ---------------------------------------------------------------------------


class TestGetNodeLabel:
    def test_manifest_with_goal(self):
        node = ManifestNode(
            id="m1",
            path="manifests/x.yaml",
            goal="Add auth",
            task_type="feature",
            version="2",
        )
        assert _get_node_label(node) == "Add auth"

    def test_manifest_without_goal(self):
        node = ManifestNode(
            id="m1",
            path="manifests/x.yaml",
            goal="",
            task_type="feature",
            version="2",
        )
        assert _get_node_label(node) == "manifests/x.yaml"

    def test_file_node(self):
        node = FileNode(id="f1", path="src/auth.py", status="tracked")
        assert _get_node_label(node) == "src/auth.py"

    def test_artifact_node(self):
        node = ArtifactNode(id="a1", name="login", artifact_type="function")
        assert _get_node_label(node) == "login"

    def test_module_node(self):
        node = ModuleNode(id="mod1", name="auth", package="src")
        assert _get_node_label(node) == "auth"

    def test_generic_node(self):
        node = Node(id="generic1", node_type=NodeType.FILE)
        assert _get_node_label(node) == "generic1"
