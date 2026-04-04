"""Integration tests: v1 backward compatibility.

Tests verify the v1-to-v2 auto-conversion pipeline:
- Load v1 JSON manifest -> auto-convert -> validate -> check result
- V1 method conversion (function + class -> method + of)
- V1 returns object format flattened
- V1 supersedes paths converted to slugs
- Full pipeline with real v1 fixture manifests
"""

from __future__ import annotations

import json
import textwrap
from pathlib import Path

import pytest
import yaml

from maid_runner.compat.v1_loader import (
    convert_v1_file,
    convert_v1_to_v2,
    is_v1_manifest,
)
from maid_runner.core.manifest import load_manifest
from maid_runner.core.result import ErrorCode
from maid_runner.core.validate import validate

FIXTURES = Path(__file__).parent.parent / "fixtures" / "manifests" / "v1"


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
# 1. V1 detection
# ---------------------------------------------------------------------------


class TestV1Detection:
    def test_v1_with_expected_artifacts(self):
        data = {"goal": "Test", "expectedArtifacts": {"file": "foo.py", "contains": []}}
        assert is_v1_manifest(data) is True

    def test_v1_with_creatable_files(self):
        data = {"goal": "Test", "creatableFiles": ["foo.py"]}
        assert is_v1_manifest(data) is True

    def test_v2_manifest_not_detected_as_v1(self):
        data = {"schema": "2", "goal": "Test", "expectedArtifacts": {}}
        assert is_v1_manifest(data) is False

    def test_v1_with_validation_command(self):
        data = {"goal": "Test", "validationCommand": ["pytest"]}
        assert is_v1_manifest(data) is True


# ---------------------------------------------------------------------------
# 2. V1 -> V2 conversion
# ---------------------------------------------------------------------------


class TestV1ToV2Conversion:
    def test_simple_create_manifest(self):
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
        assert v2["type"] == "feature"  # "create" maps to "feature"
        assert "files" in v2

        create_files = v2["files"]["create"]
        assert len(create_files) == 1
        assert create_files[0]["path"] == "maid_runner/validators/manifest_validator.py"

        artifacts = create_files[0]["artifacts"]
        assert len(artifacts) == 1
        assert artifacts[0]["kind"] == "function"
        assert artifacts[0]["name"] == "validate_schema"
        assert len(artifacts[0]["args"]) == 2

        assert v2["files"]["read"] == ["tests/test_validate_schema.py"]

    def test_method_conversion(self):
        """V1: function + class -> V2: method + of."""
        v1_artifact = {
            "type": "function",
            "name": "login",
            "class": "AuthService",
            "args": [{"name": "user", "type": "str"}],
            "returns": "bool",
        }

        v1 = {
            "goal": "Add login",
            "taskType": "edit",
            "editableFiles": ["src/auth.py"],
            "expectedArtifacts": {
                "file": "src/auth.py",
                "contains": [v1_artifact],
            },
            "validationCommand": ["pytest tests/ -v"],
        }

        v2 = convert_v1_to_v2(v1)
        art = v2["files"]["edit"][0]["artifacts"][0]

        assert art["kind"] == "method"
        assert art["name"] == "login"
        assert art["of"] == "AuthService"
        assert art["args"] == [{"name": "user", "type": "str"}]
        assert art["returns"] == "bool"

    def test_returns_object_flattened(self):
        """V1: returns: {type: "Optional[dict]"} -> V2: returns: "Optional[dict]"."""
        v1_artifact = {
            "type": "function",
            "name": "get_data",
            "returns": {"type": "Optional[dict]"},
        }

        v1 = {
            "goal": "Get data",
            "taskType": "create",
            "creatableFiles": ["src/data.py"],
            "expectedArtifacts": {
                "file": "src/data.py",
                "contains": [v1_artifact],
            },
            "validationCommand": ["pytest tests/ -v"],
        }

        v2 = convert_v1_to_v2(v1)
        art = v2["files"]["create"][0]["artifacts"][0]

        assert art["returns"] == "Optional[dict]"

    def test_supersedes_paths_to_slugs(self):
        """V1: supersedes paths -> V2: supersedes slugs."""
        v1 = {
            "goal": "Replace old",
            "taskType": "edit",
            "editableFiles": ["src/x.py"],
            "supersedes": [
                "manifests/task-001-add-schema.manifest.json",
                "manifests/task-002-add-ast-validation.manifest.json",
            ],
            "expectedArtifacts": {
                "file": "src/x.py",
                "contains": [{"type": "function", "name": "x"}],
            },
            "validationCommand": ["pytest tests/ -v"],
        }

        v2 = convert_v1_to_v2(v1)

        assert v2["supersedes"] == [
            "task-001-add-schema",
            "task-002-add-ast-validation",
        ]

    def test_task_type_mappings(self):
        """V1 taskType "create" and "edit" map to "feature" in v2."""
        for v1_type, expected_v2 in [
            ("create", "feature"),
            ("edit", "feature"),
            ("refactor", "refactor"),
            ("snapshot", "snapshot"),
            ("fix", "fix"),
        ]:
            v1 = {
                "goal": "Test",
                "taskType": v1_type,
                "creatableFiles": ["x.py"],
                "expectedArtifacts": {
                    "file": "x.py",
                    "contains": [{"type": "function", "name": "f"}],
                },
                "validationCommand": ["pytest"],
            }
            v2 = convert_v1_to_v2(v1)
            assert (
                v2["type"] == expected_v2
            ), f"{v1_type} -> {v2['type']} (expected {expected_v2})"

    def test_parameter_artifacts_skipped(self):
        """V1 'parameter' type artifacts are skipped (redundant with args)."""
        v1 = {
            "goal": "Test",
            "taskType": "create",
            "creatableFiles": ["x.py"],
            "expectedArtifacts": {
                "file": "x.py",
                "contains": [
                    {"type": "function", "name": "f"},
                    {"type": "parameter", "name": "x"},
                ],
            },
            "validationCommand": ["pytest"],
        }

        v2 = convert_v1_to_v2(v1)
        artifacts = v2["files"]["create"][0]["artifacts"]
        assert len(artifacts) == 1
        assert artifacts[0]["name"] == "f"


# ---------------------------------------------------------------------------
# 3. Full pipeline: load v1 JSON -> auto-convert -> Manifest object
# ---------------------------------------------------------------------------


class TestV1FullPipelineLoad:
    def test_load_v1_task_001(self):
        """Load real v1 fixture: task-001 create manifest."""
        path = FIXTURES / "task-001-add-schema-validation.manifest.json"
        if not path.exists():
            pytest.skip("V1 fixture not available")

        manifest = load_manifest(path)

        assert manifest.slug == "task-001-add-schema-validation"
        assert manifest.schema_version == "2"
        assert (
            "validate_schema" in manifest.goal.lower()
            or len(manifest.all_file_specs) > 0
        )

        # Should have file specs
        assert len(manifest.all_file_specs) > 0
        file_spec = manifest.all_file_specs[0]
        artifact_names = {a.name for a in file_spec.artifacts}
        assert "validate_schema" in artifact_names

    def test_load_v1_task_002_edit(self):
        """Load real v1 fixture: task-002 edit manifest with class and method."""
        path = FIXTURES / "task-002-add-ast-alignment-validation.manifest.json"
        if not path.exists():
            pytest.skip("V1 fixture not available")

        manifest = load_manifest(path)

        assert manifest.slug == "task-002-add-ast-alignment-validation"
        artifact_names = {
            a.name for fs in manifest.all_file_specs for a in fs.artifacts
        }
        assert "AlignmentError" in artifact_names
        assert "validate_with_ast" in artifact_names

    def test_load_v1_task_003_with_supersedes(self):
        """Load real v1 fixture: task-003 behavioral validation."""
        path = FIXTURES / "task-003-behavioral-validation.manifest.json"
        if not path.exists():
            pytest.skip("V1 fixture not available")

        manifest = load_manifest(path)
        assert manifest.slug == "task-003-behavioral-validation"


# ---------------------------------------------------------------------------
# 4. V1 load -> validate with source files
# ---------------------------------------------------------------------------


class TestV1ValidatePipeline:
    def test_v1_manifest_validates_against_source(self, tmp_path: Path):
        """Write a v1 JSON manifest, create matching source, validate passes."""
        manifests = tmp_path / "manifests"
        manifests.mkdir()
        src = tmp_path / "src"
        src.mkdir()

        # Create test file that references the artifact
        test_rel = _add_test_file(
            tmp_path, "tests/test_helper.py", "src.helper", ["helper"]
        )

        v1_data = {
            "goal": "Add helper",
            "taskType": "create",
            "creatableFiles": ["src/helper.py"],
            "readonlyFiles": [test_rel],
            "expectedArtifacts": {
                "file": "src/helper.py",
                "contains": [
                    {
                        "type": "function",
                        "name": "helper",
                        "parameters": [{"name": "x", "type": "int"}],
                        "returns": "str",
                    }
                ],
            },
            "validationCommand": ["pytest", "tests/test_helper.py", "-v"],
        }

        manifest_path = manifests / "add-helper.manifest.json"
        manifest_path.write_text(json.dumps(v1_data))

        (src / "helper.py").write_text(
            textwrap.dedent(
                """\
                def helper(x: int) -> str:
                    return str(x)
            """
            )
        )

        result = validate(
            str(manifest_path),
            use_chain=False,
            project_root=str(tmp_path),
        )

        assert result.success is True

    def test_v1_manifest_validates_fail_missing(self, tmp_path: Path):
        """V1 manifest with missing artifact should fail validation."""
        manifests = tmp_path / "manifests"
        manifests.mkdir()
        src = tmp_path / "src"
        src.mkdir()

        v1_data = {
            "goal": "Add foo",
            "taskType": "create",
            "creatableFiles": ["src/foo.py"],
            "expectedArtifacts": {
                "file": "src/foo.py",
                "contains": [{"type": "function", "name": "foo"}],
            },
            "validationCommand": ["pytest tests/ -v"],
        }

        manifest_path = manifests / "add-foo.manifest.json"
        manifest_path.write_text(json.dumps(v1_data))
        (src / "foo.py").write_text("# empty\n")

        result = validate(
            str(manifest_path),
            use_chain=False,
            project_root=str(tmp_path),
        )

        assert result.success is False
        assert any(e.code == ErrorCode.ARTIFACT_NOT_DEFINED for e in result.errors)


# ---------------------------------------------------------------------------
# 5. V1 file conversion
# ---------------------------------------------------------------------------


class TestV1FileConversion:
    def test_convert_v1_file_creates_yaml(self, tmp_path: Path):
        v1_data = {
            "goal": "Test convert",
            "taskType": "create",
            "creatableFiles": ["src/x.py"],
            "expectedArtifacts": {
                "file": "src/x.py",
                "contains": [{"type": "function", "name": "x_func"}],
            },
            "validationCommand": ["pytest tests/ -v"],
        }

        json_path = tmp_path / "task-042-test.manifest.json"
        json_path.write_text(json.dumps(v1_data))

        yaml_path = convert_v1_file(json_path)

        assert yaml_path.exists()
        assert yaml_path.suffix == ".yaml"

        reloaded = yaml.safe_load(yaml_path.read_text())
        assert reloaded["schema"] == "2"
        assert reloaded["goal"] == "Test convert"

    def test_convert_v1_file_to_custom_path(self, tmp_path: Path):
        v1_data = {
            "goal": "Test",
            "taskType": "create",
            "creatableFiles": ["a.py"],
            "expectedArtifacts": {
                "file": "a.py",
                "contains": [{"type": "function", "name": "a"}],
            },
            "validationCommand": ["pytest"],
        }

        json_path = tmp_path / "old.manifest.json"
        json_path.write_text(json.dumps(v1_data))

        custom_out = tmp_path / "custom.manifest.yaml"
        result_path = convert_v1_file(json_path, custom_out)

        assert result_path == custom_out
        assert custom_out.exists()


# ---------------------------------------------------------------------------
# 6. V1 manifest in chain with v2 manifests
# ---------------------------------------------------------------------------


class TestV1InChainWithV2:
    def test_mixed_v1_v2_chain(self, tmp_path: Path):
        """V1 and V2 manifests can coexist in the same manifest directory."""
        manifests = tmp_path / "manifests"
        manifests.mkdir()
        src = tmp_path / "src"
        src.mkdir()

        # Create test files that reference the artifacts
        test_base_rel = _add_test_file(
            tmp_path, "tests/test_base.py", "src.mixed", ["base_func"]
        )
        test_extra_rel = _add_test_file(
            tmp_path, "tests/test_extra.py", "src.mixed", ["extra_func"]
        )

        # V1 manifest (JSON)
        v1_data = {
            "goal": "Add base function",
            "taskType": "create",
            "creatableFiles": ["src/mixed.py"],
            "readonlyFiles": [test_base_rel],
            "expectedArtifacts": {
                "file": "src/mixed.py",
                "contains": [{"type": "function", "name": "base_func"}],
            },
            "validationCommand": ["pytest", "tests/test_base.py", "-v"],
        }
        (manifests / "add-base.manifest.json").write_text(json.dumps(v1_data))

        # V2 manifest (YAML) that edits same file
        v2_data = {
            "schema": "2",
            "goal": "Add extra function",
            "type": "feature",
            "files": {
                "edit": [
                    {
                        "path": "src/mixed.py",
                        "artifacts": [{"kind": "function", "name": "extra_func"}],
                    }
                ],
                "read": [test_extra_rel],
            },
            "validate": ["pytest tests/test_extra.py -v"],
            "created": "2025-07-01T00:00:00Z",
        }
        v2_path = manifests / "add-extra.manifest.yaml"
        v2_path.write_text(
            yaml.dump(v2_data, default_flow_style=False, sort_keys=False)
        )

        # Source has both functions
        (src / "mixed.py").write_text(
            textwrap.dedent(
                """\
                def base_func():
                    pass

                def extra_func():
                    pass
            """
            )
        )

        from maid_runner.core.validate import ValidationEngine

        engine = ValidationEngine(project_root=tmp_path)
        batch = engine.validate_all("manifests/")

        assert batch.success is True
        assert batch.passed == 2
