"""Behavioral tests for the tamper-evident plan-lock data model."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from maid_runner.core.plan_lock import (
    PlanLock,
    PlanLockRevision,
    create_plan_lock,
    default_plan_lock_path,
    revise_plan_lock,
)


def _write_project(tmp_path: Path) -> Path:
    """Create a throwaway MAID project; return the manifest path."""
    (tmp_path / "manifests").mkdir()
    (tmp_path / "tests").mkdir()
    (tmp_path / "docs").mkdir()
    (tmp_path / "tests" / "test_demo.py").write_text(
        "from src.demo import demo\n\n\ndef test_demo():\n    assert demo() == 1\n"
    )
    (tmp_path / "tests" / "test_demo_extra.py").write_text(
        "def test_extra():\n    assert True\n"
    )
    (tmp_path / "docs" / "notes.md").write_text("notes\n")
    manifest_path = tmp_path / "manifests" / "demo-task.manifest.yaml"
    manifest_path.write_text(
        """schema: "2"
goal: "Demo task"
type: feature
created: "2026-06-10T00:00:00Z"
files:
  create:
    - path: src/demo.py
      artifacts:
        - kind: function
          name: demo
  edit:
    - path: tests/test_demo_extra.py
      artifacts:
        - kind: function
          name: test_extra
  read:
    - tests/test_demo.py
    - docs/notes.md
validate:
  - python -m pytest -q tests/test_demo.py
"""
    )
    return manifest_path


class TestDefaultPlanLockPath:
    def test_path_is_under_maid_plan_locks(self, tmp_path: Path) -> None:
        path = default_plan_lock_path(tmp_path, "demo-task")
        assert path == tmp_path / ".maid" / "plan-locks" / "demo-task.lock.json"


class TestCreatePlanLock:
    def test_lock_records_manifest_and_test_hashes(self, tmp_path: Path) -> None:
        manifest_path = _write_project(tmp_path)

        lock = create_plan_lock(manifest_path, tmp_path)

        assert lock.manifest_path == "manifests/demo-task.manifest.yaml"
        assert lock.manifest_hash.startswith("sha256:")
        assert set(lock.test_hashes) == {
            "tests/test_demo.py",
            "tests/test_demo_extra.py",
        }
        assert all(h.startswith("sha256:") for h in lock.test_hashes.values())
        assert lock.revision == 1
        assert lock.revisions == ()
        assert lock.red_evidence is None
        assert lock.created_at

    def test_non_test_read_entries_are_not_hashed(self, tmp_path: Path) -> None:
        manifest_path = _write_project(tmp_path)

        lock = create_plan_lock(manifest_path, tmp_path)

        assert "docs/notes.md" not in lock.test_hashes
        assert "src/demo.py" not in lock.test_hashes

    def test_hashes_are_stable_across_runs(self, tmp_path: Path) -> None:
        manifest_path = _write_project(tmp_path)

        first = create_plan_lock(manifest_path, tmp_path)
        second = create_plan_lock(manifest_path, tmp_path)

        assert first.manifest_hash == second.manifest_hash
        assert first.test_hashes == second.test_hashes

    def test_missing_behavioral_test_file_fails(self, tmp_path: Path) -> None:
        manifest_path = _write_project(tmp_path)
        (tmp_path / "tests" / "test_demo.py").unlink()

        with pytest.raises(FileNotFoundError):
            create_plan_lock(manifest_path, tmp_path)


class TestSaveAndLoad:
    def test_round_trip_preserves_lock_record(self, tmp_path: Path) -> None:
        manifest_path = _write_project(tmp_path)
        lock = create_plan_lock(manifest_path, tmp_path)
        lock_path = default_plan_lock_path(tmp_path, "demo-task")

        lock.save(lock_path)
        loaded = PlanLock.load(lock_path)

        assert loaded == lock

    def test_round_trip_preserves_revision_history(self, tmp_path: Path) -> None:
        manifest_path = _write_project(tmp_path)
        lock = create_plan_lock(manifest_path, tmp_path)
        revised = revise_plan_lock(lock, manifest_path, tmp_path, "tighten contract")
        lock_path = default_plan_lock_path(tmp_path, "demo-task")

        revised.save(lock_path)
        loaded = PlanLock.load(lock_path)

        assert loaded == revised
        assert isinstance(loaded.revisions[0], PlanLockRevision)

    def test_load_missing_file_raises(self, tmp_path: Path) -> None:
        with pytest.raises(FileNotFoundError):
            PlanLock.load(tmp_path / ".maid" / "plan-locks" / "absent.lock.json")

    def test_load_corrupt_lock_fails_closed(self, tmp_path: Path) -> None:
        lock_path = tmp_path / "broken.lock.json"
        lock_path.write_text("{not json")

        with pytest.raises(Exception, match="broken.lock.json"):
            PlanLock.load(lock_path)

    def test_load_malformed_payload_fails_closed(self, tmp_path: Path) -> None:
        lock_path = tmp_path / "malformed.lock.json"
        lock_path.write_text(json.dumps(["not", "an", "object"]))

        with pytest.raises(Exception, match="malformed.lock.json"):
            PlanLock.load(lock_path)


class TestRevisePlanLock:
    def test_revise_appends_history_and_increments_revision(
        self, tmp_path: Path
    ) -> None:
        manifest_path = _write_project(tmp_path)
        original = create_plan_lock(manifest_path, tmp_path)
        (tmp_path / "tests" / "test_demo.py").write_text(
            "from src.demo import demo\n\n\ndef test_demo():\n"
            "    assert demo() == 1\n    assert demo() != 2\n"
        )

        revised = revise_plan_lock(
            original, manifest_path, tmp_path, "strengthen demo assertions"
        )

        assert revised.revision == 2
        assert len(revised.revisions) == 1
        entry = revised.revisions[0]
        assert entry.prior_manifest_hash == original.manifest_hash
        assert entry.prior_test_hashes == original.test_hashes
        assert entry.reason == "strengthen demo assertions"
        assert entry.revised_at
        assert (
            revised.test_hashes["tests/test_demo.py"]
            != original.test_hashes["tests/test_demo.py"]
        )
        assert revised.created_at == original.created_at

    def test_revise_rejects_empty_reason(self, tmp_path: Path) -> None:
        manifest_path = _write_project(tmp_path)
        lock = create_plan_lock(manifest_path, tmp_path)

        with pytest.raises(ValueError):
            revise_plan_lock(lock, manifest_path, tmp_path, "")

    def test_revise_rejects_whitespace_reason(self, tmp_path: Path) -> None:
        manifest_path = _write_project(tmp_path)
        lock = create_plan_lock(manifest_path, tmp_path)

        with pytest.raises(ValueError):
            revise_plan_lock(lock, manifest_path, tmp_path, "   ")

    def test_second_revision_preserves_prior_history(self, tmp_path: Path) -> None:
        manifest_path = _write_project(tmp_path)
        lock = create_plan_lock(manifest_path, tmp_path)
        first = revise_plan_lock(lock, manifest_path, tmp_path, "first revision")

        second = revise_plan_lock(first, manifest_path, tmp_path, "second revision")

        assert second.revision == 3
        assert [e.reason for e in second.revisions] == [
            "first revision",
            "second revision",
        ]
