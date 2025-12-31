"""Behavioral tests for Task 107: KnowledgeGraphBuilder class.

Tests the main orchestration class that builds a KnowledgeGraph from MAID manifests.
The KnowledgeGraphBuilder coordinates loading manifests, creating nodes and edges
using the existing factory functions, and assembling them into a complete graph.

Artifacts tested:
- KnowledgeGraphBuilder: Main class for graph construction
- __init__(self, manifest_dir: Path): Initialize with manifest directory
- build(self) -> KnowledgeGraph: Build and return the complete graph
- _process_manifest(self, manifest_data, path): Process a single manifest
- _extract_artifacts(self, manifest_data): Extract artifact data from manifest
"""

import json
import pytest
from pathlib import Path
from typing import Any, Dict

from maid_runner.graph.builder import KnowledgeGraphBuilder
from maid_runner.graph.model import (
    KnowledgeGraph,
    NodeType,
    EdgeType,
)


@pytest.fixture
def manifest_dir(tmp_path: Path) -> Path:
    """Create a temporary manifest directory."""
    manifests = tmp_path / "manifests"
    manifests.mkdir()
    return manifests


@pytest.fixture
def sample_manifest_data() -> Dict[str, Any]:
    """Create a sample manifest data dictionary."""
    return {
        "goal": "Create utility module",
        "taskType": "create",
        "creatableFiles": ["src/utils.py"],
        "editableFiles": [],
        "readonlyFiles": ["src/config.py"],
        "expectedArtifacts": {
            "file": "src/utils.py",
            "contains": [
                {"type": "function", "name": "helper_function"},
                {"type": "class", "name": "HelperClass"},
            ],
        },
    }


@pytest.fixture
def manifest_with_supersedes() -> Dict[str, Any]:
    """Create manifest data with supersedes relationship."""
    return {
        "goal": "Update utilities",
        "taskType": "edit",
        "supersedes": ["manifests/task-001.manifest.json"],
        "editableFiles": ["src/utils.py"],
        "expectedArtifacts": {
            "file": "src/utils.py",
            "contains": [
                {"type": "function", "name": "new_helper"},
            ],
        },
    }


@pytest.fixture
def manifest_without_artifacts() -> Dict[str, Any]:
    """Create manifest data without expectedArtifacts."""
    return {
        "goal": "Documentation update",
        "taskType": "edit",
        "editableFiles": ["README.md"],
    }


@pytest.fixture
def manifest_with_method_artifacts() -> Dict[str, Any]:
    """Create manifest with method artifacts that have parent classes."""
    return {
        "goal": "Add class methods",
        "taskType": "edit",
        "editableFiles": ["src/service.py"],
        "expectedArtifacts": {
            "file": "src/service.py",
            "contains": [
                {"type": "class", "name": "MyService"},
                {
                    "type": "function",
                    "name": "__init__",
                    "class": "MyService",
                    "args": [{"name": "self"}, {"name": "config", "type": "Config"}],
                },
                {
                    "type": "function",
                    "name": "process",
                    "class": "MyService",
                    "args": [{"name": "self"}, {"name": "data", "type": "Dict"}],
                    "returns": "Result",
                },
            ],
        },
    }


def create_manifest_file(
    manifest_dir: Path, filename: str, data: Dict[str, Any]
) -> Path:
    """Helper to create a manifest file in the test directory."""
    manifest_path = manifest_dir / filename
    with open(manifest_path, "w") as f:
        json.dump(data, f)
    return manifest_path


class TestKnowledgeGraphBuilderClass:
    """Tests for KnowledgeGraphBuilder class instantiation."""

    def test_class_can_be_instantiated(self, manifest_dir: Path) -> None:
        """KnowledgeGraphBuilder can be instantiated with a manifest_dir Path."""
        builder = KnowledgeGraphBuilder(manifest_dir)

        assert builder is not None
        assert isinstance(builder, KnowledgeGraphBuilder)

    def test_accepts_path_object(self, manifest_dir: Path) -> None:
        """Constructor accepts Path object for manifest_dir."""
        builder = KnowledgeGraphBuilder(manifest_dir)

        assert hasattr(builder, "manifest_dir")

    def test_stores_manifest_dir_attribute(self, manifest_dir: Path) -> None:
        """Constructor stores manifest_dir as an attribute."""
        builder = KnowledgeGraphBuilder(manifest_dir)

        assert builder.manifest_dir == manifest_dir


class TestKnowledgeGraphBuilderInit:
    """Tests for KnowledgeGraphBuilder.__init__ method."""

    def test_init_with_valid_path(self, manifest_dir: Path) -> None:
        """__init__ accepts a valid Path to manifests directory."""
        builder = KnowledgeGraphBuilder(manifest_dir=manifest_dir)

        assert builder.manifest_dir == manifest_dir

    def test_init_stores_path_as_attribute(self, tmp_path: Path) -> None:
        """__init__ stores the provided path as manifest_dir attribute."""
        custom_dir = tmp_path / "custom_manifests"
        custom_dir.mkdir()

        builder = KnowledgeGraphBuilder(manifest_dir=custom_dir)

        assert builder.manifest_dir == custom_dir

    def test_init_explicitly_called(self, manifest_dir: Path) -> None:
        """__init__ can be called explicitly on an existing instance."""
        builder = KnowledgeGraphBuilder(manifest_dir)
        original_dir = builder.manifest_dir

        # Explicitly call __init__ with manifest_dir parameter
        builder.__init__(manifest_dir=manifest_dir)

        assert builder.manifest_dir == original_dir

    def test_init_with_different_path(self, tmp_path: Path) -> None:
        """__init__ can reinitialize with a different manifest_dir."""
        dir1 = tmp_path / "manifests1"
        dir1.mkdir()
        dir2 = tmp_path / "manifests2"
        dir2.mkdir()

        builder = KnowledgeGraphBuilder(manifest_dir=dir1)
        assert builder.manifest_dir == dir1

        # Reinitialize with different path
        builder.__init__(manifest_dir=dir2)

        assert builder.manifest_dir == dir2


class TestKnowledgeGraphBuilderBuild:
    """Tests for KnowledgeGraphBuilder.build() method."""

    def test_build_returns_knowledge_graph(
        self, manifest_dir: Path, sample_manifest_data: Dict[str, Any]
    ) -> None:
        """build() returns a KnowledgeGraph instance."""
        create_manifest_file(
            manifest_dir, "task-001.manifest.json", sample_manifest_data
        )
        builder = KnowledgeGraphBuilder(manifest_dir)

        result = builder.build()

        assert isinstance(result, KnowledgeGraph)

    def test_build_with_empty_directory_returns_empty_graph(
        self, manifest_dir: Path
    ) -> None:
        """build() with empty manifest directory returns empty graph."""
        builder = KnowledgeGraphBuilder(manifest_dir)

        result = builder.build()

        assert isinstance(result, KnowledgeGraph)
        assert result.node_count == 0
        assert result.edge_count == 0

    def test_build_creates_manifest_node_for_each_manifest(
        self, manifest_dir: Path, sample_manifest_data: Dict[str, Any]
    ) -> None:
        """build() creates a ManifestNode for each active manifest."""
        create_manifest_file(
            manifest_dir, "task-001.manifest.json", sample_manifest_data
        )
        create_manifest_file(
            manifest_dir,
            "task-002.manifest.json",
            {
                "goal": "Second task",
                "taskType": "edit",
                "editableFiles": ["src/other.py"],
            },
        )
        builder = KnowledgeGraphBuilder(manifest_dir)

        result = builder.build()

        manifest_nodes = [
            n for n in result.nodes if n.node_type == NodeType.MANIFEST
        ]
        assert len(manifest_nodes) == 2

    def test_build_creates_file_nodes(
        self, manifest_dir: Path, sample_manifest_data: Dict[str, Any]
    ) -> None:
        """build() creates FileNode for files referenced in manifests."""
        create_manifest_file(
            manifest_dir, "task-001.manifest.json", sample_manifest_data
        )
        builder = KnowledgeGraphBuilder(manifest_dir)

        result = builder.build()

        file_nodes = [n for n in result.nodes if n.node_type == NodeType.FILE]
        # Should have file nodes for creatableFiles and readonlyFiles
        assert len(file_nodes) >= 2

    def test_build_creates_artifact_nodes(
        self, manifest_dir: Path, sample_manifest_data: Dict[str, Any]
    ) -> None:
        """build() creates ArtifactNode for artifacts in expectedArtifacts."""
        create_manifest_file(
            manifest_dir, "task-001.manifest.json", sample_manifest_data
        )
        builder = KnowledgeGraphBuilder(manifest_dir)

        result = builder.build()

        artifact_nodes = [n for n in result.nodes if n.node_type == NodeType.ARTIFACT]
        # Should have artifact nodes for helper_function and HelperClass
        assert len(artifact_nodes) >= 2

    def test_build_creates_supersedes_edges(
        self,
        manifest_dir: Path,
        sample_manifest_data: Dict[str, Any],
        manifest_with_supersedes: Dict[str, Any],
    ) -> None:
        """build() creates SUPERSEDES edges for supersedes relationships."""
        # Create the superseded manifest first so the edge can be validated
        create_manifest_file(
            manifest_dir, "task-001.manifest.json", sample_manifest_data
        )
        # Update supersedes path to match the actual manifest location
        manifest_with_supersedes = manifest_with_supersedes.copy()
        manifest_with_supersedes["supersedes"] = [
            str(manifest_dir / "task-001.manifest.json")
        ]
        create_manifest_file(
            manifest_dir, "task-002.manifest.json", manifest_with_supersedes
        )
        builder = KnowledgeGraphBuilder(manifest_dir)

        result = builder.build()

        supersedes_edges = [
            e for e in result.edges if e.edge_type == EdgeType.SUPERSEDES
        ]
        assert len(supersedes_edges) >= 1

    def test_build_creates_file_relationship_edges(
        self, manifest_dir: Path, sample_manifest_data: Dict[str, Any]
    ) -> None:
        """build() creates CREATES/EDITS/READS edges for file relationships."""
        create_manifest_file(
            manifest_dir, "task-001.manifest.json", sample_manifest_data
        )
        builder = KnowledgeGraphBuilder(manifest_dir)

        result = builder.build()

        creates_edges = [e for e in result.edges if e.edge_type == EdgeType.CREATES]
        reads_edges = [e for e in result.edges if e.edge_type == EdgeType.READS]

        # Should have CREATES edge for src/utils.py
        assert len(creates_edges) >= 1
        # Should have READS edge for src/config.py
        assert len(reads_edges) >= 1

    def test_build_creates_defines_edges(
        self, manifest_dir: Path, sample_manifest_data: Dict[str, Any]
    ) -> None:
        """build() creates DEFINES edges from files to artifacts."""
        create_manifest_file(
            manifest_dir, "task-001.manifest.json", sample_manifest_data
        )
        builder = KnowledgeGraphBuilder(manifest_dir)

        result = builder.build()

        defines_edges = [e for e in result.edges if e.edge_type == EdgeType.DEFINES]
        assert len(defines_edges) >= 2  # One for each artifact

    def test_build_creates_declares_edges(
        self, manifest_dir: Path, sample_manifest_data: Dict[str, Any]
    ) -> None:
        """build() creates DECLARES edges from manifest to artifacts."""
        create_manifest_file(
            manifest_dir, "task-001.manifest.json", sample_manifest_data
        )
        builder = KnowledgeGraphBuilder(manifest_dir)

        result = builder.build()

        declares_edges = [e for e in result.edges if e.edge_type == EdgeType.DECLARES]
        assert len(declares_edges) >= 2  # One for each artifact

    def test_build_with_single_manifest_creates_correct_structure(
        self, manifest_dir: Path
    ) -> None:
        """build() with single manifest creates appropriate nodes and edges."""
        manifest_data = {
            "goal": "Simple task",
            "taskType": "create",
            "creatableFiles": ["src/simple.py"],
            "expectedArtifacts": {
                "file": "src/simple.py",
                "contains": [{"type": "function", "name": "simple_func"}],
            },
        }
        create_manifest_file(manifest_dir, "task-001.manifest.json", manifest_data)
        builder = KnowledgeGraphBuilder(manifest_dir)

        result = builder.build()

        # Verify structure
        assert result.node_count >= 3  # manifest + file + artifact
        assert result.edge_count >= 3  # creates + defines + declares

    def test_build_with_multiple_manifests_creates_all_nodes(
        self, manifest_dir: Path, sample_manifest_data: Dict[str, Any]
    ) -> None:
        """build() with multiple manifests creates nodes for all."""
        create_manifest_file(
            manifest_dir, "task-001.manifest.json", sample_manifest_data
        )
        second_manifest = {
            "goal": "Second task",
            "taskType": "create",
            "creatableFiles": ["src/another.py"],
            "expectedArtifacts": {
                "file": "src/another.py",
                "contains": [{"type": "class", "name": "AnotherClass"}],
            },
        }
        create_manifest_file(manifest_dir, "task-002.manifest.json", second_manifest)
        builder = KnowledgeGraphBuilder(manifest_dir)

        result = builder.build()

        # Should have nodes from both manifests
        manifest_nodes = [n for n in result.nodes if n.node_type == NodeType.MANIFEST]
        assert len(manifest_nodes) == 2


class TestKnowledgeGraphBuilderProcessManifest:
    """Tests for KnowledgeGraphBuilder._process_manifest method."""

    def test_process_manifest_creates_manifest_node(
        self, manifest_dir: Path, sample_manifest_data: Dict[str, Any]
    ) -> None:
        """_process_manifest creates a ManifestNode for the manifest."""
        builder = KnowledgeGraphBuilder(manifest_dir)
        # Initialize the graph (would normally be done in build())
        builder._graph = KnowledgeGraph()
        manifest_path = manifest_dir / "task-001.manifest.json"

        builder._process_manifest(sample_manifest_data, manifest_path)

        manifest_nodes = [
            n for n in builder._graph.nodes if n.node_type == NodeType.MANIFEST
        ]
        assert len(manifest_nodes) == 1

    def test_process_manifest_creates_file_nodes_for_all_file_types(
        self, manifest_dir: Path
    ) -> None:
        """_process_manifest creates FileNodes for creatable, editable, readonly files."""
        manifest_data = {
            "goal": "Multi-file task",
            "taskType": "edit",
            "creatableFiles": ["src/new.py"],
            "editableFiles": ["src/existing.py"],
            "readonlyFiles": ["src/readonly.py"],
        }
        builder = KnowledgeGraphBuilder(manifest_dir)
        builder._graph = KnowledgeGraph()
        manifest_path = manifest_dir / "task-001.manifest.json"

        builder._process_manifest(manifest_data, manifest_path)

        file_nodes = [n for n in builder._graph.nodes if n.node_type == NodeType.FILE]
        # Should have 3 file nodes
        assert len(file_nodes) >= 3

    def test_process_manifest_creates_edges_for_supersedes(
        self, manifest_dir: Path, manifest_with_supersedes: Dict[str, Any]
    ) -> None:
        """_process_manifest creates SUPERSEDES edges for supersedes relationships."""
        builder = KnowledgeGraphBuilder(manifest_dir)
        builder._graph = KnowledgeGraph()
        manifest_path = manifest_dir / "task-002.manifest.json"

        builder._process_manifest(manifest_with_supersedes, manifest_path)

        supersedes_edges = [
            e for e in builder._graph.edges if e.edge_type == EdgeType.SUPERSEDES
        ]
        assert len(supersedes_edges) >= 1

    def test_process_manifest_adds_nodes_to_graph(
        self, manifest_dir: Path, sample_manifest_data: Dict[str, Any]
    ) -> None:
        """_process_manifest adds created nodes to the internal graph."""
        builder = KnowledgeGraphBuilder(manifest_dir)
        builder._graph = KnowledgeGraph()
        manifest_path = manifest_dir / "task-001.manifest.json"

        initial_count = builder._graph.node_count
        builder._process_manifest(sample_manifest_data, manifest_path)

        assert builder._graph.node_count > initial_count


class TestKnowledgeGraphBuilderExtractArtifacts:
    """Tests for KnowledgeGraphBuilder._extract_artifacts method."""

    def test_extract_artifacts_returns_list(
        self, manifest_dir: Path, sample_manifest_data: Dict[str, Any]
    ) -> None:
        """_extract_artifacts returns a list."""
        builder = KnowledgeGraphBuilder(manifest_dir)

        result = builder._extract_artifacts(sample_manifest_data)

        assert isinstance(result, list)

    def test_extract_artifacts_returns_tuples(
        self, manifest_dir: Path, sample_manifest_data: Dict[str, Any]
    ) -> None:
        """_extract_artifacts returns list of (artifact_dict, file_path) tuples."""
        builder = KnowledgeGraphBuilder(manifest_dir)

        result = builder._extract_artifacts(sample_manifest_data)

        assert len(result) > 0
        for item in result:
            assert isinstance(item, tuple)
            assert len(item) == 2
            assert isinstance(item[0], dict)  # artifact_dict
            assert isinstance(item[1], str)  # file_path

    def test_extract_artifacts_extracts_all_artifacts(
        self, manifest_dir: Path, sample_manifest_data: Dict[str, Any]
    ) -> None:
        """_extract_artifacts extracts all artifacts from expectedArtifacts."""
        builder = KnowledgeGraphBuilder(manifest_dir)

        result = builder._extract_artifacts(sample_manifest_data)

        # sample_manifest_data has 2 artifacts: helper_function and HelperClass
        assert len(result) == 2

    def test_extract_artifacts_includes_file_path(
        self, manifest_dir: Path, sample_manifest_data: Dict[str, Any]
    ) -> None:
        """_extract_artifacts includes file path from expectedArtifacts.file."""
        builder = KnowledgeGraphBuilder(manifest_dir)

        result = builder._extract_artifacts(sample_manifest_data)

        # All artifacts should have the same file path
        for artifact_dict, file_path in result:
            assert file_path == "src/utils.py"

    def test_extract_artifacts_handles_manifest_without_expected_artifacts(
        self, manifest_dir: Path, manifest_without_artifacts: Dict[str, Any]
    ) -> None:
        """_extract_artifacts handles manifest without expectedArtifacts."""
        builder = KnowledgeGraphBuilder(manifest_dir)

        result = builder._extract_artifacts(manifest_without_artifacts)

        assert result == []

    def test_extract_artifacts_handles_multiple_artifacts(
        self, manifest_dir: Path, manifest_with_method_artifacts: Dict[str, Any]
    ) -> None:
        """_extract_artifacts handles expectedArtifacts with multiple artifacts."""
        builder = KnowledgeGraphBuilder(manifest_dir)

        result = builder._extract_artifacts(manifest_with_method_artifacts)

        # Should extract all 3 artifacts: MyService, __init__, process
        assert len(result) == 3

    def test_extract_artifacts_preserves_artifact_data(
        self, manifest_dir: Path, sample_manifest_data: Dict[str, Any]
    ) -> None:
        """_extract_artifacts preserves artifact dictionary content."""
        builder = KnowledgeGraphBuilder(manifest_dir)

        result = builder._extract_artifacts(sample_manifest_data)

        artifact_names = [artifact["name"] for artifact, _ in result]
        assert "helper_function" in artifact_names
        assert "HelperClass" in artifact_names

    def test_extract_artifacts_handles_empty_contains_array(
        self, manifest_dir: Path
    ) -> None:
        """_extract_artifacts handles expectedArtifacts with empty contains array."""
        manifest_data = {
            "goal": "Empty artifacts",
            "taskType": "edit",
            "expectedArtifacts": {"file": "src/empty.py", "contains": []},
        }
        builder = KnowledgeGraphBuilder(manifest_dir)

        result = builder._extract_artifacts(manifest_data)

        assert result == []


class TestKnowledgeGraphBuilderIntegration:
    """Integration tests for KnowledgeGraphBuilder."""

    def test_full_workflow_single_manifest(
        self, manifest_dir: Path, sample_manifest_data: Dict[str, Any]
    ) -> None:
        """Test complete workflow with single manifest."""
        create_manifest_file(
            manifest_dir, "task-001.manifest.json", sample_manifest_data
        )
        builder = KnowledgeGraphBuilder(manifest_dir)

        graph = builder.build()

        # Verify all expected components exist
        assert graph.node_count > 0
        assert graph.edge_count > 0

        # Should have manifest, file, and artifact nodes
        node_types = {n.node_type for n in graph.nodes}
        assert NodeType.MANIFEST in node_types
        assert NodeType.FILE in node_types
        assert NodeType.ARTIFACT in node_types

    def test_full_workflow_multiple_manifests(
        self, manifest_dir: Path, sample_manifest_data: Dict[str, Any]
    ) -> None:
        """Test complete workflow with multiple manifests."""
        create_manifest_file(
            manifest_dir, "task-001.manifest.json", sample_manifest_data
        )
        second_manifest = {
            "goal": "Second task",
            "taskType": "edit",
            "editableFiles": ["src/utils.py"],
            "expectedArtifacts": {
                "file": "src/utils.py",
                "contains": [{"type": "function", "name": "additional_helper"}],
            },
        }
        create_manifest_file(manifest_dir, "task-002.manifest.json", second_manifest)
        builder = KnowledgeGraphBuilder(manifest_dir)

        graph = builder.build()

        # Should have 2 manifest nodes
        manifest_nodes = [n for n in graph.nodes if n.node_type == NodeType.MANIFEST]
        assert len(manifest_nodes) == 2

    def test_graph_edges_reference_existing_nodes(
        self, manifest_dir: Path, sample_manifest_data: Dict[str, Any]
    ) -> None:
        """All edge source_ids and target_ids reference existing nodes."""
        create_manifest_file(
            manifest_dir, "task-001.manifest.json", sample_manifest_data
        )
        builder = KnowledgeGraphBuilder(manifest_dir)

        graph = builder.build()

        node_ids = {n.id for n in graph.nodes}
        for edge in graph.edges:
            # SUPERSEDES edges may reference nodes not in the graph
            # (superseded manifests are not loaded)
            if edge.edge_type != EdgeType.SUPERSEDES:
                assert edge.source_id in node_ids, f"Missing source node: {edge.source_id}"
                assert edge.target_id in node_ids, f"Missing target node: {edge.target_id}"
