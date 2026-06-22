"""Install user-level MAID skills (the maid-onboard bootstrapper).

Policy is separated from the composition root: ``install_onboard_skill`` takes
both the target root (the user home) and the packaged payload root as explicit
parameters and performs no environment lookups, so it is testable against a
temporary directory.
"""

from __future__ import annotations

import shutil
from pathlib import Path


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
