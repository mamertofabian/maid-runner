"""Tests for reporting which manifests declare a changed-scope baseline.

`resolve_changed_scope_baseline` raises a generic error when active manifests
disagree, naming neither the manifests nor their values. These tests pin a
public accessor that reports exactly the declarations resolution considered, so
a caller can tell the user which manifests to reconcile.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from maid_runner.core.chain import ManifestChain
from maid_runner.core.result import ErrorCode
from maid_runner.core.worktree import resolve_changed_scope_baseline


def _git(project_dir: Path, *args: str) -> str:
    result = subprocess.run(
        [
            "git",
            "-c",
            "core.hooksPath=/dev/null",
            "-c",
            "user.email=test@example.com",
            "-c",
            "user.name=Test User",
            *args,
        ],
        cwd=project_dir,
        check=True,
        capture_output=True,
        text=True,
    )
    return result.stdout.strip()


def _seed_repo(project_dir: Path) -> None:
    (project_dir / "manifests").mkdir()
    (project_dir / "src").mkdir()
    (project_dir / "README.md").write_text("seed\n")
    _git(project_dir, "init", "-q")
    _git(project_dir, "add", ".")
    _git(project_dir, "commit", "-q", "-m", "seed")


def _write_manifest(project_dir: Path, slug: str, task_base: str | None) -> Path:
    metadata = f"metadata:\n  maid_task_base: {task_base}\n" if task_base else ""
    path = project_dir / "manifests" / f"{slug}.manifest.yaml"
    path.write_text(
        f"""schema: "2"
goal: "Task for {slug}"
type: feature
created: "2026-07-26T00:00:00Z"
{metadata}files:
  create:
    - path: src/{slug}.py
      artifacts:
        - kind: function
          name: {slug}_run
          returns: int
validate:
  - python -m pytest -q tests/test_{slug}.py
"""
    )
    return path


def _chain(project_dir: Path) -> ManifestChain:
    return ManifestChain(project_dir / "manifests", project_root=project_dir)


def test_describe_returns_declaration_per_worktree_changed_manifest(
    tmp_path: Path,
) -> None:
    from maid_runner.core.worktree import (
        BaselineDeclaration,
        describe_changed_scope_baselines,
    )

    _seed_repo(tmp_path)
    _write_manifest(tmp_path, "alpha", "aaaa111")
    _write_manifest(tmp_path, "beta", "bbbb222")

    declarations = describe_changed_scope_baselines(_chain(tmp_path))

    assert [entry.manifest_path for entry in declarations] == [
        "manifests/alpha.manifest.yaml",
        "manifests/beta.manifest.yaml",
    ]
    assert [entry.commitish for entry in declarations] == ["aaaa111", "bbbb222"]
    assert declarations[0] == BaselineDeclaration(
        manifest_path="manifests/alpha.manifest.yaml",
        commitish="aaaa111",
    )


def test_describe_ignores_committed_historical_declarations(tmp_path: Path) -> None:
    from maid_runner.core.worktree import describe_changed_scope_baselines

    _seed_repo(tmp_path)
    _write_manifest(tmp_path, "historical", "cccc333")
    _git(tmp_path, "add", ".")
    _git(tmp_path, "commit", "-q", "-m", "historical task")
    _write_manifest(tmp_path, "current", "dddd444")

    declarations = describe_changed_scope_baselines(_chain(tmp_path))

    assert [entry.manifest_path for entry in declarations] == [
        "manifests/current.manifest.yaml"
    ]
    assert [entry.commitish for entry in declarations] == ["dddd444"]


def test_describe_returns_empty_when_no_considered_manifest_declares(
    tmp_path: Path,
) -> None:
    from maid_runner.core.worktree import describe_changed_scope_baselines

    _seed_repo(tmp_path)
    _write_manifest(tmp_path, "plain", None)

    assert describe_changed_scope_baselines(_chain(tmp_path)) == ()


def test_describe_agrees_with_resolution_on_the_conflicting_set(
    tmp_path: Path,
) -> None:
    from maid_runner.core.worktree import describe_changed_scope_baselines

    _seed_repo(tmp_path)
    _write_manifest(tmp_path, "alpha", "aaaa111")
    _write_manifest(tmp_path, "beta", "bbbb222")
    chain = _chain(tmp_path)

    declarations = describe_changed_scope_baselines(chain)

    with pytest.raises(RuntimeError) as excinfo:
        resolve_changed_scope_baseline(chain)

    assert excinfo.value.error.code == ErrorCode.CHANGED_SCOPE_BASELINE_INVALID
    assert {entry.commitish for entry in declarations} == {"aaaa111", "bbbb222"}
