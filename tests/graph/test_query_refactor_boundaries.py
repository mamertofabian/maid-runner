"""Characterization tests for graph query parser/executor/facade boundaries."""

from maid_runner.core.types import (
    ArtifactKind,
    ArtifactSpec,
    FileSpec,
    Manifest,
    TaskType,
)
from maid_runner.graph.builder import GraphBuilder
from maid_runner.graph.model import Edge, EdgeType, KnowledgeGraph, Node, NodeType
from maid_runner.graph.query import (
    GraphQuery,
    QueryExecutor,
    QueryIntent,
    QueryParser,
    QueryType,
    find_cycles,
)


def _manifest(slug: str, file_path: str = "src/service.py") -> Manifest:
    return Manifest(
        slug=slug,
        source_path=f"manifests/{slug}.manifest.yaml",
        goal=f"Goal for {slug}",
        validate_commands=(("pytest", "tests/graph", "-q"),),
        files_create=(
            FileSpec(
                path=file_path,
                artifacts=(
                    ArtifactSpec(kind=ArtifactKind.CLASS, name="Service"),
                    ArtifactSpec(
                        kind=ArtifactKind.METHOD,
                        name="run",
                        of="Service",
                    ),
                ),
            ),
        ),
        task_type=TaskType.REFACTOR,
    )


def _service_graph() -> KnowledgeGraph:
    return GraphBuilder().build_from_manifests([_manifest("service")])


def test_graph_query_facade_preserves_find_node_result_shape():
    graph = _service_graph()
    query = GraphQuery(graph)

    node = query.find_node("Service", NodeType.ARTIFACT)

    assert node is not None
    assert node.id == "artifact:src/service.py:class:Service"
    assert node.node_type == NodeType.ARTIFACT


def test_query_parser_preserves_dependency_intent_detection():
    parser = QueryParser()

    dependents = parser.parse("What depends on Service?")
    dependencies = parser.parse("What does Service depend on?")
    dependencies_alias = parser.parse("Show dependencies of Service")

    assert dependents.query_type == QueryType.FIND_DEPENDENTS
    assert dependents.target == "Service"
    assert dependencies.query_type == QueryType.FIND_DEPENDENCIES
    assert dependencies.target == "Service"
    assert dependencies_alias.query_type == QueryType.FIND_DEPENDENCIES


def test_query_executor_preserves_impact_result_shape():
    graph = _service_graph()
    executor = QueryExecutor(graph)
    intent = QueryIntent(QueryType.FIND_IMPACT, "Service", "impact Service")

    result = executor.execute(intent)

    assert result.success
    assert result.query_type == QueryType.FIND_IMPACT
    assert set(result.data) == {
        "affected_files",
        "affected_manifests",
        "affected_artifacts",
        "total_impact_count",
    }
    assert result.data["affected_files"] == ["src/service.py"]
    assert result.data["total_impact_count"] >= 1


def test_cycle_detection_preserves_node_id_cycles():
    graph = KnowledgeGraph()
    for node_id in ("a", "b", "c"):
        graph.add_node(Node(node_id, NodeType.ARTIFACT))
    graph.add_edge(Edge("edge:a-b", EdgeType.CREATES, "a", "b"))
    graph.add_edge(Edge("edge:b-c", EdgeType.CREATES, "b", "c"))
    graph.add_edge(Edge("edge:c-a", EdgeType.CREATES, "c", "a"))

    cycles = find_cycles(graph)
    facade_cycles = GraphQuery(graph).find_cycles()

    assert [[node.id for node in cycle] for cycle in cycles] == [["a", "b", "c"]]
    assert facade_cycles == [["a", "b", "c"]]
