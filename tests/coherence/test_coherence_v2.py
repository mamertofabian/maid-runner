"""Tests for v2 coherence module - CoherenceEngine using v2 types."""

from maid_runner.core.types import (
    ArtifactKind,
    ArtifactSpec,
    ArgSpec,
    FileMode,
    FileSpec,
    Manifest,
    TaskType,
)
from maid_runner.graph.builder import GraphBuilder
from maid_runner.coherence.engine import CoherenceEngine
from maid_runner.coherence.result import (
    CoherenceIssue,
    CoherenceResult,
    IssueSeverity,
    IssueType,
)
from maid_runner.coherence.checks.base import get_checks
from maid_runner.coherence.checks.duplicate import DuplicateCheck
from maid_runner.coherence.checks.signature import SignatureCheck
from maid_runner.coherence.checks.naming import NamingCheck
from maid_runner.coherence.checks.boundary import ModuleBoundaryCheck
from maid_runner.coherence.checks.dependency import DependencyCheck
from maid_runner.coherence.checks.pattern import PatternCheck
from maid_runner.coherence.checks.constraint import (
    ConstraintCheck,
    load_constraint_config,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_manifest(slug, files_create=(), files_edit=(), supersedes=()):
    return Manifest(
        slug=slug,
        source_path=f"manifests/{slug}.manifest.yaml",
        goal=f"Goal for {slug}",
        validate_commands=(("pytest", "tests/", "-v"),),
        files_create=files_create,
        files_edit=files_edit,
        supersedes=supersedes,
        task_type=TaskType.FEATURE,
    )


def _make_fs(path, artifacts=(), mode=FileMode.CREATE):
    return FileSpec(path=path, artifacts=artifacts, mode=mode)


def _make_art(
    name, kind=ArtifactKind.FUNCTION, of=None, args=(), returns=None, bases=()
):
    return ArtifactSpec(
        kind=kind, name=name, of=of, args=args, returns=returns, bases=bases
    )


# ---------------------------------------------------------------------------
# CoherenceResult
# ---------------------------------------------------------------------------


class TestCoherenceResult:
    def test_empty_result_is_success(self):
        r = CoherenceResult()
        assert r.success
        assert r.error_count == 0
        assert r.warning_count == 0

    def test_error_makes_failure(self):
        issue = CoherenceIssue(
            issue_type=IssueType.DUPLICATE,
            severity=IssueSeverity.ERROR,
            message="dup",
        )
        r = CoherenceResult(issues=[issue])
        assert not r.success
        assert r.error_count == 1

    def test_warning_is_still_success(self):
        issue = CoherenceIssue(
            issue_type=IssueType.NAMING,
            severity=IssueSeverity.WARNING,
            message="bad name",
        )
        r = CoherenceResult(issues=[issue])
        assert r.success
        assert r.warning_count == 1

    def test_to_dict(self):
        issue = CoherenceIssue(
            issue_type=IssueType.DUPLICATE,
            severity=IssueSeverity.ERROR,
            message="dup",
            file="src/a.py",
            artifact="func_a",
            manifests=("m1", "m2"),
            suggestion="Fix it",
        )
        r = CoherenceResult(issues=[issue], checks_run=["duplicate"])
        d = r.to_dict()
        assert d["success"] is False
        assert d["errors"] == 1
        assert d["checks_run"] == ["duplicate"]
        assert len(d["issues"]) == 1
        assert d["issues"][0]["type"] == "duplicate"

    def test_to_json(self):
        r = CoherenceResult()
        j = r.to_json()
        assert '"success": true' in j


# ---------------------------------------------------------------------------
# CoherenceIssue
# ---------------------------------------------------------------------------


class TestCoherenceIssue:
    def test_to_dict(self):
        issue = CoherenceIssue(
            issue_type=IssueType.SIGNATURE_CONFLICT,
            severity=IssueSeverity.WARNING,
            message="sig mismatch",
            file="src/svc.py",
            manifests=("m1",),
        )
        d = issue.to_dict()
        assert d["type"] == "signature_conflict"
        assert d["severity"] == "warning"
        assert d["message"] == "sig mismatch"
        assert d["file"] == "src/svc.py"
        assert d["manifests"] == ["m1"]

    def test_to_dict_minimal(self):
        issue = CoherenceIssue(
            issue_type=IssueType.NAMING,
            severity=IssueSeverity.INFO,
            message="info msg",
        )
        d = issue.to_dict()
        assert "file" not in d
        assert "artifact" not in d
        assert "manifests" not in d


# ---------------------------------------------------------------------------
# DuplicateCheck
# ---------------------------------------------------------------------------


class TestDuplicateCheck:
    def test_no_duplicates(self):
        m1 = _make_manifest(
            "m1",
            files_create=(_make_fs("a.py", (_make_art("func_a"),)),),
        )
        m2 = _make_manifest(
            "m2",
            files_create=(_make_fs("b.py", (_make_art("func_b"),)),),
        )
        graph = GraphBuilder().build_from_manifests([m1, m2])
        chain_manifests = [m1, m2]

        check = DuplicateCheck()
        issues = check.run(graph, chain_manifests)
        assert len(issues) == 0

    def test_same_file_duplicate_detected(self):
        m1 = _make_manifest(
            "m1",
            files_create=(_make_fs("a.py", (_make_art("func_x"),)),),
        )
        m2 = _make_manifest(
            "m2",
            files_create=(_make_fs("a.py", (_make_art("func_x"),)),),
        )
        graph = GraphBuilder().build_from_manifests([m1, m2])

        check = DuplicateCheck()
        issues = check.run(graph, [m1, m2])
        assert len(issues) >= 1
        assert issues[0].severity == IssueSeverity.ERROR

    def test_superseded_duplicates_ignored(self):
        m1 = _make_manifest(
            "old",
            files_create=(_make_fs("a.py", (_make_art("func_x"),)),),
        )
        m2 = _make_manifest(
            "new",
            files_create=(_make_fs("a.py", (_make_art("func_x"),)),),
            supersedes=("old",),
        )
        graph = GraphBuilder().build_from_manifests([m1, m2])

        check = DuplicateCheck()
        issues = check.run(graph, [m1, m2])
        # Should not flag since m2 supersedes m1
        assert len(issues) == 0


# ---------------------------------------------------------------------------
# SignatureCheck
# ---------------------------------------------------------------------------


class TestSignatureCheck:
    def test_no_conflict(self):
        m1 = _make_manifest(
            "m1",
            files_create=(
                _make_fs(
                    "a.py",
                    (_make_art("fn", args=(ArgSpec("x", "int"),), returns="str"),),
                ),
            ),
        )
        m2 = _make_manifest(
            "m2",
            files_edit=(
                _make_fs(
                    "a.py",
                    (_make_art("fn", args=(ArgSpec("x", "int"),), returns="str"),),
                    mode=FileMode.EDIT,
                ),
            ),
        )
        graph = GraphBuilder().build_from_manifests([m1, m2])

        check = SignatureCheck()
        issues = check.run(graph, [m1, m2])
        assert len(issues) == 0

    def test_conflict_detected(self):
        m1 = _make_manifest(
            "m1",
            files_create=(
                _make_fs(
                    "a.py",
                    (_make_art("fn", args=(ArgSpec("x", "int"),), returns="str"),),
                ),
            ),
        )
        m2 = _make_manifest(
            "m2",
            files_create=(
                _make_fs(
                    "a.py",
                    (
                        _make_art(
                            "fn",
                            args=(ArgSpec("x", "int"), ArgSpec("y", "bool")),
                            returns="int",
                        ),
                    ),
                ),
            ),
        )
        graph = GraphBuilder().build_from_manifests([m1, m2])

        check = SignatureCheck()
        issues = check.run(graph, [m1, m2])
        assert len(issues) >= 1
        assert issues[0].issue_type == IssueType.SIGNATURE_CONFLICT


# ---------------------------------------------------------------------------
# NamingCheck
# ---------------------------------------------------------------------------


class TestNamingCheck:
    def test_python_snake_case_ok(self):
        m = _make_manifest(
            "m1",
            files_create=(_make_fs("a.py", (_make_art("my_func"),)),),
        )
        graph = GraphBuilder().build_from_manifests([m])
        check = NamingCheck()
        issues = check.run(graph, [m])
        # Snake case function should not be flagged
        errors = [i for i in issues if i.severity == IssueSeverity.ERROR]
        assert len(errors) == 0

    def test_python_class_pascal_ok(self):
        m = _make_manifest(
            "m1",
            files_create=(
                _make_fs("a.py", (_make_art("MyClass", ArtifactKind.CLASS),)),
            ),
        )
        graph = GraphBuilder().build_from_manifests([m])
        check = NamingCheck()
        issues = check.run(graph, [m])
        errors = [i for i in issues if i.severity == IssueSeverity.ERROR]
        assert len(errors) == 0


# ---------------------------------------------------------------------------
# get_checks
# ---------------------------------------------------------------------------


class TestGetChecks:
    def test_default_checks(self):
        checks = get_checks()
        names = [c.name for c in checks]
        assert "duplicate" in names
        assert "signature" in names
        assert "naming" in names

    def test_enabled_filter(self):
        checks = get_checks(enabled=["duplicate"])
        assert len(checks) == 1
        assert checks[0].name == "duplicate"

    def test_disabled_filter(self):
        checks = get_checks(disabled=["duplicate"])
        names = [c.name for c in checks]
        assert "duplicate" not in names


# ---------------------------------------------------------------------------
# CoherenceEngine
# ---------------------------------------------------------------------------


class TestCoherenceEngine:
    def test_validate_clean(self):
        m1 = _make_manifest(
            "m1",
            files_create=(_make_fs("a.py", (_make_art("func_a"),)),),
        )
        m2 = _make_manifest(
            "m2",
            files_create=(_make_fs("b.py", (_make_art("func_b"),)),),
        )
        graph = GraphBuilder().build_from_manifests([m1, m2])

        engine = CoherenceEngine()
        result = engine.validate([m1, m2], graph=graph)
        assert isinstance(result, CoherenceResult)
        assert len(result.checks_run) > 0

    def test_validate_with_graph(self):
        m = _make_manifest(
            "m1",
            files_create=(_make_fs("a.py", (_make_art("func_a"),)),),
        )
        graph = GraphBuilder().build_from_manifests([m])
        engine = CoherenceEngine()
        result = engine.validate([m], graph=graph)
        assert isinstance(result, CoherenceResult)

    def test_validate_single(self):
        m1 = _make_manifest(
            "m1",
            files_create=(_make_fs("a.py", (_make_art("func_a"),)),),
        )
        m2 = _make_manifest(
            "m2",
            files_create=(_make_fs("b.py", (_make_art("func_b"),)),),
        )
        graph = GraphBuilder().build_from_manifests([m1, m2])

        engine = CoherenceEngine()
        result = engine.validate_single(m1, [m1, m2], graph=graph)
        assert isinstance(result, CoherenceResult)

    def test_custom_checks(self):
        m = _make_manifest(
            "m",
            files_create=(_make_fs("a.py", (_make_art("f"),)),),
        )
        graph = GraphBuilder().build_from_manifests([m])

        engine = CoherenceEngine(checks=[DuplicateCheck()])
        result = engine.validate([m], graph=graph)
        assert result.checks_run == ["duplicate"]


# ---------------------------------------------------------------------------
# ModuleBoundaryCheck
# ---------------------------------------------------------------------------


class TestModuleBoundaryCheck:
    def test_no_violation_same_module(self):
        m = _make_manifest(
            "m1",
            files_create=(
                _make_fs(
                    "src/auth/service.py",
                    (_make_art("AuthService", ArtifactKind.CLASS),),
                ),
            ),
        )
        graph = GraphBuilder().build_from_manifests([m])
        check = ModuleBoundaryCheck()
        issues = check.run(graph, [m])
        boundary_issues = [
            i for i in issues if i.issue_type == IssueType.BOUNDARY_VIOLATION
        ]
        assert len(boundary_issues) == 0

    def test_repository_type_in_controller_flagged(self):
        """Controllers accessing data module via Repository type hint."""
        m = _make_manifest(
            "m1",
            files_create=(
                _make_fs(
                    "src/controllers/user_ctrl.py",
                    (
                        _make_art(
                            "get_user",
                            args=(ArgSpec("repo", "UserRepository"),),
                        ),
                    ),
                ),
            ),
        )
        graph = GraphBuilder().build_from_manifests([m])
        check = ModuleBoundaryCheck()
        issues = check.run(graph, [m])
        boundary_issues = [
            i for i in issues if i.issue_type == IssueType.BOUNDARY_VIOLATION
        ]
        assert len(boundary_issues) >= 1
        assert boundary_issues[0].severity == IssueSeverity.WARNING

    def test_private_file_access_flagged(self):
        """Accessing private files from another module is flagged."""
        m = Manifest(
            slug="m1",
            source_path="manifests/m1.manifest.yaml",
            goal="Test",
            validate_commands=(("pytest",),),
            files_create=(_make_fs("src/api/handler.py", (_make_art("handler"),)),),
            files_read=("src/internal/_helpers.py",),
            task_type=TaskType.FEATURE,
        )
        graph = GraphBuilder().build_from_manifests([m])
        check = ModuleBoundaryCheck()
        issues = check.run(graph, [m])
        boundary_issues = [
            i for i in issues if i.issue_type == IssueType.BOUNDARY_VIOLATION
        ]
        assert len(boundary_issues) >= 1


# ---------------------------------------------------------------------------
# DependencyCheck
# ---------------------------------------------------------------------------


class TestDependencyCheck:
    def test_all_deps_satisfied(self):
        m1 = _make_manifest(
            "m1",
            files_create=(_make_fs("src/utils.py", (_make_art("util"),)),),
        )
        m2 = Manifest(
            slug="m2",
            source_path="manifests/m2.manifest.yaml",
            goal="Test",
            validate_commands=(("pytest",),),
            files_create=(_make_fs("src/svc.py", (_make_art("svc"),)),),
            files_read=("src/utils.py",),
            task_type=TaskType.FEATURE,
        )
        graph = GraphBuilder().build_from_manifests([m1, m2])
        check = DependencyCheck()
        issues = check.run(graph, [m1, m2])
        dep_errors = [
            i
            for i in issues
            if i.issue_type == IssueType.DEPENDENCY
            and i.severity == IssueSeverity.ERROR
        ]
        assert len(dep_errors) == 0

    def test_missing_dep_flagged(self):
        m = Manifest(
            slug="m1",
            source_path="manifests/m1.manifest.yaml",
            goal="Test",
            validate_commands=(("pytest",),),
            files_create=(_make_fs("src/svc.py", (_make_art("svc"),)),),
            files_read=("src/nonexistent.py",),
            task_type=TaskType.FEATURE,
        )
        graph = GraphBuilder().build_from_manifests([m])
        check = DependencyCheck()
        issues = check.run(graph, [m])
        dep_errors = [
            i
            for i in issues
            if i.issue_type == IssueType.DEPENDENCY
            and i.severity == IssueSeverity.ERROR
        ]
        assert len(dep_errors) >= 1
        assert "nonexistent" in dep_errors[0].message

    def test_missing_base_class_warning(self):
        m = _make_manifest(
            "m1",
            files_create=(
                _make_fs(
                    "src/svc.py",
                    (
                        _make_art(
                            "MyService", ArtifactKind.CLASS, bases=("UnknownBase",)
                        ),
                    ),
                ),
            ),
        )
        graph = GraphBuilder().build_from_manifests([m])
        check = DependencyCheck()
        issues = check.run(graph, [m])
        base_warnings = [
            i
            for i in issues
            if i.issue_type == IssueType.DEPENDENCY and "UnknownBase" in i.message
        ]
        assert len(base_warnings) >= 1


# ---------------------------------------------------------------------------
# PatternCheck
# ---------------------------------------------------------------------------


class TestPatternCheck:
    def test_no_patterns_no_issues(self):
        """No pattern classes in graph means no issues."""
        m = _make_manifest(
            "m1",
            files_create=(_make_fs("src/utils.py", (_make_art("helper"),)),),
        )
        graph = GraphBuilder().build_from_manifests([m])
        check = PatternCheck()
        issues = check.run(graph, [m])
        assert len(issues) == 0

    def test_repository_in_wrong_module(self):
        """Repository class not in 'repositories' module is flagged."""
        # First, create a repository pattern in the graph
        m_repo = _make_manifest(
            "m-repo",
            files_create=(
                _make_fs(
                    "src/repositories/user_repo.py",
                    (_make_art("UserRepository", ArtifactKind.CLASS),),
                ),
            ),
        )
        # Now test a repository in the wrong module
        m_wrong = _make_manifest(
            "m-wrong",
            files_create=(
                _make_fs(
                    "src/utils/helpers.py",
                    (_make_art("CacheRepository", ArtifactKind.CLASS),),
                ),
            ),
        )
        graph = GraphBuilder().build_from_manifests([m_repo, m_wrong])
        check = PatternCheck()
        issues = check.run(graph, [m_repo, m_wrong])
        pattern_issues = [i for i in issues if i.issue_type == IssueType.PATTERN]
        # CacheRepository is in utils, not repositories
        assert len(pattern_issues) >= 1
        assert "CacheRepository" in pattern_issues[0].message

    def test_correct_module_no_issue(self):
        """Repository class in 'repositories' module is fine."""
        m = _make_manifest(
            "m1",
            files_create=(
                _make_fs(
                    "src/repositories/user_repo.py",
                    (_make_art("UserRepository", ArtifactKind.CLASS),),
                ),
            ),
        )
        graph = GraphBuilder().build_from_manifests([m])
        check = PatternCheck()
        issues = check.run(graph, [m])
        pattern_issues = [
            i
            for i in issues
            if i.issue_type == IssueType.PATTERN
            and "UserRepository" in (i.artifact or "")
        ]
        assert len(pattern_issues) == 0


# ---------------------------------------------------------------------------
# ConstraintCheck
# ---------------------------------------------------------------------------


class TestConstraintCheck:
    def test_no_config_no_issues(self, tmp_path):
        """No config file means no issues."""
        m = _make_manifest(
            "m1",
            files_create=(_make_fs("src/a.py", (_make_art("f"),)),),
        )
        graph = GraphBuilder().build_from_manifests([m])
        check = ConstraintCheck(config_path=tmp_path / ".maid-constraints.json")
        issues = check.run(graph, [m])
        assert len(issues) == 0

    def test_forbidden_imports_violation(self, tmp_path):
        """Constraint with file_pattern + forbidden_imports flags matching files."""
        config = {
            "version": "1",
            "enabled": True,
            "rules": [
                {
                    "name": "no-direct-db",
                    "description": "Controllers must not import database directly",
                    "pattern": {
                        "file_pattern": "src/controllers/*.py",
                        "forbidden_imports": ["database"],
                    },
                    "severity": "error",
                    "suggestion": "Use a service layer",
                }
            ],
        }
        import json

        config_path = tmp_path / ".maid-constraints.json"
        config_path.write_text(json.dumps(config))

        m = _make_manifest(
            "m1",
            files_create=(
                _make_fs("src/controllers/user.py", (_make_art("handler"),)),
            ),
        )
        graph = GraphBuilder().build_from_manifests([m])
        check = ConstraintCheck(config_path=config_path)
        issues = check.run(graph, [m])
        constraint_issues = [i for i in issues if i.issue_type == IssueType.CONSTRAINT]
        assert len(constraint_issues) >= 1
        assert constraint_issues[0].severity == IssueSeverity.ERROR

    def test_disabled_config(self, tmp_path):
        """Disabled config returns no issues."""
        config = {"version": "1", "enabled": False, "rules": []}
        import json

        config_path = tmp_path / ".maid-constraints.json"
        config_path.write_text(json.dumps(config))

        m = _make_manifest("m1", files_create=(_make_fs("a.py", (_make_art("f"),)),))
        graph = GraphBuilder().build_from_manifests([m])
        check = ConstraintCheck(config_path=config_path)
        issues = check.run(graph, [m])
        assert len(issues) == 0

    def test_max_artifacts_constraint(self, tmp_path):
        """max_artifacts_per_file constraint flags files with too many artifacts."""
        config = {
            "version": "1",
            "enabled": True,
            "rules": [
                {
                    "name": "max-artifacts",
                    "description": "Too many artifacts",
                    "pattern": {
                        "file_pattern": "*.py",
                        "max_artifacts_per_file": 2,
                    },
                    "severity": "warning",
                    "suggestion": "Split into smaller modules",
                }
            ],
        }
        import json

        config_path = tmp_path / ".maid-constraints.json"
        config_path.write_text(json.dumps(config))

        m = _make_manifest(
            "m1",
            files_create=(
                _make_fs(
                    "big.py",
                    (
                        _make_art("f1"),
                        _make_art("f2"),
                        _make_art("f3"),
                    ),
                ),
            ),
        )
        graph = GraphBuilder().build_from_manifests([m])
        check = ConstraintCheck(config_path=config_path)
        issues = check.run(graph, [m])
        assert len(issues) >= 1
        assert issues[0].severity == IssueSeverity.WARNING


class TestLoadConstraintConfig:
    def test_missing_file_returns_default(self, tmp_path):
        config = load_constraint_config(tmp_path / "nope.json")
        assert config.enabled is True
        assert config.rules == []

    def test_valid_config(self, tmp_path):
        import json

        data = {
            "version": "2",
            "enabled": True,
            "rules": [
                {
                    "name": "test-rule",
                    "description": "desc",
                    "pattern": {"file_pattern": "*.py"},
                    "severity": "warning",
                    "suggestion": "fix it",
                }
            ],
        }
        path = tmp_path / ".maid-constraints.json"
        path.write_text(json.dumps(data))
        config = load_constraint_config(path)
        assert config.version == "2"
        assert len(config.rules) == 1
        assert config.rules[0].name == "test-rule"
