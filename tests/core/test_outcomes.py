"""Behavioral tests for deterministic Outcome indexing."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
import yaml


def test_build_outcome_index_includes_completed_outcomes_by_default(tmp_path: Path):
    from maid_runner.core.outcomes import (
        OutcomeIndex,
        OutcomeIndexRecord,
        build_outcome_index,
    )

    manifest_dir = tmp_path / "manifests"
    manifest_dir.mkdir()
    _write_manifest(manifest_dir / "completed.manifest.yaml")
    _write_manifest(
        manifest_dir / "failed.manifest.yaml",
        slug_goal="failed outcome",
        outcome_status="failed",
    )
    _write_manifest(manifest_dir / "no-outcome.manifest.yaml", outcome=None)

    index = build_outcome_index(manifest_dir, project_root=tmp_path)

    assert isinstance(index, OutcomeIndex)
    assert index.schema_version == "1"
    assert index.manifest_dir == "manifests"
    assert index.project_root == tmp_path.resolve().as_posix()
    assert index.included_statuses == ("completed",)
    assert len(index.records) == 1

    record = index.records[0]
    assert isinstance(record, OutcomeIndexRecord)
    assert record.manifest_slug == "completed"
    assert record.manifest_path == "manifests/completed.manifest.yaml"
    assert record.status == "completed"
    assert record.lifecycle_status == "active"
    assert record.superseded_by is None
    assert record.task_type == "feature"
    assert record.created == "2026-05-30"
    assert record.completed_at == "2026-05-31T01:02:03Z"
    assert record.tags == ("learning", "outcome")
    assert record.declared_paths == ("src/completed.py", "tests/test_completed.py")
    assert record.artifacts == ("src/completed.py:function:completed_task",)
    assert record.validation_commands == (
        ("uv", "run", "python", "-m", "pytest", "-q", "tests/test_completed.py"),
    )
    assert record.validation_evidence[0].command == ("uv", "run", "maid", "test")
    assert record.lessons[0].lesson_type == "testing"
    assert record.review_notes[0].source == "implementation-review"
    assert len(record.source_fingerprint) == 64
    assert index.generated_from


def test_build_outcome_index_excludes_inactive_lifecycle_manifests_by_default(
    tmp_path: Path,
):
    from maid_runner.core.outcomes import build_outcome_index

    manifest_dir = tmp_path / "manifests"
    manifest_dir.mkdir()
    for status in ("planning", "draft", "archived", "archive", "epic", "legacy"):
        _write_manifest(
            manifest_dir / f"{status}.manifest.yaml",
            slug_goal=f"{status} outcome",
            metadata_status=status,
        )
    _write_manifest(manifest_dir / "active.manifest.yaml")

    index = build_outcome_index(manifest_dir, project_root=tmp_path)

    assert [record.manifest_slug for record in index.records] == ["active"]
    assert all(record.lifecycle_status == "active" for record in index.records)


def test_build_outcome_index_skips_inactive_manifest_directories_by_default(
    tmp_path: Path,
):
    from maid_runner.core.outcomes import build_outcome_index

    manifest_dir = tmp_path / "manifests"
    draft_dir = manifest_dir / "drafts"
    archive_dir = manifest_dir / "v1-archive"
    draft_dir.mkdir(parents=True)
    archive_dir.mkdir()
    _write_manifest(manifest_dir / "active.manifest.yaml")
    _write_manifest(draft_dir / "draft.manifest.yaml")
    (archive_dir / "legacy.manifest.json").write_text('{"legacy": true}\n')

    index = build_outcome_index(manifest_dir, project_root=tmp_path)

    assert [record.manifest_slug for record in index.records] == ["active"]


def test_build_outcome_index_include_statuses_replaces_default_filter(
    tmp_path: Path,
):
    from maid_runner.core.outcomes import build_outcome_index

    manifest_dir = tmp_path / "manifests"
    manifest_dir.mkdir()
    _write_manifest(manifest_dir / "completed.manifest.yaml")
    _write_manifest(
        manifest_dir / "failed.manifest.yaml",
        slug_goal="failed outcome",
        outcome_status="failed",
    )
    _write_manifest(
        manifest_dir / "partial.manifest.yaml",
        slug_goal="partial outcome",
        outcome_status="partial",
    )

    index = build_outcome_index(
        manifest_dir,
        project_root=tmp_path,
        include_statuses={"failed", "partial"},
    )

    assert [record.status for record in index.records] == ["failed", "partial"]
    assert [record.manifest_slug for record in index.records] == ["failed", "partial"]


def test_build_outcome_index_records_chain_supersession_metadata(tmp_path: Path):
    from maid_runner.core.outcomes import build_outcome_index

    manifest_dir = tmp_path / "manifests"
    manifest_dir.mkdir()
    _write_manifest(manifest_dir / "old.manifest.yaml")
    _write_manifest(
        manifest_dir / "new.manifest.yaml",
        slug_goal="new outcome",
        supersedes=["old"],
    )

    index = build_outcome_index(manifest_dir, project_root=tmp_path)

    records_by_slug = {record.manifest_slug: record for record in index.records}
    assert records_by_slug["old"].superseded_by == "new"
    assert records_by_slug["new"].superseded_by is None


def test_build_outcome_index_rejects_invalid_status_filters(tmp_path: Path):
    from maid_runner.core.outcomes import build_outcome_index

    manifest_dir = tmp_path / "manifests"
    manifest_dir.mkdir()
    _write_manifest(manifest_dir / "completed.manifest.yaml")

    with pytest.raises(ValueError, match="done"):
        build_outcome_index(
            manifest_dir,
            project_root=tmp_path,
            include_statuses={"completed", "done"},
        )


def test_outcome_index_round_trips_with_byte_stable_source_fingerprint(
    tmp_path: Path,
):
    from maid_runner.core.outcomes import read_outcome_index, write_outcome_index
    from maid_runner.core.outcomes import build_outcome_index

    manifest_dir = tmp_path / "manifests"
    manifest_dir.mkdir()
    _write_manifest(manifest_dir / "b.manifest.yaml", slug_goal="b outcome")
    _write_manifest(manifest_dir / "a.manifest.yaml", slug_goal="a outcome")
    first_path = tmp_path / "outcomes-first.json"
    second_path = tmp_path / "outcomes-second.json"

    index = build_outcome_index(manifest_dir, project_root=tmp_path)
    write_outcome_index(index, first_path)
    write_outcome_index(
        build_outcome_index(manifest_dir, project_root=tmp_path), second_path
    )

    assert first_path.read_bytes() == second_path.read_bytes()
    assert [record.manifest_slug for record in index.records] == ["a", "b"]
    assert read_outcome_index(first_path) == index
    payload = json.loads(first_path.read_text())
    assert "generated_at" not in payload
    assert payload["generated_from"] == index.generated_from
    assert (
        payload["records"][0]["source_fingerprint"]
        == index.records[0].source_fingerprint
    )


def test_outcome_index_detects_changed_and_missing_sources(tmp_path: Path):
    from maid_runner.core.outcomes import (
        build_outcome_index,
        outcome_index_is_stale,
        write_outcome_index,
    )

    manifest_dir = tmp_path / "manifests"
    manifest_dir.mkdir()
    source = manifest_dir / "completed.manifest.yaml"
    _write_manifest(source)
    index_path = tmp_path / "outcomes.json"
    write_outcome_index(
        build_outcome_index(manifest_dir, project_root=tmp_path), index_path
    )

    assert not outcome_index_is_stale(index_path, manifest_dir, project_root=tmp_path)

    data = yaml.safe_load(source.read_text())
    data["outcome"]["summary"] = "Changed after indexing."
    source.write_text(yaml.safe_dump(data, sort_keys=False))
    assert outcome_index_is_stale(index_path, manifest_dir, project_root=tmp_path)

    source.unlink()
    assert outcome_index_is_stale(index_path, manifest_dir, project_root=tmp_path)


def test_outcome_index_staleness_preserves_index_status_filter(tmp_path: Path):
    from maid_runner.core.outcomes import (
        build_outcome_index,
        outcome_index_is_stale,
        write_outcome_index,
    )

    manifest_dir = tmp_path / "manifests"
    manifest_dir.mkdir()
    _write_manifest(manifest_dir / "completed.manifest.yaml")
    _write_manifest(
        manifest_dir / "failed.manifest.yaml",
        slug_goal="failed outcome",
        outcome_status="failed",
    )
    index_path = tmp_path / "failed-outcomes.json"
    write_outcome_index(
        build_outcome_index(
            manifest_dir,
            project_root=tmp_path,
            include_statuses={"failed"},
        ),
        index_path,
    )

    assert not outcome_index_is_stale(index_path, manifest_dir, project_root=tmp_path)


def test_outcome_index_staleness_preserves_zero_record_status_filter(tmp_path: Path):
    from maid_runner.core.outcomes import (
        build_outcome_index,
        outcome_index_is_stale,
        write_outcome_index,
    )

    manifest_dir = tmp_path / "manifests"
    manifest_dir.mkdir()
    _write_manifest(manifest_dir / "completed.manifest.yaml")
    index_path = tmp_path / "failed-outcomes.json"
    index = build_outcome_index(
        manifest_dir,
        project_root=tmp_path,
        include_statuses={"failed"},
    )
    write_outcome_index(index, index_path)

    assert index.records == ()
    assert index.included_statuses == ("failed",)
    assert not outcome_index_is_stale(index_path, manifest_dir, project_root=tmp_path)


def test_outcome_index_staleness_detects_new_status_from_original_filter(
    tmp_path: Path,
):
    from maid_runner.core.outcomes import (
        build_outcome_index,
        outcome_index_is_stale,
        write_outcome_index,
    )

    manifest_dir = tmp_path / "manifests"
    manifest_dir.mkdir()
    _write_manifest(
        manifest_dir / "failed.manifest.yaml",
        slug_goal="failed outcome",
        outcome_status="failed",
    )
    index_path = tmp_path / "mixed-outcomes.json"
    write_outcome_index(
        build_outcome_index(
            manifest_dir,
            project_root=tmp_path,
            include_statuses={"failed", "partial"},
        ),
        index_path,
    )

    assert not outcome_index_is_stale(index_path, manifest_dir, project_root=tmp_path)

    _write_manifest(
        manifest_dir / "partial.manifest.yaml",
        slug_goal="partial outcome",
        outcome_status="partial",
    )
    assert outcome_index_is_stale(index_path, manifest_dir, project_root=tmp_path)


def test_outcome_index_staleness_detects_excluded_supersession_metadata_change(
    tmp_path: Path,
):
    from maid_runner.core.outcomes import (
        build_outcome_index,
        outcome_index_is_stale,
        write_outcome_index,
    )

    manifest_dir = tmp_path / "manifests"
    manifest_dir.mkdir()
    _write_manifest(manifest_dir / "old.manifest.yaml")
    index_path = tmp_path / "outcomes.json"
    write_outcome_index(
        build_outcome_index(manifest_dir, project_root=tmp_path), index_path
    )

    _write_manifest(
        manifest_dir / "new.manifest.yaml",
        slug_goal="new outcome",
        supersedes=["old"],
        outcome=None,
    )

    assert outcome_index_is_stale(index_path, manifest_dir, project_root=tmp_path)


def test_outcome_index_detects_manifest_dir_and_project_root_mismatch(tmp_path: Path):
    from maid_runner.core.outcomes import (
        build_outcome_index,
        outcome_index_is_stale,
        write_outcome_index,
    )

    manifest_dir = tmp_path / "manifests"
    other_manifest_dir = tmp_path / "other-manifests"
    other_root = tmp_path / "other-root"
    manifest_dir.mkdir()
    other_manifest_dir.mkdir()
    other_root.mkdir()
    _write_manifest(manifest_dir / "completed.manifest.yaml")
    index_path = tmp_path / "outcomes.json"
    write_outcome_index(
        build_outcome_index(manifest_dir, project_root=tmp_path), index_path
    )

    assert outcome_index_is_stale(index_path, other_manifest_dir, project_root=tmp_path)
    assert outcome_index_is_stale(index_path, manifest_dir, project_root=other_root)


def test_read_outcome_index_fails_for_malformed_index_data(tmp_path: Path):
    from maid_runner.core.outcomes import read_outcome_index

    index_path = tmp_path / "outcomes.json"
    index_path.write_text('{"schema_version": "999", "records": []}\n')

    with pytest.raises(ValueError, match=str(index_path)):
        read_outcome_index(index_path)


def test_read_outcome_index_fails_for_unsupported_record_status(tmp_path: Path):
    from maid_runner.core.outcomes import build_outcome_index, read_outcome_index
    from maid_runner.core.outcomes import write_outcome_index

    manifest_dir = tmp_path / "manifests"
    manifest_dir.mkdir()
    _write_manifest(manifest_dir / "completed.manifest.yaml")
    index_path = tmp_path / "outcomes.json"
    write_outcome_index(
        build_outcome_index(manifest_dir, project_root=tmp_path), index_path
    )
    payload = json.loads(index_path.read_text())
    payload["records"][0]["status"] = "done"
    index_path.write_text(json.dumps(payload))

    with pytest.raises(ValueError, match="done"):
        read_outcome_index(index_path)


def test_build_outcome_index_fails_for_malformed_outcome(tmp_path: Path):
    from maid_runner.core.outcomes import build_outcome_index

    manifest_dir = tmp_path / "manifests"
    manifest_dir.mkdir()
    _write_manifest(manifest_dir / "bad.manifest.yaml", outcome_status="done")

    with pytest.raises(Exception, match="bad.manifest.yaml"):
        build_outcome_index(manifest_dir, project_root=tmp_path)


def _write_manifest(
    path: Path,
    *,
    slug_goal: str = "completed outcome",
    outcome_status: str = "completed",
    metadata_status: str | None = None,
    supersedes: list[str] | None = None,
    outcome: dict | None | bool = True,
) -> None:
    slug = path.name.removesuffix(".manifest.yaml")
    metadata = {"tags": ["outcome", "learning"], "priority": "high"}
    if metadata_status is not None:
        metadata["status"] = metadata_status
    data = {
        "schema": "2",
        "goal": slug_goal,
        "type": "feature",
        "created": "2026-05-30",
        "metadata": metadata,
        "files": {
            "create": [
                {
                    "path": f"src/{slug}.py",
                    "artifacts": [
                        {"kind": "function", "name": f"{slug.replace('-', '_')}_task"}
                    ],
                }
            ],
            "read": [f"tests/test_{slug}.py"],
        },
        "validate": [
            f"uv run python -m pytest -q tests/test_{slug}.py",
        ],
    }
    if supersedes:
        data["supersedes"] = supersedes
    if outcome is True:
        data["outcome"] = {
            "status": outcome_status,
            "summary": f"{slug} implementation completed.",
            "rationale": "Implementation review accepted the manifest scope.",
            "lessons": [
                {
                    "lesson_type": "testing",
                    "summary": "Focused behavioral tests make Outcome learning traceable.",
                    "tags": ["outcome"],
                    "paths": [f"src/{slug}.py"],
                }
            ],
            "review_notes": [
                {
                    "source": "implementation-review",
                    "severity": "info",
                    "summary": "Ready after review.",
                }
            ],
            "validation": [
                {
                    "command": ["uv", "run", "maid", "test"],
                    "status": "passed",
                    "summary": "Declared validation passed.",
                }
            ],
            "completed_at": "2026-05-31T01:02:03Z",
        }
    elif isinstance(outcome, dict):
        data["outcome"] = outcome
    path.write_text(yaml.safe_dump(data, sort_keys=False))
