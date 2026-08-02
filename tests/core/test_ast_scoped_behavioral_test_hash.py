"""Behavioral tests for AST-scoped plan-lock behavioral test hashing."""

from __future__ import annotations

import ast
import hashlib
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

_CROSS_INTERPRETER_TEST = """\
from __future__ import annotations

MARKERS = (b"\\x00", 1 + 2j, ..., -0.0)


def choose(value: int | None = None) -> str:
    if value is None:
        return "missing"
    return f"value={value}"
"""

_CROSS_INTERPRETER_HASH = (
    "sha256-pyast:v2:"
    "6c231e332a5a799c74f9ca8b695acb2333df80af6ba3bef8b735901dd18bf881"
)

_LONE_SURROGATE_TEST = 'VALUE = "\\ud800"\n'
_SURROGATE_PAIR_TEST = 'VALUE = "\\ud83d\\ude00"\n'
_ASTRAL_CHARACTER_TEST = 'VALUE = "😀"\n'
_SURROGATE_HASHES = (
    "sha256-pyast:v2:0b8ca8f018a6176f0e0efd3b9efa4b3153b0649984a823c067d0563149efac99",
    "sha256-pyast:v2:971d6e8e4740b4ff2a01a2f30bc32e1d7b4f158fc52989fb21fff971ebbf386b",
    "sha256-pyast:v2:c88c235a1746ec2f174c7a312862e679f0992e065c35851c75522da58b014e5d",
)


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
    assert left.startswith("sha256-pyast:v2:")


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


def test_test_hash_matches_accepts_historical_pyast_v1(tmp_path: Path) -> None:
    path = tmp_path / "test_demo.py"
    path.write_text(_BASELINE_TEST, encoding="utf-8")
    canonical = ast.dump(
        ast.parse(_BASELINE_TEST),
        annotate_fields=True,
        include_attributes=False,
    )
    legacy_hash = "sha256-pyast:" + hashlib.sha256(canonical.encode()).hexdigest()

    assert _test_hash_matches(legacy_hash, path) is True

    path.write_text(_FORMATTED_TEST, encoding="utf-8")
    assert _test_hash_matches(legacy_hash, path) is True

    path.write_text(_ASSERTION_CHANGED_TEST, encoding="utf-8")
    assert _test_hash_matches(legacy_hash, path) is False


def test_new_locks_store_pyast_prefixed_python_test_hashes(tmp_path: Path) -> None:
    manifest_path = _write_project(tmp_path)

    lock = create_plan_lock(manifest_path, tmp_path)

    assert lock.test_hashes
    assert all(
        path.endswith(".py") and digest.startswith("sha256-pyast:v2:")
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


def test_pyast_v2_hash_has_cross_interpreter_golden_digest(tmp_path: Path) -> None:
    path = tmp_path / "test_portable.py"
    path.write_text(_CROSS_INTERPRETER_TEST, encoding="utf-8")

    assert _compute_behavioral_test_hash(path) == _CROSS_INTERPRETER_HASH


def test_pyast_v2_hash_handles_surrogate_escapes_without_collisions(
    tmp_path: Path,
) -> None:
    sources = (
        _LONE_SURROGATE_TEST,
        _SURROGATE_PAIR_TEST,
        _ASTRAL_CHARACTER_TEST,
    )
    digests = []

    for index, source in enumerate(sources):
        path = tmp_path / f"test_unicode_{index}.py"
        path.write_text(source, encoding="utf-8")
        digest = _compute_behavioral_test_hash(path)
        assert digest.startswith("sha256-pyast:v2:")
        digests.append(digest)

    assert digests == list(_SURROGATE_HASHES)
    assert len(set(digests)) == len(sources)
