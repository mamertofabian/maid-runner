"""Behavioral tests for active-task manifest resolution."""

from __future__ import annotations

from pathlib import Path

import pytest

from maid_runner.core.active_task import (
    ActiveManifestStatus,
    ActiveTaskError,
    get_active_manifest_status,
    resolve_active_manifest,
    start_active_task,
    stop_active_task,
)


def _write_manifest(project_root: Path, relative_path: str) -> Path:
    path = project_root / relative_path
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        """schema: "2"
goal: "Demo task"
type: feature
created: "2026-06-17T00:00:00Z"
files:
  read:
    - README.md
validate:
  - python -m pytest -q tests/test_demo.py
"""
    )
    return path


def test_start_active_task_writes_single_repo_relative_manifest_path(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("MAID_ACTIVE_MANIFEST", raising=False)
    _write_manifest(tmp_path, "manifests/demo.manifest.yaml")

    stored_path = start_active_task("manifests/demo.manifest.yaml", tmp_path)

    assert stored_path == "manifests/demo.manifest.yaml"
    assert (tmp_path / ".maid" / "active-manifest").read_text() == (
        "manifests/demo.manifest.yaml\n"
    )
    status = get_active_manifest_status(tmp_path)
    assert isinstance(status, ActiveManifestStatus)
    assert status.path == "manifests/demo.manifest.yaml"
    assert status.source == "file"
    assert resolve_active_manifest(tmp_path) == "manifests/demo.manifest.yaml"


@pytest.mark.parametrize(
    "manifest_path",
    [
        "/tmp/outside.manifest.yaml",
        "../outside.manifest.yaml",
        "manifests/missing.manifest.yaml",
    ],
)
def test_start_active_task_rejects_escaping_or_nonexistent_paths(
    tmp_path: Path, manifest_path: str
) -> None:
    _write_manifest(tmp_path, "manifests/demo.manifest.yaml")

    with pytest.raises(ActiveTaskError):
        start_active_task(manifest_path, tmp_path)

    assert not (tmp_path / ".maid" / "active-manifest").exists()


def test_stop_active_task_removes_file_and_is_idempotent(tmp_path: Path) -> None:
    _write_manifest(tmp_path, "manifests/demo.manifest.yaml")
    start_active_task("manifests/demo.manifest.yaml", tmp_path)

    assert stop_active_task(tmp_path) is True
    assert stop_active_task(tmp_path) is False
    assert not (tmp_path / ".maid" / "active-manifest").exists()


def test_environment_variable_overrides_file_status(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _write_manifest(tmp_path, "manifests/file-task.manifest.yaml")
    start_active_task("manifests/file-task.manifest.yaml", tmp_path)
    monkeypatch.setenv("MAID_ACTIVE_MANIFEST", "manifests/env-task.manifest.yaml")

    status = get_active_manifest_status(tmp_path)

    assert status.path == "manifests/env-task.manifest.yaml"
    assert status.source == "env"
    assert resolve_active_manifest(tmp_path) == "manifests/env-task.manifest.yaml"


def test_status_reports_no_active_task_when_env_and_file_are_absent(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("MAID_ACTIVE_MANIFEST", raising=False)

    status = get_active_manifest_status(tmp_path)

    assert status.path is None
    assert status.source == "none"
    assert resolve_active_manifest(tmp_path) is None
