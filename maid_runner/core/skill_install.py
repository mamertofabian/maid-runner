"""Install user-level MAID skills (the maid-onboard bootstrapper).

Policy is separated from the composition root: ``install_onboard_skill`` takes
both the target root (the user home) and the packaged payload root as explicit
parameters and performs no environment lookups, so it is testable against a
temporary directory.
"""

from __future__ import annotations

import os
import shutil
import stat
from pathlib import Path

from maid_runner.core.uninstall import UninstallReport


_USER_SKILL_TOOLS = ("claude", "codex")
_ONBOARD_SKILL = "maid-onboard"


def install_onboard_skill(
    target_root: Path, payload_root: Path, link: bool
) -> list[str]:
    """Install the maid-onboard skill from ``payload_root`` into ``target_root``.

    For each supported tool, the skill is written under
    ``<target_root>/.<tool>/skills/maid-onboard/``. The destination skill
    directory is replaced wholesale so reinstalls are convergent (stale files
    from an older payload are removed). Files are copied by default; when
    ``link`` is true they are symlinked, falling back to a copy when the
    platform does not support symlinks. Returns the POSIX-relative paths written
    under ``target_root``.

    Raises ``FileNotFoundError`` if the payload does not contain a maid-onboard
    skill for every supported tool, so an incomplete package fails loudly rather
    than installing a partial skill set.
    """
    target_root = Path(target_root)
    payload_root = Path(payload_root)

    missing = [
        tool
        for tool in _USER_SKILL_TOOLS
        if not (payload_root / tool / _ONBOARD_SKILL).is_dir()
    ]
    if missing:
        raise FileNotFoundError(
            f"Incomplete maid-onboard payload under {payload_root}: "
            f"missing {', '.join(missing)} skill source."
        )

    written: list[str] = []
    for tool in _USER_SKILL_TOOLS:
        source_dir = payload_root / tool / _ONBOARD_SKILL
        dest_dir = target_root / f".{tool}" / "skills" / _ONBOARD_SKILL
        _reset_directory(dest_dir)
        for source_file in sorted(source_dir.rglob("*")):
            if not source_file.is_file():
                continue
            relative = source_file.relative_to(source_dir)
            destination = dest_dir / relative
            destination.parent.mkdir(parents=True, exist_ok=True)
            _place_file(source_file, destination, link)
            written.append(
                (Path(f".{tool}") / "skills" / _ONBOARD_SKILL / relative).as_posix()
            )
    return written


def uninstall_onboard_skill(
    target_root: Path, payload_root: Path, dry_run: bool
) -> UninstallReport:
    """Remove unchanged maid-onboard installs without following redirected links."""
    target_root = Path(target_root)
    payload_root = Path(payload_root)
    removed: list[str] = []
    preserved: list[str] = []
    missing: list[str] = []

    for tool in _USER_SKILL_TOOLS:
        relative = Path(f".{tool}") / "skills" / _ONBOARD_SKILL
        destination = target_root / relative
        source = payload_root / tool / _ONBOARD_SKILL
        label = relative.as_posix()
        if not os.path.lexists(destination):
            missing.append(label)
            continue
        if (
            _has_symlinked_parent(target_root, destination)
            or not source.is_dir()
            or not _installed_tree_matches(source, destination)
        ):
            preserved.append(label)
            continue
        removed.append(label)

    report = UninstallReport(
        removed=sorted(removed),
        preserved=sorted(preserved),
        missing=sorted(missing),
    )
    if dry_run:
        return report

    for label in report.removed:
        destination = target_root / label
        if _has_symlinked_parent(target_root, destination):
            raise ValueError(
                f"refusing to cross symlink boundary during uninstall: {destination}"
            )
        source = (
            payload_root / label.split("/", 1)[0].removeprefix(".") / _ONBOARD_SKILL
        )
        _remove_owned_skill_tree(target_root, destination, source)
    return report


def _installed_tree_matches(source: Path, destination: Path) -> bool:
    if destination.is_symlink() or not destination.is_dir():
        return False
    source_entries = {
        path.relative_to(source).as_posix(): path
        for path in source.rglob("*")
        if path.is_file()
    }
    destination_entries = {
        path.relative_to(destination).as_posix(): path
        for path in destination.rglob("*")
        if path.is_file() or path.is_symlink()
    }
    if set(source_entries) != set(destination_entries):
        return False
    for relative, installed in destination_entries.items():
        packaged = source_entries[relative]
        if installed.is_symlink():
            try:
                if installed.resolve(strict=True) != packaged.resolve(strict=True):
                    return False
            except OSError:
                return False
        elif installed.read_bytes() != packaged.read_bytes():
            return False
    source_dirs = {
        path.relative_to(source).as_posix()
        for path in source.rglob("*")
        if path.is_dir()
    }
    destination_dirs = {
        path.relative_to(destination).as_posix()
        for path in destination.rglob("*")
        if path.is_dir() and not path.is_symlink()
    }
    return source_dirs == destination_dirs


def _has_symlinked_parent(target_root: Path, destination: Path) -> bool:
    relative = destination.relative_to(target_root)
    current = target_root
    for component in relative.parts[:-1]:
        current = current / component
        if current.is_symlink():
            return True
    return False


def _supports_descriptor_relative_skill_removal() -> bool:
    return (
        os.open in os.supports_dir_fd
        and os.stat in os.supports_dir_fd
        and os.unlink in os.supports_dir_fd
        and bool(getattr(shutil.rmtree, "avoids_symlink_attacks", False))
    )


def _remove_owned_skill_tree(
    target_root: Path, destination: Path, source: Path
) -> None:
    if not _installed_tree_matches(source, destination):
        raise ValueError(f"{destination} changed after uninstall planning")
    if not _supports_descriptor_relative_skill_removal():
        raise OSError(
            "safe descriptor-relative skill uninstall is unavailable on this "
            "platform; refusing pathname-based mutation"
        )

    flags = os.O_RDONLY | getattr(os, "O_DIRECTORY", 0) | getattr(os, "O_NOFOLLOW", 0)
    descriptor = os.open(target_root, flags)
    try:
        relative = destination.relative_to(target_root)
        for component in relative.parts[:-1]:
            child = os.open(component, flags, dir_fd=descriptor)
            os.close(descriptor)
            descriptor = child
        name = relative.name
        stat_result = os.stat(name, dir_fd=descriptor, follow_symlinks=False)
        if stat.S_ISDIR(stat_result.st_mode):
            shutil.rmtree(name, dir_fd=descriptor)
        else:
            os.unlink(name, dir_fd=descriptor)
    finally:
        os.close(descriptor)


def _reset_directory(path: Path) -> None:
    if path.is_symlink() or path.is_file():
        path.unlink()
    elif path.is_dir():
        shutil.rmtree(path)
    path.mkdir(parents=True)


def _place_file(source_file: Path, destination: Path, link: bool) -> None:
    if link:
        try:
            destination.symlink_to(source_file.resolve())
            return
        except (OSError, NotImplementedError):
            pass
    shutil.copyfile(source_file, destination)
