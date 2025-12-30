"""Behavioral tests for Task 119: Graph Package Init.

This module tests that the graph package exports a complete public API
including KnowledgeGraph and all exporter functions.
"""


class TestGraphPackageExports:
    """Tests that verify the graph package exports required symbols."""

    def test_knowledgegraph_importable_from_package(self) -> None:
        """KnowledgeGraph should be importable from maid_runner.graph."""
        from maid_runner.graph import KnowledgeGraph

        assert KnowledgeGraph is not None

    def test_knowledgegraph_is_class(self) -> None:
        """KnowledgeGraph should be a class that can be instantiated."""
        from maid_runner.graph import KnowledgeGraph

        assert isinstance(KnowledgeGraph, type)

    def test_knowledgegraph_instantiation(self) -> None:
        """KnowledgeGraph should be instantiable with no arguments."""
        from maid_runner.graph import KnowledgeGraph

        graph = KnowledgeGraph()
        assert graph is not None
        assert graph.node_count == 0
        assert graph.edge_count == 0

    def test_export_json_importable(self) -> None:
        """export_json should be importable from maid_runner.graph."""
        from maid_runner.graph import export_json

        assert export_json is not None

    def test_export_json_is_callable(self) -> None:
        """export_json should be a callable function."""
        from maid_runner.graph import export_json

        assert callable(export_json)

    def test_export_dot_importable(self) -> None:
        """export_dot should be importable from maid_runner.graph."""
        from maid_runner.graph import export_dot

        assert export_dot is not None

    def test_export_dot_is_callable(self) -> None:
        """export_dot should be a callable function."""
        from maid_runner.graph import export_dot

        assert callable(export_dot)

    def test_export_graphml_importable(self) -> None:
        """export_graphml should be importable from maid_runner.graph."""
        from maid_runner.graph import export_graphml

        assert export_graphml is not None

    def test_export_graphml_is_callable(self) -> None:
        """export_graphml should be a callable function."""
        from maid_runner.graph import export_graphml

        assert callable(export_graphml)

    def test_graph_to_dict_importable(self) -> None:
        """graph_to_dict should be importable from maid_runner.graph."""
        from maid_runner.graph import graph_to_dict

        assert graph_to_dict is not None

    def test_graph_to_dict_is_callable(self) -> None:
        """graph_to_dict should be a callable function."""
        from maid_runner.graph import graph_to_dict

        assert callable(graph_to_dict)

    def test_graph_to_dot_importable(self) -> None:
        """graph_to_dot should be importable from maid_runner.graph."""
        from maid_runner.graph import graph_to_dot

        assert graph_to_dot is not None

    def test_graph_to_dot_is_callable(self) -> None:
        """graph_to_dot should be a callable function."""
        from maid_runner.graph import graph_to_dot

        assert callable(graph_to_dot)

    def test_graph_to_graphml_importable(self) -> None:
        """graph_to_graphml should be importable from maid_runner.graph."""
        from maid_runner.graph import graph_to_graphml

        assert graph_to_graphml is not None

    def test_graph_to_graphml_is_callable(self) -> None:
        """graph_to_graphml should be a callable function."""
        from maid_runner.graph import graph_to_graphml

        assert callable(graph_to_graphml)


class TestGraphPackageAllList:
    """Tests that verify the __all__ list contains required symbols."""

    def test_knowledgegraph_in_all(self) -> None:
        """KnowledgeGraph should be in __all__."""
        import maid_runner.graph as graph_module

        assert "KnowledgeGraph" in graph_module.__all__

    def test_export_json_in_all(self) -> None:
        """export_json should be in __all__."""
        import maid_runner.graph as graph_module

        assert "export_json" in graph_module.__all__

    def test_export_dot_in_all(self) -> None:
        """export_dot should be in __all__."""
        import maid_runner.graph as graph_module

        assert "export_dot" in graph_module.__all__

    def test_export_graphml_in_all(self) -> None:
        """export_graphml should be in __all__."""
        import maid_runner.graph as graph_module

        assert "export_graphml" in graph_module.__all__

    def test_graph_to_dict_in_all(self) -> None:
        """graph_to_dict should be in __all__."""
        import maid_runner.graph as graph_module

        assert "graph_to_dict" in graph_module.__all__

    def test_graph_to_dot_in_all(self) -> None:
        """graph_to_dot should be in __all__."""
        import maid_runner.graph as graph_module

        assert "graph_to_dot" in graph_module.__all__

    def test_graph_to_graphml_in_all(self) -> None:
        """graph_to_graphml should be in __all__."""
        import maid_runner.graph as graph_module

        assert "graph_to_graphml" in graph_module.__all__


class TestGraphPackageBehavior:
    """Tests that verify the exported functions work correctly when used."""

    def test_graph_to_dict_returns_dict_with_nodes_and_edges(self) -> None:
        """graph_to_dict should return a dict with nodes and edges keys."""
        from maid_runner.graph import KnowledgeGraph, graph_to_dict

        graph = KnowledgeGraph()
        result = graph_to_dict(graph)

        assert isinstance(result, dict)
        assert "nodes" in result
        assert "edges" in result
        assert isinstance(result["nodes"], list)
        assert isinstance(result["edges"], list)

    def test_graph_to_dot_returns_string(self) -> None:
        """graph_to_dot should return a string in DOT format."""
        from maid_runner.graph import KnowledgeGraph, graph_to_dot

        graph = KnowledgeGraph()
        result = graph_to_dot(graph)

        assert isinstance(result, str)
        assert "digraph G" in result

    def test_graph_to_graphml_returns_string(self) -> None:
        """graph_to_graphml should return a string in GraphML format."""
        from maid_runner.graph import KnowledgeGraph, graph_to_graphml

        graph = KnowledgeGraph()
        result = graph_to_graphml(graph)

        assert isinstance(result, str)
        assert '<?xml version="1.0"' in result
        assert "graphml" in result

    def test_export_json_creates_file(self, tmp_path) -> None:
        """export_json should create a JSON file at the specified path."""
        from maid_runner.graph import KnowledgeGraph, export_json

        graph = KnowledgeGraph()
        output_file = tmp_path / "test_graph.json"

        export_json(graph, output_file)

        assert output_file.exists()
        content = output_file.read_text()
        assert '"nodes"' in content
        assert '"edges"' in content

    def test_export_dot_creates_file(self, tmp_path) -> None:
        """export_dot should create a DOT file at the specified path."""
        from maid_runner.graph import KnowledgeGraph, export_dot

        graph = KnowledgeGraph()
        output_file = tmp_path / "test_graph.dot"

        export_dot(graph, output_file)

        assert output_file.exists()
        content = output_file.read_text()
        assert "digraph G" in content

    def test_export_graphml_creates_file(self, tmp_path) -> None:
        """export_graphml should create a GraphML file at the specified path."""
        from maid_runner.graph import KnowledgeGraph, export_graphml

        graph = KnowledgeGraph()
        output_file = tmp_path / "test_graph.graphml"

        export_graphml(graph, output_file)

        assert output_file.exists()
        content = output_file.read_text()
        assert "graphml" in content


class TestCompletePublicAPI:
    """Tests that verify the package provides a complete public API."""

    def test_all_expected_exports_present(self) -> None:
        """All expected exports from task-119 should be present."""
        import maid_runner.graph as graph_module

        expected_exports = [
            "KnowledgeGraph",
            "export_json",
            "export_dot",
            "export_graphml",
            "graph_to_dict",
            "graph_to_dot",
            "graph_to_graphml",
        ]

        for export in expected_exports:
            assert hasattr(graph_module, export), f"Missing export: {export}"
            assert export in graph_module.__all__, f"Missing from __all__: {export}"

    def test_exports_are_functional(self) -> None:
        """All exported symbols should be functional (classes/functions)."""
        from maid_runner.graph import (
            KnowledgeGraph,
            export_json,
            export_dot,
            export_graphml,
            graph_to_dict,
            graph_to_dot,
            graph_to_graphml,
        )

        # KnowledgeGraph should be a class
        assert isinstance(KnowledgeGraph, type)

        # All others should be callable
        assert callable(export_json)
        assert callable(export_dot)
        assert callable(export_graphml)
        assert callable(graph_to_dict)
        assert callable(graph_to_dot)
        assert callable(graph_to_graphml)
