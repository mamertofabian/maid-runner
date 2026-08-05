"""Regression coverage for .NET files in changed/worktree scope gates."""

from __future__ import annotations

from pathlib import Path
import subprocess

from maid_runner.core.chain import ManifestChain
from maid_runner.core.result import ErrorCode
from maid_runner.core.worktree import evaluate_changed_scope, validate_worktree_scope


DOTNET_PATHS = (
    "Services/LocationService.cs",
    "Pages/_Host.cshtml",
    "Components/App.razor",
    "Resources/Labels.resx",
)


def _commit_all(project_root: Path, message: str) -> str:
    subprocess.run(["git", "init", "-q"], cwd=project_root, check=True)
    subprocess.run(["git", "add", "."], cwd=project_root, check=True)
    subprocess.run(
        [
            "git",
            "-c",
            "core.hooksPath=/dev/null",
            "-c",
            "user.email=maid-test@example.com",
            "-c",
            "user.name=MAID Test",
            "commit",
            "-qm",
            message,
        ],
        cwd=project_root,
        check=True,
    )
    result = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=project_root,
        check=True,
        capture_output=True,
        text=True,
    )
    return result.stdout.strip()


def _write_manifest(project_root: Path, *, dotnet_writable: bool) -> None:
    manifest_dir = project_root / "manifests"
    manifest_dir.mkdir(exist_ok=True)
    if dotnet_writable:
        file_contract = """  scope:
    - path: Services/LocationService.cs
      reason: Task-owned C# service.
    - path: Pages/_Host.cshtml
      reason: Task-owned Razor host page.
    - path: Components/App.razor
      reason: Task-owned Razor component.
    - path: Resources/Labels.resx
      reason: Task-owned localization resource.
"""
    else:
        file_contract = """  create:
    - path: src/owner.py
      artifacts:
        - kind: function
          name: owner
          args: []
          returns: int
"""
    (manifest_dir / "task.manifest.yaml").write_text(
        f"""schema: "2"
goal: "Own task production files"
type: fix
created: "2026-08-05T00:00:00Z"
files:
{file_contract}validate:
  - pytest tests/test_owner.py -q
""",
        encoding="utf-8",
    )


def _write_dotnet_files(project_root: Path) -> None:
    contents = {
        "Services/LocationService.cs": "public class LocationService {}\n",
        "Pages/_Host.cshtml": "<main>Host</main>\n",
        "Components/App.razor": "<h1>App</h1>\n",
        "Resources/Labels.resx": "<root />\n",
    }
    for relative_path, content in contents.items():
        path = project_root / relative_path
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")


def _chain(project_root: Path) -> ManifestChain:
    return ManifestChain(project_root / "manifests", project_root=project_root)


def _outside_scope_paths(errors) -> set[str]:
    return {
        error.location.file
        for error in errors
        if error.code == ErrorCode.CHANGED_FILE_OUTSIDE_MANIFEST_SCOPE
        and error.location is not None
        and error.location.file is not None
    }


def test_changed_scope_reports_committed_dotnet_production_files_since_explicit_baseline(
    tmp_path: Path,
) -> None:
    (tmp_path / "README.md").write_text("baseline\n", encoding="utf-8")
    baseline = _commit_all(tmp_path, "baseline")
    _write_manifest(tmp_path, dotnet_writable=False)
    _write_dotnet_files(tmp_path)
    _commit_all(tmp_path, "committed .NET task files")

    decision = evaluate_changed_scope(tmp_path, _chain(tmp_path), since=baseline)

    assert _outside_scope_paths(decision.errors) == set(DOTNET_PATHS)


def test_changed_scope_allows_committed_dotnet_files_in_writable_scope(
    tmp_path: Path,
) -> None:
    (tmp_path / "README.md").write_text("baseline\n", encoding="utf-8")
    baseline = _commit_all(tmp_path, "baseline")
    _write_manifest(tmp_path, dotnet_writable=True)
    _write_dotnet_files(tmp_path)
    _commit_all(tmp_path, "declared .NET task files")

    decision = evaluate_changed_scope(tmp_path, _chain(tmp_path), since=baseline)

    assert decision.errors == ()


def test_worktree_scope_reports_uncommitted_dotnet_production_files(
    tmp_path: Path,
) -> None:
    _write_manifest(tmp_path, dotnet_writable=False)
    _commit_all(tmp_path, "baseline manifest")
    _write_dotnet_files(tmp_path)

    errors = validate_worktree_scope(tmp_path, _chain(tmp_path))

    assert _outside_scope_paths(errors) == set(DOTNET_PATHS)
