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
