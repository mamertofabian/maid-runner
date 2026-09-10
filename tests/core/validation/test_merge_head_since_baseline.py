"""Behavioral contract for merge-aware explicit HEAD task baselines."""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from maid_runner.core.worktree import ChangedScopeBaseline, changed_files_since


def _git(
    root: Path,
    *args: str,
    check: bool = True,
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


def _conflicted_merge(root: Path) -> str:
    (root / "src").mkdir()
    (root / "src" / "conflict.py").write_text("VALUE = 'base'\n")
    _git(root, "init", "-q", "-b", "main")
    _git(root, "add", ".")
    _git(root, "commit", "-q", "-m", "base")

    _git(root, "checkout", "-q", "-b", "incoming")
    (root / "src" / "conflict.py").write_text("VALUE = 'incoming'\n")
    (root / "src" / "incoming.py").write_text("VALUE = 'incoming-only'\n")
    _git(root, "add", ".")
    _git(root, "commit", "-q", "-m", "incoming")

    _git(root, "checkout", "-q", "main")
    (root / "src" / "conflict.py").write_text("VALUE = 'current'\n")
    (root / "src" / "current.py").write_text("VALUE = 'current-only'\n")
    _git(root, "add", ".")
    _git(root, "commit", "-q", "-m", "current")
    local_head = _git(root, "rev-parse", "HEAD").stdout.strip()

    merge = _git(root, "merge", "--no-commit", "incoming", check=False)
    assert merge.returncode == 1
    (root / "src" / "conflict.py").write_text("VALUE = 'resolved'\n")
    _git(root, "add", "src/conflict.py")
    return local_head


def _octopus_merge(root: Path) -> None:
    (root / "src").mkdir()
    (root / "src" / "base.py").write_text("VALUE = 'base'\n")
    _git(root, "init", "-q", "-b", "main")
    _git(root, "add", ".")
    _git(root, "commit", "-q", "-m", "base")

    _git(root, "checkout", "-q", "-b", "incoming-one")
    (root / "src" / "one.py").write_text("VALUE = 'one'\n")
    _git(root, "add", ".")
    _git(root, "commit", "-q", "-m", "incoming one")

    _git(root, "checkout", "-q", "main")
    _git(root, "checkout", "-q", "-b", "incoming-two")
    (root / "src" / "two.py").write_text("VALUE = 'two'\n")
    _git(root, "add", ".")
    _git(root, "commit", "-q", "-m", "incoming two")

    _git(root, "checkout", "-q", "main")
    (root / "src" / "current.py").write_text("VALUE = 'current'\n")
    _git(root, "add", ".")
    _git(root, "commit", "-q", "-m", "current")
    merge = _git(
        root,
        "merge",
        "--no-commit",
        "incoming-one",
        "incoming-two",
        check=False,
    )
    assert merge.returncode == 0


def test_head_since_uses_merge_head_during_in_progress_merge(tmp_path: Path) -> None:
    _conflicted_merge(tmp_path)

    paths = changed_files_since(
        tmp_path,
        ChangedScopeBaseline(source="since", commitish="HEAD"),
    )

    assert set(paths) == {"src/conflict.py", "src/current.py"}
    assert "src/incoming.py" not in paths


def test_literal_commit_baseline_is_not_rewritten_during_merge(
    tmp_path: Path,
) -> None:
    local_head = _conflicted_merge(tmp_path)

    paths = changed_files_since(
        tmp_path,
        ChangedScopeBaseline(source="since", commitish=local_head),
    )

    assert set(paths) == {"src/conflict.py", "src/incoming.py"}
    assert "src/current.py" not in paths


@pytest.mark.parametrize("source", ["base-ref", "metadata"])
def test_non_since_head_baseline_is_not_rewritten_during_merge(
    tmp_path: Path,
    source: str,
) -> None:
    _conflicted_merge(tmp_path)

    paths = changed_files_since(
        tmp_path,
        ChangedScopeBaseline(source=source, commitish="HEAD"),
    )

    assert set(paths) == {"src/conflict.py", "src/incoming.py"}
    assert "src/current.py" not in paths


def test_head_since_remains_literal_outside_merge(tmp_path: Path) -> None:
    (tmp_path / "src").mkdir()
    changed = tmp_path / "src" / "current.py"
    changed.write_text("VALUE = 'before'\n")
    _git(tmp_path, "init", "-q", "-b", "main")
    _git(tmp_path, "add", ".")
    _git(tmp_path, "commit", "-q", "-m", "base")
    changed.write_text("VALUE = 'after'\n")

    paths = changed_files_since(
        tmp_path,
        ChangedScopeBaseline(source="since", commitish="HEAD"),
    )

    assert paths == ("src/current.py",)


def test_invalid_merge_head_falls_back_to_literal_head(tmp_path: Path) -> None:
    (tmp_path / "src").mkdir()
    changed = tmp_path / "src" / "current.py"
    changed.write_text("VALUE = 'before'\n")
    _git(tmp_path, "init", "-q", "-b", "main")
    _git(tmp_path, "add", ".")
    _git(tmp_path, "commit", "-q", "-m", "base")
    changed.write_text("VALUE = 'after'\n")
    (tmp_path / ".git" / "MERGE_HEAD").write_text("not-a-git-object\n")

    paths = changed_files_since(
        tmp_path,
        ChangedScopeBaseline(source="since", commitish="HEAD"),
    )

    assert paths == ("src/current.py",)


def test_multiple_merge_heads_fall_back_to_literal_head(tmp_path: Path) -> None:
    _octopus_merge(tmp_path)

    paths = changed_files_since(
        tmp_path,
        ChangedScopeBaseline(source="since", commitish="HEAD"),
    )

    assert set(paths) == {"src/one.py", "src/two.py"}
    assert "src/current.py" not in paths
