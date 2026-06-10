"""Behavioral tests for the `maid plan lock|revise|status` CLI commands."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from maid_runner.cli.commands._main import build_parser, main
from maid_runner.cli.commands.plan import (
    cmd_plan,
    cmd_plan_lock,
    cmd_plan_revise,
    cmd_plan_status,
)
from maid_runner.core.plan_lock import default_plan_lock_path


def _write_project(tmp_path: Path) -> Path:
    """Create a throwaway MAID project; return the manifest path."""
    (tmp_path / "manifests").mkdir()
    (tmp_path / "tests").mkdir()
    (tmp_path / "tests" / "test_demo.py").write_text(
        "from src.demo import demo\n\n\ndef test_demo():\n    assert demo() == 1\n"
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
  - python -m pytest -q tests/test_demo.py
"""
    )
    return manifest_path


def _lock_args(manifest_path: Path, project_root: Path) -> SimpleNamespace:
    return SimpleNamespace(
        plan_command="lock",
        manifest_path=str(manifest_path),
        project_root=str(project_root),
        json=False,
    )


def _revise_args(
    manifest_path: Path, project_root: Path, reason: str | None
) -> SimpleNamespace:
    return SimpleNamespace(
        plan_command="revise",
        manifest_path=str(manifest_path),
        project_root=str(project_root),
        reason=reason,
        json=False,
    )


def _status_args(
    manifest_path: Path, project_root: Path, json_mode: bool = True
) -> SimpleNamespace:
    return SimpleNamespace(
        plan_command="status",
        manifest_path=str(manifest_path),
        project_root=str(project_root),
        json=json_mode,
    )


def _status_payload(
    manifest_path: Path, project_root: Path, capsys: pytest.CaptureFixture
) -> tuple[int, dict]:
    exit_code = cmd_plan_status(_status_args(manifest_path, project_root))
    payload = json.loads(capsys.readouterr().out)
    return exit_code, payload


class TestPlanParserRegistered:
    def test_build_parser_includes_plan_subcommands(self) -> None:
        parser = build_parser()
        plan_parser: argparse.ArgumentParser | None = None
        for action in parser._actions:
            if isinstance(action, argparse._SubParsersAction):
                plan_parser = action.choices.get("plan")
                break
        assert plan_parser is not None
        plan_subs: dict[str, argparse.ArgumentParser] = {}
        for action in plan_parser._actions:
            if isinstance(action, argparse._SubParsersAction):
                for name, sub in action.choices.items():
                    plan_subs[name] = sub
        assert {"lock", "revise", "status"} <= set(plan_subs)

    def test_main_dispatches_plan_lock(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _write_project(tmp_path)
        monkeypatch.chdir(tmp_path)

        exit_code = main(["plan", "lock", "manifests/demo-task.manifest.yaml"])

        assert exit_code == 0
        assert default_plan_lock_path(Path("."), "demo-task").exists()


class TestCmdPlanDispatch:
    def test_unknown_subcommand_fails(self, capsys: pytest.CaptureFixture) -> None:
        args = SimpleNamespace(plan_command="bogus", json=False)
        assert cmd_plan(args) == 2

    def test_dispatches_to_lock(self, tmp_path: Path) -> None:
        manifest_path = _write_project(tmp_path)

        exit_code = cmd_plan(_lock_args(manifest_path, tmp_path))

        assert exit_code == 0
        assert default_plan_lock_path(tmp_path, "demo-task").exists()


class TestCmdPlanLock:
    def test_lock_creates_revision_one_record(
        self, tmp_path: Path, capsys: pytest.CaptureFixture
    ) -> None:
        manifest_path = _write_project(tmp_path)

        exit_code = cmd_plan_lock(_lock_args(manifest_path, tmp_path))

        assert exit_code == 0
        lock_path = default_plan_lock_path(tmp_path, "demo-task")
        record = json.loads(lock_path.read_text())
        assert record["revision"] == 1
        assert record["manifest_hash"].startswith("sha256:")
        assert record["red_evidence"] is None
        assert "tests/test_demo.py" in record["test_hashes"]

    def test_lock_refuses_to_overwrite_existing_lock(
        self, tmp_path: Path, capsys: pytest.CaptureFixture
    ) -> None:
        manifest_path = _write_project(tmp_path)
        assert cmd_plan_lock(_lock_args(manifest_path, tmp_path)) == 0
        lock_path = default_plan_lock_path(tmp_path, "demo-task")
        original_bytes = lock_path.read_bytes()
        capsys.readouterr()

        exit_code = cmd_plan_lock(_lock_args(manifest_path, tmp_path))

        assert exit_code == 1
        assert lock_path.read_bytes() == original_bytes
        output = capsys.readouterr()
        assert "revise" in (output.out + output.err)

    def test_lock_with_missing_manifest_fails(
        self, tmp_path: Path, capsys: pytest.CaptureFixture
    ) -> None:
        missing = tmp_path / "manifests" / "absent.manifest.yaml"

        exit_code = cmd_plan_lock(_lock_args(missing, tmp_path))

        assert exit_code == 2

    def test_lock_with_corrupt_existing_lock_fails_closed(
        self, tmp_path: Path, capsys: pytest.CaptureFixture
    ) -> None:
        manifest_path = _write_project(tmp_path)
        lock_path = default_plan_lock_path(tmp_path, "demo-task")
        lock_path.parent.mkdir(parents=True)
        lock_path.write_text("{not json")

        exit_code = cmd_plan_lock(_lock_args(manifest_path, tmp_path))

        assert exit_code == 2
        assert lock_path.read_text() == "{not json"


class TestCmdPlanRevise:
    def test_revise_with_reason_appends_history(
        self, tmp_path: Path, capsys: pytest.CaptureFixture
    ) -> None:
        manifest_path = _write_project(tmp_path)
        assert cmd_plan_lock(_lock_args(manifest_path, tmp_path)) == 0

        exit_code = cmd_plan_revise(
            _revise_args(manifest_path, tmp_path, "tighten contract")
        )

        assert exit_code == 0
        record = json.loads(default_plan_lock_path(tmp_path, "demo-task").read_text())
        assert record["revision"] == 2
        assert len(record["revisions"]) == 1
        assert record["revisions"][0]["reason"] == "tighten contract"

    def test_revise_without_reason_is_rejected(
        self, tmp_path: Path, capsys: pytest.CaptureFixture
    ) -> None:
        manifest_path = _write_project(tmp_path)
        assert cmd_plan_lock(_lock_args(manifest_path, tmp_path)) == 0
        lock_path = default_plan_lock_path(tmp_path, "demo-task")
        original_bytes = lock_path.read_bytes()

        exit_code = cmd_plan_revise(_revise_args(manifest_path, tmp_path, None))

        assert exit_code == 2
        assert lock_path.read_bytes() == original_bytes

    def test_revise_with_empty_reason_is_rejected(
        self, tmp_path: Path, capsys: pytest.CaptureFixture
    ) -> None:
        manifest_path = _write_project(tmp_path)
        assert cmd_plan_lock(_lock_args(manifest_path, tmp_path)) == 0

        exit_code = cmd_plan_revise(_revise_args(manifest_path, tmp_path, "  "))

        assert exit_code == 2

    def test_revise_without_existing_lock_fails(
        self, tmp_path: Path, capsys: pytest.CaptureFixture
    ) -> None:
        manifest_path = _write_project(tmp_path)

        exit_code = cmd_plan_revise(
            _revise_args(manifest_path, tmp_path, "no lock yet")
        )

        assert exit_code == 1


class TestCmdPlanStatus:
    def test_status_reports_unlocked_manifest(
        self, tmp_path: Path, capsys: pytest.CaptureFixture
    ) -> None:
        manifest_path = _write_project(tmp_path)

        exit_code, payload = _status_payload(manifest_path, tmp_path, capsys)

        assert exit_code == 0
        assert payload["locked"] is False

    def test_status_json_shape_for_clean_lock(
        self, tmp_path: Path, capsys: pytest.CaptureFixture
    ) -> None:
        manifest_path = _write_project(tmp_path)
        assert cmd_plan_lock(_lock_args(manifest_path, tmp_path)) == 0
        capsys.readouterr()

        exit_code, payload = _status_payload(manifest_path, tmp_path, capsys)

        assert exit_code == 0
        assert payload["locked"] is True
        assert payload["revision"] == 1
        assert payload["manifest_match"] is True
        assert payload["red_evidence"] is None
        assert payload["test_files"]["tests/test_demo.py"]["match"] is True

    def test_status_text_output_mentions_lock_state(
        self, tmp_path: Path, capsys: pytest.CaptureFixture
    ) -> None:
        manifest_path = _write_project(tmp_path)
        assert cmd_plan_lock(_lock_args(manifest_path, tmp_path)) == 0
        capsys.readouterr()

        exit_code = cmd_plan_status(
            _status_args(manifest_path, tmp_path, json_mode=False)
        )

        assert exit_code == 0
        assert "demo-task" in capsys.readouterr().out

    def test_tampered_behavioral_test_is_detected(
        self, tmp_path: Path, capsys: pytest.CaptureFixture
    ) -> None:
        """Adversarial reproduction of the gaming vector this child closes.

        Without a plan lock, weakening a behavioral test after plan approval
        goes undetected (`maid validate` still passes). With a lock, the
        recorded hash makes the tampering machine-detectable.
        """
        manifest_path = _write_project(tmp_path)
        assert cmd_plan_lock(_lock_args(manifest_path, tmp_path)) == 0
        capsys.readouterr()
        (tmp_path / "tests" / "test_demo.py").write_text(
            "from src.demo import demo\n\n\ndef test_demo():\n"
            "    demo()\n    assert True  # weakened\n"
        )

        exit_code, payload = _status_payload(manifest_path, tmp_path, capsys)

        assert exit_code == 1
        assert payload["test_files"]["tests/test_demo.py"]["match"] is False
        assert payload["manifest_match"] is True

    def test_tampered_manifest_is_detected(
        self, tmp_path: Path, capsys: pytest.CaptureFixture
    ) -> None:
        manifest_path = _write_project(tmp_path)
        assert cmd_plan_lock(_lock_args(manifest_path, tmp_path)) == 0
        capsys.readouterr()
        manifest_path.write_text(manifest_path.read_text() + "# edited\n")

        exit_code, payload = _status_payload(manifest_path, tmp_path, capsys)

        assert exit_code == 1
        assert payload["manifest_match"] is False

    def test_revise_with_reason_clears_mismatch(
        self, tmp_path: Path, capsys: pytest.CaptureFixture
    ) -> None:
        manifest_path = _write_project(tmp_path)
        assert cmd_plan_lock(_lock_args(manifest_path, tmp_path)) == 0
        (tmp_path / "tests" / "test_demo.py").write_text(
            "from src.demo import demo\n\n\ndef test_demo():\n"
            "    assert demo() == 1\n    assert demo() != 2\n"
        )
        assert (
            cmd_plan_revise(_revise_args(manifest_path, tmp_path, "stronger asserts"))
            == 0
        )
        capsys.readouterr()

        exit_code, payload = _status_payload(manifest_path, tmp_path, capsys)

        assert exit_code == 0
        assert payload["test_files"]["tests/test_demo.py"]["match"] is True

    def test_status_with_corrupt_lock_fails_closed(
        self, tmp_path: Path, capsys: pytest.CaptureFixture
    ) -> None:
        manifest_path = _write_project(tmp_path)
        lock_path = default_plan_lock_path(tmp_path, "demo-task")
        lock_path.parent.mkdir(parents=True)
        lock_path.write_text("{not json")

        exit_code = cmd_plan_status(_status_args(manifest_path, tmp_path))

        assert exit_code == 2
