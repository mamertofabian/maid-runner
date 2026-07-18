"""Behavioral coverage for robust plan revision and status sessions."""

from __future__ import annotations

import json
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace

from maid_runner.cli.commands.plan import (
    cmd_plan_lock,
    cmd_plan_revise,
    cmd_plan_status,
)
from maid_runner.core.chain import ManifestChain
from maid_runner.core.plan_lock import (
    PlanLock,
    default_plan_lock_path,
    enforce_plan_locks,
    revision_preserves_red_evidence,
)
from maid_runner.core.result import ErrorCode


def _write_validate_script(project_root: Path, exit_code: int) -> None:
    scripts = project_root / "scripts"
    scripts.mkdir(exist_ok=True)
    (scripts / "validate.py").write_text(
        f"import sys\nprint('validate {exit_code}')\nsys.exit({exit_code})\n"
    )


def _manifest_text(*, goal: str = "Test-only contract") -> str:
    return f"""schema: "2"
goal: "{goal}"
type: fix
created: "2026-07-18T00:00:00Z"
files:
  edit:
    - path: tests/test_demo.py
      artifacts:
        - kind: test_function
          name: test_demo_contract
validate:
  - python scripts/validate.py
"""


def _write_test_only_project(project_root: Path) -> Path:
    (project_root / "manifests").mkdir()
    (project_root / "tests").mkdir()
    (project_root / "tests" / "test_demo.py").write_text(
        "def test_demo_contract():\n    assert True\n"
    )
    _write_validate_script(project_root, 1)
    manifest_path = project_root / "manifests" / "demo-task.manifest.yaml"
    manifest_path.write_text(_manifest_text())
    return manifest_path


def _lock_args(manifest_path: Path, project_root: Path) -> SimpleNamespace:
    return SimpleNamespace(
        plan_command="lock",
        manifest_path=str(manifest_path),
        project_root=str(project_root),
        no_run=False,
        json=False,
        legacy_baseline=False,
        reason=None,
    )


def _revise_args(
    manifest_path: Path,
    project_root: Path,
    *,
    preserve_red_evidence: bool = False,
    test_only_green: bool = False,
) -> SimpleNamespace:
    return SimpleNamespace(
        plan_command="revise",
        manifest_path=str(manifest_path),
        project_root=str(project_root),
        reason="bookkeeping-only plan revision",
        no_run=False,
        preserve_red_evidence=preserve_red_evidence,
        stash_implementation=False,
        test_only_green=test_only_green,
        allow_sibling_dirty=False,
        json=False,
    )


def _status_args(
    manifest_path: Path, project_root: Path, *, json_mode: bool
) -> SimpleNamespace:
    return SimpleNamespace(
        plan_command="status",
        manifest_path=str(manifest_path),
        project_root=str(project_root),
        json=json_mode,
    )


def _lock_record(project_root: Path) -> dict:
    return json.loads(default_plan_lock_path(project_root, "demo-task").read_text())


def _lock_with_test_only_green(project_root: Path) -> Path:
    manifest_path = _write_test_only_project(project_root)
    assert cmd_plan_lock(_lock_args(manifest_path, project_root)) == 0
    _write_validate_script(project_root, 0)
    manifest_path.write_text(_manifest_text(goal="Implemented test-only contract"))
    assert (
        cmd_plan_revise(
            _revise_args(
                manifest_path,
                project_root,
                test_only_green=True,
            )
        )
        == 0
    )
    assert _lock_record(project_root)["red_evidence"]["mode"] == "test_only_green"
    return manifest_path


def test_plain_revise_preserves_test_only_green_evidence(
    tmp_path: Path, capsys
) -> None:
    manifest_path = _lock_with_test_only_green(tmp_path)
    original_evidence = _lock_record(tmp_path)["red_evidence"]
    capsys.readouterr()
    manifest_path.write_text(
        _manifest_text(goal="Implemented test-only contract after bookkeeping")
    )

    exit_code = cmd_plan_revise(_revise_args(manifest_path, tmp_path))

    assert exit_code == 0
    assert _lock_record(tmp_path)["red_evidence"] == original_evidence
    output = capsys.readouterr().out.lower()
    assert "test-only-green" in output
    assert "preserved" in output
    errors = enforce_plan_locks(
        ManifestChain(tmp_path / "manifests", tmp_path),
        tmp_path,
        require_plan_lock=True,
        require_red_evidence=True,
    )
    assert ErrorCode.RED_PHASE_EVIDENCE_INVALID not in {error.code for error in errors}


def test_plain_revise_recaptures_test_only_green_when_tests_change(
    tmp_path: Path,
) -> None:
    manifest_path = _lock_with_test_only_green(tmp_path)
    original_evidence = _lock_record(tmp_path)["red_evidence"]
    (tmp_path / "tests" / "test_demo.py").write_text(
        "def test_demo_contract():\n    assert 1 + 1 == 2\n"
    )

    exit_code = cmd_plan_revise(_revise_args(manifest_path, tmp_path))

    assert exit_code == 0
    current_evidence = _lock_record(tmp_path)["red_evidence"]
    assert current_evidence != original_evidence
    assert current_evidence["red"] is False
    assert "mode" not in current_evidence


def test_revision_preserves_test_only_green_predicate_bounds(
    tmp_path: Path, monkeypatch
) -> None:
    manifest_path = _lock_with_test_only_green(tmp_path)
    lock_path = default_plan_lock_path(tmp_path, "demo-task")
    existing = PlanLock.load(lock_path)
    prior_contract = _lock_record(tmp_path)["_manifest_contract"]

    assert (
        revision_preserves_red_evidence(
            existing, manifest_path, tmp_path, prior_contract
        )
        is True
    )

    invalid = replace(
        existing,
        red_evidence={
            **existing.red_evidence,
            "commands": [
                {
                    "command": "python scripts/validate.py",
                    "exit_code": 1,
                    "output_tail": "failed",
                    "classification": "red",
                }
            ],
        },
    )
    assert (
        revision_preserves_red_evidence(
            invalid, manifest_path, tmp_path, prior_contract
        )
        is False
    )

    monkeypatch.setattr(
        "maid_runner.core._file_discovery.is_test_file", lambda _path: False
    )
    assert (
        revision_preserves_red_evidence(
            existing, manifest_path, tmp_path, prior_contract
        )
        is False
    )


def test_preserve_red_evidence_flag_accepts_test_only_green(
    tmp_path: Path,
) -> None:
    manifest_path = _lock_with_test_only_green(tmp_path)
    original_evidence = _lock_record(tmp_path)["red_evidence"]
    manifest_path.write_text(
        _manifest_text(goal="Explicitly preserved test-only contract")
    )

    exit_code = cmd_plan_revise(
        _revise_args(manifest_path, tmp_path, preserve_red_evidence=True)
    )

    assert exit_code == 0
    assert _lock_record(tmp_path)["red_evidence"] == original_evidence


def test_plan_status_reports_unreadable_manifest_as_mismatch(
    tmp_path: Path, capsys
) -> None:
    manifest_path = _write_test_only_project(tmp_path)
    assert cmd_plan_lock(_lock_args(manifest_path, tmp_path)) == 0
    capsys.readouterr()
    manifest_path.write_text("schema: [\n  broken: {{\n")

    text_exit = cmd_plan_status(_status_args(manifest_path, tmp_path, json_mode=False))
    text_output = capsys.readouterr().out
    json_exit = cmd_plan_status(_status_args(manifest_path, tmp_path, json_mode=True))
    payload = json.loads(capsys.readouterr().out)

    assert text_exit == 1
    assert "Manifest: MISMATCH" in text_output
    assert "Manifest error:" in text_output
    assert "parse" in text_output.lower() or "yaml" in text_output.lower()
    assert json_exit == 1
    assert payload["manifest_match"] is False
    assert isinstance(payload["manifest_error"], str)
    assert payload["manifest_error"]
