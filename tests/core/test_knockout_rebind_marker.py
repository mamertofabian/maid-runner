"""Behavioral contract for retained-venv rebind marker self-hit prevention."""

from __future__ import annotations

from pathlib import Path

import pytest

MARKER_ASCII = "__MAID_RETAINED_VIRTUAL_ENVIRONMENT__"
MARKER_HEX = (
    "5f5f4d4149445f52455441494e45445f5649525455414c5f454e5649524f4e4d454e545f5f"
)


def test_knockout_snapshot_module_source_does_not_embed_rebind_marker() -> None:
    import maid_runner.core._knockout_snapshot as module

    source = Path(module.__file__).read_text(encoding="utf-8")
    assert MARKER_ASCII not in source


def test_rebind_succeeds_when_venv_contains_installed_snapshot_module(
    tmp_path: Path,
) -> None:
    from maid_runner.core._knockout_snapshot import _rebind_copied_python_project_root

    previous_root = tmp_path / "deps-holder"
    current_root = tmp_path / "snapshot-root"
    venv = previous_root / ".venv"
    site_packages = venv / "lib" / "python3.13" / "site-packages"
    site_packages.mkdir(parents=True)

    import maid_runner.core._knockout_snapshot as snapshot_module

    installed_module = site_packages / "_knockout_snapshot.py"
    installed_module.write_bytes(Path(snapshot_module.__file__).read_bytes())
    (site_packages / "project-root.pth").write_bytes(f"{previous_root}\n".encode())

    _rebind_copied_python_project_root(venv, previous_root, current_root)

    rewritten = (site_packages / "project-root.pth").read_bytes()
    assert str(current_root).encode() in rewritten
    assert str(previous_root).encode() not in rewritten


def test_rebind_fails_closed_on_leftover_runtime_marker(tmp_path: Path) -> None:
    from maid_runner.core._knockout_snapshot import _rebind_copied_python_project_root

    previous_root = tmp_path / "deps-holder"
    current_root = tmp_path / "snapshot-root"
    venv = previous_root / ".venv"
    site_packages = venv / "lib" / "python3.13" / "site-packages"
    site_packages.mkdir(parents=True)

    marker = bytes.fromhex(MARKER_HEX)
    (site_packages / "leftover.pth").write_bytes(b"import sys\n" + marker + b"\n")

    with pytest.raises(
        RuntimeError,
        match="Retained dependency metadata contains the reserved rebind marker",
    ):
        _rebind_copied_python_project_root(venv, previous_root, current_root)
