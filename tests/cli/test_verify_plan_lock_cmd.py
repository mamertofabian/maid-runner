"""CLI tests for plan-lock enforcement in `maid verify`."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path

from maid_runner.cli.commands._main import build_parser, main
from maid_runner.cli.commands.verify import cmd_verify
from maid_runner.core.plan_lock import create_plan_lock, default_plan_lock_path
from maid_runner.core.result import ErrorCode, VerificationResult


def _write_project(tmp_path: Path) -> Path:
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
          returns: int
  read:
    - tests/test_demo.py
validate:
  - python -m pytest -q tests/test_demo.py
"""
    )
    return manifest_path


def _write_lock(manifest_path: Path, project_root: Path) -> Path:
    lock = create_plan_lock(manifest_path, project_root)
    lock_path = default_plan_lock_path(project_root, "demo-task")
    lock.save(lock_path)
    return lock_path


def _verify_args(**overrides) -> argparse.Namespace:
    values = {
        "manifest_dir": "manifests/",
        "allow_empty": False,
        "fail_fast": True,
        "strict": False,
        "fail_on_warnings": False,
        "advisory": False,
        "worktree_scope": False,
        "changed_scope": False,
        "since": None,
        "base_ref": None,
        "include_tests": False,
        "test_jobs": 1,
        "require_plan_lock": False,
        "require_red_evidence": False,
        "json": False,
    }
    values.update(overrides)
    return argparse.Namespace(**values)


def _stage_errors(payload: dict, stage_name: str) -> list[dict]:
    stages = {stage["name"]: stage for stage in payload["stages"]}
    return stages[stage_name]["details"]["errors"]


def test_verify_parser_exposes_plan_lock_flags() -> None:
    parser = build_parser()

    args = parser.parse_args(
        ["verify", "--require-plan-lock", "--require-red-evidence"]
    )

    assert args.require_plan_lock is True
    assert args.require_red_evidence is True


def test_cmd_verify_passes_plan_lock_flags_to_run_verify(monkeypatch, capsys) -> None:
    captured = {}

    def fake_run_verify(**kwargs):
        captured["require_plan_lock"] = kwargs["require_plan_lock"]
        captured["require_red_evidence"] = kwargs["require_red_evidence"]
        return VerificationResult(stages=(), duration_ms=1.0)

    monkeypatch.setattr("maid_runner.cli.commands.verify._run_verify", fake_run_verify)

    exit_code = cmd_verify(
        _verify_args(require_plan_lock=True, require_red_evidence=True)
    )

    assert exit_code == 0
    assert captured == {
        "require_plan_lock": True,
        "require_red_evidence": True,
    }


def test_verify_text_output_reports_plan_lock_error(
    tmp_path: Path,
    monkeypatch,
    capsys,
) -> None:
    _write_project(tmp_path)
    monkeypatch.chdir(tmp_path)

    exit_code = main(["verify", "--require-plan-lock", "--no-changed-scope"])

    output = capsys.readouterr().out
    assert exit_code == 1
    assert "FAIL plan_lock" in output
    assert ErrorCode.PLAN_LOCK_MISSING.value in output
    assert "PLAN_LOCK_MISSING" in output


def test_verify_json_output_reports_same_plan_lock_error(
    tmp_path: Path,
    monkeypatch,
    capsys,
) -> None:
    _write_project(tmp_path)
    monkeypatch.chdir(tmp_path)

    exit_code = main(["verify", "--require-plan-lock", "--no-changed-scope", "--json"])

    payload = json.loads(capsys.readouterr().out)
    assert exit_code == 1
    assert _stage_errors(payload, "plan_lock")[0]["code"] == (
        ErrorCode.PLAN_LOCK_MISSING.value
    )


def test_verify_plan_lock_json_and_text_share_e701_code(
    tmp_path: Path,
    monkeypatch,
    capsys,
) -> None:
    manifest_path = _write_project(tmp_path)
    _write_lock(manifest_path, tmp_path)
    (tmp_path / "tests" / "test_demo.py").write_text(
        "from src.demo import demo\n\n\ndef test_demo_contract():\n"
        "    demo()\n    assert True\n"
    )
    monkeypatch.chdir(tmp_path)

    text_exit = main(["verify", "--require-plan-lock", "--no-changed-scope"])
    text_output = capsys.readouterr().out
    json_exit = main(["verify", "--require-plan-lock", "--no-changed-scope", "--json"])
    payload = json.loads(capsys.readouterr().out)

    assert text_exit == 1
    assert json_exit == 1
    assert ErrorCode.BEHAVIORAL_TEST_MODIFIED_AFTER_LOCK.value in text_output
    assert _stage_errors(payload, "plan_lock")[0]["code"] == (
        ErrorCode.BEHAVIORAL_TEST_MODIFIED_AFTER_LOCK.value
    )


def test_verify_without_plan_lock_flags_remains_opt_in(
    tmp_path: Path,
    monkeypatch,
    capsys,
) -> None:
    _write_project(tmp_path)
    monkeypatch.chdir(tmp_path)

    exit_code = main(["verify", "--no-changed-scope"])

    output = capsys.readouterr().out
    assert exit_code == 0
    assert "plan_lock" not in output


def test_main_dispatch_with_plan_lock_flags_works_from_project_cwd(
    tmp_path: Path,
    monkeypatch,
    capsys,
) -> None:
    manifest_path = _write_project(tmp_path)
    _write_lock(manifest_path, tmp_path)
    monkeypatch.chdir(tmp_path)
    assert os.getcwd() == str(tmp_path)

    exit_code = main(["verify", "--require-plan-lock", "--no-changed-scope"])

    assert exit_code == 0
    assert "Verify: PASS" in capsys.readouterr().out
