"""Behavioral tests for Task 132: Dependency Availability Check.

Tests the dependency availability check module that verifies dependencies
declared in a manifest's readonlyFiles exist in the knowledge graph. This
check returns CoherenceIssue with IssueType.DEPENDENCY for any missing
dependencies found.

Artifacts tested:
- check_dependency_availability(manifest_data, graph) -> List[CoherenceIssue]
- _get_required_dependencies(manifest_data: dict) -> List[str]
- _check_dependency_exists(dependency: str, graph: KnowledgeGraph) -> bool
"""

import pytest
from typing import Any, Dict

from maid_runner.coherence.checks.dependency_check import (
    check_dependency_availability,
    _get_required_dependencies,
    _check_dependency_exists,
)
from maid_runner.coherence.result import (
    CoherenceIssue,
    IssueType,
    IssueSeverity,
)
from maid_runner.graph.model import KnowledgeGraph, FileNode


@pytest.fixture
def empty_knowledge_graph() -> KnowledgeGraph:
    """Create an empty KnowledgeGraph for testing."""
    return KnowledgeGraph()


@pytest.fixture
def graph_with_files() -> KnowledgeGraph:
    """Create a KnowledgeGraph with FILE nodes for testing.

    Contains tracked files representing the readonly dependencies
    that a manifest might reference.
    """
    graph = KnowledgeGraph()

    file1 = FileNode(
        id="file:maid_runner/coherence/result.py",
        path="maid_runner/coherence/result.py",
        status="tracked",
    )
    graph.add_node(file1)

    file2 = FileNode(
        id="file:maid_runner/graph/model.py",
        path="maid_runner/graph/model.py",
        status="tracked",
    )
    graph.add_node(file2)

    file3 = FileNode(
        id="file:maid_runner/validators/manifest.py",
        path="maid_runner/validators/manifest.py",
        status="tracked",
    )
    graph.add_node(file3)

    return graph


@pytest.fixture
def manifest_with_existing_dependencies() -> Dict[str, Any]:
    """Create a manifest with readonlyFiles that exist in the graph."""
    return {
        "version": "1",
        "goal": "Create new coherence check module",
        "taskType": "create",
        "creatableFiles": ["maid_runner/coherence/checks/new_check.py"],
        "readonlyFiles": [
            "maid_runner/coherence/result.py",
            "maid_runner/graph/model.py",
        ],
        "expectedArtifacts": {
            "file": "maid_runner/coherence/checks/new_check.py",
            "contains": [
                {"type": "function", "name": "new_check"},
            ],
        },
    }


@pytest.fixture
def manifest_with_missing_dependency() -> Dict[str, Any]:
    """Create a manifest with a readonlyFile that does not exist in graph."""
    return {
        "version": "1",
        "goal": "Create module with missing dependency",
        "taskType": "create",
        "creatableFiles": ["maid_runner/new_module.py"],
        "readonlyFiles": [
            "maid_runner/coherence/result.py",
            "maid_runner/nonexistent/missing_file.py",  # Missing!
        ],
        "expectedArtifacts": {
            "file": "maid_runner/new_module.py",
            "contains": [
                {"type": "function", "name": "some_function"},
            ],
        },
    }


@pytest.fixture
def manifest_without_readonly_files() -> Dict[str, Any]:
    """Create a manifest without readonlyFiles field."""
    return {
        "version": "1",
        "goal": "Create standalone module",
        "taskType": "create",
        "creatableFiles": ["maid_runner/standalone.py"],
        "expectedArtifacts": {
            "file": "maid_runner/standalone.py",
            "contains": [
                {"type": "function", "name": "standalone_func"},
            ],
        },
    }


@pytest.fixture
def manifest_with_empty_readonly_files() -> Dict[str, Any]:
    """Create a manifest with empty readonlyFiles list."""
    return {
        "version": "1",
        "goal": "Create module with no dependencies",
        "taskType": "create",
        "creatableFiles": ["maid_runner/isolated.py"],
        "readonlyFiles": [],
        "expectedArtifacts": {
            "file": "maid_runner/isolated.py",
            "contains": [
                {"type": "function", "name": "isolated_func"},
            ],
        },
    }


class TestCheckDependencyAvailabilityFunction:
    """Tests for the check_dependency_availability main function."""

    def test_returns_empty_list_when_all_dependencies_exist(
        self,
        manifest_with_existing_dependencies: Dict[str, Any],
        graph_with_files: KnowledgeGraph,
    ) -> None:
        """check_dependency_availability returns empty list when all deps exist."""
        result = check_dependency_availability(
            manifest_data=manifest_with_existing_dependencies,
            graph=graph_with_files,
        )

        assert isinstance(result, list)
        assert len(result) == 0

    def test_returns_coherence_issue_for_missing_dependency(
        self,
        manifest_with_missing_dependency: Dict[str, Any],
        graph_with_files: KnowledgeGraph,
    ) -> None:
        """check_dependency_availability returns CoherenceIssue for missing dep."""
        result = check_dependency_availability(
            manifest_data=manifest_with_missing_dependency,
            graph=graph_with_files,
        )

        assert len(result) >= 1
        # Find the issue for the missing file
        missing_issues = [
            issue for issue in result if "missing_file.py" in issue.message
        ]
        assert len(missing_issues) == 1

    def test_returns_issue_with_dependency_type(
        self,
        manifest_with_missing_dependency: Dict[str, Any],
        graph_with_files: KnowledgeGraph,
    ) -> None:
        """check_dependency_availability returns issue with IssueType.DEPENDENCY."""
        result = check_dependency_availability(
            manifest_data=manifest_with_missing_dependency,
            graph=graph_with_files,
        )

        assert len(result) >= 1
        for issue in result:
            assert isinstance(issue, CoherenceIssue)
            assert issue.issue_type == IssueType.DEPENDENCY

    def test_handles_manifest_without_readonly_files(
        self,
        manifest_without_readonly_files: Dict[str, Any],
        graph_with_files: KnowledgeGraph,
    ) -> None:
        """check_dependency_availability handles manifest without readonlyFiles."""
        result = check_dependency_availability(
            manifest_data=manifest_without_readonly_files,
            graph=graph_with_files,
        )

        assert isinstance(result, list)
        assert len(result) == 0

    def test_handles_empty_graph(
        self,
        manifest_with_existing_dependencies: Dict[str, Any],
        empty_knowledge_graph: KnowledgeGraph,
    ) -> None:
        """check_dependency_availability handles empty graph (all deps missing)."""
        result = check_dependency_availability(
            manifest_data=manifest_with_existing_dependencies,
            graph=empty_knowledge_graph,
        )

        # All dependencies should be reported as missing
        assert isinstance(result, list)
        assert len(result) == 2  # Two readonlyFiles, both missing

    def test_issue_has_appropriate_error_message(
        self,
        manifest_with_missing_dependency: Dict[str, Any],
        graph_with_files: KnowledgeGraph,
    ) -> None:
        """check_dependency_availability returns issue with descriptive message."""
        result = check_dependency_availability(
            manifest_data=manifest_with_missing_dependency,
            graph=graph_with_files,
        )

        assert len(result) >= 1
        issue = result[0]
        # Message should contain the missing file path
        assert "maid_runner/nonexistent/missing_file.py" in issue.message
        # Message should be descriptive
        assert len(issue.message) > 0

    def test_issue_has_suggestion(
        self,
        manifest_with_missing_dependency: Dict[str, Any],
        graph_with_files: KnowledgeGraph,
    ) -> None:
        """check_dependency_availability returns issue with helpful suggestion."""
        result = check_dependency_availability(
            manifest_data=manifest_with_missing_dependency,
            graph=graph_with_files,
        )

        assert len(result) >= 1
        issue = result[0]
        assert issue.suggestion is not None
        assert len(issue.suggestion) > 0

    def test_handles_empty_readonly_files(
        self,
        manifest_with_empty_readonly_files: Dict[str, Any],
        graph_with_files: KnowledgeGraph,
    ) -> None:
        """check_dependency_availability handles empty readonlyFiles list."""
        result = check_dependency_availability(
            manifest_data=manifest_with_empty_readonly_files,
            graph=graph_with_files,
        )

        assert isinstance(result, list)
        assert len(result) == 0

    def test_detects_multiple_missing_dependencies(
        self,
        graph_with_files: KnowledgeGraph,
    ) -> None:
        """check_dependency_availability detects multiple missing dependencies."""
        manifest_with_multiple_missing = {
            "version": "1",
            "goal": "Create module with multiple missing deps",
            "taskType": "create",
            "creatableFiles": ["maid_runner/test.py"],
            "readonlyFiles": [
                "maid_runner/coherence/result.py",  # Exists
                "maid_runner/missing/one.py",  # Missing
                "maid_runner/missing/two.py",  # Missing
            ],
        }

        result = check_dependency_availability(
            manifest_data=manifest_with_multiple_missing,
            graph=graph_with_files,
        )

        assert len(result) == 2  # Two missing dependencies

    def test_issue_severity_is_error(
        self,
        manifest_with_missing_dependency: Dict[str, Any],
        graph_with_files: KnowledgeGraph,
    ) -> None:
        """check_dependency_availability returns issues with ERROR severity."""
        result = check_dependency_availability(
            manifest_data=manifest_with_missing_dependency,
            graph=graph_with_files,
        )

        assert len(result) >= 1
        for issue in result:
            assert issue.severity == IssueSeverity.ERROR

    def test_issue_has_location_field(
        self,
        manifest_with_missing_dependency: Dict[str, Any],
        graph_with_files: KnowledgeGraph,
    ) -> None:
        """check_dependency_availability returns issue with location field."""
        result = check_dependency_availability(
            manifest_data=manifest_with_missing_dependency,
            graph=graph_with_files,
        )

        assert len(result) >= 1
        issue = result[0]
        # Location should be present (can be None or a string)
        assert hasattr(issue, "location")


class TestGetRequiredDependenciesFunction:
    """Tests for the _get_required_dependencies helper function."""

    def test_extracts_file_paths_from_readonly_files(
        self,
        manifest_with_existing_dependencies: Dict[str, Any],
    ) -> None:
        """_get_required_dependencies extracts paths from readonlyFiles."""
        result = _get_required_dependencies(
            manifest_data=manifest_with_existing_dependencies
        )

        assert isinstance(result, list)
        assert len(result) == 2
        assert "maid_runner/coherence/result.py" in result
        assert "maid_runner/graph/model.py" in result

    def test_returns_empty_list_without_readonly_files(
        self,
        manifest_without_readonly_files: Dict[str, Any],
    ) -> None:
        """_get_required_dependencies returns empty list without readonlyFiles."""
        result = _get_required_dependencies(
            manifest_data=manifest_without_readonly_files
        )

        assert isinstance(result, list)
        assert len(result) == 0

    def test_returns_empty_list_for_empty_readonly_files(
        self,
        manifest_with_empty_readonly_files: Dict[str, Any],
    ) -> None:
        """_get_required_dependencies returns empty list for empty readonlyFiles."""
        result = _get_required_dependencies(
            manifest_data=manifest_with_empty_readonly_files
        )

        assert isinstance(result, list)
        assert len(result) == 0

    def test_handles_various_manifest_structures(self) -> None:
        """_get_required_dependencies handles various manifest structures."""
        # Manifest with only required fields
        minimal_manifest: Dict[str, Any] = {
            "goal": "Minimal manifest",
        }

        result = _get_required_dependencies(manifest_data=minimal_manifest)

        assert isinstance(result, list)
        assert len(result) == 0

    def test_handles_single_readonly_file(self) -> None:
        """_get_required_dependencies handles single file in readonlyFiles."""
        manifest_with_single = {
            "version": "1",
            "goal": "Single dependency",
            "readonlyFiles": ["maid_runner/single_dep.py"],
        }

        result = _get_required_dependencies(manifest_data=manifest_with_single)

        assert isinstance(result, list)
        assert len(result) == 1
        assert result[0] == "maid_runner/single_dep.py"

    def test_preserves_order_of_readonly_files(self) -> None:
        """_get_required_dependencies preserves order of readonlyFiles."""
        manifest_with_ordered = {
            "version": "1",
            "goal": "Ordered dependencies",
            "readonlyFiles": [
                "first.py",
                "second.py",
                "third.py",
            ],
        }

        result = _get_required_dependencies(manifest_data=manifest_with_ordered)

        assert result == ["first.py", "second.py", "third.py"]


class TestCheckDependencyExistsFunction:
    """Tests for the _check_dependency_exists helper function."""

    def test_returns_true_when_file_node_exists(
        self,
        graph_with_files: KnowledgeGraph,
    ) -> None:
        """_check_dependency_exists returns True when file node exists."""
        result = _check_dependency_exists(
            dependency="maid_runner/coherence/result.py",
            graph=graph_with_files,
        )

        assert result is True

    def test_returns_false_when_file_node_missing(
        self,
        graph_with_files: KnowledgeGraph,
    ) -> None:
        """_check_dependency_exists returns False when file node missing."""
        result = _check_dependency_exists(
            dependency="maid_runner/nonexistent/file.py",
            graph=graph_with_files,
        )

        assert result is False

    def test_handles_empty_graph(
        self,
        empty_knowledge_graph: KnowledgeGraph,
    ) -> None:
        """_check_dependency_exists handles empty graph."""
        result = _check_dependency_exists(
            dependency="any/file.py",
            graph=empty_knowledge_graph,
        )

        assert result is False

    def test_matches_file_paths_correctly(
        self,
        graph_with_files: KnowledgeGraph,
    ) -> None:
        """_check_dependency_exists matches exact file paths."""
        # Exact match should work
        assert (
            _check_dependency_exists(
                dependency="maid_runner/graph/model.py",
                graph=graph_with_files,
            )
            is True
        )

        # Partial path should not match
        assert (
            _check_dependency_exists(
                dependency="graph/model.py",
                graph=graph_with_files,
            )
            is False
        )

        # Different path should not match
        assert (
            _check_dependency_exists(
                dependency="maid_runner/graph/other.py",
                graph=graph_with_files,
            )
            is False
        )

    def test_handles_various_file_paths(
        self,
        empty_knowledge_graph: KnowledgeGraph,
    ) -> None:
        """_check_dependency_exists handles various file path formats."""
        graph = empty_knowledge_graph

        # Add file node with specific path format
        file_node = FileNode(
            id="file:src/module/file.py",
            path="src/module/file.py",
            status="tracked",
        )
        graph.add_node(file_node)

        # Should find the file
        assert (
            _check_dependency_exists(
                dependency="src/module/file.py",
                graph=graph,
            )
            is True
        )


class TestCheckDependencyAvailabilityEdgeCases:
    """Edge case tests for check_dependency_availability."""

    def test_handles_manifest_with_none_readonly_files(
        self,
        graph_with_files: KnowledgeGraph,
    ) -> None:
        """check_dependency_availability handles None readonlyFiles value."""
        manifest_with_none = {
            "version": "1",
            "goal": "Manifest with None readonlyFiles",
            "taskType": "create",
            "creatableFiles": ["test.py"],
            "readonlyFiles": None,
        }

        # Should not raise an exception
        result = check_dependency_availability(
            manifest_data=manifest_with_none,
            graph=graph_with_files,
        )

        assert isinstance(result, list)
        assert len(result) == 0

    def test_works_with_populated_knowledge_graph(
        self,
        manifest_with_missing_dependency: Dict[str, Any],
    ) -> None:
        """check_dependency_availability works with a populated KnowledgeGraph."""
        from maid_runner.graph.model import ManifestNode, ArtifactNode

        graph = KnowledgeGraph()

        # Add manifest node
        manifest_node = ManifestNode(
            id="manifest:task-100",
            path="manifests/task-100.manifest.json",
            goal="Create coherence result module",
            task_type="create",
            version="1",
        )
        graph.add_node(manifest_node)

        # Add file nodes
        file_node = FileNode(
            id="file:maid_runner/coherence/result.py",
            path="maid_runner/coherence/result.py",
            status="tracked",
        )
        graph.add_node(file_node)

        # Add artifact node
        artifact_node = ArtifactNode(
            id="artifact:CoherenceIssue",
            name="CoherenceIssue",
            artifact_type="class",
        )
        graph.add_node(artifact_node)

        result = check_dependency_availability(
            manifest_data=manifest_with_missing_dependency,
            graph=graph,
        )

        assert isinstance(result, list)
        # Should find the missing dependency
        assert len(result) >= 1

    def test_accepts_knowledge_graph_parameter(
        self,
        manifest_with_existing_dependencies: Dict[str, Any],
        graph_with_files: KnowledgeGraph,
    ) -> None:
        """check_dependency_availability accepts graph as a parameter."""
        result = check_dependency_availability(
            manifest_data=manifest_with_existing_dependencies,
            graph=graph_with_files,
        )

        assert isinstance(result, list)

    def test_handles_duplicate_readonly_files(
        self,
        graph_with_files: KnowledgeGraph,
    ) -> None:
        """check_dependency_availability handles duplicate entries in readonlyFiles."""
        manifest_with_duplicates = {
            "version": "1",
            "goal": "Manifest with duplicate readonlyFiles",
            "taskType": "create",
            "creatableFiles": ["test.py"],
            "readonlyFiles": [
                "maid_runner/coherence/result.py",
                "maid_runner/coherence/result.py",  # Duplicate
            ],
        }

        result = check_dependency_availability(
            manifest_data=manifest_with_duplicates,
            graph=graph_with_files,
        )

        # Should handle gracefully, no errors expected
        assert isinstance(result, list)
        # Both entries exist, so no issues
        assert len(result) == 0

    def test_handles_manifest_with_all_file_types(
        self,
        graph_with_files: KnowledgeGraph,
    ) -> None:
        """check_dependency_availability only checks readonlyFiles."""
        manifest_with_all_types = {
            "version": "1",
            "goal": "Manifest with all file types",
            "taskType": "edit",
            "creatableFiles": ["new_file.py"],
            "editableFiles": ["maid_runner/validators/manifest.py"],
            "readonlyFiles": [
                "maid_runner/coherence/result.py",  # Exists
                "maid_runner/missing/dependency.py",  # Missing
            ],
        }

        result = check_dependency_availability(
            manifest_data=manifest_with_all_types,
            graph=graph_with_files,
        )

        # Should only report the missing readonlyFile
        assert len(result) == 1
        assert "missing/dependency.py" in result[0].message


class TestCheckDependencyAvailabilityIntegration:
    """Integration tests for check_dependency_availability."""

    def test_complete_workflow_with_all_deps_present(self) -> None:
        """Integration test with complete workflow when all deps present."""
        graph = KnowledgeGraph()

        # Set up graph with all required files
        files = [
            "maid_runner/coherence/result.py",
            "maid_runner/graph/model.py",
            "maid_runner/validators/schema.py",
        ]
        for file_path in files:
            node = FileNode(
                id=f"file:{file_path}",
                path=file_path,
                status="tracked",
            )
            graph.add_node(node)

        manifest = {
            "version": "1",
            "goal": "Create new check module",
            "taskType": "create",
            "creatableFiles": ["maid_runner/coherence/checks/new_check.py"],
            "readonlyFiles": files,
        }

        result = check_dependency_availability(
            manifest_data=manifest,
            graph=graph,
        )

        assert len(result) == 0

    def test_complete_workflow_with_missing_deps(self) -> None:
        """Integration test with complete workflow when deps missing."""
        graph = KnowledgeGraph()

        # Set up graph with only some required files
        existing_file = FileNode(
            id="file:maid_runner/coherence/result.py",
            path="maid_runner/coherence/result.py",
            status="tracked",
        )
        graph.add_node(existing_file)

        manifest = {
            "version": "1",
            "goal": "Create new check module",
            "taskType": "create",
            "creatableFiles": ["maid_runner/coherence/checks/new_check.py"],
            "readonlyFiles": [
                "maid_runner/coherence/result.py",  # Exists
                "maid_runner/graph/model.py",  # Missing
                "maid_runner/utils/helpers.py",  # Missing
            ],
        }

        result = check_dependency_availability(
            manifest_data=manifest,
            graph=graph,
        )

        assert len(result) == 2
        missing_paths = [issue.message for issue in result]
        assert any("graph/model.py" in msg for msg in missing_paths)
        assert any("utils/helpers.py" in msg for msg in missing_paths)
