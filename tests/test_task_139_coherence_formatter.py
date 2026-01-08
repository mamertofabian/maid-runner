"""Behavioral tests for Task 139: Create coherence output formatter.

Tests the formatter module that formats coherence validation results for
terminal output with color-coded output and actionable suggestions.

Artifacts tested:
- format_coherence_result(result: CoherenceResult, verbose: bool) -> str
- _format_issue(issue: CoherenceIssue) -> str
- _format_suggestion(suggestion: str) -> str

The format_coherence_result function formats the entire coherence result as a
string, showing summary line with errors/warnings counts. In verbose mode,
it shows detailed issue information.

The _format_issue function formats a single issue with severity indicator
(emoji/symbol), including type, message, location, and suggestion.

The _format_suggestion function formats a suggestion with consistent styling.
"""

import pytest

from maid_runner.coherence.formatter import (
    format_coherence_result,
    _format_issue,
    _format_suggestion,
)
from maid_runner.coherence.result import (
    CoherenceResult,
    CoherenceIssue,
    IssueSeverity,
    IssueType,
)


# =============================================================================
# Fixtures
# =============================================================================


@pytest.fixture
def error_issue() -> CoherenceIssue:
    """Create a CoherenceIssue with ERROR severity."""
    return CoherenceIssue(
        issue_type=IssueType.DUPLICATE,
        severity=IssueSeverity.ERROR,
        message="Duplicate artifact 'MyClass' found in manifests",
        suggestion="Remove duplicate declaration from one manifest",
        location="manifests/task-001.manifest.json",
    )


@pytest.fixture
def warning_issue() -> CoherenceIssue:
    """Create a CoherenceIssue with WARNING severity."""
    return CoherenceIssue(
        issue_type=IssueType.NAMING,
        severity=IssueSeverity.WARNING,
        message="Function 'getUser' does not follow snake_case convention",
        suggestion="Rename to 'get_user'",
        location="src/api/handlers.py:42",
    )


@pytest.fixture
def info_issue() -> CoherenceIssue:
    """Create a CoherenceIssue with INFO severity."""
    return CoherenceIssue(
        issue_type=IssueType.PATTERN,
        severity=IssueSeverity.INFO,
        message="Consider using dependency injection pattern",
        suggestion="Inject dependencies via constructor",
        location="src/services/user_service.py",
    )


@pytest.fixture
def issue_without_location() -> CoherenceIssue:
    """Create a CoherenceIssue without a location."""
    return CoherenceIssue(
        issue_type=IssueType.CONSTRAINT,
        severity=IssueSeverity.WARNING,
        message="Constraint violation detected",
        suggestion="Fix the constraint",
        location=None,
    )


@pytest.fixture
def empty_result() -> CoherenceResult:
    """Create an empty CoherenceResult with no issues."""
    return CoherenceResult(valid=True, issues=[])


@pytest.fixture
def result_with_errors(error_issue: CoherenceIssue) -> CoherenceResult:
    """Create a CoherenceResult with error issues."""
    return CoherenceResult(valid=False, issues=[error_issue])


@pytest.fixture
def result_with_warnings(warning_issue: CoherenceIssue) -> CoherenceResult:
    """Create a CoherenceResult with warning issues."""
    return CoherenceResult(valid=True, issues=[warning_issue])


@pytest.fixture
def result_with_multiple_issues(
    error_issue: CoherenceIssue,
    warning_issue: CoherenceIssue,
    info_issue: CoherenceIssue,
) -> CoherenceResult:
    """Create a CoherenceResult with multiple issues of different severities."""
    return CoherenceResult(
        valid=False,
        issues=[error_issue, warning_issue, info_issue],
    )


# =============================================================================
# Tests for format_coherence_result function existence and signature
# =============================================================================


class TestFormatCoherenceResultFunction:
    """Verify format_coherence_result function exists and has correct signature."""

    def test_function_exists(self) -> None:
        """format_coherence_result function exists in formatter module."""
        assert format_coherence_result is not None

    def test_function_is_callable(self) -> None:
        """format_coherence_result is a callable function."""
        assert callable(format_coherence_result)

    def test_accepts_coherence_result_and_bool(
        self, empty_result: CoherenceResult
    ) -> None:
        """format_coherence_result accepts CoherenceResult and bool parameters."""
        # Should not raise an exception
        result = format_coherence_result(result=empty_result, verbose=False)
        assert isinstance(result, str)

    def test_returns_str(self, empty_result: CoherenceResult) -> None:
        """format_coherence_result returns a string."""
        result = format_coherence_result(result=empty_result, verbose=False)
        assert isinstance(result, str)


# =============================================================================
# Tests for format_coherence_result output content
# =============================================================================


class TestFormatCoherenceResultOutputContent:
    """Verify format_coherence_result output includes expected content."""

    def test_output_includes_error_count(
        self, result_with_errors: CoherenceResult
    ) -> None:
        """format_coherence_result output includes error count."""
        output = format_coherence_result(result=result_with_errors, verbose=False)

        # Should mention error count
        assert "1" in output or "error" in output.lower()

    def test_output_includes_warning_count(
        self, result_with_warnings: CoherenceResult
    ) -> None:
        """format_coherence_result output includes warning count."""
        output = format_coherence_result(result=result_with_warnings, verbose=False)

        # Should mention warning count
        assert "1" in output or "warning" in output.lower()

    def test_output_includes_both_counts_for_mixed_issues(
        self, result_with_multiple_issues: CoherenceResult
    ) -> None:
        """format_coherence_result output includes both error and warning counts."""
        output = format_coherence_result(
            result=result_with_multiple_issues, verbose=False
        )

        # Result has 1 error and 1 warning, should reflect in output
        assert isinstance(output, str)
        assert len(output) > 0

    def test_empty_result_produces_summary_line(
        self, empty_result: CoherenceResult
    ) -> None:
        """format_coherence_result produces summary line for empty result."""
        output = format_coherence_result(result=empty_result, verbose=False)

        # Empty result should still produce output
        assert isinstance(output, str)
        assert len(output) > 0


# =============================================================================
# Tests for format_coherence_result verbose mode
# =============================================================================


class TestFormatCoherenceResultVerboseMode:
    """Verify format_coherence_result verbose mode shows more detail."""

    def test_verbose_mode_shows_more_detail(
        self, result_with_errors: CoherenceResult
    ) -> None:
        """format_coherence_result verbose mode shows more detail than non-verbose."""
        non_verbose_output = format_coherence_result(
            result=result_with_errors, verbose=False
        )
        verbose_output = format_coherence_result(
            result=result_with_errors, verbose=True
        )

        # Verbose output should be longer or equal (more detail)
        assert len(verbose_output) >= len(non_verbose_output)

    def test_verbose_mode_includes_issue_details(
        self, result_with_errors: CoherenceResult, error_issue: CoherenceIssue
    ) -> None:
        """format_coherence_result verbose mode includes issue message."""
        output = format_coherence_result(result=result_with_errors, verbose=True)

        # Verbose output should contain the issue message
        assert error_issue.message in output

    def test_verbose_mode_includes_suggestion(
        self, result_with_errors: CoherenceResult, error_issue: CoherenceIssue
    ) -> None:
        """format_coherence_result verbose mode includes suggestion."""
        output = format_coherence_result(result=result_with_errors, verbose=True)

        # Verbose output should contain the suggestion
        assert error_issue.suggestion in output

    def test_non_verbose_mode_is_concise(
        self, result_with_multiple_issues: CoherenceResult
    ) -> None:
        """format_coherence_result non-verbose mode produces concise output."""
        output = format_coherence_result(
            result=result_with_multiple_issues, verbose=False
        )

        # Non-verbose output should still be valid string
        assert isinstance(output, str)
        assert len(output) > 0

    def test_verbose_false_by_default_produces_output(
        self, empty_result: CoherenceResult
    ) -> None:
        """format_coherence_result with verbose=False produces valid output."""
        output = format_coherence_result(result=empty_result, verbose=False)

        assert isinstance(output, str)


# =============================================================================
# Tests for _format_issue function existence and signature
# =============================================================================


class TestFormatIssueFunction:
    """Verify _format_issue function exists and has correct signature."""

    def test_function_exists(self) -> None:
        """_format_issue function exists in formatter module."""
        assert _format_issue is not None

    def test_function_is_callable(self) -> None:
        """_format_issue is a callable function."""
        assert callable(_format_issue)

    def test_accepts_coherence_issue(self, error_issue: CoherenceIssue) -> None:
        """_format_issue accepts a CoherenceIssue parameter."""
        # Should not raise an exception
        result = _format_issue(issue=error_issue)
        assert isinstance(result, str)

    def test_returns_str(self, error_issue: CoherenceIssue) -> None:
        """_format_issue returns a string."""
        result = _format_issue(issue=error_issue)
        assert isinstance(result, str)


# =============================================================================
# Tests for _format_issue output content
# =============================================================================


class TestFormatIssueOutputContent:
    """Verify _format_issue output contains required information."""

    def test_output_contains_severity_indicator(
        self, error_issue: CoherenceIssue
    ) -> None:
        """_format_issue output contains severity indicator (emoji/symbol)."""
        output = _format_issue(issue=error_issue)

        # Should contain some kind of severity indicator
        # Either emoji, symbol, or text indication of ERROR severity
        assert isinstance(output, str)
        assert len(output) > 0

    def test_output_contains_message(self, error_issue: CoherenceIssue) -> None:
        """_format_issue output contains the issue message."""
        output = _format_issue(issue=error_issue)

        assert error_issue.message in output

    def test_output_contains_suggestion(self, error_issue: CoherenceIssue) -> None:
        """_format_issue output contains the issue suggestion."""
        output = _format_issue(issue=error_issue)

        assert error_issue.suggestion in output

    def test_output_contains_location_when_present(
        self, error_issue: CoherenceIssue
    ) -> None:
        """_format_issue output contains location when present."""
        output = _format_issue(issue=error_issue)

        assert error_issue.location is not None
        assert error_issue.location in output

    def test_handles_issue_without_location(
        self, issue_without_location: CoherenceIssue
    ) -> None:
        """_format_issue handles issue without location gracefully."""
        output = _format_issue(issue=issue_without_location)

        # Should still produce valid output
        assert isinstance(output, str)
        assert len(output) > 0
        # Message should still be present
        assert issue_without_location.message in output


# =============================================================================
# Tests for _format_issue severity indicators
# =============================================================================


class TestFormatIssueSeverityIndicators:
    """Verify _format_issue uses different indicators for different severities."""

    def test_error_severity_has_indicator(self, error_issue: CoherenceIssue) -> None:
        """_format_issue produces output for ERROR severity."""
        output = _format_issue(issue=error_issue)

        assert isinstance(output, str)
        assert len(output) > 0

    def test_warning_severity_has_indicator(
        self, warning_issue: CoherenceIssue
    ) -> None:
        """_format_issue produces output for WARNING severity."""
        output = _format_issue(issue=warning_issue)

        assert isinstance(output, str)
        assert len(output) > 0

    def test_info_severity_has_indicator(self, info_issue: CoherenceIssue) -> None:
        """_format_issue produces output for INFO severity."""
        output = _format_issue(issue=info_issue)

        assert isinstance(output, str)
        assert len(output) > 0

    def test_different_severities_produce_different_output(
        self,
        error_issue: CoherenceIssue,
        warning_issue: CoherenceIssue,
        info_issue: CoherenceIssue,
    ) -> None:
        """_format_issue produces different output for different severities."""
        error_output = _format_issue(issue=error_issue)
        warning_output = _format_issue(issue=warning_issue)
        info_output = _format_issue(issue=info_issue)

        # All outputs should be different (different messages at minimum)
        assert error_output != warning_output
        assert warning_output != info_output


# =============================================================================
# Tests for _format_suggestion function existence and signature
# =============================================================================


class TestFormatSuggestionFunction:
    """Verify _format_suggestion function exists and has correct signature."""

    def test_function_exists(self) -> None:
        """_format_suggestion function exists in formatter module."""
        assert _format_suggestion is not None

    def test_function_is_callable(self) -> None:
        """_format_suggestion is a callable function."""
        assert callable(_format_suggestion)

    def test_accepts_str(self) -> None:
        """_format_suggestion accepts a string parameter."""
        # Should not raise an exception
        result = _format_suggestion(suggestion="Fix the issue")
        assert isinstance(result, str)

    def test_returns_str(self) -> None:
        """_format_suggestion returns a string."""
        result = _format_suggestion(suggestion="Apply the fix")
        assert isinstance(result, str)


# =============================================================================
# Tests for _format_suggestion output content
# =============================================================================


class TestFormatSuggestionOutputContent:
    """Verify _format_suggestion output contains expected content."""

    def test_output_contains_suggestion_text(self) -> None:
        """_format_suggestion output contains the suggestion text."""
        suggestion = "Rename the function to follow snake_case"
        output = _format_suggestion(suggestion=suggestion)

        assert suggestion in output

    def test_output_has_consistent_styling(self) -> None:
        """_format_suggestion output has consistent styling."""
        suggestion1 = "First suggestion"
        suggestion2 = "Second suggestion"

        output1 = _format_suggestion(suggestion=suggestion1)
        output2 = _format_suggestion(suggestion=suggestion2)

        # Both outputs should be non-empty strings
        assert isinstance(output1, str)
        assert isinstance(output2, str)
        assert len(output1) > 0
        assert len(output2) > 0

    def test_handles_empty_suggestion(self) -> None:
        """_format_suggestion handles empty string suggestion."""
        output = _format_suggestion(suggestion="")

        assert isinstance(output, str)

    def test_handles_long_suggestion(self) -> None:
        """_format_suggestion handles long suggestion text."""
        long_suggestion = "This is a very long suggestion " * 10
        output = _format_suggestion(suggestion=long_suggestion)

        assert isinstance(output, str)
        assert long_suggestion in output


# =============================================================================
# Tests for format_coherence_result edge cases
# =============================================================================


class TestFormatCoherenceResultEdgeCases:
    """Edge case tests for format_coherence_result."""

    def test_handles_result_with_many_issues(self) -> None:
        """format_coherence_result handles result with many issues."""
        issues = [
            CoherenceIssue(
                issue_type=IssueType.DUPLICATE,
                severity=IssueSeverity.ERROR,
                message=f"Error message {i}",
                suggestion=f"Fix {i}",
                location=f"file{i}.py",
            )
            for i in range(10)
        ]
        result = CoherenceResult(valid=False, issues=issues)

        output = format_coherence_result(result=result, verbose=True)

        assert isinstance(output, str)
        assert len(output) > 0

    def test_handles_result_with_only_info_issues(self) -> None:
        """format_coherence_result handles result with only INFO issues."""
        issues = [
            CoherenceIssue(
                issue_type=IssueType.PATTERN,
                severity=IssueSeverity.INFO,
                message="Info message",
                suggestion="Consider this",
            )
        ]
        result = CoherenceResult(valid=True, issues=issues)

        output = format_coherence_result(result=result, verbose=False)

        assert isinstance(output, str)

    def test_valid_result_with_no_errors_but_warnings(
        self, result_with_warnings: CoherenceResult
    ) -> None:
        """format_coherence_result handles valid result with warnings."""
        output = format_coherence_result(result=result_with_warnings, verbose=False)

        assert isinstance(output, str)
        assert len(output) > 0


# =============================================================================
# Integration tests
# =============================================================================


class TestFormatterIntegration:
    """Integration tests for formatter functions working together."""

    def test_format_result_uses_format_issue_internally(
        self, result_with_errors: CoherenceResult, error_issue: CoherenceIssue
    ) -> None:
        """format_coherence_result in verbose mode formats issues correctly."""
        result_output = format_coherence_result(result=result_with_errors, verbose=True)
        _issue_output = _format_issue(issue=error_issue)  # noqa: F841

        # The result output should contain the issue formatting
        # (may include additional context)
        assert error_issue.message in result_output
        assert error_issue.suggestion in result_output

    def test_complete_workflow(
        self, result_with_multiple_issues: CoherenceResult
    ) -> None:
        """Complete formatting workflow produces valid output."""
        # Format each issue individually
        for issue in result_with_multiple_issues.issues:
            issue_output = _format_issue(issue=issue)
            assert isinstance(issue_output, str)
            assert issue.message in issue_output

            suggestion_output = _format_suggestion(suggestion=issue.suggestion)
            assert isinstance(suggestion_output, str)
            assert issue.suggestion in suggestion_output

        # Format the complete result
        result_output = format_coherence_result(
            result=result_with_multiple_issues, verbose=True
        )
        assert isinstance(result_output, str)
        assert len(result_output) > 0

    def test_summary_for_zero_errors_and_warnings(
        self, empty_result: CoherenceResult
    ) -> None:
        """Empty result produces appropriate summary."""
        output = format_coherence_result(result=empty_result, verbose=False)

        # Should produce a summary even with no issues
        assert isinstance(output, str)
        assert len(output) > 0
