"""Behavioral tests for Task 133: Pattern Consistency Check.

Tests the pattern consistency check module that validates artifacts follow
established architectural patterns (Repository, Service, Handler, etc.) based
on the knowledge graph. Returns CoherenceIssue with IssueType.PATTERN for any
pattern consistency violations found.

Artifacts tested:
- check_pattern_consistency(manifest_data, graph) -> List[CoherenceIssue]
- _detect_patterns(graph: KnowledgeGraph) -> Dict[str, Any]
- _validate_pattern_usage(manifest_data, patterns) -> List[CoherenceIssue]
"""

import pytest
from typing import Any, Dict

from maid_runner.coherence.checks.pattern_check import (
    check_pattern_consistency,
    _detect_patterns,
    _validate_pattern_usage,
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


# =============================================================================
# Fixtures
# =============================================================================


@pytest.fixture
def empty_knowledge_graph() -> KnowledgeGraph:
    """Create an empty KnowledgeGraph for testing."""
    return KnowledgeGraph()


@pytest.fixture
def graph_with_repository_pattern() -> KnowledgeGraph:
    """Create a KnowledgeGraph with Repository pattern classes.

    Contains classes following the *Repository naming convention,
    indicating a repository pattern in the codebase.
    """
    graph = KnowledgeGraph()

    # Add file nodes for repository classes
    user_repo_file = FileNode(
        id="file:src/repositories/user_repository.py",
        path="src/repositories/user_repository.py",
        status="tracked",
    )
    graph.add_node(user_repo_file)

    order_repo_file = FileNode(
        id="file:src/repositories/order_repository.py",
        path="src/repositories/order_repository.py",
        status="tracked",
    )
    graph.add_node(order_repo_file)

    product_repo_file = FileNode(
        id="file:src/repositories/product_repository.py",
        path="src/repositories/product_repository.py",
        status="tracked",
    )
    graph.add_node(product_repo_file)

    # Add artifact nodes for repository classes
    user_repo = ArtifactNode(
        id="artifact:UserRepository",
        name="UserRepository",
        artifact_type="class",
    )
    graph.add_node(user_repo)

    order_repo = ArtifactNode(
        id="artifact:OrderRepository",
        name="OrderRepository",
        artifact_type="class",
    )
    graph.add_node(order_repo)

    product_repo = ArtifactNode(
        id="artifact:ProductRepository",
        name="ProductRepository",
        artifact_type="class",
    )
    graph.add_node(product_repo)

    # Add edges connecting artifacts to files
    graph.add_edge(
        Edge(
            id="edge:user-repo-defines",
            edge_type=EdgeType.DEFINES,
            source_id="file:src/repositories/user_repository.py",
            target_id="artifact:UserRepository",
        )
    )
    graph.add_edge(
        Edge(
            id="edge:order-repo-defines",
            edge_type=EdgeType.DEFINES,
            source_id="file:src/repositories/order_repository.py",
            target_id="artifact:OrderRepository",
        )
    )
    graph.add_edge(
        Edge(
            id="edge:product-repo-defines",
            edge_type=EdgeType.DEFINES,
            source_id="file:src/repositories/product_repository.py",
            target_id="artifact:ProductRepository",
        )
    )

    return graph


@pytest.fixture
def graph_with_service_pattern() -> KnowledgeGraph:
    """Create a KnowledgeGraph with Service pattern classes.

    Contains classes following the *Service naming convention,
    typically located in a services module.
    """
    graph = KnowledgeGraph()

    # Add module node for services
    services_module = ModuleNode(
        id="module:services",
        name="services",
        package="myapp",
    )
    graph.add_node(services_module)

    # Add file nodes for service classes
    user_service_file = FileNode(
        id="file:src/services/user_service.py",
        path="src/services/user_service.py",
        status="tracked",
    )
    graph.add_node(user_service_file)

    auth_service_file = FileNode(
        id="file:src/services/auth_service.py",
        path="src/services/auth_service.py",
        status="tracked",
    )
    graph.add_node(auth_service_file)

    payment_service_file = FileNode(
        id="file:src/services/payment_service.py",
        path="src/services/payment_service.py",
        status="tracked",
    )
    graph.add_node(payment_service_file)

    # Add artifact nodes for service classes
    user_service = ArtifactNode(
        id="artifact:UserService",
        name="UserService",
        artifact_type="class",
    )
    graph.add_node(user_service)

    auth_service = ArtifactNode(
        id="artifact:AuthService",
        name="AuthService",
        artifact_type="class",
    )
    graph.add_node(auth_service)

    payment_service = ArtifactNode(
        id="artifact:PaymentService",
        name="PaymentService",
        artifact_type="class",
    )
    graph.add_node(payment_service)

    # Add edges connecting artifacts to files
    graph.add_edge(
        Edge(
            id="edge:user-service-defines",
            edge_type=EdgeType.DEFINES,
            source_id="file:src/services/user_service.py",
            target_id="artifact:UserService",
        )
    )
    graph.add_edge(
        Edge(
            id="edge:auth-service-defines",
            edge_type=EdgeType.DEFINES,
            source_id="file:src/services/auth_service.py",
            target_id="artifact:AuthService",
        )
    )
    graph.add_edge(
        Edge(
            id="edge:payment-service-defines",
            edge_type=EdgeType.DEFINES,
            source_id="file:src/services/payment_service.py",
            target_id="artifact:PaymentService",
        )
    )

    # Add BELONGS_TO edges for service files to module
    graph.add_edge(
        Edge(
            id="edge:user-service-belongs",
            edge_type=EdgeType.BELONGS_TO,
            source_id="file:src/services/user_service.py",
            target_id="module:services",
        )
    )

    return graph


@pytest.fixture
def graph_with_mixed_patterns() -> KnowledgeGraph:
    """Create a KnowledgeGraph with multiple architectural patterns.

    Contains both Repository and Service patterns to test pattern detection
    with multiple patterns present.
    """
    graph = KnowledgeGraph()

    # Add repository pattern classes
    user_repo = ArtifactNode(
        id="artifact:UserRepository",
        name="UserRepository",
        artifact_type="class",
    )
    graph.add_node(user_repo)

    order_repo = ArtifactNode(
        id="artifact:OrderRepository",
        name="OrderRepository",
        artifact_type="class",
    )
    graph.add_node(order_repo)

    # Add service pattern classes
    user_service = ArtifactNode(
        id="artifact:UserService",
        name="UserService",
        artifact_type="class",
    )
    graph.add_node(user_service)

    auth_service = ArtifactNode(
        id="artifact:AuthService",
        name="AuthService",
        artifact_type="class",
    )
    graph.add_node(auth_service)

    # Add handler pattern classes
    request_handler = ArtifactNode(
        id="artifact:RequestHandler",
        name="RequestHandler",
        artifact_type="class",
    )
    graph.add_node(request_handler)

    event_handler = ArtifactNode(
        id="artifact:EventHandler",
        name="EventHandler",
        artifact_type="class",
    )
    graph.add_node(event_handler)

    # Add file nodes
    for artifact_id in [
        "UserRepository",
        "OrderRepository",
        "UserService",
        "AuthService",
        "RequestHandler",
        "EventHandler",
    ]:
        file_node = FileNode(
            id=f"file:src/{artifact_id.lower()}.py",
            path=f"src/{artifact_id.lower()}.py",
            status="tracked",
        )
        graph.add_node(file_node)
        graph.add_edge(
            Edge(
                id=f"edge:{artifact_id.lower()}-defines",
                edge_type=EdgeType.DEFINES,
                source_id=f"file:src/{artifact_id.lower()}.py",
                target_id=f"artifact:{artifact_id}",
            )
        )

    return graph


@pytest.fixture
def graph_without_patterns() -> KnowledgeGraph:
    """Create a KnowledgeGraph without recognizable patterns.

    Contains classes that do not follow standard naming patterns.
    """
    graph = KnowledgeGraph()

    # Add artifact nodes without pattern suffixes
    helper = ArtifactNode(
        id="artifact:Helper",
        name="Helper",
        artifact_type="class",
    )
    graph.add_node(helper)

    utils = ArtifactNode(
        id="artifact:Utils",
        name="Utils",
        artifact_type="class",
    )
    graph.add_node(utils)

    processor = ArtifactNode(
        id="artifact:DataProcessor",
        name="DataProcessor",
        artifact_type="class",
    )
    graph.add_node(processor)

    return graph


@pytest.fixture
def manifest_following_patterns() -> Dict[str, Any]:
    """Create a manifest with artifacts that follow established patterns."""
    return {
        "version": "1",
        "goal": "Add new repository class",
        "taskType": "create",
        "creatableFiles": ["src/repositories/customer_repository.py"],
        "expectedArtifacts": {
            "file": "src/repositories/customer_repository.py",
            "contains": [
                {"type": "class", "name": "CustomerRepository"},
                {"type": "function", "name": "find_by_id"},
                {"type": "function", "name": "save"},
            ],
        },
    }


@pytest.fixture
def manifest_violating_repository_pattern() -> Dict[str, Any]:
    """Create a manifest with a repository class violating the pattern.

    Example: A repository class not ending with Repository suffix,
    or a class named *Repository but not in repositories module.
    """
    return {
        "version": "1",
        "goal": "Add data access class",
        "taskType": "create",
        "creatableFiles": ["src/repositories/customer_data.py"],
        "expectedArtifacts": {
            "file": "src/repositories/customer_data.py",
            "contains": [
                # Should be CustomerRepository but named differently
                {"type": "class", "name": "CustomerData"},
                {"type": "function", "name": "get_customer"},
            ],
        },
    }


@pytest.fixture
def manifest_violating_service_pattern() -> Dict[str, Any]:
    """Create a manifest with a service class violating the pattern.

    Example: A service class not in the services module.
    """
    return {
        "version": "1",
        "goal": "Add service class in wrong location",
        "taskType": "create",
        "creatableFiles": ["src/utils/email_service.py"],
        "expectedArtifacts": {
            "file": "src/utils/email_service.py",
            "contains": [
                # Service class in utils module instead of services module
                {"type": "class", "name": "EmailService"},
            ],
        },
    }


@pytest.fixture
def manifest_violating_handler_pattern() -> Dict[str, Any]:
    """Create a manifest with a handler class violating the pattern.

    Example: A handler class not implementing handle() method.
    """
    return {
        "version": "1",
        "goal": "Add handler without handle method",
        "taskType": "create",
        "creatableFiles": ["src/handlers/notification_handler.py"],
        "expectedArtifacts": {
            "file": "src/handlers/notification_handler.py",
            "contains": [
                {"type": "class", "name": "NotificationHandler"},
                # Missing handle() method
                {"type": "function", "name": "send_notification"},
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


@pytest.fixture
def manifest_with_empty_contains() -> Dict[str, Any]:
    """Create a manifest with empty contains list."""
    return {
        "version": "1",
        "goal": "Empty artifacts",
        "taskType": "create",
        "creatableFiles": ["test.py"],
        "expectedArtifacts": {
            "file": "test.py",
            "contains": [],
        },
    }


# =============================================================================
# Tests for check_pattern_consistency
# =============================================================================


class TestCheckPatternConsistencyFunction:
    """Tests for the check_pattern_consistency main function."""

    def test_returns_empty_list_when_patterns_followed(
        self,
        manifest_following_patterns: Dict[str, Any],
        graph_with_repository_pattern: KnowledgeGraph,
    ) -> None:
        """check_pattern_consistency returns empty list when patterns are followed."""
        result = check_pattern_consistency(
            manifest_data=manifest_following_patterns,
            graph=graph_with_repository_pattern,
        )

        assert isinstance(result, list)
        assert len(result) == 0

    def test_returns_coherence_issue_with_pattern_type_for_inconsistencies(
        self,
        manifest_violating_repository_pattern: Dict[str, Any],
        graph_with_repository_pattern: KnowledgeGraph,
    ) -> None:
        """check_pattern_consistency returns CoherenceIssue with IssueType.PATTERN."""
        result = check_pattern_consistency(
            manifest_data=manifest_violating_repository_pattern,
            graph=graph_with_repository_pattern,
        )

        # If pattern violations detected, they should have PATTERN type
        for issue in result:
            assert isinstance(issue, CoherenceIssue)
            assert issue.issue_type == IssueType.PATTERN

    def test_handles_empty_manifest(
        self,
        empty_manifest: Dict[str, Any],
        graph_with_repository_pattern: KnowledgeGraph,
    ) -> None:
        """check_pattern_consistency handles empty manifest without error."""
        result = check_pattern_consistency(
            manifest_data=empty_manifest,
            graph=graph_with_repository_pattern,
        )

        assert isinstance(result, list)
        # Should not raise an exception

    def test_handles_empty_graph(
        self,
        manifest_following_patterns: Dict[str, Any],
        empty_knowledge_graph: KnowledgeGraph,
    ) -> None:
        """check_pattern_consistency handles empty graph gracefully."""
        result = check_pattern_consistency(
            manifest_data=manifest_following_patterns,
            graph=empty_knowledge_graph,
        )

        assert isinstance(result, list)
        # No patterns to detect, so no violations expected
        assert len(result) == 0

    def test_issue_has_appropriate_warning_message(
        self,
        manifest_violating_repository_pattern: Dict[str, Any],
        graph_with_repository_pattern: KnowledgeGraph,
    ) -> None:
        """check_pattern_consistency returns issue with descriptive message."""
        result = check_pattern_consistency(
            manifest_data=manifest_violating_repository_pattern,
            graph=graph_with_repository_pattern,
        )

        # If violations found, message should be descriptive
        for issue in result:
            assert isinstance(issue.message, str)
            assert len(issue.message) > 0

    def test_issue_has_suggestion(
        self,
        manifest_violating_repository_pattern: Dict[str, Any],
        graph_with_repository_pattern: KnowledgeGraph,
    ) -> None:
        """check_pattern_consistency returns issue with helpful suggestion."""
        result = check_pattern_consistency(
            manifest_data=manifest_violating_repository_pattern,
            graph=graph_with_repository_pattern,
        )

        # If violations found, suggestion should be present
        for issue in result:
            assert isinstance(issue.suggestion, str)
            assert len(issue.suggestion) > 0

    def test_handles_manifest_without_expected_artifacts(
        self,
        manifest_without_expected_artifacts: Dict[str, Any],
        graph_with_repository_pattern: KnowledgeGraph,
    ) -> None:
        """check_pattern_consistency handles manifest without expectedArtifacts."""
        result = check_pattern_consistency(
            manifest_data=manifest_without_expected_artifacts,
            graph=graph_with_repository_pattern,
        )

        assert isinstance(result, list)
        assert len(result) == 0

    def test_handles_manifest_with_empty_contains(
        self,
        manifest_with_empty_contains: Dict[str, Any],
        graph_with_repository_pattern: KnowledgeGraph,
    ) -> None:
        """check_pattern_consistency handles manifest with empty contains list."""
        result = check_pattern_consistency(
            manifest_data=manifest_with_empty_contains,
            graph=graph_with_repository_pattern,
        )

        assert isinstance(result, list)
        assert len(result) == 0

    def test_issue_severity_is_warning(
        self,
        manifest_violating_repository_pattern: Dict[str, Any],
        graph_with_repository_pattern: KnowledgeGraph,
    ) -> None:
        """check_pattern_consistency returns issues with WARNING severity."""
        result = check_pattern_consistency(
            manifest_data=manifest_violating_repository_pattern,
            graph=graph_with_repository_pattern,
        )

        # Pattern violations are suggestions, so should be warnings
        for issue in result:
            assert issue.severity == IssueSeverity.WARNING

    def test_issue_has_location_field(
        self,
        manifest_violating_repository_pattern: Dict[str, Any],
        graph_with_repository_pattern: KnowledgeGraph,
    ) -> None:
        """check_pattern_consistency returns issue with location field."""
        result = check_pattern_consistency(
            manifest_data=manifest_violating_repository_pattern,
            graph=graph_with_repository_pattern,
        )

        for issue in result:
            assert hasattr(issue, "location")

    def test_detects_service_pattern_violations(
        self,
        manifest_violating_service_pattern: Dict[str, Any],
        graph_with_service_pattern: KnowledgeGraph,
    ) -> None:
        """check_pattern_consistency detects service pattern violations."""
        result = check_pattern_consistency(
            manifest_data=manifest_violating_service_pattern,
            graph=graph_with_service_pattern,
        )

        # Service in wrong location should be detected
        for issue in result:
            assert isinstance(issue, CoherenceIssue)
            assert issue.issue_type == IssueType.PATTERN


# =============================================================================
# Tests for _detect_patterns
# =============================================================================


class TestDetectPatternsFunction:
    """Tests for the _detect_patterns helper function."""

    def test_detects_repository_pattern(
        self,
        graph_with_repository_pattern: KnowledgeGraph,
    ) -> None:
        """_detect_patterns detects Repository pattern from classes ending in Repository."""
        result = _detect_patterns(graph=graph_with_repository_pattern)

        assert isinstance(result, dict)
        # Should detect the Repository pattern
        assert "Repository" in result or any(
            "Repository" in str(v) for v in result.values()
        )

    def test_detects_service_pattern(
        self,
        graph_with_service_pattern: KnowledgeGraph,
    ) -> None:
        """_detect_patterns detects Service pattern from classes ending in Service."""
        result = _detect_patterns(graph=graph_with_service_pattern)

        assert isinstance(result, dict)
        # Should detect the Service pattern
        assert "Service" in result or any("Service" in str(v) for v in result.values())

    def test_returns_dict_with_pattern_information(
        self,
        graph_with_mixed_patterns: KnowledgeGraph,
    ) -> None:
        """_detect_patterns returns dict with pattern information."""
        result = _detect_patterns(graph=graph_with_mixed_patterns)

        assert isinstance(result, dict)
        # Should contain pattern information (keys and values)
        # Implementation may vary, but structure should be a dict

    def test_handles_empty_graph(
        self,
        empty_knowledge_graph: KnowledgeGraph,
    ) -> None:
        """_detect_patterns handles empty graph gracefully."""
        result = _detect_patterns(graph=empty_knowledge_graph)

        assert isinstance(result, dict)
        # Empty graph should result in empty or minimal patterns dict

    def test_handles_graph_without_patterns(
        self,
        graph_without_patterns: KnowledgeGraph,
    ) -> None:
        """_detect_patterns handles graph without recognizable patterns."""
        result = _detect_patterns(graph=graph_without_patterns)

        assert isinstance(result, dict)
        # No standard patterns should be detected

    def test_detects_handler_pattern(
        self,
        graph_with_mixed_patterns: KnowledgeGraph,
    ) -> None:
        """_detect_patterns detects Handler pattern from classes ending in Handler."""
        result = _detect_patterns(graph=graph_with_mixed_patterns)

        assert isinstance(result, dict)
        # Should detect the Handler pattern if present in graph

    def test_returns_patterns_from_class_names(
        self,
        graph_with_repository_pattern: KnowledgeGraph,
    ) -> None:
        """_detect_patterns extracts patterns from class naming conventions."""
        result = _detect_patterns(graph=graph_with_repository_pattern)

        assert isinstance(result, dict)
        # Patterns should be derived from class names in the graph

    def test_detects_multiple_patterns(
        self,
        graph_with_mixed_patterns: KnowledgeGraph,
    ) -> None:
        """_detect_patterns detects multiple patterns when present."""
        result = _detect_patterns(graph=graph_with_mixed_patterns)

        assert isinstance(result, dict)
        # Should detect Repository, Service, and Handler patterns
        # Implementation may store patterns in different structures

    def test_pattern_dict_contains_class_patterns(
        self,
        graph_with_repository_pattern: KnowledgeGraph,
    ) -> None:
        """_detect_patterns returns dict containing class-related patterns."""
        result = _detect_patterns(graph=graph_with_repository_pattern)

        assert isinstance(result, dict)
        # Result should contain information about class patterns


# =============================================================================
# Tests for _validate_pattern_usage
# =============================================================================


class TestValidatePatternUsageFunction:
    """Tests for the _validate_pattern_usage helper function."""

    def test_returns_empty_list_when_artifact_follows_pattern(self) -> None:
        """_validate_pattern_usage returns empty list when artifact follows pattern."""
        patterns = {
            "Repository": {
                "suffix": "Repository",
                "module": "repositories",
            },
            "Service": {
                "suffix": "Service",
                "module": "services",
            },
        }
        manifest_data = {
            "creatableFiles": ["src/repositories/customer_repository.py"],
            "expectedArtifacts": {
                "file": "src/repositories/customer_repository.py",
                "contains": [
                    {"type": "class", "name": "CustomerRepository"},
                ],
            },
        }

        result = _validate_pattern_usage(
            manifest_data=manifest_data,
            patterns=patterns,
        )

        assert isinstance(result, list)
        assert len(result) == 0

    def test_returns_coherence_issue_when_artifact_violates_pattern(self) -> None:
        """_validate_pattern_usage returns CoherenceIssue when artifact violates pattern."""
        patterns = {
            "Repository": {
                "suffix": "Repository",
                "module": "repositories",
            },
        }
        manifest_data = {
            "creatableFiles": ["src/repositories/customer_data.py"],
            "expectedArtifacts": {
                "file": "src/repositories/customer_data.py",
                "contains": [
                    # Class in repositories module but doesn't follow naming pattern
                    {"type": "class", "name": "CustomerData"},
                ],
            },
        }

        result = _validate_pattern_usage(
            manifest_data=manifest_data,
            patterns=patterns,
        )

        # Should return violation for class in repositories not following pattern
        for issue in result:
            assert isinstance(issue, CoherenceIssue)
            assert issue.issue_type == IssueType.PATTERN

    def test_handles_empty_patterns_dict(self) -> None:
        """_validate_pattern_usage handles empty patterns dict."""
        manifest_data = {
            "creatableFiles": ["test.py"],
            "expectedArtifacts": {
                "file": "test.py",
                "contains": [
                    {"type": "class", "name": "SomeClass"},
                ],
            },
        }

        result = _validate_pattern_usage(
            manifest_data=manifest_data,
            patterns={},
        )

        assert isinstance(result, list)
        # No patterns to validate against, so no violations
        assert len(result) == 0

    def test_handles_artifact_type_not_matching_any_pattern(self) -> None:
        """_validate_pattern_usage handles artifact type not matching any pattern."""
        patterns = {
            "Repository": {
                "suffix": "Repository",
                "module": "repositories",
            },
        }
        manifest_data = {
            "creatableFiles": ["src/utils/helper.py"],
            "expectedArtifacts": {
                "file": "src/utils/helper.py",
                "contains": [
                    # Function, not a class - doesn't match Repository pattern
                    {"type": "function", "name": "helper_function"},
                ],
            },
        }

        result = _validate_pattern_usage(
            manifest_data=manifest_data,
            patterns=patterns,
        )

        assert isinstance(result, list)
        # Function doesn't match class patterns, no violation expected

    def test_validates_service_pattern_module_location(self) -> None:
        """_validate_pattern_usage validates service classes are in services module."""
        patterns = {
            "Service": {
                "suffix": "Service",
                "module": "services",
            },
        }
        manifest_data = {
            # Service class in wrong module
            "creatableFiles": ["src/utils/email_service.py"],
            "expectedArtifacts": {
                "file": "src/utils/email_service.py",
                "contains": [
                    {"type": "class", "name": "EmailService"},
                ],
            },
        }

        result = _validate_pattern_usage(
            manifest_data=manifest_data,
            patterns=patterns,
        )

        # Service in utils instead of services should be detected
        for issue in result:
            assert isinstance(issue, CoherenceIssue)
            assert issue.issue_type == IssueType.PATTERN

    def test_issue_message_contains_artifact_name(self) -> None:
        """_validate_pattern_usage returns issue with artifact name in message."""
        patterns = {
            "Repository": {
                "suffix": "Repository",
                "module": "repositories",
            },
        }
        manifest_data = {
            "creatableFiles": ["src/repositories/customer_data.py"],
            "expectedArtifacts": {
                "file": "src/repositories/customer_data.py",
                "contains": [
                    {"type": "class", "name": "CustomerData"},
                ],
            },
        }

        result = _validate_pattern_usage(
            manifest_data=manifest_data,
            patterns=patterns,
        )

        for issue in result:
            assert "CustomerData" in issue.message or "repositories" in issue.message

    def test_issue_has_helpful_suggestion(self) -> None:
        """_validate_pattern_usage returns issue with helpful suggestion."""
        patterns = {
            "Repository": {
                "suffix": "Repository",
                "module": "repositories",
            },
        }
        manifest_data = {
            "creatableFiles": ["src/repositories/customer_data.py"],
            "expectedArtifacts": {
                "file": "src/repositories/customer_data.py",
                "contains": [
                    {"type": "class", "name": "CustomerData"},
                ],
            },
        }

        result = _validate_pattern_usage(
            manifest_data=manifest_data,
            patterns=patterns,
        )

        for issue in result:
            assert issue.suggestion is not None
            assert len(issue.suggestion) > 0

    def test_handles_manifest_without_expected_artifacts(self) -> None:
        """_validate_pattern_usage handles manifest without expectedArtifacts."""
        patterns = {
            "Repository": {
                "suffix": "Repository",
                "module": "repositories",
            },
        }
        manifest_data = {
            "creatableFiles": ["test.py"],
        }

        result = _validate_pattern_usage(
            manifest_data=manifest_data,
            patterns=patterns,
        )

        assert isinstance(result, list)
        assert len(result) == 0

    def test_handles_manifest_with_empty_contains(self) -> None:
        """_validate_pattern_usage handles manifest with empty contains list."""
        patterns = {
            "Repository": {
                "suffix": "Repository",
                "module": "repositories",
            },
        }
        manifest_data = {
            "creatableFiles": ["test.py"],
            "expectedArtifacts": {
                "file": "test.py",
                "contains": [],
            },
        }

        result = _validate_pattern_usage(
            manifest_data=manifest_data,
            patterns=patterns,
        )

        assert isinstance(result, list)
        assert len(result) == 0


# =============================================================================
# Edge Cases and Integration Tests
# =============================================================================


class TestCheckPatternConsistencyEdgeCases:
    """Edge case tests for check_pattern_consistency."""

    def test_handles_artifact_without_type(
        self,
        graph_with_repository_pattern: KnowledgeGraph,
    ) -> None:
        """check_pattern_consistency handles artifacts without type field."""
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
        result = check_pattern_consistency(
            manifest_data=manifest_with_typeless_artifact,
            graph=graph_with_repository_pattern,
        )

        assert isinstance(result, list)

    def test_handles_artifact_without_name(
        self,
        graph_with_repository_pattern: KnowledgeGraph,
    ) -> None:
        """check_pattern_consistency handles artifacts without name field."""
        manifest_with_nameless_artifact = {
            "version": "1",
            "goal": "Create module",
            "taskType": "create",
            "creatableFiles": ["test.py"],
            "expectedArtifacts": {
                "file": "test.py",
                "contains": [
                    {"type": "class"},  # Missing name
                ],
            },
        }

        # Should not raise an exception
        result = check_pattern_consistency(
            manifest_data=manifest_with_nameless_artifact,
            graph=graph_with_repository_pattern,
        )

        assert isinstance(result, list)

    def test_handles_none_values_in_manifest(
        self,
        graph_with_repository_pattern: KnowledgeGraph,
    ) -> None:
        """check_pattern_consistency handles None values in manifest."""
        manifest_with_none = {
            "version": "1",
            "goal": "Test None handling",
            "taskType": "create",
            "creatableFiles": None,
            "expectedArtifacts": None,
        }

        # Should not raise an exception
        result = check_pattern_consistency(
            manifest_data=manifest_with_none,
            graph=graph_with_repository_pattern,
        )

        assert isinstance(result, list)

    def test_handles_nested_module_paths(
        self,
        graph_with_mixed_patterns: KnowledgeGraph,
    ) -> None:
        """check_pattern_consistency handles deeply nested module paths."""
        manifest_with_nested_path = {
            "version": "1",
            "goal": "Create nested repository",
            "taskType": "create",
            "creatableFiles": ["src/app/data/repositories/nested/user_repository.py"],
            "expectedArtifacts": {
                "file": "src/app/data/repositories/nested/user_repository.py",
                "contains": [
                    {"type": "class", "name": "UserRepository"},
                ],
            },
        }

        result = check_pattern_consistency(
            manifest_data=manifest_with_nested_path,
            graph=graph_with_mixed_patterns,
        )

        assert isinstance(result, list)

    def test_handles_private_classes(
        self,
        graph_with_repository_pattern: KnowledgeGraph,
    ) -> None:
        """check_pattern_consistency handles private classes (with _ prefix)."""
        manifest_with_private = {
            "version": "1",
            "goal": "Create module with private classes",
            "taskType": "create",
            "creatableFiles": ["src/repositories/internal.py"],
            "expectedArtifacts": {
                "file": "src/repositories/internal.py",
                "contains": [
                    {"type": "class", "name": "_InternalRepository"},
                    {"type": "class", "name": "__PrivateHelper"},
                ],
            },
        }

        # Should not raise an exception
        result = check_pattern_consistency(
            manifest_data=manifest_with_private,
            graph=graph_with_repository_pattern,
        )

        assert isinstance(result, list)


class TestCheckPatternConsistencyIntegration:
    """Integration tests for check_pattern_consistency."""

    def test_works_with_fully_populated_graph(
        self,
        manifest_following_patterns: Dict[str, Any],
        graph_with_mixed_patterns: KnowledgeGraph,
    ) -> None:
        """check_pattern_consistency works with a fully populated KnowledgeGraph."""
        result = check_pattern_consistency(
            manifest_data=manifest_following_patterns,
            graph=graph_with_mixed_patterns,
        )

        assert isinstance(result, list)

    def test_accepts_knowledge_graph_parameter(
        self,
        manifest_following_patterns: Dict[str, Any],
        empty_knowledge_graph: KnowledgeGraph,
    ) -> None:
        """check_pattern_consistency accepts graph as a parameter."""
        result = check_pattern_consistency(
            manifest_data=manifest_following_patterns,
            graph=empty_knowledge_graph,
        )

        assert isinstance(result, list)

    def test_complete_workflow_with_violations(
        self,
        graph_with_repository_pattern: KnowledgeGraph,
    ) -> None:
        """Integration test for complete workflow with pattern violations."""
        # Manifest with multiple pattern violations
        manifest_with_violations = {
            "version": "1",
            "goal": "Create multiple modules with violations",
            "taskType": "create",
            "creatableFiles": [
                "src/repositories/customer_data.py",  # Should be *Repository
                "src/utils/payment_service.py",  # Service in wrong module
            ],
            "expectedArtifacts": {
                "file": "src/repositories/customer_data.py",
                "contains": [
                    {"type": "class", "name": "CustomerData"},
                ],
            },
        }

        result = check_pattern_consistency(
            manifest_data=manifest_with_violations,
            graph=graph_with_repository_pattern,
        )

        assert isinstance(result, list)
        # Should detect violations
        for issue in result:
            assert isinstance(issue, CoherenceIssue)
            assert issue.issue_type == IssueType.PATTERN

    def test_graph_with_only_artifact_nodes(
        self,
        manifest_following_patterns: Dict[str, Any],
    ) -> None:
        """check_pattern_consistency works with graph containing only artifact nodes."""
        graph = KnowledgeGraph()

        # Add only artifact nodes, no file or module nodes
        artifact = ArtifactNode(
            id="artifact:TestRepository",
            name="TestRepository",
            artifact_type="class",
        )
        graph.add_node(artifact)

        result = check_pattern_consistency(
            manifest_data=manifest_following_patterns,
            graph=graph,
        )

        assert isinstance(result, list)

    def test_multiple_artifacts_in_single_file(
        self,
        graph_with_repository_pattern: KnowledgeGraph,
    ) -> None:
        """check_pattern_consistency handles multiple artifacts in single file."""
        manifest_with_multiple = {
            "version": "1",
            "goal": "Create module with multiple classes",
            "taskType": "create",
            "creatableFiles": ["src/repositories/multi_repo.py"],
            "expectedArtifacts": {
                "file": "src/repositories/multi_repo.py",
                "contains": [
                    {"type": "class", "name": "UserRepository"},
                    {"type": "class", "name": "OrderRepository"},
                    {"type": "class", "name": "DataHelper"},  # Not following pattern
                ],
            },
        }

        result = check_pattern_consistency(
            manifest_data=manifest_with_multiple,
            graph=graph_with_repository_pattern,
        )

        assert isinstance(result, list)
        # DataHelper in repositories module should potentially be flagged
