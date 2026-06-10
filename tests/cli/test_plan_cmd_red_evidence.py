"""CLI behavior for plan-lock red-phase evidence capture."""

from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

from maid_runner.cli.commands._main import build_parser
from maid_runner.cli.commands.plan import cmd_plan_lock, cmd_plan_revise
from maid_runner.core.plan_lock import default_plan_lock_path


def _write_project(tmp_path: Path, exit_code: int) -> Path:
    (tmp_path / "manifests").mkdir()
    (tmp_path / "tests").mkdir()
    (tmp_path / "scripts").mkdir()
    (tmp_path / "tests" / "test_demo.py").write_text(
        "def test_demo_contract():\n    assert True\n"
    )
    (tmp_path / "scripts" / "validate.py").write_text(
        "import sys\n"
        f"print('validate exit {exit_code}')\n"
        f"sys.exit({exit_code})\n"
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
  read:
    - tests/test_demo.py
validate:
  - python scripts/validate.py
"""
    )
    return manifest_path


def _set_validate_exit(project_root: Path, exit_code: int) -> None:
    (project_root / "scripts" / "validate.py").write_text(
        "import sys\n"
        f"print('validate exit {exit_code}')\n"
        f"sys.exit({exit_code})\n"
    )


def _lock_args(
    manifest_path: Path, project_root: Path, *, no_run: bool = False
) -> SimpleNamespace:
    return SimpleNamespace(
        plan_command="lock",
        manifest_path=str(manifest_path),
        project_root=str(project_root),
        no_run=no_run,
        json=False,
    )


def _revise_args(
    manifest_path: Path,
    project_root: Path,
    reason: str,
    *,
    no_run: bool = False,
) -> SimpleNamespace:
    return SimpleNamespace(
        plan_command="revise",
        manifest_path=str(manifest_path),
        project_root=str(project_root),
        reason=reason,
        no_run=no_run,
        json=False,
    )


def _lock_record(project_root: Path) -> dict:
    return json.loads(default_plan_lock_path(project_root, "demo-task").read_text())


class TestPlanNoRunParser:
    def test_lock_parser_exposes_no_run(self) -> None:
        args = build_parser().parse_args(
            ["plan", "lock", "manifests/demo-task.manifest.yaml", "--no-run"]
        )

        assert args.no_run is True

    def test_revise_parser_exposes_no_run(self) -> None:
        args = build_parser().parse_args(
            [
                "plan",
                "revise",
                "manifests/demo-task.manifest.yaml",
                "--reason",
                "refresh evidence",
                "--no-run",
            ]
        )

        assert args.no_run is True


class TestCmdPlanLockRedEvidence:
    def test_lock_captures_red_evidence_by_default(self, tmp_path: Path) -> None:
        manifest_path = _write_project(tmp_path, exit_code=1)

        exit_code = cmd_plan_lock(_lock_args(manifest_path, tmp_path))

        assert exit_code == 0
        evidence = _lock_record(tmp_path)["red_evidence"]
        assert evidence["red"] is True
        assert evidence["commands"][0]["command"] == "python scripts/validate.py"
        assert evidence["commands"][0]["exit_code"] == 1
        assert evidence["commands"][0]["classification"] == "red"

    def test_lock_no_run_records_null_evidence(self, tmp_path: Path) -> None:
        manifest_path = _write_project(tmp_path, exit_code=1)

        exit_code = cmd_plan_lock(_lock_args(manifest_path, tmp_path, no_run=True))

        assert exit_code == 0
        assert _lock_record(tmp_path)["red_evidence"] is None

    def test_lock_records_collection_error_as_invalid_not_red(
        self, tmp_path: Path
    ) -> None:
        manifest_path = _write_project(tmp_path, exit_code=2)

        exit_code = cmd_plan_lock(_lock_args(manifest_path, tmp_path))

        assert exit_code == 0
        evidence = _lock_record(tmp_path)["red_evidence"]
        assert evidence["red"] is False
        assert evidence["commands"][0]["exit_code"] == 2
        assert evidence["commands"][0]["classification"] == "invalid"


class TestCmdPlanReviseRedEvidence:
    def test_revise_recaptures_red_evidence_by_default(self, tmp_path: Path) -> None:
        manifest_path = _write_project(tmp_path, exit_code=1)
        assert cmd_plan_lock(_lock_args(manifest_path, tmp_path, no_run=True)) == 0
        _set_validate_exit(tmp_path, exit_code=0)

        exit_code = cmd_plan_revise(
            _revise_args(manifest_path, tmp_path, "refresh red evidence")
        )

        assert exit_code == 0
        record = _lock_record(tmp_path)
        assert record["revision"] == 2
        assert record["red_evidence"]["red"] is False
        assert record["red_evidence"]["commands"][0]["classification"] == "not_red"

    def test_revise_no_run_records_null_evidence(self, tmp_path: Path) -> None:
        manifest_path = _write_project(tmp_path, exit_code=1)
        assert cmd_plan_lock(_lock_args(manifest_path, tmp_path)) == 0

        exit_code = cmd_plan_revise(
            _revise_args(
                manifest_path,
                tmp_path,
                "skip rerun after intentional manifest revision",
                no_run=True,
            )
        )

        assert exit_code == 0
        assert _lock_record(tmp_path)["red_evidence"] is None
