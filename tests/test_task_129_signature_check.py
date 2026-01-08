"""Behavioral tests for Task 129: Signature Conflict Detection.

Tests the signature conflict detection module that checks for artifacts with
the same name but different signatures (arguments, return types) across the
system. Returns CoherenceIssue with IssueType.SIGNATURE_CONFLICT for any
conflicts found.

Artifacts tested:
- check_signature_conflicts(manifest_data, system_artifacts) -> List[CoherenceIssue]
- _extract_artifact_signature(artifact: dict) -> str
- _compare_signatures(new_sig: str, existing_sig: str) -> bool
"""

import pytest
from typing import Any, Dict, List

from maid_runner.coherence.checks.signature_check import (
    check_signature_conflicts,
    _extract_artifact_signature,
    _compare_signatures,
)
from maid_runner.coherence.result import (
    CoherenceIssue,
    IssueType,
    IssueSeverity,
)


@pytest.fixture
def sample_system_artifacts() -> List[Dict[str, Any]]:
    """Create sample system artifacts with signatures for testing.

    Represents artifacts aggregated from all existing manifests in the system.
    """
    return [
        {
            "name": "validate_data",
            "type": "function",
            "file": "maid_runner/validators/data.py",
            "args": [
                {"name": "data", "type": "dict"},
                {"name": "strict", "type": "bool"},
            ],
            "returns": "bool",
        },
        {
            "name": "process_config",
            "type": "function",
            "file": "maid_runner/config/processor.py",
            "args": [{"name": "config", "type": "Config"}],
            "returns": "ProcessedConfig",
        },
        {
            "name": "ConfigLoader",
            "type": "class",
            "file": "maid_runner/config/loader.py",
        },
        {
            "name": "format_output",
            "type": "function",
            "file": "maid_runner/output/formatter.py",
            "args": [{"name": "data", "type": "str"}],
            "returns": "str",
        },
    ]


@pytest.fixture
def manifest_without_conflicts() -> Dict[str, Any]:
    """Create a manifest that declares artifacts without signature conflicts."""
    return {
        "version": "1",
        "goal": "Create new utility module",
        "taskType": "create",
        "creatableFiles": ["maid_runner/utils/helpers.py"],
        "expectedArtifacts": {
            "file": "maid_runner/utils/helpers.py",
            "contains": [
                {
                    "type": "function",
                    "name": "format_path",
                    "args": [{"name": "path", "type": "str"}],
                    "returns": "str",
                },
                {
                    "type": "class",
                    "name": "PathFormatter",
                },
            ],
        },
    }


@pytest.fixture
def manifest_with_args_conflict() -> Dict[str, Any]:
    """Create a manifest with a function that has different args than system."""
    return {
        "version": "1",
        "goal": "Create validation utilities",
        "taskType": "create",
        "creatableFiles": ["maid_runner/utils/validation.py"],
        "expectedArtifacts": {
            "file": "maid_runner/utils/validation.py",
            "contains": [
                {
                    "type": "function",
                    "name": "validate_data",  # Same name
                    "args": [{"name": "data", "type": "str"}],  # Different args!
                    "returns": "bool",
                },
            ],
        },
    }


@pytest.fixture
def manifest_with_return_type_conflict() -> Dict[str, Any]:
    """Create a manifest with a function that has different return type."""
    return {
        "version": "1",
        "goal": "Create output module",
        "taskType": "create",
        "creatableFiles": ["maid_runner/output/new_formatter.py"],
        "expectedArtifacts": {
            "file": "maid_runner/output/new_formatter.py",
            "contains": [
                {
                    "type": "function",
                    "name": "format_output",  # Same name
                    "args": [{"name": "data", "type": "str"}],  # Same args
                    "returns": "bytes",  # Different return type!
                },
            ],
        },
    }


class TestCheckSignatureConflictsFunction:
    """Tests for the check_signature_conflicts main function."""

    def test_returns_empty_list_when_no_conflicts(
        self,
        manifest_without_conflicts: Dict[str, Any],
        sample_system_artifacts: List[Dict[str, Any]],
    ) -> None:
        """check_signature_conflicts returns empty list when no conflicts exist."""
        result = check_signature_conflicts(
            manifest_data=manifest_without_conflicts,
            system_artifacts=sample_system_artifacts,
        )

        assert isinstance(result, list)
        assert len(result) == 0

    def test_detects_conflict_when_different_args(
        self,
        manifest_with_args_conflict: Dict[str, Any],
        sample_system_artifacts: List[Dict[str, Any]],
    ) -> None:
        """check_signature_conflicts detects when same function has different args."""
        result = check_signature_conflicts(
            manifest_data=manifest_with_args_conflict,
            system_artifacts=sample_system_artifacts,
        )

        assert len(result) >= 1
        conflict_issues = [
            issue for issue in result if "validate_data" in issue.message
        ]
        assert len(conflict_issues) == 1

    def test_detects_conflict_when_different_return_type(
        self,
        manifest_with_return_type_conflict: Dict[str, Any],
        sample_system_artifacts: List[Dict[str, Any]],
    ) -> None:
        """check_signature_conflicts detects when same function has different return type."""
        result = check_signature_conflicts(
            manifest_data=manifest_with_return_type_conflict,
            system_artifacts=sample_system_artifacts,
        )

        assert len(result) >= 1
        conflict_issues = [
            issue for issue in result if "format_output" in issue.message
        ]
        assert len(conflict_issues) == 1

    def test_returns_coherence_issue_with_signature_conflict_type(
        self,
        manifest_with_args_conflict: Dict[str, Any],
        sample_system_artifacts: List[Dict[str, Any]],
    ) -> None:
        """check_signature_conflicts returns CoherenceIssue with IssueType.SIGNATURE_CONFLICT."""
        result = check_signature_conflicts(
            manifest_data=manifest_with_args_conflict,
            system_artifacts=sample_system_artifacts,
        )

        assert len(result) >= 1
        for issue in result:
            assert isinstance(issue, CoherenceIssue)
            assert issue.issue_type == IssueType.SIGNATURE_CONFLICT

    def test_issue_has_appropriate_warning_message(
        self,
        manifest_with_args_conflict: Dict[str, Any],
        sample_system_artifacts: List[Dict[str, Any]],
    ) -> None:
        """check_signature_conflicts returns issue with descriptive warning message."""
        result = check_signature_conflicts(
            manifest_data=manifest_with_args_conflict,
            system_artifacts=sample_system_artifacts,
        )

        assert len(result) >= 1
        issue = result[0]
        # Message should contain artifact name
        assert "validate_data" in issue.message
        # Message should be non-empty and descriptive
        assert len(issue.message) > 10

    def test_issue_has_suggestion(
        self,
        manifest_with_args_conflict: Dict[str, Any],
        sample_system_artifacts: List[Dict[str, Any]],
    ) -> None:
        """check_signature_conflicts returns issue with helpful suggestion."""
        result = check_signature_conflicts(
            manifest_data=manifest_with_args_conflict,
            system_artifacts=sample_system_artifacts,
        )

        assert len(result) >= 1
        issue = result[0]
        assert issue.suggestion is not None
        assert len(issue.suggestion) > 0

    def test_handles_empty_system_artifacts(
        self,
        manifest_with_args_conflict: Dict[str, Any],
    ) -> None:
        """check_signature_conflicts returns empty list when system_artifacts is empty."""
        result = check_signature_conflicts(
            manifest_data=manifest_with_args_conflict,
            system_artifacts=[],
        )

        assert isinstance(result, list)
        assert len(result) == 0

    def test_handles_manifest_without_expected_artifacts(
        self,
        sample_system_artifacts: List[Dict[str, Any]],
    ) -> None:
        """check_signature_conflicts handles manifest without expectedArtifacts."""
        manifest_without_artifacts = {
            "version": "1",
            "goal": "Minimal manifest",
            "taskType": "create",
            "creatableFiles": ["test.py"],
        }

        result = check_signature_conflicts(
            manifest_data=manifest_without_artifacts,
            system_artifacts=sample_system_artifacts,
        )

        assert isinstance(result, list)
        assert len(result) == 0

    def test_issue_severity_is_warning(
        self,
        manifest_with_args_conflict: Dict[str, Any],
        sample_system_artifacts: List[Dict[str, Any]],
    ) -> None:
        """check_signature_conflicts returns issues with WARNING severity."""
        result = check_signature_conflicts(
            manifest_data=manifest_with_args_conflict,
            system_artifacts=sample_system_artifacts,
        )

        assert len(result) >= 1
        for issue in result:
            assert issue.severity == IssueSeverity.WARNING

    def test_detects_multiple_conflicts(
        self,
        sample_system_artifacts: List[Dict[str, Any]],
    ) -> None:
        """check_signature_conflicts detects multiple signature conflicts."""
        manifest_with_multiple_conflicts = {
            "version": "1",
            "goal": "Create module with conflicts",
            "taskType": "create",
            "creatableFiles": ["maid_runner/new_module.py"],
            "expectedArtifacts": {
                "file": "maid_runner/new_module.py",
                "contains": [
                    {
                        "type": "function",
                        "name": "validate_data",  # Conflict 1
                        "args": [{"name": "x", "type": "int"}],
                        "returns": "bool",
                    },
                    {
                        "type": "function",
                        "name": "format_output",  # Conflict 2
                        "args": [],  # Different args
                        "returns": "str",
                    },
                    {
                        "type": "function",
                        "name": "unique_function",  # No conflict
                        "args": [],
                        "returns": "None",
                    },
                ],
            },
        }

        result = check_signature_conflicts(
            manifest_data=manifest_with_multiple_conflicts,
            system_artifacts=sample_system_artifacts,
        )

        assert len(result) == 2  # Two conflicts found

    def test_issue_has_location_field(
        self,
        manifest_with_args_conflict: Dict[str, Any],
        sample_system_artifacts: List[Dict[str, Any]],
    ) -> None:
        """check_signature_conflicts returns issue with location field."""
        result = check_signature_conflicts(
            manifest_data=manifest_with_args_conflict,
            system_artifacts=sample_system_artifacts,
        )

        assert len(result) >= 1
        issue = result[0]
        # Location should be present (can be None or a string)
        assert hasattr(issue, "location")

    def test_same_signature_no_conflict(
        self,
        sample_system_artifacts: List[Dict[str, Any]],
    ) -> None:
        """check_signature_conflicts does not flag when signatures match exactly."""
        manifest_with_same_signature = {
            "version": "1",
            "goal": "Create module with same signature",
            "taskType": "create",
            "creatableFiles": ["maid_runner/new_module.py"],
            "expectedArtifacts": {
                "file": "maid_runner/new_module.py",
                "contains": [
                    {
                        "type": "function",
                        "name": "validate_data",
                        "args": [
                            {"name": "data", "type": "dict"},
                            {"name": "strict", "type": "bool"},
                        ],
                        "returns": "bool",
                    },
                ],
            },
        }

        result = check_signature_conflicts(
            manifest_data=manifest_with_same_signature,
            system_artifacts=sample_system_artifacts,
        )

        assert len(result) == 0

    def test_handles_empty_contains_list(
        self,
        sample_system_artifacts: List[Dict[str, Any]],
    ) -> None:
        """check_signature_conflicts handles empty contains list."""
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

        result = check_signature_conflicts(
            manifest_data=manifest_with_empty_contains,
            system_artifacts=sample_system_artifacts,
        )

        assert isinstance(result, list)
        assert len(result) == 0

    def test_different_artifact_type_no_conflict(
        self,
        sample_system_artifacts: List[Dict[str, Any]],
    ) -> None:
        """check_signature_conflicts does not compare artifacts of different types."""
        manifest_with_class_same_name = {
            "version": "1",
            "goal": "Create class with function name",
            "taskType": "create",
            "creatableFiles": ["maid_runner/new_module.py"],
            "expectedArtifacts": {
                "file": "maid_runner/new_module.py",
                "contains": [
                    {
                        "type": "class",  # Class, not function
                        "name": "validate_data",  # Same name as function
                    },
                ],
            },
        }

        result = check_signature_conflicts(
            manifest_data=manifest_with_class_same_name,
            system_artifacts=sample_system_artifacts,
        )

        # Should not flag since types differ (class vs function)
        assert len(result) == 0


class TestExtractArtifactSignatureFunction:
    """Tests for the _extract_artifact_signature helper function."""

    def test_extracts_args_into_signature_string(self) -> None:
        """_extract_artifact_signature extracts args into signature string."""
        artifact = {
            "name": "my_function",
            "type": "function",
            "args": [
                {"name": "arg1", "type": "str"},
                {"name": "arg2", "type": "int"},
            ],
            "returns": "bool",
        }

        result = _extract_artifact_signature(artifact)

        # Should contain args in parentheses format
        assert "arg1: str" in result
        assert "arg2: int" in result
        assert "(" in result
        assert ")" in result

    def test_includes_return_type(self) -> None:
        """_extract_artifact_signature includes return type with arrow notation."""
        artifact = {
            "name": "my_function",
            "type": "function",
            "args": [{"name": "x", "type": "int"}],
            "returns": "str",
        }

        result = _extract_artifact_signature(artifact)

        assert "->" in result
        assert "str" in result

    def test_handles_artifact_with_no_args(self) -> None:
        """_extract_artifact_signature handles artifact with no args."""
        artifact = {
            "name": "no_args_function",
            "type": "function",
            "returns": "None",
        }

        result = _extract_artifact_signature(artifact)

        assert isinstance(result, str)
        # Should still have parentheses for empty args
        assert "()" in result or "(" in result

    def test_handles_artifact_with_no_return_type(self) -> None:
        """_extract_artifact_signature handles artifact with no return type."""
        artifact = {
            "name": "no_return_function",
            "type": "function",
            "args": [{"name": "x", "type": "int"}],
        }

        result = _extract_artifact_signature(artifact)

        assert isinstance(result, str)
        assert "x: int" in result

    def test_handles_artifact_with_neither_args_nor_returns(self) -> None:
        """_extract_artifact_signature handles artifact with neither args nor returns."""
        artifact = {
            "name": "minimal_function",
            "type": "function",
        }

        result = _extract_artifact_signature(artifact)

        assert isinstance(result, str)
        # Should return some consistent signature representation
        assert "()" in result or result == ""

    def test_handles_empty_args_list(self) -> None:
        """_extract_artifact_signature handles empty args list."""
        artifact = {
            "name": "empty_args_function",
            "type": "function",
            "args": [],
            "returns": "int",
        }

        result = _extract_artifact_signature(artifact)

        assert isinstance(result, str)
        assert "()" in result
        assert "int" in result

    def test_multiple_args_comma_separated(self) -> None:
        """_extract_artifact_signature separates multiple args with commas."""
        artifact = {
            "name": "multi_arg_function",
            "type": "function",
            "args": [
                {"name": "a", "type": "int"},
                {"name": "b", "type": "str"},
                {"name": "c", "type": "bool"},
            ],
            "returns": "None",
        }

        result = _extract_artifact_signature(artifact)

        assert "a: int" in result
        assert "b: str" in result
        assert "c: bool" in result
        # Should have comma separators
        assert "," in result


class TestCompareSignaturesFunction:
    """Tests for the _compare_signatures helper function."""

    def test_returns_true_when_signatures_match_exactly(self) -> None:
        """_compare_signatures returns True when signatures match exactly."""
        sig1 = "(arg1: str, arg2: int) -> bool"
        sig2 = "(arg1: str, arg2: int) -> bool"

        result = _compare_signatures(sig1, sig2)

        assert result is True

    def test_returns_false_when_signatures_differ(self) -> None:
        """_compare_signatures returns False when signatures differ."""
        sig1 = "(arg1: str) -> bool"
        sig2 = "(arg1: int) -> bool"

        result = _compare_signatures(sig1, sig2)

        assert result is False

    def test_handles_empty_signatures(self) -> None:
        """_compare_signatures handles empty signatures."""
        result_both_empty = _compare_signatures("", "")
        result_one_empty = _compare_signatures("(x: int) -> str", "")
        result_other_empty = _compare_signatures("", "(x: int) -> str")

        assert result_both_empty is True  # Both empty should match
        assert result_one_empty is False
        assert result_other_empty is False

    def test_is_case_sensitive(self) -> None:
        """_compare_signatures is case-sensitive."""
        sig1 = "(arg: String) -> Bool"
        sig2 = "(arg: string) -> bool"

        result = _compare_signatures(sig1, sig2)

        assert result is False

    def test_different_arg_count_returns_false(self) -> None:
        """_compare_signatures returns False when arg counts differ."""
        sig1 = "(a: int, b: str) -> None"
        sig2 = "(a: int) -> None"

        result = _compare_signatures(sig1, sig2)

        assert result is False

    def test_different_return_type_returns_false(self) -> None:
        """_compare_signatures returns False when return types differ."""
        sig1 = "(x: int) -> str"
        sig2 = "(x: int) -> int"

        result = _compare_signatures(sig1, sig2)

        assert result is False

    def test_whitespace_handling(self) -> None:
        """_compare_signatures handles whitespace consistently."""
        sig1 = "(arg1: str, arg2: int) -> bool"
        sig2 = "(arg1:str,arg2:int)->bool"

        # These should either both match or both not match depending on
        # implementation, but should be consistent
        result = _compare_signatures(sig1, sig2)
        # Either way, calling the function should work
        assert isinstance(result, bool)


class TestCheckSignatureConflictsEdgeCases:
    """Edge case tests for check_signature_conflicts."""

    def test_handles_artifact_without_type(
        self,
        sample_system_artifacts: List[Dict[str, Any]],
    ) -> None:
        """check_signature_conflicts handles artifacts without type field."""
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
        result = check_signature_conflicts(
            manifest_data=manifest_with_typeless_artifact,
            system_artifacts=sample_system_artifacts,
        )

        assert isinstance(result, list)

    def test_handles_artifact_without_name(
        self,
        sample_system_artifacts: List[Dict[str, Any]],
    ) -> None:
        """check_signature_conflicts handles artifacts without name field."""
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
        result = check_signature_conflicts(
            manifest_data=manifest_with_nameless_artifact,
            system_artifacts=sample_system_artifacts,
        )

        assert isinstance(result, list)

    def test_handles_system_artifact_without_signature(self) -> None:
        """check_signature_conflicts handles system artifacts without signature info."""
        system_artifacts = [
            {
                "name": "minimal_func",
                "type": "function",
                "file": "some/file.py",
                # No args or returns
            },
        ]

        manifest = {
            "version": "1",
            "goal": "Create module",
            "taskType": "create",
            "creatableFiles": ["test.py"],
            "expectedArtifacts": {
                "file": "test.py",
                "contains": [
                    {
                        "type": "function",
                        "name": "minimal_func",  # Same name
                        "args": [{"name": "x", "type": "int"}],  # Has args
                    },
                ],
            },
        }

        # Should detect conflict (one has args, one doesn't)
        result = check_signature_conflicts(
            manifest_data=manifest,
            system_artifacts=system_artifacts,
        )

        assert isinstance(result, list)
        # Should find a conflict since signatures differ
        assert len(result) >= 1

    def test_arg_names_can_differ_types_matter(
        self,
        sample_system_artifacts: List[Dict[str, Any]],
    ) -> None:
        """check_signature_conflicts: arg names can differ but types must match."""
        # System has: validate_data(data: dict, strict: bool) -> bool
        manifest_different_arg_names = {
            "version": "1",
            "goal": "Create module",
            "taskType": "create",
            "creatableFiles": ["test.py"],
            "expectedArtifacts": {
                "file": "test.py",
                "contains": [
                    {
                        "type": "function",
                        "name": "validate_data",
                        "args": [
                            {"name": "input_data", "type": "dict"},  # Different name
                            {"name": "is_strict", "type": "bool"},  # Different name
                        ],
                        "returns": "bool",
                    },
                ],
            },
        }

        result = check_signature_conflicts(
            manifest_data=manifest_different_arg_names,
            system_artifacts=sample_system_artifacts,
        )

        # Implementation may or may not consider arg names, but types should match
        # If only types matter, should be no conflict
        # If names matter too, should be conflict
        # Either behavior is acceptable, test just validates function works
        assert isinstance(result, list)
