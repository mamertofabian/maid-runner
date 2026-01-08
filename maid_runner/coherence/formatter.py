"""
Output formatter for coherence validation results.

This module provides functions for formatting coherence validation results
for terminal output with color-coded severity indicators and actionable
suggestions.

Module Organization:
    - format_coherence_result: Formats the entire CoherenceResult
    - _format_issue: Formats a single CoherenceIssue with severity indicator
    - _format_suggestion: Formats a suggestion with consistent styling

Usage:
    from maid_runner.coherence.formatter import format_coherence_result
    from maid_runner.coherence.result import CoherenceResult

    result = CoherenceResult(valid=True, issues=[])
    output = format_coherence_result(result=result, verbose=False)
    print(output)
"""

from maid_runner.coherence.result import CoherenceResult, CoherenceIssue, IssueSeverity


# Severity indicators using Unicode symbols for terminal output
_SEVERITY_INDICATORS = {
    IssueSeverity.ERROR: "\u274c",  # Red X
    IssueSeverity.WARNING: "\u26a0\ufe0f",  # Warning sign
    IssueSeverity.INFO: "\u2139\ufe0f",  # Information symbol
}

# Severity labels for output
_SEVERITY_LABELS = {
    IssueSeverity.ERROR: "ERROR",
    IssueSeverity.WARNING: "WARNING",
    IssueSeverity.INFO: "INFO",
}


def format_coherence_result(result: CoherenceResult, verbose: bool) -> str:
    """Format the entire coherence result as a string.

    Formats the coherence validation result for terminal output. In non-verbose
    mode, shows a summary line with error and warning counts. In verbose mode,
    includes detailed information for each issue.

    Args:
        result: The CoherenceResult to format.
        verbose: If True, show detailed issue information.

    Returns:
        Formatted string representation of the result.

    Example:
        result = CoherenceResult(valid=True, issues=[])
        output = format_coherence_result(result=result, verbose=False)
        # Returns: "Coherence check passed: 0 errors, 0 warnings"
    """
    error_count = result.errors
    warning_count = result.warnings

    lines = []

    # Summary line
    if result.valid and error_count == 0 and warning_count == 0:
        lines.append("Coherence check passed: 0 errors, 0 warnings")
    elif result.valid:
        lines.append(
            f"Coherence check passed with warnings: "
            f"{error_count} errors, {warning_count} warnings"
        )
    else:
        lines.append(
            f"Coherence check failed: {error_count} errors, {warning_count} warnings"
        )

    # In verbose mode, add detailed issue information
    if verbose and result.issues:
        lines.append("")  # Blank line before issues
        for issue in result.issues:
            lines.append(_format_issue(issue=issue))

    return "\n".join(lines)


def _format_issue(issue: CoherenceIssue) -> str:
    """Format a single coherence issue with severity indicator.

    Formats the issue with a severity indicator (emoji/symbol), including
    the issue type, message, location (if present), and suggestion.

    Args:
        issue: The CoherenceIssue to format.

    Returns:
        Formatted string representation of the issue.

    Example:
        issue = CoherenceIssue(
            issue_type=IssueType.DUPLICATE,
            severity=IssueSeverity.ERROR,
            message="Duplicate artifact found",
            suggestion="Remove one duplicate",
            location="manifests/task-001.manifest.json",
        )
        output = _format_issue(issue=issue)
    """
    indicator = _SEVERITY_INDICATORS.get(issue.severity, "")
    label = _SEVERITY_LABELS.get(issue.severity, "UNKNOWN")

    lines = []

    # First line: severity indicator, label, and type
    header = f"{indicator} [{label}] {issue.issue_type.value.upper()}"
    lines.append(header)

    # Message line
    lines.append(f"  Message: {issue.message}")

    # Location line (if present)
    if issue.location:
        lines.append(f"  Location: {issue.location}")

    # Suggestion line
    lines.append(f"  {_format_suggestion(suggestion=issue.suggestion)}")

    return "\n".join(lines)


def _format_suggestion(suggestion: str) -> str:
    """Format a suggestion with consistent styling.

    Adds a prefix to the suggestion text for consistent visual styling
    across all formatted suggestions.

    Args:
        suggestion: The suggestion text to format.

    Returns:
        Formatted suggestion string with prefix.

    Example:
        output = _format_suggestion(suggestion="Rename to snake_case")
        # Returns: "Suggestion: Rename to snake_case"
    """
    return f"Suggestion: {suggestion}"
