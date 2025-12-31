"""Behavioral tests for Task 110: Cycle Detection.

Tests for the cycle detection functions in the query module:
- find_cycles: Find all cycles (circular dependencies) in the graph
- is_acyclic: Check if the graph has no cycles
"""

import pytest

from maid_runner.graph.model import (
    ArtifactNode,
    Edge,
    EdgeType,
    KnowledgeGraph,
    Node,
)
from maid_runner.graph.query import (
    find_cycles,
    is_acyclic,
)


# =============================================================================
# Fixtures
# =============================================================================


@pytest.fixture
def empty_graph() -> KnowledgeGraph:
    """Create an empty knowledge graph."""
    return KnowledgeGraph()


@pytest.fixture
def single_node_graph() -> KnowledgeGraph:
    """Create a graph with a single node and no edges."""
    graph = KnowledgeGraph()

    node = ArtifactNode(
        id="artifact-001",
        name="standalone_function",
        artifact_type="function",
    )
    graph.add_node(node)

    return graph


@pytest.fixture
def self_loop_graph() -> KnowledgeGraph:
    """Create a graph with a self-referencing node (A -> A).

    Structure:
    artifact-A -> artifact-A (self-loop)
    """
    graph = KnowledgeGraph()

    node_a = ArtifactNode(
        id="artifact-A",
        name="SelfReferencer",
        artifact_type="class",
    )
    graph.add_node(node_a)

    # Self-loop edge
    edge = Edge(
        id="edge-001",
        edge_type=EdgeType.CONTAINS,
        source_id="artifact-A",
        target_id="artifact-A",
    )
    graph.add_edge(edge)

    return graph


@pytest.fixture
def simple_cycle_graph() -> KnowledgeGraph:
    """Create a graph with a simple two-node cycle (A -> B -> A).

    Structure:
    artifact-A -> artifact-B -> artifact-A
    """
    graph = KnowledgeGraph()

    node_a = ArtifactNode(
        id="artifact-A",
        name="ModuleA",
        artifact_type="class",
    )
    node_b = ArtifactNode(
        id="artifact-B",
        name="ModuleB",
        artifact_type="class",
    )

    graph.add_node(node_a)
    graph.add_node(node_b)

    # A -> B
    edge1 = Edge(
        id="edge-001",
        edge_type=EdgeType.CONTAINS,
        source_id="artifact-A",
        target_id="artifact-B",
    )
    # B -> A (creates cycle)
    edge2 = Edge(
        id="edge-002",
        edge_type=EdgeType.CONTAINS,
        source_id="artifact-B",
        target_id="artifact-A",
    )

    graph.add_edge(edge1)
    graph.add_edge(edge2)

    return graph


@pytest.fixture
def larger_cycle_graph() -> KnowledgeGraph:
    """Create a graph with a larger cycle (A -> B -> C -> A).

    Structure:
    artifact-A -> artifact-B -> artifact-C -> artifact-A
    """
    graph = KnowledgeGraph()

    node_a = ArtifactNode(
        id="artifact-A",
        name="ModuleA",
        artifact_type="class",
    )
    node_b = ArtifactNode(
        id="artifact-B",
        name="ModuleB",
        artifact_type="class",
    )
    node_c = ArtifactNode(
        id="artifact-C",
        name="ModuleC",
        artifact_type="class",
    )

    graph.add_node(node_a)
    graph.add_node(node_b)
    graph.add_node(node_c)

    # A -> B -> C -> A
    edge1 = Edge(
        id="edge-001",
        edge_type=EdgeType.CONTAINS,
        source_id="artifact-A",
        target_id="artifact-B",
    )
    edge2 = Edge(
        id="edge-002",
        edge_type=EdgeType.CONTAINS,
        source_id="artifact-B",
        target_id="artifact-C",
    )
    edge3 = Edge(
        id="edge-003",
        edge_type=EdgeType.CONTAINS,
        source_id="artifact-C",
        target_id="artifact-A",
    )

    graph.add_edge(edge1)
    graph.add_edge(edge2)
    graph.add_edge(edge3)

    return graph


@pytest.fixture
def acyclic_linear_graph() -> KnowledgeGraph:
    """Create an acyclic linear chain (A -> B -> C).

    Structure:
    artifact-A -> artifact-B -> artifact-C (no cycle)
    """
    graph = KnowledgeGraph()

    node_a = ArtifactNode(
        id="artifact-A",
        name="ModuleA",
        artifact_type="class",
    )
    node_b = ArtifactNode(
        id="artifact-B",
        name="ModuleB",
        artifact_type="class",
    )
    node_c = ArtifactNode(
        id="artifact-C",
        name="ModuleC",
        artifact_type="class",
    )

    graph.add_node(node_a)
    graph.add_node(node_b)
    graph.add_node(node_c)

    # Linear chain: A -> B -> C
    edge1 = Edge(
        id="edge-001",
        edge_type=EdgeType.CONTAINS,
        source_id="artifact-A",
        target_id="artifact-B",
    )
    edge2 = Edge(
        id="edge-002",
        edge_type=EdgeType.CONTAINS,
        source_id="artifact-B",
        target_id="artifact-C",
    )

    graph.add_edge(edge1)
    graph.add_edge(edge2)

    return graph


@pytest.fixture
def acyclic_tree_graph() -> KnowledgeGraph:
    """Create an acyclic tree structure.

    Structure:
           artifact-A
          /         \\
    artifact-B    artifact-C
        |
    artifact-D
    """
    graph = KnowledgeGraph()

    node_a = ArtifactNode(
        id="artifact-A",
        name="Root",
        artifact_type="class",
    )
    node_b = ArtifactNode(
        id="artifact-B",
        name="ChildB",
        artifact_type="class",
    )
    node_c = ArtifactNode(
        id="artifact-C",
        name="ChildC",
        artifact_type="class",
    )
    node_d = ArtifactNode(
        id="artifact-D",
        name="GrandchildD",
        artifact_type="class",
    )

    graph.add_node(node_a)
    graph.add_node(node_b)
    graph.add_node(node_c)
    graph.add_node(node_d)

    # A -> B, A -> C, B -> D
    edge1 = Edge(
        id="edge-001",
        edge_type=EdgeType.CONTAINS,
        source_id="artifact-A",
        target_id="artifact-B",
    )
    edge2 = Edge(
        id="edge-002",
        edge_type=EdgeType.CONTAINS,
        source_id="artifact-A",
        target_id="artifact-C",
    )
    edge3 = Edge(
        id="edge-003",
        edge_type=EdgeType.CONTAINS,
        source_id="artifact-B",
        target_id="artifact-D",
    )

    graph.add_edge(edge1)
    graph.add_edge(edge2)
    graph.add_edge(edge3)

    return graph


@pytest.fixture
def multiple_cycles_graph() -> KnowledgeGraph:
    """Create a graph with multiple independent cycles.

    Structure:
    Cycle 1: artifact-A -> artifact-B -> artifact-A
    Cycle 2: artifact-C -> artifact-D -> artifact-C
    (Two separate disconnected cycles)
    """
    graph = KnowledgeGraph()

    # Cycle 1 nodes
    node_a = ArtifactNode(
        id="artifact-A",
        name="ModuleA",
        artifact_type="class",
    )
    node_b = ArtifactNode(
        id="artifact-B",
        name="ModuleB",
        artifact_type="class",
    )

    # Cycle 2 nodes
    node_c = ArtifactNode(
        id="artifact-C",
        name="ModuleC",
        artifact_type="class",
    )
    node_d = ArtifactNode(
        id="artifact-D",
        name="ModuleD",
        artifact_type="class",
    )

    graph.add_node(node_a)
    graph.add_node(node_b)
    graph.add_node(node_c)
    graph.add_node(node_d)

    # Cycle 1: A -> B -> A
    edge1 = Edge(
        id="edge-001",
        edge_type=EdgeType.CONTAINS,
        source_id="artifact-A",
        target_id="artifact-B",
    )
    edge2 = Edge(
        id="edge-002",
        edge_type=EdgeType.CONTAINS,
        source_id="artifact-B",
        target_id="artifact-A",
    )

    # Cycle 2: C -> D -> C
    edge3 = Edge(
        id="edge-003",
        edge_type=EdgeType.CONTAINS,
        source_id="artifact-C",
        target_id="artifact-D",
    )
    edge4 = Edge(
        id="edge-004",
        edge_type=EdgeType.CONTAINS,
        source_id="artifact-D",
        target_id="artifact-C",
    )

    graph.add_edge(edge1)
    graph.add_edge(edge2)
    graph.add_edge(edge3)
    graph.add_edge(edge4)

    return graph


@pytest.fixture
def disconnected_with_cycle_graph() -> KnowledgeGraph:
    """Create a graph with disconnected components, one with a cycle.

    Structure:
    Component 1 (acyclic): artifact-A -> artifact-B
    Component 2 (cyclic): artifact-C -> artifact-D -> artifact-C
    """
    graph = KnowledgeGraph()

    # Acyclic component
    node_a = ArtifactNode(
        id="artifact-A",
        name="ModuleA",
        artifact_type="class",
    )
    node_b = ArtifactNode(
        id="artifact-B",
        name="ModuleB",
        artifact_type="class",
    )

    # Cyclic component
    node_c = ArtifactNode(
        id="artifact-C",
        name="ModuleC",
        artifact_type="class",
    )
    node_d = ArtifactNode(
        id="artifact-D",
        name="ModuleD",
        artifact_type="class",
    )

    graph.add_node(node_a)
    graph.add_node(node_b)
    graph.add_node(node_c)
    graph.add_node(node_d)

    # Acyclic: A -> B (no back edge)
    edge1 = Edge(
        id="edge-001",
        edge_type=EdgeType.CONTAINS,
        source_id="artifact-A",
        target_id="artifact-B",
    )

    # Cyclic: C -> D -> C
    edge2 = Edge(
        id="edge-002",
        edge_type=EdgeType.CONTAINS,
        source_id="artifact-C",
        target_id="artifact-D",
    )
    edge3 = Edge(
        id="edge-003",
        edge_type=EdgeType.CONTAINS,
        source_id="artifact-D",
        target_id="artifact-C",
    )

    graph.add_edge(edge1)
    graph.add_edge(edge2)
    graph.add_edge(edge3)

    return graph


# =============================================================================
# Tests for find_cycles
# =============================================================================


class TestFindCycles:
    """Tests for the find_cycles function."""

    def test_returns_list(self, empty_graph: KnowledgeGraph) -> None:
        """Test that find_cycles returns a list."""
        result = find_cycles(empty_graph)

        assert isinstance(result, list)

    def test_returns_empty_list_for_empty_graph(
        self, empty_graph: KnowledgeGraph
    ) -> None:
        """Test that find_cycles returns empty list for empty graph."""
        result = find_cycles(empty_graph)

        assert result == []

    def test_returns_empty_list_for_single_node_no_edges(
        self, single_node_graph: KnowledgeGraph
    ) -> None:
        """Test that find_cycles returns empty list for single node with no edges."""
        result = find_cycles(single_node_graph)

        assert result == []

    def test_finds_self_loop(self, self_loop_graph: KnowledgeGraph) -> None:
        """Test that find_cycles detects self-loops (A -> A)."""
        result = find_cycles(self_loop_graph)

        assert len(result) >= 1
        # At least one cycle should contain artifact-A
        cycle_node_ids = []
        for cycle in result:
            cycle_node_ids.extend([node.id for node in cycle])
        assert "artifact-A" in cycle_node_ids

    def test_finds_simple_cycle(self, simple_cycle_graph: KnowledgeGraph) -> None:
        """Test that find_cycles detects simple two-node cycle (A -> B -> A)."""
        result = find_cycles(simple_cycle_graph)

        assert len(result) >= 1
        # Should find a cycle containing A and B
        cycle_node_ids = []
        for cycle in result:
            cycle_node_ids.extend([node.id for node in cycle])
        assert "artifact-A" in cycle_node_ids
        assert "artifact-B" in cycle_node_ids

    def test_finds_larger_cycle(self, larger_cycle_graph: KnowledgeGraph) -> None:
        """Test that find_cycles detects larger cycle (A -> B -> C -> A)."""
        result = find_cycles(larger_cycle_graph)

        assert len(result) >= 1
        # Should find a cycle containing A, B, and C
        cycle_node_ids = []
        for cycle in result:
            cycle_node_ids.extend([node.id for node in cycle])
        assert "artifact-A" in cycle_node_ids
        assert "artifact-B" in cycle_node_ids
        assert "artifact-C" in cycle_node_ids

    def test_returns_empty_list_for_acyclic_graph(
        self, acyclic_linear_graph: KnowledgeGraph
    ) -> None:
        """Test that find_cycles returns empty list for acyclic linear chain."""
        result = find_cycles(acyclic_linear_graph)

        assert result == []

    def test_returns_empty_list_for_tree_structure(
        self, acyclic_tree_graph: KnowledgeGraph
    ) -> None:
        """Test that find_cycles returns empty list for tree structure."""
        result = find_cycles(acyclic_tree_graph)

        assert result == []

    def test_finds_multiple_independent_cycles(
        self, multiple_cycles_graph: KnowledgeGraph
    ) -> None:
        """Test that find_cycles finds multiple independent cycles."""
        result = find_cycles(multiple_cycles_graph)

        # Should find at least 2 cycles (one for each component)
        assert len(result) >= 2

        # Verify both sets of nodes are represented in cycles
        all_cycle_node_ids = []
        for cycle in result:
            all_cycle_node_ids.extend([node.id for node in cycle])

        # Both cycle 1 (A, B) and cycle 2 (C, D) should be found
        assert "artifact-A" in all_cycle_node_ids or "artifact-B" in all_cycle_node_ids
        assert "artifact-C" in all_cycle_node_ids or "artifact-D" in all_cycle_node_ids

    def test_handles_disconnected_components_with_cycle(
        self, disconnected_with_cycle_graph: KnowledgeGraph
    ) -> None:
        """Test that find_cycles detects cycle in disconnected component."""
        result = find_cycles(disconnected_with_cycle_graph)

        # Should find cycle in the cyclic component (C, D)
        assert len(result) >= 1

        # The cycle should include C and D
        cycle_node_ids = []
        for cycle in result:
            cycle_node_ids.extend([node.id for node in cycle])
        assert "artifact-C" in cycle_node_ids or "artifact-D" in cycle_node_ids

    def test_cycle_is_list_of_nodes(self, simple_cycle_graph: KnowledgeGraph) -> None:
        """Test that each cycle in the result is a list of Node objects."""
        result = find_cycles(simple_cycle_graph)

        assert len(result) >= 1
        for cycle in result:
            assert isinstance(cycle, list)
            for node in cycle:
                assert isinstance(node, Node)


# =============================================================================
# Tests for is_acyclic
# =============================================================================


class TestIsAcyclic:
    """Tests for the is_acyclic function."""

    def test_returns_bool(self, empty_graph: KnowledgeGraph) -> None:
        """Test that is_acyclic returns a boolean."""
        result = is_acyclic(empty_graph)

        assert isinstance(result, bool)

    def test_returns_true_for_empty_graph(self, empty_graph: KnowledgeGraph) -> None:
        """Test that is_acyclic returns True for empty graph."""
        result = is_acyclic(empty_graph)

        assert result is True

    def test_returns_true_for_single_node(
        self, single_node_graph: KnowledgeGraph
    ) -> None:
        """Test that is_acyclic returns True for single node with no edges."""
        result = is_acyclic(single_node_graph)

        assert result is True

    def test_returns_true_for_linear_chain(
        self, acyclic_linear_graph: KnowledgeGraph
    ) -> None:
        """Test that is_acyclic returns True for linear chain (A -> B -> C)."""
        result = is_acyclic(acyclic_linear_graph)

        assert result is True

    def test_returns_true_for_tree_structure(
        self, acyclic_tree_graph: KnowledgeGraph
    ) -> None:
        """Test that is_acyclic returns True for tree structure."""
        result = is_acyclic(acyclic_tree_graph)

        assert result is True

    def test_returns_false_for_simple_cycle(
        self, simple_cycle_graph: KnowledgeGraph
    ) -> None:
        """Test that is_acyclic returns False for simple cycle (A -> B -> A)."""
        result = is_acyclic(simple_cycle_graph)

        assert result is False

    def test_returns_false_for_larger_cycle(
        self, larger_cycle_graph: KnowledgeGraph
    ) -> None:
        """Test that is_acyclic returns False for larger cycle (A -> B -> C -> A)."""
        result = is_acyclic(larger_cycle_graph)

        assert result is False

    def test_returns_false_for_self_loop(self, self_loop_graph: KnowledgeGraph) -> None:
        """Test that is_acyclic returns False for self-loop (A -> A)."""
        result = is_acyclic(self_loop_graph)

        assert result is False

    def test_returns_false_when_any_cycle_exists(
        self, disconnected_with_cycle_graph: KnowledgeGraph
    ) -> None:
        """Test that is_acyclic returns False when any cycle exists in the graph."""
        result = is_acyclic(disconnected_with_cycle_graph)

        assert result is False

    def test_returns_false_for_multiple_cycles(
        self, multiple_cycles_graph: KnowledgeGraph
    ) -> None:
        """Test that is_acyclic returns False when multiple cycles exist."""
        result = is_acyclic(multiple_cycles_graph)

        assert result is False
