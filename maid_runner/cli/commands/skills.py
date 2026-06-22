"""CLI handler for `maid skills` subcommands."""

from __future__ import annotations

import argparse
import os
from importlib import resources
from pathlib import Path

from maid_runner.cli.commands._format import print_error
from maid_runner.core.skill_install import install_onboard_skill


def cmd_skills(args: argparse.Namespace) -> int:
    subcommand = getattr(args, "skills_command", None)
    if subcommand == "install":
        return _cmd_skills_install(args)

    print_error("Unknown or missing skills subcommand")
    return 2


def _cmd_skills_install(args: argparse.Namespace) -> int:
    target_root = _resolve_target_root(args)
    payload_root = _packaged_user_skills_root()
    link = bool(getattr(args, "link", False))

    try:
        written = install_onboard_skill(target_root, payload_root, link)
    except FileNotFoundError as exc:
        print_error(str(exc))
        return 1

    if not written:
        print_error(
            f"No user skills payload found to install (looked in {payload_root})."
        )
        return 1

    linked = link and all(
        os.path.islink(target_root / relative) for relative in written
    )
    if not link:
        summary = f"Installed maid-onboard skill ({len(written)} files)"
    elif linked:
        summary = f"Linked maid-onboard skill ({len(written)} files)"
    else:
        summary = (
            f"Installed maid-onboard skill ({len(written)} files) "
            "[symlinks unavailable; copied instead]"
        )

    print(f"{summary} under {target_root}")
    for relative in written:
        print(f"  {relative}")
    return 0


def _resolve_target_root(args: argparse.Namespace) -> Path:
    target = getattr(args, "target_root", None)
    if target:
        return Path(target)
    return Path.home()


def _packaged_user_skills_root() -> Path:
    return Path(str(resources.files("maid_runner").joinpath("user_skills")))
