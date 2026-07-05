"""Regression tests for files.read stash-backed plan-lock revision targets."""

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


def _commit_all(project_root: Path, message: str) -> None:
    _git(project_root, "add", ".")
    _git(project_root, "commit", "-q", "-m", message)


def _lock_args(manifest_path: Path, project_root: Path) -> SimpleNamespace:
    return SimpleNamespace(
        plan_command="lock",
        manifest_path=str(manifest_path),
        project_root=str(project_root),
        no_run=False,
        json=False,
    )


def _revise_args(
    manifest_path: Path,
    project_root: Path,
    reason: str = "review tightened wiring behavior",
) -> SimpleNamespace:
    return SimpleNamespace(
        plan_command="revise",
        manifest_path=str(manifest_path),
        project_root=str(project_root),
        reason=reason,
        no_run=False,
        preserve_red_evidence=False,
        stash_implementation=True,
        json=False,
    )


def _lock_record(project_root: Path, slug: str = "wiring-task") -> dict:
    return json.loads(default_plan_lock_path(project_root, slug).read_text())


def _write_wiring_project(
    project_root: Path,
    *,
    contract: str = "assert demo() == 1 or wired is True",
    test_reads_message: str | None = None,
    extra_read: str = "",
    test_read_path: str = "tests/test_wiring.py",
) -> Path:
    (project_root / "manifests").mkdir(parents=True)
    (project_root / "src").mkdir()
    (project_root / "tests").mkdir()
    (project_root / "src" / "__init__.py").write_text("")
    (project_root / "src" / "demo.py").write_text("def demo() -> int:\n    return 0\n")
    (project_root / "src" / "page.py").write_text("wired = False\n")
    message = f", {test_reads_message!r}" if test_reads_message else ""
    (project_root / "tests" / "test_wiring.py").write_text(
        "from src.demo import demo\n"
        "from src.page import wired\n\n\n"
        "def test_wiring_contract():\n"
        f"    {contract}{message}\n"
    )
    manifest_path = project_root / "manifests" / "wiring-task.manifest.yaml"
    manifest_path.write_text(
        f"""schema: "2"
goal: "Wiring task"
type: fix
created: "2026-07-03T00:00:00Z"
files:
  edit:
    - path: src/demo.py
      artifacts:
        - kind: function
          name: demo
          args: []
          returns: int
  read:
    - src/page.py
    - {test_read_path}
{extra_read}validate:
  - python -m pytest -q tests/test_wiring.py
"""
    )
    _git(project_root, "init", "-q")
    _commit_all(project_root, "red wiring contract")
    assert cmd_plan_lock(_lock_args(manifest_path, project_root)) == 0
    _commit_all(project_root, "plan lock")
    return manifest_path


def _implement_demo_and_wiring(project_root: Path) -> None:
    (project_root / "src" / "demo.py").write_text("def demo() -> int:\n    return 1\n")
    (project_root / "src" / "page.py").write_text("wired = True\n")


def test_stash_revise_stashes_dirty_declared_files_read_wiring_path(
    tmp_path: Path,
) -> None:
    manifest_path = _write_wiring_project(tmp_path)
    _implement_demo_and_wiring(tmp_path)

    exit_code = cmd_plan_revise(_revise_args(manifest_path, tmp_path))

    assert exit_code == 0
    assert (tmp_path / "src" / "demo.py").read_text() == (
        "def demo() -> int:\n    return 1\n"
    )
    assert (tmp_path / "src" / "page.py").read_text() == "wired = True\n"
    assert _git(tmp_path, "stash", "list") == ""
    record = _lock_record(tmp_path)
    assert record["revision"] == 2
    assert record["red_evidence"]["red"] is True
    assert record["red_evidence"]["commands"][0]["classification"] == "red"


def test_stash_revise_restores_files_read_changes_after_capture(
    tmp_path: Path,
) -> None:
    success_manifest = _write_wiring_project(tmp_path / "success")
    _implement_demo_and_wiring(tmp_path / "success")

    success_exit = cmd_plan_revise(_revise_args(success_manifest, tmp_path / "success"))

    assert success_exit == 0
    assert (tmp_path / "success" / "src" / "page.py").read_text() == "wired = True\n"

    refused_root = tmp_path / "refused"
    refused_manifest = _write_wiring_project(refused_root)
    _implement_demo_and_wiring(refused_root)
    test_path = refused_root / "tests" / "test_wiring.py"
    test_path.write_text(
        "from src.demo import demo\n\n\n"
        "def test_wiring_contract():\n"
        "    assert demo() in {0, 1}\n"
    )
    original_lock = default_plan_lock_path(refused_root, "wiring-task").read_bytes()

    refused_exit = cmd_plan_revise(_revise_args(refused_manifest, refused_root))

    assert refused_exit == 1
    assert (
        default_plan_lock_path(refused_root, "wiring-task").read_bytes()
        == original_lock
    )
    assert (refused_root / "src" / "page.py").read_text() == "wired = True\n"
    assert _git(refused_root, "stash", "list") == ""


def test_stash_revise_still_refuses_undeclared_dirty_paths(
    tmp_path: Path,
    capsys,
) -> None:
    manifest_path = _write_wiring_project(tmp_path)
    _implement_demo_and_wiring(tmp_path)
    (tmp_path / "README.md").write_text("unrelated work\n")
    lock_path = default_plan_lock_path(tmp_path, "wiring-task")
    original_lock = lock_path.read_bytes()

    exit_code = cmd_plan_revise(_revise_args(manifest_path, tmp_path))

    output = capsys.readouterr()
    message = output.out + output.err
    assert exit_code == 2
    assert lock_path.read_bytes() == original_lock
    assert (tmp_path / "src" / "page.py").read_text() == "wired = True\n"
    assert _git(tmp_path, "stash", "list") == ""
    assert "README.md" in message
    assert "files.read" in message


def test_stash_revise_never_stashes_test_files_declared_under_files_read(
    tmp_path: Path,
) -> None:
    manifest_path = _write_wiring_project(
        tmp_path,
        contract="assert demo() == 1",
        test_reads_message="ORIGINAL_TEST_SHOULD_NOT_BE_RESTORED_FOR_CAPTURE",
    )
    _implement_demo_and_wiring(tmp_path)
    (tmp_path / "tests" / "test_wiring.py").write_text(
        "from src.demo import demo\n"
        "from src.page import wired\n\n\n"
        "def test_wiring_contract():\n"
        "    assert demo() == 2 and wired is True, 'TIGHTENED_TEST_VISIBLE'\n"
    )

    exit_code = cmd_plan_revise(_revise_args(manifest_path, tmp_path))

    record = _lock_record(tmp_path)
    assert exit_code == 0
    assert record["red_evidence"]["red"] is True
    assert (
        "TIGHTENED_TEST_VISIBLE" in record["red_evidence"]["commands"][0]["output_tail"]
    )
    assert (tmp_path / "tests" / "test_wiring.py").read_text().count(
        "TIGHTENED_TEST_VISIBLE"
    ) == 1


def test_stash_revise_counts_files_read_targets_for_dirty_guard(
    tmp_path: Path,
) -> None:
    manifest_path = _write_wiring_project(
        tmp_path,
        contract="assert wired is True",
    )
    (tmp_path / "src" / "page.py").write_text("wired = True\n")

    exit_code = cmd_plan_revise(_revise_args(manifest_path, tmp_path))

    assert exit_code == 0
    assert (tmp_path / "src" / "demo.py").read_text() == (
        "def demo() -> int:\n    return 0\n"
    )
    assert (tmp_path / "src" / "page.py").read_text() == "wired = True\n"
    assert _lock_record(tmp_path)["red_evidence"]["red"] is True


def test_stash_revise_keeps_backslash_files_read_test_visible(
    tmp_path: Path,
) -> None:
    manifest_path = _write_wiring_project(
        tmp_path,
        contract="assert demo() == 1",
        test_read_path="tests\\test_wiring.py",
    )
    _implement_demo_and_wiring(tmp_path)
    (tmp_path / "tests" / "test_wiring.py").write_text(
        "from src.demo import demo\n"
        "from src.page import wired\n\n\n"
        "def test_wiring_contract():\n"
        "    assert demo() == 2 and wired is True, 'BACKSLASH_TEST_VISIBLE'\n"
    )

    exit_code = cmd_plan_revise(_revise_args(manifest_path, tmp_path))

    record = _lock_record(tmp_path)
    assert exit_code == 0
    assert record["red_evidence"]["red"] is True
    assert (
        "BACKSLASH_TEST_VISIBLE" in record["red_evidence"]["commands"][0]["output_tail"]
    )
