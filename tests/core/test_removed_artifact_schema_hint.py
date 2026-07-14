"""Behavioral contract for the removed_artifacts test_function schema hint.

Contract: manifests/drafts/add-removed-test-artifact-schema-hint.manifest.yaml

When schema validation rejects a removed_artifacts entry whose kind is
exactly 'test_function', the error string keeps the original jsonschema
"path: message" prefix and appends a targeted remediation hint. Other
invalid kinds keep the bare enum error so the hint never misleads.
"""

import pytest
import yaml

from maid_runner.core.manifest import (
    ManifestSchemaError,
    load_manifest,
    validate_manifest_schema,
)

HINT_PHRASE = "test artifacts never need removed_artifacts entries"
HINT_REMEDY_PHRASE = "superseding manifest"


def _manifest_data(removed_artifacts=None, create_artifacts=None):
    data = {
        "schema": "2",
        "goal": "Retire obsolete tests while superseding a manifest",
        "files": {
            "create": [
                {
                    "path": "src/app.py",
                    "artifacts": create_artifacts
                    or [{"kind": "function", "name": "main"}],
                }
            ]
        },
        "validate": ["pytest tests/ -v"],
    }
    if removed_artifacts is not None:
        data["removed_artifacts"] = removed_artifacts
    return data


class TestRemovedTestArtifactSchemaHint:
    def test_removed_test_function_kind_error_includes_targeted_hint(self):
        data = _manifest_data(
            removed_artifacts=[
                {
                    "kind": "test_function",
                    "name": "test_pat_selection",
                    "file": "tests/test_pat.py",
                },
                {
                    "kind": "function",
                    "name": "select_pat",
                    "file": "src/pat.py",
                },
                {
                    "kind": "test_function",
                    "name": "test_pat_factory",
                    "file": "tests/test_pat.py",
                },
            ]
        )

        errors = validate_manifest_schema(data)

        hinted = [e for e in errors if HINT_PHRASE in e]
        assert len(hinted) == 2
        for index, error in zip((0, 2), sorted(hinted)):
            prefix = f"removed_artifacts.{index}.kind: 'test_function' is not one of"
            assert error.startswith(prefix)
            assert HINT_REMEDY_PHRASE in error
        assert not any("removed_artifacts.1" in e for e in errors)

    def test_removed_unknown_kind_error_has_no_test_hint(self):
        data = _manifest_data(
            removed_artifacts=[
                {
                    "kind": "component",
                    "name": "PatPicker",
                    "file": "src/pat.py",
                },
            ]
        )

        errors = validate_manifest_schema(data)

        assert any(
            e.startswith("removed_artifacts.0.kind: 'component' is not one of")
            for e in errors
        )
        assert not any(HINT_PHRASE in e for e in errors)

    def test_valid_removed_artifact_kind_produces_no_error(self):
        data = _manifest_data(
            removed_artifacts=[
                {
                    "kind": "function",
                    "name": "select_pat",
                    "file": "src/pat.py",
                },
            ]
        )

        errors = validate_manifest_schema(data)

        assert errors == []

    def test_test_function_kind_elsewhere_gets_no_removed_hint(self):
        data = _manifest_data(
            create_artifacts=[
                {"kind": "test_function", "name": "test_main_runs"},
            ]
        )
        data["files"]["create"][0]["path"] = "tests/test_app.py"

        errors = validate_manifest_schema(data)

        assert errors == []

    def test_load_manifest_schema_error_carries_hint(self, tmp_path):
        data = _manifest_data(
            removed_artifacts=[
                {
                    "kind": "test_function",
                    "name": "test_pat_selection",
                    "file": "tests/test_pat.py",
                },
            ]
        )
        manifest_path = tmp_path / "retire-pat-tests.manifest.yaml"
        manifest_path.write_text(yaml.dump(data, sort_keys=False))

        with pytest.raises(ManifestSchemaError) as exc_info:
            load_manifest(manifest_path)

        assert HINT_PHRASE in str(exc_info.value)
        assert HINT_REMEDY_PHRASE in str(exc_info.value)
