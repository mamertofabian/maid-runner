"""Behavioral tests for deriving recall queries from manifests."""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from maid_runner.core.outcomes import OutcomeIndex, OutcomeIndexRecord


def test_derive_recall_query_extracts_traceable_manifest_signals(tmp_path: Path):
    from maid_runner.core.outcome_recall import (
        ManifestQuerySignal,
        ManifestRecallDerivation,
        derive_recall_query,
    )

    manifest_path = tmp_path / "manifests" / "drafts" / "query.manifest.yaml"
    _write_manifest(
        manifest_path,
        files={
            "create": [
                {
                    "path": "src/new.py",
                    "artifacts": [{"kind": "function", "name": "build_new"}],
                }
            ],
            "edit": [
                {
                    "path": "src/existing.py",
                    "artifacts": [
                        {
                            "kind": "method",
                            "name": "refresh",
                            "of": "ExistingService",
                        }
                    ],
                }
            ],
            "delete": [{"path": "src/old.py", "reason": "Replaced"}],
        },
        tags=["outcome-records", "recall"],
        validate=[
            "uv run python -m pytest -q tests/core/test_manifest_recall_query.py"
        ],
    )

    derivation = derive_recall_query(manifest_path, project_root=tmp_path)

    assert isinstance(derivation, ManifestRecallDerivation)
    assert derivation.manifest_path == "manifests/drafts/query.manifest.yaml"
    assert isinstance(derivation.signals[0], ManifestQuerySignal)
    assert (
        ManifestQuerySignal(
            value="src/new.py",
            dimension="path",
            source_field="files.create[0].path",
        )
        in derivation.signals
    )
    assert (
        ManifestQuerySignal(
            value="src/existing.py",
            dimension="path",
            source_field="files.edit[0].path",
        )
        in derivation.signals
    )
    assert (
        ManifestQuerySignal(
            value="src/old.py",
            dimension="path",
            source_field="files.delete[0].path",
        )
        in derivation.signals
    )
    assert (
        ManifestQuerySignal(
            value="src/new.py:function:build_new",
            dimension="artifact",
            source_field="files.create[0].artifacts[0].name",
        )
        in derivation.signals
    )
    assert (
        ManifestQuerySignal(
            value="src/existing.py:method:ExistingService.refresh",
            dimension="artifact",
            source_field="files.edit[0].artifacts[0].name",
        )
        in derivation.signals
    )
    assert (
        ManifestQuerySignal(
            value="outcome-records",
            dimension="tag",
            source_field="metadata.tags[0]",
        )
        in derivation.signals
    )
    assert (
        ManifestQuerySignal(
            value="pytest",
            dimension="validation-command",
            source_field="validate[0]",
        )
        in derivation.signals
    )
    assert derivation.query.paths == ("src/new.py", "src/existing.py", "src/old.py")
    assert derivation.query.artifacts == (
        "src/new.py:function:build_new",
        "src/existing.py:method:ExistingService.refresh",
    )
    assert derivation.query.tags == ("outcome-records", "recall")
    assert "pytest" in derivation.query.validation_commands
    assert derivation.query.project_root == str(tmp_path)


def test_derive_recall_query_rejects_manifest_without_query_signals(
    tmp_path: Path,
):
    from maid_runner.core.outcome_recall import derive_recall_query

    manifest_path = tmp_path / "empty.manifest.yaml"
    _write_manifest(manifest_path, files={"read": ["README.md"]})

    with pytest.raises(ValueError) as exc_info:
        derive_recall_query(manifest_path, project_root=tmp_path)

    assert str(manifest_path) in str(exc_info.value)
    assert "no recall query signals" in str(exc_info.value)


def test_derive_recall_query_resolves_relative_manifest_under_project_root(
    tmp_path: Path,
    monkeypatch,
):
    from maid_runner.core.outcome_recall import derive_recall_query

    project_root = tmp_path / "repo"
    manifest_path = project_root / "manifests" / "query.manifest.yaml"
    _write_manifest(
        manifest_path,
        files={
            "edit": [
                {
                    "path": "src/project.py",
                    "artifacts": [{"kind": "function", "name": "project_task"}],
                }
            ]
        },
    )
    outside = tmp_path / "outside"
    outside.mkdir()
    monkeypatch.chdir(outside)

    derivation = derive_recall_query(
        "manifests/query.manifest.yaml",
        project_root=project_root,
    )

    assert derivation.manifest_path == "manifests/query.manifest.yaml"
    assert derivation.query.paths == ("src/project.py",)


def test_manifest_derived_query_reuses_existing_recall_tie_breakers(
    tmp_path: Path,
):
    from maid_runner.core.outcome_recall import derive_recall_query, recall_outcomes

    manifest_path = tmp_path / "query.manifest.yaml"
    _write_manifest(manifest_path, tags=["shared"])
    derivation = derive_recall_query(manifest_path, project_root=tmp_path)

    beta = _record(
        "beta",
        manifest_path="manifests/z-beta.manifest.yaml",
        tags=("shared",),
    )
    alpha = _record(
        "alpha",
        manifest_path="manifests/z-alpha.manifest.yaml",
        tags=("shared",),
    )

    matches = recall_outcomes(_index(beta, alpha), derivation.query)

    assert [match.record.manifest_slug for match in matches] == ["alpha", "beta"]


def test_manifest_derived_query_returns_no_matches_for_empty_index(tmp_path: Path):
    from maid_runner.core.outcome_recall import derive_recall_query, recall_outcomes

    manifest_path = tmp_path / "query.manifest.yaml"
    _write_manifest(manifest_path, tags=["missing"])
    derivation = derive_recall_query(manifest_path, project_root=tmp_path)

    assert recall_outcomes(_index(), derivation.query) == []


def _write_manifest(
    path: Path,
    *,
    files: dict | None = None,
    tags: list[str] | None = None,
    validate: list[str] | None = None,
) -> None:
    data = {
        "schema": "2",
        "goal": "derive recall query",
        "type": "feature",
        "created": "2026-06-10T06:01:00Z",
        "metadata": {"tags": tags or []},
        "files": files or {},
        "validate": validate or [],
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(yaml.safe_dump(data, sort_keys=False))


def _index(*records: OutcomeIndexRecord) -> OutcomeIndex:
    return OutcomeIndex(
        schema_version="1",
        generated_from="test",
        included_statuses=("completed",),
        manifest_dir="manifests",
        project_root=".",
        records=tuple(records),
    )


def _record(
    manifest_slug: str,
    *,
    manifest_path: str | None = None,
    tags: tuple[str, ...] = (),
) -> OutcomeIndexRecord:
    return OutcomeIndexRecord(
        manifest_slug=manifest_slug,
        manifest_path=manifest_path or f"manifests/{manifest_slug}.manifest.yaml",
        status="completed",
        lifecycle_status="active",
        superseded_by=None,
        task_type="feature",
        created="2026-05-30",
        completed_at="2026-05-31T01:02:03Z",
        tags=tags,
        declared_paths=(),
        artifacts=(),
        validation_commands=(),
        validation_evidence=(),
        lessons=(),
        review_notes=(),
        source_fingerprint="0" * 64,
    )
