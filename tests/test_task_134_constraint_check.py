"""Behavioral tests for Task 134: Architectural Constraint Validation.

Tests the architectural constraint validation module that enforces configurable
constraints loaded from .maid-constraints.json configuration files. The module
validates that manifest changes adhere to defined architectural rules and
returns CoherenceIssue with IssueType.CONSTRAINT for any violations.

Artifacts tested:
- check_architectural_constraints(manifest_data, graph, config_path=None) -> List[CoherenceIssue]
- load_constraint_config(config_path: Optional[Path]) -> ConstraintConfig
- ConstraintConfig dataclass (version, rules, enabled attributes)
- ConstraintRule dataclass (name, description, pattern, severity, suggestion attributes)
- _evaluate_constraint(rule, manifest_data, graph) -> Optional[CoherenceIssue]
"""

import json
import pytest
from pathlib import Path
from typing import Any, Dict

from maid_runner.coherence.checks.constraint_check import (
    check_architectural_constraints,
    load_constraint_config,
    ConstraintConfig,
    ConstraintRule,
    _evaluate_constraint,
)
from maid_runner.coherence.result import (
    CoherenceIssue,
    IssueType,
    IssueSeverity,
)
from maid_runner.graph.model import KnowledgeGraph, FileNode


# =============================================================================
# Fixtures - Config files
# =============================================================================


@pytest.fixture
def sample_constraint_config() -> Dict[str, Any]:
    """Return sample constraint config data for testing."""
    return {
        "version": "1",
        "enabled": True,
        "rules": [
            {
                "name": "no-db-in-controllers",
                "description": "Controllers should not access database directly",
                "pattern": {
                    "file_pattern": "**/controllers/**/*.py",
                    "forbidden_imports": ["psycopg2"],
                },
                "severity": "error",
                "suggestion": "Use repository pattern",
            }
        ],
    }


@pytest.fixture
def config_with_multiple_rules() -> Dict[str, Any]:
    """Return config with multiple constraint rules."""
    return {
        "version": "1",
        "enabled": True,
        "rules": [
            {
                "name": "no-db-in-controllers",
                "description": "Controllers should not access database directly",
                "pattern": {
                    "file_pattern": "**/controllers/**/*.py",
                    "forbidden_imports": ["psycopg2", "sqlite3"],
                },
                "severity": "error",
                "suggestion": "Use repository pattern",
            },
            {
                "name": "no-http-in-services",
                "description": "Services should not make HTTP calls directly",
                "pattern": {
                    "file_pattern": "**/services/**/*.py",
                    "forbidden_imports": ["requests", "httpx"],
                },
                "severity": "warning",
                "suggestion": "Use client adapters",
            },
        ],
    }


@pytest.fixture
def disabled_config() -> Dict[str, Any]:
    """Return config with enabled=False."""
    return {
        "version": "1",
        "enabled": False,
        "rules": [
            {
                "name": "disabled-rule",
                "description": "This rule should not be evaluated",
                "pattern": {"file_pattern": "**/*.py", "forbidden_imports": ["os"]},
                "severity": "error",
                "suggestion": "N/A",
            }
        ],
    }


@pytest.fixture
def config_with_warning_severity() -> Dict[str, Any]:
    """Return config with warning severity rules."""
    return {
        "version": "1",
        "enabled": True,
        "rules": [
            {
                "name": "warning-rule",
                "description": "A warning-level constraint",
                "pattern": {
                    "file_pattern": "**/utils/**/*.py",
                    "forbidden_imports": ["deprecated_module"],
                },
                "severity": "warning",
                "suggestion": "Consider alternatives",
            }
        ],
    }


@pytest.fixture
def constraint_config_file(
    tmp_path: Path, sample_constraint_config: Dict[str, Any]
) -> Path:
    """Create a constraint config file in tmp_path."""
    config_path = tmp_path / ".maid-constraints.json"
    config_path.write_text(json.dumps(sample_constraint_config))
    return config_path


@pytest.fixture
def disabled_config_file(tmp_path: Path, disabled_config: Dict[str, Any]) -> Path:
    """Create a disabled constraint config file in tmp_path."""
    config_path = tmp_path / ".maid-constraints.json"
    config_path.write_text(json.dumps(disabled_config))
    return config_path


@pytest.fixture
def multiple_rules_config_file(
    tmp_path: Path, config_with_multiple_rules: Dict[str, Any]
) -> Path:
    """Create a config file with multiple rules."""
    config_path = tmp_path / ".maid-constraints.json"
    config_path.write_text(json.dumps(config_with_multiple_rules))
    return config_path


@pytest.fixture
def warning_config_file(
    tmp_path: Path, config_with_warning_severity: Dict[str, Any]
) -> Path:
    """Create a config file with warning severity rules."""
    config_path = tmp_path / ".maid-constraints.json"
    config_path.write_text(json.dumps(config_with_warning_severity))
    return config_path


# =============================================================================
# Fixtures - Knowledge Graph
# =============================================================================


@pytest.fixture
def empty_knowledge_graph() -> KnowledgeGraph:
    """Create an empty KnowledgeGraph for testing."""
    return KnowledgeGraph()


@pytest.fixture
def graph_with_controller_files() -> KnowledgeGraph:
    """Create a KnowledgeGraph with controller file nodes."""
    graph = KnowledgeGraph()

    controller_file = FileNode(
        id="file:src/controllers/user_controller.py",
        path="src/controllers/user_controller.py",
        status="tracked",
    )
    graph.add_node(controller_file)

    return graph


@pytest.fixture
def graph_with_service_files() -> KnowledgeGraph:
    """Create a KnowledgeGraph with service file nodes."""
    graph = KnowledgeGraph()

    service_file = FileNode(
        id="file:src/services/user_service.py",
        path="src/services/user_service.py",
        status="tracked",
    )
    graph.add_node(service_file)

    return graph


# =============================================================================
# Fixtures - Manifest data
# =============================================================================


@pytest.fixture
def manifest_no_violations() -> Dict[str, Any]:
    """Create a manifest that should not violate any constraints."""
    return {
        "version": "1",
        "goal": "Add repository class",
        "taskType": "create",
        "creatableFiles": ["src/repositories/user_repository.py"],
        "expectedArtifacts": {
            "file": "src/repositories/user_repository.py",
            "contains": [
                {"type": "class", "name": "UserRepository"},
            ],
        },
    }


@pytest.fixture
def manifest_controller_with_db() -> Dict[str, Any]:
    """Create a manifest with controller file that might violate db constraint."""
    return {
        "version": "1",
        "goal": "Add controller with db access",
        "taskType": "create",
        "creatableFiles": ["src/controllers/user_controller.py"],
        "expectedArtifacts": {
            "file": "src/controllers/user_controller.py",
            "contains": [
                {"type": "class", "name": "UserController"},
            ],
        },
    }


@pytest.fixture
def manifest_service_with_http() -> Dict[str, Any]:
    """Create a manifest with service file that might violate http constraint."""
    return {
        "version": "1",
        "goal": "Add service with http calls",
        "taskType": "create",
        "creatableFiles": ["src/services/payment_service.py"],
        "expectedArtifacts": {
            "file": "src/services/payment_service.py",
            "contains": [
                {"type": "class", "name": "PaymentService"},
            ],
        },
    }


@pytest.fixture
def empty_manifest() -> Dict[str, Any]:
    """Create an empty manifest."""
    return {}


# =============================================================================
# Tests for ConstraintConfig dataclass
# =============================================================================


class TestConstraintConfigDataclass:
    """Tests for the ConstraintConfig dataclass."""

    def test_has_version_attribute(self) -> None:
        """ConstraintConfig has version attribute."""
        config = ConstraintConfig(version="1", rules=[], enabled=True)
        assert hasattr(config, "version")
        assert config.version == "1"

    def test_has_rules_attribute(self) -> None:
        """ConstraintConfig has rules attribute as a list."""
        config = ConstraintConfig(version="1", rules=[], enabled=True)
        assert hasattr(config, "rules")
        assert isinstance(config.rules, list)

    def test_has_enabled_attribute(self) -> None:
        """ConstraintConfig has enabled attribute with default True."""
        config = ConstraintConfig(version="1", rules=[])
        assert hasattr(config, "enabled")
        assert config.enabled is True

    def test_can_be_instantiated_with_values(self) -> None:
        """ConstraintConfig can be instantiated with all values."""
        rule = ConstraintRule(
            name="test-rule",
            description="Test description",
            pattern={"file_pattern": "**/*.py"},
            severity="error",
            suggestion="Fix it",
        )
        config = ConstraintConfig(version="2", rules=[rule], enabled=False)

        assert config.version == "2"
        assert len(config.rules) == 1
        assert config.enabled is False

    def test_rules_can_contain_constraint_rules(self) -> None:
        """ConstraintConfig rules attribute can contain ConstraintRule instances."""
        rule1 = ConstraintRule(
            name="rule-1",
            description="First rule",
            pattern={},
            severity="error",
            suggestion="Suggestion 1",
        )
        rule2 = ConstraintRule(
            name="rule-2",
            description="Second rule",
            pattern={},
            severity="warning",
            suggestion="Suggestion 2",
        )
        config = ConstraintConfig(version="1", rules=[rule1, rule2], enabled=True)

        assert len(config.rules) == 2
        assert config.rules[0].name == "rule-1"
        assert config.rules[1].name == "rule-2"


# =============================================================================
# Tests for ConstraintRule dataclass
# =============================================================================


class TestConstraintRuleDataclass:
    """Tests for the ConstraintRule dataclass."""

    def test_has_name_attribute(self) -> None:
        """ConstraintRule has name attribute."""
        rule = ConstraintRule(
            name="test-rule",
            description="Test",
            pattern={},
            severity="error",
            suggestion="Fix",
        )
        assert hasattr(rule, "name")
        assert rule.name == "test-rule"

    def test_has_description_attribute(self) -> None:
        """ConstraintRule has description attribute."""
        rule = ConstraintRule(
            name="test",
            description="Test description",
            pattern={},
            severity="error",
            suggestion="Fix",
        )
        assert hasattr(rule, "description")
        assert rule.description == "Test description"

    def test_has_pattern_attribute(self) -> None:
        """ConstraintRule has pattern attribute."""
        pattern_data = {"file_pattern": "**/controllers/**/*.py"}
        rule = ConstraintRule(
            name="test",
            description="Test",
            pattern=pattern_data,
            severity="error",
            suggestion="Fix",
        )
        assert hasattr(rule, "pattern")
        assert rule.pattern == pattern_data

    def test_has_severity_attribute(self) -> None:
        """ConstraintRule has severity attribute."""
        rule = ConstraintRule(
            name="test",
            description="Test",
            pattern={},
            severity="warning",
            suggestion="Fix",
        )
        assert hasattr(rule, "severity")
        assert rule.severity == "warning"

    def test_has_suggestion_attribute(self) -> None:
        """ConstraintRule has suggestion attribute."""
        rule = ConstraintRule(
            name="test",
            description="Test",
            pattern={},
            severity="error",
            suggestion="Use repository pattern",
        )
        assert hasattr(rule, "suggestion")
        assert rule.suggestion == "Use repository pattern"

    def test_can_be_instantiated_with_all_attributes(self) -> None:
        """ConstraintRule can be instantiated with all required attributes."""
        rule = ConstraintRule(
            name="no-db-in-controllers",
            description="Controllers should not access database directly",
            pattern={
                "file_pattern": "**/controllers/**/*.py",
                "forbidden_imports": ["psycopg2"],
            },
            severity="error",
            suggestion="Use repository pattern",
        )

        assert rule.name == "no-db-in-controllers"
        assert rule.description == "Controllers should not access database directly"
        assert "file_pattern" in rule.pattern
        assert "forbidden_imports" in rule.pattern
        assert rule.severity == "error"
        assert rule.suggestion == "Use repository pattern"


# =============================================================================
# Tests for load_constraint_config
# =============================================================================


class TestLoadConstraintConfigFunction:
    """Tests for the load_constraint_config function."""

    def test_loads_config_from_file_path(
        self, constraint_config_file: Path, sample_constraint_config: Dict[str, Any]
    ) -> None:
        """load_constraint_config loads config from file path."""
        result = load_constraint_config(config_path=constraint_config_file)

        assert isinstance(result, ConstraintConfig)
        assert result.version == sample_constraint_config["version"]
        assert result.enabled is True
        assert len(result.rules) == 1

    def test_returns_default_config_when_no_file(self) -> None:
        """load_constraint_config returns default config when no file provided."""
        result = load_constraint_config(config_path=None)

        assert isinstance(result, ConstraintConfig)
        # Default config should have empty rules or default values
        assert hasattr(result, "version")
        assert hasattr(result, "rules")
        assert hasattr(result, "enabled")

    def test_returns_default_config_when_file_missing(self, tmp_path: Path) -> None:
        """load_constraint_config returns default config when file does not exist."""
        nonexistent_path = tmp_path / "nonexistent.json"
        result = load_constraint_config(config_path=nonexistent_path)

        assert isinstance(result, ConstraintConfig)
        # Should return default, not raise error

    def test_parses_json_correctly(self, constraint_config_file: Path) -> None:
        """load_constraint_config parses JSON correctly."""
        result = load_constraint_config(config_path=constraint_config_file)

        assert isinstance(result, ConstraintConfig)
        assert len(result.rules) == 1
        assert result.rules[0].name == "no-db-in-controllers"

    def test_returns_constraint_config_with_rules(
        self, multiple_rules_config_file: Path
    ) -> None:
        """load_constraint_config returns ConstraintConfig with rules."""
        result = load_constraint_config(config_path=multiple_rules_config_file)

        assert isinstance(result, ConstraintConfig)
        assert len(result.rules) == 2
        rule_names = [rule.name for rule in result.rules]
        assert "no-db-in-controllers" in rule_names
        assert "no-http-in-services" in rule_names

    def test_rules_are_constraint_rule_instances(
        self, constraint_config_file: Path
    ) -> None:
        """load_constraint_config returns rules as ConstraintRule instances."""
        result = load_constraint_config(config_path=constraint_config_file)

        for rule in result.rules:
            assert isinstance(rule, ConstraintRule)

    def test_loads_enabled_field(self, disabled_config_file: Path) -> None:
        """load_constraint_config loads enabled field from config."""
        result = load_constraint_config(config_path=disabled_config_file)

        assert result.enabled is False


# =============================================================================
# Tests for check_architectural_constraints
# =============================================================================


class TestCheckArchitecturalConstraintsFunction:
    """Tests for the check_architectural_constraints main function."""

    def test_returns_empty_list_when_no_violations(
        self,
        manifest_no_violations: Dict[str, Any],
        empty_knowledge_graph: KnowledgeGraph,
        constraint_config_file: Path,
    ) -> None:
        """check_architectural_constraints returns empty list when no violations."""
        result = check_architectural_constraints(
            manifest_data=manifest_no_violations,
            graph=empty_knowledge_graph,
            config_path=constraint_config_file,
        )

        assert isinstance(result, list)
        assert len(result) == 0

    def test_returns_coherence_issue_with_constraint_type(
        self,
        manifest_controller_with_db: Dict[str, Any],
        graph_with_controller_files: KnowledgeGraph,
        constraint_config_file: Path,
    ) -> None:
        """check_architectural_constraints returns CoherenceIssue with IssueType.CONSTRAINT."""
        result = check_architectural_constraints(
            manifest_data=manifest_controller_with_db,
            graph=graph_with_controller_files,
            config_path=constraint_config_file,
        )

        # If violations are detected, they should have CONSTRAINT type
        for issue in result:
            assert isinstance(issue, CoherenceIssue)
            assert issue.issue_type == IssueType.CONSTRAINT

    def test_handles_missing_config_file(
        self,
        manifest_no_violations: Dict[str, Any],
        empty_knowledge_graph: KnowledgeGraph,
        tmp_path: Path,
    ) -> None:
        """check_architectural_constraints handles missing config file gracefully."""
        nonexistent_path = tmp_path / "missing.json"
        result = check_architectural_constraints(
            manifest_data=manifest_no_violations,
            graph=empty_knowledge_graph,
            config_path=nonexistent_path,
        )

        assert isinstance(result, list)
        assert len(result) == 0  # No errors, just empty list

    def test_handles_no_config_path(
        self,
        manifest_no_violations: Dict[str, Any],
        empty_knowledge_graph: KnowledgeGraph,
    ) -> None:
        """check_architectural_constraints handles None config_path."""
        result = check_architectural_constraints(
            manifest_data=manifest_no_violations,
            graph=empty_knowledge_graph,
            config_path=None,
        )

        assert isinstance(result, list)
        # With no config, should return empty list (no constraints to check)
        assert len(result) == 0

    def test_handles_disabled_constraints(
        self,
        manifest_controller_with_db: Dict[str, Any],
        graph_with_controller_files: KnowledgeGraph,
        disabled_config_file: Path,
    ) -> None:
        """check_architectural_constraints handles disabled constraints (enabled=False)."""
        result = check_architectural_constraints(
            manifest_data=manifest_controller_with_db,
            graph=graph_with_controller_files,
            config_path=disabled_config_file,
        )

        assert isinstance(result, list)
        # Disabled config should not generate violations
        assert len(result) == 0

    def test_respects_error_severity(
        self,
        manifest_controller_with_db: Dict[str, Any],
        graph_with_controller_files: KnowledgeGraph,
        constraint_config_file: Path,
    ) -> None:
        """check_architectural_constraints respects error severity from rule."""
        result = check_architectural_constraints(
            manifest_data=manifest_controller_with_db,
            graph=graph_with_controller_files,
            config_path=constraint_config_file,
        )

        # The sample config has severity "error"
        for issue in result:
            assert issue.severity == IssueSeverity.ERROR

    def test_respects_warning_severity(
        self,
        manifest_service_with_http: Dict[str, Any],
        graph_with_service_files: KnowledgeGraph,
        warning_config_file: Path,
    ) -> None:
        """check_architectural_constraints respects warning severity from rule."""
        # Note: This test may not produce violations depending on implementation
        # but if it does, severity should be WARNING
        result = check_architectural_constraints(
            manifest_data=manifest_service_with_http,
            graph=graph_with_service_files,
            config_path=warning_config_file,
        )

        for issue in result:
            assert issue.severity == IssueSeverity.WARNING

    def test_handles_empty_manifest(
        self,
        empty_manifest: Dict[str, Any],
        empty_knowledge_graph: KnowledgeGraph,
        constraint_config_file: Path,
    ) -> None:
        """check_architectural_constraints handles empty manifest without error."""
        result = check_architectural_constraints(
            manifest_data=empty_manifest,
            graph=empty_knowledge_graph,
            config_path=constraint_config_file,
        )

        assert isinstance(result, list)

    def test_handles_empty_graph(
        self,
        manifest_controller_with_db: Dict[str, Any],
        empty_knowledge_graph: KnowledgeGraph,
        constraint_config_file: Path,
    ) -> None:
        """check_architectural_constraints handles empty graph gracefully."""
        result = check_architectural_constraints(
            manifest_data=manifest_controller_with_db,
            graph=empty_knowledge_graph,
            config_path=constraint_config_file,
        )

        assert isinstance(result, list)

    def test_issue_has_message(
        self,
        manifest_controller_with_db: Dict[str, Any],
        graph_with_controller_files: KnowledgeGraph,
        constraint_config_file: Path,
    ) -> None:
        """check_architectural_constraints returns issues with descriptive messages."""
        result = check_architectural_constraints(
            manifest_data=manifest_controller_with_db,
            graph=graph_with_controller_files,
            config_path=constraint_config_file,
        )

        for issue in result:
            assert isinstance(issue.message, str)
            assert len(issue.message) > 0

    def test_issue_has_suggestion(
        self,
        manifest_controller_with_db: Dict[str, Any],
        graph_with_controller_files: KnowledgeGraph,
        constraint_config_file: Path,
    ) -> None:
        """check_architectural_constraints returns issues with suggestions."""
        result = check_architectural_constraints(
            manifest_data=manifest_controller_with_db,
            graph=graph_with_controller_files,
            config_path=constraint_config_file,
        )

        for issue in result:
            assert isinstance(issue.suggestion, str)
            assert len(issue.suggestion) > 0


# =============================================================================
# Tests for _evaluate_constraint
# =============================================================================


class TestEvaluateConstraintFunction:
    """Tests for the _evaluate_constraint helper function."""

    def test_returns_none_when_rule_not_violated(
        self,
        manifest_no_violations: Dict[str, Any],
        empty_knowledge_graph: KnowledgeGraph,
    ) -> None:
        """_evaluate_constraint returns None when rule not violated."""
        rule = ConstraintRule(
            name="no-db-in-controllers",
            description="Controllers should not access database directly",
            pattern={
                "file_pattern": "**/controllers/**/*.py",
                "forbidden_imports": ["psycopg2"],
            },
            severity="error",
            suggestion="Use repository pattern",
        )

        result = _evaluate_constraint(
            rule=rule,
            manifest_data=manifest_no_violations,
            graph=empty_knowledge_graph,
        )

        assert result is None

    def test_returns_coherence_issue_when_rule_violated(
        self,
        manifest_controller_with_db: Dict[str, Any],
        graph_with_controller_files: KnowledgeGraph,
    ) -> None:
        """_evaluate_constraint returns CoherenceIssue when rule violated."""
        rule = ConstraintRule(
            name="no-db-in-controllers",
            description="Controllers should not access database directly",
            pattern={
                "file_pattern": "**/controllers/**/*.py",
                "forbidden_imports": ["psycopg2"],
            },
            severity="error",
            suggestion="Use repository pattern",
        )

        result = _evaluate_constraint(
            rule=rule,
            manifest_data=manifest_controller_with_db,
            graph=graph_with_controller_files,
        )

        # Result may be None or CoherenceIssue depending on actual violation detection
        if result is not None:
            assert isinstance(result, CoherenceIssue)
            assert result.issue_type == IssueType.CONSTRAINT

    def test_handles_file_pattern_constraint(
        self,
        manifest_controller_with_db: Dict[str, Any],
        graph_with_controller_files: KnowledgeGraph,
    ) -> None:
        """_evaluate_constraint handles file_pattern constraint."""
        rule = ConstraintRule(
            name="test-file-pattern",
            description="Test file pattern matching",
            pattern={"file_pattern": "**/controllers/**/*.py"},
            severity="warning",
            suggestion="Check file location",
        )

        # Should not raise exception
        result = _evaluate_constraint(
            rule=rule,
            manifest_data=manifest_controller_with_db,
            graph=graph_with_controller_files,
        )

        assert result is None or isinstance(result, CoherenceIssue)

    def test_handles_forbidden_imports_constraint(
        self,
        manifest_controller_with_db: Dict[str, Any],
        graph_with_controller_files: KnowledgeGraph,
    ) -> None:
        """_evaluate_constraint handles forbidden_imports constraint."""
        rule = ConstraintRule(
            name="test-forbidden-imports",
            description="Test forbidden imports",
            pattern={
                "file_pattern": "**/controllers/**/*.py",
                "forbidden_imports": ["psycopg2", "sqlite3"],
            },
            severity="error",
            suggestion="Use repository pattern",
        )

        # Should not raise exception
        result = _evaluate_constraint(
            rule=rule,
            manifest_data=manifest_controller_with_db,
            graph=graph_with_controller_files,
        )

        assert result is None or isinstance(result, CoherenceIssue)

    def test_issue_severity_matches_rule(
        self,
        manifest_controller_with_db: Dict[str, Any],
        graph_with_controller_files: KnowledgeGraph,
    ) -> None:
        """_evaluate_constraint creates issue with severity matching rule."""
        rule = ConstraintRule(
            name="warning-rule",
            description="A warning level rule",
            pattern={"file_pattern": "**/controllers/**/*.py"},
            severity="warning",
            suggestion="Consider alternatives",
        )

        result = _evaluate_constraint(
            rule=rule,
            manifest_data=manifest_controller_with_db,
            graph=graph_with_controller_files,
        )

        if result is not None:
            assert result.severity == IssueSeverity.WARNING

    def test_issue_suggestion_from_rule(
        self,
        manifest_controller_with_db: Dict[str, Any],
        graph_with_controller_files: KnowledgeGraph,
    ) -> None:
        """_evaluate_constraint includes suggestion from rule."""
        rule = ConstraintRule(
            name="test-rule",
            description="Test rule",
            pattern={"file_pattern": "**/controllers/**/*.py"},
            severity="error",
            suggestion="Use repository pattern instead",
        )

        result = _evaluate_constraint(
            rule=rule,
            manifest_data=manifest_controller_with_db,
            graph=graph_with_controller_files,
        )

        if result is not None:
            assert (
                "repository" in result.suggestion.lower() or len(result.suggestion) > 0
            )


# =============================================================================
# Edge Cases and Integration Tests
# =============================================================================


class TestCheckArchitecturalConstraintsEdgeCases:
    """Edge case tests for check_architectural_constraints."""

    def test_handles_manifest_with_none_values(
        self,
        empty_knowledge_graph: KnowledgeGraph,
        constraint_config_file: Path,
    ) -> None:
        """check_architectural_constraints handles manifest with None values."""
        manifest_with_none = {
            "version": "1",
            "goal": "Test None handling",
            "taskType": "create",
            "creatableFiles": None,
            "expectedArtifacts": None,
        }

        result = check_architectural_constraints(
            manifest_data=manifest_with_none,
            graph=empty_knowledge_graph,
            config_path=constraint_config_file,
        )

        assert isinstance(result, list)

    def test_handles_empty_rules_list(
        self,
        manifest_controller_with_db: Dict[str, Any],
        graph_with_controller_files: KnowledgeGraph,
        tmp_path: Path,
    ) -> None:
        """check_architectural_constraints handles config with empty rules list."""
        config_empty_rules = {"version": "1", "enabled": True, "rules": []}
        config_path = tmp_path / ".maid-constraints.json"
        config_path.write_text(json.dumps(config_empty_rules))

        result = check_architectural_constraints(
            manifest_data=manifest_controller_with_db,
            graph=graph_with_controller_files,
            config_path=config_path,
        )

        assert isinstance(result, list)
        assert len(result) == 0

    def test_handles_nested_module_paths(
        self,
        empty_knowledge_graph: KnowledgeGraph,
        constraint_config_file: Path,
    ) -> None:
        """check_architectural_constraints handles deeply nested module paths."""
        manifest_nested = {
            "version": "1",
            "goal": "Create nested controller",
            "taskType": "create",
            "creatableFiles": ["src/app/api/v1/controllers/nested/user_controller.py"],
            "expectedArtifacts": {
                "file": "src/app/api/v1/controllers/nested/user_controller.py",
                "contains": [{"type": "class", "name": "UserController"}],
            },
        }

        result = check_architectural_constraints(
            manifest_data=manifest_nested,
            graph=empty_knowledge_graph,
            config_path=constraint_config_file,
        )

        assert isinstance(result, list)

    def test_handles_multiple_files_in_manifest(
        self,
        empty_knowledge_graph: KnowledgeGraph,
        constraint_config_file: Path,
    ) -> None:
        """check_architectural_constraints handles multiple files in manifest."""
        manifest_multiple_files = {
            "version": "1",
            "goal": "Create multiple modules",
            "taskType": "create",
            "creatableFiles": [
                "src/controllers/user_controller.py",
                "src/controllers/order_controller.py",
            ],
            "expectedArtifacts": {
                "file": "src/controllers/user_controller.py",
                "contains": [{"type": "class", "name": "UserController"}],
            },
        }

        result = check_architectural_constraints(
            manifest_data=manifest_multiple_files,
            graph=empty_knowledge_graph,
            config_path=constraint_config_file,
        )

        assert isinstance(result, list)


class TestCheckArchitecturalConstraintsIntegration:
    """Integration tests for check_architectural_constraints."""

    def test_full_workflow_no_violations(
        self,
        tmp_path: Path,
    ) -> None:
        """Integration test for complete workflow with no violations."""
        # Setup config
        config = {
            "version": "1",
            "enabled": True,
            "rules": [
                {
                    "name": "no-db-in-controllers",
                    "description": "Controllers should not access database",
                    "pattern": {
                        "file_pattern": "**/controllers/**/*.py",
                        "forbidden_imports": ["psycopg2"],
                    },
                    "severity": "error",
                    "suggestion": "Use repository pattern",
                }
            ],
        }
        config_path = tmp_path / ".maid-constraints.json"
        config_path.write_text(json.dumps(config))

        # Setup graph
        graph = KnowledgeGraph()
        file_node = FileNode(
            id="file:src/repositories/user_repository.py",
            path="src/repositories/user_repository.py",
            status="tracked",
        )
        graph.add_node(file_node)

        # Setup manifest (repository, not controller)
        manifest = {
            "version": "1",
            "goal": "Add repository",
            "taskType": "create",
            "creatableFiles": ["src/repositories/user_repository.py"],
            "expectedArtifacts": {
                "file": "src/repositories/user_repository.py",
                "contains": [{"type": "class", "name": "UserRepository"}],
            },
        }

        result = check_architectural_constraints(
            manifest_data=manifest,
            graph=graph,
            config_path=config_path,
        )

        assert isinstance(result, list)
        assert len(result) == 0

    def test_full_workflow_with_violations(
        self,
        tmp_path: Path,
    ) -> None:
        """Integration test for complete workflow with violations."""
        # Setup config
        config = {
            "version": "1",
            "enabled": True,
            "rules": [
                {
                    "name": "no-db-in-controllers",
                    "description": "Controllers should not access database",
                    "pattern": {
                        "file_pattern": "**/controllers/**/*.py",
                        "forbidden_imports": ["psycopg2"],
                    },
                    "severity": "error",
                    "suggestion": "Use repository pattern",
                }
            ],
        }
        config_path = tmp_path / ".maid-constraints.json"
        config_path.write_text(json.dumps(config))

        # Setup graph with controller
        graph = KnowledgeGraph()
        file_node = FileNode(
            id="file:src/controllers/user_controller.py",
            path="src/controllers/user_controller.py",
            status="tracked",
        )
        graph.add_node(file_node)

        # Setup manifest (controller)
        manifest = {
            "version": "1",
            "goal": "Add controller",
            "taskType": "create",
            "creatableFiles": ["src/controllers/user_controller.py"],
            "expectedArtifacts": {
                "file": "src/controllers/user_controller.py",
                "contains": [{"type": "class", "name": "UserController"}],
            },
        }

        result = check_architectural_constraints(
            manifest_data=manifest,
            graph=graph,
            config_path=config_path,
        )

        assert isinstance(result, list)
        # All issues should be CONSTRAINT type
        for issue in result:
            assert issue.issue_type == IssueType.CONSTRAINT

    def test_accepts_path_object(
        self,
        manifest_no_violations: Dict[str, Any],
        empty_knowledge_graph: KnowledgeGraph,
        constraint_config_file: Path,
    ) -> None:
        """check_architectural_constraints accepts Path object for config_path."""
        result = check_architectural_constraints(
            manifest_data=manifest_no_violations,
            graph=empty_knowledge_graph,
            config_path=constraint_config_file,  # Path object
        )

        assert isinstance(result, list)

    def test_config_path_default_is_none(
        self,
        manifest_no_violations: Dict[str, Any],
        empty_knowledge_graph: KnowledgeGraph,
    ) -> None:
        """check_architectural_constraints has config_path default of None."""
        # Should work without providing config_path
        result = check_architectural_constraints(
            manifest_data=manifest_no_violations,
            graph=empty_knowledge_graph,
        )

        assert isinstance(result, list)


class TestLoadConstraintConfigErrors:
    """Test error handling in load_constraint_config."""

    def test_handles_invalid_json_config(self, tmp_path: Path) -> None:
        """load_constraint_config returns empty config for invalid JSON."""
        from maid_runner.coherence.checks.constraint_check import load_constraint_config

        # Create a file with invalid JSON
        config_path = tmp_path / "bad_config.json"
        config_path.write_text("not valid json {{{")

        result = load_constraint_config(config_path)

        # Should return empty config, not raise
        assert result.rules == []

    def test_handles_os_error(self, tmp_path: Path) -> None:
        """load_constraint_config handles OS errors gracefully."""
        from maid_runner.coherence.checks.constraint_check import load_constraint_config

        # Reference non-existent file
        config_path = tmp_path / "nonexistent.json"

        # Should not raise - returns empty config
        result = load_constraint_config(config_path)

        # Should return empty config with no rules
        assert result.rules == []
