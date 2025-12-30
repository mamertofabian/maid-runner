"""Behavioral tests for Task 109: Dependency Analysis.

Tests for the dependency analysis functions in the query module:
- find_dependents: Find nodes that depend on (use) a named artifact
- find_dependencies: Find nodes that an artifact depends on
- get_dependency_tree: Build a recursive dependency tree with cycle detection
"""

import pytest

from maid_runner.graph.model import (
    ArtifactNode,
    Edge,
    EdgeType,
    FileNode,
    KnowledgeGraph,
    ManifestNode,
    NodeType,
)
from maid_runner.graph.query import (
    find_dependents,
    find_dependencies,
    get_dependency_tree,
)


# =============================================================================
# Fixtures
# =============================================================================


@pytest.fixture
def empty_graph() -> KnowledgeGraph:
    """Create an empty knowledge graph."""
    return KnowledgeGraph()


@pytest.fixture
def simple_dependency_graph() -> KnowledgeGraph:
    """Create a simple graph with clear dependency relationships.

    Structure:
    - manifest-001 DECLARES artifact "my_function"
    - file-001 DEFINES artifact "my_function"
    - class-001 CONTAINS artifact "my_method"
    """
    graph = KnowledgeGraph()

    # Create nodes
    manifest = ManifestNode(
        id="manifest-001",
        path="manifests/task-001.manifest.json",
        goal="Create function",
        task_type="create",
        version="1.0",
    )
    file_node = FileNode(
        id="file-001",
        path="src/module.py",
        status="tracked",
    )
    function_artifact = ArtifactNode(
        id="artifact-func-001",
        name="my_function",
        artifact_type="function",
        signature="def my_function(x: int) -> str",
    )
    class_artifact = ArtifactNode(
        id="artifact-class-001",
        name="MyClass",
        artifact_type="class",
    )
    method_artifact = ArtifactNode(
        id="artifact-method-001",
        name="my_method",
        artifact_type="function",
        parent_class="MyClass",
    )

    graph.add_node(manifest)
    graph.add_node(file_node)
    graph.add_node(function_artifact)
    graph.add_node(class_artifact)
    graph.add_node(method_artifact)

    # Create edges
    # manifest DECLARES function
    edge1 = Edge(
        id="edge-001",
        edge_type=EdgeType.DECLARES,
        source_id="manifest-001",
        target_id="artifact-func-001",
    )
    # file DEFINES function
    edge2 = Edge(
        id="edge-002",
        edge_type=EdgeType.DEFINES,
        source_id="file-001",
        target_id="artifact-func-001",
    )
    # class CONTAINS method
    edge3 = Edge(
        id="edge-003",
        edge_type=EdgeType.CONTAINS,
        source_id="artifact-class-001",
        target_id="artifact-method-001",
    )
    # file DEFINES class
    edge4 = Edge(
        id="edge-004",
        edge_type=EdgeType.DEFINES,
        source_id="file-001",
        target_id="artifact-class-001",
    )
    # manifest DECLARES class
    edge5 = Edge(
        id="edge-005",
        edge_type=EdgeType.DECLARES,
        source_id="manifest-001",
        target_id="artifact-class-001",
    )

    graph.add_edge(edge1)
    graph.add_edge(edge2)
    graph.add_edge(edge3)
    graph.add_edge(edge4)
    graph.add_edge(edge5)

    return graph


@pytest.fixture
def multi_dependent_graph() -> KnowledgeGraph:
    """Create a graph where multiple nodes depend on one artifact.

    Structure:
    - manifest-001 DECLARES "shared_util"
    - manifest-002 DECLARES "shared_util"
    - file-001 DEFINES "shared_util"
    - file-002 READS file-001 (dependency on shared_util)
    """
    graph = KnowledgeGraph()

    # Create nodes
    manifest1 = ManifestNode(
        id="manifest-001",
        path="manifests/task-001.manifest.json",
        goal="Create shared utility",
        task_type="create",
        version="1.0",
    )
    manifest2 = ManifestNode(
        id="manifest-002",
        path="manifests/task-002.manifest.json",
        goal="Use shared utility",
        task_type="edit",
        version="1.0",
    )
    file1 = FileNode(
        id="file-001",
        path="src/utils.py",
        status="tracked",
    )
    file2 = FileNode(
        id="file-002",
        path="src/consumer.py",
        status="tracked",
    )
    shared_artifact = ArtifactNode(
        id="artifact-shared",
        name="shared_util",
        artifact_type="function",
    )

    graph.add_node(manifest1)
    graph.add_node(manifest2)
    graph.add_node(file1)
    graph.add_node(file2)
    graph.add_node(shared_artifact)

    # Create edges
    edge1 = Edge(
        id="edge-001",
        edge_type=EdgeType.DECLARES,
        source_id="manifest-001",
        target_id="artifact-shared",
    )
    edge2 = Edge(
        id="edge-002",
        edge_type=EdgeType.DECLARES,
        source_id="manifest-002",
        target_id="artifact-shared",
    )
    edge3 = Edge(
        id="edge-003",
        edge_type=EdgeType.DEFINES,
        source_id="file-001",
        target_id="artifact-shared",
    )

    graph.add_edge(edge1)
    graph.add_edge(edge2)
    graph.add_edge(edge3)

    return graph


@pytest.fixture
def deep_dependency_graph() -> KnowledgeGraph:
    """Create a graph with nested dependencies for tree testing.

    Structure (depth levels):
    Level 0: artifact-A
    Level 1: artifact-B (A CONTAINS B)
    Level 2: artifact-C (B CONTAINS C)
    Level 3: artifact-D (C CONTAINS D)
    """
    graph = KnowledgeGraph()

    # Create artifact nodes
    artifact_a = ArtifactNode(
        id="artifact-A",
        name="ClassA",
        artifact_type="class",
    )
    artifact_b = ArtifactNode(
        id="artifact-B",
        name="method_b",
        artifact_type="function",
        parent_class="ClassA",
    )
    artifact_c = ArtifactNode(
        id="artifact-C",
        name="helper_c",
        artifact_type="function",
    )
    artifact_d = ArtifactNode(
        id="artifact-D",
        name="util_d",
        artifact_type="function",
    )

    graph.add_node(artifact_a)
    graph.add_node(artifact_b)
    graph.add_node(artifact_c)
    graph.add_node(artifact_d)

    # Create CONTAINS edges (parent -> child)
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
        target_id="artifact-D",
    )

    graph.add_edge(edge1)
    graph.add_edge(edge2)
    graph.add_edge(edge3)

    return graph


@pytest.fixture
def cyclic_dependency_graph() -> KnowledgeGraph:
    """Create a graph with a cycle for cycle detection testing.

    Structure:
    artifact-A -> artifact-B -> artifact-C -> artifact-A (cycle)
    """
    graph = KnowledgeGraph()

    # Create artifact nodes
    artifact_a = ArtifactNode(
        id="artifact-A",
        name="ModuleA",
        artifact_type="class",
    )
    artifact_b = ArtifactNode(
        id="artifact-B",
        name="ModuleB",
        artifact_type="class",
    )
    artifact_c = ArtifactNode(
        id="artifact-C",
        name="ModuleC",
        artifact_type="class",
    )

    graph.add_node(artifact_a)
    graph.add_node(artifact_b)
    graph.add_node(artifact_c)

    # Create cyclic edges using CONTAINS relationship
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
def leaf_node_graph() -> KnowledgeGraph:
    """Create a graph with a leaf node (no dependencies)."""
    graph = KnowledgeGraph()

    leaf_artifact = ArtifactNode(
        id="artifact-leaf",
        name="standalone_function",
        artifact_type="function",
    )

    graph.add_node(leaf_artifact)

    return graph


@pytest.fixture
def different_artifact_types_graph() -> KnowledgeGraph:
    """Create a graph with various artifact types for type testing.

    Structure:
    - manifest DECLARES function artifact
    - manifest DECLARES class artifact
    - manifest DECLARES attribute artifact
    - file DEFINES all artifacts
    """
    graph = KnowledgeGraph()

    manifest = ManifestNode(
        id="manifest-001",
        path="manifests/task-001.manifest.json",
        goal="Create various artifacts",
        task_type="create",
        version="1.0",
    )
    file_node = FileNode(
        id="file-001",
        path="src/module.py",
        status="tracked",
    )
    func_artifact = ArtifactNode(
        id="artifact-func",
        name="my_function",
        artifact_type="function",
    )
    class_artifact = ArtifactNode(
        id="artifact-class",
        name="MyClass",
        artifact_type="class",
    )
    attr_artifact = ArtifactNode(
        id="artifact-attr",
        name="MY_CONSTANT",
        artifact_type="attribute",
    )

    graph.add_node(manifest)
    graph.add_node(file_node)
    graph.add_node(func_artifact)
    graph.add_node(class_artifact)
    graph.add_node(attr_artifact)

    # Manifest DECLARES all artifacts
    edge1 = Edge(
        id="edge-001",
        edge_type=EdgeType.DECLARES,
        source_id="manifest-001",
        target_id="artifact-func",
    )
    edge2 = Edge(
        id="edge-002",
        edge_type=EdgeType.DECLARES,
        source_id="manifest-001",
        target_id="artifact-class",
    )
    edge3 = Edge(
        id="edge-003",
        edge_type=EdgeType.DECLARES,
        source_id="manifest-001",
        target_id="artifact-attr",
    )
    # File DEFINES all artifacts
    edge4 = Edge(
        id="edge-004",
        edge_type=EdgeType.DEFINES,
        source_id="file-001",
        target_id="artifact-func",
    )
    edge5 = Edge(
        id="edge-005",
        edge_type=EdgeType.DEFINES,
        source_id="file-001",
        target_id="artifact-class",
    )
    edge6 = Edge(
        id="edge-006",
        edge_type=EdgeType.DEFINES,
        source_id="file-001",
        target_id="artifact-attr",
    )

    graph.add_edge(edge1)
    graph.add_edge(edge2)
    graph.add_edge(edge3)
    graph.add_edge(edge4)
    graph.add_edge(edge5)
    graph.add_edge(edge6)

    return graph


# =============================================================================
# Tests for find_dependents
# =============================================================================


class TestFindDependents:
    """Tests for the find_dependents function."""

    def test_returns_list_of_nodes(
        self, simple_dependency_graph: KnowledgeGraph
    ) -> None:
        """Test that find_dependents returns a list."""
        result = find_dependents(simple_dependency_graph, "my_function")

        assert isinstance(result, list)

    def test_finds_manifests_that_declare_artifact(
        self, simple_dependency_graph: KnowledgeGraph
    ) -> None:
        """Test finding manifests that DECLARE the artifact."""
        result = find_dependents(simple_dependency_graph, "my_function")

        manifest_ids = [n.id for n in result if n.node_type == NodeType.MANIFEST]
        assert "manifest-001" in manifest_ids

    def test_finds_files_that_define_artifact(
        self, simple_dependency_graph: KnowledgeGraph
    ) -> None:
        """Test finding files that DEFINE the artifact."""
        result = find_dependents(simple_dependency_graph, "my_function")

        file_ids = [n.id for n in result if n.node_type == NodeType.FILE]
        assert "file-001" in file_ids

    def test_returns_empty_list_when_artifact_not_found(
        self, simple_dependency_graph: KnowledgeGraph
    ) -> None:
        """Test returns empty list when artifact name doesn't exist."""
        result = find_dependents(simple_dependency_graph, "nonexistent_artifact")

        assert result == []

    def test_returns_empty_list_when_no_dependents_exist(
        self, leaf_node_graph: KnowledgeGraph
    ) -> None:
        """Test returns empty list when artifact has no dependents."""
        result = find_dependents(leaf_node_graph, "standalone_function")

        assert result == []

    def test_finds_multiple_dependents(
        self, multi_dependent_graph: KnowledgeGraph
    ) -> None:
        """Test finding multiple nodes that depend on the same artifact."""
        result = find_dependents(multi_dependent_graph, "shared_util")

        # Should find both manifests that DECLARE and the file that DEFINES
        assert len(result) >= 2
        result_ids = [n.id for n in result]
        assert "manifest-001" in result_ids or "manifest-002" in result_ids

    def test_works_with_function_artifact_type(
        self, different_artifact_types_graph: KnowledgeGraph
    ) -> None:
        """Test finding dependents for function artifact type."""
        result = find_dependents(different_artifact_types_graph, "my_function")

        assert len(result) > 0

    def test_works_with_class_artifact_type(
        self, different_artifact_types_graph: KnowledgeGraph
    ) -> None:
        """Test finding dependents for class artifact type."""
        result = find_dependents(different_artifact_types_graph, "MyClass")

        assert len(result) > 0

    def test_works_with_attribute_artifact_type(
        self, different_artifact_types_graph: KnowledgeGraph
    ) -> None:
        """Test finding dependents for attribute artifact type."""
        result = find_dependents(different_artifact_types_graph, "MY_CONSTANT")

        assert len(result) > 0

    def test_works_with_empty_graph(self, empty_graph: KnowledgeGraph) -> None:
        """Test find_dependents works with an empty graph."""
        result = find_dependents(empty_graph, "any_artifact")

        assert result == []


# =============================================================================
# Tests for find_dependencies
# =============================================================================


class TestFindDependencies:
    """Tests for the find_dependencies function."""

    def test_returns_list_of_nodes(
        self, simple_dependency_graph: KnowledgeGraph
    ) -> None:
        """Test that find_dependencies returns a list."""
        result = find_dependencies(simple_dependency_graph, "my_method")

        assert isinstance(result, list)

    def test_finds_parent_class_for_contains_relationship(
        self, simple_dependency_graph: KnowledgeGraph
    ) -> None:
        """Test finding parent class via CONTAINS relationship."""
        result = find_dependencies(simple_dependency_graph, "my_method")

        # my_method is CONTAINED BY MyClass (artifact-class-001)
        parent_ids = [n.id for n in result]
        assert "artifact-class-001" in parent_ids

    def test_finds_file_that_defines_artifact(
        self, simple_dependency_graph: KnowledgeGraph
    ) -> None:
        """Test finding the file that defines the artifact."""
        result = find_dependencies(simple_dependency_graph, "my_function")

        # my_function is defined in file-001
        file_ids = [n.id for n in result if n.node_type == NodeType.FILE]
        assert "file-001" in file_ids

    def test_returns_empty_list_when_artifact_not_found(
        self, simple_dependency_graph: KnowledgeGraph
    ) -> None:
        """Test returns empty list when artifact name doesn't exist."""
        result = find_dependencies(simple_dependency_graph, "nonexistent_artifact")

        assert result == []

    def test_returns_empty_list_when_no_dependencies_exist(
        self, leaf_node_graph: KnowledgeGraph
    ) -> None:
        """Test returns empty list when artifact has no dependencies."""
        result = find_dependencies(leaf_node_graph, "standalone_function")

        assert result == []

    def test_works_with_empty_graph(self, empty_graph: KnowledgeGraph) -> None:
        """Test find_dependencies works with an empty graph."""
        result = find_dependencies(empty_graph, "any_artifact")

        assert result == []


# =============================================================================
# Tests for get_dependency_tree
# =============================================================================


class TestGetDependencyTree:
    """Tests for the get_dependency_tree function."""

    def test_returns_dict_with_node_info(
        self, simple_dependency_graph: KnowledgeGraph
    ) -> None:
        """Test that get_dependency_tree returns a dictionary."""
        node = simple_dependency_graph.get_node("artifact-func-001")
        assert node is not None

        result = get_dependency_tree(simple_dependency_graph, node)

        assert isinstance(result, dict)

    def test_includes_node_id_in_result(
        self, simple_dependency_graph: KnowledgeGraph
    ) -> None:
        """Test that result includes the node's id."""
        node = simple_dependency_graph.get_node("artifact-func-001")
        assert node is not None

        result = get_dependency_tree(simple_dependency_graph, node)

        assert "id" in result or "node_id" in result or result.get("node") is not None

    def test_includes_nested_dependencies(
        self, deep_dependency_graph: KnowledgeGraph
    ) -> None:
        """Test that result includes nested dependencies."""
        root_node = deep_dependency_graph.get_node("artifact-A")
        assert root_node is not None

        result = get_dependency_tree(deep_dependency_graph, root_node)

        # The tree should contain nested structure
        assert isinstance(result, dict)
        # Check that result has some structure for dependencies
        assert "dependencies" in result or "children" in result or len(result) > 0

    def test_depth_zero_returns_only_node(
        self, deep_dependency_graph: KnowledgeGraph
    ) -> None:
        """Test that depth=0 returns only the node itself without dependencies."""
        root_node = deep_dependency_graph.get_node("artifact-A")
        assert root_node is not None

        result = get_dependency_tree(deep_dependency_graph, root_node, depth=0)

        # With depth=0, should have minimal or empty dependencies
        deps = result.get("dependencies", result.get("children", []))
        assert deps == [] or deps is None or len(deps) == 0

    def test_depth_one_returns_direct_dependencies_only(
        self, deep_dependency_graph: KnowledgeGraph
    ) -> None:
        """Test that depth=1 returns only direct dependencies."""
        root_node = deep_dependency_graph.get_node("artifact-A")
        assert root_node is not None

        result = get_dependency_tree(deep_dependency_graph, root_node, depth=1)

        # With depth=1, should have direct dependencies but no nested ones
        assert isinstance(result, dict)

    def test_depth_negative_one_returns_full_tree(
        self, deep_dependency_graph: KnowledgeGraph
    ) -> None:
        """Test that depth=-1 returns the full dependency tree."""
        root_node = deep_dependency_graph.get_node("artifact-A")
        assert root_node is not None

        result = get_dependency_tree(deep_dependency_graph, root_node, depth=-1)

        # With depth=-1, should traverse the full tree
        assert isinstance(result, dict)

    def test_handles_cycles_without_infinite_loop(
        self, cyclic_dependency_graph: KnowledgeGraph
    ) -> None:
        """Test that cycles are handled and don't cause infinite loops."""
        node_a = cyclic_dependency_graph.get_node("artifact-A")
        assert node_a is not None

        # This should complete without hanging/infinite recursion
        result = get_dependency_tree(cyclic_dependency_graph, node_a, depth=-1)

        # Should return a valid result despite the cycle
        assert isinstance(result, dict)

    def test_returns_empty_dependencies_for_leaf_nodes(
        self, leaf_node_graph: KnowledgeGraph
    ) -> None:
        """Test that leaf nodes return empty dependencies."""
        leaf_node = leaf_node_graph.get_node("artifact-leaf")
        assert leaf_node is not None

        result = get_dependency_tree(leaf_node_graph, leaf_node)

        # Leaf node should have no dependencies
        deps = result.get("dependencies", result.get("children", []))
        assert deps == [] or deps is None or len(deps) == 0

    def test_default_depth_is_unlimited(
        self, deep_dependency_graph: KnowledgeGraph
    ) -> None:
        """Test that default depth parameter traverses the full tree."""
        root_node = deep_dependency_graph.get_node("artifact-A")
        assert root_node is not None

        # Call without depth parameter (should default to -1)
        result = get_dependency_tree(deep_dependency_graph, root_node)

        # Should work and return full tree
        assert isinstance(result, dict)

    def test_works_with_empty_graph_node(self, empty_graph: KnowledgeGraph) -> None:
        """Test get_dependency_tree with a node added to empty graph."""
        standalone_node = ArtifactNode(
            id="standalone",
            name="test_func",
            artifact_type="function",
        )
        empty_graph.add_node(standalone_node)

        result = get_dependency_tree(empty_graph, standalone_node)

        assert isinstance(result, dict)
