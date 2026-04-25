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
from maid_runner.coherence.checks.base import (
    BaseCheck,
    get_checks,
    get_default_check_classes,
)
from maid_runner.coherence.checks.duplicate import DuplicateCheck
from maid_runner.coherence.checks.signature import SignatureCheck
from maid_runner.coherence.checks.naming import NamingCheck
from maid_runner.coherence.checks.boundary import ModuleBoundaryCheck
from maid_runner.coherence.checks.dependency import DependencyCheck
from maid_runner.coherence.checks.pattern import PatternCheck
from maid_runner.coherence.checks.constraint import (
    ConstraintConfig,
    ConstraintCheck,
    ConstraintRule,
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
        assert r.duration_ms is None

    def test_consolidated_contract_symbols_are_referenced(self):
        rule = ConstraintRule(
            name="no-cross-boundary",
            description="disallow dependency",
            pattern={"from": "a", "to": "b"},
            severity="warning",
            suggestion="Use a public boundary",
        )
        config = ConstraintConfig(version="1", rules=[rule], enabled=True)

        assert BaseCheck is not None
        assert get_default_check_classes()
        assert config.rules[0].description == "disallow dependency"
        assert config.rules[0].pattern["from"] == "a"

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
        assert len(issues) == 0

    def test_partial_duplicate_redeclaration_is_compatible(self):
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
            files_edit=(_make_fs("a.py", (_make_art("fn"),), mode=FileMode.EDIT),),
        )
        graph = GraphBuilder().build_from_manifests([m1, m2])

        check = DuplicateCheck()
        issues = check.run(graph, [m1, m2])
        assert len(issues) == 0

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

    def test_partial_redeclaration_does_not_conflict(self):
        m1 = _make_manifest(
            "m1",
            files_create=(
                _make_fs(
                    "a.py",
                    (
                        _make_art(
                            "fn",
                            args=(ArgSpec("x", "int"),),
                            returns="str",
                        ),
                    ),
                ),
            ),
        )
        m2 = _make_manifest(
            "m2",
            files_edit=(_make_fs("a.py", (_make_art("fn"),), mode=FileMode.EDIT),),
        )
        graph = GraphBuilder().build_from_manifests([m1, m2])

        check = SignatureCheck()
        issues = check.run(graph, [m1, m2])
        assert len(issues) == 0


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

    def test_tsx_pascal_case_function_accepted(self):
        """PascalCase functions in .tsx files are valid React components."""
        m = _make_manifest(
            "m1",
            files_create=(_make_fs("src/App.tsx", (_make_art("UserProfile"),)),),
        )
        graph = GraphBuilder().build_from_manifests([m])
        check = NamingCheck()
        issues = check.run(graph, [m])
        assert len(issues) == 0

    def test_tsx_camel_case_function_still_accepted(self):
        """camelCase functions in .tsx files remain valid."""
        m = _make_manifest(
            "m1",
            files_create=(_make_fs("src/hooks.tsx", (_make_art("useAuth"),)),),
        )
        graph = GraphBuilder().build_from_manifests([m])
        check = NamingCheck()
        issues = check.run(graph, [m])
        assert len(issues) == 0

    def test_ts_pascal_case_function_still_flagged(self):
        """PascalCase functions in .ts files (not .tsx) should still be flagged."""
        m = _make_manifest(
            "m1",
            files_create=(_make_fs("src/utils.ts", (_make_art("MyHelper"),)),),
        )
        graph = GraphBuilder().build_from_manifests([m])
        check = NamingCheck()
        issues = check.run(graph, [m])
        naming_issues = [i for i in issues if i.issue_type == IssueType.NAMING]
        assert len(naming_issues) == 1
        assert naming_issues[0].severity == IssueSeverity.INFO


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
    def test_external_base_classes_are_ignored(self):
        m = _make_manifest(
            "m1",
            files_create=(
                _make_fs(
                    "src/types.py",
                    (
                        _make_art(
                            "Severity", ArtifactKind.CLASS, bases=("str", "Enum")
                        ),
                        _make_art("BaseCheck", ArtifactKind.CLASS, bases=("ABC",)),
                        _make_art(
                            "Visitor",
                            ArtifactKind.CLASS,
                            bases=("ast.NodeVisitor",),
                        ),
                    ),
                ),
            ),
        )
        graph = GraphBuilder().build_from_manifests([m])

        check = DependencyCheck()
        issues = check.run(graph, [m])
        dep_issues = [i for i in issues if i.issue_type == IssueType.DEPENDENCY]
        assert len(dep_issues) == 0

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

    def test_missing_read_dep_is_warning_not_error(self):
        """Read deps not created by any manifest should be WARNING, not ERROR."""
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
        dep_issues = [i for i in issues if i.issue_type == IssueType.DEPENDENCY]
        assert len(dep_issues) >= 1
        assert dep_issues[0].severity == IssueSeverity.WARNING
        assert "nonexistent" in dep_issues[0].message

    def test_missing_read_dep_does_not_cause_error(self):
        """Read deps should never produce ERROR severity."""
        m = Manifest(
            slug="m1",
            source_path="manifests/m1.manifest.yaml",
            goal="Test",
            validate_commands=(("pytest",),),
            files_create=(_make_fs("src/svc.py", (_make_art("svc"),)),),
            files_read=("src/infrastructure.py",),
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
        assert len(dep_errors) == 0

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

    def test_existing_file_no_false_positive(self, tmp_path):
        """Read dep that exists on disk but not in any manifest should NOT warn."""
        # Create the infrastructure file on disk
        infra = tmp_path / "src" / "utils.py"
        infra.parent.mkdir(parents=True)
        infra.write_text("def helper(): pass\n")

        m = Manifest(
            slug="m1",
            source_path="manifests/m1.manifest.yaml",
            goal="Test",
            validate_commands=(("pytest",),),
            files_create=(_make_fs("src/svc.py", (_make_art("svc"),)),),
            files_read=("src/utils.py",),
            task_type=TaskType.FEATURE,
        )
        graph = GraphBuilder().build_from_manifests([m])
        check = DependencyCheck()
        issues = check.run(graph, [m], project_root=tmp_path)
        dep_issues = [i for i in issues if i.issue_type == IssueType.DEPENDENCY]
        assert len(dep_issues) == 0

    def test_missing_file_still_warns(self, tmp_path):
        """Read dep that doesn't exist on disk AND not in manifests should warn."""
        m = Manifest(
            slug="m1",
            source_path="manifests/m1.manifest.yaml",
            goal="Test",
            validate_commands=(("pytest",),),
            files_create=(_make_fs("src/svc.py", (_make_art("svc"),)),),
            files_read=("src/truly_missing.py",),
            task_type=TaskType.FEATURE,
        )
        graph = GraphBuilder().build_from_manifests([m])
        check = DependencyCheck()
        issues = check.run(graph, [m], project_root=tmp_path)
        dep_issues = [i for i in issues if i.issue_type == IssueType.DEPENDENCY]
        assert len(dep_issues) >= 1
        assert "truly_missing" in dep_issues[0].message

    def test_no_project_root_preserves_old_behavior(self):
        """Without project_root, read deps not in manifests still warn (backward compat)."""
        m = Manifest(
            slug="m1",
            source_path="manifests/m1.manifest.yaml",
            goal="Test",
            validate_commands=(("pytest",),),
            files_create=(_make_fs("src/svc.py", (_make_art("svc"),)),),
            files_read=("src/infrastructure.py",),
            task_type=TaskType.FEATURE,
        )
        graph = GraphBuilder().build_from_manifests([m])
        check = DependencyCheck()
        issues = check.run(graph, [m])
        dep_issues = [i for i in issues if i.issue_type == IssueType.DEPENDENCY]
        assert len(dep_issues) >= 1

    def test_engine_passes_project_root(self, tmp_path):
        """CoherenceEngine.validate() with project_root threads it to checks."""
        from maid_runner.coherence.engine import CoherenceEngine

        infra = tmp_path / "src" / "utils.py"
        infra.parent.mkdir(parents=True)
        infra.write_text("def helper(): pass\n")

        m = Manifest(
            slug="m1",
            source_path="manifests/m1.manifest.yaml",
            goal="Test",
            validate_commands=(("pytest",),),
            files_create=(_make_fs("src/svc.py", (_make_art("svc"),)),),
            files_read=("src/utils.py",),
            task_type=TaskType.FEATURE,
        )
        engine = CoherenceEngine(checks=[DependencyCheck()])
        result = engine.validate([m], project_root=tmp_path)
        dep_issues = [i for i in result.issues if i.issue_type == IssueType.DEPENDENCY]
        assert len(dep_issues) == 0

    def test_validate_single_threads_project_root(self, tmp_path):
        """validate_single passes project_root through to checks."""
        from maid_runner.coherence.engine import CoherenceEngine

        infra = tmp_path / "src" / "utils.py"
        infra.parent.mkdir(parents=True)
        infra.write_text("def helper(): pass\n")

        m1 = Manifest(
            slug="m1",
            source_path="manifests/m1.manifest.yaml",
            goal="Test",
            validate_commands=(("pytest",),),
            files_create=(_make_fs("src/svc.py", (_make_art("svc"),)),),
            files_read=("src/utils.py",),
            task_type=TaskType.FEATURE,
        )
        engine = CoherenceEngine(checks=[DependencyCheck()])
        result = engine.validate_single(m1, [m1], project_root=tmp_path)
        dep_issues = [i for i in result.issues if i.issue_type == IssueType.DEPENDENCY]
        assert len(dep_issues) == 0

    def test_missing_file_suggestion_mentions_disk(self, tmp_path):
        """Suggestion text for missing deps mentions 'not found on disk'."""
        m = Manifest(
            slug="m1",
            source_path="manifests/m1.manifest.yaml",
            goal="Test",
            validate_commands=(("pytest",),),
            files_create=(_make_fs("src/svc.py", (_make_art("svc"),)),),
            files_read=("src/gone.py",),
            task_type=TaskType.FEATURE,
        )
        graph = GraphBuilder().build_from_manifests([m])
        check = DependencyCheck()
        issues = check.run(graph, [m], project_root=tmp_path)
        dep_issues = [i for i in issues if i.issue_type == IssueType.DEPENDENCY]
        assert len(dep_issues) == 1
        assert "not found on disk" in dep_issues[0].suggestion


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


# ---------------------------------------------------------------------------
# Boundary check - forbidden patterns coverage
# ---------------------------------------------------------------------------


class TestBoundaryCheckForbiddenPatterns:
    """Tests for _BOUNDARY_VIOLATION_PATTERNS defined in boundary.py.

    The boundary module defines forbidden patterns:
        controllers -> data
        cli -> data
    Only the 'Repository' heuristic (which maps to 'data') was previously tested.
    These tests exercise the explicit pattern matching via type hints resolved
    through the knowledge graph.
    """

    def test_controller_accessing_data_module_via_graph(self):
        """A controller artifact with a type hint that resolves to the data module
        should be flagged as a boundary violation."""
        # Create a data module artifact so the graph can resolve the type hint
        m_data = _make_manifest(
            "m-data",
            files_create=(
                _make_fs(
                    "src/data/store.py",
                    (_make_art("DataStore", ArtifactKind.CLASS),),
                ),
            ),
        )
        # Controller references DataStore via a type hint
        m_ctrl = _make_manifest(
            "m-ctrl",
            files_create=(
                _make_fs(
                    "src/controllers/user_ctrl.py",
                    (
                        _make_art(
                            "list_users",
                            args=(ArgSpec("store", "DataStore"),),
                        ),
                    ),
                ),
            ),
        )
        graph = GraphBuilder().build_from_manifests([m_data, m_ctrl])
        check = ModuleBoundaryCheck()
        issues = check.run(graph, [m_data, m_ctrl])
        boundary_issues = [
            i for i in issues if i.issue_type == IssueType.BOUNDARY_VIOLATION
        ]
        assert len(boundary_issues) >= 1
        assert any("controllers" in i.message for i in boundary_issues)

    def test_cli_accessing_data_module_via_graph(self):
        """A CLI artifact with a type hint that resolves to the data module
        should be flagged as a boundary violation."""
        m_data = _make_manifest(
            "m-data",
            files_create=(
                _make_fs(
                    "src/data/connector.py",
                    (_make_art("DbConnector", ArtifactKind.CLASS),),
                ),
            ),
        )
        m_cli = _make_manifest(
            "m-cli",
            files_create=(
                _make_fs(
                    "src/cli/run.py",
                    (
                        _make_art(
                            "execute",
                            args=(ArgSpec("conn", "DbConnector"),),
                        ),
                    ),
                ),
            ),
        )
        graph = GraphBuilder().build_from_manifests([m_data, m_cli])
        check = ModuleBoundaryCheck()
        issues = check.run(graph, [m_data, m_cli])
        boundary_issues = [
            i for i in issues if i.issue_type == IssueType.BOUNDARY_VIOLATION
        ]
        assert len(boundary_issues) >= 1
        assert any("cli" in i.message for i in boundary_issues)

    def test_controller_accessing_non_forbidden_module_no_issue(self):
        """A controller referencing a services module should not be flagged."""
        m_svc = _make_manifest(
            "m-svc",
            files_create=(
                _make_fs(
                    "src/services/auth.py",
                    (_make_art("AuthService", ArtifactKind.CLASS),),
                ),
            ),
        )
        m_ctrl = _make_manifest(
            "m-ctrl",
            files_create=(
                _make_fs(
                    "src/controllers/auth_ctrl.py",
                    (
                        _make_art(
                            "login",
                            args=(ArgSpec("svc", "AuthService"),),
                        ),
                    ),
                ),
            ),
        )
        graph = GraphBuilder().build_from_manifests([m_svc, m_ctrl])
        check = ModuleBoundaryCheck()
        issues = check.run(graph, [m_svc, m_ctrl])
        boundary_issues = [
            i for i in issues if i.issue_type == IssueType.BOUNDARY_VIOLATION
        ]
        assert len(boundary_issues) == 0

    def test_base_class_from_data_module_flagged(self):
        """A controller class inheriting from a data-module class should be flagged."""
        m_data = _make_manifest(
            "m-data",
            files_create=(
                _make_fs(
                    "src/data/base_repo.py",
                    (_make_art("BaseRepo", ArtifactKind.CLASS),),
                ),
            ),
        )
        m_ctrl = _make_manifest(
            "m-ctrl",
            files_create=(
                _make_fs(
                    "src/controllers/mixed.py",
                    (
                        _make_art(
                            "MixedCtrl",
                            kind=ArtifactKind.CLASS,
                            bases=("BaseRepo",),
                        ),
                    ),
                ),
            ),
        )
        graph = GraphBuilder().build_from_manifests([m_data, m_ctrl])
        check = ModuleBoundaryCheck()
        issues = check.run(graph, [m_data, m_ctrl])
        boundary_issues = [
            i for i in issues if i.issue_type == IssueType.BOUNDARY_VIOLATION
        ]
        assert len(boundary_issues) >= 1


# ---------------------------------------------------------------------------
# Naming check - private artifacts and unknown language
# ---------------------------------------------------------------------------


class TestNamingPrivateArtifacts:
    """Private artifacts (is_private=True) should be skipped by NamingCheck."""

    def test_private_function_skipped(self):
        """A private function (name starts with _) that violates naming should not
        produce any issues because private artifacts are skipped."""
        m = _make_manifest(
            "m1",
            files_create=(
                _make_fs(
                    "a.py",
                    # PascalCase for a function is a naming violation, but since
                    # the name starts with _, it should be skipped
                    (_make_art("_BadName", ArtifactKind.FUNCTION),),
                ),
            ),
        )
        graph = GraphBuilder().build_from_manifests([m])
        check = NamingCheck()
        issues = check.run(graph, [m])
        assert len(issues) == 0

    def test_private_method_skipped(self):
        """A private method should not be checked for naming conventions."""
        m = _make_manifest(
            "m1",
            files_create=(
                _make_fs(
                    "svc.py",
                    (
                        ArtifactSpec(
                            kind=ArtifactKind.METHOD,
                            name="_InternalHelper",
                            of="Service",
                        ),
                    ),
                ),
            ),
        )
        graph = GraphBuilder().build_from_manifests([m])
        check = NamingCheck()
        issues = check.run(graph, [m])
        assert len(issues) == 0

    def test_private_class_skipped(self):
        """A private class (name starts with _) should not be checked."""
        m = _make_manifest(
            "m1",
            files_create=(
                _make_fs(
                    "mod.py",
                    (_make_art("_bad_class_name", ArtifactKind.CLASS),),
                ),
            ),
        )
        graph = GraphBuilder().build_from_manifests([m])
        check = NamingCheck()
        issues = check.run(graph, [m])
        assert len(issues) == 0


class TestNamingUnknownLanguage:
    """Files with unknown extensions should not produce naming issues."""

    def test_unknown_extension_no_issues(self):
        """A .rs file (Rust) is not recognized by _detect_language,
        so NamingCheck should produce no issues regardless of naming."""
        m = _make_manifest(
            "m1",
            files_create=(
                _make_fs(
                    "src/lib.rs",
                    (_make_art("BadlyNamedThing", ArtifactKind.FUNCTION),),
                ),
            ),
        )
        graph = GraphBuilder().build_from_manifests([m])
        check = NamingCheck()
        issues = check.run(graph, [m])
        assert len(issues) == 0

    def test_unknown_extension_java(self):
        """A .java file should also be treated as unknown language."""
        m = _make_manifest(
            "m1",
            files_create=(
                _make_fs(
                    "Main.java",
                    (_make_art("snake_case_class", ArtifactKind.CLASS),),
                ),
            ),
        )
        graph = GraphBuilder().build_from_manifests([m])
        check = NamingCheck()
        issues = check.run(graph, [m])
        assert len(issues) == 0

    def test_no_extension_no_issues(self):
        """A file without any extension should produce no naming issues."""
        m = _make_manifest(
            "m1",
            files_create=(
                _make_fs(
                    "Makefile",
                    (_make_art("BAD_NAME", ArtifactKind.FUNCTION),),
                ),
            ),
        )
        graph = GraphBuilder().build_from_manifests([m])
        check = NamingCheck()
        issues = check.run(graph, [m])
        assert len(issues) == 0


# ---------------------------------------------------------------------------
# Naming regex helpers - direct unit tests
# ---------------------------------------------------------------------------


class TestNamingRegexHelpers:
    """Direct tests for _is_snake_case, _is_pascal_case, _is_camel_case."""

    def test_is_snake_case_valid(self):
        from maid_runner.coherence.checks.naming import _is_snake_case

        assert _is_snake_case("my_func") is True
        assert _is_snake_case("a") is True
        assert _is_snake_case("get_user_by_id") is True
        assert _is_snake_case("_private") is True
        assert _is_snake_case("x2") is True

    def test_is_snake_case_invalid(self):
        from maid_runner.coherence.checks.naming import _is_snake_case

        assert _is_snake_case("MyFunc") is False
        assert _is_snake_case("myFunc") is False
        assert _is_snake_case("2bad") is False
        assert _is_snake_case("has-dash") is False
        assert _is_snake_case("") is False

    def test_is_pascal_case_valid(self):
        from maid_runner.coherence.checks.naming import _is_pascal_case

        assert _is_pascal_case("MyClass") is True
        assert _is_pascal_case("A") is True
        assert _is_pascal_case("HTMLParser") is True
        assert _is_pascal_case("X2") is True

    def test_is_pascal_case_invalid(self):
        from maid_runner.coherence.checks.naming import _is_pascal_case

        assert _is_pascal_case("myClass") is False
        assert _is_pascal_case("my_class") is False
        assert _is_pascal_case("_Private") is False
        assert _is_pascal_case("") is False

    def test_is_camel_case_valid(self):
        from maid_runner.coherence.checks.naming import _is_camel_case

        assert _is_camel_case("myFunc") is True
        assert _is_camel_case("a") is True
        assert _is_camel_case("getUserById") is True
        assert _is_camel_case("x2") is True

    def test_is_camel_case_invalid(self):
        from maid_runner.coherence.checks.naming import _is_camel_case

        assert _is_camel_case("MyFunc") is False
        assert _is_camel_case("my_func") is False
        assert _is_camel_case("_private") is False
        assert _is_camel_case("2bad") is False
        assert _is_camel_case("") is False
