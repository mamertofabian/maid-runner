"""Behavioral tests for advisory manifest header backfill at agent gates."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from maid_runner.cli.commands.manifest import cmd_manifest
from maid_runner.cli.commands.plan import cmd_plan_lock, cmd_plan_revise
from maid_runner.core.manifest import MANIFEST_HEADER_COMMENT, prepend_manifest_header
from maid_runner.core.plan_lock import (
    PlanLock,
    compute_manifest_contract_hash,
    create_plan_lock,
    default_plan_lock_path,
)


_MANIFEST_BODY = """schema: "2"
goal: "Demo task"
type: feature
created: "2026-07-25T00:00:00Z"
files:
  create:
    - path: src/demo.py
      artifacts:
        - kind: function
          name: demo
  read:
    - tests/test_demo.py
validate:
  - python -m pytest -q tests/test_demo.py
"""

_TEST_BODY = "from src.demo import demo\n\n\ndef test_demo():\n    assert demo() == 1\n"


def _write_project(project_root: Path, *, headed: bool = False) -> Path:
    (project_root / "manifests").mkdir(parents=True, exist_ok=True)
    (project_root / "src").mkdir()
    (project_root / "src" / "demo.py").write_text("def demo():\n    return 1\n")
    (project_root / "tests").mkdir()
    (project_root / "tests" / "test_demo.py").write_text(_TEST_BODY)
    manifest_path = project_root / "manifests" / "demo-task.manifest.yaml"
    manifest_path.write_text(
        prepend_manifest_header(_MANIFEST_BODY) if headed else _MANIFEST_BODY
    )
    return manifest_path


def _lock_args(manifest_path: Path, project_root: Path) -> SimpleNamespace:
    return SimpleNamespace(
        plan_command="lock",
        manifest_path=str(manifest_path),
        project_root=str(project_root),
        no_run=True,
        json=False,
    )


def _revise_args(
    manifest_path: Path, project_root: Path, *, reason: str = "refresh lock"
) -> SimpleNamespace:
    return SimpleNamespace(
        plan_command="revise",
        manifest_path=str(manifest_path),
        project_root=str(project_root),
        reason=reason,
        no_run=True,
        json=False,
        preserve_red_evidence=False,
        stash_implementation=False,
        allow_sibling_dirty=False,
        test_only_green=False,
    )


def _promote_args(project_root: Path, draft_path: Path) -> argparse.Namespace:
    return argparse.Namespace(
        manifest_command="promote",
        manifest_path=str(draft_path),
        output_dir=str(project_root / "manifests"),
        project_root=str(project_root),
        no_run=True,
        json=False,
    )


def _write_draft(project_root: Path, *, headed: bool = False) -> Path:
    draft_dir = project_root / "manifests" / "drafts"
    draft_dir.mkdir(parents=True, exist_ok=True)
    (project_root / "tests").mkdir(exist_ok=True)
    (project_root / "tests" / "test_demo.py").write_text(_TEST_BODY)
    draft_path = draft_dir / "demo-task.manifest.yaml"
    body = "# draft-kind: implementation\n" + _MANIFEST_BODY
    draft_path.write_text(prepend_manifest_header(body) if headed else body)
    return draft_path


class TestManifestHeaderBackfillHelper:
    def test_backfill_manifest_header_updates_missing_banner(self, tmp_path: Path):
        import maid_runner.core.manifest as manifest_mod

        manifest_path = tmp_path / "demo.manifest.yaml"
        manifest_path.write_text(_MANIFEST_BODY)

        assert manifest_mod.backfill_manifest_header(manifest_path) is True

        assert manifest_path.read_text().startswith(MANIFEST_HEADER_COMMENT)

    def test_backfill_manifest_header_leaves_headed_file_unchanged(
        self, tmp_path: Path
    ):
        import maid_runner.core.manifest as manifest_mod

        manifest_path = tmp_path / "demo.manifest.yaml"
        manifest_path.write_text(prepend_manifest_header(_MANIFEST_BODY))
        original = manifest_path.read_bytes()

        assert manifest_mod.backfill_manifest_header(manifest_path) is False

        assert manifest_path.read_bytes() == original

    def test_backfill_manifest_header_preserves_original_on_write_failure(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ):
        import maid_runner.core.manifest as manifest_mod

        manifest_path = tmp_path / "demo.manifest.yaml"
        manifest_path.write_text(_MANIFEST_BODY)
        original = manifest_path.read_text()
        real_write_text = Path.write_text

        def fail_after_partial_write(self: Path, data: str, *args, **kwargs):
            real_write_text(self, "partial write")
            raise OSError("disk full")

        monkeypatch.setattr(Path, "write_text", fail_after_partial_write)

        with pytest.raises(OSError):
            manifest_mod.backfill_manifest_header(manifest_path)

        assert manifest_path.read_text() == original


class TestPlanGateManifestHeaderBackfill:
    def test_plan_lock_backfills_missing_manifest_header(
        self, tmp_path: Path, capsys: pytest.CaptureFixture
    ):
        manifest_path = _write_project(tmp_path)
        pre_backfill_hash = compute_manifest_contract_hash(manifest_path)

        exit_code = cmd_plan_lock(_lock_args(manifest_path, tmp_path))

        assert exit_code == 0
        assert manifest_path.read_text().startswith(MANIFEST_HEADER_COMMENT)
        lock = PlanLock.load(default_plan_lock_path(tmp_path, "demo-task"))
        assert lock.manifest_hash == pre_backfill_hash

    def test_plan_lock_on_headed_manifest_leaves_bytes_unchanged(
        self, tmp_path: Path, capsys: pytest.CaptureFixture
    ):
        manifest_path = _write_project(tmp_path, headed=True)
        original = manifest_path.read_bytes()

        exit_code = cmd_plan_lock(_lock_args(manifest_path, tmp_path))

        assert exit_code == 0
        assert manifest_path.read_bytes() == original

    def test_plan_revise_backfills_missing_manifest_header(
        self, tmp_path: Path, capsys: pytest.CaptureFixture
    ):
        manifest_path = _write_project(tmp_path)
        lock_path = default_plan_lock_path(tmp_path, "demo-task")
        create_plan_lock(manifest_path, tmp_path).save(lock_path)

        exit_code = cmd_plan_revise(_revise_args(manifest_path, tmp_path))

        assert exit_code == 0
        assert manifest_path.read_text().startswith(MANIFEST_HEADER_COMMENT)

    def test_plan_revise_test_only_green_backfills_missing_manifest_header(
        self,
        tmp_path: Path,
        capsys: pytest.CaptureFixture,
        monkeypatch: pytest.MonkeyPatch,
    ):
        import maid_runner.cli.commands.plan as plan_cmd

        manifest_path = _write_project(tmp_path)
        lock_path = default_plan_lock_path(tmp_path, "demo-task")
        create_plan_lock(manifest_path, tmp_path).save(lock_path)
        args = _revise_args(manifest_path, tmp_path)
        args.no_run = False
        args.test_only_green = True

        monkeypatch.setattr(
            plan_cmd,
            "_cmd_plan_revise_test_only_green",
            lambda **kwargs: 0,
        )

        exit_code = cmd_plan_revise(args)

        assert exit_code == 0
        assert manifest_path.read_text().startswith(MANIFEST_HEADER_COMMENT)

    def test_plan_revise_stash_implementation_backfills_missing_manifest_header(
        self,
        tmp_path: Path,
        capsys: pytest.CaptureFixture,
        monkeypatch: pytest.MonkeyPatch,
    ):
        import maid_runner.cli.commands.plan as plan_cmd

        manifest_path = _write_project(tmp_path)
        lock_path = default_plan_lock_path(tmp_path, "demo-task")
        create_plan_lock(manifest_path, tmp_path).save(lock_path)
        args = _revise_args(manifest_path, tmp_path)
        args.no_run = False
        args.stash_implementation = True

        monkeypatch.setattr(
            plan_cmd,
            "_cmd_plan_revise_with_stashed_implementation",
            lambda **kwargs: 0,
        )

        exit_code = cmd_plan_revise(args)

        assert exit_code == 0
        assert manifest_path.read_text().startswith(MANIFEST_HEADER_COMMENT)

    def test_plan_lock_backfill_failure_is_advisory(
        self,
        tmp_path: Path,
        capsys: pytest.CaptureFixture,
        monkeypatch: pytest.MonkeyPatch,
    ):
        import maid_runner.cli.commands.plan as plan_cmd

        manifest_path = _write_project(tmp_path)

        def fail_backfill(path: Path) -> bool:
            raise OSError("read-only checkout")

        monkeypatch.setattr(
            plan_cmd, "backfill_manifest_header", fail_backfill, raising=False
        )

        exit_code = cmd_plan_lock(_lock_args(manifest_path, tmp_path))

        output = capsys.readouterr()
        assert exit_code == 0
        assert default_plan_lock_path(tmp_path, "demo-task").exists()
        assert str(manifest_path) in output.err
        assert "advisory" in output.err.lower()


class TestPromoteManifestHeaderBackfill:
    def test_manifest_promote_backfills_header_and_keeps_draft_marker_line_one(
        self, tmp_path: Path, capsys: pytest.CaptureFixture
    ):
        draft_path = _write_draft(tmp_path)
        lock_path = default_plan_lock_path(tmp_path, "demo-task")
        create_plan_lock(draft_path, tmp_path).save(lock_path)

        exit_code = cmd_manifest(_promote_args(tmp_path, draft_path))

        assert exit_code == 0
        promoted = tmp_path / "manifests" / "demo-task.manifest.yaml"
        lines = promoted.read_text().splitlines()
        assert lines[0] == "# draft-kind: implementation"
        assert lines[1] == MANIFEST_HEADER_COMMENT.splitlines()[0]

        lock = json.loads(lock_path.read_text())
        assert lock["manifest_path"] == "manifests/demo-task.manifest.yaml"

    def test_manifest_promote_backfill_failure_is_advisory(
        self,
        tmp_path: Path,
        capsys: pytest.CaptureFixture,
        monkeypatch: pytest.MonkeyPatch,
    ):
        import maid_runner.cli.commands.manifest as manifest_cmd

        draft_path = _write_draft(tmp_path)

        def fail_backfill(path: Path) -> bool:
            raise OSError("read-only checkout")

        monkeypatch.setattr(
            manifest_cmd, "backfill_manifest_header", fail_backfill, raising=False
        )

        exit_code = cmd_manifest(_promote_args(tmp_path, draft_path))

        promoted = tmp_path / "manifests" / "demo-task.manifest.yaml"
        output = capsys.readouterr()
        assert exit_code == 0
        assert promoted.exists()
        assert str(promoted) in output.err
        assert "advisory" in output.err.lower()
