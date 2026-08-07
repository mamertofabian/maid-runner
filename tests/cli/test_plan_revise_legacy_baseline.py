"""Regression coverage for preserving legacy-baseline evidence on revise."""

from __future__ import annotations

import json
from pathlib import Path
import subprocess
from types import SimpleNamespace

import pytest

from maid_runner.cli.commands._main import build_parser
from maid_runner.cli.commands.plan import cmd_plan_lock, cmd_plan_revise
from maid_runner.core.chain import ManifestChain
from maid_runner.core.plan_lock import (
    PlanLock,
    default_plan_lock_path,
    enforce_plan_locks,
    revise_plan_lock,
)


def _git(project_root: Path, *args: str) -> None:
    subprocess.run(
        ["git", *args],
        cwd=project_root,
        check=True,
        capture_output=True,
        text=True,
    )


def _write_legacy_project(project_root: Path) -> Path:
    for directory in ("manifests", "src", "tests", "scripts"):
        (project_root / directory).mkdir(parents=True, exist_ok=True)
    (project_root / "src" / "demo.py").write_text(
        "def demo() -> int:\n    return 1\n", encoding="utf-8"
    )
    (project_root / "tests" / "test_demo.py").write_text(
        "from src.demo import demo\n\n\ndef test_demo() -> None:\n"
        "    assert demo() == 1\n",
        encoding="utf-8",
    )
    (project_root / "scripts" / "validate.py").write_text(
        "raise SystemExit(0)\n", encoding="utf-8"
    )
    manifest_path = project_root / "manifests" / "legacy-task.manifest.yaml"
    manifest_path.write_text(
        """schema: "2"
goal: "Completed legacy task"
type: fix
created: "2026-05-01T00:00:00Z"
files:
  edit:
    - path: src/demo.py
      artifacts:
        - kind: function
          name: demo
          args: []
          returns: int
  read:
    - tests/test_demo.py
validate:
  - python scripts/validate.py
""",
        encoding="utf-8",
    )
    (project_root / ".gitignore").write_text(".maid/\n", encoding="utf-8")
    _git(project_root, "init", "-q")
    _git(project_root, "config", "user.email", "maid-test@example.com")
    _git(project_root, "config", "user.name", "MAID Test")
    _git(project_root, "add", ".")
    _git(project_root, "commit", "-qm", "completed legacy task")
    return manifest_path


def _lock_args(manifest_path: Path, project_root: Path) -> SimpleNamespace:
    return SimpleNamespace(
        manifest_path=str(manifest_path),
        project_root=str(project_root),
        legacy_baseline=True,
        reason="Audited completed work",
        no_run=False,
        json=False,
    )


def _revise_args(
    manifest_path: Path,
    project_root: Path,
    *,
    preserve: bool = False,
    no_run: bool = False,
) -> SimpleNamespace:
    return SimpleNamespace(
        manifest_path=str(manifest_path),
        project_root=str(project_root),
        reason="Refresh shared behavioral test hash",
        no_run=no_run,
        preserve_red_evidence=preserve,
        stash_implementation=False,
        allow_sibling_dirty=False,
        test_only_green=False,
        json=False,
    )


def _create_legacy_lock(project_root: Path) -> tuple[Path, Path, dict]:
    manifest_path = _write_legacy_project(project_root)
    assert cmd_plan_lock(_lock_args(manifest_path, project_root)) == 0
    lock_path = default_plan_lock_path(project_root, "legacy-task")
    payload = json.loads(lock_path.read_text(encoding="utf-8"))
    assert payload["red_evidence"] is None
    assert payload["legacy_baseline"]["kind"] == "legacy_baseline"
    return manifest_path, lock_path, payload


def test_no_run_revise_retains_legacy_baseline(tmp_path: Path) -> None:
    manifest_path, _lock_path, original = _create_legacy_lock(tmp_path)

    revised = revise_plan_lock(
        PlanLock.load(_lock_path),
        manifest_path,
        tmp_path,
        "Refresh hashes without running validation",
    )

    assert revised.red_evidence is None
    assert revised.legacy_baseline == original["legacy_baseline"]


def test_explicit_preserve_refreshes_shared_test_hash_and_keeps_legacy_baseline(
    tmp_path: Path, capsys
) -> None:
    manifest_path, lock_path, original = _create_legacy_lock(tmp_path)
    capsys.readouterr()
    test_path = tmp_path / "tests" / "test_demo.py"
    test_path.write_text(
        test_path.read_text(encoding="utf-8")
        + "\n\ndef test_unrelated_shared_behavior() -> None:\n    assert True\n",
        encoding="utf-8",
    )

    exit_code = cmd_plan_revise(_revise_args(manifest_path, tmp_path, preserve=True))

    revised = json.loads(lock_path.read_text(encoding="utf-8"))
    assert exit_code == 0
    assert revised["test_hashes"] != original["test_hashes"]
    assert revised["legacy_baseline"] == original["legacy_baseline"]
    assert revised["red_evidence"] is None
    assert (
        "legacy-baseline evidence preserved by explicit request"
        in capsys.readouterr().out
    )


def test_plain_contract_preserving_revise_keeps_legacy_baseline(
    tmp_path: Path, capsys
) -> None:
    manifest_path, lock_path, original = _create_legacy_lock(tmp_path)
    capsys.readouterr()

    assert cmd_plan_revise(_revise_args(manifest_path, tmp_path)) == 0

    revised = json.loads(lock_path.read_text(encoding="utf-8"))
    assert revised["legacy_baseline"] == original["legacy_baseline"]
    assert revised["red_evidence"] is None
    assert (
        "legacy-baseline evidence preserved because the revision is contract-preserving"
        in capsys.readouterr().out
    )
    errors = enforce_plan_locks(
        ManifestChain(tmp_path / "manifests", tmp_path),
        tmp_path,
        require_plan_lock=True,
        require_red_evidence=True,
        changed_paths={"manifests/legacy-task.manifest.yaml"},
        plan_lock_scope="task",
    )
    assert errors == ()


def test_explicit_preserve_rejects_invalid_legacy_baseline(
    tmp_path: Path, capsys
) -> None:
    manifest_path, lock_path, original = _create_legacy_lock(tmp_path)
    capsys.readouterr()
    corrupted = dict(original)
    corrupted["legacy_baseline"] = dict(original["legacy_baseline"], green=False)
    lock_path.write_text(json.dumps(corrupted, indent=2), encoding="utf-8")
    before = lock_path.read_bytes()

    exit_code = cmd_plan_revise(_revise_args(manifest_path, tmp_path, preserve=True))

    assert exit_code == 2
    assert lock_path.read_bytes() == before
    assert "requires existing valid" in capsys.readouterr().err


def test_plain_changed_test_replaces_legacy_baseline_with_fresh_red_evidence(
    tmp_path: Path,
) -> None:
    manifest_path, lock_path, _original = _create_legacy_lock(tmp_path)
    test_path = tmp_path / "tests" / "test_demo.py"
    test_path.write_text(
        test_path.read_text(encoding="utf-8").replace("== 1", "== 2"),
        encoding="utf-8",
    )
    (tmp_path / "scripts" / "validate.py").write_text(
        "raise SystemExit(1)\n", encoding="utf-8"
    )

    assert cmd_plan_revise(_revise_args(manifest_path, tmp_path)) == 0

    revised = json.loads(lock_path.read_text(encoding="utf-8"))
    assert revised["red_evidence"]["red"] is True
    assert revised["legacy_baseline"] is None
    errors = enforce_plan_locks(
        ManifestChain(tmp_path / "manifests", tmp_path),
        tmp_path,
        require_plan_lock=True,
        require_red_evidence=True,
        changed_paths={"manifests/legacy-task.manifest.yaml"},
        plan_lock_scope="task",
    )
    assert errors == ()


def test_revise_help_documents_legacy_baseline_preservation(capsys) -> None:
    with pytest.raises(SystemExit) as exc_info:
        build_parser().parse_args(["plan", "revise", "task.manifest.yaml", "--help"])

    assert exc_info.value.code == 0
    help_text = " ".join(capsys.readouterr().out.split())
    assert "valid red, test-only-green, or legacy-" in help_text
    assert "baseline evidence during metadata-only revisions" in help_text


def test_explicit_preserve_rejects_dual_evidence_channels(
    tmp_path: Path, capsys
) -> None:
    manifest_path, lock_path, original = _create_legacy_lock(tmp_path)
    capsys.readouterr()
    corrupted = dict(original)
    corrupted["red_evidence"] = {
        "red": True,
        "commands": [
            {
                "command": "python scripts/validate.py",
                "exit_code": 1,
                "classification": "red",
                "output_tail": "expected failure",
            }
        ],
    }
    lock_path.write_text(json.dumps(corrupted, indent=2), encoding="utf-8")
    before = lock_path.read_bytes()

    assert cmd_plan_revise(_revise_args(manifest_path, tmp_path, preserve=True)) == 2
    assert lock_path.read_bytes() == before
    assert "requires existing valid" in capsys.readouterr().err


def test_no_run_revise_rejects_legacy_command_mismatch(tmp_path: Path, capsys) -> None:
    manifest_path, lock_path, _original = _create_legacy_lock(tmp_path)
    capsys.readouterr()
    manifest_path.write_text(
        manifest_path.read_text(encoding="utf-8").replace(
            "python scripts/validate.py", "python scripts/validate.py --changed"
        ),
        encoding="utf-8",
    )
    before = lock_path.read_bytes()

    assert cmd_plan_revise(_revise_args(manifest_path, tmp_path, no_run=True)) == 2
    assert lock_path.read_bytes() == before
    assert "legacy baseline" in capsys.readouterr().err.lower()


def test_core_fresh_evidence_transition_drops_legacy_baseline(tmp_path: Path) -> None:
    manifest_path, lock_path, _original = _create_legacy_lock(tmp_path)

    revised = revise_plan_lock(
        PlanLock.load(lock_path),
        manifest_path,
        tmp_path,
        "Capture fresh red evidence",
        preserve_legacy_baseline=False,
    )

    assert revised.legacy_baseline is None


def test_legacy_preservation_docs_are_synced() -> None:
    root = Path(__file__).resolve().parents[2]
    anchors = (
        "metadata-only revision carries the",
        "valid command-bound legacy",
        "locks never preserve two evidence classes at once",
    )

    for relative_path in ("docs/maid_specs.md", "maid_runner/docs/maid_specs.md"):
        text = " ".join((root / relative_path).read_text(encoding="utf-8").split())
        for anchor in anchors:
            assert anchor in text
