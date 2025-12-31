"""Behavioral tests for Task 111: Impact Analysis.

Tests for the impact analysis functions in the query module:
- analyze_impact: Comprehensive impact analysis for an artifact
- get_affected_files: Find files affected by changing an artifact
- get_affected_manifests: Find manifests affected by changing an artifact
"""

import pytest

from maid_runner.graph.model import (
    ArtifactNode,
    Edge,
    EdgeType,
    FileNode,
    KnowledgeGraph,
    ManifestNode,
)
from maid_runner.graph.query import (
    analyze_impact,
    get_affected_files,
    get_affected_manifests,
)


# =============================================================================
# Fixtures
# =============================================================================


@pytest.fixture
def empty_graph() -> KnowledgeGraph:
    """Create an empty knowledge graph."""
    return KnowledgeGraph()


@pytest.fixture
def simple_impact_graph() -> KnowledgeGraph:
    """Create a simple graph with clear impact relationships.

    Structure:
    - manifest-001 DECLARES artifact "my_function"
    - file-001 DEFINES artifact "my_function"
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

    graph.add_node(manifest)
    graph.add_node(file_node)
    graph.add_node(function_artifact)

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

    graph.add_edge(edge1)
    graph.add_edge(edge2)

    return graph


@pytest.fixture
def multi_manifest_graph() -> KnowledgeGraph:
    """Create a graph where multiple manifests declare the same artifact.

    Structure:
    - manifest-001 DECLARES "shared_util"
    - manifest-002 DECLARES "shared_util"
    - file-001 DEFINES "shared_util"
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
    shared_artifact = ArtifactNode(
        id="artifact-shared",
        name="shared_util",
        artifact_type="function",
    )

    graph.add_node(manifest1)
    graph.add_node(manifest2)
    graph.add_node(file1)
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
def multi_file_graph() -> KnowledgeGraph:
    """Create a graph where an artifact affects multiple files.

    Structure:
    - file-001 DEFINES "base_class"
    - file-002 DEFINES "derived_class" which depends on "base_class"
    - artifact "derived_class" has edge to "base_class"
    """
    graph = KnowledgeGraph()

    # Create nodes
    file1 = FileNode(
        id="file-001",
        path="src/base.py",
        status="tracked",
    )
    file2 = FileNode(
        id="file-002",
        path="src/derived.py",
        status="tracked",
    )
    base_artifact = ArtifactNode(
        id="artifact-base",
        name="base_class",
        artifact_type="class",
    )
    derived_artifact = ArtifactNode(
        id="artifact-derived",
        name="derived_class",
        artifact_type="class",
    )

    graph.add_node(file1)
    graph.add_node(file2)
    graph.add_node(base_artifact)
    graph.add_node(derived_artifact)

    # Create edges
    # file-001 DEFINES base_class
    edge1 = Edge(
        id="edge-001",
        edge_type=EdgeType.DEFINES,
        source_id="file-001",
        target_id="artifact-base",
    )
    # file-002 DEFINES derived_class
    edge2 = Edge(
        id="edge-002",
        edge_type=EdgeType.DEFINES,
        source_id="file-002",
        target_id="artifact-derived",
    )
    # derived_class INHERITS base_class
    edge3 = Edge(
        id="edge-003",
        edge_type=EdgeType.INHERITS,
        source_id="artifact-derived",
        target_id="artifact-base",
    )

    graph.add_edge(edge1)
    graph.add_edge(edge2)
    graph.add_edge(edge3)

    return graph


@pytest.fixture
def transitive_impact_graph() -> KnowledgeGraph:
    """Create a graph with transitive impact relationships.

    Structure:
    - artifact-A is DECLARED by manifest-001
    - artifact-B depends on artifact-A
    - artifact-C depends on artifact-B
    - Changing artifact-A should transitively affect B and C
    """
    graph = KnowledgeGraph()

    # Create nodes
    manifest = ManifestNode(
        id="manifest-001",
        path="manifests/task-001.manifest.json",
        goal="Create base artifact",
        task_type="create",
        version="1.0",
    )
    file_node = FileNode(
        id="file-001",
        path="src/module.py",
        status="tracked",
    )
    artifact_a = ArtifactNode(
        id="artifact-A",
        name="artifact_a",
        artifact_type="function",
    )
    artifact_b = ArtifactNode(
        id="artifact-B",
        name="artifact_b",
        artifact_type="function",
    )
    artifact_c = ArtifactNode(
        id="artifact-C",
        name="artifact_c",
        artifact_type="function",
    )

    graph.add_node(manifest)
    graph.add_node(file_node)
    graph.add_node(artifact_a)
    graph.add_node(artifact_b)
    graph.add_node(artifact_c)

    # Create edges
    # manifest DECLARES artifact-A
    edge1 = Edge(
        id="edge-001",
        edge_type=EdgeType.DECLARES,
        source_id="manifest-001",
        target_id="artifact-A",
    )
    # file DEFINES all artifacts
    edge2 = Edge(
        id="edge-002",
        edge_type=EdgeType.DEFINES,
        source_id="file-001",
        target_id="artifact-A",
    )
    edge3 = Edge(
        id="edge-003",
        edge_type=EdgeType.DEFINES,
        source_id="file-001",
        target_id="artifact-B",
    )
    edge4 = Edge(
        id="edge-004",
        edge_type=EdgeType.DEFINES,
        source_id="file-001",
        target_id="artifact-C",
    )
    # B depends on A (CONTAINS relationship for dependency)
    edge5 = Edge(
        id="edge-005",
        edge_type=EdgeType.CONTAINS,
        source_id="artifact-B",
        target_id="artifact-A",
    )
    # C depends on B
    edge6 = Edge(
        id="edge-006",
        edge_type=EdgeType.CONTAINS,
        source_id="artifact-C",
        target_id="artifact-B",
    )

    graph.add_edge(edge1)
    graph.add_edge(edge2)
    graph.add_edge(edge3)
    graph.add_edge(edge4)
    graph.add_edge(edge5)
    graph.add_edge(edge6)

    return graph


@pytest.fixture
def complex_impact_graph() -> KnowledgeGraph:
    """Create a complex graph with multiple files, manifests, and dependencies.

    Structure:
    - manifest-001 DECLARES "core_function"
    - manifest-002 DECLARES "helper_function"
    - file-001 DEFINES "core_function"
    - file-002 DEFINES "helper_function"
    - "helper_function" depends on "core_function"
    """
    graph = KnowledgeGraph()

    # Create nodes
    manifest1 = ManifestNode(
        id="manifest-001",
        path="manifests/task-001.manifest.json",
        goal="Create core function",
        task_type="create",
        version="1.0",
    )
    manifest2 = ManifestNode(
        id="manifest-002",
        path="manifests/task-002.manifest.json",
        goal="Create helper function",
        task_type="create",
        version="1.0",
    )
    file1 = FileNode(
        id="file-001",
        path="src/core.py",
        status="tracked",
    )
    file2 = FileNode(
        id="file-002",
        path="src/helpers.py",
        status="tracked",
    )
    core_artifact = ArtifactNode(
        id="artifact-core",
        name="core_function",
        artifact_type="function",
    )
    helper_artifact = ArtifactNode(
        id="artifact-helper",
        name="helper_function",
        artifact_type="function",
    )

    graph.add_node(manifest1)
    graph.add_node(manifest2)
    graph.add_node(file1)
    graph.add_node(file2)
    graph.add_node(core_artifact)
    graph.add_node(helper_artifact)

    # Create edges
    edge1 = Edge(
        id="edge-001",
        edge_type=EdgeType.DECLARES,
        source_id="manifest-001",
        target_id="artifact-core",
    )
    edge2 = Edge(
        id="edge-002",
        edge_type=EdgeType.DECLARES,
        source_id="manifest-002",
        target_id="artifact-helper",
    )
    edge3 = Edge(
        id="edge-003",
        edge_type=EdgeType.DEFINES,
        source_id="file-001",
        target_id="artifact-core",
    )
    edge4 = Edge(
        id="edge-004",
        edge_type=EdgeType.DEFINES,
        source_id="file-002",
        target_id="artifact-helper",
    )
    # helper depends on core
    edge5 = Edge(
        id="edge-005",
        edge_type=EdgeType.CONTAINS,
        source_id="artifact-helper",
        target_id="artifact-core",
    )

    graph.add_edge(edge1)
    graph.add_edge(edge2)
    graph.add_edge(edge3)
    graph.add_edge(edge4)
    graph.add_edge(edge5)

    return graph


@pytest.fixture
def isolated_artifact_graph() -> KnowledgeGraph:
    """Create a graph with an isolated artifact (no relationships)."""
    graph = KnowledgeGraph()

    isolated_artifact = ArtifactNode(
        id="artifact-isolated",
        name="isolated_function",
        artifact_type="function",
    )

    graph.add_node(isolated_artifact)

    return graph


# =============================================================================
# Tests for analyze_impact
# =============================================================================


class TestAnalyzeImpact:
    """Tests for the analyze_impact function."""

    def test_returns_dict(self, simple_impact_graph: KnowledgeGraph) -> None:
        """Test that analyze_impact returns a dictionary."""
        result = analyze_impact(simple_impact_graph, "my_function")

        assert isinstance(result, dict)

    def test_contains_affected_files_key(
        self, simple_impact_graph: KnowledgeGraph
    ) -> None:
        """Test that result contains 'affected_files' key."""
        result = analyze_impact(simple_impact_graph, "my_function")

        assert "affected_files" in result

    def test_contains_affected_manifests_key(
        self, simple_impact_graph: KnowledgeGraph
    ) -> None:
        """Test that result contains 'affected_manifests' key."""
        result = analyze_impact(simple_impact_graph, "my_function")

        assert "affected_manifests" in result

    def test_contains_affected_artifacts_key(
        self, simple_impact_graph: KnowledgeGraph
    ) -> None:
        """Test that result contains 'affected_artifacts' key."""
        result = analyze_impact(simple_impact_graph, "my_function")

        assert "affected_artifacts" in result

    def test_contains_total_impact_count_key(
        self, simple_impact_graph: KnowledgeGraph
    ) -> None:
        """Test that result contains 'total_impact_count' key."""
        result = analyze_impact(simple_impact_graph, "my_function")

        assert "total_impact_count" in result

    def test_returns_empty_impact_for_nonexistent_artifact(
        self, simple_impact_graph: KnowledgeGraph
    ) -> None:
        """Test that non-existent artifact returns empty impact."""
        result = analyze_impact(simple_impact_graph, "nonexistent_artifact")

        assert result["affected_files"] == []
        assert result["affected_manifests"] == []
        assert result["affected_artifacts"] == []
        assert result["total_impact_count"] == 0

    def test_counts_multiple_affected_items_correctly(
        self, multi_manifest_graph: KnowledgeGraph
    ) -> None:
        """Test that multiple affected items are counted correctly."""
        result = analyze_impact(multi_manifest_graph, "shared_util")

        # Should have at least 1 file and 2 manifests
        assert len(result["affected_files"]) >= 1
        assert len(result["affected_manifests"]) >= 2
        assert result["total_impact_count"] >= 3

    def test_includes_transitive_impacts(
        self, transitive_impact_graph: KnowledgeGraph
    ) -> None:
        """Test that transitive impacts are included."""
        result = analyze_impact(transitive_impact_graph, "artifact_a")

        # artifact_a is used by artifact_b, which is used by artifact_c
        # So changing artifact_a should affect artifact_b (directly) and artifact_c (transitively)
        affected_artifact_names = result["affected_artifacts"]
        assert len(affected_artifact_names) >= 1  # At least artifact_b

    def test_affected_files_are_strings(
        self, simple_impact_graph: KnowledgeGraph
    ) -> None:
        """Test that affected_files contains strings (file paths)."""
        result = analyze_impact(simple_impact_graph, "my_function")

        for file_path in result["affected_files"]:
            assert isinstance(file_path, str)

    def test_affected_manifests_are_strings(
        self, simple_impact_graph: KnowledgeGraph
    ) -> None:
        """Test that affected_manifests contains strings (manifest paths)."""
        result = analyze_impact(simple_impact_graph, "my_function")

        for manifest_path in result["affected_manifests"]:
            assert isinstance(manifest_path, str)

    def test_total_impact_count_is_integer(
        self, simple_impact_graph: KnowledgeGraph
    ) -> None:
        """Test that total_impact_count is an integer."""
        result = analyze_impact(simple_impact_graph, "my_function")

        assert isinstance(result["total_impact_count"], int)

    def test_works_with_empty_graph(self, empty_graph: KnowledgeGraph) -> None:
        """Test analyze_impact works with an empty graph."""
        result = analyze_impact(empty_graph, "any_artifact")

        assert result["affected_files"] == []
        assert result["affected_manifests"] == []
        assert result["affected_artifacts"] == []
        assert result["total_impact_count"] == 0

    def test_complex_graph_impact_analysis(
        self, complex_impact_graph: KnowledgeGraph
    ) -> None:
        """Test impact analysis on a complex graph."""
        result = analyze_impact(complex_impact_graph, "core_function")

        # core_function is in file-001, declared by manifest-001
        # helper_function depends on core_function
        assert len(result["affected_files"]) >= 1
        assert len(result["affected_manifests"]) >= 1


# =============================================================================
# Tests for get_affected_files
# =============================================================================


class TestGetAffectedFiles:
    """Tests for the get_affected_files function."""

    def test_returns_list(self, simple_impact_graph: KnowledgeGraph) -> None:
        """Test that get_affected_files returns a list."""
        result = get_affected_files(simple_impact_graph, "my_function")

        assert isinstance(result, list)

    def test_finds_file_that_defines_artifact(
        self, simple_impact_graph: KnowledgeGraph
    ) -> None:
        """Test finding the file that DEFINES the artifact."""
        result = get_affected_files(simple_impact_graph, "my_function")

        assert "src/module.py" in result

    def test_returns_empty_list_for_nonexistent_artifact(
        self, simple_impact_graph: KnowledgeGraph
    ) -> None:
        """Test returns empty list when artifact doesn't exist."""
        result = get_affected_files(simple_impact_graph, "nonexistent_artifact")

        assert result == []

    def test_returns_file_paths_as_strings(
        self, simple_impact_graph: KnowledgeGraph
    ) -> None:
        """Test that returned items are string file paths."""
        result = get_affected_files(simple_impact_graph, "my_function")

        for file_path in result:
            assert isinstance(file_path, str)

    def test_finds_multiple_affected_files(
        self, multi_file_graph: KnowledgeGraph
    ) -> None:
        """Test finding multiple files affected by an artifact change."""
        result = get_affected_files(multi_file_graph, "base_class")

        # base_class is defined in file-001
        # derived_class (in file-002) depends on base_class
        # So both files could be affected
        assert len(result) >= 1
        assert "src/base.py" in result

    def test_works_with_empty_graph(self, empty_graph: KnowledgeGraph) -> None:
        """Test get_affected_files works with an empty graph."""
        result = get_affected_files(empty_graph, "any_artifact")

        assert result == []

    def test_isolated_artifact_returns_empty_list(
        self, isolated_artifact_graph: KnowledgeGraph
    ) -> None:
        """Test that isolated artifact (no file relationship) returns empty list."""
        result = get_affected_files(isolated_artifact_graph, "isolated_function")

        assert result == []


# =============================================================================
# Tests for get_affected_manifests
# =============================================================================


class TestGetAffectedManifests:
    """Tests for the get_affected_manifests function."""

    def test_returns_list(self, simple_impact_graph: KnowledgeGraph) -> None:
        """Test that get_affected_manifests returns a list."""
        result = get_affected_manifests(simple_impact_graph, "my_function")

        assert isinstance(result, list)

    def test_finds_manifest_that_declares_artifact(
        self, simple_impact_graph: KnowledgeGraph
    ) -> None:
        """Test finding the manifest that DECLARES the artifact."""
        result = get_affected_manifests(simple_impact_graph, "my_function")

        assert "manifests/task-001.manifest.json" in result

    def test_returns_empty_list_for_nonexistent_artifact(
        self, simple_impact_graph: KnowledgeGraph
    ) -> None:
        """Test returns empty list when artifact doesn't exist."""
        result = get_affected_manifests(simple_impact_graph, "nonexistent_artifact")

        assert result == []

    def test_returns_manifest_paths_as_strings(
        self, simple_impact_graph: KnowledgeGraph
    ) -> None:
        """Test that returned items are string manifest paths."""
        result = get_affected_manifests(simple_impact_graph, "my_function")

        for manifest_path in result:
            assert isinstance(manifest_path, str)

    def test_finds_multiple_affected_manifests(
        self, multi_manifest_graph: KnowledgeGraph
    ) -> None:
        """Test finding multiple manifests that declare the artifact."""
        result = get_affected_manifests(multi_manifest_graph, "shared_util")

        # shared_util is declared by both manifest-001 and manifest-002
        assert len(result) >= 2
        assert "manifests/task-001.manifest.json" in result
        assert "manifests/task-002.manifest.json" in result

    def test_works_with_empty_graph(self, empty_graph: KnowledgeGraph) -> None:
        """Test get_affected_manifests works with an empty graph."""
        result = get_affected_manifests(empty_graph, "any_artifact")

        assert result == []

    def test_isolated_artifact_returns_empty_list(
        self, isolated_artifact_graph: KnowledgeGraph
    ) -> None:
        """Test that isolated artifact (no manifest relationship) returns empty list."""
        result = get_affected_manifests(isolated_artifact_graph, "isolated_function")

        assert result == []
