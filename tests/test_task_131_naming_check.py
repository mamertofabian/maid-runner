"""Behavioral tests for Task 131: Naming Convention Compliance.

Tests the naming convention validation module that extracts naming patterns
from existing codebase artifacts and validates that new artifacts follow
similar conventions. Returns CoherenceIssue with IssueType.NAMING for any
naming violations.

Artifacts tested:
- check_naming_conventions(manifest_data, system_artifacts) -> List[CoherenceIssue]
- _extract_naming_patterns(system_artifacts: List[Dict]) -> Dict[str, List[str]]
- _validate_artifact_name(name, artifact_type, patterns) -> Optional[CoherenceIssue]
"""

import pytest
from typing import Any, Dict, List

from maid_runner.coherence.checks.naming_check import (
    check_naming_conventions,
    _extract_naming_patterns,
    _validate_artifact_name,
)
from maid_runner.coherence.result import (
    CoherenceIssue,
    IssueType,
    IssueSeverity,
)


# =============================================================================
# Fixtures
# =============================================================================


@pytest.fixture
def empty_system_artifacts() -> List[Dict[str, Any]]:
    """Create an empty list of system artifacts."""
    return []


@pytest.fixture
def system_artifacts_with_function_patterns() -> List[Dict[str, Any]]:
    """Create system artifacts with recognizable function naming patterns.

    Includes functions following get_*, fetch_*, create_*, and validate_* patterns.
    """
    return [
        {"name": "get_user", "type": "function", "file": "users.py"},
        {"name": "get_config", "type": "function", "file": "config.py"},
        {"name": "get_manifest", "type": "function", "file": "manifest.py"},
        {"name": "fetch_data", "type": "function", "file": "data.py"},
        {"name": "fetch_results", "type": "function", "file": "results.py"},
        {"name": "create_instance", "type": "function", "file": "factory.py"},
        {"name": "create_report", "type": "function", "file": "reports.py"},
        {"name": "validate_input", "type": "function", "file": "validation.py"},
        {"name": "validate_schema", "type": "function", "file": "schema.py"},
    ]


@pytest.fixture
def system_artifacts_with_class_patterns() -> List[Dict[str, Any]]:
    """Create system artifacts with recognizable class naming patterns.

    Includes classes following *Service, *Repository, and *Validator patterns.
    """
    return [
        {"name": "UserService", "type": "class", "file": "services/user.py"},
        {"name": "OrderService", "type": "class", "file": "services/order.py"},
        {"name": "PaymentService", "type": "class", "file": "services/payment.py"},
        {"name": "UserRepository", "type": "class", "file": "repos/user.py"},
        {"name": "OrderRepository", "type": "class", "file": "repos/order.py"},
        {"name": "InputValidator", "type": "class", "file": "validators/input.py"},
        {"name": "SchemaValidator", "type": "class", "file": "validators/schema.py"},
    ]


@pytest.fixture
def system_artifacts_with_mixed_patterns() -> List[Dict[str, Any]]:
    """Create system artifacts with both function and class naming patterns."""
    return [
        # Functions with get_* pattern
        {"name": "get_user", "type": "function", "file": "users.py"},
        {"name": "get_config", "type": "function", "file": "config.py"},
        {"name": "get_data", "type": "function", "file": "data.py"},
        # Functions with fetch_* pattern
        {"name": "fetch_results", "type": "function", "file": "results.py"},
        {"name": "fetch_records", "type": "function", "file": "records.py"},
        # Classes with *Service pattern
        {"name": "UserService", "type": "class", "file": "services/user.py"},
        {"name": "OrderService", "type": "class", "file": "services/order.py"},
        # Classes with *Repository pattern
        {"name": "UserRepository", "type": "class", "file": "repos/user.py"},
        {"name": "OrderRepository", "type": "class", "file": "repos/order.py"},
    ]


@pytest.fixture
def system_artifacts_without_patterns() -> List[Dict[str, Any]]:
    """Create system artifacts without recognizable naming patterns.

    Each artifact has a unique naming style with no common prefix/suffix.
    """
    return [
        {"name": "process", "type": "function", "file": "main.py"},
        {"name": "handle", "type": "function", "file": "handler.py"},
        {"name": "run", "type": "function", "file": "runner.py"},
        {"name": "Helper", "type": "class", "file": "helper.py"},
        {"name": "Manager", "type": "class", "file": "manager.py"},
        {"name": "Worker", "type": "class", "file": "worker.py"},
    ]


@pytest.fixture
def manifest_with_compliant_names() -> Dict[str, Any]:
    """Create a manifest with artifact names that follow established patterns."""
    return {
        "version": "1",
        "goal": "Add new user functions",
        "taskType": "create",
        "creatableFiles": ["maid_runner/new_module.py"],
        "expectedArtifacts": {
            "file": "maid_runner/new_module.py",
            "contains": [
                {"type": "function", "name": "get_session"},
                {"type": "function", "name": "fetch_profile"},
                {"type": "class", "name": "AuthService"},
            ],
        },
    }


@pytest.fixture
def manifest_with_non_compliant_names() -> Dict[str, Any]:
    """Create a manifest with artifact names that violate naming conventions."""
    return {
        "version": "1",
        "goal": "Add new module with unusual names",
        "taskType": "create",
        "creatableFiles": ["maid_runner/unusual.py"],
        "expectedArtifacts": {
            "file": "maid_runner/unusual.py",
            "contains": [
                {
                    "type": "function",
                    "name": "retrieve_data",
                },  # Should be get_* or fetch_*
                {"type": "function", "name": "make_request"},  # Should be create_*
                {
                    "type": "class",
                    "name": "DataHandler",
                },  # Should be *Service or *Repository
            ],
        },
    }


@pytest.fixture
def empty_manifest() -> Dict[str, Any]:
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
        "goal": "Manifest with empty artifacts",
        "taskType": "create",
        "creatableFiles": ["test.py"],
        "expectedArtifacts": {
            "file": "test.py",
            "contains": [],
        },
    }


# =============================================================================
# Tests for check_naming_conventions
# =============================================================================


class TestCheckNamingConventionsFunction:
    """Tests for the check_naming_conventions main function."""

    def test_returns_empty_list_when_names_follow_conventions(
        self,
        manifest_with_compliant_names: Dict[str, Any],
        system_artifacts_with_mixed_patterns: List[Dict[str, Any]],
    ) -> None:
        """check_naming_conventions returns empty list when all names follow conventions."""
        result = check_naming_conventions(
            manifest_data=manifest_with_compliant_names,
            system_artifacts=system_artifacts_with_mixed_patterns,
        )

        assert isinstance(result, list)
        assert len(result) == 0

    def test_returns_coherence_issue_with_naming_type_for_violations(
        self,
        manifest_with_non_compliant_names: Dict[str, Any],
        system_artifacts_with_mixed_patterns: List[Dict[str, Any]],
    ) -> None:
        """check_naming_conventions returns CoherenceIssue with IssueType.NAMING for violations."""
        result = check_naming_conventions(
            manifest_data=manifest_with_non_compliant_names,
            system_artifacts=system_artifacts_with_mixed_patterns,
        )

        assert len(result) >= 1
        for issue in result:
            assert isinstance(issue, CoherenceIssue)
            assert issue.issue_type == IssueType.NAMING

    def test_handles_empty_manifest(
        self,
        empty_manifest: Dict[str, Any],
        system_artifacts_with_mixed_patterns: List[Dict[str, Any]],
    ) -> None:
        """check_naming_conventions handles manifest without expectedArtifacts."""
        result = check_naming_conventions(
            manifest_data=empty_manifest,
            system_artifacts=system_artifacts_with_mixed_patterns,
        )

        assert isinstance(result, list)
        assert len(result) == 0

    def test_handles_empty_system_artifacts(
        self,
        manifest_with_non_compliant_names: Dict[str, Any],
        empty_system_artifacts: List[Dict[str, Any]],
    ) -> None:
        """check_naming_conventions returns empty list when system_artifacts is empty."""
        result = check_naming_conventions(
            manifest_data=manifest_with_non_compliant_names,
            system_artifacts=empty_system_artifacts,
        )

        assert isinstance(result, list)
        # No patterns to extract, so no violations can be detected
        assert len(result) == 0

    def test_issue_has_appropriate_warning_message(
        self,
        manifest_with_non_compliant_names: Dict[str, Any],
        system_artifacts_with_mixed_patterns: List[Dict[str, Any]],
    ) -> None:
        """check_naming_conventions returns issue with descriptive message."""
        result = check_naming_conventions(
            manifest_data=manifest_with_non_compliant_names,
            system_artifacts=system_artifacts_with_mixed_patterns,
        )

        assert len(result) >= 1
        issue = result[0]
        # Message should contain the artifact name
        assert len(issue.message) > 0
        # Message should be descriptive about the naming issue
        assert any(
            name in issue.message
            for name in ["retrieve_data", "make_request", "DataHandler"]
        )

    def test_issue_has_suggestion(
        self,
        manifest_with_non_compliant_names: Dict[str, Any],
        system_artifacts_with_mixed_patterns: List[Dict[str, Any]],
    ) -> None:
        """check_naming_conventions returns issue with helpful suggestion."""
        result = check_naming_conventions(
            manifest_data=manifest_with_non_compliant_names,
            system_artifacts=system_artifacts_with_mixed_patterns,
        )

        assert len(result) >= 1
        issue = result[0]
        assert issue.suggestion is not None
        assert len(issue.suggestion) > 0

    def test_handles_manifest_with_empty_contains(
        self,
        manifest_with_empty_contains: Dict[str, Any],
        system_artifacts_with_mixed_patterns: List[Dict[str, Any]],
    ) -> None:
        """check_naming_conventions handles manifest with empty contains list."""
        result = check_naming_conventions(
            manifest_data=manifest_with_empty_contains,
            system_artifacts=system_artifacts_with_mixed_patterns,
        )

        assert isinstance(result, list)
        assert len(result) == 0

    def test_issue_severity_is_warning(
        self,
        manifest_with_non_compliant_names: Dict[str, Any],
        system_artifacts_with_mixed_patterns: List[Dict[str, Any]],
    ) -> None:
        """check_naming_conventions returns issues with WARNING severity."""
        result = check_naming_conventions(
            manifest_data=manifest_with_non_compliant_names,
            system_artifacts=system_artifacts_with_mixed_patterns,
        )

        assert len(result) >= 1
        for issue in result:
            assert issue.severity == IssueSeverity.WARNING

    def test_detects_multiple_violations(
        self,
        system_artifacts_with_mixed_patterns: List[Dict[str, Any]],
    ) -> None:
        """check_naming_conventions detects multiple naming violations."""
        manifest_with_multiple_violations = {
            "version": "1",
            "goal": "Create module with violations",
            "taskType": "create",
            "creatableFiles": ["test.py"],
            "expectedArtifacts": {
                "file": "test.py",
                "contains": [
                    {"type": "function", "name": "retrieve_info"},  # Violation
                    {"type": "function", "name": "obtain_value"},  # Violation
                    {"type": "class", "name": "DataProcessor"},  # Violation
                ],
            },
        }

        result = check_naming_conventions(
            manifest_data=manifest_with_multiple_violations,
            system_artifacts=system_artifacts_with_mixed_patterns,
        )

        # Should detect at least some violations
        assert len(result) >= 1


# =============================================================================
# Tests for _extract_naming_patterns
# =============================================================================


class TestExtractNamingPatternsFunction:
    """Tests for the _extract_naming_patterns helper function."""

    def test_extracts_patterns_from_function_names(
        self,
        system_artifacts_with_function_patterns: List[Dict[str, Any]],
    ) -> None:
        """_extract_naming_patterns extracts patterns from function names."""
        result = _extract_naming_patterns(
            system_artifacts=system_artifacts_with_function_patterns
        )

        assert isinstance(result, dict)
        assert "function" in result
        patterns = result["function"]
        assert isinstance(patterns, list)
        # Should contain patterns like "get_*", "fetch_*", etc.
        assert len(patterns) >= 1

    def test_extracts_patterns_from_class_names(
        self,
        system_artifacts_with_class_patterns: List[Dict[str, Any]],
    ) -> None:
        """_extract_naming_patterns extracts patterns from class names."""
        result = _extract_naming_patterns(
            system_artifacts=system_artifacts_with_class_patterns
        )

        assert isinstance(result, dict)
        assert "class" in result
        patterns = result["class"]
        assert isinstance(patterns, list)
        # Should contain patterns like "*Service", "*Repository", etc.
        assert len(patterns) >= 1

    def test_returns_dict_mapping_artifact_types_to_patterns(
        self,
        system_artifacts_with_mixed_patterns: List[Dict[str, Any]],
    ) -> None:
        """_extract_naming_patterns returns dict mapping artifact types to patterns."""
        result = _extract_naming_patterns(
            system_artifacts=system_artifacts_with_mixed_patterns
        )

        assert isinstance(result, dict)
        # Should have entries for both function and class types
        for key in result:
            assert isinstance(key, str)
            assert isinstance(result[key], list)

    def test_handles_empty_system_artifacts(
        self,
        empty_system_artifacts: List[Dict[str, Any]],
    ) -> None:
        """_extract_naming_patterns handles empty system_artifacts list."""
        result = _extract_naming_patterns(system_artifacts=empty_system_artifacts)

        assert isinstance(result, dict)
        # Should return empty dict or dict with empty lists
        for key in result:
            assert isinstance(result[key], list)

    def test_handles_system_artifacts_without_recognizable_patterns(
        self,
        system_artifacts_without_patterns: List[Dict[str, Any]],
    ) -> None:
        """_extract_naming_patterns handles artifacts without recognizable patterns."""
        result = _extract_naming_patterns(
            system_artifacts=system_artifacts_without_patterns
        )

        assert isinstance(result, dict)
        # May return empty patterns or no patterns for each type
        # Implementation-specific behavior, but should not raise an exception

    def test_pattern_format_uses_wildcards(
        self,
        system_artifacts_with_function_patterns: List[Dict[str, Any]],
    ) -> None:
        """_extract_naming_patterns returns patterns using wildcard format."""
        result = _extract_naming_patterns(
            system_artifacts=system_artifacts_with_function_patterns
        )

        if "function" in result and len(result["function"]) > 0:
            # Patterns should include wildcards like "get_*" or similar notation
            patterns = result["function"]
            # At least some patterns should contain pattern markers
            assert any("*" in p or "_" in p for p in patterns)


# =============================================================================
# Tests for _validate_artifact_name
# =============================================================================


class TestValidateArtifactNameFunction:
    """Tests for the _validate_artifact_name helper function."""

    def test_returns_none_when_name_matches_pattern(self) -> None:
        """_validate_artifact_name returns None when name matches a pattern."""
        patterns = {
            "function": ["get_*", "fetch_*", "create_*"],
            "class": ["*Service", "*Repository"],
        }

        result = _validate_artifact_name(
            name="get_user",
            artifact_type="function",
            patterns=patterns,
        )

        assert result is None

    def test_returns_coherence_issue_when_name_does_not_match(self) -> None:
        """_validate_artifact_name returns CoherenceIssue when name doesn't match."""
        patterns = {
            "function": ["get_*", "fetch_*", "create_*"],
            "class": ["*Service", "*Repository"],
        }

        result = _validate_artifact_name(
            name="retrieve_data",
            artifact_type="function",
            patterns=patterns,
        )

        assert result is not None
        assert isinstance(result, CoherenceIssue)
        assert result.issue_type == IssueType.NAMING

    def test_handles_empty_patterns_dict(self) -> None:
        """_validate_artifact_name handles empty patterns dict."""
        result = _validate_artifact_name(
            name="any_function",
            artifact_type="function",
            patterns={},
        )

        # With no patterns, cannot determine violation - should return None
        assert result is None

    def test_handles_artifact_type_not_in_patterns(self) -> None:
        """_validate_artifact_name handles artifact type not present in patterns."""
        patterns = {
            "class": ["*Service", "*Repository"],
            # No "function" key
        }

        result = _validate_artifact_name(
            name="some_function",
            artifact_type="function",
            patterns=patterns,
        )

        # Type not in patterns, cannot determine violation - should return None
        assert result is None

    def test_is_case_sensitive(self) -> None:
        """_validate_artifact_name is case-sensitive when matching patterns."""
        patterns = {
            "class": ["*Service"],
        }

        # Exact case match should pass
        result_match = _validate_artifact_name(
            name="UserService",
            artifact_type="class",
            patterns=patterns,
        )
        assert result_match is None

        # Different case should fail
        result_no_match = _validate_artifact_name(
            name="userservice",
            artifact_type="class",
            patterns=patterns,
        )
        # Should return an issue because case doesn't match
        assert result_no_match is not None
        assert isinstance(result_no_match, CoherenceIssue)

    def test_matches_prefix_pattern(self) -> None:
        """_validate_artifact_name correctly matches prefix patterns like get_*."""
        patterns = {
            "function": ["get_*"],
        }

        # Should match
        result_match = _validate_artifact_name(
            name="get_user_data",
            artifact_type="function",
            patterns=patterns,
        )
        assert result_match is None

        # Should not match
        result_no_match = _validate_artifact_name(
            name="fetch_user_data",
            artifact_type="function",
            patterns=patterns,
        )
        assert result_no_match is not None

    def test_matches_suffix_pattern(self) -> None:
        """_validate_artifact_name correctly matches suffix patterns like *Service."""
        patterns = {
            "class": ["*Service"],
        }

        # Should match
        result_match = _validate_artifact_name(
            name="AuthenticationService",
            artifact_type="class",
            patterns=patterns,
        )
        assert result_match is None

        # Should not match
        result_no_match = _validate_artifact_name(
            name="AuthenticationHandler",
            artifact_type="class",
            patterns=patterns,
        )
        assert result_no_match is not None

    def test_issue_contains_artifact_name_in_message(self) -> None:
        """_validate_artifact_name returns issue with artifact name in message."""
        patterns = {
            "function": ["get_*", "fetch_*"],
        }

        result = _validate_artifact_name(
            name="retrieve_data",
            artifact_type="function",
            patterns=patterns,
        )

        assert result is not None
        assert "retrieve_data" in result.message

    def test_issue_has_suggestion(self) -> None:
        """_validate_artifact_name returns issue with suggestion."""
        patterns = {
            "function": ["get_*", "fetch_*"],
        }

        result = _validate_artifact_name(
            name="retrieve_data",
            artifact_type="function",
            patterns=patterns,
        )

        assert result is not None
        assert result.suggestion is not None
        assert len(result.suggestion) > 0


# =============================================================================
# Edge Cases and Integration Tests
# =============================================================================


class TestCheckNamingConventionsEdgeCases:
    """Edge case tests for check_naming_conventions."""

    def test_handles_artifact_without_type(
        self,
        system_artifacts_with_mixed_patterns: List[Dict[str, Any]],
    ) -> None:
        """check_naming_conventions handles artifacts without type field."""
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
        result = check_naming_conventions(
            manifest_data=manifest_with_typeless_artifact,
            system_artifacts=system_artifacts_with_mixed_patterns,
        )

        assert isinstance(result, list)

    def test_handles_artifact_without_name(
        self,
        system_artifacts_with_mixed_patterns: List[Dict[str, Any]],
    ) -> None:
        """check_naming_conventions handles artifacts without name field."""
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
        result = check_naming_conventions(
            manifest_data=manifest_with_nameless_artifact,
            system_artifacts=system_artifacts_with_mixed_patterns,
        )

        assert isinstance(result, list)

    def test_issue_has_location_field(
        self,
        manifest_with_non_compliant_names: Dict[str, Any],
        system_artifacts_with_mixed_patterns: List[Dict[str, Any]],
    ) -> None:
        """check_naming_conventions returns issue with location field."""
        result = check_naming_conventions(
            manifest_data=manifest_with_non_compliant_names,
            system_artifacts=system_artifacts_with_mixed_patterns,
        )

        assert len(result) >= 1
        issue = result[0]
        # Location should be present (can be None or a string)
        assert hasattr(issue, "location")

    def test_handles_system_artifacts_with_missing_fields(self) -> None:
        """check_naming_conventions handles system artifacts with missing fields."""
        incomplete_artifacts = [
            {"name": "get_user"},  # Missing type and file
            {"type": "function", "file": "test.py"},  # Missing name
            {"name": "SomeClass", "type": "class"},  # Missing file
        ]

        manifest = {
            "version": "1",
            "goal": "Test",
            "taskType": "create",
            "creatableFiles": ["test.py"],
            "expectedArtifacts": {
                "file": "test.py",
                "contains": [
                    {"type": "function", "name": "some_function"},
                ],
            },
        }

        # Should not raise an exception
        result = check_naming_conventions(
            manifest_data=manifest,
            system_artifacts=incomplete_artifacts,
        )

        assert isinstance(result, list)

    def test_private_artifacts_are_handled(
        self,
        system_artifacts_with_mixed_patterns: List[Dict[str, Any]],
    ) -> None:
        """check_naming_conventions handles private artifacts (with _ prefix)."""
        manifest_with_private = {
            "version": "1",
            "goal": "Create module with private functions",
            "taskType": "create",
            "creatableFiles": ["test.py"],
            "expectedArtifacts": {
                "file": "test.py",
                "contains": [
                    {"type": "function", "name": "_internal_helper"},
                    {"type": "function", "name": "__private_method"},
                ],
            },
        }

        # Should not raise an exception
        result = check_naming_conventions(
            manifest_data=manifest_with_private,
            system_artifacts=system_artifacts_with_mixed_patterns,
        )

        assert isinstance(result, list)
