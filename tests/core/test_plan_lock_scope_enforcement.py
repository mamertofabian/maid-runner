"""Behavioral tests for task-window scoping of plan-lock enforcement."""

from __future__ import annotations

import json
from pathlib import Path

from maid_runner.core.chain import ManifestChain
from maid_runner.core.plan_lock import (
    create_plan_lock,
    default_plan_lock_path,
    enforce_plan_locks,
)
from maid_runner.core.result import ErrorCode


OLD_MANIFEST = "manifests/old-task.manifest.yaml"
NEW_MANIFEST = "manifests/new-task.manifest.yaml"


def _manifest_text(module: str, function: str, created: str) -> str:
    return f"""schema: "2"
goal: "Task for {module}"
type: feature
created: "{created}"
files:
  create:
    - path: src/{module}.py
      artifacts:
        - kind: function
          name: {function}
          returns: int
  read:
    - tests/test_{module}.py
validate:
  - python -m pytest -q tests/test_{module}.py
"""


def _write_module(tmp_path: Path, module: str, function: str) -> None:
    (tmp_path / "src" / f"{module}.py").write_text(
        f"def {function}() -> int:\n    value = 1\n    return value\n"
    )
    (tmp_path / "tests" / f"test_{module}.py").write_text(
        f"from src.{module} import {function}\n\n\n"
        f"def test_{function}_contract():\n    assert {function}() == 1\n"
    )


def _write_two_manifest_project(tmp_path: Path) -> tuple[Path, Path]:
    """One historical manifest plus one task-window manifest, both unlocked."""
    (tmp_path / "manifests").mkdir()
    (tmp_path / "src").mkdir()
    (tmp_path / "tests").mkdir()
    _write_module(tmp_path, "old", "old_demo")
    _write_module(tmp_path, "new", "new_demo")
    old_path = tmp_path / OLD_MANIFEST
    old_path.write_text(_manifest_text("old", "old_demo", "2026-06-01T00:00:00Z"))
    new_path = tmp_path / NEW_MANIFEST
    new_path.write_text(_manifest_text("new", "new_demo", "2026-06-11T00:00:00Z"))
    return old_path, new_path


def _chain(tmp_path: Path) -> ManifestChain:
    return ManifestChain(tmp_path / "manifests", tmp_path)


def _lock(manifest_path: Path, project_root: Path, slug: str) -> Path:
    lock = create_plan_lock(manifest_path, project_root)
    lock_path = default_plan_lock_path(project_root, slug)
    lock.save(lock_path)
    return lock_path


def _codes(errors) -> list[ErrorCode]:
    return [error.code for error in errors]


def _locations(errors) -> list[str]:
    return [str(error.location.file) for error in errors]


def test_changed_paths_scope_suppresses_e700_for_untouched_manifests(
    tmp_path: Path,
) -> None:
    _write_two_manifest_project(tmp_path)

    errors = enforce_plan_locks(
        _chain(tmp_path),
        tmp_path,
        require_plan_lock=True,
        require_red_evidence=False,
        changed_paths=[NEW_MANIFEST],
    )

    assert _codes(errors) == [ErrorCode.PLAN_LOCK_MISSING]
    assert _locations(errors) == [NEW_MANIFEST]


def test_empty_changed_paths_reports_no_requirement_errors(tmp_path: Path) -> None:
    _write_two_manifest_project(tmp_path)

    errors = enforce_plan_locks(
        _chain(tmp_path),
        tmp_path,
        require_plan_lock=True,
        require_red_evidence=True,
        changed_paths=[],
    )

    assert errors == ()


def test_none_changed_paths_preserves_full_scope_enforcement(tmp_path: Path) -> None:
    _write_two_manifest_project(tmp_path)

    errors = enforce_plan_locks(
        _chain(tmp_path),
        tmp_path,
        require_plan_lock=True,
        require_red_evidence=False,
        changed_paths=None,
    )

    assert _codes(errors) == [ErrorCode.PLAN_LOCK_MISSING, ErrorCode.PLAN_LOCK_MISSING]
    assert sorted(_locations(errors)) == [NEW_MANIFEST, OLD_MANIFEST]


def test_require_red_evidence_reports_e704_for_in_scope_manifest_without_lock(
    tmp_path: Path,
) -> None:
    _write_two_manifest_project(tmp_path)

    errors = enforce_plan_locks(
        _chain(tmp_path),
        tmp_path,
        require_plan_lock=False,
        require_red_evidence=True,
        changed_paths=[NEW_MANIFEST],
    )

    assert _codes(errors) == [ErrorCode.RED_PHASE_EVIDENCE_MISSING]
    assert _locations(errors) == [NEW_MANIFEST]


def test_both_flags_report_e700_and_e704_for_in_scope_manifest_without_lock(
    tmp_path: Path,
) -> None:
    _write_two_manifest_project(tmp_path)

    errors = enforce_plan_locks(
        _chain(tmp_path),
        tmp_path,
        require_plan_lock=True,
        require_red_evidence=True,
        changed_paths=[NEW_MANIFEST],
    )

    assert sorted(_codes(errors), key=lambda code: code.value) == [
        ErrorCode.PLAN_LOCK_MISSING,
        ErrorCode.RED_PHASE_EVIDENCE_MISSING,
    ]
    assert set(_locations(errors)) == {NEW_MANIFEST}


def test_out_of_scope_locked_manifest_with_tampered_test_still_fails_e701(
    tmp_path: Path,
) -> None:
    old_path, _ = _write_two_manifest_project(tmp_path)
    _lock(old_path, tmp_path, "old-task")
    (tmp_path / "tests" / "test_old.py").write_text(
        "from src.old import old_demo\n\n\ndef test_old_demo_contract():\n"
        "    old_demo()\n    assert True  # weakened after approval\n"
    )

    errors = enforce_plan_locks(
        _chain(tmp_path),
        tmp_path,
        require_plan_lock=True,
        require_red_evidence=False,
        changed_paths=[NEW_MANIFEST],
    )

    assert ErrorCode.BEHAVIORAL_TEST_MODIFIED_AFTER_LOCK in _codes(errors)


def test_out_of_scope_locked_manifest_with_null_evidence_passes_e704(
    tmp_path: Path,
) -> None:
    old_path, _ = _write_two_manifest_project(tmp_path)
    _lock(old_path, tmp_path, "old-task")

    errors = enforce_plan_locks(
        _chain(tmp_path),
        tmp_path,
        require_plan_lock=False,
        require_red_evidence=True,
        changed_paths=[NEW_MANIFEST],
    )

    assert ErrorCode.RED_PHASE_EVIDENCE_MISSING in _codes(errors)
    assert _locations(errors) == [NEW_MANIFEST]


def test_out_of_scope_locked_manifest_with_invalid_evidence_passes_e705(
    tmp_path: Path,
) -> None:
    old_path, _ = _write_two_manifest_project(tmp_path)
    lock_path = _lock(old_path, tmp_path, "old-task")
    payload = json.loads(lock_path.read_text())
    payload["red_evidence"] = {
        "red": False,
        "commands": [
            {
                "command": "python -m pytest -q tests/test_old.py",
                "exit_code": 2,
                "output_tail": "collection error",
                "classification": "invalid",
            }
        ],
        "captured_at": "2026-06-11T00:00:00Z",
    }
    lock_path.write_text(json.dumps(payload))

    errors = enforce_plan_locks(
        _chain(tmp_path),
        tmp_path,
        require_plan_lock=False,
        require_red_evidence=True,
        changed_paths=[NEW_MANIFEST],
    )

    assert ErrorCode.RED_PHASE_EVIDENCE_INVALID not in _codes(errors)
    assert _codes(errors) == [ErrorCode.RED_PHASE_EVIDENCE_MISSING]


def test_in_scope_locked_manifest_with_invalid_evidence_fails_e705(
    tmp_path: Path,
) -> None:
    _, new_path = _write_two_manifest_project(tmp_path)
    lock_path = _lock(new_path, tmp_path, "new-task")
    payload = json.loads(lock_path.read_text())
    payload["red_evidence"] = {
        "red": False,
        "commands": [
            {
                "command": "python -m pytest -q tests/test_new.py",
                "exit_code": 2,
                "output_tail": "collection error",
                "classification": "invalid",
            }
        ],
        "captured_at": "2026-06-11T00:00:00Z",
    }
    lock_path.write_text(json.dumps(payload))

    errors = enforce_plan_locks(
        _chain(tmp_path),
        tmp_path,
        require_plan_lock=False,
        require_red_evidence=True,
        changed_paths=[NEW_MANIFEST],
    )

    assert _codes(errors) == [ErrorCode.RED_PHASE_EVIDENCE_INVALID]


def test_corrupt_lock_reports_e706_regardless_of_scope(tmp_path: Path) -> None:
    _write_two_manifest_project(tmp_path)
    lock_path = default_plan_lock_path(tmp_path, "old-task")
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    lock_path.write_text("{not valid json")

    errors = enforce_plan_locks(
        _chain(tmp_path),
        tmp_path,
        require_plan_lock=False,
        require_red_evidence=True,
        changed_paths=[NEW_MANIFEST],
    )

    assert ErrorCode.PLAN_LOCK_UNREADABLE in _codes(errors)
    assert ErrorCode.PLAN_LOCK_STALE not in _codes(errors)


def test_corrupt_lock_message_names_unreadable_lock(tmp_path: Path) -> None:
    old_path, _ = _write_two_manifest_project(tmp_path)
    lock_path = _lock(old_path, tmp_path, "old-task")
    lock_path.write_text("{not valid json")

    errors = enforce_plan_locks(
        _chain(tmp_path),
        tmp_path,
        require_plan_lock=True,
        require_red_evidence=False,
        changed_paths=None,
    )

    unreadable = [
        error for error in errors if error.code == ErrorCode.PLAN_LOCK_UNREADABLE
    ]
    assert len(unreadable) == 1
    assert "PLAN_LOCK_UNREADABLE" in unreadable[0].message
