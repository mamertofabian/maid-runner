"""Git worktree scope checks for MAID validation."""

from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Union

from maid_runner.core._file_discovery import is_test_file
from maid_runner.core.chain import ManifestChain
from maid_runner.core.result import ErrorCode, Location, Severity, ValidationError

_SOURCE_EXTENSIONS = {".py", ".ts", ".tsx", ".js", ".jsx", ".svelte"}


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
