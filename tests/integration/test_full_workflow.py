"""Integration tests: full MAID Runner v2 workflow.

Tests exercise the complete pipeline with real files on disk:
- Load v2 YAML manifest -> validate -> check result
- Multi-file manifest -> chain resolution -> merged validation
- Snapshot generation -> save -> reload -> validate
- Behavioral validation with test files
- Delete file validation
- Supersession chain workflows
"""

from __future__ import annotations

import textwrap
from pathlib import Path

import pytest
import yaml

from maid_runner.core.chain import ManifestChain
from maid_runner.core.manifest import load_manifest
from maid_runner.core.result import ErrorCode
from maid_runner.core.snapshot import generate_snapshot, save_snapshot
from maid_runner.core.types import TaskType, ValidationMode
from maid_runner.core.validate import ValidationEngine, validate


@pytest.fixture
def project(tmp_path: Path) -> Path:
    """Create a minimal project structure with manifests and source files."""
    manifests = tmp_path / "manifests"
    manifests.mkdir()
    src = tmp_path / "src"
    src.mkdir()
    tests = tmp_path / "tests"
    tests.mkdir()
    return tmp_path


def _write_yaml(path: Path, data: dict) -> None:
    path.write_text(yaml.dump(data, default_flow_style=False, sort_keys=False))


def _add_test_file(project_dir, test_rel_path, source_module, artifact_names):
    """Write a minimal test file that references the given artifacts."""
    public_names = [n for n in artifact_names if not n.startswith("_")]
    if not public_names:
        public_names = artifact_names
    imports = ", ".join(public_names)
    tests = "\n".join(
        f"def test_{n}():\n    assert {n} is not None\n" for n in public_names
    )
    content = f"from {source_module} import {imports}\n\n{tests}\n"
    path = project_dir / test_rel_path
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content)
    return test_rel_path


# ---------------------------------------------------------------------------
# 1. Load v2 YAML manifest -> validate -> pass
# ---------------------------------------------------------------------------


class TestV2ManifestValidatePass:
    def test_simple_function_passes(self, project: Path):
        manifest_path = project / "manifests" / "add-greet.manifest.yaml"
        _write_yaml(
            manifest_path,
            {
                "schema": "2",
                "goal": "Add greeting function",
                "type": "feature",
                "files": {
                    "create": [
                        {
                            "path": "src/greet.py",
                            "artifacts": [
                                {
                                    "kind": "function",
                                    "name": "greet",
                                    "args": [{"name": "name", "type": "str"}],
                                    "returns": "str",
                                }
                            ],
                        }
                    ]
                },
                "validate": ["pytest tests/test_greet.py -v"],
            },
        )
        (project / "src" / "greet.py").write_text(
            textwrap.dedent(
                """\
                def greet(name: str) -> str:
                    return f"Hello, {name}!"
            """
            )
        )

        result = validate(
            str(manifest_path),
            mode=ValidationMode.IMPLEMENTATION,
            use_chain=False,
            project_root=str(project),
        )

        assert result.success is True
        assert result.errors == []
        assert result.manifest_slug == "add-greet"

    def test_class_with_method_passes(self, project: Path):
        manifest_path = project / "manifests" / "add-service.manifest.yaml"
        _write_yaml(
            manifest_path,
            {
                "schema": "2",
                "goal": "Add auth service",
                "type": "feature",
                "files": {
                    "create": [
                        {
                            "path": "src/service.py",
                            "artifacts": [
                                {"kind": "class", "name": "AuthService"},
                                {
                                    "kind": "method",
                                    "name": "login",
                                    "of": "AuthService",
                                    "args": [
                                        {"name": "user", "type": "str"},
                                        {"name": "password", "type": "str"},
                                    ],
                                    "returns": "bool",
                                },
                            ],
                        }
                    ],
                    "read": ["tests/test_service.py"],
                },
                "validate": ["pytest tests/test_service.py -v"],
            },
        )
        (project / "src" / "service.py").write_text(
            textwrap.dedent(
                """\
                class AuthService:
                    def login(self, user: str, password: str) -> bool:
                        return user == "admin"
            """
            )
        )
        _add_test_file(project, "tests/test_service.py", "src.service", ["AuthService"])

        result = validate(
            str(manifest_path),
            use_chain=False,
            project_root=str(project),
        )

        assert result.success is True


# ---------------------------------------------------------------------------
# 2. Load v2 YAML manifest -> validate -> fail
# ---------------------------------------------------------------------------


class TestV2ManifestValidateFail:
    def test_missing_artifact_fails(self, project: Path):
        manifest_path = project / "manifests" / "add-greet.manifest.yaml"
        _write_yaml(
            manifest_path,
            {
                "schema": "2",
                "goal": "Add greeting",
                "type": "feature",
                "files": {
                    "create": [
                        {
                            "path": "src/greet.py",
                            "artifacts": [
                                {"kind": "function", "name": "greet"},
                            ],
                        }
                    ]
                },
                "validate": ["pytest tests/ -v"],
            },
        )
        (project / "src" / "greet.py").write_text("# empty\n")

        result = validate(
            str(manifest_path),
            use_chain=False,
            project_root=str(project),
        )

        assert result.success is False
        assert any(e.code == ErrorCode.ARTIFACT_NOT_DEFINED for e in result.errors)

    def test_unexpected_public_artifact_strict_mode(self, project: Path):
        manifest_path = project / "manifests" / "add-greet.manifest.yaml"
        _write_yaml(
            manifest_path,
            {
                "schema": "2",
                "goal": "Add greeting",
                "type": "feature",
                "files": {
                    "create": [
                        {
                            "path": "src/greet.py",
                            "artifacts": [
                                {"kind": "function", "name": "greet"},
                            ],
                        }
                    ]
                },
                "validate": ["pytest tests/ -v"],
            },
        )
        (project / "src" / "greet.py").write_text(
            textwrap.dedent(
                """\
                def greet(name):
                    return f"Hello, {name}!"

                def farewell(name):
                    return f"Goodbye, {name}!"
            """
            )
        )

        result = validate(
            str(manifest_path),
            use_chain=False,
            project_root=str(project),
        )

        assert result.success is False
        assert any(e.code == ErrorCode.UNEXPECTED_ARTIFACT for e in result.errors)

    def test_type_mismatch_fails(self, project: Path):
        manifest_path = project / "manifests" / "add-calc.manifest.yaml"
        _write_yaml(
            manifest_path,
            {
                "schema": "2",
                "goal": "Add calculator",
                "type": "feature",
                "files": {
                    "create": [
                        {
                            "path": "src/calc.py",
                            "artifacts": [
                                {
                                    "kind": "function",
                                    "name": "add",
                                    "args": [
                                        {"name": "a", "type": "int"},
                                        {"name": "b", "type": "int"},
                                    ],
                                    "returns": "int",
                                }
                            ],
                        }
                    ]
                },
                "validate": ["pytest tests/ -v"],
            },
        )
        (project / "src" / "calc.py").write_text(
            textwrap.dedent(
                """\
                def add(a: str, b: str) -> str:
                    return a + b
            """
            )
        )

        result = validate(
            str(manifest_path),
            use_chain=False,
            project_root=str(project),
        )

        assert result.success is False
        assert any(e.code == ErrorCode.TYPE_MISMATCH for e in result.errors)


# ---------------------------------------------------------------------------
# 3. Permissive (edit) mode allows extra public artifacts
# ---------------------------------------------------------------------------


class TestPermissiveMode:
    def test_edit_mode_allows_extra_public(self, project: Path):
        manifest_path = project / "manifests" / "add-farewell.manifest.yaml"
        _write_yaml(
            manifest_path,
            {
                "schema": "2",
                "goal": "Add farewell",
                "type": "feature",
                "files": {
                    "edit": [
                        {
                            "path": "src/greet.py",
                            "artifacts": [
                                {"kind": "function", "name": "farewell"},
                            ],
                        }
                    ],
                    "read": ["tests/test_farewell.py"],
                },
                "validate": ["pytest tests/test_farewell.py -v"],
            },
        )
        (project / "src" / "greet.py").write_text(
            textwrap.dedent(
                """\
                def greet(name):
                    return f"Hello, {name}!"

                def farewell(name):
                    return f"Goodbye, {name}!"
            """
            )
        )
        _add_test_file(project, "tests/test_farewell.py", "src.greet", ["farewell"])

        result = validate(
            str(manifest_path),
            use_chain=False,
            project_root=str(project),
        )

        assert result.success is True


# ---------------------------------------------------------------------------
# 4. Multi-file manifest with chain resolution
# ---------------------------------------------------------------------------


class TestMultiFileChainMerge:
    def test_chain_merges_artifacts_from_multiple_manifests(self, project: Path):
        # Manifest 1: creates service with 'start' method
        _write_yaml(
            project / "manifests" / "add-base.manifest.yaml",
            {
                "schema": "2",
                "goal": "Add base service",
                "type": "feature",
                "files": {
                    "create": [
                        {
                            "path": "src/service.py",
                            "artifacts": [
                                {"kind": "class", "name": "Service"},
                                {
                                    "kind": "method",
                                    "name": "start",
                                    "of": "Service",
                                },
                            ],
                        }
                    ],
                    "read": ["tests/test_service_base.py"],
                },
                "validate": ["pytest tests/test_service_base.py -v"],
                "created": "2025-06-01T00:00:00Z",
            },
        )
        # Manifest 2: edits service to add 'stop' method
        _write_yaml(
            project / "manifests" / "add-stop.manifest.yaml",
            {
                "schema": "2",
                "goal": "Add stop method",
                "type": "feature",
                "files": {
                    "edit": [
                        {
                            "path": "src/service.py",
                            "artifacts": [
                                {
                                    "kind": "method",
                                    "name": "stop",
                                    "of": "Service",
                                },
                            ],
                        }
                    ],
                    "read": ["tests/test_service_stop.py"],
                },
                "validate": ["pytest tests/test_service_stop.py -v"],
                "created": "2025-06-15T00:00:00Z",
            },
        )

        # Source has all three: Service class, start, stop
        (project / "src" / "service.py").write_text(
            textwrap.dedent(
                """\
                class Service:
                    def start(self):
                        pass

                    def stop(self):
                        pass
            """
            )
        )
        _add_test_file(
            project, "tests/test_service_base.py", "src.service", ["Service"]
        )
        _add_test_file(
            project, "tests/test_service_stop.py", "src.service", ["Service"]
        )

        # Validate with chain
        engine = ValidationEngine(project_root=project)
        batch = engine.validate_all("manifests/")

        assert batch.success is True
        assert batch.passed == 2

    def test_chain_merged_artifacts_for_file(self, project: Path):
        _write_yaml(
            project / "manifests" / "add-base.manifest.yaml",
            {
                "schema": "2",
                "goal": "Add base",
                "type": "feature",
                "files": {
                    "create": [
                        {
                            "path": "src/svc.py",
                            "artifacts": [
                                {"kind": "class", "name": "Svc"},
                                {"kind": "method", "name": "run", "of": "Svc"},
                            ],
                        }
                    ]
                },
                "validate": ["pytest tests/ -v"],
                "created": "2025-01-01T00:00:00Z",
            },
        )
        _write_yaml(
            project / "manifests" / "add-stop.manifest.yaml",
            {
                "schema": "2",
                "goal": "Add stop",
                "type": "feature",
                "files": {
                    "edit": [
                        {
                            "path": "src/svc.py",
                            "artifacts": [
                                {"kind": "method", "name": "halt", "of": "Svc"},
                            ],
                        }
                    ]
                },
                "validate": ["pytest tests/ -v"],
                "created": "2025-02-01T00:00:00Z",
            },
        )

        chain = ManifestChain(project / "manifests", project)
        merged = chain.merged_artifacts_for("src/svc.py")
        names = {a.qualified_name for a in merged}

        assert names == {"Svc", "Svc.run", "Svc.halt"}


# ---------------------------------------------------------------------------
# 5. Supersession chain workflow
# ---------------------------------------------------------------------------


class TestSupersessionWorkflow:
    def test_superseded_manifest_excluded_from_active(self, project: Path):
        _write_yaml(
            project / "manifests" / "old-feature.manifest.yaml",
            {
                "schema": "2",
                "goal": "Old feature",
                "type": "feature",
                "files": {
                    "create": [
                        {
                            "path": "src/old.py",
                            "artifacts": [
                                {"kind": "function", "name": "old_func"},
                            ],
                        }
                    ]
                },
                "validate": ["pytest tests/ -v"],
            },
        )
        _write_yaml(
            project / "manifests" / "new-feature.manifest.yaml",
            {
                "schema": "2",
                "goal": "New feature",
                "type": "refactor",
                "supersedes": ["old-feature"],
                "files": {
                    "edit": [
                        {
                            "path": "src/old.py",
                            "artifacts": [
                                {"kind": "function", "name": "new_func"},
                            ],
                        }
                    ]
                },
                "validate": ["pytest tests/ -v"],
            },
        )

        chain = ManifestChain(project / "manifests", project)

        active_slugs = {m.slug for m in chain.active_manifests()}
        assert "new-feature" in active_slugs
        assert "old-feature" not in active_slugs

        assert chain.is_superseded("old-feature") is True
        assert chain.superseded_by("old-feature") == "new-feature"

    def test_validate_all_skips_superseded(self, project: Path):
        _write_yaml(
            project / "manifests" / "old.manifest.yaml",
            {
                "schema": "2",
                "goal": "Old",
                "type": "feature",
                "files": {
                    "create": [
                        {
                            "path": "src/x.py",
                            "artifacts": [{"kind": "function", "name": "x"}],
                        }
                    ],
                    "read": ["tests/test_x.py"],
                },
                "validate": ["pytest tests/test_x.py -v"],
            },
        )
        _write_yaml(
            project / "manifests" / "new.manifest.yaml",
            {
                "schema": "2",
                "goal": "New replaces old",
                "type": "refactor",
                "supersedes": ["old"],
                "files": {
                    "edit": [
                        {
                            "path": "src/x.py",
                            "artifacts": [{"kind": "function", "name": "x_new"}],
                        }
                    ],
                    "read": ["tests/test_x_new.py"],
                },
                "validate": ["pytest tests/test_x_new.py -v"],
            },
        )
        (project / "src" / "x.py").write_text(
            textwrap.dedent(
                """\
                def x_new():
                    pass
            """
            )
        )
        _add_test_file(project, "tests/test_x.py", "src.x", ["x"])
        _add_test_file(project, "tests/test_x_new.py", "src.x", ["x_new"])

        engine = ValidationEngine(project_root=project)
        batch = engine.validate_all("manifests/")

        assert batch.skipped == 1
        assert batch.passed == 1
        assert batch.total_manifests == 2


# ---------------------------------------------------------------------------
# 6. Delete file validation
# ---------------------------------------------------------------------------


class TestDeleteFileValidation:
    def test_file_still_exists_fails(self, project: Path):
        manifest_path = project / "manifests" / "remove-old.manifest.yaml"
        _write_yaml(
            manifest_path,
            {
                "schema": "2",
                "goal": "Remove old module",
                "type": "refactor",
                "files": {
                    "delete": [
                        {"path": "src/old_module.py", "reason": "Deprecated"},
                    ]
                },
                "validate": ["pytest tests/ -v"],
            },
        )
        (project / "src" / "old_module.py").write_text("# old\n")

        result = validate(
            str(manifest_path),
            use_chain=False,
            project_root=str(project),
        )

        assert result.success is False
        assert any(e.code == ErrorCode.FILE_SHOULD_BE_ABSENT for e in result.errors)

    def test_file_deleted_passes(self, project: Path):
        manifest_path = project / "manifests" / "remove-old.manifest.yaml"
        _write_yaml(
            manifest_path,
            {
                "schema": "2",
                "goal": "Remove old module",
                "type": "refactor",
                "files": {
                    "delete": [
                        {"path": "src/old_module.py", "reason": "Deprecated"},
                    ]
                },
                "validate": ["pytest tests/ -v"],
            },
        )
        # File does NOT exist -> should pass

        result = validate(
            str(manifest_path),
            use_chain=False,
            project_root=str(project),
        )

        assert result.success is True


# ---------------------------------------------------------------------------
# 7. Snapshot generation -> save -> reload -> validate
# ---------------------------------------------------------------------------


class TestSnapshotRoundtrip:
    def test_generate_save_reload_validate(self, project: Path):
        source_file = project / "src" / "utils.py"
        source_file.write_text(
            textwrap.dedent(
                """\
                def helper(x: int) -> str:
                    return str(x)

                def compute(a: float, b: float) -> float:
                    return a + b
            """
            )
        )

        # Generate snapshot
        manifest = generate_snapshot(
            str(source_file),
            project_root=str(project),
        )

        assert manifest.task_type == TaskType.SNAPSHOT
        artifact_names = {
            a.name for fs in manifest.all_file_specs for a in fs.artifacts
        }
        assert "helper" in artifact_names
        assert "compute" in artifact_names

        # Save snapshot
        out = save_snapshot(
            manifest,
            output_dir=str(project / "manifests"),
        )
        assert out.exists()

        # Reload
        reloaded = load_manifest(out)
        assert reloaded.goal == manifest.goal
        reloaded_names = {
            a.name for fs in reloaded.all_file_specs for a in fs.artifacts
        }
        assert reloaded_names == artifact_names

        # Validate against source (snapshot mode = strict)
        result = validate(
            str(out),
            use_chain=False,
            project_root=str(project),
        )

        assert result.success is True


# ---------------------------------------------------------------------------
# 8. Behavioral validation
# ---------------------------------------------------------------------------


class TestBehavioralValidation:
    def test_artifact_used_in_test_passes(self, project: Path):
        manifest_path = project / "manifests" / "add-greet.manifest.yaml"
        _write_yaml(
            manifest_path,
            {
                "schema": "2",
                "goal": "Add greeting",
                "type": "feature",
                "files": {
                    "create": [
                        {
                            "path": "src/greet.py",
                            "artifacts": [
                                {"kind": "function", "name": "greet"},
                            ],
                        }
                    ],
                    "read": ["tests/test_greet.py"],
                },
                "validate": ["pytest tests/test_greet.py -v"],
            },
        )
        (project / "tests" / "test_greet.py").write_text(
            textwrap.dedent(
                """\
                from src.greet import greet

                def test_greet():
                    assert greet("World") == "Hello, World!"
            """
            )
        )

        result = validate(
            str(manifest_path),
            mode=ValidationMode.BEHAVIORAL,
            use_chain=False,
            project_root=str(project),
        )

        assert result.success is True

    def test_artifact_not_used_in_test_fails(self, project: Path):
        manifest_path = project / "manifests" / "add-greet.manifest.yaml"
        _write_yaml(
            manifest_path,
            {
                "schema": "2",
                "goal": "Add greeting",
                "type": "feature",
                "files": {
                    "create": [
                        {
                            "path": "src/greet.py",
                            "artifacts": [
                                {"kind": "function", "name": "greet"},
                            ],
                        }
                    ],
                    "read": ["tests/test_greet.py"],
                },
                "validate": ["pytest tests/test_greet.py -v"],
            },
        )
        (project / "tests" / "test_greet.py").write_text(
            textwrap.dedent(
                """\
                def test_something():
                    assert True
            """
            )
        )

        result = validate(
            str(manifest_path),
            mode=ValidationMode.BEHAVIORAL,
            use_chain=False,
            project_root=str(project),
        )

        assert result.success is False
        assert any(
            e.code == ErrorCode.ARTIFACT_NOT_USED_IN_TESTS for e in result.errors
        )


# ---------------------------------------------------------------------------
# 9. Result serialization
# ---------------------------------------------------------------------------


class TestResultSerialization:
    def test_result_to_dict_and_json(self, project: Path):
        manifest_path = project / "manifests" / "add-greet.manifest.yaml"
        _write_yaml(
            manifest_path,
            {
                "schema": "2",
                "goal": "Add greeting",
                "type": "feature",
                "files": {
                    "create": [
                        {
                            "path": "src/greet.py",
                            "artifacts": [
                                {"kind": "function", "name": "greet"},
                            ],
                        }
                    ],
                    "read": ["tests/test_greet.py"],
                },
                "validate": ["pytest tests/test_greet.py -v"],
            },
        )
        (project / "src" / "greet.py").write_text("def greet(): pass\n")
        _add_test_file(project, "tests/test_greet.py", "src.greet", ["greet"])

        result = validate(
            str(manifest_path),
            use_chain=False,
            project_root=str(project),
        )

        d = result.to_dict()
        assert d["success"] is True
        assert d["manifest"] == "add-greet"
        assert d["mode"] == "implementation"
        assert isinstance(d["errors"], list)
        assert "duration_ms" in d

        json_str = result.to_json()
        assert '"success": true' in json_str


# ---------------------------------------------------------------------------
# 10. Private artifacts allowed in strict mode
# ---------------------------------------------------------------------------


class TestPrivateArtifacts:
    def test_private_functions_not_flagged_in_strict(self, project: Path):
        manifest_path = project / "manifests" / "add-greet.manifest.yaml"
        _write_yaml(
            manifest_path,
            {
                "schema": "2",
                "goal": "Add greeting",
                "type": "feature",
                "files": {
                    "create": [
                        {
                            "path": "src/greet.py",
                            "artifacts": [
                                {"kind": "function", "name": "greet"},
                            ],
                        }
                    ],
                    "read": ["tests/test_greet.py"],
                },
                "validate": ["pytest tests/test_greet.py -v"],
            },
        )
        (project / "src" / "greet.py").write_text(
            textwrap.dedent(
                """\
                def greet(name):
                    return _format(name)

                def _format(name):
                    return f"Hello, {name}!"
            """
            )
        )
        _add_test_file(project, "tests/test_greet.py", "src.greet", ["greet"])

        result = validate(
            str(manifest_path),
            use_chain=False,
            project_root=str(project),
        )

        assert result.success is True


# ---------------------------------------------------------------------------
# Behavioral depth checks (stub detection, assertion checking, imports)
# ---------------------------------------------------------------------------


class TestDepthChecks:
    """Integration tests for check_stubs, check_assertions, and imports."""

    def test_stub_detected_in_full_pipeline(self, project: Path):
        """Stub function flagged as warning when check_stubs=True."""
        manifest_path = project / "manifests" / "add-greet.manifest.yaml"
        _write_yaml(
            manifest_path,
            {
                "schema": "2",
                "goal": "Add greeter",
                "files": {
                    "create": [
                        {
                            "path": "src/greet.py",
                            "artifacts": [{"kind": "function", "name": "greet"}],
                        }
                    ],
                    "read": ["tests/test_greet.py"],
                },
                "validate": ["pytest tests/test_greet.py -v"],
            },
        )
        (project / "src" / "greet.py").write_text("def greet():\n    pass\n")
        _add_test_file(project, "tests/test_greet.py", "src.greet", ["greet"])

        result = validate(
            str(manifest_path),
            use_chain=False,
            project_root=str(project),
            check_stubs=True,
        )
        assert result.success is True  # stubs are warnings
        assert any(w.code == ErrorCode.STUB_FUNCTION_DETECTED for w in result.warnings)

    def test_missing_assertion_in_full_pipeline(self, project: Path):
        """Test without assertions flagged when check_assertions=True."""
        manifest_path = project / "manifests" / "add-greet.manifest.yaml"
        _write_yaml(
            manifest_path,
            {
                "schema": "2",
                "goal": "Add greeter",
                "files": {
                    "create": [
                        {
                            "path": "src/greet.py",
                            "artifacts": [{"kind": "function", "name": "greet"}],
                        }
                    ],
                    "read": ["tests/test_greet.py"],
                },
                "validate": ["pytest tests/test_greet.py -v"],
            },
        )
        (project / "src" / "greet.py").write_text(
            'def greet(name):\n    return f"Hello, {name}!"\n'
        )
        (project / "tests" / "test_greet.py").write_text(
            "from src.greet import greet\n\ndef test_greet():\n    greet('World')\n"
        )

        result = validate(
            str(manifest_path),
            mode=ValidationMode.BEHAVIORAL,
            use_chain=False,
            project_root=str(project),
            check_assertions=True,
        )
        assert any(w.code == ErrorCode.MISSING_ASSERTIONS for w in result.warnings)

    def test_missing_import_in_full_pipeline(self, project: Path):
        """Required import missing from source -> E320 error."""
        manifest_path = project / "manifests" / "add-page.manifest.yaml"
        _write_yaml(
            manifest_path,
            {
                "schema": "2",
                "goal": "Add page",
                "files": {
                    "create": [
                        {
                            "path": "src/pages/budget.py",
                            "artifacts": [{"kind": "function", "name": "BudgetPage"}],
                            "imports": ["src.api.budgets"],
                        }
                    ]
                },
                "validate": ["pytest tests/ -v"],
            },
        )
        pages_dir = project / "src" / "pages"
        pages_dir.mkdir(parents=True)
        (pages_dir / "budget.py").write_text(
            "def BudgetPage():\n    return {'title': 'Budget'}\n"
        )

        result = validate(
            str(manifest_path),
            use_chain=False,
            project_root=str(project),
        )
        assert result.success is False
        assert any(e.code == ErrorCode.MISSING_REQUIRED_IMPORT for e in result.errors)

    def test_all_depth_checks_pass_clean_code(self, project: Path):
        """Well-implemented code passes all depth checks."""
        manifest_path = project / "manifests" / "add-greet.manifest.yaml"
        _write_yaml(
            manifest_path,
            {
                "schema": "2",
                "goal": "Add greeter",
                "files": {
                    "create": [
                        {
                            "path": "src/greet.py",
                            "artifacts": [{"kind": "function", "name": "greet"}],
                            "imports": ["os"],
                        }
                    ],
                    "read": ["tests/test_greet.py"],
                },
                "validate": ["pytest tests/test_greet.py -v"],
            },
        )
        (project / "src" / "greet.py").write_text(
            'import os\n\ndef greet(name):\n    prefix = os.getenv("GREETING", "Hello")\n    return f"{prefix}, {name}!"\n'
        )
        (project / "tests" / "test_greet.py").write_text(
            'from src.greet import greet\n\ndef test_greet():\n    assert greet("World") == "Hello, World!"\n'
        )

        result_impl = validate(
            str(manifest_path),
            use_chain=False,
            project_root=str(project),
            check_stubs=True,
        )
        assert result_impl.success is True
        assert not any(
            w.code == ErrorCode.STUB_FUNCTION_DETECTED for w in result_impl.warnings
        )

        result_beh = validate(
            str(manifest_path),
            mode=ValidationMode.BEHAVIORAL,
            use_chain=False,
            project_root=str(project),
            check_assertions=True,
        )
        assert not any(
            w.code == ErrorCode.MISSING_ASSERTIONS for w in result_beh.warnings
        )
