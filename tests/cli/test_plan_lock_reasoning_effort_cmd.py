"""CLI behavior for agent reasoning-effort plan-lock provenance."""

from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

from maid_runner.cli.commands._main import build_parser
from maid_runner.cli.commands.plan import cmd_plan_lock, cmd_plan_status
from maid_runner.core.plan_lock import default_plan_lock_path


def test_plan_lock_stores_reasoning_effort_from_flag(tmp_path: Path) -> None:
    parsed = build_parser().parse_args(
        ["plan", "lock", "example.manifest.yaml", "--agent-reasoning-effort", "medium"]
    )
    assert parsed.agent_reasoning_effort == "medium"
    manifest_path = _write_project(tmp_path)
    assert cmd_plan_lock(_args(manifest_path, tmp_path, "gpt-5.5", "medium")) == 0
    payload = json.loads(default_plan_lock_path(tmp_path, "demo").read_text())
    assert payload["agent"]["reasoning_effort"] == "medium"


def test_plan_lock_stores_reasoning_effort_from_env(
    tmp_path: Path, monkeypatch
) -> None:
    manifest_path = _write_project(tmp_path)
    monkeypatch.setenv("MAID_AGENT_MODEL", "gpt-5.5")
    monkeypatch.setenv("MAID_AGENT_REASONING_EFFORT", "high")
    assert cmd_plan_lock(_args(manifest_path, tmp_path, None, None)) == 0
    payload = json.loads(default_plan_lock_path(tmp_path, "demo").read_text())
    assert payload["agent"]["reasoning_effort"] == "high"
    assert payload["agent"]["source"] == "environment"


def test_plan_status_reports_reasoning_effort(tmp_path: Path, capsys) -> None:
    manifest_path = _write_project(tmp_path)
    assert cmd_plan_lock(_args(manifest_path, tmp_path, "gpt-5.5", "medium")) == 0
    capsys.readouterr()
    status = SimpleNamespace(
        manifest_path=str(manifest_path), project_root=str(tmp_path), json=True
    )
    assert cmd_plan_status(status) == 0
    assert json.loads(capsys.readouterr().out)["agent"]["reasoning_effort"] == "medium"
    status.json = False
    assert cmd_plan_status(status) == 0
    assert "reasoning_effort=medium" in capsys.readouterr().out

    absent_root = tmp_path / "absent"
    absent_manifest = _write_project(absent_root)
    assert cmd_plan_lock(_args(absent_manifest, absent_root, "gpt-5.5", None)) == 0
    capsys.readouterr()
    absent_status = SimpleNamespace(
        manifest_path=str(absent_manifest), project_root=str(absent_root), json=True
    )
    assert cmd_plan_status(absent_status) == 0
    assert "reasoning_effort" not in json.loads(capsys.readouterr().out)["agent"]
    absent_status.json = False
    assert cmd_plan_status(absent_status) == 0
    assert "reasoning_effort" not in capsys.readouterr().out


def _args(
    path: Path, root: Path, model: str | None, effort: str | None
) -> SimpleNamespace:
    return SimpleNamespace(
        manifest_path=str(path),
        project_root=str(root),
        no_run=True,
        json=False,
        legacy_baseline=False,
        reason=None,
        agent_model=model,
        agent_reasoning_effort=effort,
        agent_provider=None,
        agent_client=None,
        agent_skill=None,
        agent_instructions_fingerprint=None,
    )


def _write_project(tmp_path: Path) -> Path:
    tmp_path.mkdir(parents=True, exist_ok=True)
    (tmp_path / "manifests").mkdir()
    (tmp_path / "tests").mkdir()
    (tmp_path / "tests/test_demo.py").write_text("def test_demo(): assert True\n")
    path = tmp_path / "manifests/demo.manifest.yaml"
    path.write_text(
        """schema: "2"\ngoal: "demo"\ntype: feature\ncreated: "2026-07-19"\nfiles:\n  create:\n    - path: src/demo.py\n      artifacts:\n        - kind: function\n          name: demo\n  read:\n    - tests/test_demo.py\nvalidate:\n  - python -m pytest -q tests/test_demo.py\n"""
    )
    return path
