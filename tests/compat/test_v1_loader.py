"""Tests for maid_runner.compat.v1_loader - V1 manifest conversion."""

import json
from pathlib import Path

from maid_runner.compat.v1_loader import (
    convert_v1_file,
    convert_v1_to_v2,
    is_v1_manifest,
)

V1_FIXTURES = Path(__file__).parent.parent / "fixtures" / "manifests" / "v1"


class TestV1Detection:
    def test_v1_with_expected_artifacts(self):
        data = {
            "goal": "Test",
            "expectedArtifacts": {"file": "a.py", "contains": []},
            "readonlyFiles": [],
            "validationCommand": ["pytest"],
        }
        assert is_v1_manifest(data) is True

    def test_v1_with_creatable_files(self):
        data = {"goal": "Test", "creatableFiles": ["a.py"]}
        assert is_v1_manifest(data) is True

    def test_v1_with_editable_files(self):
        data = {"goal": "Test", "editableFiles": ["a.py"]}
        assert is_v1_manifest(data) is True

    def test_v1_with_version_field(self):
        data = {"goal": "Test", "version": "1"}
        assert is_v1_manifest(data) is True

    def test_v1_with_validation_command_singular(self):
        data = {"goal": "Test", "validationCommand": ["pytest"]}
        assert is_v1_manifest(data) is True

    def test_v2_not_detected_as_v1(self):
        data = {
            "schema": "2",
            "goal": "Test",
            "files": {"create": [{"path": "a.py", "artifacts": []}]},
            "validate": ["pytest"],
        }
        assert is_v1_manifest(data) is False


class TestV1Conversion:
    def test_simple_create(self):
        """Golden test 2.1: Convert simple V1 create manifest."""
        v1 = {
            "goal": "Add schema validation",
            "taskType": "create",
            "creatableFiles": ["maid_runner/validators/manifest_validator.py"],
            "readonlyFiles": ["tests/test_validate_schema.py"],
            "expectedArtifacts": {
                "file": "maid_runner/validators/manifest_validator.py",
                "contains": [
                    {
                        "type": "function",
                        "name": "validate_schema",
                        "parameters": [
                            {"name": "manifest_data"},
                            {"name": "schema_path"},
                        ],
                    }
                ],
            },
            "validationCommand": ["pytest", "tests/test_validate_schema.py"],
        }
        v2 = convert_v1_to_v2(v1)

        assert v2["schema"] == "2"
        assert v2["goal"] == "Add schema validation"
        assert v2["type"] == "feature"

        create = v2["files"]["create"]
        assert len(create) == 1
        assert create[0]["path"] == "maid_runner/validators/manifest_validator.py"

        artifact = create[0]["artifacts"][0]
        assert artifact["kind"] == "function"
        assert artifact["name"] == "validate_schema"
        assert len(artifact["args"]) == 2
        assert artifact["args"][0]["name"] == "manifest_data"

        assert v2["files"]["read"] == ["tests/test_validate_schema.py"]
        assert v2["validate"] == [["pytest", "tests/test_validate_schema.py"]]

    def test_method_conversion(self):
        """Golden test 2.2: V1 type:function + class:X -> v2 kind:method + of:X."""
        v1 = {
            "goal": "Test",
            "taskType": "edit",
            "editableFiles": ["service.py"],
            "readonlyFiles": [],
            "expectedArtifacts": {
                "file": "service.py",
                "contains": [
                    {
                        "type": "function",
                        "name": "login",
                        "class": "AuthService",
                        "args": [{"name": "user", "type": "str"}],
                        "returns": "bool",
                    }
                ],
            },
            "validationCommand": ["pytest"],
        }
        v2 = convert_v1_to_v2(v1)
        artifact = v2["files"]["edit"][0]["artifacts"][0]
        assert artifact["kind"] == "method"
        assert artifact["of"] == "AuthService"
        assert artifact["args"] == [{"name": "user", "type": "str"}]
        assert artifact["returns"] == "bool"

    def test_returns_object_to_string(self):
        """Golden test 2.3: V1 returns: {type: X} -> v2 returns: X."""
        v1 = {
            "goal": "Test",
            "editableFiles": ["a.py"],
            "readonlyFiles": [],
            "expectedArtifacts": {
                "file": "a.py",
                "contains": [
                    {
                        "type": "function",
                        "name": "f",
                        "returns": {"type": "Optional[dict]"},
                    }
                ],
            },
            "validationCommand": ["pytest"],
        }
        v2 = convert_v1_to_v2(v1)
        artifact = v2["files"]["edit"][0]["artifacts"][0]
        assert artifact["returns"] == "Optional[dict]"

    def test_supersedes_path_to_slug(self):
        """Golden test 2.4: Convert full paths to slugs."""
        v1 = {
            "goal": "Test",
            "editableFiles": ["a.py"],
            "readonlyFiles": [],
            "expectedArtifacts": {
                "file": "a.py",
                "contains": [{"type": "class", "name": "A"}],
            },
            "supersedes": ["manifests/task-001-add-schema.manifest.json"],
            "validationCommand": ["pytest"],
        }
        v2 = convert_v1_to_v2(v1)
        assert v2["supersedes"] == ["task-001-add-schema"]

    def test_parameter_artifacts_skipped(self):
        """V1 type:parameter artifacts are omitted."""
        v1 = {
            "goal": "Test",
            "creatableFiles": ["a.py"],
            "readonlyFiles": [],
            "expectedArtifacts": {
                "file": "a.py",
                "contains": [
                    {"type": "function", "name": "f"},
                    {"type": "parameter", "name": "x", "function": "f"},
                ],
            },
            "validationCommand": ["pytest"],
        }
        v2 = convert_v1_to_v2(v1)
        artifacts = v2["files"]["create"][0]["artifacts"]
        assert len(artifacts) == 1
        assert artifacts[0]["name"] == "f"

    def test_validation_command_singular(self):
        """V1 validationCommand -> v2 validate (wrapped in list)."""
        v1 = {
            "goal": "Test",
            "creatableFiles": ["a.py"],
            "readonlyFiles": [],
            "expectedArtifacts": {
                "file": "a.py",
                "contains": [{"type": "class", "name": "A"}],
            },
            "validationCommand": ["pytest", "tests/test.py", "-v"],
        }
        v2 = convert_v1_to_v2(v1)
        assert v2["validate"] == [["pytest", "tests/test.py", "-v"]]

    def test_validation_commands_plural(self):
        """V1 validationCommands -> v2 validate (direct)."""
        v1 = {
            "goal": "Test",
            "creatableFiles": ["a.py"],
            "readonlyFiles": [],
            "expectedArtifacts": {
                "file": "a.py",
                "contains": [{"type": "class", "name": "A"}],
            },
            "validationCommands": [["pytest", "a.py"], ["vitest", "b.ts"]],
        }
        v2 = convert_v1_to_v2(v1)
        assert v2["validate"] == [["pytest", "a.py"], ["vitest", "b.ts"]]

    def test_system_artifacts(self):
        """V1 systemArtifacts -> v2 files.snapshot."""
        v1 = {
            "goal": "System snapshot",
            "taskType": "system-snapshot",
            "readonlyFiles": [],
            "systemArtifacts": [
                {
                    "file": "src/a.py",
                    "contains": [{"type": "class", "name": "A"}],
                },
                {
                    "file": "src/b.py",
                    "contains": [{"type": "function", "name": "b"}],
                },
            ],
            "validationCommand": ["pytest"],
        }
        v2 = convert_v1_to_v2(v1)
        assert v2["type"] == "system-snapshot"
        snapshot = v2["files"]["snapshot"]
        assert len(snapshot) == 2
        assert snapshot[0]["path"] == "src/a.py"
        assert snapshot[0]["artifacts"][0]["kind"] == "class"

    def test_empty_supersedes(self):
        """V1 empty supersedes array is handled."""
        v1 = {
            "goal": "Test",
            "creatableFiles": ["a.py"],
            "readonlyFiles": [],
            "expectedArtifacts": {
                "file": "a.py",
                "contains": [{"type": "class", "name": "A"}],
            },
            "supersedes": [],
            "validationCommand": ["pytest"],
        }
        v2 = convert_v1_to_v2(v1)
        assert "supersedes" not in v2  # empty supersedes not included

    def test_default_task_type(self):
        """V1 without taskType defaults to feature."""
        v1 = {
            "goal": "Test",
            "creatableFiles": ["a.py"],
            "readonlyFiles": [],
            "expectedArtifacts": {
                "file": "a.py",
                "contains": [{"type": "class", "name": "A"}],
            },
            "validationCommand": ["pytest"],
        }
        v2 = convert_v1_to_v2(v1)
        assert v2["type"] == "feature"

    def test_parameters_legacy_format(self):
        """V1 parameters (legacy) converted to args."""
        v1 = {
            "goal": "Test",
            "creatableFiles": ["a.py"],
            "readonlyFiles": [],
            "expectedArtifacts": {
                "file": "a.py",
                "contains": [
                    {
                        "type": "function",
                        "name": "f",
                        "parameters": [{"name": "x"}, {"name": "y", "type": "int"}],
                    }
                ],
            },
            "validationCommand": ["pytest"],
        }
        v2 = convert_v1_to_v2(v1)
        artifact = v2["files"]["create"][0]["artifacts"][0]
        assert artifact["args"][0] == {"name": "x"}
        assert artifact["args"][1] == {"name": "y", "type": "int"}

    def test_real_project_manifest(self):
        """Convert actual v1 manifest from project fixtures."""
        fixture = V1_FIXTURES / "task-001-add-schema-validation.manifest.json"
        data = json.loads(fixture.read_text())
        v2 = convert_v1_to_v2(data)
        assert v2["schema"] == "2"
        assert v2["goal"] is not None
        assert "files" in v2
        assert "validate" in v2


class TestConvertV1File:
    def test_convert_file(self, tmp_path):
        v1 = {
            "goal": "Test conversion",
            "taskType": "create",
            "creatableFiles": ["src/app.py"],
            "readonlyFiles": [],
            "expectedArtifacts": {
                "file": "src/app.py",
                "contains": [{"type": "function", "name": "main"}],
            },
            "validationCommand": ["pytest"],
        }
        input_path = tmp_path / "test-task.manifest.json"
        input_path.write_text(json.dumps(v1))

        output = convert_v1_file(input_path)
        assert output.exists()
        assert output.suffix == ".yaml"
        assert "test-task" in output.name

    def test_convert_file_custom_output(self, tmp_path):
        v1 = {
            "goal": "Test",
            "creatableFiles": ["a.py"],
            "readonlyFiles": [],
            "expectedArtifacts": {
                "file": "a.py",
                "contains": [{"type": "class", "name": "A"}],
            },
            "validationCommand": ["pytest"],
        }
        input_path = tmp_path / "test.manifest.json"
        input_path.write_text(json.dumps(v1))
        output_path = tmp_path / "custom.manifest.yaml"

        result = convert_v1_file(input_path, output_path)
        assert result == output_path
        assert result.exists()
