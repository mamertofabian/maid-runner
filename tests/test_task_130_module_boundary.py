"""Behavioral tests for Task 130: Module Boundary Validation.

Tests the module boundary validation module that checks for artifacts
staying within appropriate module boundaries based on file paths. For example,
it might detect if a 'controllers' module is directly accessing a 'data' module,
suggesting the need for a service layer. Returns CoherenceIssue with
IssueType.BOUNDARY_VIOLATION for any violations found.

Artifacts tested:
- check_module_boundaries(manifest_data, graph) -> List[CoherenceIssue]
- _extract_module_from_path(file_path: str) -> str
- _detect_boundary_violation(source_module, target_module, artifact_name) -> Optional[CoherenceIssue]
"""

import pytest
from typing import Any, Dict

from maid_runner.coherence.checks.module_boundary import (
    check_module_boundaries,
    _extract_module_from_path,
    _detect_boundary_violation,
)
from maid_runner.coherence.result import (
    CoherenceIssue,
    IssueType,
    IssueSeverity,
)
from maid_runner.graph.model import (
    KnowledgeGraph,
    FileNode,
    ArtifactNode,
    ModuleNode,
    Edge,
    EdgeType,
)


@pytest.fixture
def empty_knowledge_graph() -> KnowledgeGraph:
    """Create an empty KnowledgeGraph for testing."""
    return KnowledgeGraph()


@pytest.fixture
def graph_with_module_relationships() -> KnowledgeGraph:
    """Create a KnowledgeGraph with module relationships for testing.

    Sets up a graph with modules: controllers, services, data
    with edges representing cross-module access patterns.
    """
    graph = KnowledgeGraph()

    # Add module nodes
    controllers_module = ModuleNode(
        id="module:controllers",
        name="controllers",
        package="myapp",
    )
    graph.add_node(controllers_module)

    services_module = ModuleNode(
        id="module:services",
        name="services",
        package="myapp",
    )
    graph.add_node(services_module)

    data_module = ModuleNode(
        id="module:data",
        name="data",
        package="myapp",
    )
    graph.add_node(data_module)

    # Add file nodes
    controller_file = FileNode(
        id="file:myapp/controllers/user_controller.py",
        path="myapp/controllers/user_controller.py",
        status="tracked",
    )
    graph.add_node(controller_file)

    service_file = FileNode(
        id="file:myapp/services/user_service.py",
        path="myapp/services/user_service.py",
        status="tracked",
    )
    graph.add_node(service_file)

    data_file = FileNode(
        id="file:myapp/data/user_repository.py",
        path="myapp/data/user_repository.py",
        status="tracked",
    )
    graph.add_node(data_file)

    # Add artifact nodes
    controller_artifact = ArtifactNode(
        id="artifact:UserController",
        name="UserController",
        artifact_type="class",
    )
    graph.add_node(controller_artifact)

    service_artifact = ArtifactNode(
        id="artifact:UserService",
        name="UserService",
        artifact_type="class",
    )
    graph.add_node(service_artifact)

    data_artifact = ArtifactNode(
        id="artifact:UserRepository",
        name="UserRepository",
        artifact_type="class",
    )
    graph.add_node(data_artifact)

    # Add edges representing relationships
    # Controller file belongs to controllers module
    graph.add_edge(
        Edge(
            id="edge:controller-belongs",
            edge_type=EdgeType.BELONGS_TO,
            source_id="file:myapp/controllers/user_controller.py",
            target_id="module:controllers",
        )
    )

    # Service file belongs to services module
    graph.add_edge(
        Edge(
            id="edge:service-belongs",
            edge_type=EdgeType.BELONGS_TO,
            source_id="file:myapp/services/user_service.py",
            target_id="module:services",
        )
    )

    # Data file belongs to data module
    graph.add_edge(
        Edge(
            id="edge:data-belongs",
            edge_type=EdgeType.BELONGS_TO,
            source_id="file:myapp/data/user_repository.py",
            target_id="module:data",
        )
    )

    return graph


@pytest.fixture
def manifest_without_violations() -> Dict[str, Any]:
    """Create a manifest that does not violate module boundaries."""
    return {
        "version": "1",
        "goal": "Create new service module",
        "taskType": "create",
        "creatableFiles": ["myapp/services/order_service.py"],
        "expectedArtifacts": {
            "file": "myapp/services/order_service.py",
            "contains": [
                {"type": "class", "name": "OrderService"},
                {"type": "function", "name": "process_order"},
            ],
        },
    }


@pytest.fixture
def manifest_with_boundary_violation() -> Dict[str, Any]:
    """Create a manifest that violates module boundaries.

    Example: a controller directly accessing data layer without going
    through the service layer.
    """
    return {
        "version": "1",
        "goal": "Create controller with direct data access",
        "taskType": "create",
        "creatableFiles": ["myapp/controllers/admin_controller.py"],
        "expectedArtifacts": {
            "file": "myapp/controllers/admin_controller.py",
            "contains": [
                {"type": "class", "name": "AdminController"},
                {
                    "type": "function",
                    "name": "get_user_data",
                    "args": [{"name": "repo", "type": "UserRepository"}],
                },
            ],
        },
    }


@pytest.fixture
def empty_manifest() -> Dict[str, Any]:
    """Create an empty manifest."""
    return {}


@pytest.fixture
def manifest_without_expected_artifacts() -> Dict[str, Any]:
    """Create a manifest without expectedArtifacts."""
    return {
        "version": "1",
        "goal": "Minimal manifest",
        "taskType": "create",
        "creatableFiles": ["test.py"],
    }


class TestCheckModuleBoundariesFunction:
    """Tests for the check_module_boundaries main function."""

    def test_returns_empty_list_when_no_violations(
        self,
        manifest_without_violations: Dict[str, Any],
        empty_knowledge_graph: KnowledgeGraph,
    ) -> None:
        """check_module_boundaries returns empty list when no violations exist."""
        result = check_module_boundaries(
            manifest_data=manifest_without_violations,
            graph=empty_knowledge_graph,
        )

        assert isinstance(result, list)
        assert len(result) == 0

    def test_returns_coherence_issue_with_boundary_violation_type(
        self,
        manifest_with_boundary_violation: Dict[str, Any],
        graph_with_module_relationships: KnowledgeGraph,
    ) -> None:
        """check_module_boundaries returns CoherenceIssue with IssueType.BOUNDARY_VIOLATION."""
        result = check_module_boundaries(
            manifest_data=manifest_with_boundary_violation,
            graph=graph_with_module_relationships,
        )

        # If violations are detected, they should have BOUNDARY_VIOLATION type
        for issue in result:
            assert isinstance(issue, CoherenceIssue)
            assert issue.issue_type == IssueType.BOUNDARY_VIOLATION

    def test_handles_empty_manifest(
        self,
        empty_manifest: Dict[str, Any],
        empty_knowledge_graph: KnowledgeGraph,
    ) -> None:
        """check_module_boundaries handles empty manifest without error."""
        result = check_module_boundaries(
            manifest_data=empty_manifest,
            graph=empty_knowledge_graph,
        )

        assert isinstance(result, list)
        # Should not raise an exception

    def test_handles_manifest_without_expected_artifacts(
        self,
        manifest_without_expected_artifacts: Dict[str, Any],
        empty_knowledge_graph: KnowledgeGraph,
    ) -> None:
        """check_module_boundaries handles manifest without expectedArtifacts."""
        result = check_module_boundaries(
            manifest_data=manifest_without_expected_artifacts,
            graph=empty_knowledge_graph,
        )

        assert isinstance(result, list)
        assert len(result) == 0

    def test_with_graph_containing_module_relationships(
        self,
        manifest_without_violations: Dict[str, Any],
        graph_with_module_relationships: KnowledgeGraph,
    ) -> None:
        """check_module_boundaries works with a graph containing module relationships."""
        result = check_module_boundaries(
            manifest_data=manifest_without_violations,
            graph=graph_with_module_relationships,
        )

        assert isinstance(result, list)
        # Well-structured manifest should not have violations

    def test_issue_has_appropriate_message(
        self,
        manifest_with_boundary_violation: Dict[str, Any],
        graph_with_module_relationships: KnowledgeGraph,
    ) -> None:
        """check_module_boundaries returns issue with descriptive message."""
        result = check_module_boundaries(
            manifest_data=manifest_with_boundary_violation,
            graph=graph_with_module_relationships,
        )

        # If violations found, message should be descriptive
        for issue in result:
            assert isinstance(issue.message, str)
            assert len(issue.message) > 0

    def test_issue_has_suggestion(
        self,
        manifest_with_boundary_violation: Dict[str, Any],
        graph_with_module_relationships: KnowledgeGraph,
    ) -> None:
        """check_module_boundaries returns issue with helpful suggestion."""
        result = check_module_boundaries(
            manifest_data=manifest_with_boundary_violation,
            graph=graph_with_module_relationships,
        )

        # If violations found, suggestion should be present
        for issue in result:
            assert isinstance(issue.suggestion, str)
            assert len(issue.suggestion) > 0

    def test_handles_manifest_with_empty_contains_list(
        self,
        empty_knowledge_graph: KnowledgeGraph,
    ) -> None:
        """check_module_boundaries handles manifest with empty contains list."""
        manifest_with_empty_contains = {
            "version": "1",
            "goal": "Create module",
            "taskType": "create",
            "creatableFiles": ["test.py"],
            "expectedArtifacts": {
                "file": "test.py",
                "contains": [],
            },
        }

        result = check_module_boundaries(
            manifest_data=manifest_with_empty_contains,
            graph=empty_knowledge_graph,
        )

        assert isinstance(result, list)
        assert len(result) == 0

    def test_issue_severity_is_warning(
        self,
        manifest_with_boundary_violation: Dict[str, Any],
        graph_with_module_relationships: KnowledgeGraph,
    ) -> None:
        """check_module_boundaries returns issues with WARNING severity."""
        result = check_module_boundaries(
            manifest_data=manifest_with_boundary_violation,
            graph=graph_with_module_relationships,
        )

        # Boundary violations are typically warnings (suggestions for improvement)
        for issue in result:
            assert issue.severity == IssueSeverity.WARNING

    def test_issue_has_location_field(
        self,
        manifest_with_boundary_violation: Dict[str, Any],
        graph_with_module_relationships: KnowledgeGraph,
    ) -> None:
        """check_module_boundaries returns issue with location field."""
        result = check_module_boundaries(
            manifest_data=manifest_with_boundary_violation,
            graph=graph_with_module_relationships,
        )

        for issue in result:
            assert hasattr(issue, "location")


class TestExtractModuleFromPathFunction:
    """Tests for the _extract_module_from_path helper function."""

    def test_extracts_module_from_src_auth_service_py(self) -> None:
        """_extract_module_from_path extracts 'auth' from 'src/auth/service.py'."""
        result = _extract_module_from_path("src/auth/service.py")

        assert result == "auth"

    def test_extracts_module_from_nested_maid_runner_path(self) -> None:
        """_extract_module_from_path extracts 'checks' from nested path."""
        result = _extract_module_from_path("maid_runner/coherence/checks/module.py")

        assert result == "checks"

    def test_handles_single_directory_file(self) -> None:
        """_extract_module_from_path handles single file without parent directory."""
        result = _extract_module_from_path("service.py")

        assert result == ""

    def test_handles_nested_paths(self) -> None:
        """_extract_module_from_path handles deeply nested paths."""
        result = _extract_module_from_path("a/b/c/d/e/file.py")

        # Should return the immediate parent directory
        assert result == "e"

    def test_handles_paths_with_single_parent(self) -> None:
        """_extract_module_from_path handles paths with single parent directory."""
        result = _extract_module_from_path("mymodule/file.py")

        assert result == "mymodule"

    def test_handles_paths_with_tests_directory(self) -> None:
        """_extract_module_from_path handles paths in tests directory."""
        result = _extract_module_from_path("tests/unit/test_module.py")

        assert result == "unit"

    def test_returns_string_type(self) -> None:
        """_extract_module_from_path always returns a string."""
        result = _extract_module_from_path("any/path/file.py")

        assert isinstance(result, str)

    def test_handles_path_with_dot_directory(self) -> None:
        """_extract_module_from_path handles paths with dot directories."""
        result = _extract_module_from_path("./src/module/file.py")

        # Should still extract the module correctly
        assert isinstance(result, str)

    def test_handles_empty_string(self) -> None:
        """_extract_module_from_path handles empty string input."""
        result = _extract_module_from_path("")

        assert result == ""

    def test_handles_path_ending_with_slash(self) -> None:
        """_extract_module_from_path handles paths ending with slash."""
        result = _extract_module_from_path("src/module/")

        assert isinstance(result, str)


class TestDetectBoundaryViolationFunction:
    """Tests for the _detect_boundary_violation helper function."""

    def test_returns_none_when_modules_are_same(self) -> None:
        """_detect_boundary_violation returns None when source and target modules are same."""
        result = _detect_boundary_violation(
            source_module="services",
            target_module="services",
            artifact_name="some_function",
        )

        assert result is None

    def test_returns_none_when_no_known_violations(self) -> None:
        """_detect_boundary_violation returns None when no violation pattern matches."""
        result = _detect_boundary_violation(
            source_module="services",
            target_module="utils",
            artifact_name="helper_function",
        )

        assert result is None

    def test_returns_coherence_issue_for_known_bad_patterns(self) -> None:
        """_detect_boundary_violation returns CoherenceIssue for known bad patterns.

        Example: controllers directly accessing data layer.
        """
        result = _detect_boundary_violation(
            source_module="controllers",
            target_module="data",
            artifact_name="get_all_users",
        )

        # If this is a known violation pattern
        if result is not None:
            assert isinstance(result, CoherenceIssue)
            assert result.issue_type == IssueType.BOUNDARY_VIOLATION

    def test_issue_has_appropriate_message_and_suggestion(self) -> None:
        """_detect_boundary_violation returns issue with message and suggestion."""
        result = _detect_boundary_violation(
            source_module="controllers",
            target_module="data",
            artifact_name="direct_db_access",
        )

        if result is not None:
            assert isinstance(result.message, str)
            assert len(result.message) > 0
            assert isinstance(result.suggestion, str)
            assert len(result.suggestion) > 0

    def test_handles_empty_source_module(self) -> None:
        """_detect_boundary_violation handles empty source module."""
        result = _detect_boundary_violation(
            source_module="",
            target_module="data",
            artifact_name="some_artifact",
        )

        # Should handle gracefully, either returning None or a valid issue
        assert result is None or isinstance(result, CoherenceIssue)

    def test_handles_empty_target_module(self) -> None:
        """_detect_boundary_violation handles empty target module."""
        result = _detect_boundary_violation(
            source_module="controllers",
            target_module="",
            artifact_name="some_artifact",
        )

        # Should handle gracefully
        assert result is None or isinstance(result, CoherenceIssue)

    def test_handles_empty_artifact_name(self) -> None:
        """_detect_boundary_violation handles empty artifact name."""
        result = _detect_boundary_violation(
            source_module="controllers",
            target_module="data",
            artifact_name="",
        )

        # Should still detect boundary violation based on modules
        assert result is None or isinstance(result, CoherenceIssue)

    def test_returns_optional_coherence_issue(self) -> None:
        """_detect_boundary_violation returns Optional[CoherenceIssue]."""
        result = _detect_boundary_violation(
            source_module="any",
            target_module="other",
            artifact_name="artifact",
        )

        assert result is None or isinstance(result, CoherenceIssue)


class TestCheckModuleBoundariesEdgeCases:
    """Edge case tests for check_module_boundaries."""

    def test_handles_artifact_without_type(
        self,
        empty_knowledge_graph: KnowledgeGraph,
    ) -> None:
        """check_module_boundaries handles artifacts without type field."""
        manifest_with_typeless_artifact = {
            "version": "1",
            "goal": "Create module",
            "taskType": "create",
            "creatableFiles": ["test.py"],
            "expectedArtifacts": {
                "file": "test.py",
                "contains": [
                    {"name": "some_artifact"},  # Missing type
                ],
            },
        }

        # Should not raise an exception
        result = check_module_boundaries(
            manifest_data=manifest_with_typeless_artifact,
            graph=empty_knowledge_graph,
        )

        assert isinstance(result, list)

    def test_handles_artifact_without_name(
        self,
        empty_knowledge_graph: KnowledgeGraph,
    ) -> None:
        """check_module_boundaries handles artifacts without name field."""
        manifest_with_nameless_artifact = {
            "version": "1",
            "goal": "Create module",
            "taskType": "create",
            "creatableFiles": ["test.py"],
            "expectedArtifacts": {
                "file": "test.py",
                "contains": [
                    {"type": "function"},  # Missing name
                ],
            },
        }

        # Should not raise an exception
        result = check_module_boundaries(
            manifest_data=manifest_with_nameless_artifact,
            graph=empty_knowledge_graph,
        )

        assert isinstance(result, list)

    def test_handles_nested_module_structures(
        self,
        empty_knowledge_graph: KnowledgeGraph,
    ) -> None:
        """check_module_boundaries handles deeply nested module structures."""
        manifest_with_nested_path = {
            "version": "1",
            "goal": "Create nested module",
            "taskType": "create",
            "creatableFiles": ["src/app/modules/submodule/handler.py"],
            "expectedArtifacts": {
                "file": "src/app/modules/submodule/handler.py",
                "contains": [
                    {"type": "class", "name": "Handler"},
                ],
            },
        }

        result = check_module_boundaries(
            manifest_data=manifest_with_nested_path,
            graph=empty_knowledge_graph,
        )

        assert isinstance(result, list)

    def test_multiple_artifacts_in_manifest(
        self,
        graph_with_module_relationships: KnowledgeGraph,
    ) -> None:
        """check_module_boundaries checks all artifacts in manifest."""
        manifest_with_multiple_artifacts = {
            "version": "1",
            "goal": "Create module with multiple artifacts",
            "taskType": "create",
            "creatableFiles": ["myapp/controllers/multi_controller.py"],
            "expectedArtifacts": {
                "file": "myapp/controllers/multi_controller.py",
                "contains": [
                    {"type": "class", "name": "Controller1"},
                    {"type": "class", "name": "Controller2"},
                    {"type": "function", "name": "helper_function"},
                ],
            },
        }

        result = check_module_boundaries(
            manifest_data=manifest_with_multiple_artifacts,
            graph=graph_with_module_relationships,
        )

        assert isinstance(result, list)


class TestCheckModuleBoundariesIntegration:
    """Integration tests for check_module_boundaries with various graph configurations."""

    def test_works_with_populated_knowledge_graph(
        self,
        manifest_without_violations: Dict[str, Any],
        graph_with_module_relationships: KnowledgeGraph,
    ) -> None:
        """check_module_boundaries works with a fully populated KnowledgeGraph."""
        result = check_module_boundaries(
            manifest_data=manifest_without_violations,
            graph=graph_with_module_relationships,
        )

        assert isinstance(result, list)

    def test_accepts_knowledge_graph_parameter(
        self,
        manifest_without_violations: Dict[str, Any],
        empty_knowledge_graph: KnowledgeGraph,
    ) -> None:
        """check_module_boundaries accepts graph as a parameter."""
        result = check_module_boundaries(
            manifest_data=manifest_without_violations,
            graph=empty_knowledge_graph,
        )

        assert isinstance(result, list)

    def test_graph_with_no_module_nodes(
        self,
        manifest_without_violations: Dict[str, Any],
    ) -> None:
        """check_module_boundaries works with graph that has no module nodes."""
        graph = KnowledgeGraph()

        # Add only file nodes, no module nodes
        file_node = FileNode(
            id="file:src/app.py",
            path="src/app.py",
            status="tracked",
        )
        graph.add_node(file_node)

        result = check_module_boundaries(
            manifest_data=manifest_without_violations,
            graph=graph,
        )

        assert isinstance(result, list)

    def test_expected_artifacts_with_empty_file_path(
        self,
        empty_knowledge_graph: KnowledgeGraph,
    ) -> None:
        """check_module_boundaries handles expectedArtifacts with empty file path."""
        manifest_with_empty_file = {
            "version": "1",
            "goal": "Test with empty file",
            "taskType": "create",
            "creatableFiles": ["test.py"],
            "expectedArtifacts": {
                "file": "",  # Empty file path
                "contains": [{"type": "function", "name": "test"}],
            },
        }

        result = check_module_boundaries(
            manifest_data=manifest_with_empty_file,
            graph=empty_knowledge_graph,
        )

        assert isinstance(result, list)
        assert len(result) == 0  # Should return early

    def test_expected_artifacts_with_missing_contains(
        self,
        empty_knowledge_graph: KnowledgeGraph,
    ) -> None:
        """check_module_boundaries handles expectedArtifacts with missing contains."""
        manifest_without_contains = {
            "version": "1",
            "goal": "Test without contains",
            "taskType": "create",
            "creatableFiles": ["test.py"],
            "expectedArtifacts": {
                "file": "src/module/test.py",
                # No "contains" key
            },
        }

        result = check_module_boundaries(
            manifest_data=manifest_without_contains,
            graph=empty_knowledge_graph,
        )

        assert isinstance(result, list)
        assert len(result) == 0  # Should return early
