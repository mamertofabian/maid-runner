"""Behavioral tests for task-126: Coherence Result Types.

These tests verify the data structures for coherence validation results including
severity levels, issue types, and result containers. Tests focus on behavioral
validation - using (instantiating, accessing) the declared artifacts rather than
implementation details.

Artifacts tested:
- IssueSeverity enum with values: ERROR, WARNING, INFO
- IssueType enum with values: DUPLICATE, SIGNATURE_CONFLICT, BOUNDARY_VIOLATION,
  NAMING, DEPENDENCY, PATTERN, CONSTRAINT
- CoherenceIssue dataclass with issue_type, severity, message, suggestion, location
- CoherenceResult dataclass with valid, issues, errors, warnings attributes
"""

from maid_runner.coherence.result import (
    IssueSeverity,
    IssueType,
    CoherenceIssue,
    CoherenceResult,
)


class TestIssueSeverityEnum:
    """Tests for the IssueSeverity enumeration."""

    def test_issue_severity_has_error_value(self):
        """IssueSeverity enum has ERROR value."""
        assert hasattr(IssueSeverity, "ERROR")
        error_severity = IssueSeverity.ERROR
        assert error_severity is not None

    def test_issue_severity_has_warning_value(self):
        """IssueSeverity enum has WARNING value."""
        assert hasattr(IssueSeverity, "WARNING")
        warning_severity = IssueSeverity.WARNING
        assert warning_severity is not None

    def test_issue_severity_has_info_value(self):
        """IssueSeverity enum has INFO value."""
        assert hasattr(IssueSeverity, "INFO")
        info_severity = IssueSeverity.INFO
        assert info_severity is not None

    def test_issue_severity_values_are_distinct(self):
        """All IssueSeverity values are distinct from each other."""
        values = [IssueSeverity.ERROR, IssueSeverity.WARNING, IssueSeverity.INFO]
        assert len(values) == len(set(values))

    def test_issue_severity_iteration(self):
        """IssueSeverity can be iterated over (standard enum behavior)."""
        severities = list(IssueSeverity)
        assert len(severities) >= 3
        assert IssueSeverity.ERROR in severities
        assert IssueSeverity.WARNING in severities
        assert IssueSeverity.INFO in severities


class TestIssueTypeEnum:
    """Tests for the IssueType enumeration."""

    def test_issue_type_has_duplicate_value(self):
        """IssueType enum has DUPLICATE value."""
        assert hasattr(IssueType, "DUPLICATE")
        duplicate_type = IssueType.DUPLICATE
        assert duplicate_type is not None

    def test_issue_type_has_signature_conflict_value(self):
        """IssueType enum has SIGNATURE_CONFLICT value."""
        assert hasattr(IssueType, "SIGNATURE_CONFLICT")
        signature_conflict_type = IssueType.SIGNATURE_CONFLICT
        assert signature_conflict_type is not None

    def test_issue_type_has_boundary_violation_value(self):
        """IssueType enum has BOUNDARY_VIOLATION value."""
        assert hasattr(IssueType, "BOUNDARY_VIOLATION")
        boundary_violation_type = IssueType.BOUNDARY_VIOLATION
        assert boundary_violation_type is not None

    def test_issue_type_has_naming_value(self):
        """IssueType enum has NAMING value."""
        assert hasattr(IssueType, "NAMING")
        naming_type = IssueType.NAMING
        assert naming_type is not None

    def test_issue_type_has_dependency_value(self):
        """IssueType enum has DEPENDENCY value."""
        assert hasattr(IssueType, "DEPENDENCY")
        dependency_type = IssueType.DEPENDENCY
        assert dependency_type is not None

    def test_issue_type_has_pattern_value(self):
        """IssueType enum has PATTERN value."""
        assert hasattr(IssueType, "PATTERN")
        pattern_type = IssueType.PATTERN
        assert pattern_type is not None

    def test_issue_type_has_constraint_value(self):
        """IssueType enum has CONSTRAINT value."""
        assert hasattr(IssueType, "CONSTRAINT")
        constraint_type = IssueType.CONSTRAINT
        assert constraint_type is not None

    def test_issue_type_values_are_distinct(self):
        """All IssueType values are distinct from each other."""
        values = [
            IssueType.DUPLICATE,
            IssueType.SIGNATURE_CONFLICT,
            IssueType.BOUNDARY_VIOLATION,
            IssueType.NAMING,
            IssueType.DEPENDENCY,
            IssueType.PATTERN,
            IssueType.CONSTRAINT,
        ]
        assert len(values) == len(set(values))

    def test_issue_type_iteration(self):
        """IssueType can be iterated over (standard enum behavior)."""
        issue_types = list(IssueType)
        assert len(issue_types) >= 7
        assert IssueType.DUPLICATE in issue_types
        assert IssueType.SIGNATURE_CONFLICT in issue_types
        assert IssueType.BOUNDARY_VIOLATION in issue_types
        assert IssueType.NAMING in issue_types
        assert IssueType.DEPENDENCY in issue_types
        assert IssueType.PATTERN in issue_types
        assert IssueType.CONSTRAINT in issue_types


class TestCoherenceIssueDataclass:
    """Tests for the CoherenceIssue dataclass."""

    def test_coherence_issue_creation_with_all_attributes(self):
        """CoherenceIssue can be created with all expected attributes."""
        issue = CoherenceIssue(
            issue_type=IssueType.DUPLICATE,
            severity=IssueSeverity.ERROR,
            message="Duplicate artifact 'validate' found in multiple manifests",
            suggestion="Consolidate into a single manifest or use supersession",
            location="manifests/task-001.manifest.json",
        )

        assert issue.issue_type == IssueType.DUPLICATE
        assert issue.severity == IssueSeverity.ERROR
        assert (
            issue.message == "Duplicate artifact 'validate' found in multiple manifests"
        )
        assert (
            issue.suggestion == "Consolidate into a single manifest or use supersession"
        )
        assert issue.location == "manifests/task-001.manifest.json"

    def test_coherence_issue_has_issue_type_attribute(self):
        """CoherenceIssue has issue_type attribute."""
        issue = CoherenceIssue(
            issue_type=IssueType.NAMING,
            severity=IssueSeverity.WARNING,
            message="test",
            suggestion="fix it",
            location="file.py",
        )

        assert hasattr(issue, "issue_type")
        assert issue.issue_type == IssueType.NAMING

    def test_coherence_issue_has_severity_attribute(self):
        """CoherenceIssue has severity attribute."""
        issue = CoherenceIssue(
            issue_type=IssueType.PATTERN,
            severity=IssueSeverity.INFO,
            message="test",
            suggestion="consider",
            location="file.py",
        )

        assert hasattr(issue, "severity")
        assert issue.severity == IssueSeverity.INFO

    def test_coherence_issue_has_message_attribute(self):
        """CoherenceIssue has message attribute."""
        issue = CoherenceIssue(
            issue_type=IssueType.CONSTRAINT,
            severity=IssueSeverity.ERROR,
            message="The message content here",
            suggestion="suggestion",
            location="loc",
        )

        assert hasattr(issue, "message")
        assert issue.message == "The message content here"

    def test_coherence_issue_has_suggestion_attribute(self):
        """CoherenceIssue has suggestion attribute."""
        issue = CoherenceIssue(
            issue_type=IssueType.DEPENDENCY,
            severity=IssueSeverity.WARNING,
            message="msg",
            suggestion="The suggestion content here",
            location="loc",
        )

        assert hasattr(issue, "suggestion")
        assert issue.suggestion == "The suggestion content here"

    def test_coherence_issue_has_location_attribute(self):
        """CoherenceIssue has location attribute."""
        issue = CoherenceIssue(
            issue_type=IssueType.BOUNDARY_VIOLATION,
            severity=IssueSeverity.ERROR,
            message="msg",
            suggestion="sug",
            location="src/validators/core.py:42",
        )

        assert hasattr(issue, "location")
        assert issue.location == "src/validators/core.py:42"

    def test_coherence_issue_with_different_issue_types(self):
        """CoherenceIssue can be created with any IssueType value."""
        for issue_type in IssueType:
            issue = CoherenceIssue(
                issue_type=issue_type,
                severity=IssueSeverity.WARNING,
                message=f"Issue of type {issue_type.name}",
                suggestion="Fix it",
                location="test.py",
            )
            assert issue.issue_type == issue_type

    def test_coherence_issue_with_different_severities(self):
        """CoherenceIssue can be created with any IssueSeverity value."""
        for severity in IssueSeverity:
            issue = CoherenceIssue(
                issue_type=IssueType.DUPLICATE,
                severity=severity,
                message=f"Issue with severity {severity.name}",
                suggestion="Address it",
                location="test.py",
            )
            assert issue.severity == severity


class TestCoherenceResultDataclass:
    """Tests for the CoherenceResult dataclass."""

    def test_coherence_result_creation_with_valid_true_and_no_issues(self):
        """CoherenceResult can be created with valid=True and empty issues list."""
        result = CoherenceResult(valid=True, issues=[])

        assert result.valid is True
        assert result.issues == []

    def test_coherence_result_creation_with_issues(self):
        """CoherenceResult can be created with a list of CoherenceIssue objects."""
        issue1 = CoherenceIssue(
            issue_type=IssueType.DUPLICATE,
            severity=IssueSeverity.ERROR,
            message="Duplicate found",
            suggestion="Remove one",
            location="manifest1.json",
        )
        issue2 = CoherenceIssue(
            issue_type=IssueType.NAMING,
            severity=IssueSeverity.WARNING,
            message="Naming convention violated",
            suggestion="Use snake_case",
            location="file.py",
        )

        result = CoherenceResult(valid=False, issues=[issue1, issue2])

        assert result.valid is False
        assert len(result.issues) == 2
        assert result.issues[0] == issue1
        assert result.issues[1] == issue2

    def test_coherence_result_has_valid_attribute(self):
        """CoherenceResult has valid attribute."""
        result = CoherenceResult(valid=True, issues=[])

        assert hasattr(result, "valid")
        assert isinstance(result.valid, bool)

    def test_coherence_result_has_issues_attribute(self):
        """CoherenceResult has issues attribute."""
        result = CoherenceResult(valid=True, issues=[])

        assert hasattr(result, "issues")
        assert isinstance(result.issues, list)

    def test_coherence_result_errors_property_returns_error_count(self):
        """CoherenceResult.errors returns count of ERROR severity issues."""
        error_issue1 = CoherenceIssue(
            issue_type=IssueType.DUPLICATE,
            severity=IssueSeverity.ERROR,
            message="Error 1",
            suggestion="Fix 1",
            location="loc1",
        )
        error_issue2 = CoherenceIssue(
            issue_type=IssueType.SIGNATURE_CONFLICT,
            severity=IssueSeverity.ERROR,
            message="Error 2",
            suggestion="Fix 2",
            location="loc2",
        )
        warning_issue = CoherenceIssue(
            issue_type=IssueType.NAMING,
            severity=IssueSeverity.WARNING,
            message="Warning",
            suggestion="Consider",
            location="loc3",
        )
        info_issue = CoherenceIssue(
            issue_type=IssueType.PATTERN,
            severity=IssueSeverity.INFO,
            message="Info",
            suggestion="Note",
            location="loc4",
        )

        result = CoherenceResult(
            valid=False,
            issues=[error_issue1, error_issue2, warning_issue, info_issue],
        )

        assert result.errors == 2

    def test_coherence_result_errors_property_returns_zero_when_no_errors(self):
        """CoherenceResult.errors returns 0 when no ERROR severity issues exist."""
        warning_issue = CoherenceIssue(
            issue_type=IssueType.NAMING,
            severity=IssueSeverity.WARNING,
            message="Warning",
            suggestion="Consider",
            location="loc",
        )
        info_issue = CoherenceIssue(
            issue_type=IssueType.PATTERN,
            severity=IssueSeverity.INFO,
            message="Info",
            suggestion="Note",
            location="loc",
        )

        result = CoherenceResult(valid=True, issues=[warning_issue, info_issue])

        assert result.errors == 0

    def test_coherence_result_warnings_property_returns_warning_count(self):
        """CoherenceResult.warnings returns count of WARNING severity issues."""
        error_issue = CoherenceIssue(
            issue_type=IssueType.DUPLICATE,
            severity=IssueSeverity.ERROR,
            message="Error",
            suggestion="Fix",
            location="loc1",
        )
        warning_issue1 = CoherenceIssue(
            issue_type=IssueType.NAMING,
            severity=IssueSeverity.WARNING,
            message="Warning 1",
            suggestion="Consider 1",
            location="loc2",
        )
        warning_issue2 = CoherenceIssue(
            issue_type=IssueType.DEPENDENCY,
            severity=IssueSeverity.WARNING,
            message="Warning 2",
            suggestion="Consider 2",
            location="loc3",
        )
        warning_issue3 = CoherenceIssue(
            issue_type=IssueType.BOUNDARY_VIOLATION,
            severity=IssueSeverity.WARNING,
            message="Warning 3",
            suggestion="Consider 3",
            location="loc4",
        )
        info_issue = CoherenceIssue(
            issue_type=IssueType.PATTERN,
            severity=IssueSeverity.INFO,
            message="Info",
            suggestion="Note",
            location="loc5",
        )

        result = CoherenceResult(
            valid=False,
            issues=[
                error_issue,
                warning_issue1,
                warning_issue2,
                warning_issue3,
                info_issue,
            ],
        )

        assert result.warnings == 3

    def test_coherence_result_warnings_property_returns_zero_when_no_warnings(self):
        """CoherenceResult.warnings returns 0 when no WARNING severity issues exist."""
        error_issue = CoherenceIssue(
            issue_type=IssueType.DUPLICATE,
            severity=IssueSeverity.ERROR,
            message="Error",
            suggestion="Fix",
            location="loc",
        )
        info_issue = CoherenceIssue(
            issue_type=IssueType.PATTERN,
            severity=IssueSeverity.INFO,
            message="Info",
            suggestion="Note",
            location="loc",
        )

        result = CoherenceResult(valid=False, issues=[error_issue, info_issue])

        assert result.warnings == 0

    def test_coherence_result_errors_property_is_accessible(self):
        """CoherenceResult has errors property that is accessible."""
        result = CoherenceResult(valid=True, issues=[])

        assert hasattr(result, "errors")
        # Property should return an integer
        assert isinstance(result.errors, int)

    def test_coherence_result_warnings_property_is_accessible(self):
        """CoherenceResult has warnings property that is accessible."""
        result = CoherenceResult(valid=True, issues=[])

        assert hasattr(result, "warnings")
        # Property should return an integer
        assert isinstance(result.warnings, int)

    def test_coherence_result_valid_reflects_absence_of_errors(self):
        """CoherenceResult.valid should reflect presence/absence of errors."""
        # Result with no errors should be valid
        warning_issue = CoherenceIssue(
            issue_type=IssueType.NAMING,
            severity=IssueSeverity.WARNING,
            message="Warning",
            suggestion="Consider",
            location="loc",
        )
        valid_result = CoherenceResult(valid=True, issues=[warning_issue])
        assert valid_result.valid is True
        assert valid_result.errors == 0

        # Result with errors should be invalid
        error_issue = CoherenceIssue(
            issue_type=IssueType.DUPLICATE,
            severity=IssueSeverity.ERROR,
            message="Error",
            suggestion="Fix",
            location="loc",
        )
        invalid_result = CoherenceResult(valid=False, issues=[error_issue])
        assert invalid_result.valid is False
        assert invalid_result.errors > 0

    def test_coherence_result_with_empty_issues_list(self):
        """CoherenceResult works correctly with empty issues list."""
        result = CoherenceResult(valid=True, issues=[])

        assert result.valid is True
        assert result.issues == []
        assert result.errors == 0
        assert result.warnings == 0


class TestIntegrationBetweenTypes:
    """Integration tests verifying the types work together correctly."""

    def test_create_result_from_multiple_issue_types_and_severities(self):
        """CoherenceResult can aggregate issues of different types and severities."""
        issues = [
            CoherenceIssue(
                issue_type=IssueType.DUPLICATE,
                severity=IssueSeverity.ERROR,
                message="Duplicate artifact",
                suggestion="Remove duplicate",
                location="manifest1.json",
            ),
            CoherenceIssue(
                issue_type=IssueType.SIGNATURE_CONFLICT,
                severity=IssueSeverity.ERROR,
                message="Signature mismatch",
                suggestion="Align signatures",
                location="file.py:10",
            ),
            CoherenceIssue(
                issue_type=IssueType.NAMING,
                severity=IssueSeverity.WARNING,
                message="Naming convention",
                suggestion="Use snake_case",
                location="file.py:20",
            ),
            CoherenceIssue(
                issue_type=IssueType.PATTERN,
                severity=IssueSeverity.INFO,
                message="Pattern suggestion",
                suggestion="Consider using factory",
                location="file.py:30",
            ),
        ]

        result = CoherenceResult(valid=False, issues=issues)

        assert len(result.issues) == 4
        assert result.errors == 2
        assert result.warnings == 1
        assert result.valid is False

    def test_issue_types_can_be_filtered_from_result(self):
        """Issues in CoherenceResult can be filtered by type."""
        issues = [
            CoherenceIssue(
                issue_type=IssueType.DUPLICATE,
                severity=IssueSeverity.ERROR,
                message="Duplicate 1",
                suggestion="Fix 1",
                location="loc1",
            ),
            CoherenceIssue(
                issue_type=IssueType.NAMING,
                severity=IssueSeverity.WARNING,
                message="Naming 1",
                suggestion="Fix 2",
                location="loc2",
            ),
            CoherenceIssue(
                issue_type=IssueType.DUPLICATE,
                severity=IssueSeverity.ERROR,
                message="Duplicate 2",
                suggestion="Fix 3",
                location="loc3",
            ),
        ]

        result = CoherenceResult(valid=False, issues=issues)

        duplicate_issues = [
            i for i in result.issues if i.issue_type == IssueType.DUPLICATE
        ]
        naming_issues = [i for i in result.issues if i.issue_type == IssueType.NAMING]

        assert len(duplicate_issues) == 2
        assert len(naming_issues) == 1

    def test_severity_enum_used_correctly_in_issue(self):
        """IssueSeverity enum values work correctly in CoherenceIssue."""
        for severity in IssueSeverity:
            issue = CoherenceIssue(
                issue_type=IssueType.CONSTRAINT,
                severity=severity,
                message=f"Issue with {severity.name} severity",
                suggestion="Handle appropriately",
                location="test.py",
            )
            assert issue.severity == severity
            assert issue.severity in IssueSeverity

    def test_issue_type_enum_used_correctly_in_issue(self):
        """IssueType enum values work correctly in CoherenceIssue."""
        for issue_type in IssueType:
            issue = CoherenceIssue(
                issue_type=issue_type,
                severity=IssueSeverity.WARNING,
                message=f"Issue of type {issue_type.name}",
                suggestion="Address it",
                location="test.py",
            )
            assert issue.issue_type == issue_type
            assert issue.issue_type in IssueType
