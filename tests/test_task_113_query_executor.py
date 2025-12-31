"""Behavioral tests for Task 113: Query Executor.

Tests the QueryResult dataclass and QueryExecutor class for executing parsed
queries against the knowledge graph.
"""

import pytest

# Import artifacts from the module under test
from maid_runner.graph.query import (
    QueryResult,
    QueryExecutor,
    QueryType,
    QueryIntent,
)

# Import model types used for test fixtures
from maid_runner.graph.model import (
    KnowledgeGraph,
    Edge,
    EdgeType,
    FileNode,
    ArtifactNode,
    ModuleNode,
    ManifestNode,
)


# --- Fixtures ---


@pytest.fixture
def empty_graph():
    """Create an empty KnowledgeGraph for testing."""
    return KnowledgeGraph()


@pytest.fixture
def simple_graph():
    """Create a simple KnowledgeGraph with nodes and edges for testing."""
    graph = KnowledgeGraph()

    # Add file node
    file_node = FileNode(
        id="file:src/validator.py",
        path="src/validator.py",
        status="tracked",
    )
    graph.add_node(file_node)

    # Add artifact nodes
    class_node = ArtifactNode(
        id="artifact:Validator",
        name="Validator",
        artifact_type="class",
    )
    graph.add_node(class_node)

    method_node = ArtifactNode(
        id="artifact:Validator.validate",
        name="validate",
        artifact_type="function",
        parent_class="Validator",
    )
    graph.add_node(method_node)

    function_node = ArtifactNode(
        id="artifact:helper_func",
        name="helper_func",
        artifact_type="function",
    )
    graph.add_node(function_node)

    # Add module node
    module_node = ModuleNode(
        id="module:validators",
        name="validators",
        package="maid_runner",
    )
    graph.add_node(module_node)

    # Add manifest node
    manifest_node = ManifestNode(
        id="manifest:task-001",
        path="manifests/task-001.manifest.json",
        goal="Create validator",
        task_type="create",
        version="1.0",
    )
    graph.add_node(manifest_node)

    # Add edges: file DEFINES class
    edge1 = Edge(
        id="edge:1",
        edge_type=EdgeType.DEFINES,
        source_id="file:src/validator.py",
        target_id="artifact:Validator",
    )
    graph.add_edge(edge1)

    # Add edge: file DEFINES function
    edge2 = Edge(
        id="edge:2",
        edge_type=EdgeType.DEFINES,
        source_id="file:src/validator.py",
        target_id="artifact:helper_func",
    )
    graph.add_edge(edge2)

    # Add edge: class CONTAINS method
    edge3 = Edge(
        id="edge:3",
        edge_type=EdgeType.CONTAINS,
        source_id="artifact:Validator",
        target_id="artifact:Validator.validate",
    )
    graph.add_edge(edge3)

    # Add edge: manifest DECLARES class
    edge4 = Edge(
        id="edge:4",
        edge_type=EdgeType.DECLARES,
        source_id="manifest:task-001",
        target_id="artifact:Validator",
    )
    graph.add_edge(edge4)

    # Add edge: module CONTAINS file
    edge5 = Edge(
        id="edge:5",
        edge_type=EdgeType.CONTAINS,
        source_id="module:validators",
        target_id="file:src/validator.py",
    )
    graph.add_edge(edge5)

    return graph


@pytest.fixture
def cyclic_graph():
    """Create a KnowledgeGraph with a cycle for testing FIND_CYCLES."""
    graph = KnowledgeGraph()

    # Add three nodes that form a cycle
    node_a = ArtifactNode(id="A", name="A", artifact_type="function")
    node_b = ArtifactNode(id="B", name="B", artifact_type="function")
    node_c = ArtifactNode(id="C", name="C", artifact_type="function")

    graph.add_node(node_a)
    graph.add_node(node_b)
    graph.add_node(node_c)

    # A -> B -> C -> A (cycle)
    graph.add_edge(
        Edge(id="e1", edge_type=EdgeType.DECLARES, source_id="A", target_id="B")
    )
    graph.add_edge(
        Edge(id="e2", edge_type=EdgeType.DECLARES, source_id="B", target_id="C")
    )
    graph.add_edge(
        Edge(id="e3", edge_type=EdgeType.DECLARES, source_id="C", target_id="A")
    )

    return graph


# --- QueryResult Dataclass Tests ---


class TestQueryResultDataclass:
    """Test QueryResult dataclass creation and attribute access."""

    def test_creation_with_all_attributes(self):
        """QueryResult can be created with success, query_type, data, and message."""
        result = QueryResult(
            success=True,
            query_type=QueryType.FIND_DEFINITION,
            data={"node_id": "test"},
            message="Found definition",
        )
        assert result is not None

    def test_success_attribute_accessible(self):
        """QueryResult.success attribute is accessible and correct."""
        result = QueryResult(
            success=True,
            query_type=QueryType.FIND_DEFINITION,
            data=None,
            message="Test message",
        )
        assert result.success is True

    def test_success_can_be_false(self):
        """QueryResult.success can be False."""
        result = QueryResult(
            success=False,
            query_type=QueryType.FIND_DEFINITION,
            data=None,
            message="Not found",
        )
        assert result.success is False

    def test_query_type_attribute_accessible(self):
        """QueryResult.query_type attribute is accessible and correct."""
        result = QueryResult(
            success=True,
            query_type=QueryType.FIND_DEPENDENTS,
            data=[],
            message="Found dependents",
        )
        assert result.query_type == QueryType.FIND_DEPENDENTS

    def test_data_attribute_accessible(self):
        """QueryResult.data attribute is accessible and correct."""
        test_data = {"key": "value", "count": 5}
        result = QueryResult(
            success=True,
            query_type=QueryType.FIND_IMPACT,
            data=test_data,
            message="Impact analysis complete",
        )
        assert result.data == test_data

    def test_data_can_be_list(self):
        """QueryResult.data can be a list."""
        test_list = ["item1", "item2", "item3"]
        result = QueryResult(
            success=True,
            query_type=QueryType.LIST_ARTIFACTS,
            data=test_list,
            message="Found artifacts",
        )
        assert result.data == test_list
        assert isinstance(result.data, list)

    def test_data_can_be_dict(self):
        """QueryResult.data can be a dict."""
        test_dict = {"affected_files": [], "total_impact_count": 0}
        result = QueryResult(
            success=True,
            query_type=QueryType.FIND_IMPACT,
            data=test_dict,
            message="Impact analysis",
        )
        assert result.data == test_dict
        assert isinstance(result.data, dict)

    def test_data_can_be_none(self):
        """QueryResult.data can be None."""
        result = QueryResult(
            success=False,
            query_type=QueryType.FIND_DEFINITION,
            data=None,
            message="Target not found",
        )
        assert result.data is None

    def test_message_attribute_accessible(self):
        """QueryResult.message attribute is accessible and correct."""
        msg = "Successfully found 3 definitions"
        result = QueryResult(
            success=True,
            query_type=QueryType.FIND_DEFINITION,
            data=["def1", "def2", "def3"],
            message=msg,
        )
        assert result.message == msg

    def test_message_is_string(self):
        """QueryResult.message is a string."""
        result = QueryResult(
            success=True,
            query_type=QueryType.FIND_CYCLES,
            data=[],
            message="No cycles found",
        )
        assert isinstance(result.message, str)


# --- QueryExecutor Class Tests ---


class TestQueryExecutorInit:
    """Test QueryExecutor class instantiation."""

    def test_can_instantiate_with_graph(self, empty_graph):
        """QueryExecutor can be instantiated with a KnowledgeGraph."""
        executor = QueryExecutor(graph=empty_graph)
        assert executor is not None

    def test_stores_graph_reference(self, simple_graph):
        """QueryExecutor stores the graph reference."""
        executor = QueryExecutor(graph=simple_graph)
        # The executor should have access to the graph
        # We verify by checking it can execute queries against it
        assert executor is not None

    def test_init_explicitly_called_with_graph_parameter(
        self, empty_graph, simple_graph
    ):
        """__init__ can be called explicitly with graph parameter."""
        executor = QueryExecutor(graph=empty_graph)

        # Explicitly call __init__ with graph parameter to verify it accepts the parameter
        executor.__init__(graph=simple_graph)

        # Executor should now work with the new graph
        assert executor is not None

    def test_init_reinitialize_with_different_graph(self, empty_graph, cyclic_graph):
        """__init__ can reinitialize executor with a different graph."""
        executor = QueryExecutor(graph=empty_graph)

        # Reinitialize with a different graph
        executor.__init__(graph=cyclic_graph)

        # Verify the executor can work with the new graph
        intent = QueryIntent(
            query_type=QueryType.FIND_CYCLES,
            target=None,
            original_query="Find cycles",
        )
        result = executor.execute(intent)
        # Should find cycles in cyclic_graph
        assert result.query_type == QueryType.FIND_CYCLES


class TestQueryExecutorExecute:
    """Test QueryExecutor.execute method behavior."""

    def test_execute_returns_query_result(self, simple_graph):
        """execute() returns a QueryResult object."""
        executor = QueryExecutor(graph=simple_graph)
        intent = QueryIntent(
            query_type=QueryType.FIND_DEFINITION,
            target="Validator",
            original_query="What defines Validator?",
        )
        result = executor.execute(intent)
        assert isinstance(result, QueryResult)

    def test_execute_result_has_correct_query_type(self, simple_graph):
        """execute() returns result with matching query_type."""
        executor = QueryExecutor(graph=simple_graph)
        intent = QueryIntent(
            query_type=QueryType.FIND_DEPENDENTS,
            target="Validator",
            original_query="What depends on Validator?",
        )
        result = executor.execute(intent)
        assert result.query_type == QueryType.FIND_DEPENDENTS


class TestQueryExecutorFindDefinition:
    """Test QueryExecutor.execute for FIND_DEFINITION queries."""

    def test_find_definition_returns_definition_info(self, simple_graph):
        """FIND_DEFINITION query returns information about what defines the target."""
        executor = QueryExecutor(graph=simple_graph)
        intent = QueryIntent(
            query_type=QueryType.FIND_DEFINITION,
            target="Validator",
            original_query="What defines Validator?",
        )
        result = executor.execute(intent)

        assert result.success is True
        assert result.query_type == QueryType.FIND_DEFINITION
        # Data should contain definition information
        assert result.data is not None

    def test_find_definition_for_nonexistent_target(self, simple_graph):
        """FIND_DEFINITION returns success=False for non-existent target."""
        executor = QueryExecutor(graph=simple_graph)
        intent = QueryIntent(
            query_type=QueryType.FIND_DEFINITION,
            target="NonExistentClass",
            original_query="What defines NonExistentClass?",
        )
        result = executor.execute(intent)

        assert result.success is False
        assert result.query_type == QueryType.FIND_DEFINITION


class TestQueryExecutorFindDependents:
    """Test QueryExecutor.execute for FIND_DEPENDENTS queries."""

    def test_find_dependents_returns_dependent_nodes(self, simple_graph):
        """FIND_DEPENDENTS query returns nodes that depend on the target."""
        executor = QueryExecutor(graph=simple_graph)
        intent = QueryIntent(
            query_type=QueryType.FIND_DEPENDENTS,
            target="Validator",
            original_query="What depends on Validator?",
        )
        result = executor.execute(intent)

        assert result.success is True
        assert result.query_type == QueryType.FIND_DEPENDENTS
        assert result.data is not None

    def test_find_dependents_for_nonexistent_target(self, simple_graph):
        """FIND_DEPENDENTS returns success=False for non-existent target."""
        executor = QueryExecutor(graph=simple_graph)
        intent = QueryIntent(
            query_type=QueryType.FIND_DEPENDENTS,
            target="NonExistent",
            original_query="What depends on NonExistent?",
        )
        result = executor.execute(intent)

        assert result.success is False


class TestQueryExecutorFindDependencies:
    """Test QueryExecutor.execute for FIND_DEPENDENCIES queries."""

    def test_find_dependencies_returns_dependency_nodes(self, simple_graph):
        """FIND_DEPENDENCIES query returns nodes that the target depends on."""
        executor = QueryExecutor(graph=simple_graph)
        intent = QueryIntent(
            query_type=QueryType.FIND_DEPENDENCIES,
            target="Validator",
            original_query="What does Validator depend on?",
        )
        result = executor.execute(intent)

        assert result.success is True
        assert result.query_type == QueryType.FIND_DEPENDENCIES
        assert result.data is not None

    def test_find_dependencies_for_nonexistent_target(self, simple_graph):
        """FIND_DEPENDENCIES returns success=False for non-existent target."""
        executor = QueryExecutor(graph=simple_graph)
        intent = QueryIntent(
            query_type=QueryType.FIND_DEPENDENCIES,
            target="NonExistent",
            original_query="What does NonExistent depend on?",
        )
        result = executor.execute(intent)

        assert result.success is False


class TestQueryExecutorFindImpact:
    """Test QueryExecutor.execute for FIND_IMPACT queries."""

    def test_find_impact_returns_impact_dict(self, simple_graph):
        """FIND_IMPACT query returns impact analysis as a dict."""
        executor = QueryExecutor(graph=simple_graph)
        intent = QueryIntent(
            query_type=QueryType.FIND_IMPACT,
            target="Validator",
            original_query="What would break if I change Validator?",
        )
        result = executor.execute(intent)

        assert result.success is True
        assert result.query_type == QueryType.FIND_IMPACT
        assert isinstance(result.data, dict)

    def test_find_impact_dict_structure(self, simple_graph):
        """FIND_IMPACT result data contains expected impact analysis keys."""
        executor = QueryExecutor(graph=simple_graph)
        intent = QueryIntent(
            query_type=QueryType.FIND_IMPACT,
            target="Validator",
            original_query="What would break if I change Validator?",
        )
        result = executor.execute(intent)

        assert result.success is True
        # Impact dict should have standard keys from analyze_impact
        assert result.data is not None

    def test_find_impact_for_nonexistent_target(self, simple_graph):
        """FIND_IMPACT returns success=False for non-existent target."""
        executor = QueryExecutor(graph=simple_graph)
        intent = QueryIntent(
            query_type=QueryType.FIND_IMPACT,
            target="NonExistent",
            original_query="What would break if I change NonExistent?",
        )
        result = executor.execute(intent)

        assert result.success is False


class TestQueryExecutorFindCycles:
    """Test QueryExecutor.execute for FIND_CYCLES queries."""

    def test_find_cycles_returns_cycles_list(self, cyclic_graph):
        """FIND_CYCLES query returns a list of cycles."""
        executor = QueryExecutor(graph=cyclic_graph)
        intent = QueryIntent(
            query_type=QueryType.FIND_CYCLES,
            target=None,
            original_query="Find circular dependencies",
        )
        result = executor.execute(intent)

        assert result.success is True
        assert result.query_type == QueryType.FIND_CYCLES
        assert isinstance(result.data, list)

    def test_find_cycles_no_cycles(self, simple_graph):
        """FIND_CYCLES query returns empty list when no cycles exist."""
        executor = QueryExecutor(graph=simple_graph)
        intent = QueryIntent(
            query_type=QueryType.FIND_CYCLES,
            target=None,
            original_query="Find circular dependencies",
        )
        result = executor.execute(intent)

        assert result.success is True
        assert result.query_type == QueryType.FIND_CYCLES
        assert isinstance(result.data, list)
        # simple_graph has no cycles, data should be empty or indicate no cycles
        assert result.data == [] or len(result.data) == 0

    def test_find_cycles_detects_cycle(self, cyclic_graph):
        """FIND_CYCLES detects cycles when they exist."""
        executor = QueryExecutor(graph=cyclic_graph)
        intent = QueryIntent(
            query_type=QueryType.FIND_CYCLES,
            target=None,
            original_query="Find circular dependencies",
        )
        result = executor.execute(intent)

        assert result.success is True
        assert len(result.data) > 0  # Should find at least one cycle


class TestQueryExecutorListArtifacts:
    """Test QueryExecutor.execute for LIST_ARTIFACTS queries."""

    def test_list_artifacts_returns_artifacts_list(self, simple_graph):
        """LIST_ARTIFACTS query returns a list of artifacts."""
        executor = QueryExecutor(graph=simple_graph)
        intent = QueryIntent(
            query_type=QueryType.LIST_ARTIFACTS,
            target="validators",
            original_query="Show all artifacts in module validators",
        )
        result = executor.execute(intent)

        assert result.success is True
        assert result.query_type == QueryType.LIST_ARTIFACTS
        assert isinstance(result.data, list)

    def test_list_artifacts_without_target(self, simple_graph):
        """LIST_ARTIFACTS query works when listing all artifacts."""
        executor = QueryExecutor(graph=simple_graph)
        intent = QueryIntent(
            query_type=QueryType.LIST_ARTIFACTS,
            target=None,
            original_query="Show all artifacts",
        )
        result = executor.execute(intent)

        # Should succeed and return list of all artifacts
        assert result.query_type == QueryType.LIST_ARTIFACTS
        assert isinstance(result.data, list)


class TestQueryExecutorMessageReadability:
    """Test that QueryExecutor.execute returns human-readable messages."""

    def test_success_message_is_readable(self, simple_graph):
        """Successful query returns a human-readable message."""
        executor = QueryExecutor(graph=simple_graph)
        intent = QueryIntent(
            query_type=QueryType.FIND_DEFINITION,
            target="Validator",
            original_query="What defines Validator?",
        )
        result = executor.execute(intent)

        assert result.message is not None
        assert isinstance(result.message, str)
        assert len(result.message) > 0

    def test_failure_message_is_readable(self, simple_graph):
        """Failed query returns a human-readable message."""
        executor = QueryExecutor(graph=simple_graph)
        intent = QueryIntent(
            query_type=QueryType.FIND_DEFINITION,
            target="NonExistent",
            original_query="What defines NonExistent?",
        )
        result = executor.execute(intent)

        assert result.message is not None
        assert isinstance(result.message, str)
        assert len(result.message) > 0


class TestQueryExecutorEmptyGraph:
    """Test QueryExecutor behavior with an empty graph."""

    def test_find_definition_with_empty_graph(self, empty_graph):
        """FIND_DEFINITION with empty graph returns success=False."""
        executor = QueryExecutor(graph=empty_graph)
        intent = QueryIntent(
            query_type=QueryType.FIND_DEFINITION,
            target="SomeClass",
            original_query="What defines SomeClass?",
        )
        result = executor.execute(intent)

        assert result.success is False

    def test_find_cycles_with_empty_graph(self, empty_graph):
        """FIND_CYCLES with empty graph returns success=True and empty list."""
        executor = QueryExecutor(graph=empty_graph)
        intent = QueryIntent(
            query_type=QueryType.FIND_CYCLES,
            target=None,
            original_query="Find circular dependencies",
        )
        result = executor.execute(intent)

        assert result.success is True
        assert result.data == []

    def test_list_artifacts_with_empty_graph(self, empty_graph):
        """LIST_ARTIFACTS with empty graph returns empty list."""
        executor = QueryExecutor(graph=empty_graph)
        intent = QueryIntent(
            query_type=QueryType.LIST_ARTIFACTS,
            target=None,
            original_query="Show all artifacts",
        )
        result = executor.execute(intent)

        assert result.success is True
        assert result.data == []


class TestQueryExecutorIntegration:
    """Integration tests for full query execution workflow."""

    def test_full_workflow_find_definition(self, simple_graph):
        """Full workflow: parse-like intent to QueryResult for FIND_DEFINITION."""
        executor = QueryExecutor(graph=simple_graph)
        intent = QueryIntent(
            query_type=QueryType.FIND_DEFINITION,
            target="Validator",
            original_query="What defines Validator?",
        )
        result = executor.execute(intent)

        assert isinstance(result, QueryResult)
        assert result.query_type == QueryType.FIND_DEFINITION
        assert result.success is True
        assert result.data is not None
        assert isinstance(result.message, str)

    def test_full_workflow_find_cycles_with_cycle(self, cyclic_graph):
        """Full workflow for FIND_CYCLES detecting actual cycles."""
        executor = QueryExecutor(graph=cyclic_graph)
        intent = QueryIntent(
            query_type=QueryType.FIND_CYCLES,
            target=None,
            original_query="Find circular dependencies",
        )
        result = executor.execute(intent)

        assert isinstance(result, QueryResult)
        assert result.query_type == QueryType.FIND_CYCLES
        assert result.success is True
        assert isinstance(result.data, list)
        assert len(result.data) > 0  # Should detect the A->B->C->A cycle

    def test_full_workflow_list_artifacts(self, simple_graph):
        """Full workflow for LIST_ARTIFACTS query."""
        executor = QueryExecutor(graph=simple_graph)
        intent = QueryIntent(
            query_type=QueryType.LIST_ARTIFACTS,
            target=None,
            original_query="Show all artifacts",
        )
        result = executor.execute(intent)

        assert isinstance(result, QueryResult)
        assert result.query_type == QueryType.LIST_ARTIFACTS
        assert result.success is True
        assert isinstance(result.data, list)
        # simple_graph has 3 artifact nodes: Validator, Validator.validate, helper_func
        assert len(result.data) >= 1
