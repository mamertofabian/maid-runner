"""Behavioral tests for Task 136: Coherence Package Init.

Tests that all coherence validation types, classes, and functions are properly
exported from the maid_runner.coherence package.
"""


class TestCoherencePackageExports:
    """Test that all expected symbols are exported from maid_runner.coherence."""

    def test_import_coherence_issue(self) -> None:
        """Test CoherenceIssue can be imported from coherence package."""
        from maid_runner.coherence import CoherenceIssue

        # Verify it's a class that can be instantiated
        from maid_runner.coherence import IssueSeverity, IssueType

        issue = CoherenceIssue(
            issue_type=IssueType.DUPLICATE,
            severity=IssueSeverity.ERROR,
            message="Test message",
            suggestion="Test suggestion",
        )
        assert issue.message == "Test message"
        assert issue.suggestion == "Test suggestion"

    def test_import_coherence_result(self) -> None:
        """Test CoherenceResult can be imported from coherence package."""
        from maid_runner.coherence import CoherenceResult

        # Verify it's a class that can be instantiated
        result = CoherenceResult(valid=True, issues=[])
        assert result.valid is True
        assert result.issues == []

    def test_import_issue_severity(self) -> None:
        """Test IssueSeverity can be imported from coherence package."""
        from maid_runner.coherence import IssueSeverity

        # Verify enum values exist
        assert IssueSeverity.ERROR.value == "error"
        assert IssueSeverity.WARNING.value == "warning"
        assert IssueSeverity.INFO.value == "info"

    def test_import_issue_type(self) -> None:
        """Test IssueType can be imported from coherence package."""
        from maid_runner.coherence import IssueType

        # Verify enum values exist
        assert IssueType.DUPLICATE.value == "duplicate"
        assert IssueType.SIGNATURE_CONFLICT.value == "signature_conflict"
        assert IssueType.BOUNDARY_VIOLATION.value == "boundary_violation"
        assert IssueType.NAMING.value == "naming"
        assert IssueType.DEPENDENCY.value == "dependency"
        assert IssueType.PATTERN.value == "pattern"
        assert IssueType.CONSTRAINT.value == "constraint"

    def test_import_coherence_validator(self) -> None:
        """Test CoherenceValidator can be imported from coherence package."""
        from maid_runner.coherence import CoherenceValidator
        from pathlib import Path

        # Verify it's a class that can be instantiated
        validator = CoherenceValidator(manifest_dir=Path("manifests"))
        assert validator.manifest_dir == Path("manifests")

    def test_import_check_duplicate_artifacts(self) -> None:
        """Test check_duplicate_artifacts can be imported from coherence package."""
        from maid_runner.coherence import check_duplicate_artifacts

        # Verify it's callable
        assert callable(check_duplicate_artifacts)

    def test_import_check_signature_conflicts(self) -> None:
        """Test check_signature_conflicts can be imported from coherence package."""
        from maid_runner.coherence import check_signature_conflicts

        # Verify it's callable
        assert callable(check_signature_conflicts)

    def test_import_check_module_boundaries(self) -> None:
        """Test check_module_boundaries can be imported from coherence package."""
        from maid_runner.coherence import check_module_boundaries

        # Verify it's callable
        assert callable(check_module_boundaries)

    def test_import_check_naming_conventions(self) -> None:
        """Test check_naming_conventions can be imported from coherence package."""
        from maid_runner.coherence import check_naming_conventions

        # Verify it's callable
        assert callable(check_naming_conventions)

    def test_import_check_dependency_availability(self) -> None:
        """Test check_dependency_availability can be imported from coherence package."""
        from maid_runner.coherence import check_dependency_availability

        # Verify it's callable
        assert callable(check_dependency_availability)

    def test_import_check_pattern_consistency(self) -> None:
        """Test check_pattern_consistency can be imported from coherence package."""
        from maid_runner.coherence import check_pattern_consistency

        # Verify it's callable
        assert callable(check_pattern_consistency)

    def test_import_check_architectural_constraints(self) -> None:
        """Test check_architectural_constraints can be imported from coherence package."""
        from maid_runner.coherence import check_architectural_constraints

        # Verify it's callable
        assert callable(check_architectural_constraints)

    def test_import_load_constraint_config(self) -> None:
        """Test load_constraint_config can be imported from coherence package."""
        from maid_runner.coherence import load_constraint_config

        # Verify it's callable and returns ConstraintConfig
        config = load_constraint_config(None)
        assert config is not None

    def test_import_constraint_config(self) -> None:
        """Test ConstraintConfig can be imported from coherence package."""
        from maid_runner.coherence import ConstraintConfig

        # Verify it's a class that can be instantiated
        config = ConstraintConfig(version="1", rules=[], enabled=True)
        assert config.version == "1"
        assert config.rules == []
        assert config.enabled is True

    def test_import_constraint_rule(self) -> None:
        """Test ConstraintRule can be imported from coherence package."""
        from maid_runner.coherence import ConstraintRule

        # Verify it's a class that can be instantiated
        rule = ConstraintRule(
            name="test_rule",
            description="Test description",
            pattern={"file_pattern": "*.py"},
            severity="error",
            suggestion="Test suggestion",
        )
        assert rule.name == "test_rule"
        assert rule.description == "Test description"
        assert rule.pattern == {"file_pattern": "*.py"}
        assert rule.severity == "error"
        assert rule.suggestion == "Test suggestion"


class TestCoherencePackageAllList:
    """Test that __all__ exports all expected symbols."""

    def test_all_contains_result_types(self) -> None:
        """Test __all__ contains result types from result.py."""
        import maid_runner.coherence as coherence

        all_exports = coherence.__all__

        assert "CoherenceIssue" in all_exports
        assert "CoherenceResult" in all_exports
        assert "IssueSeverity" in all_exports
        assert "IssueType" in all_exports

    def test_all_contains_validator(self) -> None:
        """Test __all__ contains CoherenceValidator."""
        import maid_runner.coherence as coherence

        all_exports = coherence.__all__

        assert "CoherenceValidator" in all_exports

    def test_all_contains_check_functions(self) -> None:
        """Test __all__ contains all check functions."""
        import maid_runner.coherence as coherence

        all_exports = coherence.__all__

        assert "check_duplicate_artifacts" in all_exports
        assert "check_signature_conflicts" in all_exports
        assert "check_module_boundaries" in all_exports
        assert "check_naming_conventions" in all_exports
        assert "check_dependency_availability" in all_exports
        assert "check_pattern_consistency" in all_exports
        assert "check_architectural_constraints" in all_exports

    def test_all_contains_constraint_types(self) -> None:
        """Test __all__ contains constraint-related types and functions."""
        import maid_runner.coherence as coherence

        all_exports = coherence.__all__

        assert "load_constraint_config" in all_exports
        assert "ConstraintConfig" in all_exports
        assert "ConstraintRule" in all_exports


class TestCoherencePackageIntegration:
    """Integration tests verifying exports work together correctly."""

    def test_create_coherence_issue_with_imported_types(self) -> None:
        """Test creating a CoherenceIssue using all imported types."""
        from maid_runner.coherence import (
            CoherenceIssue,
            CoherenceResult,
            IssueSeverity,
            IssueType,
        )

        issue = CoherenceIssue(
            issue_type=IssueType.NAMING,
            severity=IssueSeverity.WARNING,
            message="Function name does not follow snake_case",
            suggestion="Rename the function",
            location="src/module.py:42",
        )

        result = CoherenceResult(valid=False, issues=[issue])

        assert result.valid is False
        assert len(result.issues) == 1
        assert result.issues[0].issue_type == IssueType.NAMING
        assert result.warnings == 1
        assert result.errors == 0

    def test_create_constraint_config_with_rules(self) -> None:
        """Test creating ConstraintConfig with ConstraintRule instances."""
        from maid_runner.coherence import ConstraintConfig, ConstraintRule

        rule = ConstraintRule(
            name="no_direct_db",
            description="No direct database access in controllers",
            pattern={"file_pattern": "**/controllers/*.py"},
            severity="error",
            suggestion="Use repository pattern",
        )

        config = ConstraintConfig(version="1", rules=[rule], enabled=True)

        assert len(config.rules) == 1
        assert config.rules[0].name == "no_direct_db"
        assert config.enabled is True
