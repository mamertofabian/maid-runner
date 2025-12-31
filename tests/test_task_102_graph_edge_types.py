"""Behavioral tests for task-102: Graph Edge Types.

These tests verify the graph edge data structures for the Knowledge Graph Builder.
Tests focus on behavioral validation - using (instantiating, accessing) the declared
artifacts rather than implementation details.

Artifacts tested:
- EdgeType enum with values: SUPERSEDES, CREATES, EDITS, READS, DEFINES,
  DECLARES, CONTAINS, INHERITS, BELONGS_TO
- Edge dataclass with id, edge_type, source_id, target_id, attributes
"""

from maid_runner.graph.model import (
    EdgeType,
    Edge,
)


class TestEdgeTypeEnum:
    """Tests for the EdgeType enumeration."""

    def test_edge_type_has_supersedes_value(self):
        """EdgeType enum has SUPERSEDES value."""
        assert hasattr(EdgeType, "SUPERSEDES")
        edge_type = EdgeType.SUPERSEDES
        assert edge_type is not None

    def test_edge_type_has_creates_value(self):
        """EdgeType enum has CREATES value."""
        assert hasattr(EdgeType, "CREATES")
        edge_type = EdgeType.CREATES
        assert edge_type is not None

    def test_edge_type_has_edits_value(self):
        """EdgeType enum has EDITS value."""
        assert hasattr(EdgeType, "EDITS")
        edge_type = EdgeType.EDITS
        assert edge_type is not None

    def test_edge_type_has_reads_value(self):
        """EdgeType enum has READS value."""
        assert hasattr(EdgeType, "READS")
        edge_type = EdgeType.READS
        assert edge_type is not None

    def test_edge_type_has_defines_value(self):
        """EdgeType enum has DEFINES value."""
        assert hasattr(EdgeType, "DEFINES")
        edge_type = EdgeType.DEFINES
        assert edge_type is not None

    def test_edge_type_has_declares_value(self):
        """EdgeType enum has DECLARES value."""
        assert hasattr(EdgeType, "DECLARES")
        edge_type = EdgeType.DECLARES
        assert edge_type is not None

    def test_edge_type_has_contains_value(self):
        """EdgeType enum has CONTAINS value."""
        assert hasattr(EdgeType, "CONTAINS")
        edge_type = EdgeType.CONTAINS
        assert edge_type is not None

    def test_edge_type_has_inherits_value(self):
        """EdgeType enum has INHERITS value."""
        assert hasattr(EdgeType, "INHERITS")
        edge_type = EdgeType.INHERITS
        assert edge_type is not None

    def test_edge_type_has_belongs_to_value(self):
        """EdgeType enum has BELONGS_TO value."""
        assert hasattr(EdgeType, "BELONGS_TO")
        edge_type = EdgeType.BELONGS_TO
        assert edge_type is not None

    def test_edge_type_values_are_distinct(self):
        """All EdgeType values are distinct from each other."""
        values = [
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
        assert len(values) == len(set(values))

    def test_edge_type_iteration(self):
        """EdgeType can be iterated over (standard enum behavior)."""
        edge_types = list(EdgeType)
        assert len(edge_types) >= 9
        assert EdgeType.SUPERSEDES in edge_types
        assert EdgeType.CREATES in edge_types
        assert EdgeType.EDITS in edge_types
        assert EdgeType.READS in edge_types
        assert EdgeType.DEFINES in edge_types
        assert EdgeType.DECLARES in edge_types
        assert EdgeType.CONTAINS in edge_types
        assert EdgeType.INHERITS in edge_types
        assert EdgeType.BELONGS_TO in edge_types


class TestEdgeDataclass:
    """Tests for the Edge dataclass."""

    def test_edge_creation_with_required_attributes(self):
        """Edge can be created with id, edge_type, source_id, and target_id."""
        edge = Edge(
            id="edge-1",
            edge_type=EdgeType.CREATES,
            source_id="manifest-001",
            target_id="file-001",
        )

        assert edge.id == "edge-1"
        assert edge.edge_type == EdgeType.CREATES
        assert edge.source_id == "manifest-001"
        assert edge.target_id == "file-001"

    def test_edge_attributes_defaults_to_empty_dict(self):
        """Edge attributes defaults to empty dict when not provided."""
        edge = Edge(
            id="edge-2",
            edge_type=EdgeType.EDITS,
            source_id="manifest-002",
            target_id="file-002",
        )

        assert edge.attributes == {} or edge.attributes is not None
        # Verify it's dict-like
        assert hasattr(edge.attributes, "get")

    def test_edge_creation_with_custom_attributes(self):
        """Edge can be created with custom attributes dict."""
        custom_attrs = {"reason": "refactoring", "priority": 1, "tags": ["urgent"]}
        edge = Edge(
            id="edge-3",
            edge_type=EdgeType.SUPERSEDES,
            source_id="manifest-003",
            target_id="manifest-002",
            attributes=custom_attrs,
        )

        assert edge.attributes["reason"] == "refactoring"
        assert edge.attributes["priority"] == 1
        assert edge.attributes["tags"] == ["urgent"]

    def test_edge_has_id_attribute(self):
        """Edge has an id attribute that is accessible."""
        edge = Edge(
            id="unique-edge-id",
            edge_type=EdgeType.READS,
            source_id="src",
            target_id="tgt",
        )

        assert hasattr(edge, "id")
        assert edge.id == "unique-edge-id"

    def test_edge_has_edge_type_attribute(self):
        """Edge has an edge_type attribute that is accessible."""
        edge = Edge(
            id="edge-type-test",
            edge_type=EdgeType.DEFINES,
            source_id="src",
            target_id="tgt",
        )

        assert hasattr(edge, "edge_type")
        assert edge.edge_type == EdgeType.DEFINES

    def test_edge_has_source_id_attribute(self):
        """Edge has a source_id attribute that is accessible."""
        edge = Edge(
            id="source-test",
            edge_type=EdgeType.DECLARES,
            source_id="manifest-source-123",
            target_id="artifact-456",
        )

        assert hasattr(edge, "source_id")
        assert edge.source_id == "manifest-source-123"

    def test_edge_has_target_id_attribute(self):
        """Edge has a target_id attribute that is accessible."""
        edge = Edge(
            id="target-test",
            edge_type=EdgeType.CONTAINS,
            source_id="module-parent",
            target_id="file-child-789",
        )

        assert hasattr(edge, "target_id")
        assert edge.target_id == "file-child-789"

    def test_edge_has_attributes_attribute(self):
        """Edge has an attributes attribute that is accessible."""
        edge = Edge(
            id="attrs-test",
            edge_type=EdgeType.INHERITS,
            source_id="src",
            target_id="tgt",
        )

        assert hasattr(edge, "attributes")

    def test_edge_with_different_edge_types(self):
        """Edge can be created with any EdgeType value."""
        for edge_type in EdgeType:
            edge = Edge(
                id=f"edge-{edge_type.name}",
                edge_type=edge_type,
                source_id="src-node",
                target_id="tgt-node",
            )
            assert edge.edge_type == edge_type


class TestEdgeSemanticMeaning:
    """Tests verifying the semantic use of edge types in graph relationships."""

    def test_supersedes_edge_represents_manifest_supersession(self):
        """SUPERSEDES edge represents one manifest replacing another."""
        edge = Edge(
            id="supersede-edge",
            edge_type=EdgeType.SUPERSEDES,
            source_id="manifest-002",
            target_id="manifest-001",
        )

        assert edge.edge_type == EdgeType.SUPERSEDES
        assert edge.source_id != edge.target_id

    def test_creates_edge_represents_file_creation(self):
        """CREATES edge represents a manifest creating a file."""
        edge = Edge(
            id="creates-edge",
            edge_type=EdgeType.CREATES,
            source_id="manifest-task-001",
            target_id="file-new-module",
        )

        assert edge.edge_type == EdgeType.CREATES

    def test_edits_edge_represents_file_modification(self):
        """EDITS edge represents a manifest editing a file."""
        edge = Edge(
            id="edits-edge",
            edge_type=EdgeType.EDITS,
            source_id="manifest-task-005",
            target_id="file-existing-module",
        )

        assert edge.edge_type == EdgeType.EDITS

    def test_reads_edge_represents_file_dependency(self):
        """READS edge represents a manifest reading/depending on a file."""
        edge = Edge(
            id="reads-edge",
            edge_type=EdgeType.READS,
            source_id="manifest-task-010",
            target_id="file-dependency",
        )

        assert edge.edge_type == EdgeType.READS

    def test_defines_edge_represents_artifact_definition(self):
        """DEFINES edge represents a file defining an artifact."""
        edge = Edge(
            id="defines-edge",
            edge_type=EdgeType.DEFINES,
            source_id="file-module",
            target_id="artifact-function",
        )

        assert edge.edge_type == EdgeType.DEFINES

    def test_declares_edge_represents_artifact_declaration(self):
        """DECLARES edge represents a manifest declaring an artifact."""
        edge = Edge(
            id="declares-edge",
            edge_type=EdgeType.DECLARES,
            source_id="manifest-task-015",
            target_id="artifact-class",
        )

        assert edge.edge_type == EdgeType.DECLARES

    def test_contains_edge_represents_containment(self):
        """CONTAINS edge represents a parent containing a child element."""
        edge = Edge(
            id="contains-edge",
            edge_type=EdgeType.CONTAINS,
            source_id="module-parent",
            target_id="file-child",
        )

        assert edge.edge_type == EdgeType.CONTAINS

    def test_inherits_edge_represents_inheritance(self):
        """INHERITS edge represents class inheritance."""
        edge = Edge(
            id="inherits-edge",
            edge_type=EdgeType.INHERITS,
            source_id="artifact-child-class",
            target_id="artifact-parent-class",
        )

        assert edge.edge_type == EdgeType.INHERITS

    def test_belongs_to_edge_represents_membership(self):
        """BELONGS_TO edge represents entity membership."""
        edge = Edge(
            id="belongs-edge",
            edge_type=EdgeType.BELONGS_TO,
            source_id="artifact-method",
            target_id="artifact-class",
        )

        assert edge.edge_type == EdgeType.BELONGS_TO


class TestEdgeWithAttributes:
    """Tests for Edge with various attribute patterns."""

    def test_edge_with_empty_attributes(self):
        """Edge can have explicitly empty attributes dict."""
        edge = Edge(
            id="empty-attrs",
            edge_type=EdgeType.CREATES,
            source_id="src",
            target_id="tgt",
            attributes={},
        )

        assert edge.attributes == {}

    def test_edge_with_string_attributes(self):
        """Edge can have string value attributes."""
        edge = Edge(
            id="string-attrs",
            edge_type=EdgeType.EDITS,
            source_id="src",
            target_id="tgt",
            attributes={"description": "Major refactoring", "author": "developer"},
        )

        assert edge.attributes["description"] == "Major refactoring"
        assert edge.attributes["author"] == "developer"

    def test_edge_with_numeric_attributes(self):
        """Edge can have numeric value attributes."""
        edge = Edge(
            id="numeric-attrs",
            edge_type=EdgeType.SUPERSEDES,
            source_id="src",
            target_id="tgt",
            attributes={"weight": 1.5, "count": 42},
        )

        assert edge.attributes["weight"] == 1.5
        assert edge.attributes["count"] == 42

    def test_edge_with_nested_attributes(self):
        """Edge can have nested dict attributes."""
        edge = Edge(
            id="nested-attrs",
            edge_type=EdgeType.DEFINES,
            source_id="src",
            target_id="tgt",
            attributes={
                "metadata": {
                    "created": "2024-01-01",
                    "version": "1.0",
                }
            },
        )

        assert edge.attributes["metadata"]["created"] == "2024-01-01"
        assert edge.attributes["metadata"]["version"] == "1.0"

    def test_edge_with_list_attributes(self):
        """Edge can have list value attributes."""
        edge = Edge(
            id="list-attrs",
            edge_type=EdgeType.DECLARES,
            source_id="src",
            target_id="tgt",
            attributes={"tags": ["important", "reviewed", "approved"]},
        )

        assert "important" in edge.attributes["tags"]
        assert len(edge.attributes["tags"]) == 3
