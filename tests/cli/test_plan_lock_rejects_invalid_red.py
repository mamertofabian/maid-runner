"""Behavioral contract for rejecting unusable plan-lock red evidence."""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest

from maid_runner.cli.commands.plan import cmd_plan_lock
from maid_runner.core.plan_lock import default_plan_lock_path


def _project_with_validation_exit(tmp_path: Path, exit_code: int) -> Path:
    (tmp_path / "manifests").mkdir()
    (tmp_path / "scripts").mkdir()
    (tmp_path / "tests").mkdir()
    (tmp_path / "tests" / "test_demo.py").write_text(
        "def test_demo_contract():\n    assert True\n"
    )
    (tmp_path / "scripts" / "validate.py").write_text(
        "import sys\n" f"sys.exit({exit_code})\n"
    )
    manifest_path = tmp_path / "manifests" / "demo-task.manifest.yaml"
    manifest_path.write_text(
        """schema: "2"
goal: "Demo task"
type: feature
created: "2026-08-20T00:00:00Z"
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


@pytest.mark.parametrize(
    ("exit_code", "classification"),
    ((0, "not_red"), (2, "invalid")),
)
def test_plan_lock_rejects_non_red_validation_without_writing_lock(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    exit_code: int,
    classification: str,
) -> None:
    manifest_path = _project_with_validation_exit(tmp_path, exit_code)
    args = SimpleNamespace(
        plan_command="lock",
        manifest_path=str(manifest_path),
        project_root=str(tmp_path),
        no_run=False,
        legacy_baseline=False,
        reason=None,
        json=False,
    )

    result = cmd_plan_lock(args)

    assert result == 1
    assert not default_plan_lock_path(tmp_path, "demo-task").exists()
    error = capsys.readouterr().err
    assert "did not capture valid red evidence" in error
    assert f"classification {classification}" in error
