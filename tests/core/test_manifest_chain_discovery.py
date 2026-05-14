"""Regression tests for manifest directory discovery."""

from __future__ import annotations

import json
from pathlib import Path

import yaml

from maid_runner.core.chain import ManifestChain
from maid_runner.core.result import ErrorCode
from maid_runner.core.types import ValidationMode
from maid_runner.core.validate import ValidationEngine


def _write_manifest(
    path: Path,
    *,
    goal: str,
    source_path: str,
    artifact: str,
    draft_marker: bool = False,
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    manifest = {
        "schema": "2",
        "goal": goal,
        "type": "fix",
        "files": {
            "create": [
                {
                    "path": source_path,
                    "artifacts": [{"kind": "function", "name": artifact}],
                }
            ],
            "read": [f"tests/test_{artifact}.py"],
        },
        "validate": [f"pytest tests/test_{artifact}.py -q"],
    }
    if path.suffix == ".json":
        path.write_text(json.dumps(manifest))
    else:
        prefix = "# draft-kind: implementation\n" if draft_marker else ""
        path.write_text(prefix + yaml.dump(manifest))


def _write_manifest_with_description(
    path: Path,
    *,
    description: str,
    source_path: str,
    artifact: str,
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        yaml.dump(
            {
                "schema": "2",
                "goal": "Manifest with marker-looking text in description",
                "description": description,
                "type": "fix",
                "files": {
                    "create": [
                        {
                            "path": source_path,
                            "artifacts": [{"kind": "function", "name": artifact}],
                        }
                    ],
                    "read": [f"tests/test_{artifact}.py"],
                },
                "validate": [f"pytest tests/test_{artifact}.py -q"],
            }
        )
    )


def _write_manifest_with_block_description_marker(
    path: Path,
    *,
    source_path: str,
    artifact: str,
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        f"""schema: "2"
goal: "Manifest with marker-looking block scalar text"
description: |
  # draft-kind: this is scalar content, not a file marker
type: fix
files:
  create:
    - path: {source_path}
      artifacts:
        - kind: function
          name: {artifact}
  read:
    - tests/test_{artifact}.py
validate:
  - pytest tests/test_{artifact}.py -q
"""
    )


def _write_v1_manifest(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(
            {
                "goal": "Legacy archived v1 manifest",
                "taskType": "create",
                "creatableFiles": ["src/legacy.py"],
                "readonlyFiles": ["tests/test_legacy.py"],
                "expectedArtifacts": {
                    "file": "src/legacy.py",
                    "contains": [{"type": "function", "name": "legacy"}],
                },
                "validationCommand": ["pytest tests/test_legacy.py"],
            }
        )
    )


def _write_test(project_root: Path, *, artifact: str, module: str) -> None:
    test_path = project_root / "tests" / f"test_{artifact}.py"
    test_path.parent.mkdir(parents=True, exist_ok=True)
    test_path.write_text(
        f"from {module} import {artifact}\n\n"
        f"def test_{artifact}():\n"
        f"    assert {artifact} is not None\n"
    )


def test_manifest_chain_discovers_nested_active_manifests_and_skips_inactive_dirs(
    tmp_path: Path,
) -> None:
    manifest_dir = tmp_path / "manifests"
    _write_manifest(
        manifest_dir / "top-level.manifest.yaml",
        goal="Top-level active manifest",
        source_path="src/top_level.py",
        artifact="top_level",
    )
    _write_test(tmp_path, artifact="top_level", module="src.top_level")
    _write_manifest(
        manifest_dir / "components" / "auth" / "nested-yaml.manifest.yaml",
        goal="Nested active YAML manifest",
        source_path="src/nested_yaml.py",
        artifact="nested_yaml",
    )
    _write_test(tmp_path, artifact="nested_yaml", module="src.nested_yaml")
    _write_manifest(
        manifest_dir / "features" / "billing" / "nested-yml.manifest.yml",
        goal="Nested active YML manifest",
        source_path="src/nested_yml.py",
        artifact="nested_yml",
    )
    _write_test(tmp_path, artifact="nested_yml", module="src.nested_yml")
    _write_manifest(
        manifest_dir / "domains" / "search" / "nested-json.manifest.json",
        goal="Nested active JSON manifest",
        source_path="src/nested_json.py",
        artifact="nested_json",
    )
    _write_test(tmp_path, artifact="nested_json", module="src.nested_json")
    _write_manifest(
        manifest_dir / "drafts" / "future-draft.manifest.yaml",
        goal="Inactive draft manifest",
        source_path="src/future_draft.py",
        artifact="future_draft",
        draft_marker=True,
    )
    _write_v1_manifest(manifest_dir / "v1-archive" / "archived.manifest.json")

    chain = ManifestChain(manifest_dir, tmp_path)

    assert {manifest.slug for manifest in chain.all_manifests} == {
        "nested-json",
        "nested-yaml",
        "nested-yml",
        "top-level",
    }
    assert {manifest.slug for manifest in chain.active_manifests()} == {
        "nested-json",
        "nested-yaml",
        "nested-yml",
        "top-level",
    }
    assert chain.diagnostics() == []


def test_validate_all_reports_nested_active_manifest_failures_from_root_dir(
    tmp_path: Path,
) -> None:
    manifest_dir = tmp_path / "manifests"
    _write_manifest(
        manifest_dir / "top-level.manifest.yaml",
        goal="Top-level active manifest",
        source_path="src/top_level.py",
        artifact="top_level",
    )
    _write_test(tmp_path, artifact="top_level", module="src.top_level")
    _write_manifest(
        manifest_dir / "components" / "auth" / "nested-active.manifest.yml",
        goal="Nested active manifest",
        source_path="src/missing_nested.py",
        artifact="missing_nested",
    )
    _write_test(tmp_path, artifact="missing_nested", module="src.missing_nested")
    _write_manifest(
        manifest_dir / "drafts" / "future-draft.manifest.yaml",
        goal="Inactive draft manifest",
        source_path="src/future_draft.py",
        artifact="future_draft",
        draft_marker=True,
    )
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "top_level.py").write_text(
        "def top_level():\n    return 'top-level'\n"
    )

    engine = ValidationEngine(project_root=tmp_path)
    direct_nested = engine.validate(
        manifest_dir / "components" / "auth" / "nested-active.manifest.yml",
        mode=ValidationMode.IMPLEMENTATION,
        use_chain=False,
    )

    assert direct_nested.success is False

    batch = engine.validate_all("manifests/", mode=ValidationMode.IMPLEMENTATION)

    assert batch.success is False
    assert {result.manifest_slug for result in batch.results} == {
        "nested-active",
        "top-level",
    }
    nested_result = next(
        result for result in batch.results if result.manifest_slug == "nested-active"
    )
    assert [error.code for error in nested_result.errors] == [
        ErrorCode.FILE_SHOULD_BE_PRESENT
    ]


def test_manifest_chain_reports_unmarked_manifest_hidden_under_inactive_dir(
    tmp_path: Path,
) -> None:
    manifest_dir = tmp_path / "manifests"
    _write_manifest(
        manifest_dir / "top-level.manifest.yaml",
        goal="Top-level active manifest",
        source_path="src/top_level.py",
        artifact="top_level",
    )
    _write_manifest(
        manifest_dir / "drafts" / "hidden-active.manifest.yaml",
        goal="Hidden active-looking draft manifest",
        source_path="src/hidden_active.py",
        artifact="hidden_active",
    )
    _write_manifest(
        manifest_dir / "v1-archive" / "hidden-active.manifest.yaml",
        goal="Hidden active-looking archive manifest",
        source_path="src/hidden_archive.py",
        artifact="hidden_archive",
    )

    chain = ManifestChain(manifest_dir, tmp_path)

    assert {manifest.slug for manifest in chain.all_manifests} == {"top-level"}
    hidden_errors = [
        error
        for error in chain.inactive_manifest_diagnostics()
        if error.code == ErrorCode.INACTIVE_MANIFEST_NOT_MARKED
    ]
    assert [error.location.file for error in hidden_errors] == [
        str(manifest_dir / "drafts" / "hidden-active.manifest.yaml"),
        str(manifest_dir / "v1-archive" / "hidden-active.manifest.yaml"),
    ]


def test_validate_all_fails_when_inactive_dir_contains_unmarked_v2_manifest(
    tmp_path: Path,
) -> None:
    manifest_dir = tmp_path / "manifests"
    _write_manifest(
        manifest_dir / "top-level.manifest.yaml",
        goal="Top-level active manifest",
        source_path="src/top_level.py",
        artifact="top_level",
    )
    _write_test(tmp_path, artifact="top_level", module="src.top_level")
    _write_manifest(
        manifest_dir / "drafts" / "hidden-active.manifest.yaml",
        goal="Hidden active-looking draft manifest",
        source_path="src/hidden_active.py",
        artifact="hidden_active",
    )
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "top_level.py").write_text(
        "def top_level():\n    return 'top-level'\n"
    )

    batch = ValidationEngine(project_root=tmp_path).validate_all(
        "manifests/", mode=ValidationMode.IMPLEMENTATION
    )

    assert batch.success is False
    assert [error.code for error in batch.chain_errors] == [
        ErrorCode.INACTIVE_MANIFEST_NOT_MARKED
    ]
    assert "hidden-active.manifest.yaml" in batch.chain_errors[0].message


def test_inactive_marker_text_inside_yaml_value_does_not_mark_manifest(
    tmp_path: Path,
) -> None:
    manifest_dir = tmp_path / "manifests"
    _write_manifest(
        manifest_dir / "top-level.manifest.yaml",
        goal="Top-level active manifest",
        source_path="src/top_level.py",
        artifact="top_level",
    )
    _write_manifest_with_description(
        manifest_dir / "drafts" / "hidden-active.manifest.yaml",
        description="This text mentions # draft-kind: but is not a marker line.",
        source_path="src/hidden_active.py",
        artifact="hidden_active",
    )

    chain = ManifestChain(manifest_dir, tmp_path)

    assert [error.code for error in chain.inactive_manifest_diagnostics()] == [
        ErrorCode.INACTIVE_MANIFEST_NOT_MARKED
    ]


def test_inactive_marker_text_inside_yaml_block_scalar_does_not_mark_manifest(
    tmp_path: Path,
) -> None:
    manifest_dir = tmp_path / "manifests"
    _write_manifest(
        manifest_dir / "top-level.manifest.yaml",
        goal="Top-level active manifest",
        source_path="src/top_level.py",
        artifact="top_level",
    )
    _write_manifest_with_block_description_marker(
        manifest_dir / "drafts" / "hidden-active.manifest.yaml",
        source_path="src/hidden_active.py",
        artifact="hidden_active",
    )

    chain = ManifestChain(manifest_dir, tmp_path)

    assert [error.code for error in chain.inactive_manifest_diagnostics()] == [
        ErrorCode.INACTIVE_MANIFEST_NOT_MARKED
    ]


def test_validate_all_schema_mode_fails_when_inactive_dir_contains_unmarked_v2_manifest(
    tmp_path: Path,
) -> None:
    manifest_dir = tmp_path / "manifests"
    _write_manifest(
        manifest_dir / "top-level.manifest.yaml",
        goal="Top-level active manifest",
        source_path="src/top_level.py",
        artifact="top_level",
    )
    _write_manifest(
        manifest_dir / "drafts" / "hidden-active.manifest.yaml",
        goal="Hidden active-looking draft manifest",
        source_path="src/hidden_active.py",
        artifact="hidden_active",
    )

    batch = ValidationEngine(project_root=tmp_path).validate_all(
        "manifests/", mode=ValidationMode.SCHEMA
    )

    assert batch.success is False
    assert [error.code for error in batch.chain_errors] == [
        ErrorCode.INACTIVE_MANIFEST_NOT_MARKED
    ]


def test_selected_inactive_directory_root_still_loads_direct_manifests(
    tmp_path: Path,
) -> None:
    manifest_dir = tmp_path / "manifests"
    _write_manifest(
        manifest_dir / "drafts" / "selected-draft.manifest.yaml",
        goal="Selected draft manifest",
        source_path="src/selected_draft.py",
        artifact="selected_draft",
    )

    chain = ManifestChain(manifest_dir / "drafts", tmp_path)

    assert {manifest.slug for manifest in chain.all_manifests} == {"selected-draft"}
    assert chain.diagnostics() == []
