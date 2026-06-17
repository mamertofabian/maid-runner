"""Fast single-manifest scope decisions for edit-time hooks."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path, PureWindowsPath
from typing import Literal, Union

from maid_runner.core.manifest import load_manifest
from maid_runner.core.types import Manifest


@dataclass(frozen=True)
class ScopeCheckDecision:
    """JSON-serializable hook scope decision."""

    decision: Literal["allow", "deny"]
    reason: str
    active_manifest: str | None


def declared_scope_paths(
    manifest: Manifest,
    project_root: Union[str, Path] = ".",
) -> set[str]:
    """Return the allowed edit-time scope for a single manifest."""
    root = Path(project_root)
    paths = set(manifest.all_writable_paths)
    paths.add(_display_project_path(manifest.source_path, root))
    paths.update(_declared_test_paths(manifest, root))
    paths.add("manifests/drafts/")
    return {_normalize_display_path(path, root) for path in paths}


def scope_check_path(
    candidate_path: str,
    active_manifest: str | None,
    project_root: Union[str, Path] = ".",
    strict: bool = False,
) -> ScopeCheckDecision:
    root = Path(project_root)
    if active_manifest is None:
        return ScopeCheckDecision(
            decision="deny" if strict else "allow",
            reason="no-active-task",
            active_manifest=None,
        )

    try:
        active_manifest_path = Path(active_manifest)
        if not active_manifest_path.is_absolute():
            active_manifest_path = root / active_manifest_path
        manifest = load_manifest(active_manifest_path)
        allowed_paths = declared_scope_paths(manifest, root)
        candidate = _normalize_display_path(candidate_path, root)
    except Exception as exc:
        return ScopeCheckDecision(
            decision="deny" if strict else "allow",
            reason=f"internal-error: {type(exc).__name__}: {exc}",
            active_manifest=active_manifest,
        )

    if candidate in allowed_paths or _is_under_draft_manifests(candidate):
        return ScopeCheckDecision(
            decision="allow",
            reason="in-scope",
            active_manifest=active_manifest,
        )

    closest = ", ".join(sorted(allowed_paths - {"manifests/drafts/"})[:5])
    return ScopeCheckDecision(
        decision="deny",
        reason=(
            f"out-of-scope for {active_manifest}; closest declared scope: "
            f"{closest or 'none'}"
        ),
        active_manifest=active_manifest,
    )


def _declared_test_paths(manifest: Manifest, project_root: Path) -> set[str]:
    paths = {
        _normalize_display_path(path, project_root)
        for path in manifest.files_read
        if _looks_like_test_path(path)
    }
    for command in manifest.validate_commands:
        paths.update(_test_paths_from_command(command, project_root))
    return paths


def _test_paths_from_command(
    command: tuple[str, ...],
    project_root: Path,
) -> set[str]:
    paths: set[str] = set()
    cwd = Path(".")
    index = 0
    while index < len(command):
        part = command[index]
        if part in {"&&", "||", ";"}:
            index += 1
            continue
        if part == "cd" and index + 1 < len(command):
            cwd = cwd / command[index + 1]
            index += 2
            continue
        if part in {"-C", "--cwd", "--dir", "--prefix"} and index + 1 < len(command):
            cwd = cwd / command[index + 1]
            index += 2
            continue
        if not part.startswith("-"):
            candidate = _normalize_display_path(str(cwd / part), project_root)
            if _looks_like_test_path(candidate):
                paths.add(candidate)
        index += 1
    return paths


def _is_under_draft_manifests(path: str) -> bool:
    return path.startswith("manifests/drafts/")


def _looks_like_test_path(path: str) -> bool:
    normalized = path.replace("\\", "/")
    path_obj = Path(normalized)
    lower_name = path_obj.name.lower()
    if any(
        part.lower() in {"test", "tests", "__tests__", "spec", "specs"}
        for part in path_obj.parts
    ):
        return True
    return (
        lower_name == "conftest.py"
        or (lower_name.startswith("test_") and lower_name.endswith(".py"))
        or lower_name.endswith("_test.py")
        or lower_name.endswith(
            (
                ".test.ts",
                ".test.tsx",
                ".test.js",
                ".test.jsx",
                ".spec.ts",
                ".spec.tsx",
                ".spec.js",
                ".spec.jsx",
            )
        )
    )


def _display_project_path(path: str, project_root: Path) -> str:
    candidate = Path(path)
    if not candidate.is_absolute():
        return candidate.as_posix()
    try:
        return candidate.resolve().relative_to(project_root.resolve()).as_posix()
    except (OSError, RuntimeError, ValueError):
        return candidate.as_posix()


def _normalize_display_path(path: str, project_root: Path) -> str:
    windows_path = PureWindowsPath(path)
    candidate = Path(path)
    if candidate.is_absolute() or windows_path.is_absolute() or windows_path.drive:
        try:
            return candidate.resolve().relative_to(project_root.resolve()).as_posix()
        except (OSError, RuntimeError, ValueError):
            return candidate.as_posix()
    normalized = Path(path).as_posix()
    try:
        normalized = (
            (project_root / normalized).resolve().relative_to(project_root.resolve())
        )
        return normalized.as_posix()
    except (OSError, RuntimeError, ValueError):
        if normalized.startswith("./"):
            normalized = normalized[2:]
        return normalized
