"""Regression coverage for declared SQL tests during stash-backed revision."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path
from types import SimpleNamespace

from maid_runner.cli.commands.plan import cmd_plan_lock, cmd_plan_revise
from maid_runner.core.plan_lock import default_plan_lock_path


def _git(project_root: Path, *args: str) -> str:
    result = subprocess.run(
        [
            "git",
            "-c",
            "user.name=maid-test",
            "-c",
            "user.email=maid-test@example.com",
            *args,
        ],
        cwd=project_root,
        check=True,
        text=True,
        capture_output=True,
    )
    return result.stdout


def _lock_args(manifest_path: Path, project_root: Path) -> SimpleNamespace:
    return SimpleNamespace(
        plan_command="lock",
        manifest_path=str(manifest_path),
        project_root=str(project_root),
        no_run=False,
        legacy_baseline=False,
        reason=None,
        json=False,
    )


def _revise_args(manifest_path: Path, project_root: Path) -> SimpleNamespace:
    return SimpleNamespace(
        plan_command="revise",
        manifest_path=str(manifest_path),
        project_root=str(project_root),
        reason="review added the declared pgTAP contract",
        no_run=False,
        preserve_red_evidence=False,
        stash_implementation=True,
        json=False,
    )


def test_stash_implementation_keeps_declared_sql_test_visible(
    tmp_path: Path,
) -> None:
    (tmp_path / "README.md").write_text("fixture repository\n")
    deleted_test_path = tmp_path / "tests" / "obsolete.test.js"
    deleted_test_path.parent.mkdir()
    deleted_test_path.write_text("export const obsolete = true;\n")
    _git(tmp_path, "init", "-q")
    _git(tmp_path, "add", "README.md", "tests/obsolete.test.js")
    _git(tmp_path, "commit", "-q", "-m", "baseline")

    manifest_dir = tmp_path / "manifests"
    sql_test_paths = (
        tmp_path / "supabase" / "tests" / "demo.test.sql",
        tmp_path / "supabase" / "tests" / "demo.pgtap.sql",
    )
    scope_test_path = tmp_path / "tests" / "review-contract.test.js"
    implementation_path = tmp_path / "src" / "generated.py"
    manifest_dir.mkdir()
    sql_test_paths[0].parent.mkdir(parents=True)
    for sql_test_path in sql_test_paths:
        sql_test_path.write_text(
            "select plan(1);\nselect ok(true, 'fixture visible');\n"
        )
    scope_test_path.write_text("export const reviewed = true;\n")
    deleted_test_path.unlink()
    manifest_path = manifest_dir / "sql-stash-task.manifest.yaml"
    manifest_path.write_text(
        """schema: "2"
goal: "Protect declared SQL behavior during revision"
type: fix
created: "2026-07-13T09:55:00Z"
files:
  create:
    - path: src/generated.py
      artifacts:
        - kind: attribute
          name: VALUE
          of: module
          type: int
    - path: supabase/tests/demo.test.sql
      artifacts:
        - kind: test_function
          name: declared pgTAP fixture
    - path: supabase/tests/demo.pgtap.sql
      artifacts:
        - kind: test_function
          name: declared nonstandard pgTAP fixture
  scope:
    - path: tests/review-contract.test.js
      reason: Preserve the tightened filename-classified behavioral fixture.
  delete:
    - path: tests/obsolete.test.js
      reason: Preserve the reviewed removal of an obsolete behavioral fixture.
validate:
  - python -c "from pathlib import Path; import sys; sql = all(Path(path).is_file() for path in ['supabase/tests/demo.test.sql', 'supabase/tests/demo.pgtap.sql']); scope_path = Path('tests/review-contract.test.js'); scope = scope_path.is_file() and scope_path.read_text() == 'export const reviewed = true;\\n'; deleted = not Path('tests/obsolete.test.js').exists(); implementation = Path('src/generated.py').is_file(); contract = sql and scope and deleted; sys.exit(1 if contract and not implementation else (0 if contract and implementation else 2))"
"""
    )

    assert cmd_plan_lock(_lock_args(manifest_path, tmp_path)) == 0
    implementation_path.parent.mkdir()
    implementation_path.write_text("VALUE = 1\n")

    exit_code = cmd_plan_revise(_revise_args(manifest_path, tmp_path))

    lock = json.loads(default_plan_lock_path(tmp_path, "sql-stash-task").read_text())
    assert exit_code == 0
    assert all(sql_test_path.is_file() for sql_test_path in sql_test_paths)
    assert all(
        "fixture visible" in sql_test_path.read_text()
        for sql_test_path in sql_test_paths
    )
    assert scope_test_path.read_text() == "export const reviewed = true;\n"
    assert not deleted_test_path.exists()
    assert implementation_path.read_text() == "VALUE = 1\n"
    assert lock["revision"] == 2
    assert lock["red_evidence"]["red"] is True
    assert lock["red_evidence"]["commands"][0]["classification"] == "red"
    assert _git(tmp_path, "stash", "list") == ""
