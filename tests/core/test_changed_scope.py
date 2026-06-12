"""Tests for task-baseline changed-scope validation."""

from __future__ import annotations

import subprocess

import pytest

from maid_runner.core.chain import ManifestChain
from maid_runner.core.result import ErrorCode
from maid_runner.core.worktree import (
    ChangedScopeBaseline,
    changed_files_since,
    resolve_changed_scope_baseline,
    validate_changed_scope,
)


def _commit_all(project_dir, message: str = "commit") -> str:
    subprocess.run(["git", "init"], cwd=project_dir, check=True, capture_output=True)
    subprocess.run(
        ["git", "add", "."], cwd=project_dir, check=True, capture_output=True
    )
    subprocess.run(
        [
            "git",
            "-c",
            "core.hooksPath=/dev/null",
            "-c",
            "user.email=test@example.com",
            "-c",
            "user.name=Test User",
            "commit",
            "-m",
            message,
        ],
        cwd=project_dir,
        check=True,
        capture_output=True,
    )
    result = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=project_dir,
        check=True,
        capture_output=True,
        text=True,
    )
    return result.stdout.strip()


def _write_manifest(project_dir, name: str, body: str):
    manifest_dir = project_dir / "manifests"
    manifest_dir.mkdir(exist_ok=True)
    path = manifest_dir / name
    path.write_text(body)
    return path


def _write_source(project_dir, rel_path: str, content: str) -> None:
    path = project_dir / rel_path
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content)


def _chain(project_dir) -> ManifestChain:
    return ManifestChain(project_dir / "manifests", project_root=project_dir)


def test_changed_scope_rejects_changed_read_only_production_file_since_metadata_base(
    tmp_path,
):
    _write_source(tmp_path, "src/dep.py", "def helper():\n    return 'base'\n")
    baseline = _commit_all(tmp_path, "baseline")
    _write_manifest(
        tmp_path,
        "use-dep.manifest.yaml",
        f"""schema: "2"
goal: "Use dependency"
metadata:
  maid_task_base: {baseline}
files:
  create:
    - path: src/app.py
      artifacts:
        - kind: function
          name: run
  read:
    - src/dep.py
validate:
  - pytest tests/test_app.py -v
""",
    )
    _write_source(tmp_path, "src/app.py", "def run():\n    return 'ok'\n")
    _write_source(tmp_path, "src/dep.py", "def helper():\n    return 'changed'\n")

    errors = validate_changed_scope(tmp_path, _chain(tmp_path))

    assert any(
        error.code == ErrorCode.CHANGED_FILE_OUTSIDE_MANIFEST_SCOPE
        and error.location
        and error.location.file == "src/dep.py"
        for error in errors
    )


def test_changed_scope_allows_changed_file_in_files_edit(tmp_path):
    _write_source(tmp_path, "src/app.py", "def run():\n    return 'base'\n")
    baseline = _commit_all(tmp_path, "baseline")
    _write_manifest(
        tmp_path,
        "edit-app.manifest.yaml",
        f"""schema: "2"
goal: "Edit app"
metadata:
  maid_task_base: {baseline}
files:
  edit:
    - path: src/app.py
      artifacts:
        - kind: function
          name: run
validate:
  - pytest tests/test_app.py -v
""",
    )
    _write_source(tmp_path, "src/app.py", "def run():\n    return 'changed'\n")

    assert validate_changed_scope(tmp_path, _chain(tmp_path)) == []


def test_changed_scope_requires_baseline_when_requested(tmp_path):
    _write_manifest(
        tmp_path,
        "add-app.manifest.yaml",
        """schema: "2"
goal: "Add app"
files:
  create:
    - path: src/app.py
      artifacts:
        - kind: function
          name: run
validate:
  - pytest tests/test_app.py -v
""",
    )

    with pytest.raises(Exception) as exc_info:
        resolve_changed_scope_baseline(_chain(tmp_path))

    error = exc_info.value.error
    assert error.code == ErrorCode.CHANGED_SCOPE_BASELINE_REQUIRED
    assert "origin/main" not in error.message


def test_changed_scope_rejects_conflicting_manifest_task_bases(tmp_path):
    _write_manifest(
        tmp_path,
        "one.manifest.yaml",
        """schema: "2"
goal: "One"
metadata:
  maid_task_base: one
files:
  create:
    - path: src/one_owner.py
      artifacts:
        - kind: function
          name: one_owner
  read:
    - src/one.py
validate:
  - pytest tests/test_one.py -v
""",
    )
    _write_manifest(
        tmp_path,
        "two.manifest.yaml",
        """schema: "2"
goal: "Two"
metadata:
  maid_task_base: two
files:
  create:
    - path: src/two_owner.py
      artifacts:
        - kind: function
          name: two_owner
  read:
    - src/two.py
validate:
  - pytest tests/test_two.py -v
""",
    )

    with pytest.raises(Exception) as exc_info:
        resolve_changed_scope_baseline(_chain(tmp_path))

    assert exc_info.value.error.code == ErrorCode.CHANGED_SCOPE_BASELINE_INVALID


def test_changed_scope_base_ref_uses_merge_base(tmp_path):
    _write_source(tmp_path, "src/root.py", "def root():\n    return 'root'\n")
    _commit_all(tmp_path, "root")
    subprocess.run(["git", "checkout", "-b", "parent"], cwd=tmp_path, check=True)
    _write_source(tmp_path, "src/parent.py", "def parent():\n    return 'parent'\n")
    _commit_all(tmp_path, "parent")
    subprocess.run(["git", "checkout", "-b", "feature"], cwd=tmp_path, check=True)
    _write_source(tmp_path, "src/feature.py", "def feature():\n    return 'feature'\n")

    paths = changed_files_since(
        tmp_path,
        ChangedScopeBaseline(source="base-ref", commitish="parent"),
    )

    assert "src/feature.py" in paths
    assert "src/parent.py" not in paths


def test_changed_scope_include_tests_reports_changed_test_file(tmp_path):
    _write_source(tmp_path, "tests/test_app.py", "def test_app():\n    assert True\n")
    baseline = _commit_all(tmp_path, "baseline")
    _write_manifest(
        tmp_path,
        "use-test.manifest.yaml",
        f"""schema: "2"
goal: "Use test"
metadata:
  maid_task_base: {baseline}
files:
  create:
    - path: src/app.py
      artifacts:
        - kind: function
          name: run
  read:
    - tests/test_app.py
validate:
  - pytest tests/test_app.py -v
""",
    )
    _write_source(tmp_path, "src/app.py", "def run():\n    return 'ok'\n")
    _write_source(tmp_path, "tests/test_app.py", "def test_app():\n    assert False\n")

    default_errors = validate_changed_scope(tmp_path, _chain(tmp_path))
    include_errors = validate_changed_scope(
        tmp_path,
        _chain(tmp_path),
        include_tests=True,
    )

    assert default_errors == []
    assert any(
        error.code == ErrorCode.CHANGED_FILE_OUTSIDE_MANIFEST_SCOPE
        and error.location
        and error.location.file == "tests/test_app.py"
        for error in include_errors
    )


def _conflicting_base_manifest(name: str, base: str) -> str:
    return f"""schema: "2"
goal: "{name.capitalize()}"
metadata:
  maid_task_base: {base}
files:
  create:
    - path: src/{name}_owner.py
      artifacts:
        - kind: function
          name: {name}_owner
  read:
    - src/{name}.py
validate:
  - pytest tests/test_{name}.py -v
"""


def test_committed_conflicting_task_bases_are_ignored(tmp_path):
    _write_manifest(
        tmp_path, "one.manifest.yaml", _conflicting_base_manifest("one", "one")
    )
    _write_manifest(
        tmp_path, "two.manifest.yaml", _conflicting_base_manifest("two", "two")
    )
    _commit_all(tmp_path, "history")

    with pytest.raises(Exception) as exc_info:
        resolve_changed_scope_baseline(_chain(tmp_path))

    assert exc_info.value.error.code == ErrorCode.CHANGED_SCOPE_BASELINE_REQUIRED


def test_worktree_changed_manifest_task_base_resolves(tmp_path):
    _write_manifest(
        tmp_path, "one.manifest.yaml", _conflicting_base_manifest("one", "one")
    )
    _write_manifest(
        tmp_path, "two.manifest.yaml", _conflicting_base_manifest("two", "two")
    )
    _commit_all(tmp_path, "history")
    _write_manifest(
        tmp_path,
        "current.manifest.yaml",
        _conflicting_base_manifest("current", "task-base"),
    )

    baseline = resolve_changed_scope_baseline(_chain(tmp_path))

    assert baseline == ChangedScopeBaseline(source="metadata", commitish="task-base")


def test_conflicting_worktree_changed_task_bases_fail_invalid(tmp_path):
    _write_source(tmp_path, "src/seed.py", "def seed():\n    return 'seed'\n")
    _commit_all(tmp_path, "seed")
    _write_manifest(
        tmp_path, "one.manifest.yaml", _conflicting_base_manifest("one", "one")
    )
    _write_manifest(
        tmp_path, "two.manifest.yaml", _conflicting_base_manifest("two", "two")
    )

    with pytest.raises(Exception) as exc_info:
        resolve_changed_scope_baseline(_chain(tmp_path))

    assert exc_info.value.error.code == ErrorCode.CHANGED_SCOPE_BASELINE_INVALID


def test_resolve_changed_scope_baseline_prefers_explicit_since(tmp_path):
    _write_manifest(
        tmp_path,
        "add-app.manifest.yaml",
        """schema: "2"
goal: "Add app"
metadata:
  maid_task_base: metadata-base
files:
  create:
    - path: src/owner.py
      artifacts:
        - kind: function
          name: owner
  read:
    - src/app.py
validate:
  - pytest tests/test_app.py -v
""",
    )

    baseline = resolve_changed_scope_baseline(_chain(tmp_path), since="explicit")

    assert baseline == ChangedScopeBaseline(source="since", commitish="explicit")
