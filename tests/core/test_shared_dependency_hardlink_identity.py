"""Behavioral contract for shared dependency hardlink identity."""

from __future__ import annotations

import os
import stat
import sys
from pathlib import Path

import pytest


def _project_with_hardlinked_dependency(tmp_path: Path) -> tuple[Path, Path, Path]:
    project = tmp_path / "project"
    source = project / "src/target.py"
    source.parent.mkdir(parents=True)
    source.write_text("VALUE = 1\n", encoding="utf-8")
    dependency = project / ".venv/lib/python/site-packages/example.py"
    dependency.parent.mkdir(parents=True)
    dependency.write_text("VALUE = 1\n", encoding="utf-8")
    cache_file = tmp_path / "cache/example.py"
    cache_file.parent.mkdir(parents=True)
    os.link(dependency, cache_file)
    return project, dependency, cache_file


def test_shared_snapshot_accepts_transient_external_hardlink_bookkeeping(
    tmp_path: Path,
) -> None:
    from maid_runner.core._knockout_snapshot import (
        SharedEnvironmentProjectSnapshotBackend,
    )

    project, dependency, _cache_file = _project_with_hardlinked_dependency(tmp_path)
    transient = tmp_path / "cache/transient.py"
    before = dependency.stat()

    with SharedEnvironmentProjectSnapshotBackend().create(
        project, ("src/target.py",), "hardlink-bookkeeping"
    ):
        os.link(dependency, transient)
        transient.unlink()

    after = dependency.stat()
    if os.name != "nt":
        assert after.st_ctime_ns > before.st_ctime_ns
    assert after.st_nlink == before.st_nlink
    assert dependency.read_bytes() == b"VALUE = 1\n"


def test_shared_snapshot_rejects_hardlinked_byte_change_with_restored_mtime(
    tmp_path: Path,
) -> None:
    from maid_runner.core._knockout_snapshot import (
        SharedEnvironmentProjectSnapshotBackend,
    )

    project, dependency, _cache_file = _project_with_hardlinked_dependency(tmp_path)
    before = dependency.stat()

    with pytest.raises(RuntimeError, match="source dependency"):
        with SharedEnvironmentProjectSnapshotBackend().create(
            project, ("src/target.py",), "hardlink-byte-change"
        ):
            dependency.write_bytes(b"VALUE = 2\n")
            os.utime(dependency, ns=(before.st_atime_ns, before.st_mtime_ns))


def test_shared_snapshot_rejects_remaining_external_hardlink(tmp_path: Path) -> None:
    from maid_runner.core._knockout_snapshot import (
        SharedEnvironmentProjectSnapshotBackend,
    )

    project, dependency, _cache_file = _project_with_hardlinked_dependency(tmp_path)
    remaining = tmp_path / "cache/remaining.py"

    with pytest.raises(RuntimeError, match="source dependency"):
        with SharedEnvironmentProjectSnapshotBackend().create(
            project, ("src/target.py",), "remaining-hardlink"
        ):
            os.link(dependency, remaining)


def test_shared_snapshot_rejects_hardlinked_mode_change(tmp_path: Path) -> None:
    from maid_runner.core._knockout_snapshot import (
        SharedEnvironmentProjectSnapshotBackend,
    )

    project, dependency, _cache_file = _project_with_hardlinked_dependency(tmp_path)

    with pytest.raises(RuntimeError, match="source dependency"):
        with SharedEnvironmentProjectSnapshotBackend().create(
            project, ("src/target.py",), "hardlink-mode-change"
        ):
            dependency.chmod(dependency.stat().st_mode | stat.S_IXUSR)


def test_shared_snapshot_rejects_hardlinked_mtime_change(tmp_path: Path) -> None:
    from maid_runner.core._knockout_snapshot import (
        SharedEnvironmentProjectSnapshotBackend,
    )

    project, dependency, _cache_file = _project_with_hardlinked_dependency(tmp_path)
    before = dependency.stat()

    with pytest.raises(RuntimeError, match="source dependency"):
        with SharedEnvironmentProjectSnapshotBackend().create(
            project, ("src/target.py",), "hardlink-mtime-change"
        ):
            os.utime(
                dependency,
                ns=(before.st_atime_ns, before.st_mtime_ns + 1_000_000_000),
            )


def test_shared_snapshot_rejects_transient_link_for_initially_single_link_file(
    tmp_path: Path,
) -> None:
    from maid_runner.core._knockout_snapshot import (
        SharedEnvironmentProjectSnapshotBackend,
    )

    project = tmp_path / "project"
    source = project / "src/target.py"
    source.parent.mkdir(parents=True)
    source.write_text("VALUE = 1\n", encoding="utf-8")
    dependency = project / ".venv/lib/python/site-packages/example.py"
    dependency.parent.mkdir(parents=True)
    dependency.write_text("VALUE = 1\n", encoding="utf-8")
    transient = tmp_path / "transient.py"
    assert dependency.stat().st_nlink == 1

    with pytest.raises(RuntimeError, match="source dependency"):
        with SharedEnvironmentProjectSnapshotBackend().create(
            project, ("src/target.py",), "single-link-bookkeeping"
        ):
            os.link(dependency, transient)
            transient.unlink()


def test_shared_snapshot_disables_source_dependency_bytecode_writes(
    tmp_path: Path,
) -> None:
    from maid_runner.core._knockout_snapshot import (
        SharedEnvironmentProjectSnapshotBackend,
    )
    from maid_runner.core.knockout import KnockoutCommandExecutor

    project, dependency, _cache_file = _project_with_hardlinked_dependency(tmp_path)
    site_packages = dependency.parent
    pycache = site_packages / "__pycache__"

    with SharedEnvironmentProjectSnapshotBackend().create(
        project, ("src/target.py",), "disable-shared-bytecode"
    ) as snapshot:
        environment = dict(snapshot.environment_overrides)
        environment.pop("PYTHONPYCACHEPREFIX")
        environment["PYTHONPATH"] = os.pathsep.join(
            (str(site_packages), environment["PYTHONPATH"])
        )
        assert environment["PYTHONDONTWRITEBYTECODE"] == "1"
        result = KnockoutCommandExecutor().execute(
            (sys.executable, "-c", "import example"),
            snapshot.root,
            "shared-dependency-import",
            environment,
            snapshot.environment_removals,
        )

    assert result.exit_code == 0, result.stderr
    assert not pycache.exists()
