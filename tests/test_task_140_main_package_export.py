"""Behavioral tests for Task 140: Export coherence in main __init__.py.

Tests that the coherence module is properly exported from maid_runner,
enabling `from maid_runner import coherence` for programmatic use.

These tests verify:
- The coherence attribute exists on the maid_runner module (explicit export)
- The coherence attribute is a module
- All coherence types are accessible via maid_runner.coherence
- All check functions are accessible via maid_runner.coherence
- The coherence module can be imported directly from maid_runner
- coherence is included in __all__

IMPORTANT: The key behavior being tested is that coherence is EXPLICITLY
exported in maid_runner/__init__.py, not just implicitly available as a
subpackage. This means:
- `coherence` should be in maid_runner.__all__
- `coherence` should appear in dir(maid_runner) after import
"""

import types


class TestCoherenceAttributeExport:
    """Tests that verify coherence is exported as an attribute from maid_runner."""

    def test_coherence_importable_from_maid_runner(self) -> None:
        """coherence should be importable directly from maid_runner."""
        from maid_runner import coherence

        assert coherence is not None

    def test_maid_runner_has_coherence_attribute(self) -> None:
        """maid_runner module should have a coherence attribute."""
        import maid_runner

        assert hasattr(maid_runner, "coherence")

    def test_coherence_attribute_is_module(self) -> None:
        """The coherence attribute should be a module."""
        from maid_runner import coherence

        assert isinstance(coherence, types.ModuleType)

    def test_coherence_is_same_as_coherence_package(self) -> None:
        """The coherence attribute should be the same as maid_runner.coherence."""
        from maid_runner import coherence
        import maid_runner.coherence as coherence_direct

        assert coherence is coherence_direct

    def test_coherence_in_all_list(self) -> None:
        """coherence should be in maid_runner.__all__ for explicit export."""
        import maid_runner

        assert "coherence" in maid_runner.__all__


class TestCoherenceValidatorAccess:
    """Tests that verify CoherenceValidator is accessible via maid_runner.coherence."""

    def test_coherence_validator_accessible(self) -> None:
        """CoherenceValidator should be accessible via coherence module."""
        from maid_runner import coherence

        assert hasattr(coherence, "CoherenceValidator")
        assert coherence.CoherenceValidator is not None

    def test_coherence_validator_is_class(self) -> None:
        """CoherenceValidator should be a class."""
        from maid_runner import coherence

        assert isinstance(coherence.CoherenceValidator, type)

    def test_coherence_validator_instantiable(self) -> None:
        """CoherenceValidator should be instantiable."""
        from maid_runner import coherence
        from pathlib import Path

        validator = coherence.CoherenceValidator(manifest_dir=Path("manifests"))
        assert validator.manifest_dir == Path("manifests")


class TestCoherenceResultAccess:
    """Tests that verify CoherenceResult is accessible via maid_runner.coherence."""

    def test_coherence_result_accessible(self) -> None:
        """CoherenceResult should be accessible via coherence module."""
        from maid_runner import coherence

        assert hasattr(coherence, "CoherenceResult")
        assert coherence.CoherenceResult is not None

    def test_coherence_result_is_class(self) -> None:
        """CoherenceResult should be a class."""
        from maid_runner import coherence

        assert isinstance(coherence.CoherenceResult, type)

    def test_coherence_result_instantiable(self) -> None:
        """CoherenceResult should be instantiable."""
        from maid_runner import coherence

        result = coherence.CoherenceResult(valid=True, issues=[])
        assert result.valid is True
        assert result.issues == []


class TestCoherenceIssueAccess:
    """Tests that verify CoherenceIssue is accessible via maid_runner.coherence."""

    def test_coherence_issue_accessible(self) -> None:
        """CoherenceIssue should be accessible via coherence module."""
        from maid_runner import coherence

        assert hasattr(coherence, "CoherenceIssue")
        assert coherence.CoherenceIssue is not None

    def test_coherence_issue_is_class(self) -> None:
        """CoherenceIssue should be a class."""
        from maid_runner import coherence

        assert isinstance(coherence.CoherenceIssue, type)

    def test_coherence_issue_instantiable(self) -> None:
        """CoherenceIssue should be instantiable."""
        from maid_runner import coherence

        issue = coherence.CoherenceIssue(
            issue_type=coherence.IssueType.DUPLICATE,
            severity=coherence.IssueSeverity.ERROR,
            message="Test message",
            suggestion="Test suggestion",
        )
        assert issue.message == "Test message"


class TestIssueSeverityAccess:
    """Tests that verify IssueSeverity is accessible via maid_runner.coherence."""

    def test_issue_severity_accessible(self) -> None:
        """IssueSeverity should be accessible via coherence module."""
        from maid_runner import coherence

        assert hasattr(coherence, "IssueSeverity")
        assert coherence.IssueSeverity is not None

    def test_issue_severity_has_expected_values(self) -> None:
        """IssueSeverity should have expected enum values."""
        from maid_runner import coherence

        assert coherence.IssueSeverity.ERROR.value == "error"
        assert coherence.IssueSeverity.WARNING.value == "warning"
        assert coherence.IssueSeverity.INFO.value == "info"


class TestIssueTypeAccess:
    """Tests that verify IssueType is accessible via maid_runner.coherence."""

    def test_issue_type_accessible(self) -> None:
        """IssueType should be accessible via coherence module."""
        from maid_runner import coherence

        assert hasattr(coherence, "IssueType")
        assert coherence.IssueType is not None

    def test_issue_type_has_expected_values(self) -> None:
        """IssueType should have expected enum values."""
        from maid_runner import coherence

        assert coherence.IssueType.DUPLICATE.value == "duplicate"
        assert coherence.IssueType.SIGNATURE_CONFLICT.value == "signature_conflict"
        assert coherence.IssueType.BOUNDARY_VIOLATION.value == "boundary_violation"
        assert coherence.IssueType.NAMING.value == "naming"
        assert coherence.IssueType.DEPENDENCY.value == "dependency"
        assert coherence.IssueType.PATTERN.value == "pattern"
        assert coherence.IssueType.CONSTRAINT.value == "constraint"


class TestCheckFunctionsAccess:
    """Tests that verify all check functions are accessible via maid_runner.coherence."""

    def test_check_duplicate_artifacts_accessible(self) -> None:
        """check_duplicate_artifacts should be accessible via coherence module."""
        from maid_runner import coherence

        assert hasattr(coherence, "check_duplicate_artifacts")
        assert callable(coherence.check_duplicate_artifacts)

    def test_check_signature_conflicts_accessible(self) -> None:
        """check_signature_conflicts should be accessible via coherence module."""
        from maid_runner import coherence

        assert hasattr(coherence, "check_signature_conflicts")
        assert callable(coherence.check_signature_conflicts)

    def test_check_module_boundaries_accessible(self) -> None:
        """check_module_boundaries should be accessible via coherence module."""
        from maid_runner import coherence

        assert hasattr(coherence, "check_module_boundaries")
        assert callable(coherence.check_module_boundaries)

    def test_check_naming_conventions_accessible(self) -> None:
        """check_naming_conventions should be accessible via coherence module."""
        from maid_runner import coherence

        assert hasattr(coherence, "check_naming_conventions")
        assert callable(coherence.check_naming_conventions)

    def test_check_dependency_availability_accessible(self) -> None:
        """check_dependency_availability should be accessible via coherence module."""
        from maid_runner import coherence

        assert hasattr(coherence, "check_dependency_availability")
        assert callable(coherence.check_dependency_availability)

    def test_check_pattern_consistency_accessible(self) -> None:
        """check_pattern_consistency should be accessible via coherence module."""
        from maid_runner import coherence

        assert hasattr(coherence, "check_pattern_consistency")
        assert callable(coherence.check_pattern_consistency)

    def test_check_architectural_constraints_accessible(self) -> None:
        """check_architectural_constraints should be accessible via coherence module."""
        from maid_runner import coherence

        assert hasattr(coherence, "check_architectural_constraints")
        assert callable(coherence.check_architectural_constraints)


class TestConstraintConfigAccess:
    """Tests that verify constraint configuration types are accessible."""

    def test_load_constraint_config_accessible(self) -> None:
        """load_constraint_config should be accessible via coherence module."""
        from maid_runner import coherence

        assert hasattr(coherence, "load_constraint_config")
        assert callable(coherence.load_constraint_config)

    def test_constraint_config_accessible(self) -> None:
        """ConstraintConfig should be accessible via coherence module."""
        from maid_runner import coherence

        assert hasattr(coherence, "ConstraintConfig")
        assert coherence.ConstraintConfig is not None

    def test_constraint_rule_accessible(self) -> None:
        """ConstraintRule should be accessible via coherence module."""
        from maid_runner import coherence

        assert hasattr(coherence, "ConstraintRule")
        assert coherence.ConstraintRule is not None


class TestCoherenceIntegration:
    """Integration tests verifying coherence export works with existing API."""

    def test_coherence_export_alongside_existing_exports(self) -> None:
        """coherence should be importable alongside existing maid_runner exports."""
        from maid_runner import (
            coherence,
            __version__,
            AlignmentError,
            validate_schema,
        )

        assert coherence is not None
        assert __version__ is not None
        assert AlignmentError is not None
        assert validate_schema is not None

    def test_coherence_types_match_direct_imports(self) -> None:
        """Types accessed via coherence should be same as direct imports."""
        from maid_runner import coherence
        from maid_runner.coherence import (
            CoherenceValidator as DirectValidator,
            CoherenceResult as DirectResult,
            CoherenceIssue as DirectIssue,
            IssueSeverity as DirectSeverity,
            IssueType as DirectType,
        )

        assert coherence.CoherenceValidator is DirectValidator
        assert coherence.CoherenceResult is DirectResult
        assert coherence.CoherenceIssue is DirectIssue
        assert coherence.IssueSeverity is DirectSeverity
        assert coherence.IssueType is DirectType

    def test_can_create_full_validation_flow(self) -> None:
        """Should be able to use coherence exports for a full validation flow."""
        from maid_runner import coherence
        from pathlib import Path

        # Create validator
        validator = coherence.CoherenceValidator(manifest_dir=Path("manifests"))

        # Create an issue
        issue = coherence.CoherenceIssue(
            issue_type=coherence.IssueType.NAMING,
            severity=coherence.IssueSeverity.WARNING,
            message="Test naming issue",
            suggestion="Follow snake_case",
            location="test.py:10",
        )

        # Create a result
        result = coherence.CoherenceResult(valid=False, issues=[issue])

        assert validator.manifest_dir == Path("manifests")
        assert result.valid is False
        assert len(result.issues) == 1
        assert result.warnings == 1
        assert result.errors == 0
