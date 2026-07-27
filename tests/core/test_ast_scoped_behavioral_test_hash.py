"""Behavioral tests for AST-scoped plan-lock behavioral test hashing."""

from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from maid_runner.cli.commands.plan import cmd_plan_status
from maid_runner.core import plan_lock as plan_lock_mod
from maid_runner.core.chain import ManifestChain
from maid_runner.core.plan_lock import create_plan_lock, enforce_plan_locks
from maid_runner.core.result import ErrorCode
from maid_runner.core.supersession_audit import compute_manifest_hash


_BASELINE_MANIFEST = """\
schema: "2"
goal: "Demo task"
type: feature
created: "2026-06-10T00:00:00Z"
description: |
  Baseline for AST-scoped behavioral test hashing.
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

_BASELINE_TEST = """\
from src.demo import demo


def test_demo():
    assert demo() == 1
"""

_FORMATTED_TEST = """\
from src.demo import demo  # import kept


def test_demo():


    assert demo() == 1  # same assertion
"""

_ASSERTION_CHANGED_TEST = """\
from src.demo import demo


def test_demo():
    assert demo() == 2
"""

_IMPORT_CHANGED_TEST = """\
from src.other import demo


def test_demo():
    assert demo() == 1
"""

_STRING_CHANGED_TEST = """\
from src.demo import demo


def test_demo():
    assert demo() == 1
    assert "changed" == "changed"
"""


def _compute_behavioral_test_hash(path: Path) -> str:
    assert hasattr(
        plan_lock_mod, "compute_behavioral_test_hash"
    ), "compute_behavioral_test_hash must be public on plan_lock"
    return plan_lock_mod.compute_behavioral_test_hash(path)


def _test_hash_matches(lock_hash: str, path: Path) -> bool:
    assert hasattr(
        plan_lock_mod, "test_hash_matches"
    ), "test_hash_matches must be public on plan_lock"
    return plan_lock_mod.test_hash_matches(lock_hash, path)


def _write_project(tmp_path: Path) -> Path:
    (tmp_path / "manifests").mkdir(exist_ok=True)
    (tmp_path / "tests").mkdir(exist_ok=True)
    (tmp_path / "src").mkdir(exist_ok=True)
    (tmp_path / "src" / "demo.py").write_text(
        "def demo():\n    return 1\n", encoding="utf-8"
    )
    (tmp_path / "tests" / "test_demo.py").write_text(_BASELINE_TEST, encoding="utf-8")
    manifest_path = tmp_path / "manifests" / "demo-task.manifest.yaml"
    manifest_path.write_text(_BASELINE_MANIFEST, encoding="utf-8")
    return manifest_path


def _status_args(manifest_path: Path, project_root: Path) -> SimpleNamespace:
    return SimpleNamespace(
        plan_command="status",
        manifest_path=str(manifest_path),
        project_root=str(project_root),
        json=True,
    )


def test_pyast_hash_ignores_whitespace_and_comment_only_edits(tmp_path: Path) -> None:
    baseline = tmp_path / "baseline.py"
    formatted = tmp_path / "formatted.py"
    baseline.write_text(_BASELINE_TEST, encoding="utf-8")
    formatted.write_text(_FORMATTED_TEST, encoding="utf-8")

    left = _compute_behavioral_test_hash(baseline)
    right = _compute_behavioral_test_hash(formatted)

    assert left == right
    assert left.startswith("sha256-pyast:")


def test_pyast_hash_tracks_assertion_and_import_changes(tmp_path: Path) -> None:
    baseline = tmp_path / "baseline.py"
    baseline.write_text(_BASELINE_TEST, encoding="utf-8")
    baseline_hash = _compute_behavioral_test_hash(baseline)

    assertion = tmp_path / "assertion.py"
    assertion.write_text(_ASSERTION_CHANGED_TEST, encoding="utf-8")
    import_changed = tmp_path / "import_changed.py"
    import_changed.write_text(_IMPORT_CHANGED_TEST, encoding="utf-8")
    string_changed = tmp_path / "string_changed.py"
    string_changed.write_text(_STRING_CHANGED_TEST, encoding="utf-8")

    for variant in (assertion, import_changed, string_changed):
        assert _compute_behavioral_test_hash(variant) != baseline_hash


def test_non_python_behavioral_test_remains_byte_hashed(tmp_path: Path) -> None:
    sql = tmp_path / "test_demo.sql"
    sql.write_text("SELECT 1;\n", encoding="utf-8")

    digest = _compute_behavioral_test_hash(sql)

    assert digest.startswith("sha256:")
    assert not digest.startswith("sha256-pyast:")
    assert digest == compute_manifest_hash(sql)


def test_test_hash_matches_dispatches_on_prefix(tmp_path: Path) -> None:
    path = tmp_path / "test_demo.py"
    path.write_text(_BASELINE_TEST, encoding="utf-8")
    legacy_hash = compute_manifest_hash(path)
    pyast_hash = _compute_behavioral_test_hash(path)

    assert _test_hash_matches(legacy_hash, path) is True
    assert _test_hash_matches(pyast_hash, path) is True

    path.write_text(_FORMATTED_TEST, encoding="utf-8")
    assert _test_hash_matches(legacy_hash, path) is False
    assert _test_hash_matches(pyast_hash, path) is True

    path.write_text(_ASSERTION_CHANGED_TEST, encoding="utf-8")
    assert _test_hash_matches(pyast_hash, path) is False
    assert _test_hash_matches("sha256-unknown:deadbeef", path) is False
    assert _test_hash_matches("not-a-hash", path) is False


def test_new_locks_store_pyast_prefixed_python_test_hashes(tmp_path: Path) -> None:
    manifest_path = _write_project(tmp_path)

    lock = create_plan_lock(manifest_path, tmp_path)

    assert lock.test_hashes
    assert all(
        path.endswith(".py") and digest.startswith("sha256-pyast:")
        for path, digest in lock.test_hashes.items()
    )


def test_plan_status_and_enforce_tolerate_formatter_only_python_edits(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    manifest_path = _write_project(tmp_path)
    lock_path = tmp_path / ".maid" / "plan-locks" / "demo-task.lock.json"
    create_plan_lock(manifest_path, tmp_path).save(lock_path)

    test_path = tmp_path / "tests" / "test_demo.py"
    test_path.write_text(_FORMATTED_TEST, encoding="utf-8")

    exit_code = cmd_plan_status(_status_args(manifest_path, tmp_path))
    payload = json.loads(capsys.readouterr().out)
    assert exit_code == 0
    assert payload["test_files"]["tests/test_demo.py"]["match"] is True

    errors = enforce_plan_locks(
        ManifestChain(tmp_path / "manifests", tmp_path),
        tmp_path,
        require_plan_lock=True,
        require_red_evidence=False,
    )
    assert ErrorCode.BEHAVIORAL_TEST_MODIFIED_AFTER_LOCK not in {
        error.code for error in errors
    }

    test_path.write_text(_ASSERTION_CHANGED_TEST, encoding="utf-8")
    exit_code = cmd_plan_status(_status_args(manifest_path, tmp_path))
    payload = json.loads(capsys.readouterr().out)
    assert exit_code == 1
    assert payload["test_files"]["tests/test_demo.py"]["match"] is False

    errors = enforce_plan_locks(
        ManifestChain(tmp_path / "manifests", tmp_path),
        tmp_path,
        require_plan_lock=True,
        require_red_evidence=False,
    )
    assert ErrorCode.BEHAVIORAL_TEST_MODIFIED_AFTER_LOCK in {
        error.code for error in errors
    }


def test_pyast_hash_raises_on_unparseable_python(tmp_path: Path) -> None:
    assert hasattr(
        plan_lock_mod, "compute_behavioral_test_hash"
    ), "compute_behavioral_test_hash must be public on plan_lock"
    bad = tmp_path / "broken.py"
    bad.write_text("def broken(:\n", encoding="utf-8")

    with pytest.raises(SyntaxError):
        plan_lock_mod.compute_behavioral_test_hash(bad)
