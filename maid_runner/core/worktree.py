"""Git worktree scope checks for MAID validation."""

from __future__ import annotations

from dataclasses import dataclass
import subprocess
from pathlib import Path
from typing import Optional, Union

from maid_runner.core._file_discovery import is_test_file
from maid_runner.core.chain import ManifestChain
from maid_runner.core.result import ErrorCode, Location, Severity, ValidationError
from maid_runner.core.types import Manifest

_SOURCE_EXTENSIONS = {".py", ".ts", ".tsx", ".js", ".jsx", ".svelte"}


@dataclass(frozen=True)
class ChangedScopeBaseline:
    """Resolved task baseline for changed-scope validation."""

    source: str
    commitish: str


class _ChangedScopeBaselineError(RuntimeError):
    def __init__(
        self,
        code: ErrorCode,
        message: str,
        *,
        suggestion: str | None = None,
    ) -> None:
        super().__init__(message)
        self.error = ValidationError(
            code=code,
            message=message,
            severity=Severity.ERROR,
            suggestion=suggestion,
        )


def changed_files(project_root: Union[str, Path]) -> "tuple[str, ...]":
    """Return git-reported changed file paths relative to the project root."""
    root = Path(project_root)
    prefix = _git_prefix(root)
    try:
        result = subprocess.run(
            [
                "git",
                "status",
                "--porcelain=v1",
                "-z",
                "--untracked-files=all",
                "--",
                ".",
            ],
            cwd=root,
            capture_output=True,
            text=True,
            timeout=10,
        )
    except FileNotFoundError as exc:
        raise RuntimeError(
            "Worktree scope gate requires git metadata: git executable not found"
        ) from exc
    except subprocess.TimeoutExpired as exc:
        raise RuntimeError(
            "Worktree scope gate requires git metadata: git status timed out"
        ) from exc

    if result.returncode != 0:
        detail = (result.stderr or result.stdout).strip()
        message = "Worktree scope gate requires git metadata"
        if detail:
            message = f"{message}: {detail}"
        raise RuntimeError(message)

    return _to_project_relative_paths(_parse_porcelain_z(result.stdout), prefix)


def resolve_changed_scope_baseline(
    chain: ManifestChain,
    since: Optional[str] = None,
    base_ref: Optional[str] = None,
) -> ChangedScopeBaseline:
    """Resolve the explicit or manifest-declared changed-scope baseline."""
    if since and base_ref:
        raise _ChangedScopeBaselineError(
            ErrorCode.CHANGED_SCOPE_BASELINE_INVALID,
            "--changed-scope accepts either --since or --base-ref, not both",
            suggestion="Pass one baseline source for the task window.",
        )
    if since:
        return ChangedScopeBaseline(source="since", commitish=since)
    if base_ref:
        return ChangedScopeBaseline(source="base-ref", commitish=base_ref)

    bases = {
        str(manifest.metadata.get("maid_task_base")).strip()
        for manifest in _baseline_metadata_manifests(chain)
        if isinstance(manifest.metadata, dict)
        and manifest.metadata.get("maid_task_base")
    }
    if len(bases) == 1:
        return ChangedScopeBaseline(source="metadata", commitish=next(iter(bases)))
    if len(bases) > 1:
        raise _ChangedScopeBaselineError(
            ErrorCode.CHANGED_SCOPE_BASELINE_INVALID,
            "Active manifests declare conflicting metadata.maid_task_base values",
            suggestion=(
                "Make active manifest metadata agree, or pass --since/--base-ref "
                "for this validation run."
            ),
        )

    raise _ChangedScopeBaselineError(
        ErrorCode.CHANGED_SCOPE_BASELINE_REQUIRED,
        "--changed-scope requires --since, --base-ref, or metadata.maid_task_base",
        suggestion=(
            "Pass the task baseline explicitly; MAID will not guess main, dev, "
            "or a remote branch."
        ),
    )


def _baseline_metadata_manifests(chain: ManifestChain) -> "list[Manifest]":
    """Active manifests whose metadata baselines count for resolution.

    `maid_task_base` is a current-task declaration, so only manifests with
    uncommitted worktree changes (the task in flight) are considered;
    committed historical declarations would otherwise poison bare baseline
    resolution forever once two completed tasks disagree. When git state
    cannot be read, every active manifest is considered: degraded
    environments keep the chain-wide behavior and only get stricter.
    """
    active = chain.active_manifests()
    declaring = [
        manifest
        for manifest in active
        if isinstance(manifest.metadata, dict)
        and manifest.metadata.get("maid_task_base")
    ]
    if not declaring:
        return active
    project_root = getattr(chain, "_project_root", None)
    if project_root is None:
        return active
    try:
        changed = set(changed_files(project_root))
    except RuntimeError:
        return active
    return [
        manifest
        for manifest in declaring
        if _project_relative_manifest_path(manifest, Path(project_root)) in changed
    ]


def _project_relative_manifest_path(manifest: "Manifest", project_root: Path) -> str:
    path = Path(manifest.source_path)
    try:
        return path.resolve().relative_to(project_root.resolve()).as_posix()
    except ValueError:
        return _normalize_git_path(str(path))


def changed_files_since(
    project_root: Union[str, Path],
    baseline: ChangedScopeBaseline,
) -> "tuple[str, ...]":
    """Return files changed from the task baseline to the current worktree."""
    root = Path(project_root)
    commitish = _baseline_commitish(root, baseline)
    tracked = _changed_tracked_paths_since(root, commitish)
    untracked = _untracked_paths(root)
    return tuple(dict.fromkeys((*tracked, *untracked)))


def validate_changed_scope(
    project_root: Union[str, Path],
    chain: ManifestChain,
    since: Optional[str] = None,
    base_ref: Optional[str] = None,
    include_tests: bool = False,
) -> list[ValidationError]:
    """Report baseline-changed files outside active writable manifest scope."""
    try:
        baseline = resolve_changed_scope_baseline(chain, since=since, base_ref=base_ref)
        paths = changed_files_since(project_root, baseline)
    except _ChangedScopeBaselineError as exc:
        return [exc.error]
    except RuntimeError as exc:
        return [
            ValidationError(
                code=ErrorCode.FILE_READ_ERROR,
                message=str(exc),
                severity=Severity.ERROR,
            )
        ]

    return _scope_errors_for_paths(paths, chain, include_tests=include_tests)


def validate_worktree_scope(
    project_root: Union[str, Path],
    chain: ManifestChain,
    include_tests: bool = False,
) -> list[ValidationError]:
    """Report changed files that are outside active writable manifest scope."""
    try:
        paths = changed_files(project_root)
    except RuntimeError as exc:
        return [
            ValidationError(
                code=ErrorCode.FILE_READ_ERROR,
                message=str(exc),
                severity=Severity.ERROR,
            )
        ]

    return _scope_errors_for_paths(paths, chain, include_tests=include_tests)


def _scope_errors_for_paths(
    paths: tuple[str, ...],
    chain: ManifestChain,
    *,
    include_tests: bool,
) -> list[ValidationError]:
    writable_paths = _active_writable_paths(chain)
    errors: list[ValidationError] = []

    for path in paths:
        if not _is_source_path(path):
            continue
        if is_test_file(path) and not include_tests:
            continue
        if path in writable_paths:
            continue
        errors.append(
            ValidationError(
                code=ErrorCode.CHANGED_FILE_OUTSIDE_MANIFEST_SCOPE,
                message=(f"Changed file '{path}' is outside writable manifest scope"),
                severity=Severity.ERROR,
                location=Location(file=path),
                suggestion=(
                    "Declare the file in files.create, files.edit, or files.delete "
                    "for the active manifest chain, or revert the change."
                ),
            )
        )

    return errors


def _baseline_commitish(root: Path, baseline: ChangedScopeBaseline) -> str:
    if baseline.source != "base-ref":
        return baseline.commitish

    try:
        result = subprocess.run(
            ["git", "merge-base", baseline.commitish, "HEAD"],
            cwd=root,
            capture_output=True,
            text=True,
            timeout=10,
        )
    except FileNotFoundError as exc:
        raise RuntimeError(
            "Changed-scope gate requires git metadata: git executable not found"
        ) from exc
    except subprocess.TimeoutExpired as exc:
        raise RuntimeError(
            "Changed-scope gate requires git metadata: git merge-base timed out"
        ) from exc

    if result.returncode != 0:
        detail = (result.stderr or result.stdout).strip()
        message = f"Changed-scope baseline is invalid: {baseline.commitish}"
        if detail:
            message = f"{message}: {detail}"
        raise _ChangedScopeBaselineError(
            ErrorCode.CHANGED_SCOPE_BASELINE_INVALID,
            message,
        )
    return result.stdout.strip()


def _changed_tracked_paths_since(root: Path, commitish: str) -> tuple[str, ...]:
    try:
        result = subprocess.run(
            [
                "git",
                "diff",
                "--name-status",
                "-z",
                "--relative",
                commitish,
                "--",
                ".",
            ],
            cwd=root,
            capture_output=True,
            text=True,
            timeout=10,
        )
    except FileNotFoundError as exc:
        raise RuntimeError(
            "Changed-scope gate requires git metadata: git executable not found"
        ) from exc
    except subprocess.TimeoutExpired as exc:
        raise RuntimeError(
            "Changed-scope gate requires git metadata: git diff timed out"
        ) from exc

    if result.returncode != 0:
        detail = (result.stderr or result.stdout).strip()
        message = f"Changed-scope baseline is invalid: {commitish}"
        if detail:
            message = f"{message}: {detail}"
        raise _ChangedScopeBaselineError(
            ErrorCode.CHANGED_SCOPE_BASELINE_INVALID,
            message,
        )
    return _parse_name_status_z(result.stdout)


def _untracked_paths(root: Path) -> tuple[str, ...]:
    try:
        result = subprocess.run(
            ["git", "ls-files", "--others", "--exclude-standard", "-z", "--", "."],
            cwd=root,
            capture_output=True,
            text=True,
            timeout=10,
        )
    except FileNotFoundError as exc:
        raise RuntimeError(
            "Changed-scope gate requires git metadata: git executable not found"
        ) from exc
    except subprocess.TimeoutExpired as exc:
        raise RuntimeError(
            "Changed-scope gate requires git metadata: git ls-files timed out"
        ) from exc

    if result.returncode != 0:
        detail = (result.stderr or result.stdout).strip()
        message = "Changed-scope gate requires git metadata"
        if detail:
            message = f"{message}: {detail}"
        raise RuntimeError(message)
    paths = tuple(
        _normalize_git_path(path) for path in result.stdout.split("\0") if path
    )
    return tuple(dict.fromkeys(paths))


def _parse_name_status_z(output: str) -> tuple[str, ...]:
    paths: list[str] = []
    fields = [field for field in output.split("\0") if field]
    index = 0
    while index < len(fields):
        status = fields[index]
        index += 1
        if index >= len(fields):
            break
        path = fields[index]
        index += 1
        if status.startswith(("R", "C")):
            if index >= len(fields):
                break
            new_path = fields[index]
            index += 1
            paths.append(_normalize_git_path(path))
            paths.append(_normalize_git_path(new_path))
        else:
            paths.append(_normalize_git_path(path))
    return tuple(dict.fromkeys(paths))


def _parse_porcelain_z(output: str) -> tuple[str, ...]:
    paths: list[str] = []
    fields = output.split("\0")
    index = 0
    while index < len(fields):
        entry = fields[index]
        index += 1
        if not entry:
            continue
        if len(entry) < 4:
            continue

        status = entry[:2]
        path = entry[3:]
        if path:
            paths.append(_normalize_git_path(path))

        if "R" in status or "C" in status:
            original_path = fields[index] if index < len(fields) else ""
            index += 1
            if "R" in status and original_path:
                paths.append(_normalize_git_path(original_path))

    return tuple(dict.fromkeys(paths))


def _git_prefix(root: Path) -> str:
    try:
        result = subprocess.run(
            ["git", "rev-parse", "--show-prefix"],
            cwd=root,
            capture_output=True,
            text=True,
            timeout=10,
        )
    except FileNotFoundError as exc:
        raise RuntimeError(
            "Worktree scope gate requires git metadata: git executable not found"
        ) from exc
    except subprocess.TimeoutExpired as exc:
        raise RuntimeError(
            "Worktree scope gate requires git metadata: git rev-parse timed out"
        ) from exc

    if result.returncode != 0:
        detail = (result.stderr or result.stdout).strip()
        message = "Worktree scope gate requires git metadata"
        if detail:
            message = f"{message}: {detail}"
        raise RuntimeError(message)

    lines = result.stdout.splitlines()
    return _normalize_git_path(lines[0] if lines else "")


def _to_project_relative_paths(paths: tuple[str, ...], prefix: str) -> tuple[str, ...]:
    if not prefix:
        return paths

    project_paths: list[str] = []
    for path in paths:
        if not path.startswith(prefix):
            continue
        rel_path = path[len(prefix) :]
        if rel_path:
            project_paths.append(rel_path)

    return tuple(dict.fromkeys(project_paths))


def _normalize_git_path(path: str) -> str:
    return path.replace("\\", "/")


def _is_source_path(path: str) -> bool:
    return Path(path).suffix in _SOURCE_EXTENSIONS


def _active_writable_paths(chain: ManifestChain) -> set[str]:
    paths: set[str] = set()
    for manifest in chain.active_manifests():
        paths.update(file_spec.path for file_spec in manifest.files_create)
        paths.update(file_spec.path for file_spec in manifest.files_edit)
        paths.update(delete_spec.path for delete_spec in manifest.files_delete)
    return paths
