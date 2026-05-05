"""Tests for maid_runner.core.manifest - loading, saving, validation."""

from pathlib import Path

import pytest

from maid_runner.core.manifest import (
    ManifestLoadError,
    ManifestSchemaError,
    load_manifest,
    load_manifest_raw,
    save_manifest,
    slug_from_path,
    validate_manifest_schema,
)
from maid_runner.core.types import (
    ArtifactKind,
    FileMode,
    TaskType,
)

FIXTURES_DIR = Path(__file__).parent.parent / "fixtures" / "manifests"
V2_FIXTURES = FIXTURES_DIR / "v2"


class TestSlugFromPath:
    @pytest.mark.parametrize(
        "filename,expected",
        [
            ("add-jwt-auth.manifest.yaml", "add-jwt-auth"),
            ("fix-cls-parameter.manifest.yaml", "fix-cls-parameter"),
            ("task-001-add-schema.manifest.json", "task-001-add-schema"),
            ("snapshot-auth-service.manifest.yaml", "snapshot-auth-service"),
        ],
    )
    def test_slug_extraction(self, filename, expected):
        assert slug_from_path(filename) == expected

    def test_slug_from_full_path(self):
        assert slug_from_path("manifests/add-auth.manifest.yaml") == "add-auth"

    def test_slug_from_path_object(self):
        assert slug_from_path(Path("manifests/add-auth.manifest.yaml")) == "add-auth"

    def test_slug_yml_extension(self):
        assert slug_from_path("test.manifest.yml") == "test"


class TestValidateManifestSchema:
    def test_valid_manifest(self):
        data = {
            "schema": "2",
            "goal": "Add feature",
            "files": {
                "create": [
                    {
                        "path": "src/app.py",
                        "artifacts": [{"kind": "function", "name": "main"}],
                    }
                ]
            },
            "validate": ["pytest tests/ -v"],
        }
        errors = validate_manifest_schema(data)
        assert errors == []

    def test_missing_goal(self):
        data = {
            "schema": "2",
            "files": {
                "create": [
                    {
                        "path": "src/foo.py",
                        "artifacts": [{"kind": "class", "name": "Foo"}],
                    }
                ]
            },
            "validate": ["pytest tests/ -v"],
        }
        errors = validate_manifest_schema(data)
        assert any("goal" in e.lower() for e in errors)

    def test_missing_validate(self):
        data = {
            "schema": "2",
            "goal": "Test",
            "files": {
                "create": [
                    {
                        "path": "src/foo.py",
                        "artifacts": [{"kind": "class", "name": "Foo"}],
                    }
                ]
            },
        }
        errors = validate_manifest_schema(data)
        assert len(errors) > 0

    def test_no_writable_files(self):
        data = {
            "schema": "2",
            "goal": "Empty manifest",
            "validate": ["pytest tests/ -v"],
        }
        errors = validate_manifest_schema(data)
        assert len(errors) > 0


class TestLoadManifestRaw:
    def test_load_yaml(self):
        data = load_manifest_raw(V2_FIXTURES / "simple-feature.manifest.yaml")
        assert data["goal"] == "Add greeting function"
        assert data["schema"] == "2"

    def test_load_nonexistent(self):
        with pytest.raises(ManifestLoadError):
            load_manifest_raw("/nonexistent/file.manifest.yaml")


class TestLoadManifest:
    def test_load_simple_feature(self):
        manifest = load_manifest(V2_FIXTURES / "simple-feature.manifest.yaml")
        assert manifest.slug == "simple-feature"
        assert manifest.goal == "Add greeting function"
        assert manifest.schema_version == "2"
        assert manifest.task_type == TaskType.FEATURE
        assert len(manifest.files_create) == 1
        assert manifest.files_create[0].path == "src/greet.py"
        assert manifest.files_create[0].mode == FileMode.CREATE

        greet = manifest.files_create[0].artifacts[0]
        assert greet.kind == ArtifactKind.FUNCTION
        assert greet.name == "greet"
        assert len(greet.args) == 1
        assert greet.args[0].name == "name"
        assert greet.args[0].type == "str"
        assert greet.returns == "str"

        assert manifest.files_read == ("tests/test_greet.py",)
        assert manifest.validate_commands == (("python", "-c", "pass"),)
        assert manifest.created == "2025-06-15T10:30:00Z"

    def test_load_multi_file(self):
        manifest = load_manifest(V2_FIXTURES / "multi-file.manifest.yaml")
        assert len(manifest.files_create) == 2
        assert len(manifest.files_edit) == 1
        assert manifest.files_read == ("src/database.py",)

        service = manifest.files_create[0]
        assert service.path == "src/auth/service.py"
        assert len(service.artifacts) == 2
        login = service.artifacts[1]
        assert login.kind == ArtifactKind.METHOD
        assert login.of == "AuthService"

        config = manifest.files_edit[0]
        assert config.mode == FileMode.EDIT
        assert config.artifacts[0].kind == ArtifactKind.ATTRIBUTE
        assert config.artifacts[0].type_annotation == "str"

    def test_load_deletion(self):
        manifest = load_manifest(V2_FIXTURES / "deletion.manifest.yaml")
        assert len(manifest.files_delete) == 1
        assert manifest.files_delete[0].path == "src/legacy_adapter.py"
        assert manifest.files_delete[0].reason == "All consumers migrated to new API"
        assert manifest.supersedes == ("create-legacy-adapter",)

    def test_load_snapshot(self):
        manifest = load_manifest(V2_FIXTURES / "snapshot.manifest.yaml")
        assert manifest.task_type == TaskType.SNAPSHOT
        assert len(manifest.files_snapshot) == 1
        assert manifest.files_snapshot[0].mode == FileMode.SNAPSHOT

    def test_load_with_supersession(self):
        manifest = load_manifest(V2_FIXTURES / "with-supersession.manifest.yaml")
        assert manifest.supersedes == ("simple-feature",)

    def test_load_nonexistent(self):
        with pytest.raises(ManifestLoadError):
            load_manifest("/nonexistent/file.manifest.yaml")

    def test_load_invalid_schema(self, tmp_path):
        bad = tmp_path / "bad.manifest.yaml"
        bad.write_text("schema: '2'\nvalidate:\n  - pytest\n")
        with pytest.raises(ManifestSchemaError) as exc_info:
            load_manifest(bad)
        assert "goal" in str(exc_info.value).lower()

    def test_load_unknown_extension(self, tmp_path):
        bad = tmp_path / "bad.manifest.txt"
        bad.write_text("hello")
        with pytest.raises(ManifestLoadError, match="Unknown extension"):
            load_manifest(bad)

    def test_validate_command_string_form(self):
        """Single string commands are split into tuples."""
        manifest = load_manifest(V2_FIXTURES / "simple-feature.manifest.yaml")
        assert manifest.validate_commands == (("python", "-c", "pass"),)

    def test_validate_command_string_preserves_quoted_args(self, tmp_path):
        path = tmp_path / "quoted.manifest.yaml"
        path.write_text(
            """schema: "2"
goal: "Quoted"
files:
  create:
    - path: src/q.py
      artifacts:
        - kind: function
          name: q
validate:
  - python -c "print('hello world')"
"""
        )
        manifest = load_manifest(path)
        assert manifest.validate_commands == (("python", "-c", "print('hello world')"),)

    def test_async_artifact(self, tmp_path):
        content = """schema: "2"
goal: "Add async function"
type: feature
files:
  create:
    - path: src/fetcher.py
      artifacts:
        - kind: function
          name: fetch_data
          async: true
          args:
            - name: url
              type: str
          returns: dict
validate:
  - pytest tests/ -v
"""
        p = tmp_path / "async.manifest.yaml"
        p.write_text(content)
        manifest = load_manifest(p)
        assert manifest.files_create[0].artifacts[0].is_async is True

    def test_load_with_acceptance(self, tmp_path):
        content = """schema: "2"
goal: "Add auth"
type: feature
files:
  create:
    - path: src/auth.py
      artifacts:
        - kind: class
          name: AuthService
acceptance:
  tests:
    - pytest tests/acceptance/test_auth.py -v
  immutable: true
validate:
  - pytest tests/test_auth.py -v
"""
        p = tmp_path / "with-acceptance.manifest.yaml"
        p.write_text(content)
        manifest = load_manifest(p)
        assert manifest.acceptance is not None
        assert manifest.acceptance.tests == (
            ("pytest", "tests/acceptance/test_auth.py", "-v"),
        )
        assert manifest.acceptance.immutable is True

    def test_load_with_acceptance_immutable_false(self, tmp_path):
        content = """schema: "2"
goal: "Add auth"
files:
  create:
    - path: src/auth.py
      artifacts:
        - kind: class
          name: AuthService
acceptance:
  tests:
    - pytest tests/acceptance/test_auth.py -v
  immutable: false
validate:
  - pytest tests/ -v
"""
        p = tmp_path / "mutable-acceptance.manifest.yaml"
        p.write_text(content)
        manifest = load_manifest(p)
        assert manifest.acceptance is not None
        assert manifest.acceptance.immutable is False

    def test_load_fixture_with_acceptance(self):
        """Load the v2 fixture manifest with acceptance field."""
        manifest = load_manifest(V2_FIXTURES / "with-acceptance.manifest.yaml")
        assert manifest.acceptance is not None
        assert manifest.acceptance.tests == (
            ("pytest", "tests/acceptance/test_auth.py", "-v"),
        )
        assert manifest.acceptance.immutable is True
        assert manifest.goal == "Add user authentication"
        assert manifest.task_type == TaskType.FEATURE

    def test_load_without_acceptance_backward_compat(self):
        """Existing manifests without acceptance keep working."""
        manifest = load_manifest(V2_FIXTURES / "simple-feature.manifest.yaml")
        assert manifest.acceptance is None

    def test_load_with_temptations(self, tmp_path):
        content = """schema: "2"
goal: "Add guarded feature"
description: |
  Add feature with known implementation risks.
temptations:
  - risk: "Do not import private parser helpers from tests."
    instead: "Test through load_manifest and validate_manifest_schema."
  - risk: "Do not satisfy schema tests by loosening additionalProperties."
    instead: "Add the explicit top-level schema property and focused tests."
files:
  create:
    - path: src/guarded.py
      artifacts:
        - kind: function
          name: guarded
validate:
  - pytest tests/test_guarded.py -v
"""
        p = tmp_path / "with-temptations.manifest.yaml"
        p.write_text(content)

        manifest = load_manifest(p)

        assert len(manifest.temptations) == 2
        assert manifest.temptations[0].risk.startswith("Do not import")
        assert manifest.temptations[0].instead == (
            "Test through load_manifest and validate_manifest_schema."
        )
        assert manifest.description.startswith("Add feature")

    def test_load_without_temptations_backward_compat(self):
        manifest = load_manifest(V2_FIXTURES / "simple-feature.manifest.yaml")
        assert manifest.temptations == ()


class TestValidateManifestSchemaAcceptance:
    def test_valid_acceptance(self):
        data = {
            "schema": "2",
            "goal": "Test",
            "files": {
                "create": [
                    {
                        "path": "src/app.py",
                        "artifacts": [{"kind": "function", "name": "main"}],
                    }
                ]
            },
            "acceptance": {
                "tests": ["pytest tests/acceptance/test_auth.py -v"],
            },
            "validate": ["pytest tests/ -v"],
        }
        errors = validate_manifest_schema(data)
        assert errors == []


class TestValidateManifestSchemaTemptations:
    def _base_manifest(self) -> dict:
        return {
            "schema": "2",
            "goal": "Test",
            "files": {
                "create": [
                    {
                        "path": "src/app.py",
                        "artifacts": [{"kind": "function", "name": "main"}],
                    }
                ]
            },
            "validate": ["pytest tests/ -v"],
        }

    def test_valid_temptations(self):
        data = self._base_manifest()
        data["temptations"] = [
            {
                "risk": "Do not import private implementation helpers.",
                "instead": "Exercise behavior through the public module API.",
            },
            {
                "risk": "Do not broaden the schema to accept arbitrary keys.",
                "instead": "Declare the exact property and add schema tests.",
            },
        ]

        errors = validate_manifest_schema(data)

        assert errors == []

    def test_temptations_require_risk_and_instead(self):
        data = self._base_manifest()
        data["temptations"] = [
            {"risk": "Do not stop at naming the risk without a procedure."}
        ]

        errors = validate_manifest_schema(data)

        assert any("instead" in e for e in errors)

    def test_temptations_are_capped_at_five(self):
        data = self._base_manifest()
        data["temptations"] = [
            {"risk": f"Do not take shortcut {i}.", "instead": f"Use procedure {i}."}
            for i in range(6)
        ]

        errors = validate_manifest_schema(data)

        assert any("too long" in e.lower() for e in errors)

    def test_acceptance_missing_tests(self):
        data = {
            "schema": "2",
            "goal": "Test",
            "files": {
                "create": [
                    {
                        "path": "src/app.py",
                        "artifacts": [{"kind": "function", "name": "main"}],
                    }
                ]
            },
            "acceptance": {
                "immutable": True,
            },
            "validate": ["pytest tests/ -v"],
        }
        errors = validate_manifest_schema(data)
        assert len(errors) > 0

    def test_acceptance_with_immutable_false(self):
        data = {
            "schema": "2",
            "goal": "Test",
            "files": {
                "create": [
                    {
                        "path": "src/app.py",
                        "artifacts": [{"kind": "function", "name": "main"}],
                    }
                ]
            },
            "acceptance": {
                "tests": ["pytest tests/acceptance/ -v"],
                "immutable": False,
            },
            "validate": ["pytest tests/ -v"],
        }
        errors = validate_manifest_schema(data)
        assert errors == []


class TestSaveManifest:
    def test_round_trip(self, tmp_path):
        original = load_manifest(V2_FIXTURES / "simple-feature.manifest.yaml")
        output = tmp_path / "output.manifest.yaml"
        save_manifest(original, output)
        reloaded = load_manifest(output)
        assert reloaded.goal == original.goal
        assert reloaded.files_create[0].path == original.files_create[0].path
        assert reloaded.files_create[0].artifacts[0].name == "greet"
        assert reloaded.validate_commands == original.validate_commands
        assert "[python, -c, pass]" not in output.read_text()

    def test_round_trip_with_acceptance(self, tmp_path):
        content = """schema: "2"
goal: "Add auth"
files:
  create:
    - path: src/auth.py
      artifacts:
        - kind: class
          name: AuthService
acceptance:
  tests:
    - pytest tests/acceptance/test_auth.py -v
validate:
  - pytest tests/test_auth.py -v
"""
        source = tmp_path / "source.manifest.yaml"
        source.write_text(content)
        original = load_manifest(source)

        output = tmp_path / "output.manifest.yaml"
        save_manifest(original, output)
        reloaded = load_manifest(output)

        assert reloaded.acceptance is not None
        assert reloaded.acceptance.tests == original.acceptance.tests
        assert reloaded.acceptance.immutable is True

    def test_round_trip_with_temptations_preserves_order_near_top(self, tmp_path):
        content = """schema: "2"
goal: "Add guarded feature"
type: feature
description: |
  Add feature with known implementation risks.
temptations:
  - risk: "Do not import private parser helpers from tests."
    instead: "Test through load_manifest and validate_manifest_schema."
files:
  create:
    - path: src/guarded.py
      artifacts:
        - kind: function
          name: guarded
validate:
  - pytest tests/test_guarded.py -v
"""
        source = tmp_path / "source.manifest.yaml"
        source.write_text(content)
        original = load_manifest(source)

        output = tmp_path / "output.manifest.yaml"
        save_manifest(original, output)
        reloaded = load_manifest(output)
        saved = output.read_text()

        assert reloaded.temptations == original.temptations
        assert saved.index("description:") < saved.index("temptations:")
        assert saved.index("temptations:") < saved.index("files:")


class TestImportsField:
    """Tests for the optional imports field on FileSpec."""

    def test_imports_parsed_from_yaml(self, tmp_path):
        """FileSpec.imports is populated from manifest YAML."""
        content = """\
schema: "2"
goal: "Add page"
files:
  create:
    - path: src/pages/budget.py
      artifacts:
        - kind: function
          name: BudgetPage
      imports:
        - src.api.budgets
        - src.stores.budget_store
validate:
  - pytest tests/ -v
"""
        path = tmp_path / "page.manifest.yaml"
        path.write_text(content)
        manifest = load_manifest(path)
        fs = manifest.files_create[0]
        assert fs.imports == ("src.api.budgets", "src.stores.budget_store")

    def test_missing_imports_defaults_empty(self, tmp_path):
        """FileSpec.imports defaults to empty tuple when not in YAML."""
        content = """\
schema: "2"
goal: "Add greet"
files:
  create:
    - path: src/greet.py
      artifacts:
        - kind: function
          name: greet
validate:
  - pytest tests/ -v
"""
        path = tmp_path / "greet.manifest.yaml"
        path.write_text(content)
        manifest = load_manifest(path)
        fs = manifest.files_create[0]
        assert fs.imports == ()

    def test_imports_roundtrip(self, tmp_path):
        """Imports survive save_manifest -> load_manifest round-trip."""
        content = """\
schema: "2"
goal: "Add page"
files:
  create:
    - path: src/pages/budget.py
      artifacts:
        - kind: function
          name: BudgetPage
      imports:
        - src.api.budgets
validate:
  - pytest tests/ -v
"""
        source = tmp_path / "source.manifest.yaml"
        source.write_text(content)
        original = load_manifest(source)

        output = tmp_path / "output.manifest.yaml"
        save_manifest(original, output)
        reloaded = load_manifest(output)

        assert reloaded.files_create[0].imports == ("src.api.budgets",)
