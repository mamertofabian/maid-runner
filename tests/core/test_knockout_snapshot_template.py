"""Behavioral contract for template-backed fresh knockout roots."""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

from maid_runner.core.manifest import load_manifest
from maid_runner.core.result import TestRunResult
from maid_runner.core.types import TestStream


MUTANT_MARKER = 'raise NotImplementedError("maid-knockout")'


def test_template_backed_batch_keeps_distinct_roots_and_editable_mutation_visibility(
    tmp_path: Path,
) -> None:
    from maid_runner.core._knockout_snapshot import (
        WorkerRetainedProjectSnapshotBackend,
    )
    from maid_runner.core.knockout import KnockoutCommandExecutor

    root = _project(tmp_path / "project", names=("alpha",), editable=True)
    backend = WorkerRetainedProjectSnapshotBackend()
    roots: list[Path] = []
    dependency_roots: list[Path] = []
    pycache_roots: list[Path] = []

    with backend.retain():
        for worker_id, value in (
            ("000001-slug-alpha", "first"),
            ("000002-slug-bravo", "second"),
        ):
            with backend.create(root, ("src/target.py",), worker_id) as snapshot:
                roots.append(snapshot.root)
                dependency_roots.append(
                    Path(snapshot.environment_overrides["VIRTUAL_ENV"]).resolve()
                )
                pycache_roots.append(
                    Path(
                        snapshot.environment_overrides["PYTHONPYCACHEPREFIX"]
                    ).resolve()
                )
                (snapshot.root / "src/editable_pkg/__init__.py").write_text(
                    f"VALUE = {value!r}\n", encoding="utf-8"
                )
                (snapshot.root / "expected.txt").write_text(value, encoding="utf-8")
                if value == "first":
                    (snapshot.root / "generated.txt").write_text(
                        "first declaration\n", encoding="utf-8"
                    )
                else:
                    assert not (snapshot.root / "generated.txt").exists()
                result = KnockoutCommandExecutor().execute(
                    ("snapshot-tool",),
                    snapshot.root,
                    "template-contract",
                    snapshot.environment_overrides,
                    snapshot.environment_removals,
                )
                assert result.exit_code == 0, result.stderr
                assert any(pycache_roots[-1].rglob("*.pyc"))

    assert roots[0] != roots[1]
    assert dependency_roots[0] == dependency_roots[1]
    assert pycache_roots[0] != pycache_roots[1]
    assert all(
        pycache.is_relative_to(root) for pycache, root in zip(pycache_roots, roots)
    )
    assert all(not root.exists() for root in roots)
    assert not pycache_roots[0].exists()


def test_live_repository_capture_count_is_constant_across_declarations(
    tmp_path: Path,
) -> None:
    from maid_runner.core._knockout_snapshot import (
        WorkerRetainedProjectSnapshotBackend,
    )

    root = _project(tmp_path / "project", names=("alpha",), git=True)
    backend = WorkerRetainedProjectSnapshotBackend()

    with _record_git_working_directories(tmp_path) as log_path:
        with backend.retain():
            with backend.create(root, ("src/target.py",), "first"):
                pass
            first_capture_count = _git_calls_for(log_path, root)
            for index in range(1, 4):
                with backend.create(root, ("src/target.py",), f"later-{index}"):
                    pass
                assert _git_calls_for(log_path, root) == first_capture_count


@pytest.mark.parametrize("drift", ("source", "repository", "dependency"))
def test_template_batch_fails_closed_on_live_source_repository_or_dependency_drift(
    tmp_path: Path,
    drift: str,
) -> None:
    from maid_runner.core._knockout_snapshot import (
        WorkerRetainedProjectSnapshotBackend,
    )

    root = _project(tmp_path / "project", names=("alpha",), git=True, editable=True)
    backend = WorkerRetainedProjectSnapshotBackend()

    with pytest.raises(RuntimeError, match="changed|identity"):
        with backend.retain():
            with backend.create(root, ("src/target.py",), "capture"):
                pass
            if drift == "source":
                (root / "tests/test_target.py").write_text(
                    "def test_changed():\n    assert True\n", encoding="utf-8"
                )
            elif drift == "repository":
                _git(root, "config", "maid.test-drift", "changed")
            else:
                (root / ".venv/dependency-drift").write_text(
                    "changed\n", encoding="utf-8"
                )


def test_repository_identity_change_invalidates_interrupted_spec_checkpoint(
    tmp_path: Path,
) -> None:
    from maid_runner.core.knockout import run_knockout_batch

    root = _project(tmp_path / "project", names=("alpha",), git=True)
    manifest = _manifest(root, names=("alpha",))
    executor = _RecordingExecutor()

    first = run_knockout_batch((manifest,), root, executor=executor)
    _git(root, "config", "maid.checkpoint-generation", "two")
    second = run_knockout_batch((manifest,), root, executor=executor)

    assert first[manifest.source_path].success is True
    assert second[manifest.source_path].success is True
    assert first[manifest.source_path].results[0].cache_hit is False
    assert second[manifest.source_path].results[0].cache_hit is False
    assert len(executor.roots) == 6


def test_batch_template_captures_later_git_ignored_required_path(
    tmp_path: Path,
) -> None:
    from maid_runner.core.knockout import run_knockout_batch

    root = _project(tmp_path / "project", names=("alpha",))
    (root / "src/tracked.py").write_text(
        "def tracked() -> str:\n    return 'tracked'\n", encoding="utf-8"
    )
    (root / "src/ignored.py").write_text(
        "def ignored() -> str:\n    return 'ignored'\n", encoding="utf-8"
    )
    (root / ".gitignore").write_text("src/ignored.py\n", encoding="utf-8")
    tracked = _manifest_for_path(root, "tracked", "src/tracked.py", "tracked")
    ignored = _manifest_for_path(root, "ignored", "src/ignored.py", "ignored")
    _git(root, "init")
    _git(root, "add", ".")
    _git(
        root,
        "-c",
        "user.name=MAID Test",
        "-c",
        "user.email=maid-test@example.invalid",
        "commit",
        "-m",
        "fixture",
    )

    reports = run_knockout_batch(
        (tracked, ignored),
        root,
        executor=_RecordingExecutor(),
        no_cache=True,
    )

    assert reports[tracked.source_path].success is True
    assert reports[ignored.source_path].success is True
    assert reports[ignored.source_path].results[0].artifact_name == "ignored"
    assert reports[ignored.source_path].results[0].detected is True


def test_bounded_template_batch_matches_reports_without_snapshot_convoy(
    tmp_path: Path,
) -> None:
    from maid_runner.core._knockout_snapshot import MaterializedProjectSnapshotBackend
    from maid_runner.core.knockout import run_knockout_batch

    names = ("alpha", "beta", "gamma", "delta")
    root = _project(tmp_path / "project", names=names, git=True)
    manifest = _manifest(root, names=names)
    reference_executor = _RecordingExecutor()
    executor = _RecordingExecutor()

    reference = run_knockout_batch(
        (manifest,),
        root,
        executor=reference_executor,
        snapshot_backend=MaterializedProjectSnapshotBackend(),
        jobs=1,
        max_processes=1,
        no_cache=True,
    )

    with _record_git_working_directories(tmp_path) as log_path:
        reports = run_knockout_batch(
            (manifest,),
            root,
            executor=executor,
            jobs=1,
            max_processes=1,
            no_cache=True,
        )

    report = reports[manifest.source_path]
    assert report.success is True
    assert [result.artifact_name for result in report.results] == list(names)
    assert all(result.detected for result in report.results)
    assert len(set(executor.roots)) == 1
    assert _git_calls_for(log_path, root) <= 30
    assert _without_durations(report.to_dict()) == _without_durations(
        reference[manifest.source_path].to_dict()
    )


def _project(
    root: Path,
    *,
    names: tuple[str, ...],
    git: bool = False,
    editable: bool = False,
) -> Path:
    (root / "src/editable_pkg").mkdir(parents=True)
    (root / "tests").mkdir()
    (root / "manifests").mkdir()
    (root / "src/__init__.py").write_text("", encoding="utf-8")
    (root / "src/editable_pkg/__init__.py").write_text(
        "VALUE = 'source'\n", encoding="utf-8"
    )
    (root / "src/target.py").write_text(
        "\n\n".join(f"def {name}() -> str:\n    return {name!r}" for name in names)
        + "\n",
        encoding="utf-8",
    )
    (root / "tests/test_target.py").write_text(
        "from src import target\n\n"
        + "\n".join(
            f"def test_{name}():\n    assert target.{name}() == {name!r}\n"
            for name in names
        ),
        encoding="utf-8",
    )
    if editable:
        _write_editable_environment(root)
    else:
        # Synthetic template scenarios need no installed dependency packages.
        (root / ".venv").mkdir()
    if git:
        _git(root, "init")
        _git(root, "add", ".")
        _git(
            root,
            "-c",
            "user.name=MAID Test",
            "-c",
            "user.email=maid-test@example.invalid",
            "commit",
            "-m",
            "fixture",
        )
    return root


def _write_editable_environment(root: Path) -> None:
    subprocess.run(
        ("uv", "venv", ".venv", "--python", sys.executable),
        cwd=root,
        check=True,
        capture_output=True,
    )
    site_packages = next((root / ".venv/lib").glob("python*/site-packages"))
    package = root / "src/editable_pkg/__init__.py"
    (site_packages / "editable_fixture.pth").write_text(
        "import editable_finder\n", encoding="utf-8"
    )
    (site_packages / "editable_finder.py").write_text(
        "import importlib.abc, importlib.util, pathlib, sys\n"
        f"SOURCE = pathlib.Path({str(package)!r})\n"
        "class Finder(importlib.abc.MetaPathFinder):\n"
        "    @classmethod\n"
        "    def find_spec(cls, fullname, path=None, target=None):\n"
        "        if fullname == 'editable_pkg':\n"
        "            return importlib.util.spec_from_file_location(fullname, SOURCE)\n"
        "sys.meta_path.insert(0, Finder)\n",
        encoding="utf-8",
    )
    launcher = root / ".venv/bin/snapshot-tool"
    launcher.write_text(
        f"#!{root / '.venv/bin/python'}\n"
        "import editable_pkg, pathlib\n"
        "assert editable_pkg.VALUE == pathlib.Path('expected.txt').read_text()\n",
        encoding="utf-8",
    )
    launcher.chmod(0o755)


def _manifest(root: Path, *, names: tuple[str, ...]):
    path = root / "manifests/target.manifest.yaml"
    path.write_text(
        """schema: "2"
goal: "Exercise template-backed knockout roots"
type: refactor
created: "2026-08-17T15:00:00Z"
files:
  edit:
    - path: src/target.py
      artifacts:
"""
        + "".join(
            "        - kind: function\n"
            f"          name: {name}\n"
            "          args: []\n"
            "          returns: str\n"
            for name in names
        )
        + """  read:
    - tests/test_target.py
validate:
  - python -m pytest -q tests/test_target.py
""",
        encoding="utf-8",
    )
    return load_manifest(path)


def _manifest_for_path(
    root: Path,
    slug: str,
    file_path: str,
    artifact_name: str,
):
    path = root / f"manifests/{slug}.manifest.yaml"
    path.write_text(
        f"""schema: "2"
goal: "Exercise {slug} template input"
type: refactor
created: "2026-08-17T15:00:00Z"
files:
  edit:
    - path: {file_path}
      artifacts:
        - kind: function
          name: {artifact_name}
          args: []
          returns: str
  read:
    - tests/test_target.py
validate:
  - python -m pytest -q tests/test_target.py
""",
        encoding="utf-8",
    )
    return load_manifest(path)


class _RecordingExecutor:
    def __init__(self) -> None:
        self.roots: list[Path] = []

    def execute(self, command, project_root, manifest_slug, *environment):
        root = Path(project_root)
        self.roots.append(root)
        mutated = any(
            MUTANT_MARKER in path.read_text(encoding="utf-8")
            for path in (root / "src").glob("*.py")
        )
        return TestRunResult(
            manifest_slug=manifest_slug,
            command=tuple(command),
            exit_code=1 if mutated else 0,
            stdout="",
            stderr="",
            duration_ms=1.0,
            stream=TestStream.IMPLEMENTATION,
        )


class _record_git_working_directories:
    def __init__(self, base: Path) -> None:
        self._base = base
        self._original_path = os.environ.get("PATH")
        self.log_path = base / "git-calls.log"

    def __enter__(self) -> Path:
        real_git = shutil.which("git")
        assert real_git is not None
        bin_path = self._base / "recording-bin"
        bin_path.mkdir(exist_ok=True)
        wrapper = bin_path / "git"
        wrapper.write_text(
            "#!/bin/sh\n"
            f"printf '%s\\n' \"$PWD\" >> {str(self.log_path)!r}\n"
            f'exec {real_git!r} "$@"\n',
            encoding="utf-8",
        )
        wrapper.chmod(0o755)
        os.environ["PATH"] = f"{bin_path}{os.pathsep}{self._original_path or ''}"
        return self.log_path

    def __exit__(self, exc_type, exc, traceback) -> None:
        if self._original_path is None:
            os.environ.pop("PATH", None)
        else:
            os.environ["PATH"] = self._original_path


def _git_calls_for(log_path: Path, root: Path) -> int:
    if not log_path.exists():
        return 0
    expected = str(root.resolve())
    return sum(
        line == expected for line in log_path.read_text(encoding="utf-8").splitlines()
    )


def _without_durations(value):
    if isinstance(value, dict):
        return {
            key: _without_durations(item)
            for key, item in value.items()
            if key != "duration_ms"
        }
    if isinstance(value, list):
        return [_without_durations(item) for item in value]
    return value


def _git(root: Path, *args: str) -> str:
    environment = {
        name: value for name, value in os.environ.items() if not name.startswith("GIT_")
    }
    return subprocess.run(
        ("git", *args),
        cwd=root,
        env=environment,
        check=True,
        capture_output=True,
        text=True,
    ).stdout
