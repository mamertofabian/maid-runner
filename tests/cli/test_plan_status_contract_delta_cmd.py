"""CLI status behavior for plan-lock contract deltas."""

from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

import pytest
import yaml

from maid_runner.cli.commands.manifest import cmd_manifest
from maid_runner.cli.commands.plan import (
    cmd_plan_lock,
    cmd_plan_revise,
    cmd_plan_status,
)
from maid_runner.core.plan_lock import create_plan_lock, default_plan_lock_path


def _write_project(
    tmp_path: Path,
    *,
    validate_commands: tuple[str, ...] = ("python -m pytest -q tests/test_demo.py",),
) -> Path:
    (tmp_path / "manifests").mkdir(exist_ok=True)
    (tmp_path / "src").mkdir(exist_ok=True)
    (tmp_path / "tests").mkdir(exist_ok=True)
    (tmp_path / "src" / "demo.py").write_text("def demo() -> int:\n    return 1\n")
    (tmp_path / "tests" / "test_demo.py").write_text(
        "from src.demo import demo\n\n\n"
        "def test_demo_contract():\n    assert demo() == 1\n"
    )
    (tmp_path / "tests" / "test_extra.py").write_text(
        "def test_extra_contract():\n    assert True\n"
    )
    validate_block = "\n".join(f"  - {command}" for command in validate_commands)
    manifest_path = tmp_path / "manifests" / "demo-task.manifest.yaml"
    manifest_path.write_text(
        f"""schema: "2"
goal: "Demo task"
type: feature
created: "2026-07-06T00:00:00Z"
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
{validate_block}
"""
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
    manifest_path: Path, project_root: Path, reason: str
) -> SimpleNamespace:
    return SimpleNamespace(
        plan_command="revise",
        manifest_path=str(manifest_path),
        project_root=str(project_root),
        reason=reason,
        no_run=True,
        preserve_red_evidence=False,
        stash_implementation=False,
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


def _write_lock_record(project_root: Path, payload: dict) -> None:
    default_plan_lock_path(project_root, "demo-task").write_text(
        json.dumps(payload, indent=2)
    )


def _write_lock_with_legacy_and_delta_revisions(tmp_path: Path) -> Path:
    manifest_path = _write_project(tmp_path)
    assert cmd_plan_lock(_lock_args(manifest_path, tmp_path)) == 0
    assert (
        cmd_plan_revise(_revise_args(manifest_path, tmp_path, "legacy revision")) == 0
    )
    payload = _lock_record(tmp_path)
    payload["revisions"][0].pop("contract_delta", None)
    _write_lock_record(tmp_path, payload)
    manifest_path = _write_project(
        tmp_path,
        validate_commands=(
            "python -m pytest -q tests/test_demo.py",
            "python -m pytest -q tests/test_extra.py",
        ),
    )
    assert (
        cmd_plan_revise(_revise_args(manifest_path, tmp_path, "add extra validation"))
        == 0
    )
    return manifest_path


def _promote_args(project_root: Path, draft_path: Path) -> SimpleNamespace:
    return SimpleNamespace(
        manifest_command="promote",
        manifest_path=str(draft_path),
        output_dir=str(project_root / "manifests"),
        project_root=str(project_root),
        no_run=True,
        json=False,
    )


def test_plan_status_json_exposes_contract_delta_per_revision(
    tmp_path: Path,
    capsys: pytest.CaptureFixture,
) -> None:
    manifest_path = _write_lock_with_legacy_and_delta_revisions(tmp_path)
    capsys.readouterr()

    assert cmd_plan_status(_status_args(manifest_path, tmp_path, json_mode=True)) == 0
    payload = json.loads(capsys.readouterr().out)

    assert payload["revisions"][0]["contract_delta"] is None
    delta = payload["revisions"][1]["contract_delta"]
    assert delta["artifacts_added"] == []
    assert delta["artifacts_removed"] == []
    assert delta["files_added"] == []
    assert delta["files_removed"] == []
    assert delta["validate_commands_added"] == [
        "python -m pytest -q tests/test_extra.py"
    ]
    assert delta["validate_commands_removed"] == []


def test_plan_status_text_prints_delta_counts_only_when_present(
    tmp_path: Path,
    capsys: pytest.CaptureFixture,
) -> None:
    manifest_path = _write_lock_with_legacy_and_delta_revisions(tmp_path)
    capsys.readouterr()

    assert cmd_plan_status(_status_args(manifest_path, tmp_path, json_mode=False)) == 0
    text = capsys.readouterr().out

    assert text.count("Delta:") == 1
    assert "Delta: +1 validate command" in text


def test_manifest_promote_stores_contract_delta_for_migrated_revision(
    tmp_path: Path,
) -> None:
    draft_dir = tmp_path / "manifests" / "drafts"
    draft_dir.mkdir(parents=True)
    draft_path = draft_dir / "demo-task.manifest.yaml"
    draft_rel = "manifests/drafts/demo-task.manifest.yaml"
    promoted_rel = "manifests/demo-task.manifest.yaml"
    draft_path.write_text(
        yaml.safe_dump(
            {
                "schema": "2",
                "goal": "Demo task",
                "type": "feature",
                "created": "2026-07-06T00:00:00Z",
                "files": {
                    "create": [
                        {
                            "path": "src/demo.py",
                            "artifacts": [{"kind": "function", "name": "demo"}],
                        }
                    ]
                },
                "validate": [f"maid validate {draft_rel} --mode schema --quiet"],
            },
            sort_keys=False,
        )
    )
    lock = create_plan_lock(draft_path, tmp_path)
    lock_path = default_plan_lock_path(tmp_path, "demo-task")
    lock.save(lock_path)

    assert cmd_manifest(_promote_args(tmp_path, draft_path)) == 0

    payload = json.loads(lock_path.read_text())
    delta = payload["revisions"][-1]["contract_delta"]
    assert delta["validate_commands_removed"] == [
        f"maid validate {draft_rel} --mode schema --quiet"
    ]
    assert delta["validate_commands_added"] == [
        f"maid validate {promoted_rel} --mode schema --quiet"
    ]
