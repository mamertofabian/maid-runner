"""Behavioral tests for baseline diff-scope collection."""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from maid_runner.core.diff_scope import (
    DiffScopeBaseline,
    DiffScopeError,
    DiffScopeResult,
    FileArtifactDelta,
    collect_diff_scope,
)


def _git(project_dir: Path, *argv: str) -> str:
    result = subprocess.run(
        [
            "git",
            "-c",
            "core.hooksPath=/dev/null",
            "-c",
            "user.email=test@example.com",
            "-c",
            "user.name=Test User",
            *argv,
        ],
        cwd=project_dir,
        check=True,
        capture_output=True,
        text=True,
    )
    return result.stdout.strip()


def _init_repo(project_dir: Path) -> None:
    _git(project_dir, "init")


def _commit_all(project_dir: Path, message: str = "commit") -> str:
    _git(project_dir, "add", ".")
    _git(project_dir, "commit", "-m", message)
    return _git(project_dir, "rev-parse", "HEAD")


def _write(project_dir: Path, rel_path: str, content: str) -> None:
    path = project_dir / rel_path
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content)


def _write_bytes(project_dir: Path, rel_path: str, content: bytes) -> None:
    path = project_dir / rel_path
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(content)


def _delta_for(result: DiffScopeResult, path: str) -> FileArtifactDelta:
    for delta in result.deltas:
        if delta.path == path:
            return delta
    raise AssertionError(f"No delta found for {path}")


def _names(artifacts) -> list[str]:
    return [artifact.name for artifact in artifacts]


BASELINE_MODULE = (
    "def keep(x: int) -> int:\n"
    "    return x\n"
    "\n"
    "\n"
    "def change(a: int) -> int:\n"
    "    return a\n"
    "\n"
    "\n"
    "def gone() -> None:\n"
    "    return None\n"
)

CURRENT_MODULE = (
    "def keep(x: int) -> int:\n"
    "    return x\n"
    "\n"
    "\n"
    "def change(a: str) -> str:\n"
    "    return a\n"
    "\n"
    "\n"
    "def fresh() -> bool:\n"
    "    return True\n"
)


def test_since_baseline_partitions_created_edited_deleted(tmp_path):
    _init_repo(tmp_path)
    _write(tmp_path, "src/edited.py", "def run() -> str:\n    return 'base'\n")
    _write(tmp_path, "src/deleted.py", "def dead() -> None:\n    return None\n")
    sha = _commit_all(tmp_path, "baseline")
    _write(tmp_path, "src/edited.py", "def run() -> str:\n    return 'changed'\n")
    _write(tmp_path, "src/created.py", "def born() -> None:\n    return None\n")
    (tmp_path / "src/deleted.py").unlink()
    baseline = DiffScopeBaseline(source="since", commitish=sha)

    result = collect_diff_scope(tmp_path, baseline)

    assert isinstance(result, DiffScopeResult)
    assert baseline.source == "since"
    assert baseline.commitish == sha
    assert result.created == ("src/created.py",)
    assert result.edited == ("src/edited.py",)
    assert result.deleted == ("src/deleted.py",)


def test_base_ref_baseline_partitions_from_merge_base(tmp_path):
    _init_repo(tmp_path)
    _write(tmp_path, "src/root.py", "def root() -> None:\n    return None\n")
    _commit_all(tmp_path, "root")
    _git(tmp_path, "checkout", "-b", "parent")
    _write(tmp_path, "src/parent.py", "def parent() -> None:\n    return None\n")
    _commit_all(tmp_path, "parent")
    _git(tmp_path, "checkout", "-b", "feature")
    _write(tmp_path, "src/feature.py", "def feature() -> None:\n    return None\n")

    result = collect_diff_scope(
        tmp_path,
        DiffScopeBaseline(source="base-ref", commitish="parent"),
    )

    assert result.created == ("src/feature.py",)
    assert result.edited == ()
    assert result.deleted == ()


def test_worktree_baseline_partitions_against_head(tmp_path):
    _init_repo(tmp_path)
    _write(tmp_path, "src/edited.py", "def run() -> str:\n    return 'base'\n")
    _write(tmp_path, "src/deleted.py", "def dead() -> None:\n    return None\n")
    _commit_all(tmp_path, "baseline")
    _write(tmp_path, "src/edited.py", "def run() -> str:\n    return 'changed'\n")
    _write(tmp_path, "src/created.py", "def born() -> None:\n    return None\n")
    (tmp_path / "src/deleted.py").unlink()

    result = collect_diff_scope(
        tmp_path,
        DiffScopeBaseline(source="worktree", commitish=None),
    )

    assert result.created == ("src/created.py",)
    assert result.edited == ("src/edited.py",)
    assert result.deleted == ("src/deleted.py",)


def test_worktree_baseline_reports_artifact_deltas_against_head(tmp_path):
    _init_repo(tmp_path)
    _write(tmp_path, "src/mod.py", BASELINE_MODULE)
    _commit_all(tmp_path, "baseline")
    _write(tmp_path, "src/mod.py", CURRENT_MODULE)

    result = collect_diff_scope(
        tmp_path,
        DiffScopeBaseline(source="worktree", commitish=None),
    )

    delta = _delta_for(result, "src/mod.py")
    assert _names(delta.added) == ["fresh"]
    assert _names(delta.signature_changed) == ["change"]
    assert _names(delta.removed) == ["gone"]


def test_base_ref_baseline_reports_artifact_deltas_from_merge_base(tmp_path):
    _init_repo(tmp_path)
    _write(tmp_path, "src/mod.py", BASELINE_MODULE)
    _commit_all(tmp_path, "root")
    _git(tmp_path, "checkout", "-b", "parent")
    _write(tmp_path, "src/parent.py", "def parent() -> None:\n    return None\n")
    _commit_all(tmp_path, "parent")
    _git(tmp_path, "checkout", "-b", "feature")
    _write(tmp_path, "src/mod.py", CURRENT_MODULE)
    _commit_all(tmp_path, "feature")
    _git(tmp_path, "checkout", "parent")
    _write(tmp_path, "src/mod.py", "def parent_only() -> None:\n    return None\n")
    _commit_all(tmp_path, "parent moves past divergence")
    _git(tmp_path, "checkout", "feature")

    result = collect_diff_scope(
        tmp_path,
        DiffScopeBaseline(source="base-ref", commitish="parent"),
    )

    delta = _delta_for(result, "src/mod.py")
    assert _names(delta.added) == ["fresh"]
    assert _names(delta.signature_changed) == ["change"]
    assert _names(delta.removed) == ["gone"]


def test_edited_file_reports_added_signature_changed_and_removed(tmp_path):
    _init_repo(tmp_path)
    _write(tmp_path, "src/mod.py", BASELINE_MODULE)
    sha = _commit_all(tmp_path, "baseline")
    _write(tmp_path, "src/mod.py", CURRENT_MODULE)

    result = collect_diff_scope(
        tmp_path,
        DiffScopeBaseline(source="since", commitish=sha),
    )

    delta = _delta_for(result, "src/mod.py")
    assert isinstance(delta, FileArtifactDelta)
    assert delta.path == "src/mod.py"
    assert _names(delta.added) == ["fresh"]
    assert _names(delta.signature_changed) == ["change"]
    assert _names(delta.removed) == ["gone"]


def test_signature_changed_carries_current_signature(tmp_path):
    _init_repo(tmp_path)
    _write(tmp_path, "src/mod.py", BASELINE_MODULE)
    sha = _commit_all(tmp_path, "baseline")
    _write(tmp_path, "src/mod.py", CURRENT_MODULE)

    result = collect_diff_scope(
        tmp_path,
        DiffScopeBaseline(source="since", commitish=sha),
    )

    changed = _delta_for(result, "src/mod.py").signature_changed
    assert [artifact.returns for artifact in changed] == ["str"]


def test_created_file_reports_all_public_artifacts_as_added(tmp_path):
    _init_repo(tmp_path)
    _write(tmp_path, "src/anchor.py", "def anchor() -> None:\n    return None\n")
    sha = _commit_all(tmp_path, "baseline")
    _write(tmp_path, "src/mod.py", BASELINE_MODULE)

    result = collect_diff_scope(
        tmp_path,
        DiffScopeBaseline(source="since", commitish=sha),
    )

    delta = _delta_for(result, "src/mod.py")
    assert _names(delta.added) == ["change", "gone", "keep"]
    assert delta.signature_changed == ()
    assert delta.removed == ()


def test_deleted_file_reports_all_public_artifacts_as_removed(tmp_path):
    _init_repo(tmp_path)
    _write(tmp_path, "src/mod.py", BASELINE_MODULE)
    sha = _commit_all(tmp_path, "baseline")
    (tmp_path / "src/mod.py").unlink()

    result = collect_diff_scope(
        tmp_path,
        DiffScopeBaseline(source="since", commitish=sha),
    )

    delta = _delta_for(result, "src/mod.py")
    assert delta.added == ()
    assert delta.signature_changed == ()
    assert _names(delta.removed) == ["change", "gone", "keep"]


def test_identical_inputs_produce_identical_ordered_results(tmp_path):
    _init_repo(tmp_path)
    _write(tmp_path, "src/anchor.py", "def anchor() -> None:\n    return None\n")
    sha = _commit_all(tmp_path, "baseline")
    _write(tmp_path, "src/zeta.py", "def zeta() -> None:\n    return None\n")
    _write(tmp_path, "src/alpha.py", BASELINE_MODULE)
    baseline = DiffScopeBaseline(source="since", commitish=sha)

    first = collect_diff_scope(tmp_path, baseline)
    second = collect_diff_scope(tmp_path, baseline)

    assert first == second
    assert first.created == tuple(sorted(first.created))
    assert [delta.path for delta in first.deltas] == sorted(
        delta.path for delta in first.deltas
    )


def test_missing_commitish_raises_diff_scope_error(tmp_path):
    _init_repo(tmp_path)
    _write(tmp_path, "src/mod.py", BASELINE_MODULE)
    _commit_all(tmp_path, "baseline")

    with pytest.raises(DiffScopeError):
        collect_diff_scope(
            tmp_path,
            DiffScopeBaseline(source="since", commitish=None),
        )


def test_invalid_commitish_raises_diff_scope_error(tmp_path):
    _init_repo(tmp_path)
    _write(tmp_path, "src/mod.py", BASELINE_MODULE)
    _commit_all(tmp_path, "baseline")

    with pytest.raises(DiffScopeError):
        collect_diff_scope(
            tmp_path,
            DiffScopeBaseline(source="since", commitish="not-a-commit"),
        )


def test_unknown_baseline_source_raises_diff_scope_error(tmp_path):
    _init_repo(tmp_path)
    _write(tmp_path, "src/mod.py", BASELINE_MODULE)
    _commit_all(tmp_path, "baseline")

    with pytest.raises(DiffScopeError):
        collect_diff_scope(
            tmp_path,
            DiffScopeBaseline(source="guess", commitish=None),
        )


def test_private_artifacts_are_excluded_from_deltas(tmp_path):
    _init_repo(tmp_path)
    _write(tmp_path, "src/anchor.py", "def anchor() -> None:\n    return None\n")
    sha = _commit_all(tmp_path, "baseline")
    _write(
        tmp_path,
        "src/mod.py",
        "def visible() -> None:\n"
        "    return None\n"
        "\n"
        "\n"
        "def _hidden() -> None:\n"
        "    return None\n",
    )

    result = collect_diff_scope(
        tmp_path,
        DiffScopeBaseline(source="since", commitish=sha),
    )

    assert _names(_delta_for(result, "src/mod.py").added) == ["visible"]


def test_non_source_changed_file_yields_empty_delta(tmp_path):
    _init_repo(tmp_path)
    _write(tmp_path, "README.md", "base\n")
    sha = _commit_all(tmp_path, "baseline")
    _write(tmp_path, "README.md", "changed\n")

    result = collect_diff_scope(
        tmp_path,
        DiffScopeBaseline(source="since", commitish=sha),
    )

    assert result.edited == ("README.md",)
    delta = _delta_for(result, "README.md")
    assert delta.added == ()
    assert delta.signature_changed == ()
    assert delta.removed == ()


def test_changed_binary_file_yields_empty_delta(tmp_path):
    _init_repo(tmp_path)
    _write_bytes(tmp_path, "assets/logo.png", b"\x89PNG\r\n\x1a\n\x00\x00")
    sha = _commit_all(tmp_path, "baseline")
    _write_bytes(tmp_path, "assets/logo.png", b"\x89PNG\r\n\x1a\n\x00\x01")

    result = collect_diff_scope(
        tmp_path,
        DiffScopeBaseline(source="since", commitish=sha),
    )

    assert result.edited == ("assets/logo.png",)
    delta = _delta_for(result, "assets/logo.png")
    assert delta.added == ()
    assert delta.signature_changed == ()
    assert delta.removed == ()


def test_unparseable_changed_source_raises_diff_scope_error(tmp_path):
    _init_repo(tmp_path)
    _write(tmp_path, "src/anchor.py", "def anchor() -> None:\n    return None\n")
    sha = _commit_all(tmp_path, "baseline")
    _write(tmp_path, "src/broken.py", "def broken(:\n")

    with pytest.raises(DiffScopeError, match="src/broken.py"):
        collect_diff_scope(
            tmp_path,
            DiffScopeBaseline(source="since", commitish=sha),
        )
