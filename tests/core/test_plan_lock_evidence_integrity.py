"""Behavioral tests for plan-lock red-evidence command integrity (E707).

Covers the detector for incident 20260611-133856: red-phase evidence whose
command strings do not match the validate commands snapshotted into the lock
is machine-detectable evidence splicing and must fail closed with E707.
"""

from __future__ import annotations

import json
from pathlib import Path

from maid_runner.core.chain import ManifestChain
from maid_runner.core.plan_lock import (
    PlanLock,
    create_plan_lock,
    default_plan_lock_path,
    enforce_plan_locks,
)
from maid_runner.core.result import ErrorCode

_DEMO_VALIDATE = "python -m pytest -q tests/test_demo.py"


def _manifest_text(validate_lines: list[str]) -> str:
    validate_block = "".join(f"  - {line}\n" for line in validate_lines)
    return f"""schema: "2"
goal: "Demo task"
type: feature
created: "2026-06-12T00:00:00Z"
files:
  create:
    - path: src/demo.py
      artifacts:
        - kind: function
          name: demo
          returns: int
  read:
    - tests/test_demo.py
validate:
{validate_block}"""


def _write_project(tmp_path: Path, validate_lines: list[str] | None = None) -> Path:
    (tmp_path / "manifests").mkdir()
    (tmp_path / "src").mkdir()
    (tmp_path / "tests").mkdir()
    (tmp_path / "src" / "demo.py").write_text(
        "def demo() -> int:\n    value = 1\n    return value\n"
    )
    (tmp_path / "tests" / "test_demo.py").write_text(
        "from src.demo import demo\n\n\ndef test_demo_contract():\n"
        "    assert demo() == 1\n"
    )
    manifest_path = tmp_path / "manifests" / "demo-task.manifest.yaml"
    manifest_path.write_text(_manifest_text(validate_lines or [_DEMO_VALIDATE]))
    return manifest_path


def _chain(tmp_path: Path) -> ManifestChain:
    return ManifestChain(tmp_path / "manifests", tmp_path)


def _lock(manifest_path: Path, project_root: Path) -> Path:
    lock = create_plan_lock(manifest_path, project_root)
    lock_path = default_plan_lock_path(project_root, "demo-task")
    lock.save(lock_path)
    return lock_path


def _splice_red_evidence(lock_path: Path, command_strings: list[str]) -> None:
    payload = json.loads(lock_path.read_text())
    payload["red_evidence"] = {
        "red": True,
        "captured_at": "2026-06-12T00:00:00Z",
        "commands": [
            {
                "command": command,
                "exit_code": 1,
                "output_tail": "1 failed",
                "classification": "red",
            }
            for command in command_strings
        ],
    }
    lock_path.write_text(json.dumps(payload))


def _codes(errors) -> list[ErrorCode]:
    return [error.code for error in errors]


def test_honest_lock_passes_evidence_command_check(tmp_path: Path) -> None:
    manifest_path = _write_project(tmp_path)
    lock_path = _lock(manifest_path, tmp_path)
    _splice_red_evidence(lock_path, [_DEMO_VALIDATE])

    errors = enforce_plan_locks(
        _chain(tmp_path),
        tmp_path,
        require_plan_lock=True,
        require_red_evidence=True,
    )

    assert ErrorCode.RED_EVIDENCE_COMMAND_MISMATCH not in _codes(errors)
    assert errors == ()


def test_spliced_draft_evidence_fails_e707(tmp_path: Path) -> None:
    manifest_path = _write_project(tmp_path)
    lock_path = _lock(manifest_path, tmp_path)
    _splice_red_evidence(
        lock_path,
        [
            "uv run maid validate manifests/drafts/demo-task.manifest.yaml"
            " --mode behavioral --quiet"
        ],
    )

    errors = enforce_plan_locks(
        _chain(tmp_path),
        tmp_path,
        require_plan_lock=True,
        require_red_evidence=False,
        changed_paths=frozenset(),
    )

    assert _codes(errors) == [ErrorCode.RED_EVIDENCE_COMMAND_MISMATCH]
    assert errors[0].location is not None
    assert errors[0].location.file == "manifests/demo-task.manifest.yaml"


def test_legacy_lock_without_snapshot_field_is_skipped(tmp_path: Path) -> None:
    manifest_path = _write_project(tmp_path)
    lock_path = _lock(manifest_path, tmp_path)
    payload = json.loads(lock_path.read_text())
    payload["_manifest_contract"].pop("validate_commands", None)
    lock_path.write_text(json.dumps(payload))
    _splice_red_evidence(
        lock_path,
        ["python -m pytest -q tests/test_renamed_long_ago.py"],
    )

    errors = enforce_plan_locks(
        _chain(tmp_path),
        tmp_path,
        require_plan_lock=True,
        require_red_evidence=False,
    )

    assert ErrorCode.RED_EVIDENCE_COMMAND_MISMATCH not in _codes(errors)
    assert errors == ()


def test_null_evidence_lock_is_not_checked_for_e707(tmp_path: Path) -> None:
    manifest_path = _write_project(tmp_path)
    _lock(manifest_path, tmp_path)

    errors_without_requirement = enforce_plan_locks(
        _chain(tmp_path),
        tmp_path,
        require_plan_lock=True,
        require_red_evidence=False,
    )
    errors_with_requirement = enforce_plan_locks(
        _chain(tmp_path),
        tmp_path,
        require_plan_lock=False,
        require_red_evidence=True,
    )

    assert ErrorCode.RED_EVIDENCE_COMMAND_MISMATCH not in _codes(
        errors_without_requirement
    )
    assert errors_without_requirement == ()
    assert _codes(errors_with_requirement) == [ErrorCode.RED_PHASE_EVIDENCE_MISSING]


def test_post_lock_additive_validate_edit_still_passes(tmp_path: Path) -> None:
    manifest_path = _write_project(tmp_path)
    lock_path = _lock(manifest_path, tmp_path)
    _splice_red_evidence(lock_path, [_DEMO_VALIDATE])
    manifest_path.write_text(
        _manifest_text([f"{_DEMO_VALIDATE} tests/test_added_later.py"])
    )

    errors = enforce_plan_locks(
        _chain(tmp_path),
        tmp_path,
        require_plan_lock=True,
        require_red_evidence=True,
    )

    assert ErrorCode.RED_EVIDENCE_COMMAND_MISMATCH not in _codes(errors)
    assert errors == ()


def test_save_records_validate_commands_snapshot(tmp_path: Path) -> None:
    manifest_path = _write_project(
        tmp_path,
        validate_lines=[
            _DEMO_VALIDATE,
            f"{_DEMO_VALIDATE} -k contract",
        ],
    )
    lock: PlanLock = create_plan_lock(manifest_path, tmp_path)
    lock_path = default_plan_lock_path(tmp_path, "demo-task")
    lock.save(lock_path)

    payload = json.loads(lock_path.read_text())

    assert payload["_manifest_contract"]["validate_commands"] == [
        _DEMO_VALIDATE,
        f"{_DEMO_VALIDATE} -k contract",
    ]


def test_e707_docs_are_discoverable() -> None:
    root = Path(__file__).resolve().parents[2]

    specs_text = (root / "docs" / "maid_specs.md").read_text()
    claude_text = (root / "CLAUDE.md").read_text()

    assert "E707" in specs_text
    assert "RED_EVIDENCE_COMMAND_MISMATCH" in specs_text
    assert "E707" in claude_text
