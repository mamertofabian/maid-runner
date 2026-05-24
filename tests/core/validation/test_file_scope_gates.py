"""Focused characterization tests for file-scope validation gates."""

import subprocess

import pytest

from maid_runner.core.chain import ManifestChain
from maid_runner.core.result import ErrorCode, FileTrackingStatus
from maid_runner.core.validate import ValidationEngine
from maid_runner.core.worktree import validate_changed_scope, validate_worktree_scope


@pytest.fixture()
def project(tmp_path):
    """Create a temporary project directory."""
    (tmp_path / "src").mkdir()
    (tmp_path / "manifests").mkdir()
    (tmp_path / "tests").mkdir()
    return tmp_path


def write_manifest(project_dir, name, content):
    path = project_dir / "manifests" / name
    path.write_text(content)
    return path


def write_source(project_dir, rel_path, content):
    path = project_dir / rel_path
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content)
    return path


def commit_all(project_dir, message="baseline"):
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


def manifest_chain(project_dir):
    return ManifestChain(project_dir / "manifests", project_root=project_dir)


def scope_error_files(errors):
    return {
        error.location.file
        for error in errors
        if error.code == ErrorCode.CHANGED_FILE_OUTSIDE_MANIFEST_SCOPE
        and error.location is not None
    }


def test_file_tracking_reports_undeclared_source_file(project):
    write_manifest(
        project,
        "add-app.manifest.yaml",
        """schema: "2"
goal: "Add app"
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
    write_source(project, "src/app.py", "def run():\n    return 'ok'\n")
    write_source(project, "src/extra.py", "def extra():\n    return 'drift'\n")
    write_source(
        project,
        "tests/test_app.py",
        "from src.app import run\n\n" "def test_run():\n" "    assert run() == 'ok'\n",
    )

    engine = ValidationEngine(project_root=project)
    result = engine.validate_all(project / "manifests", check_file_tracking=True)
    reports = [item.file_tracking for item in result.results if item.file_tracking]

    assert result.success is False
    assert any(
        entry.path == "src/extra.py"
        for report in reports
        for entry in report.undeclared
    )


def test_file_tracking_ignores_gitignored_source_file(project):
    subprocess.run(["git", "init"], cwd=project, check=True, capture_output=True)
    (project / ".gitignore").write_text("generated.py\n")
    write_source(project, "generated.py", "def generated():\n    return 'ignored'\n")

    engine = ValidationEngine(project_root=project)
    report = engine.run_file_tracking(manifest_chain(project))

    assert all(entry.path != "generated.py" for entry in report.entries)


def test_file_tracking_reports_manifest_created_source_file_as_tracked(project):
    write_manifest(
        project,
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
    write_source(project, "src/app.py", "def run():\n    return 'ok'\n")

    engine = ValidationEngine(project_root=project)
    report = engine.run_file_tracking(manifest_chain(project))
    entries = [entry for entry in report.entries if entry.path == "src/app.py"]

    assert len(entries) == 1
    assert entries[0].status == FileTrackingStatus.TRACKED


def test_file_tracking_classifies_files_read_as_registered(project):
    write_manifest(
        project,
        "use-dep.manifest.yaml",
        """schema: "2"
goal: "Use dependency"
files:
  create:
    - path: src/app.py
      artifacts:
        - kind: function
          name: run
  read:
    - src/dep.py
validate:
  - pytest tests/ -v
""",
    )
    write_source(project, "src/app.py", "def run():\n    return 'ok'\n")
    write_source(project, "src/dep.py", "def helper():\n    return 'dep'\n")

    engine = ValidationEngine(project_root=project)
    report = engine.run_file_tracking(manifest_chain(project))
    dep_entries = [entry for entry in report.entries if entry.path == "src/dep.py"]

    assert len(dep_entries) == 1
    assert dep_entries[0].status == FileTrackingStatus.REGISTERED
    assert dep_entries[0].status != FileTrackingStatus.UNDECLARED
    assert any("read" in issue.lower() for issue in dep_entries[0].issues)


def test_worktree_scope_rejects_changed_file_in_files_read(project):
    write_manifest(
        project,
        "use-dep.manifest.yaml",
        """schema: "2"
goal: "Use dependency"
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
    write_source(project, "src/app.py", "def run():\n    return 'ok'\n")
    write_source(project, "src/dep.py", "def helper():\n    return 'changed'\n")
    subprocess.run(["git", "init"], cwd=project, check=True, capture_output=True)

    errors = validate_worktree_scope(project, manifest_chain(project))

    assert "src/dep.py" in scope_error_files(errors)


def test_worktree_scope_allows_changed_file_in_files_edit(project):
    write_manifest(
        project,
        "edit-app.manifest.yaml",
        """schema: "2"
goal: "Edit app"
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
    write_source(project, "src/app.py", "def run():\n    return 'changed'\n")
    subprocess.run(["git", "init"], cwd=project, check=True, capture_output=True)

    assert validate_worktree_scope(project, manifest_chain(project)) == []


def test_changed_scope_rejects_changed_read_only_file_since_task_base(project):
    write_source(project, "src/dep.py", "def helper():\n    return 'base'\n")
    baseline = commit_all(project)
    write_manifest(
        project,
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
    write_source(project, "src/app.py", "def run():\n    return 'ok'\n")
    write_source(project, "src/dep.py", "def helper():\n    return 'changed'\n")

    errors = validate_changed_scope(project, manifest_chain(project))

    assert "src/dep.py" in scope_error_files(errors)
