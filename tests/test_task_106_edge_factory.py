"""Behavioral tests for Task 106: Edge Factory functions.

Tests the factory functions that create Edge objects for different relationship
types in the knowledge graph:
- create_supersedes_edges: Creates SUPERSEDES edges between manifests
- create_file_edges: Creates CREATES/EDITS/READS edges between manifests and files
- create_artifact_edges: Creates DEFINES/DECLARES/CONTAINS edges for artifacts
"""

import pytest
from typing import Any, Dict

from maid_runner.graph.builder import (
    create_supersedes_edges,
    create_file_edges,
    create_artifact_edges,
)
from maid_runner.graph.model import Edge, EdgeType, ManifestNode


@pytest.fixture
def sample_manifest_node() -> ManifestNode:
    """Create a sample ManifestNode for testing."""
    return ManifestNode(
        id="manifest:manifests/task-100.manifest.json",
        path="manifests/task-100.manifest.json",
        goal="Sample task for testing",
        task_type="edit",
        version="1",
    )


@pytest.fixture
def manifest_with_supersedes() -> Dict[str, Any]:
    """Create manifest data with supersedes field."""
    return {
        "goal": "Superseding task",
        "taskType": "edit",
        "supersedes": [
            "manifests/task-050.manifest.json",
            "manifests/task-075.manifest.json",
        ],
    }


@pytest.fixture
def manifest_without_supersedes() -> Dict[str, Any]:
    """Create manifest data without supersedes field."""
    return {
        "goal": "Non-superseding task",
        "taskType": "create",
    }


@pytest.fixture
def manifest_with_all_file_types() -> Dict[str, Any]:
    """Create manifest data with all file type fields."""
    return {
        "goal": "Full file task",
        "taskType": "edit",
        "creatableFiles": ["src/new_module.py", "src/another_new.py"],
        "editableFiles": ["src/existing.py"],
        "readonlyFiles": ["src/dependency.py", "src/utils.py"],
    }


@pytest.fixture
def manifest_with_no_files() -> Dict[str, Any]:
    """Create manifest data without any file fields."""
    return {
        "goal": "No files task",
        "taskType": "snapshot",
    }


class TestCreateSupersedesEdges:
    """Tests for create_supersedes_edges function."""

    def test_returns_list_of_edges(
        self, manifest_with_supersedes: Dict[str, Any], sample_manifest_node: ManifestNode
    ) -> None:
        """Function returns a list of Edge objects."""
        result = create_supersedes_edges(manifest_with_supersedes, sample_manifest_node)

        assert isinstance(result, list)
        assert all(isinstance(edge, Edge) for edge in result)

    def test_creates_edge_for_each_superseded_manifest(
        self, manifest_with_supersedes: Dict[str, Any], sample_manifest_node: ManifestNode
    ) -> None:
        """Creates one SUPERSEDES edge for each item in supersedes array."""
        result = create_supersedes_edges(manifest_with_supersedes, sample_manifest_node)

        assert len(result) == 2

    def test_returns_empty_list_when_no_supersedes_field(
        self, manifest_without_supersedes: Dict[str, Any], sample_manifest_node: ManifestNode
    ) -> None:
        """Returns empty list when manifest has no supersedes field."""
        result = create_supersedes_edges(manifest_without_supersedes, sample_manifest_node)

        assert result == []

    def test_edge_source_id_is_manifest_node_id(
        self, manifest_with_supersedes: Dict[str, Any], sample_manifest_node: ManifestNode
    ) -> None:
        """Each edge source_id matches the manifest node ID."""
        result = create_supersedes_edges(manifest_with_supersedes, sample_manifest_node)

        for edge in result:
            assert edge.source_id == sample_manifest_node.id

    def test_edge_target_id_references_superseded_manifest_path(
        self, manifest_with_supersedes: Dict[str, Any], sample_manifest_node: ManifestNode
    ) -> None:
        """Each edge target_id references the superseded manifest path."""
        result = create_supersedes_edges(manifest_with_supersedes, sample_manifest_node)

        target_ids = {edge.target_id for edge in result}
        assert "manifest:manifests/task-050.manifest.json" in target_ids
        assert "manifest:manifests/task-075.manifest.json" in target_ids

    def test_edge_type_is_supersedes(
        self, manifest_with_supersedes: Dict[str, Any], sample_manifest_node: ManifestNode
    ) -> None:
        """Each edge has EdgeType.SUPERSEDES."""
        result = create_supersedes_edges(manifest_with_supersedes, sample_manifest_node)

        for edge in result:
            assert edge.edge_type == EdgeType.SUPERSEDES

    def test_returns_empty_list_when_supersedes_is_empty_array(
        self, sample_manifest_node: ManifestNode
    ) -> None:
        """Returns empty list when supersedes field is empty array."""
        manifest_data = {"goal": "Task", "supersedes": []}

        result = create_supersedes_edges(manifest_data, sample_manifest_node)

        assert result == []


class TestCreateFileEdges:
    """Tests for create_file_edges function."""

    def test_creates_creates_edges_for_creatable_files(
        self, manifest_with_all_file_types: Dict[str, Any], sample_manifest_node: ManifestNode
    ) -> None:
        """Creates CREATES edges for creatableFiles."""
        result = create_file_edges(manifest_with_all_file_types, sample_manifest_node)

        creates_edges = [e for e in result if e.edge_type == EdgeType.CREATES]
        assert len(creates_edges) == 2

        target_ids = {e.target_id for e in creates_edges}
        assert "file:src/new_module.py" in target_ids
        assert "file:src/another_new.py" in target_ids

    def test_creates_edits_edges_for_editable_files(
        self, manifest_with_all_file_types: Dict[str, Any], sample_manifest_node: ManifestNode
    ) -> None:
        """Creates EDITS edges for editableFiles."""
        result = create_file_edges(manifest_with_all_file_types, sample_manifest_node)

        edits_edges = [e for e in result if e.edge_type == EdgeType.EDITS]
        assert len(edits_edges) == 1
        assert edits_edges[0].target_id == "file:src/existing.py"

    def test_creates_reads_edges_for_readonly_files(
        self, manifest_with_all_file_types: Dict[str, Any], sample_manifest_node: ManifestNode
    ) -> None:
        """Creates READS edges for readonlyFiles."""
        result = create_file_edges(manifest_with_all_file_types, sample_manifest_node)

        reads_edges = [e for e in result if e.edge_type == EdgeType.READS]
        assert len(reads_edges) == 2

        target_ids = {e.target_id for e in reads_edges}
        assert "file:src/dependency.py" in target_ids
        assert "file:src/utils.py" in target_ids

    def test_returns_empty_list_when_no_file_fields(
        self, manifest_with_no_files: Dict[str, Any], sample_manifest_node: ManifestNode
    ) -> None:
        """Returns empty list when manifest has no file fields."""
        result = create_file_edges(manifest_with_no_files, sample_manifest_node)

        assert result == []

    def test_edge_source_id_is_manifest_node_id(
        self, manifest_with_all_file_types: Dict[str, Any], sample_manifest_node: ManifestNode
    ) -> None:
        """Each edge source_id matches the manifest node ID."""
        result = create_file_edges(manifest_with_all_file_types, sample_manifest_node)

        for edge in result:
            assert edge.source_id == sample_manifest_node.id

    def test_edge_target_id_is_file_path_formatted(
        self, sample_manifest_node: ManifestNode
    ) -> None:
        """Edge target_id is file path formatted as file:{path}."""
        manifest_data = {
            "goal": "Test",
            "creatableFiles": ["path/to/file.py"],
        }

        result = create_file_edges(manifest_data, sample_manifest_node)

        assert len(result) == 1
        assert result[0].target_id == "file:path/to/file.py"

    def test_creates_correct_edge_type_for_each_file_category(
        self, sample_manifest_node: ManifestNode
    ) -> None:
        """Verifies correct EdgeType is used for each file category."""
        manifest_data = {
            "goal": "Test",
            "creatableFiles": ["create.py"],
            "editableFiles": ["edit.py"],
            "readonlyFiles": ["read.py"],
        }

        result = create_file_edges(manifest_data, sample_manifest_node)

        edge_map = {e.target_id: e.edge_type for e in result}
        assert edge_map["file:create.py"] == EdgeType.CREATES
        assert edge_map["file:edit.py"] == EdgeType.EDITS
        assert edge_map["file:read.py"] == EdgeType.READS


class TestCreateArtifactEdges:
    """Tests for create_artifact_edges function."""

    def test_creates_defines_edge_from_file_to_artifact(
        self, sample_manifest_node: ManifestNode
    ) -> None:
        """Creates DEFINES edge from file to artifact."""
        artifact = {"name": "my_function", "type": "function"}
        file_path = "src/module.py"

        result = create_artifact_edges(artifact, file_path, sample_manifest_node)

        defines_edges = [e for e in result if e.edge_type == EdgeType.DEFINES]
        assert len(defines_edges) == 1
        assert defines_edges[0].source_id == f"file:{file_path}"

    def test_creates_declares_edge_from_manifest_to_artifact(
        self, sample_manifest_node: ManifestNode
    ) -> None:
        """Creates DECLARES edge from manifest to artifact."""
        artifact = {"name": "MyClass", "type": "class"}
        file_path = "src/module.py"

        result = create_artifact_edges(artifact, file_path, sample_manifest_node)

        declares_edges = [e for e in result if e.edge_type == EdgeType.DECLARES]
        assert len(declares_edges) == 1
        assert declares_edges[0].source_id == sample_manifest_node.id

    def test_creates_contains_edge_when_artifact_has_class_field(
        self, sample_manifest_node: ManifestNode
    ) -> None:
        """Creates CONTAINS edge when artifact has 'class' field (parent_class)."""
        artifact = {"name": "method_name", "type": "function", "class": "ParentClass"}
        file_path = "src/module.py"

        result = create_artifact_edges(artifact, file_path, sample_manifest_node)

        contains_edges = [e for e in result if e.edge_type == EdgeType.CONTAINS]
        assert len(contains_edges) == 1

    def test_contains_edge_connects_parent_to_child(
        self, sample_manifest_node: ManifestNode
    ) -> None:
        """CONTAINS edge connects parent class to child artifact."""
        artifact = {"name": "child_method", "type": "function", "class": "ParentClass"}
        file_path = "src/module.py"

        result = create_artifact_edges(artifact, file_path, sample_manifest_node)

        contains_edges = [e for e in result if e.edge_type == EdgeType.CONTAINS]
        assert len(contains_edges) == 1

        # Source should be parent class artifact
        assert "ParentClass" in contains_edges[0].source_id
        # Target should be child artifact
        assert "child_method" in contains_edges[0].target_id

    def test_returns_only_defines_and_declares_when_no_parent_class(
        self, sample_manifest_node: ManifestNode
    ) -> None:
        """Returns only DEFINES and DECLARES edges when no parent class."""
        artifact = {"name": "standalone_func", "type": "function"}
        file_path = "src/module.py"

        result = create_artifact_edges(artifact, file_path, sample_manifest_node)

        edge_types = {e.edge_type for e in result}
        assert edge_types == {EdgeType.DEFINES, EdgeType.DECLARES}
        assert len(result) == 2

    def test_edge_ids_are_unique(
        self, sample_manifest_node: ManifestNode
    ) -> None:
        """All edge IDs are unique."""
        artifact = {"name": "my_method", "type": "function", "class": "MyClass"}
        file_path = "src/module.py"

        result = create_artifact_edges(artifact, file_path, sample_manifest_node)

        edge_ids = [e.id for e in result]
        assert len(edge_ids) == len(set(edge_ids))

    def test_correct_edge_types_are_used(
        self, sample_manifest_node: ManifestNode
    ) -> None:
        """Verifies correct EdgeType enums are used for each relationship."""
        artifact = {"name": "test_artifact", "type": "class", "class": "Container"}
        file_path = "src/file.py"

        result = create_artifact_edges(artifact, file_path, sample_manifest_node)

        edge_types = {e.edge_type for e in result}
        assert EdgeType.DEFINES in edge_types
        assert EdgeType.DECLARES in edge_types
        assert EdgeType.CONTAINS in edge_types

    def test_declares_edge_target_is_artifact_id(
        self, sample_manifest_node: ManifestNode
    ) -> None:
        """DECLARES edge target_id references the artifact."""
        artifact = {"name": "my_artifact", "type": "function"}
        file_path = "src/module.py"

        result = create_artifact_edges(artifact, file_path, sample_manifest_node)

        declares_edges = [e for e in result if e.edge_type == EdgeType.DECLARES]
        assert len(declares_edges) == 1
        assert "my_artifact" in declares_edges[0].target_id

    def test_defines_edge_target_is_artifact_id(
        self, sample_manifest_node: ManifestNode
    ) -> None:
        """DEFINES edge target_id references the artifact."""
        artifact = {"name": "defined_func", "type": "function"}
        file_path = "src/module.py"

        result = create_artifact_edges(artifact, file_path, sample_manifest_node)

        defines_edges = [e for e in result if e.edge_type == EdgeType.DEFINES]
        assert len(defines_edges) == 1
        assert "defined_func" in defines_edges[0].target_id
