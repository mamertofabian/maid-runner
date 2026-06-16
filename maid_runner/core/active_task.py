"""Active-task manifest pointer helpers."""

from __future__ import annotations

from dataclasses import dataclass
import os
from pathlib import Path, PureWindowsPath
from typing import Literal, Union


class ActiveTaskError(Exception):
    """Raised when an active task cannot be started."""


@dataclass(frozen=True)
class ActiveManifestStatus:
    """Resolved active manifest path and source."""

    path: str | None
    source: Literal["env", "file", "none"]


def get_active_manifest_status(
    project_root: Union[str, Path] = ".",
) -> ActiveManifestStatus:
    if "MAID_ACTIVE_MANIFEST" in os.environ:
        return ActiveManifestStatus(
            path=os.environ["MAID_ACTIVE_MANIFEST"],
            source="env",
        )

    active_file = _active_manifest_file(project_root)
    if not active_file.exists():
        return ActiveManifestStatus(path=None, source="none")

    stored_path = _read_first_line(active_file)
    if stored_path is None:
        return ActiveManifestStatus(path=None, source="none")
    return ActiveManifestStatus(path=stored_path, source="file")


def resolve_active_manifest(project_root: Union[str, Path] = ".") -> str | None:
    return get_active_manifest_status(project_root).path


def start_active_task(
    manifest_path: str,
    project_root: Union[str, Path] = ".",
) -> str:
    root = Path(project_root)
    stored_path = _repo_relative_manifest_path(manifest_path, root)
    active_file = _active_manifest_file(root)
    active_file.parent.mkdir(parents=True, exist_ok=True)
    active_file.write_text(f"{stored_path}\n")
    return stored_path


def stop_active_task(project_root: Union[str, Path] = ".") -> bool:
    active_file = _active_manifest_file(project_root)
    if not active_file.exists():
        return False
    active_file.unlink()
    return True


def _active_manifest_file(project_root: Union[str, Path]) -> Path:
    return Path(project_root) / ".maid" / "active-manifest"


def _read_first_line(path: Path) -> str | None:
    try:
        first_line = path.read_text().splitlines()[0]
    except IndexError:
        return None
    stripped = first_line.strip()
    return stripped or None


def _repo_relative_manifest_path(manifest_path: str, project_root: Path) -> str:
    candidate = Path(manifest_path)
    windows_candidate = PureWindowsPath(manifest_path)
    if (
        candidate.is_absolute()
        or windows_candidate.is_absolute()
        or windows_candidate.drive
    ):
        raise ActiveTaskError(
            "Manifest path must be project-relative and inside the repository."
        )

    try:
        project_abs = project_root.resolve()
        resolved = (project_root / candidate).resolve()
        relative = resolved.relative_to(project_abs)
    except (OSError, RuntimeError, ValueError) as exc:
        raise ActiveTaskError(
            "Manifest path must be project-relative and inside the repository."
        ) from exc

    if not resolved.is_file():
        raise ActiveTaskError(f"Manifest path does not exist: {manifest_path}")

    return relative.as_posix()
