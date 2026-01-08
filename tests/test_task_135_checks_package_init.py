"""Behavioral tests for Task 135: Checks Package Init.

This module tests that the coherence checks package exports all check functions
and related classes for convenient import from maid_runner.coherence.checks.
"""


class TestChecksPackageExports:
    """Tests that verify the checks package exports required symbols."""

    def test_check_duplicate_artifacts_importable(self) -> None:
        """check_duplicate_artifacts should be importable from maid_runner.coherence.checks."""
        from maid_runner.coherence.checks import check_duplicate_artifacts

        assert check_duplicate_artifacts is not None

    def test_check_duplicate_artifacts_is_callable(self) -> None:
        """check_duplicate_artifacts should be a callable function."""
        from maid_runner.coherence.checks import check_duplicate_artifacts

        assert callable(check_duplicate_artifacts)

    def test_check_signature_conflicts_importable(self) -> None:
        """check_signature_conflicts should be importable from maid_runner.coherence.checks."""
        from maid_runner.coherence.checks import check_signature_conflicts

        assert check_signature_conflicts is not None

    def test_check_signature_conflicts_is_callable(self) -> None:
        """check_signature_conflicts should be a callable function."""
        from maid_runner.coherence.checks import check_signature_conflicts

        assert callable(check_signature_conflicts)

    def test_check_module_boundaries_importable(self) -> None:
        """check_module_boundaries should be importable from maid_runner.coherence.checks."""
        from maid_runner.coherence.checks import check_module_boundaries

        assert check_module_boundaries is not None

    def test_check_module_boundaries_is_callable(self) -> None:
        """check_module_boundaries should be a callable function."""
        from maid_runner.coherence.checks import check_module_boundaries

        assert callable(check_module_boundaries)

    def test_check_naming_conventions_importable(self) -> None:
        """check_naming_conventions should be importable from maid_runner.coherence.checks."""
        from maid_runner.coherence.checks import check_naming_conventions

        assert check_naming_conventions is not None

    def test_check_naming_conventions_is_callable(self) -> None:
        """check_naming_conventions should be a callable function."""
        from maid_runner.coherence.checks import check_naming_conventions

        assert callable(check_naming_conventions)

    def test_check_dependency_availability_importable(self) -> None:
        """check_dependency_availability should be importable from maid_runner.coherence.checks."""
        from maid_runner.coherence.checks import check_dependency_availability

        assert check_dependency_availability is not None

    def test_check_dependency_availability_is_callable(self) -> None:
        """check_dependency_availability should be a callable function."""
        from maid_runner.coherence.checks import check_dependency_availability

        assert callable(check_dependency_availability)

    def test_check_pattern_consistency_importable(self) -> None:
        """check_pattern_consistency should be importable from maid_runner.coherence.checks."""
        from maid_runner.coherence.checks import check_pattern_consistency

        assert check_pattern_consistency is not None

    def test_check_pattern_consistency_is_callable(self) -> None:
        """check_pattern_consistency should be a callable function."""
        from maid_runner.coherence.checks import check_pattern_consistency

        assert callable(check_pattern_consistency)

    def test_check_architectural_constraints_importable(self) -> None:
        """check_architectural_constraints should be importable from maid_runner.coherence.checks."""
        from maid_runner.coherence.checks import check_architectural_constraints

        assert check_architectural_constraints is not None

    def test_check_architectural_constraints_is_callable(self) -> None:
        """check_architectural_constraints should be a callable function."""
        from maid_runner.coherence.checks import check_architectural_constraints

        assert callable(check_architectural_constraints)

    def test_load_constraint_config_importable(self) -> None:
        """load_constraint_config should be importable from maid_runner.coherence.checks."""
        from maid_runner.coherence.checks import load_constraint_config

        assert load_constraint_config is not None

    def test_load_constraint_config_is_callable(self) -> None:
        """load_constraint_config should be a callable function."""
        from maid_runner.coherence.checks import load_constraint_config

        assert callable(load_constraint_config)

    def test_constraint_config_importable(self) -> None:
        """ConstraintConfig should be importable from maid_runner.coherence.checks."""
        from maid_runner.coherence.checks import ConstraintConfig

        assert ConstraintConfig is not None

    def test_constraint_config_is_class(self) -> None:
        """ConstraintConfig should be a class that can be instantiated."""
        from maid_runner.coherence.checks import ConstraintConfig

        assert isinstance(ConstraintConfig, type)

    def test_constraint_rule_importable(self) -> None:
        """ConstraintRule should be importable from maid_runner.coherence.checks."""
        from maid_runner.coherence.checks import ConstraintRule

        assert ConstraintRule is not None

    def test_constraint_rule_is_class(self) -> None:
        """ConstraintRule should be a class that can be instantiated."""
        from maid_runner.coherence.checks import ConstraintRule

        assert isinstance(ConstraintRule, type)


class TestChecksPackageAllList:
    """Tests that verify the __all__ list contains required symbols."""

    def test_check_duplicate_artifacts_in_all(self) -> None:
        """check_duplicate_artifacts should be in __all__."""
        import maid_runner.coherence.checks as checks_module

        assert "check_duplicate_artifacts" in checks_module.__all__

    def test_check_signature_conflicts_in_all(self) -> None:
        """check_signature_conflicts should be in __all__."""
        import maid_runner.coherence.checks as checks_module

        assert "check_signature_conflicts" in checks_module.__all__

    def test_check_module_boundaries_in_all(self) -> None:
        """check_module_boundaries should be in __all__."""
        import maid_runner.coherence.checks as checks_module

        assert "check_module_boundaries" in checks_module.__all__

    def test_check_naming_conventions_in_all(self) -> None:
        """check_naming_conventions should be in __all__."""
        import maid_runner.coherence.checks as checks_module

        assert "check_naming_conventions" in checks_module.__all__

    def test_check_dependency_availability_in_all(self) -> None:
        """check_dependency_availability should be in __all__."""
        import maid_runner.coherence.checks as checks_module

        assert "check_dependency_availability" in checks_module.__all__

    def test_check_pattern_consistency_in_all(self) -> None:
        """check_pattern_consistency should be in __all__."""
        import maid_runner.coherence.checks as checks_module

        assert "check_pattern_consistency" in checks_module.__all__

    def test_check_architectural_constraints_in_all(self) -> None:
        """check_architectural_constraints should be in __all__."""
        import maid_runner.coherence.checks as checks_module

        assert "check_architectural_constraints" in checks_module.__all__

    def test_load_constraint_config_in_all(self) -> None:
        """load_constraint_config should be in __all__."""
        import maid_runner.coherence.checks as checks_module

        assert "load_constraint_config" in checks_module.__all__

    def test_constraint_config_in_all(self) -> None:
        """ConstraintConfig should be in __all__."""
        import maid_runner.coherence.checks as checks_module

        assert "ConstraintConfig" in checks_module.__all__

    def test_constraint_rule_in_all(self) -> None:
        """ConstraintRule should be in __all__."""
        import maid_runner.coherence.checks as checks_module

        assert "ConstraintRule" in checks_module.__all__


class TestChecksPackageBehavior:
    """Tests that verify the exported symbols work correctly when used."""

    def test_constraint_config_instantiation(self) -> None:
        """ConstraintConfig should be instantiable with default arguments."""
        from maid_runner.coherence.checks import ConstraintConfig

        config = ConstraintConfig()

        assert config is not None
        assert config.version == "1"
        assert config.rules == []
        assert config.enabled is True

    def test_constraint_rule_instantiation(self) -> None:
        """ConstraintRule should be instantiable with required arguments."""
        from maid_runner.coherence.checks import ConstraintRule

        rule = ConstraintRule(
            name="test-rule",
            description="A test rule",
            pattern={"file_pattern": "*.py"},
            severity="warning",
            suggestion="Fix the issue",
        )

        assert rule is not None
        assert rule.name == "test-rule"
        assert rule.description == "A test rule"
        assert rule.pattern == {"file_pattern": "*.py"}
        assert rule.severity == "warning"
        assert rule.suggestion == "Fix the issue"

    def test_load_constraint_config_with_none_returns_default(self) -> None:
        """load_constraint_config with None should return default config."""
        from maid_runner.coherence.checks import (
            ConstraintConfig,
            load_constraint_config,
        )

        config = load_constraint_config(None)

        assert isinstance(config, ConstraintConfig)
        assert config.enabled is True

    def test_check_functions_return_list(self) -> None:
        """Check functions should return a list of CoherenceIssue objects."""
        from maid_runner.coherence.checks import (
            check_duplicate_artifacts,
            check_naming_conventions,
            check_signature_conflicts,
        )
        from maid_runner.graph.model import KnowledgeGraph

        manifest_data = {}
        system_artifacts: list = []
        graph = KnowledgeGraph()

        # Test check_duplicate_artifacts
        result = check_duplicate_artifacts(manifest_data, system_artifacts, graph)
        assert isinstance(result, list)

        # Test check_signature_conflicts
        result = check_signature_conflicts(manifest_data, system_artifacts)
        assert isinstance(result, list)

        # Test check_naming_conventions
        result = check_naming_conventions(manifest_data, system_artifacts)
        assert isinstance(result, list)

    def test_module_boundary_check_returns_list(self) -> None:
        """check_module_boundaries should return a list of CoherenceIssue objects."""
        from maid_runner.coherence.checks import check_module_boundaries
        from maid_runner.graph.model import KnowledgeGraph

        manifest_data = {}
        graph = KnowledgeGraph()

        result = check_module_boundaries(manifest_data, graph)

        assert isinstance(result, list)

    def test_dependency_check_returns_list(self) -> None:
        """check_dependency_availability should return a list of CoherenceIssue objects."""
        from maid_runner.coherence.checks import check_dependency_availability
        from maid_runner.graph.model import KnowledgeGraph

        manifest_data = {}
        graph = KnowledgeGraph()

        result = check_dependency_availability(manifest_data, graph)

        assert isinstance(result, list)

    def test_pattern_check_returns_list(self) -> None:
        """check_pattern_consistency should return a list of CoherenceIssue objects."""
        from maid_runner.coherence.checks import check_pattern_consistency
        from maid_runner.graph.model import KnowledgeGraph

        manifest_data = {}
        graph = KnowledgeGraph()

        result = check_pattern_consistency(manifest_data, graph)

        assert isinstance(result, list)

    def test_constraint_check_returns_list(self) -> None:
        """check_architectural_constraints should return a list of CoherenceIssue objects."""
        from maid_runner.coherence.checks import check_architectural_constraints
        from maid_runner.graph.model import KnowledgeGraph

        manifest_data = {}
        graph = KnowledgeGraph()

        result = check_architectural_constraints(manifest_data, graph)

        assert isinstance(result, list)


class TestCompletePublicAPI:
    """Tests that verify the package provides a complete public API."""

    def test_all_expected_exports_present(self) -> None:
        """All expected exports from task-135 should be present."""
        import maid_runner.coherence.checks as checks_module

        expected_exports = [
            "check_duplicate_artifacts",
            "check_signature_conflicts",
            "check_module_boundaries",
            "check_naming_conventions",
            "check_dependency_availability",
            "check_pattern_consistency",
            "check_architectural_constraints",
            "load_constraint_config",
            "ConstraintConfig",
            "ConstraintRule",
        ]

        for export in expected_exports:
            assert hasattr(checks_module, export), f"Missing export: {export}"
            assert export in checks_module.__all__, f"Missing from __all__: {export}"

    def test_exports_are_functional(self) -> None:
        """All exported symbols should be functional (classes/functions)."""
        from maid_runner.coherence.checks import (
            ConstraintConfig,
            ConstraintRule,
            check_architectural_constraints,
            check_dependency_availability,
            check_duplicate_artifacts,
            check_module_boundaries,
            check_naming_conventions,
            check_pattern_consistency,
            check_signature_conflicts,
            load_constraint_config,
        )

        # Classes should be types
        assert isinstance(ConstraintConfig, type)
        assert isinstance(ConstraintRule, type)

        # Functions should be callable
        assert callable(check_duplicate_artifacts)
        assert callable(check_signature_conflicts)
        assert callable(check_module_boundaries)
        assert callable(check_naming_conventions)
        assert callable(check_dependency_availability)
        assert callable(check_pattern_consistency)
        assert callable(check_architectural_constraints)
        assert callable(load_constraint_config)
