"""Behavioral contract for merge-aware worktree-scope validation."""

from __future__ import annotations

import subprocess
from pathlib import Path

from maid_runner.core.chain import ManifestChain
from maid_runner.core.result import ErrorCode
from maid_runner.core.worktree import changed_files, validate_worktree_scope


def _git(
    root: Path, *args: str, check: bool = True
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        (
            "git",
            "-c",
            "core.hooksPath=/dev/null",
            "-c",
            "user.name=MAID Test",
            "-c",
            "user.email=maid-test@example.com",
            *args,
        ),
        cwd=root,
        check=check,
        capture_output=True,
        text=True,
    )


def _conflicted_merge_project(tmp_path: Path) -> ManifestChain:
    (tmp_path / "manifests").mkdir()
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "conflict.py").write_text("VALUE = 'base'\n")
    (tmp_path / "manifests" / "resolve-merge.manifest.yaml").write_text(
        """schema: "2"
goal: "Resolve merge conflict"
type: fix
created: "2026-08-20T00:00:00Z"
files:
  scope:
    - path: src/conflict.py
      reason: "The current task owns only the conflict resolution."
validate:
  - python -c "print('ok')"
"""
    )
    _git(tmp_path, "init", "-q", "-b", "main")
    _git(tmp_path, "add", ".")
    _git(tmp_path, "commit", "-q", "-m", "base")

    _git(tmp_path, "checkout", "-q", "-b", "incoming")
    (tmp_path / "src" / "conflict.py").write_text("VALUE = 'incoming'\n")
    (tmp_path / "src" / "incoming.py").write_text("VALUE = 'incoming-only'\n")
    _git(tmp_path, "add", ".")
    _git(tmp_path, "commit", "-q", "-m", "incoming")

    _git(tmp_path, "checkout", "-q", "main")
    (tmp_path / "src" / "conflict.py").write_text("VALUE = 'current'\n")
    _git(tmp_path, "add", ".")
    _git(tmp_path, "commit", "-q", "-m", "current")
    merge = _git(tmp_path, "merge", "--no-commit", "incoming", check=False)
    assert merge.returncode == 1
    assert _git(tmp_path, "rev-parse", "--verify", "AUTO_MERGE").returncode == 0

    (tmp_path / "src" / "conflict.py").write_text("VALUE = 'resolved'\n")
    _git(tmp_path, "add", "src/conflict.py")
    return ManifestChain(tmp_path / "manifests", project_root=tmp_path)


def _scope_error_paths(errors) -> set[str]:
    return {
        error.location.file
        for error in errors
        if error.code == ErrorCode.CHANGED_FILE_OUTSIDE_MANIFEST_SCOPE
        and error.location is not None
    }


def test_worktree_scope_ignores_unchanged_incoming_merge_files(tmp_path: Path) -> None:
    chain = _conflicted_merge_project(tmp_path)

    paths = changed_files(tmp_path)
    errors = validate_worktree_scope(tmp_path, chain)

    assert paths == ("src/conflict.py",)
    assert errors == []


def test_worktree_scope_fails_closed_when_auto_merge_baseline_is_missing(
    tmp_path: Path,
) -> None:
    chain = _conflicted_merge_project(tmp_path)
    _git(tmp_path, "update-ref", "-d", "AUTO_MERGE")

    errors = validate_worktree_scope(tmp_path, chain)

    assert "src/incoming.py" in _scope_error_paths(errors)
