"""Behavioral tests for Task 141: Add JSON output format for coherence validation.

Tests that verify the format_coherence_json function in maid_runner.cli.validate
properly formats CoherenceResult objects as JSON strings suitable for CI/CD
integration.

These tests verify:
- format_coherence_json function exists and is callable
- format_coherence_json accepts CoherenceResult and Path arguments
- format_coherence_json returns a string
- Output is valid JSON
- JSON includes "manifest", "valid", "summary", "issues" keys
- "summary" includes "total_issues", "errors", "warnings"
- "issues" is an array with correct structure for each issue
"""

import json
from pathlib import Path

from maid_runner.cli.validate import format_coherence_json
from maid_runner.coherence import (
    CoherenceResult,
    CoherenceIssue,
    IssueSeverity,
    IssueType,
)


class TestFormatCoherenceJsonExists:
    """Tests that verify format_coherence_json exists and is callable."""

    def test_format_coherence_json_exists(self) -> None:
        """format_coherence_json should be importable from maid_runner.cli.validate."""
        assert format_coherence_json is not None

    def test_format_coherence_json_is_callable(self) -> None:
        """format_coherence_json should be a callable function."""
        assert callable(format_coherence_json)


class TestFormatCoherenceJsonAcceptsCorrectArguments:
    """Tests that verify format_coherence_json accepts the expected arguments."""

    def test_accepts_coherence_result_and_path(self) -> None:
        """format_coherence_json should accept CoherenceResult and Path arguments."""
        result = CoherenceResult(valid=True, issues=[])
        manifest_path = Path("manifests/test.manifest.json")

        # Should not raise an exception
        output = format_coherence_json(result, manifest_path)
        assert output is not None

    def test_works_with_empty_issues(self) -> None:
        """format_coherence_json should work with empty issues list."""
        result = CoherenceResult(valid=True, issues=[])
        manifest_path = Path("manifests/test.manifest.json")

        output = format_coherence_json(result, manifest_path)
        assert isinstance(output, str)

    def test_works_with_issues(self) -> None:
        """format_coherence_json should work with non-empty issues list."""
        issue = CoherenceIssue(
            issue_type=IssueType.DUPLICATE,
            severity=IssueSeverity.ERROR,
            message="Duplicate artifact found",
            suggestion="Remove one of the duplicates",
            location="src/module.py",
        )
        result = CoherenceResult(valid=False, issues=[issue])
        manifest_path = Path("manifests/test.manifest.json")

        output = format_coherence_json(result, manifest_path)
        assert isinstance(output, str)


class TestFormatCoherenceJsonReturnsString:
    """Tests that verify format_coherence_json returns a string."""

    def test_returns_string(self) -> None:
        """format_coherence_json should return a string."""
        result = CoherenceResult(valid=True, issues=[])
        manifest_path = Path("manifests/test.manifest.json")

        output = format_coherence_json(result, manifest_path)
        assert isinstance(output, str)

    def test_returns_non_empty_string(self) -> None:
        """format_coherence_json should return a non-empty string."""
        result = CoherenceResult(valid=True, issues=[])
        manifest_path = Path("manifests/test.manifest.json")

        output = format_coherence_json(result, manifest_path)
        assert len(output) > 0


class TestFormatCoherenceJsonOutputIsValidJson:
    """Tests that verify format_coherence_json returns valid JSON."""

    def test_output_is_valid_json(self) -> None:
        """format_coherence_json output should be parseable as JSON."""
        result = CoherenceResult(valid=True, issues=[])
        manifest_path = Path("manifests/test.manifest.json")

        output = format_coherence_json(result, manifest_path)
        parsed = json.loads(output)
        assert parsed is not None

    def test_output_is_valid_json_with_issues(self) -> None:
        """format_coherence_json output with issues should be parseable as JSON."""
        issue = CoherenceIssue(
            issue_type=IssueType.SIGNATURE_CONFLICT,
            severity=IssueSeverity.WARNING,
            message="Signature mismatch",
            suggestion="Update signature",
            location="src/api.py:42",
        )
        result = CoherenceResult(valid=False, issues=[issue])
        manifest_path = Path("manifests/test.manifest.json")

        output = format_coherence_json(result, manifest_path)
        parsed = json.loads(output)
        assert parsed is not None


class TestFormatCoherenceJsonTopLevelKeys:
    """Tests that verify JSON includes required top-level keys."""

    def test_json_has_manifest_key(self) -> None:
        """JSON output should include 'manifest' key."""
        result = CoherenceResult(valid=True, issues=[])
        manifest_path = Path("manifests/test.manifest.json")

        output = format_coherence_json(result, manifest_path)
        parsed = json.loads(output)
        assert "manifest" in parsed

    def test_json_has_valid_key(self) -> None:
        """JSON output should include 'valid' key."""
        result = CoherenceResult(valid=True, issues=[])
        manifest_path = Path("manifests/test.manifest.json")

        output = format_coherence_json(result, manifest_path)
        parsed = json.loads(output)
        assert "valid" in parsed

    def test_json_has_summary_key(self) -> None:
        """JSON output should include 'summary' key."""
        result = CoherenceResult(valid=True, issues=[])
        manifest_path = Path("manifests/test.manifest.json")

        output = format_coherence_json(result, manifest_path)
        parsed = json.loads(output)
        assert "summary" in parsed

    def test_json_has_issues_key(self) -> None:
        """JSON output should include 'issues' key."""
        result = CoherenceResult(valid=True, issues=[])
        manifest_path = Path("manifests/test.manifest.json")

        output = format_coherence_json(result, manifest_path)
        parsed = json.loads(output)
        assert "issues" in parsed


class TestFormatCoherenceJsonManifestValue:
    """Tests that verify 'manifest' key has correct value."""

    def test_manifest_contains_path_string(self) -> None:
        """manifest value should be the string representation of the path."""
        result = CoherenceResult(valid=True, issues=[])
        manifest_path = Path("manifests/task-141.manifest.json")

        output = format_coherence_json(result, manifest_path)
        parsed = json.loads(output)
        assert parsed["manifest"] == "manifests/task-141.manifest.json"

    def test_manifest_handles_absolute_path(self) -> None:
        """manifest value should handle absolute paths."""
        result = CoherenceResult(valid=True, issues=[])
        manifest_path = Path("/home/user/manifests/test.manifest.json")

        output = format_coherence_json(result, manifest_path)
        parsed = json.loads(output)
        assert parsed["manifest"] == "/home/user/manifests/test.manifest.json"


class TestFormatCoherenceJsonValidValue:
    """Tests that verify 'valid' key has correct value."""

    def test_valid_true_when_result_is_valid(self) -> None:
        """valid should be true when CoherenceResult.valid is True."""
        result = CoherenceResult(valid=True, issues=[])
        manifest_path = Path("manifests/test.manifest.json")

        output = format_coherence_json(result, manifest_path)
        parsed = json.loads(output)
        assert parsed["valid"] is True

    def test_valid_false_when_result_is_invalid(self) -> None:
        """valid should be false when CoherenceResult.valid is False."""
        result = CoherenceResult(valid=False, issues=[])
        manifest_path = Path("manifests/test.manifest.json")

        output = format_coherence_json(result, manifest_path)
        parsed = json.loads(output)
        assert parsed["valid"] is False


class TestFormatCoherenceJsonSummaryStructure:
    """Tests that verify 'summary' has correct structure."""

    def test_summary_has_total_issues(self) -> None:
        """summary should include 'total_issues' key."""
        result = CoherenceResult(valid=True, issues=[])
        manifest_path = Path("manifests/test.manifest.json")

        output = format_coherence_json(result, manifest_path)
        parsed = json.loads(output)
        assert "total_issues" in parsed["summary"]

    def test_summary_has_errors(self) -> None:
        """summary should include 'errors' key."""
        result = CoherenceResult(valid=True, issues=[])
        manifest_path = Path("manifests/test.manifest.json")

        output = format_coherence_json(result, manifest_path)
        parsed = json.loads(output)
        assert "errors" in parsed["summary"]

    def test_summary_has_warnings(self) -> None:
        """summary should include 'warnings' key."""
        result = CoherenceResult(valid=True, issues=[])
        manifest_path = Path("manifests/test.manifest.json")

        output = format_coherence_json(result, manifest_path)
        parsed = json.loads(output)
        assert "warnings" in parsed["summary"]


class TestFormatCoherenceJsonSummaryValues:
    """Tests that verify 'summary' has correct values."""

    def test_total_issues_is_zero_when_no_issues(self) -> None:
        """total_issues should be 0 when there are no issues."""
        result = CoherenceResult(valid=True, issues=[])
        manifest_path = Path("manifests/test.manifest.json")

        output = format_coherence_json(result, manifest_path)
        parsed = json.loads(output)
        assert parsed["summary"]["total_issues"] == 0

    def test_total_issues_matches_issue_count(self) -> None:
        """total_issues should match the number of issues."""
        issues = [
            CoherenceIssue(
                issue_type=IssueType.DUPLICATE,
                severity=IssueSeverity.ERROR,
                message="First issue",
                suggestion="Fix it",
            ),
            CoherenceIssue(
                issue_type=IssueType.NAMING,
                severity=IssueSeverity.WARNING,
                message="Second issue",
                suggestion="Fix it too",
            ),
        ]
        result = CoherenceResult(valid=False, issues=issues)
        manifest_path = Path("manifests/test.manifest.json")

        output = format_coherence_json(result, manifest_path)
        parsed = json.loads(output)
        assert parsed["summary"]["total_issues"] == 2

    def test_errors_count_matches_error_severity_issues(self) -> None:
        """errors should count only ERROR severity issues."""
        issues = [
            CoherenceIssue(
                issue_type=IssueType.DUPLICATE,
                severity=IssueSeverity.ERROR,
                message="Error issue",
                suggestion="Fix it",
            ),
            CoherenceIssue(
                issue_type=IssueType.NAMING,
                severity=IssueSeverity.WARNING,
                message="Warning issue",
                suggestion="Fix it",
            ),
            CoherenceIssue(
                issue_type=IssueType.PATTERN,
                severity=IssueSeverity.ERROR,
                message="Another error",
                suggestion="Fix it",
            ),
        ]
        result = CoherenceResult(valid=False, issues=issues)
        manifest_path = Path("manifests/test.manifest.json")

        output = format_coherence_json(result, manifest_path)
        parsed = json.loads(output)
        assert parsed["summary"]["errors"] == 2

    def test_warnings_count_matches_warning_severity_issues(self) -> None:
        """warnings should count only WARNING severity issues."""
        issues = [
            CoherenceIssue(
                issue_type=IssueType.DUPLICATE,
                severity=IssueSeverity.ERROR,
                message="Error issue",
                suggestion="Fix it",
            ),
            CoherenceIssue(
                issue_type=IssueType.NAMING,
                severity=IssueSeverity.WARNING,
                message="Warning issue",
                suggestion="Fix it",
            ),
            CoherenceIssue(
                issue_type=IssueType.PATTERN,
                severity=IssueSeverity.WARNING,
                message="Another warning",
                suggestion="Fix it",
            ),
        ]
        result = CoherenceResult(valid=False, issues=issues)
        manifest_path = Path("manifests/test.manifest.json")

        output = format_coherence_json(result, manifest_path)
        parsed = json.loads(output)
        assert parsed["summary"]["warnings"] == 2


class TestFormatCoherenceJsonIssuesArray:
    """Tests that verify 'issues' is an array with correct structure."""

    def test_issues_is_array(self) -> None:
        """issues should be an array."""
        result = CoherenceResult(valid=True, issues=[])
        manifest_path = Path("manifests/test.manifest.json")

        output = format_coherence_json(result, manifest_path)
        parsed = json.loads(output)
        assert isinstance(parsed["issues"], list)

    def test_issues_array_is_empty_when_no_issues(self) -> None:
        """issues array should be empty when there are no issues."""
        result = CoherenceResult(valid=True, issues=[])
        manifest_path = Path("manifests/test.manifest.json")

        output = format_coherence_json(result, manifest_path)
        parsed = json.loads(output)
        assert len(parsed["issues"]) == 0

    def test_issues_array_length_matches_issue_count(self) -> None:
        """issues array length should match number of issues."""
        issues = [
            CoherenceIssue(
                issue_type=IssueType.DUPLICATE,
                severity=IssueSeverity.ERROR,
                message="First issue",
                suggestion="Fix it",
            ),
            CoherenceIssue(
                issue_type=IssueType.NAMING,
                severity=IssueSeverity.WARNING,
                message="Second issue",
                suggestion="Fix it",
            ),
        ]
        result = CoherenceResult(valid=False, issues=issues)
        manifest_path = Path("manifests/test.manifest.json")

        output = format_coherence_json(result, manifest_path)
        parsed = json.loads(output)
        assert len(parsed["issues"]) == 2


class TestFormatCoherenceJsonIssueStructure:
    """Tests that verify each issue object has correct structure."""

    def test_issue_has_type_key(self) -> None:
        """Each issue should have 'type' key."""
        issue = CoherenceIssue(
            issue_type=IssueType.DUPLICATE,
            severity=IssueSeverity.ERROR,
            message="Test",
            suggestion="Fix",
        )
        result = CoherenceResult(valid=False, issues=[issue])
        manifest_path = Path("manifests/test.manifest.json")

        output = format_coherence_json(result, manifest_path)
        parsed = json.loads(output)
        assert "type" in parsed["issues"][0]

    def test_issue_has_severity_key(self) -> None:
        """Each issue should have 'severity' key."""
        issue = CoherenceIssue(
            issue_type=IssueType.DUPLICATE,
            severity=IssueSeverity.ERROR,
            message="Test",
            suggestion="Fix",
        )
        result = CoherenceResult(valid=False, issues=[issue])
        manifest_path = Path("manifests/test.manifest.json")

        output = format_coherence_json(result, manifest_path)
        parsed = json.loads(output)
        assert "severity" in parsed["issues"][0]

    def test_issue_has_message_key(self) -> None:
        """Each issue should have 'message' key."""
        issue = CoherenceIssue(
            issue_type=IssueType.DUPLICATE,
            severity=IssueSeverity.ERROR,
            message="Test message",
            suggestion="Fix",
        )
        result = CoherenceResult(valid=False, issues=[issue])
        manifest_path = Path("manifests/test.manifest.json")

        output = format_coherence_json(result, manifest_path)
        parsed = json.loads(output)
        assert "message" in parsed["issues"][0]

    def test_issue_has_location_key(self) -> None:
        """Each issue should have 'location' key."""
        issue = CoherenceIssue(
            issue_type=IssueType.DUPLICATE,
            severity=IssueSeverity.ERROR,
            message="Test",
            suggestion="Fix",
            location="src/file.py:10",
        )
        result = CoherenceResult(valid=False, issues=[issue])
        manifest_path = Path("manifests/test.manifest.json")

        output = format_coherence_json(result, manifest_path)
        parsed = json.loads(output)
        assert "location" in parsed["issues"][0]

    def test_issue_has_suggestion_key(self) -> None:
        """Each issue should have 'suggestion' key."""
        issue = CoherenceIssue(
            issue_type=IssueType.DUPLICATE,
            severity=IssueSeverity.ERROR,
            message="Test",
            suggestion="Fix the issue",
        )
        result = CoherenceResult(valid=False, issues=[issue])
        manifest_path = Path("manifests/test.manifest.json")

        output = format_coherence_json(result, manifest_path)
        parsed = json.loads(output)
        assert "suggestion" in parsed["issues"][0]


class TestFormatCoherenceJsonIssueValues:
    """Tests that verify issue object values are correct."""

    def test_issue_type_value_is_enum_value(self) -> None:
        """Issue type should be the string value of the IssueType enum."""
        issue = CoherenceIssue(
            issue_type=IssueType.DUPLICATE,
            severity=IssueSeverity.ERROR,
            message="Test",
            suggestion="Fix",
        )
        result = CoherenceResult(valid=False, issues=[issue])
        manifest_path = Path("manifests/test.manifest.json")

        output = format_coherence_json(result, manifest_path)
        parsed = json.loads(output)
        assert parsed["issues"][0]["type"] == "duplicate"

    def test_issue_severity_value_is_enum_value(self) -> None:
        """Issue severity should be the string value of the IssueSeverity enum."""
        issue = CoherenceIssue(
            issue_type=IssueType.NAMING,
            severity=IssueSeverity.WARNING,
            message="Test",
            suggestion="Fix",
        )
        result = CoherenceResult(valid=False, issues=[issue])
        manifest_path = Path("manifests/test.manifest.json")

        output = format_coherence_json(result, manifest_path)
        parsed = json.loads(output)
        assert parsed["issues"][0]["severity"] == "warning"

    def test_issue_message_value_matches_input(self) -> None:
        """Issue message should match the input message."""
        issue = CoherenceIssue(
            issue_type=IssueType.PATTERN,
            severity=IssueSeverity.INFO,
            message="This is a detailed message",
            suggestion="Fix",
        )
        result = CoherenceResult(valid=True, issues=[issue])
        manifest_path = Path("manifests/test.manifest.json")

        output = format_coherence_json(result, manifest_path)
        parsed = json.loads(output)
        assert parsed["issues"][0]["message"] == "This is a detailed message"

    def test_issue_location_value_matches_input(self) -> None:
        """Issue location should match the input location."""
        issue = CoherenceIssue(
            issue_type=IssueType.BOUNDARY_VIOLATION,
            severity=IssueSeverity.ERROR,
            message="Test",
            suggestion="Fix",
            location="src/validators/check.py:42",
        )
        result = CoherenceResult(valid=False, issues=[issue])
        manifest_path = Path("manifests/test.manifest.json")

        output = format_coherence_json(result, manifest_path)
        parsed = json.loads(output)
        assert parsed["issues"][0]["location"] == "src/validators/check.py:42"

    def test_issue_location_can_be_none(self) -> None:
        """Issue location should be None when not provided."""
        issue = CoherenceIssue(
            issue_type=IssueType.DEPENDENCY,
            severity=IssueSeverity.WARNING,
            message="Test",
            suggestion="Fix",
            location=None,
        )
        result = CoherenceResult(valid=False, issues=[issue])
        manifest_path = Path("manifests/test.manifest.json")

        output = format_coherence_json(result, manifest_path)
        parsed = json.loads(output)
        assert parsed["issues"][0]["location"] is None

    def test_issue_suggestion_value_matches_input(self) -> None:
        """Issue suggestion should match the input suggestion."""
        issue = CoherenceIssue(
            issue_type=IssueType.CONSTRAINT,
            severity=IssueSeverity.ERROR,
            message="Test",
            suggestion="Apply this specific fix",
        )
        result = CoherenceResult(valid=False, issues=[issue])
        manifest_path = Path("manifests/test.manifest.json")

        output = format_coherence_json(result, manifest_path)
        parsed = json.loads(output)
        assert parsed["issues"][0]["suggestion"] == "Apply this specific fix"


class TestFormatCoherenceJsonCompleteExample:
    """Integration tests with complete realistic examples."""

    def test_complete_valid_result(self) -> None:
        """Test with complete valid result (no issues)."""
        result = CoherenceResult(valid=True, issues=[])
        manifest_path = Path("manifests/task-141.manifest.json")

        output = format_coherence_json(result, manifest_path)
        parsed = json.loads(output)

        assert parsed["manifest"] == "manifests/task-141.manifest.json"
        assert parsed["valid"] is True
        assert parsed["summary"]["total_issues"] == 0
        assert parsed["summary"]["errors"] == 0
        assert parsed["summary"]["warnings"] == 0
        assert parsed["issues"] == []

    def test_complete_invalid_result_with_multiple_issues(self) -> None:
        """Test with complete invalid result containing multiple issues."""
        issues = [
            CoherenceIssue(
                issue_type=IssueType.DUPLICATE,
                severity=IssueSeverity.ERROR,
                message="Duplicate artifact 'validate' in manifests",
                suggestion="Remove duplicate definition from one manifest",
                location="manifests/task-010.manifest.json",
            ),
            CoherenceIssue(
                issue_type=IssueType.NAMING,
                severity=IssueSeverity.WARNING,
                message="Function 'validateData' should use snake_case",
                suggestion="Rename to 'validate_data'",
                location="src/validators.py:25",
            ),
            CoherenceIssue(
                issue_type=IssueType.PATTERN,
                severity=IssueSeverity.INFO,
                message="Consider using factory pattern",
                suggestion="Refactor to use factory",
                location=None,
            ),
        ]
        result = CoherenceResult(valid=False, issues=issues)
        manifest_path = Path("manifests/task-141.manifest.json")

        output = format_coherence_json(result, manifest_path)
        parsed = json.loads(output)

        assert parsed["manifest"] == "manifests/task-141.manifest.json"
        assert parsed["valid"] is False
        assert parsed["summary"]["total_issues"] == 3
        assert parsed["summary"]["errors"] == 1
        assert parsed["summary"]["warnings"] == 1

        assert len(parsed["issues"]) == 3

        assert parsed["issues"][0]["type"] == "duplicate"
        assert parsed["issues"][0]["severity"] == "error"
        assert (
            parsed["issues"][0]["message"]
            == "Duplicate artifact 'validate' in manifests"
        )
        assert parsed["issues"][0]["location"] == "manifests/task-010.manifest.json"

        assert parsed["issues"][1]["type"] == "naming"
        assert parsed["issues"][1]["severity"] == "warning"

        assert parsed["issues"][2]["type"] == "pattern"
        assert parsed["issues"][2]["severity"] == "info"
        assert parsed["issues"][2]["location"] is None
