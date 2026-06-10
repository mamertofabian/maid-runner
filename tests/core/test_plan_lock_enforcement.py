"""Behavioral tests for enforcing plan locks during verification."""

from __future__ import annotations

import json
from pathlib import Path

from maid_runner.core.chain import ManifestChain
from maid_runner.core.plan_lock import (
    PlanLock,
    create_plan_lock,
    default_plan_lock_path,
    enforce_plan_locks,
    revise_plan_lock,
)
from maid_runner.core.result import ErrorCode


def _write_project(tmp_path: Path) -> Path:
    (tmp_path / "manifests").mkdir()
    (tmp_path / "src").mkdir()
    (tmp_path / "tests").mkdir()
    (tmp_path / "src" / "demo.py").write_text(
        "def demo() -> int:\n    value = 1\n    return value\n\n"
        "def extra_demo() -> int:\n    value = 2\n    return value\n"
    )
    (tmp_path / "tests" / "test_demo.py").write_text(
        "from src.demo import demo\n\n\ndef test_demo_contract():\n"
        "    assert demo() == 1\n"
    )
    manifest_path = tmp_path / "manifests" / "demo-task.manifest.yaml"
    manifest_path.write_text(_manifest_text())
    return manifest_path


def _manifest_text(
    extra_artifact: str = "",
    read_line: str = "    - tests/test_demo.py\n",
) -> str:
    return f"""schema: "2"
goal: "Demo task"
type: feature
created: "2026-06-10T00:00:00Z"
files:
  create:
    - path: src/demo.py
      artifacts:
        - kind: function
          name: demo
          returns: int
{extra_artifact}  read:
{read_line}validate:
  - python -m pytest -q tests/test_demo.py
"""


def _chain(tmp_path: Path) -> ManifestChain:
    return ManifestChain(tmp_path / "manifests", tmp_path)


def _lock(manifest_path: Path, project_root: Path) -> Path:
    lock = create_plan_lock(manifest_path, project_root)
    lock_path = default_plan_lock_path(project_root, "demo-task")
    lock.save(lock_path)
    return lock_path


def _codes(errors) -> list[ErrorCode]:
    return [error.code for error in errors]


def test_no_enforcement_flags_return_no_errors_for_unlocked_manifest(
    tmp_path: Path,
) -> None:
    _write_project(tmp_path)

    errors = enforce_plan_locks(
        _chain(tmp_path),
        tmp_path,
        require_plan_lock=False,
        require_red_evidence=False,
    )

    assert errors == ()


def test_require_plan_lock_reports_missing_lock(tmp_path: Path) -> None:
    _write_project(tmp_path)

    errors = enforce_plan_locks(
        _chain(tmp_path),
        tmp_path,
        require_plan_lock=True,
        require_red_evidence=False,
    )

    assert _codes(errors) == [ErrorCode.PLAN_LOCK_MISSING]


def test_require_red_evidence_does_not_report_missing_lock_without_lock_scope(
    tmp_path: Path,
) -> None:
    _write_project(tmp_path)

    errors = enforce_plan_locks(
        _chain(tmp_path),
        tmp_path,
        require_plan_lock=False,
        require_red_evidence=True,
    )

    assert errors == ()


def test_behavioral_test_modified_after_lock_reports_e701(tmp_path: Path) -> None:
    manifest_path = _write_project(tmp_path)
    _lock(manifest_path, tmp_path)
    (tmp_path / "tests" / "test_demo.py").write_text(
        "from src.demo import demo\n\n\ndef test_demo_contract():\n"
        "    demo()\n    assert True  # weakened after approval\n"
    )

    errors = enforce_plan_locks(
        _chain(tmp_path),
        tmp_path,
        require_plan_lock=True,
        require_red_evidence=False,
    )

    assert _codes(errors) == [ErrorCode.BEHAVIORAL_TEST_MODIFIED_AFTER_LOCK]


def test_removed_declared_artifact_after_lock_reports_e702(tmp_path: Path) -> None:
    manifest_path = _write_project(tmp_path)
    manifest_path.write_text(
        _manifest_text(
            extra_artifact=(
                "        - kind: function\n"
                "          name: extra_demo\n"
                "          returns: int\n"
            )
        )
    )
    _lock(manifest_path, tmp_path)
    manifest_path.write_text(_manifest_text())

    errors = enforce_plan_locks(
        _chain(tmp_path),
        tmp_path,
        require_plan_lock=True,
        require_red_evidence=False,
    )

    assert _codes(errors) == [ErrorCode.MANIFEST_CONTRACT_WEAKENED_AFTER_LOCK]


def test_removed_artifact_metadata_after_lock_reports_e702(tmp_path: Path) -> None:
    manifest_path = _write_project(tmp_path)
    _lock(manifest_path, tmp_path)
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
  read:
    - tests/test_demo.py
validate:
  - python -m pytest -q tests/test_demo.py
"""
    )

    errors = enforce_plan_locks(
        _chain(tmp_path),
        tmp_path,
        require_plan_lock=True,
        require_red_evidence=False,
    )

    assert _codes(errors) == [ErrorCode.MANIFEST_CONTRACT_WEAKENED_AFTER_LOCK]
    assert "declared artifacts shrank" in errors[0].message


def test_legacy_lock_without_contract_snapshot_fails_closed_on_manifest_change(
    tmp_path: Path,
) -> None:
    manifest_path = _write_project(tmp_path)
    manifest_path.write_text(
        _manifest_text(
            extra_artifact=(
                "        - kind: function\n"
                "          name: extra_demo\n"
                "          returns: int\n"
            )
        )
    )
    lock_path = _lock(manifest_path, tmp_path)
    payload = json.loads(lock_path.read_text())
    payload.pop("_manifest_contract")
    lock_path.write_text(json.dumps(payload))
    manifest_path.write_text(_manifest_text())

    errors = enforce_plan_locks(
        _chain(tmp_path),
        tmp_path,
        require_plan_lock=True,
        require_red_evidence=False,
    )

    assert _codes(errors) == [ErrorCode.MANIFEST_CONTRACT_WEAKENED_AFTER_LOCK]
    assert "legacy plan lock" in errors[0].message


def test_additive_manifest_edit_after_lock_is_allowed(tmp_path: Path) -> None:
    manifest_path = _write_project(tmp_path)
    _lock(manifest_path, tmp_path)
    manifest_path.write_text(
        _manifest_text(
            extra_artifact=(
                "        - kind: function\n"
                "          name: extra_demo\n"
                "          returns: int\n"
            )
        )
    )

    errors = enforce_plan_locks(
        _chain(tmp_path),
        tmp_path,
        require_plan_lock=True,
        require_red_evidence=False,
    )

    assert errors == ()


def test_revise_with_reason_clears_behavioral_test_mismatch(tmp_path: Path) -> None:
    manifest_path = _write_project(tmp_path)
    lock_path = _lock(manifest_path, tmp_path)
    (tmp_path / "tests" / "test_demo.py").write_text(
        "from src.demo import demo\n\n\ndef test_demo_contract():\n"
        "    assert demo() == 1\n    assert demo() != 2\n"
    )
    revised = revise_plan_lock(
        PlanLock.load(lock_path),
        manifest_path,
        tmp_path,
        "strengthen approved test",
    )
    revised.save(lock_path)

    errors = enforce_plan_locks(
        _chain(tmp_path),
        tmp_path,
        require_plan_lock=True,
        require_red_evidence=False,
    )

    assert errors == ()


def test_lock_with_missing_recorded_manifest_path_reports_e703(tmp_path: Path) -> None:
    manifest_path = _write_project(tmp_path)
    lock_path = _lock(manifest_path, tmp_path)
    payload = json.loads(lock_path.read_text())
    payload["manifest_path"] = "manifests/missing-task.manifest.yaml"
    lock_path.write_text(json.dumps(payload))

    errors = enforce_plan_locks(
        _chain(tmp_path),
        tmp_path,
        require_plan_lock=True,
        require_red_evidence=False,
    )

    assert _codes(errors) == [ErrorCode.PLAN_LOCK_STALE]


def test_require_red_evidence_reports_missing_red_evidence(tmp_path: Path) -> None:
    manifest_path = _write_project(tmp_path)
    _lock(manifest_path, tmp_path)

    errors = enforce_plan_locks(
        _chain(tmp_path),
        tmp_path,
        require_plan_lock=False,
        require_red_evidence=True,
    )

    assert _codes(errors) == [ErrorCode.RED_PHASE_EVIDENCE_MISSING]


def test_require_red_evidence_reports_invalid_red_evidence(tmp_path: Path) -> None:
    manifest_path = _write_project(tmp_path)
    lock_path = _lock(manifest_path, tmp_path)
    payload = json.loads(lock_path.read_text())
    payload["red_evidence"] = {
        "red": False,
        "commands": [
            {
                "command": "python -m pytest -q tests/test_demo.py",
                "exit_code": 2,
                "output_tail": "collection error",
                "classification": "invalid",
            }
        ],
        "captured_at": "2026-06-10T00:00:00Z",
    }
    lock_path.write_text(json.dumps(payload))

    errors = enforce_plan_locks(
        _chain(tmp_path),
        tmp_path,
        require_plan_lock=False,
        require_red_evidence=True,
    )

    assert _codes(errors) == [ErrorCode.RED_PHASE_EVIDENCE_INVALID]


def test_require_red_evidence_accepts_valid_red_evidence(tmp_path: Path) -> None:
    manifest_path = _write_project(tmp_path)
    lock_path = _lock(manifest_path, tmp_path)
    payload = json.loads(lock_path.read_text())
    payload["red_evidence"] = {
        "red": True,
        "commands": [
            {
                "command": "python -m pytest -q tests/test_demo.py",
                "exit_code": 1,
                "output_tail": "assertion failed",
                "classification": "red",
            }
        ],
        "captured_at": "2026-06-10T00:00:00Z",
    }
    lock_path.write_text(json.dumps(payload))

    errors = enforce_plan_locks(
        _chain(tmp_path),
        tmp_path,
        require_plan_lock=False,
        require_red_evidence=True,
    )

    assert errors == ()
