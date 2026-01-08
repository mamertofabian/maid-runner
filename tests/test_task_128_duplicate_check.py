"""Behavioral tests for Task 128: Duplicate Artifact Detection.

Tests the duplicate artifact detection module that checks for artifacts declared
in multiple manifests without proper supersession. This check queries the system
snapshot (aggregated artifacts from all manifests) and returns CoherenceIssue
with IssueType.DUPLICATE for any duplicates found.

Artifacts tested:
- check_duplicate_artifacts(manifest_data, system_artifacts, graph) -> List[CoherenceIssue]
- _find_existing_artifact(artifact_name, artifact_type, system_artifacts) -> Optional[str]
- _is_valid_supersession(manifest_data, existing_file) -> bool
"""

import pytest
from typing import Any, Dict, List

from maid_runner.coherence.checks.duplicate_check import (
    check_duplicate_artifacts,
    _find_existing_artifact,
    _is_valid_supersession,
)
from maid_runner.coherence.result import (
    CoherenceIssue,
    IssueType,
    IssueSeverity,
)
from maid_runner.graph.model import KnowledgeGraph


@pytest.fixture
def empty_knowledge_graph() -> KnowledgeGraph:
    """Create an empty KnowledgeGraph for testing."""
    return KnowledgeGraph()


@pytest.fixture
def sample_system_artifacts() -> List[Dict[str, Any]]:
    """Create a sample list of system artifacts.

    Represents artifacts aggregated from all existing manifests in the system.
    """
    return [
        {
            "name": "validate_manifest",
            "type": "function",
            "file": "maid_runner/validators/manifest.py",
        },
        {
            "name": "ManifestValidator",
            "type": "class",
            "file": "maid_runner/validators/manifest.py",
        },
        {
            "name": "parse_config",
            "type": "function",
            "file": "maid_runner/config/parser.py",
        },
        {
            "name": "ConfigLoader",
            "type": "class",
            "file": "maid_runner/config/loader.py",
        },
    ]


@pytest.fixture
def manifest_without_duplicates() -> Dict[str, Any]:
    """Create a manifest that declares unique artifacts (no duplicates)."""
    return {
        "version": "1",
        "goal": "Create new utility module",
        "taskType": "create",
        "creatableFiles": ["maid_runner/utils/helpers.py"],
        "expectedArtifacts": {
            "file": "maid_runner/utils/helpers.py",
            "contains": [
                {"type": "function", "name": "format_path"},
                {"type": "class", "name": "PathFormatter"},
            ],
        },
    }


@pytest.fixture
def manifest_with_duplicate_function() -> Dict[str, Any]:
    """Create a manifest that declares a function already in system artifacts."""
    return {
        "version": "1",
        "goal": "Create validation utilities",
        "taskType": "create",
        "creatableFiles": ["maid_runner/utils/validation.py"],
        "expectedArtifacts": {
            "file": "maid_runner/utils/validation.py",
            "contains": [
                {"type": "function", "name": "validate_manifest"},  # Duplicate!
                {"type": "function", "name": "check_schema"},
            ],
        },
    }


@pytest.fixture
def manifest_with_duplicate_class() -> Dict[str, Any]:
    """Create a manifest that declares a class already in system artifacts."""
    return {
        "version": "1",
        "goal": "Create new config module",
        "taskType": "create",
        "creatableFiles": ["maid_runner/config/new_loader.py"],
        "expectedArtifacts": {
            "file": "maid_runner/config/new_loader.py",
            "contains": [
                {"type": "class", "name": "ConfigLoader"},  # Duplicate!
                {"type": "function", "name": "load_yaml"},
            ],
        },
    }


@pytest.fixture
def manifest_with_supersedes() -> Dict[str, Any]:
    """Create a manifest that properly supersedes an existing file."""
    return {
        "version": "1",
        "goal": "Refactor validator module",
        "taskType": "edit",
        "supersedes": ["manifests/task-050-manifest-validator.manifest.json"],
        "editableFiles": ["maid_runner/validators/manifest.py"],
        "expectedArtifacts": {
            "file": "maid_runner/validators/manifest.py",
            "contains": [
                {"type": "function", "name": "validate_manifest"},
                {"type": "class", "name": "ManifestValidator"},
            ],
        },
    }


class TestCheckDuplicateArtifactsFunction:
    """Tests for the check_duplicate_artifacts main function."""

    def test_returns_empty_list_when_no_duplicates(
        self,
        manifest_without_duplicates: Dict[str, Any],
        sample_system_artifacts: List[Dict[str, Any]],
        empty_knowledge_graph: KnowledgeGraph,
    ) -> None:
        """check_duplicate_artifacts returns empty list when no duplicates exist."""
        result = check_duplicate_artifacts(
            manifest_data=manifest_without_duplicates,
            system_artifacts=sample_system_artifacts,
            graph=empty_knowledge_graph,
        )

        assert isinstance(result, list)
        assert len(result) == 0

    def test_detects_duplicate_function_declaration(
        self,
        manifest_with_duplicate_function: Dict[str, Any],
        sample_system_artifacts: List[Dict[str, Any]],
        empty_knowledge_graph: KnowledgeGraph,
    ) -> None:
        """check_duplicate_artifacts detects when a function is declared multiple times."""
        result = check_duplicate_artifacts(
            manifest_data=manifest_with_duplicate_function,
            system_artifacts=sample_system_artifacts,
            graph=empty_knowledge_graph,
        )

        assert len(result) >= 1
        # Find the duplicate issue for validate_manifest
        duplicate_issues = [
            issue for issue in result if "validate_manifest" in issue.message
        ]
        assert len(duplicate_issues) == 1

    def test_detects_duplicate_class_declaration(
        self,
        manifest_with_duplicate_class: Dict[str, Any],
        sample_system_artifacts: List[Dict[str, Any]],
        empty_knowledge_graph: KnowledgeGraph,
    ) -> None:
        """check_duplicate_artifacts detects when a class is declared multiple times."""
        result = check_duplicate_artifacts(
            manifest_data=manifest_with_duplicate_class,
            system_artifacts=sample_system_artifacts,
            graph=empty_knowledge_graph,
        )

        assert len(result) >= 1
        # Find the duplicate issue for ConfigLoader
        duplicate_issues = [
            issue for issue in result if "ConfigLoader" in issue.message
        ]
        assert len(duplicate_issues) == 1

    def test_returns_coherence_issue_with_duplicate_type(
        self,
        manifest_with_duplicate_function: Dict[str, Any],
        sample_system_artifacts: List[Dict[str, Any]],
        empty_knowledge_graph: KnowledgeGraph,
    ) -> None:
        """check_duplicate_artifacts returns CoherenceIssue with IssueType.DUPLICATE."""
        result = check_duplicate_artifacts(
            manifest_data=manifest_with_duplicate_function,
            system_artifacts=sample_system_artifacts,
            graph=empty_knowledge_graph,
        )

        assert len(result) >= 1
        for issue in result:
            assert isinstance(issue, CoherenceIssue)
            assert issue.issue_type == IssueType.DUPLICATE

    def test_issue_has_appropriate_error_message(
        self,
        manifest_with_duplicate_function: Dict[str, Any],
        sample_system_artifacts: List[Dict[str, Any]],
        empty_knowledge_graph: KnowledgeGraph,
    ) -> None:
        """check_duplicate_artifacts returns issue with descriptive message."""
        result = check_duplicate_artifacts(
            manifest_data=manifest_with_duplicate_function,
            system_artifacts=sample_system_artifacts,
            graph=empty_knowledge_graph,
        )

        assert len(result) >= 1
        issue = result[0]
        # Message should contain artifact name
        assert "validate_manifest" in issue.message
        # Message should indicate it's a duplicate
        assert len(issue.message) > 0

    def test_issue_has_suggestion(
        self,
        manifest_with_duplicate_function: Dict[str, Any],
        sample_system_artifacts: List[Dict[str, Any]],
        empty_knowledge_graph: KnowledgeGraph,
    ) -> None:
        """check_duplicate_artifacts returns issue with helpful suggestion."""
        result = check_duplicate_artifacts(
            manifest_data=manifest_with_duplicate_function,
            system_artifacts=sample_system_artifacts,
            graph=empty_knowledge_graph,
        )

        assert len(result) >= 1
        issue = result[0]
        assert issue.suggestion is not None
        assert len(issue.suggestion) > 0

    def test_with_empty_system_artifacts(
        self,
        manifest_with_duplicate_function: Dict[str, Any],
        empty_knowledge_graph: KnowledgeGraph,
    ) -> None:
        """check_duplicate_artifacts returns empty list when system_artifacts is empty."""
        result = check_duplicate_artifacts(
            manifest_data=manifest_with_duplicate_function,
            system_artifacts=[],
            graph=empty_knowledge_graph,
        )

        assert isinstance(result, list)
        assert len(result) == 0

    def test_with_manifest_missing_expected_artifacts(
        self,
        sample_system_artifacts: List[Dict[str, Any]],
        empty_knowledge_graph: KnowledgeGraph,
    ) -> None:
        """check_duplicate_artifacts handles manifest without expectedArtifacts."""
        manifest_without_artifacts = {
            "version": "1",
            "goal": "Minimal manifest",
            "taskType": "create",
            "creatableFiles": ["test.py"],
        }

        result = check_duplicate_artifacts(
            manifest_data=manifest_without_artifacts,
            system_artifacts=sample_system_artifacts,
            graph=empty_knowledge_graph,
        )

        assert isinstance(result, list)
        assert len(result) == 0

    def test_valid_supersession_does_not_report_duplicate(
        self,
        manifest_with_supersedes: Dict[str, Any],
        sample_system_artifacts: List[Dict[str, Any]],
        empty_knowledge_graph: KnowledgeGraph,
    ) -> None:
        """check_duplicate_artifacts does not flag duplicates when supersession is valid."""
        # The manifest supersedes the file containing validate_manifest
        # So declaring validate_manifest should NOT be flagged as duplicate
        result = check_duplicate_artifacts(
            manifest_data=manifest_with_supersedes,
            system_artifacts=sample_system_artifacts,
            graph=empty_knowledge_graph,
        )

        # Should not find duplicates because supersession is valid
        duplicate_issues = [
            issue for issue in result if "validate_manifest" in issue.message
        ]
        assert len(duplicate_issues) == 0

    def test_detects_multiple_duplicates(
        self,
        sample_system_artifacts: List[Dict[str, Any]],
        empty_knowledge_graph: KnowledgeGraph,
    ) -> None:
        """check_duplicate_artifacts detects multiple duplicate declarations."""
        manifest_with_multiple_duplicates = {
            "version": "1",
            "goal": "Create module with duplicates",
            "taskType": "create",
            "creatableFiles": ["maid_runner/new_module.py"],
            "expectedArtifacts": {
                "file": "maid_runner/new_module.py",
                "contains": [
                    {"type": "function", "name": "validate_manifest"},  # Duplicate
                    {"type": "class", "name": "ConfigLoader"},  # Duplicate
                    {"type": "function", "name": "unique_function"},  # Not duplicate
                ],
            },
        }

        result = check_duplicate_artifacts(
            manifest_data=manifest_with_multiple_duplicates,
            system_artifacts=sample_system_artifacts,
            graph=empty_knowledge_graph,
        )

        assert len(result) == 2  # Two duplicates found

    def test_issue_severity_is_error(
        self,
        manifest_with_duplicate_function: Dict[str, Any],
        sample_system_artifacts: List[Dict[str, Any]],
        empty_knowledge_graph: KnowledgeGraph,
    ) -> None:
        """check_duplicate_artifacts returns issues with ERROR severity."""
        result = check_duplicate_artifacts(
            manifest_data=manifest_with_duplicate_function,
            system_artifacts=sample_system_artifacts,
            graph=empty_knowledge_graph,
        )

        assert len(result) >= 1
        for issue in result:
            assert issue.severity == IssueSeverity.ERROR


class TestFindExistingArtifactFunction:
    """Tests for the _find_existing_artifact helper function."""

    def test_returns_none_when_artifact_not_found(
        self,
        sample_system_artifacts: List[Dict[str, Any]],
    ) -> None:
        """_find_existing_artifact returns None when artifact does not exist."""
        result = _find_existing_artifact(
            artifact_name="nonexistent_function",
            artifact_type="function",
            system_artifacts=sample_system_artifacts,
        )

        assert result is None

    def test_returns_file_path_when_artifact_found(
        self,
        sample_system_artifacts: List[Dict[str, Any]],
    ) -> None:
        """_find_existing_artifact returns file path when artifact exists."""
        result = _find_existing_artifact(
            artifact_name="validate_manifest",
            artifact_type="function",
            system_artifacts=sample_system_artifacts,
        )

        assert result is not None
        assert result == "maid_runner/validators/manifest.py"

    def test_matches_by_both_name_and_type(
        self,
        sample_system_artifacts: List[Dict[str, Any]],
    ) -> None:
        """_find_existing_artifact matches by both name AND type."""
        # Add an artifact with same name but different type
        artifacts_with_same_name = sample_system_artifacts + [
            {
                "name": "validate_manifest",
                "type": "class",  # Same name, different type
                "file": "maid_runner/validators/other.py",
            },
        ]

        # Should find the function, not the class
        result = _find_existing_artifact(
            artifact_name="validate_manifest",
            artifact_type="function",
            system_artifacts=artifacts_with_same_name,
        )

        assert result == "maid_runner/validators/manifest.py"

        # Should find the class when asked for class type
        result_class = _find_existing_artifact(
            artifact_name="validate_manifest",
            artifact_type="class",
            system_artifacts=artifacts_with_same_name,
        )

        assert result_class == "maid_runner/validators/other.py"

    def test_handles_empty_system_artifacts_list(self) -> None:
        """_find_existing_artifact handles empty system_artifacts list."""
        result = _find_existing_artifact(
            artifact_name="any_function",
            artifact_type="function",
            system_artifacts=[],
        )

        assert result is None

    def test_finds_class_artifact(
        self,
        sample_system_artifacts: List[Dict[str, Any]],
    ) -> None:
        """_find_existing_artifact finds class artifacts."""
        result = _find_existing_artifact(
            artifact_name="ManifestValidator",
            artifact_type="class",
            system_artifacts=sample_system_artifacts,
        )

        assert result is not None
        assert result == "maid_runner/validators/manifest.py"

    def test_does_not_find_wrong_type(
        self,
        sample_system_artifacts: List[Dict[str, Any]],
    ) -> None:
        """_find_existing_artifact does not match artifact with wrong type."""
        # ManifestValidator exists as a class, not as a function
        result = _find_existing_artifact(
            artifact_name="ManifestValidator",
            artifact_type="function",
            system_artifacts=sample_system_artifacts,
        )

        assert result is None


class TestIsValidSupersessionFunction:
    """Tests for the _is_valid_supersession helper function."""

    def test_returns_true_when_manifest_supersedes_file(self) -> None:
        """_is_valid_supersession returns True when manifest supersedes the file."""
        manifest_data = {
            "version": "1",
            "goal": "Update validator",
            "taskType": "edit",
            "supersedes": ["manifests/task-050-validator.manifest.json"],
            "editableFiles": ["maid_runner/validators/manifest.py"],
        }

        result = _is_valid_supersession(
            manifest_data=manifest_data,
            existing_file="maid_runner/validators/manifest.py",
        )

        assert result is True

    def test_returns_false_when_no_supersession(self) -> None:
        """_is_valid_supersession returns False when no supersession exists."""
        manifest_data = {
            "version": "1",
            "goal": "Create new module",
            "taskType": "create",
            "creatableFiles": ["maid_runner/new_module.py"],
        }

        result = _is_valid_supersession(
            manifest_data=manifest_data,
            existing_file="maid_runner/validators/manifest.py",
        )

        assert result is False

    def test_handles_empty_supersedes_list(self) -> None:
        """_is_valid_supersession handles empty supersedes list."""
        manifest_data = {
            "version": "1",
            "goal": "Create module",
            "taskType": "create",
            "supersedes": [],
            "creatableFiles": ["maid_runner/new.py"],
        }

        result = _is_valid_supersession(
            manifest_data=manifest_data,
            existing_file="maid_runner/validators/manifest.py",
        )

        assert result is False

    def test_handles_manifest_without_supersedes_field(self) -> None:
        """_is_valid_supersession handles manifest without supersedes field."""
        manifest_data = {
            "version": "1",
            "goal": "Create module",
            "taskType": "create",
            "creatableFiles": ["maid_runner/new.py"],
        }

        result = _is_valid_supersession(
            manifest_data=manifest_data,
            existing_file="maid_runner/validators/manifest.py",
        )

        assert result is False

    def test_returns_true_for_editable_file_match(self) -> None:
        """_is_valid_supersession returns True when existing_file is in editableFiles."""
        manifest_data = {
            "version": "1",
            "goal": "Edit existing module",
            "taskType": "edit",
            "editableFiles": ["maid_runner/validators/manifest.py"],
        }

        result = _is_valid_supersession(
            manifest_data=manifest_data,
            existing_file="maid_runner/validators/manifest.py",
        )

        assert result is True

    def test_returns_false_for_different_file(self) -> None:
        """_is_valid_supersession returns False when editing a different file."""
        manifest_data = {
            "version": "1",
            "goal": "Edit config module",
            "taskType": "edit",
            "editableFiles": ["maid_runner/config/parser.py"],
        }

        result = _is_valid_supersession(
            manifest_data=manifest_data,
            existing_file="maid_runner/validators/manifest.py",
        )

        assert result is False

    def test_returns_true_when_file_matches_expected_artifacts(self) -> None:
        """_is_valid_supersession returns True when existing_file matches expectedArtifacts.file."""
        manifest_data = {
            "version": "1",
            "goal": "Create new module",
            "taskType": "create",
            "creatableFiles": ["maid_runner/coherence/validator.py"],
            "expectedArtifacts": {
                "file": "maid_runner/coherence/validator.py",
                "contains": [{"type": "class", "name": "CoherenceValidator"}],
            },
        }

        result = _is_valid_supersession(
            manifest_data=manifest_data,
            existing_file="maid_runner/coherence/validator.py",
        )

        assert result is True

    def test_returns_true_when_file_in_creatable_files(self) -> None:
        """_is_valid_supersession returns True when existing_file is in creatableFiles."""
        manifest_data = {
            "version": "1",
            "goal": "Create new module",
            "taskType": "create",
            "creatableFiles": ["maid_runner/new_module.py"],
            "expectedArtifacts": {
                "file": "maid_runner/new_module.py",
                "contains": [{"type": "function", "name": "helper"}],
            },
        }

        result = _is_valid_supersession(
            manifest_data=manifest_data,
            existing_file="maid_runner/new_module.py",
        )

        assert result is True

    def test_returns_false_when_different_expected_artifacts_file(self) -> None:
        """_is_valid_supersession returns False when expectedArtifacts.file is different."""
        manifest_data = {
            "version": "1",
            "goal": "Create new module",
            "taskType": "create",
            "creatableFiles": ["maid_runner/other.py"],
            "expectedArtifacts": {
                "file": "maid_runner/other.py",
                "contains": [{"type": "function", "name": "other_func"}],
            },
        }

        result = _is_valid_supersession(
            manifest_data=manifest_data,
            existing_file="maid_runner/validators/manifest.py",  # Different file
        )

        assert result is False

    def test_returns_false_when_no_expected_artifacts(self) -> None:
        """_is_valid_supersession returns False when expectedArtifacts is missing."""
        manifest_data = {
            "version": "1",
            "goal": "Create new module",
            "taskType": "create",
            "creatableFiles": ["maid_runner/other.py"],
        }

        result = _is_valid_supersession(
            manifest_data=manifest_data,
            existing_file="maid_runner/validators/manifest.py",
        )

        assert result is False


class TestCheckDuplicateArtifactsEdgeCases:
    """Edge case tests for check_duplicate_artifacts."""

    def test_handles_artifact_without_type(
        self,
        sample_system_artifacts: List[Dict[str, Any]],
        empty_knowledge_graph: KnowledgeGraph,
    ) -> None:
        """check_duplicate_artifacts handles artifacts without type field."""
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
        result = check_duplicate_artifacts(
            manifest_data=manifest_with_typeless_artifact,
            system_artifacts=sample_system_artifacts,
            graph=empty_knowledge_graph,
        )

        assert isinstance(result, list)

    def test_handles_empty_contains_list(
        self,
        sample_system_artifacts: List[Dict[str, Any]],
        empty_knowledge_graph: KnowledgeGraph,
    ) -> None:
        """check_duplicate_artifacts handles empty contains list."""
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

        result = check_duplicate_artifacts(
            manifest_data=manifest_with_empty_contains,
            system_artifacts=sample_system_artifacts,
            graph=empty_knowledge_graph,
        )

        assert isinstance(result, list)
        assert len(result) == 0

    def test_issue_has_location_field(
        self,
        manifest_with_duplicate_function: Dict[str, Any],
        sample_system_artifacts: List[Dict[str, Any]],
        empty_knowledge_graph: KnowledgeGraph,
    ) -> None:
        """check_duplicate_artifacts returns issue with location field."""
        result = check_duplicate_artifacts(
            manifest_data=manifest_with_duplicate_function,
            system_artifacts=sample_system_artifacts,
            graph=empty_knowledge_graph,
        )

        assert len(result) >= 1
        issue = result[0]
        # Location should be present (can be None or a string)
        assert hasattr(issue, "location")

    def test_same_name_different_type_not_duplicate(
        self,
        empty_knowledge_graph: KnowledgeGraph,
    ) -> None:
        """Artifact with same name but different type is not a duplicate."""
        system_artifacts = [
            {
                "name": "Validator",
                "type": "class",
                "file": "validators.py",
            },
        ]

        manifest_with_function = {
            "version": "1",
            "goal": "Create module",
            "taskType": "create",
            "creatableFiles": ["new_module.py"],
            "expectedArtifacts": {
                "file": "new_module.py",
                "contains": [
                    {
                        "type": "function",
                        "name": "Validator",
                    },  # Same name, different type
                ],
            },
        }

        result = check_duplicate_artifacts(
            manifest_data=manifest_with_function,
            system_artifacts=system_artifacts,
            graph=empty_knowledge_graph,
        )

        # Should not be flagged as duplicate since types differ
        assert len(result) == 0


class TestCheckDuplicateArtifactsIntegration:
    """Integration tests for check_duplicate_artifacts with KnowledgeGraph."""

    def test_works_with_populated_knowledge_graph(
        self,
        manifest_with_duplicate_function: Dict[str, Any],
        sample_system_artifacts: List[Dict[str, Any]],
    ) -> None:
        """check_duplicate_artifacts works with a populated KnowledgeGraph."""
        from maid_runner.graph.model import ManifestNode, FileNode, ArtifactNode

        graph = KnowledgeGraph()

        # Add some nodes to the graph
        manifest_node = ManifestNode(
            id="manifest:task-050",
            path="manifests/task-050.manifest.json",
            goal="Create validator",
            task_type="create",
            version="1",
        )
        graph.add_node(manifest_node)

        file_node = FileNode(
            id="file:validators/manifest.py",
            path="maid_runner/validators/manifest.py",
            status="tracked",
        )
        graph.add_node(file_node)

        artifact_node = ArtifactNode(
            id="artifact:validate_manifest",
            name="validate_manifest",
            artifact_type="function",
        )
        graph.add_node(artifact_node)

        result = check_duplicate_artifacts(
            manifest_data=manifest_with_duplicate_function,
            system_artifacts=sample_system_artifacts,
            graph=graph,
        )

        assert isinstance(result, list)
        # Should still detect duplicates
        assert len(result) >= 1

    def test_accepts_knowledge_graph_parameter(
        self,
        manifest_without_duplicates: Dict[str, Any],
        sample_system_artifacts: List[Dict[str, Any]],
        empty_knowledge_graph: KnowledgeGraph,
    ) -> None:
        """check_duplicate_artifacts accepts graph as a parameter."""
        result = check_duplicate_artifacts(
            manifest_data=manifest_without_duplicates,
            system_artifacts=sample_system_artifacts,
            graph=empty_knowledge_graph,
        )

        assert isinstance(result, list)
