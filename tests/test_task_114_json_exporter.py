"""Behavioral tests for Task 114: JSON Exporter.

Tests the export_json and graph_to_dict functions which convert a
KnowledgeGraph to JSON format and write it to a file.
"""

import json
from pathlib import Path

from maid_runner.graph.exporters import export_json, graph_to_dict
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


class TestGraphToDictEmptyGraph:
    """Tests for graph_to_dict with an empty graph."""

    def test_empty_graph_returns_dict_with_nodes_key(self) -> None:
        """Empty graph dict contains 'nodes' key."""
        graph = KnowledgeGraph()

        result = graph_to_dict(graph)

        assert "nodes" in result

    def test_empty_graph_returns_dict_with_edges_key(self) -> None:
        """Empty graph dict contains 'edges' key."""
        graph = KnowledgeGraph()

        result = graph_to_dict(graph)

        assert "edges" in result

    def test_empty_graph_nodes_is_empty_list(self) -> None:
        """Empty graph has empty nodes array."""
        graph = KnowledgeGraph()

        result = graph_to_dict(graph)

        assert result["nodes"] == []

    def test_empty_graph_edges_is_empty_list(self) -> None:
        """Empty graph has empty edges array."""
        graph = KnowledgeGraph()

        result = graph_to_dict(graph)

        assert result["edges"] == []

    def test_empty_graph_returns_dict_type(self) -> None:
        """graph_to_dict returns a dictionary."""
        graph = KnowledgeGraph()

        result = graph_to_dict(graph)

        assert isinstance(result, dict)


class TestGraphToDictNodes:
    """Tests for graph_to_dict node serialization."""

    def test_node_includes_id(self) -> None:
        """Node dict includes 'id' field."""
        graph = KnowledgeGraph()
        node = Node(id="test-node", node_type=NodeType.FILE)
        graph.add_node(node)

        result = graph_to_dict(graph)

        assert len(result["nodes"]) == 1
        assert result["nodes"][0]["id"] == "test-node"

    def test_node_includes_type(self) -> None:
        """Node dict includes 'type' field with NodeType value."""
        graph = KnowledgeGraph()
        node = Node(id="test-node", node_type=NodeType.FILE)
        graph.add_node(node)

        result = graph_to_dict(graph)

        assert result["nodes"][0]["type"] == "file"

    def test_node_includes_attributes(self) -> None:
        """Node dict includes 'attributes' field."""
        graph = KnowledgeGraph()
        node = Node(
            id="test-node",
            node_type=NodeType.FILE,
            attributes={"custom": "value", "count": 42},
        )
        graph.add_node(node)

        result = graph_to_dict(graph)

        assert result["nodes"][0]["attributes"]["custom"] == "value"
        assert result["nodes"][0]["attributes"]["count"] == 42

    def test_multiple_nodes_all_serialized(self) -> None:
        """Multiple nodes are all included in the output."""
        graph = KnowledgeGraph()
        node1 = Node(id="node1", node_type=NodeType.FILE)
        node2 = Node(id="node2", node_type=NodeType.MANIFEST)
        node3 = Node(id="node3", node_type=NodeType.ARTIFACT)
        graph.add_node(node1)
        graph.add_node(node2)
        graph.add_node(node3)

        result = graph_to_dict(graph)

        assert len(result["nodes"]) == 3
        node_ids = [n["id"] for n in result["nodes"]]
        assert "node1" in node_ids
        assert "node2" in node_ids
        assert "node3" in node_ids


class TestGraphToDictManifestNode:
    """Tests for graph_to_dict ManifestNode serialization."""

    def test_manifest_node_includes_path(self) -> None:
        """ManifestNode dict includes 'path' field."""
        graph = KnowledgeGraph()
        manifest = ManifestNode(
            id="manifest1",
            path="manifests/task-001.manifest.json",
            goal="Test goal",
            task_type="create",
            version="1.0",
        )
        graph.add_node(manifest)

        result = graph_to_dict(graph)

        assert result["nodes"][0]["path"] == "manifests/task-001.manifest.json"

    def test_manifest_node_includes_goal(self) -> None:
        """ManifestNode dict includes 'goal' field."""
        graph = KnowledgeGraph()
        manifest = ManifestNode(
            id="manifest1",
            path="manifests/task-001.manifest.json",
            goal="Test goal description",
            task_type="create",
            version="1.0",
        )
        graph.add_node(manifest)

        result = graph_to_dict(graph)

        assert result["nodes"][0]["goal"] == "Test goal description"

    def test_manifest_node_includes_task_type(self) -> None:
        """ManifestNode dict includes 'task_type' field."""
        graph = KnowledgeGraph()
        manifest = ManifestNode(
            id="manifest1",
            path="manifests/task-001.manifest.json",
            goal="Test goal",
            task_type="edit",
            version="1.0",
        )
        graph.add_node(manifest)

        result = graph_to_dict(graph)

        assert result["nodes"][0]["task_type"] == "edit"

    def test_manifest_node_includes_version(self) -> None:
        """ManifestNode dict includes 'version' field."""
        graph = KnowledgeGraph()
        manifest = ManifestNode(
            id="manifest1",
            path="manifests/task-001.manifest.json",
            goal="Test goal",
            task_type="create",
            version="2.5",
        )
        graph.add_node(manifest)

        result = graph_to_dict(graph)

        assert result["nodes"][0]["version"] == "2.5"

    def test_manifest_node_type_is_manifest(self) -> None:
        """ManifestNode dict has type 'manifest'."""
        graph = KnowledgeGraph()
        manifest = ManifestNode(
            id="manifest1",
            path="path",
            goal="goal",
            task_type="create",
            version="1.0",
        )
        graph.add_node(manifest)

        result = graph_to_dict(graph)

        assert result["nodes"][0]["type"] == "manifest"


class TestGraphToDictFileNode:
    """Tests for graph_to_dict FileNode serialization."""

    def test_file_node_includes_path(self) -> None:
        """FileNode dict includes 'path' field."""
        graph = KnowledgeGraph()
        file_node = FileNode(
            id="file1",
            path="src/module.py",
            status="tracked",
        )
        graph.add_node(file_node)

        result = graph_to_dict(graph)

        assert result["nodes"][0]["path"] == "src/module.py"

    def test_file_node_includes_status(self) -> None:
        """FileNode dict includes 'status' field."""
        graph = KnowledgeGraph()
        file_node = FileNode(
            id="file1",
            path="src/module.py",
            status="untracked",
        )
        graph.add_node(file_node)

        result = graph_to_dict(graph)

        assert result["nodes"][0]["status"] == "untracked"

    def test_file_node_type_is_file(self) -> None:
        """FileNode dict has type 'file'."""
        graph = KnowledgeGraph()
        file_node = FileNode(
            id="file1",
            path="src/module.py",
            status="tracked",
        )
        graph.add_node(file_node)

        result = graph_to_dict(graph)

        assert result["nodes"][0]["type"] == "file"


class TestGraphToDictArtifactNode:
    """Tests for graph_to_dict ArtifactNode serialization."""

    def test_artifact_node_includes_name(self) -> None:
        """ArtifactNode dict includes 'name' field."""
        graph = KnowledgeGraph()
        artifact = ArtifactNode(
            id="artifact1",
            name="my_function",
            artifact_type="function",
        )
        graph.add_node(artifact)

        result = graph_to_dict(graph)

        assert result["nodes"][0]["name"] == "my_function"

    def test_artifact_node_includes_artifact_type(self) -> None:
        """ArtifactNode dict includes 'artifact_type' field."""
        graph = KnowledgeGraph()
        artifact = ArtifactNode(
            id="artifact1",
            name="MyClass",
            artifact_type="class",
        )
        graph.add_node(artifact)

        result = graph_to_dict(graph)

        assert result["nodes"][0]["artifact_type"] == "class"

    def test_artifact_node_includes_signature(self) -> None:
        """ArtifactNode dict includes 'signature' field when present."""
        graph = KnowledgeGraph()
        artifact = ArtifactNode(
            id="artifact1",
            name="my_function",
            artifact_type="function",
            signature="def my_function(x: int) -> str",
        )
        graph.add_node(artifact)

        result = graph_to_dict(graph)

        assert result["nodes"][0]["signature"] == "def my_function(x: int) -> str"

    def test_artifact_node_includes_parent_class(self) -> None:
        """ArtifactNode dict includes 'parent_class' field when present."""
        graph = KnowledgeGraph()
        artifact = ArtifactNode(
            id="artifact1",
            name="method",
            artifact_type="function",
            parent_class="MyClass",
        )
        graph.add_node(artifact)

        result = graph_to_dict(graph)

        assert result["nodes"][0]["parent_class"] == "MyClass"

    def test_artifact_node_type_is_artifact(self) -> None:
        """ArtifactNode dict has type 'artifact'."""
        graph = KnowledgeGraph()
        artifact = ArtifactNode(
            id="artifact1",
            name="my_function",
            artifact_type="function",
        )
        graph.add_node(artifact)

        result = graph_to_dict(graph)

        assert result["nodes"][0]["type"] == "artifact"


class TestGraphToDictModuleNode:
    """Tests for graph_to_dict ModuleNode serialization."""

    def test_module_node_includes_name(self) -> None:
        """ModuleNode dict includes 'name' field."""
        graph = KnowledgeGraph()
        module = ModuleNode(
            id="module1",
            name="utils",
            package="maid_runner",
        )
        graph.add_node(module)

        result = graph_to_dict(graph)

        assert result["nodes"][0]["name"] == "utils"

    def test_module_node_includes_package(self) -> None:
        """ModuleNode dict includes 'package' field."""
        graph = KnowledgeGraph()
        module = ModuleNode(
            id="module1",
            name="utils",
            package="maid_runner.graph",
        )
        graph.add_node(module)

        result = graph_to_dict(graph)

        assert result["nodes"][0]["package"] == "maid_runner.graph"

    def test_module_node_type_is_module(self) -> None:
        """ModuleNode dict has type 'module'."""
        graph = KnowledgeGraph()
        module = ModuleNode(
            id="module1",
            name="utils",
            package="maid_runner",
        )
        graph.add_node(module)

        result = graph_to_dict(graph)

        assert result["nodes"][0]["type"] == "module"

    def test_module_node_handles_none_package(self) -> None:
        """ModuleNode with None package is serialized correctly."""
        graph = KnowledgeGraph()
        module = ModuleNode(
            id="module1",
            name="standalone",
            package=None,
        )
        graph.add_node(module)

        result = graph_to_dict(graph)

        assert result["nodes"][0]["package"] is None


class TestGraphToDictEdges:
    """Tests for graph_to_dict edge serialization."""

    def test_edge_includes_id(self) -> None:
        """Edge dict includes 'id' field."""
        graph = KnowledgeGraph()
        edge = Edge(
            id="edge1",
            edge_type=EdgeType.CREATES,
            source_id="manifest1",
            target_id="file1",
        )
        graph.add_edge(edge)

        result = graph_to_dict(graph)

        assert len(result["edges"]) == 1
        assert result["edges"][0]["id"] == "edge1"

    def test_edge_includes_source(self) -> None:
        """Edge dict includes 'source' field with source_id."""
        graph = KnowledgeGraph()
        edge = Edge(
            id="edge1",
            edge_type=EdgeType.CREATES,
            source_id="manifest1",
            target_id="file1",
        )
        graph.add_edge(edge)

        result = graph_to_dict(graph)

        assert result["edges"][0]["source"] == "manifest1"

    def test_edge_includes_target(self) -> None:
        """Edge dict includes 'target' field with target_id."""
        graph = KnowledgeGraph()
        edge = Edge(
            id="edge1",
            edge_type=EdgeType.CREATES,
            source_id="manifest1",
            target_id="file1",
        )
        graph.add_edge(edge)

        result = graph_to_dict(graph)

        assert result["edges"][0]["target"] == "file1"

    def test_edge_includes_type(self) -> None:
        """Edge dict includes 'type' field with EdgeType value."""
        graph = KnowledgeGraph()
        edge = Edge(
            id="edge1",
            edge_type=EdgeType.SUPERSEDES,
            source_id="manifest2",
            target_id="manifest1",
        )
        graph.add_edge(edge)

        result = graph_to_dict(graph)

        assert result["edges"][0]["type"] == "supersedes"

    def test_edge_includes_attributes(self) -> None:
        """Edge dict includes 'attributes' field."""
        graph = KnowledgeGraph()
        edge = Edge(
            id="edge1",
            edge_type=EdgeType.CREATES,
            source_id="manifest1",
            target_id="file1",
            attributes={"weight": 1.5, "label": "test"},
        )
        graph.add_edge(edge)

        result = graph_to_dict(graph)

        assert result["edges"][0]["attributes"]["weight"] == 1.5
        assert result["edges"][0]["attributes"]["label"] == "test"

    def test_multiple_edges_all_serialized(self) -> None:
        """Multiple edges are all included in the output."""
        graph = KnowledgeGraph()
        edge1 = Edge(
            id="e1",
            edge_type=EdgeType.CREATES,
            source_id="m1",
            target_id="f1",
        )
        edge2 = Edge(
            id="e2",
            edge_type=EdgeType.EDITS,
            source_id="m2",
            target_id="f1",
        )
        edge3 = Edge(
            id="e3",
            edge_type=EdgeType.DEFINES,
            source_id="f1",
            target_id="a1",
        )
        graph.add_edge(edge1)
        graph.add_edge(edge2)
        graph.add_edge(edge3)

        result = graph_to_dict(graph)

        assert len(result["edges"]) == 3
        edge_ids = [e["id"] for e in result["edges"]]
        assert "e1" in edge_ids
        assert "e2" in edge_ids
        assert "e3" in edge_ids

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

        for i, (edge_type, expected_str) in enumerate(edge_type_mapping.items()):
            edge = Edge(
                id=f"edge{i}",
                edge_type=edge_type,
                source_id="source",
                target_id="target",
            )
            graph.add_edge(edge)

        result = graph_to_dict(graph)

        serialized_types = {e["type"] for e in result["edges"]}
        for expected_str in edge_type_mapping.values():
            assert expected_str in serialized_types


class TestExportJson:
    """Tests for export_json function."""

    def test_creates_file_at_output_path(self, tmp_path: Path) -> None:
        """export_json creates a file at the specified path."""
        graph = KnowledgeGraph()
        output_path = tmp_path / "output.json"

        export_json(graph, output_path)

        assert output_path.exists()

    def test_file_contains_valid_json(self, tmp_path: Path) -> None:
        """Exported file contains valid JSON."""
        graph = KnowledgeGraph()
        output_path = tmp_path / "output.json"

        export_json(graph, output_path)

        content = output_path.read_text()
        parsed = json.loads(content)  # Should not raise
        assert isinstance(parsed, dict)

    def test_file_contains_nodes_and_edges_keys(self, tmp_path: Path) -> None:
        """Exported JSON has 'nodes' and 'edges' keys."""
        graph = KnowledgeGraph()
        output_path = tmp_path / "output.json"

        export_json(graph, output_path)

        content = json.loads(output_path.read_text())
        assert "nodes" in content
        assert "edges" in content

    def test_exports_graph_with_single_node(self, tmp_path: Path) -> None:
        """Exports a graph with a single node correctly."""
        graph = KnowledgeGraph()
        node = Node(id="test-node", node_type=NodeType.FILE)
        graph.add_node(node)
        output_path = tmp_path / "output.json"

        export_json(graph, output_path)

        content = json.loads(output_path.read_text())
        assert len(content["nodes"]) == 1
        assert content["nodes"][0]["id"] == "test-node"

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
        output_path = tmp_path / "output.json"

        export_json(graph, output_path)

        content = json.loads(output_path.read_text())
        assert len(content["edges"]) == 1
        assert content["edges"][0]["id"] == "test-edge"

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

        output_path = tmp_path / "complex.json"

        export_json(graph, output_path)

        content = json.loads(output_path.read_text())
        assert len(content["nodes"]) == 4
        assert len(content["edges"]) == 3

        # Verify node types present
        node_types = {n["type"] for n in content["nodes"]}
        assert "manifest" in node_types
        assert "file" in node_types
        assert "artifact" in node_types
        assert "module" in node_types

        # Verify edge types present
        edge_types = {e["type"] for e in content["edges"]}
        assert "creates" in edge_types
        assert "defines" in edge_types
        assert "belongs_to" in edge_types

    def test_creates_nested_directories(self, tmp_path: Path) -> None:
        """export_json creates parent directories if they don't exist."""
        graph = KnowledgeGraph()
        output_path = tmp_path / "nested" / "deep" / "output.json"

        export_json(graph, output_path)

        assert output_path.exists()

    def test_overwrites_existing_file(self, tmp_path: Path) -> None:
        """export_json overwrites an existing file."""
        graph1 = KnowledgeGraph()
        node1 = Node(id="first", node_type=NodeType.FILE)
        graph1.add_node(node1)

        graph2 = KnowledgeGraph()
        node2 = Node(id="second", node_type=NodeType.MANIFEST)
        graph2.add_node(node2)

        output_path = tmp_path / "output.json"

        export_json(graph1, output_path)
        export_json(graph2, output_path)

        content = json.loads(output_path.read_text())
        assert len(content["nodes"]) == 1
        assert content["nodes"][0]["id"] == "second"

    def test_returns_none(self, tmp_path: Path) -> None:
        """export_json returns None."""
        graph = KnowledgeGraph()
        output_path = tmp_path / "output.json"

        result = export_json(graph, output_path)

        assert result is None


class TestGraphToDictJsonSerializable:
    """Tests that graph_to_dict output is JSON serializable."""

    def test_result_is_json_serializable(self) -> None:
        """graph_to_dict result can be serialized to JSON."""
        graph = KnowledgeGraph()
        manifest = ManifestNode(
            id="m1",
            path="path",
            goal="goal",
            task_type="create",
            version="1.0",
        )
        file_node = FileNode(id="f1", path="file.py", status="tracked")
        artifact = ArtifactNode(
            id="a1",
            name="func",
            artifact_type="function",
            signature="def func()",
            parent_class=None,
        )
        module = ModuleNode(id="mod1", name="mod", package=None)
        edge = Edge(
            id="e1",
            edge_type=EdgeType.CREATES,
            source_id="m1",
            target_id="f1",
            attributes={"key": "value"},
        )

        graph.add_node(manifest)
        graph.add_node(file_node)
        graph.add_node(artifact)
        graph.add_node(module)
        graph.add_edge(edge)

        result = graph_to_dict(graph)

        # Should not raise
        json_string = json.dumps(result)
        assert isinstance(json_string, str)
        assert len(json_string) > 0
