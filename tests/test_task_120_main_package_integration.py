"""Behavioral tests for Task 120: Main Package Integration.

This module tests that the main maid_runner package exports graph-related symbols
including KnowledgeGraph, KnowledgeGraphBuilder, NodeType, and EdgeType.

These tests verify:
- Each symbol can be imported from maid_runner
- Each symbol is in the __all__ list
- KnowledgeGraph is a class that can be instantiated
- KnowledgeGraphBuilder is a class that can be instantiated
- NodeType is an Enum with expected values
- EdgeType is an Enum with expected values
- New exports work alongside existing exports
"""

from enum import Enum


class TestMainPackageGraphExports:
    """Tests that verify graph symbols are importable from maid_runner."""

    def test_knowledgegraph_importable_from_maid_runner(self) -> None:
        """KnowledgeGraph should be importable from maid_runner."""
        from maid_runner import KnowledgeGraph

        assert KnowledgeGraph is not None

    def test_knowledgegraphbuilder_importable_from_maid_runner(self) -> None:
        """KnowledgeGraphBuilder should be importable from maid_runner."""
        from maid_runner import KnowledgeGraphBuilder

        assert KnowledgeGraphBuilder is not None

    def test_nodetype_importable_from_maid_runner(self) -> None:
        """NodeType should be importable from maid_runner."""
        from maid_runner import NodeType

        assert NodeType is not None

    def test_edgetype_importable_from_maid_runner(self) -> None:
        """EdgeType should be importable from maid_runner."""
        from maid_runner import EdgeType

        assert EdgeType is not None


class TestMainPackageAllList:
    """Tests that verify graph symbols are in the __all__ list."""

    def test_knowledgegraph_in_all(self) -> None:
        """KnowledgeGraph should be in __all__."""
        import maid_runner

        assert "KnowledgeGraph" in maid_runner.__all__

    def test_knowledgegraphbuilder_in_all(self) -> None:
        """KnowledgeGraphBuilder should be in __all__."""
        import maid_runner

        assert "KnowledgeGraphBuilder" in maid_runner.__all__

    def test_nodetype_in_all(self) -> None:
        """NodeType should be in __all__."""
        import maid_runner

        assert "NodeType" in maid_runner.__all__

    def test_edgetype_in_all(self) -> None:
        """EdgeType should be in __all__."""
        import maid_runner

        assert "EdgeType" in maid_runner.__all__


class TestGraphSymbolTypes:
    """Tests that verify the correct types of exported graph symbols."""

    def test_knowledgegraph_is_class(self) -> None:
        """KnowledgeGraph should be a class (type)."""
        from maid_runner import KnowledgeGraph

        assert isinstance(KnowledgeGraph, type)

    def test_knowledgegraphbuilder_is_class(self) -> None:
        """KnowledgeGraphBuilder should be a class (type)."""
        from maid_runner import KnowledgeGraphBuilder

        assert isinstance(KnowledgeGraphBuilder, type)

    def test_nodetype_is_enum(self) -> None:
        """NodeType should be an Enum class."""
        from maid_runner import NodeType

        assert issubclass(NodeType, Enum)

    def test_edgetype_is_enum(self) -> None:
        """EdgeType should be an Enum class."""
        from maid_runner import EdgeType

        assert issubclass(EdgeType, Enum)


class TestGraphSymbolBehavior:
    """Tests that verify exported graph symbols have expected behavior."""

    def test_knowledgegraph_instantiation(self) -> None:
        """KnowledgeGraph should be instantiable with no arguments."""
        from maid_runner import KnowledgeGraph

        graph = KnowledgeGraph()
        assert graph is not None
        assert graph.node_count == 0
        assert graph.edge_count == 0

    def test_knowledgegraphbuilder_instantiation(self, tmp_path) -> None:
        """KnowledgeGraphBuilder should be instantiable with a manifest directory."""
        from maid_runner import KnowledgeGraphBuilder

        builder = KnowledgeGraphBuilder(tmp_path)
        assert builder is not None

    def test_nodetype_has_expected_values(self) -> None:
        """NodeType should have expected enum values."""
        from maid_runner import NodeType

        assert hasattr(NodeType, "MANIFEST")
        assert hasattr(NodeType, "FILE")
        assert hasattr(NodeType, "ARTIFACT")
        assert hasattr(NodeType, "MODULE")
        assert NodeType.MANIFEST.value == "manifest"
        assert NodeType.FILE.value == "file"
        assert NodeType.ARTIFACT.value == "artifact"
        assert NodeType.MODULE.value == "module"

    def test_edgetype_has_expected_values(self) -> None:
        """EdgeType should have expected enum values."""
        from maid_runner import EdgeType

        assert hasattr(EdgeType, "SUPERSEDES")
        assert hasattr(EdgeType, "CREATES")
        assert hasattr(EdgeType, "EDITS")
        assert hasattr(EdgeType, "READS")
        assert hasattr(EdgeType, "DEFINES")
        assert hasattr(EdgeType, "DECLARES")
        assert EdgeType.SUPERSEDES.value == "supersedes"
        assert EdgeType.CREATES.value == "creates"
        assert EdgeType.EDITS.value == "edits"


class TestExistingExportsPreserved:
    """Tests that verify existing exports still work alongside new graph exports."""

    def test_version_still_importable(self) -> None:
        """__version__ should still be importable from maid_runner."""
        from maid_runner import __version__

        assert __version__ is not None
        assert isinstance(__version__, str)

    def test_alignmenterror_still_importable(self) -> None:
        """AlignmentError should still be importable from maid_runner."""
        from maid_runner import AlignmentError

        assert AlignmentError is not None
        assert issubclass(AlignmentError, Exception)

    def test_validate_schema_still_importable(self) -> None:
        """validate_schema should still be importable from maid_runner."""
        from maid_runner import validate_schema

        assert validate_schema is not None
        assert callable(validate_schema)

    def test_validate_with_ast_still_importable(self) -> None:
        """validate_with_ast should still be importable from maid_runner."""
        from maid_runner import validate_with_ast

        assert validate_with_ast is not None
        assert callable(validate_with_ast)

    def test_generate_snapshot_still_importable(self) -> None:
        """generate_snapshot should still be importable from maid_runner."""
        from maid_runner import generate_snapshot

        assert generate_snapshot is not None
        assert callable(generate_snapshot)

    def test_all_existing_exports_in_all(self) -> None:
        """All existing exports should still be in __all__."""
        import maid_runner

        existing_exports = [
            "__version__",
            "AlignmentError",
            "collect_behavioral_artifacts",
            "discover_related_manifests",
            "validate_schema",
            "validate_with_ast",
            "generate_snapshot",
        ]
        for export in existing_exports:
            assert export in maid_runner.__all__, f"Missing existing export: {export}"


class TestCombinedUsage:
    """Tests that verify graph symbols can be used together with existing API."""

    def test_can_import_all_symbols_together(self) -> None:
        """All symbols (new and existing) should be importable in single import."""
        from maid_runner import (
            __version__,
            AlignmentError,
            EdgeType,
            KnowledgeGraph,
            KnowledgeGraphBuilder,
            NodeType,
            generate_snapshot,
            validate_schema,
            validate_with_ast,
        )

        # Verify all imports are not None
        assert __version__ is not None
        assert AlignmentError is not None
        assert validate_schema is not None
        assert validate_with_ast is not None
        assert generate_snapshot is not None
        assert KnowledgeGraph is not None
        assert KnowledgeGraphBuilder is not None
        assert NodeType is not None
        assert EdgeType is not None

    def test_maid_runner_module_has_all_graph_attributes(self) -> None:
        """maid_runner module should have all graph attributes accessible."""
        import maid_runner

        assert hasattr(maid_runner, "KnowledgeGraph")
        assert hasattr(maid_runner, "KnowledgeGraphBuilder")
        assert hasattr(maid_runner, "NodeType")
        assert hasattr(maid_runner, "EdgeType")

    def test_exported_graph_symbols_are_same_as_graph_package(self) -> None:
        """Symbols exported from maid_runner should be same as from maid_runner.graph."""
        from maid_runner import EdgeType, KnowledgeGraph, KnowledgeGraphBuilder, NodeType
        from maid_runner.graph import (
            EdgeType as GraphEdgeType,
            KnowledgeGraph as GraphKnowledgeGraph,
            KnowledgeGraphBuilder as GraphKnowledgeGraphBuilder,
            NodeType as GraphNodeType,
        )

        assert KnowledgeGraph is GraphKnowledgeGraph
        assert KnowledgeGraphBuilder is GraphKnowledgeGraphBuilder
        assert NodeType is GraphNodeType
        assert EdgeType is GraphEdgeType
