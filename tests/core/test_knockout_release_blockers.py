"""Behavioral contracts for repository-wide knockout blocker fixes."""

from __future__ import annotations

import subprocess
import sys
import threading
from pathlib import Path

import pytest
import yaml

from maid_runner.core.manifest import load_manifest


def test_default_executor_shares_identical_baseline_across_manifest_slugs(
    tmp_path: Path,
) -> None:
    from maid_runner.core.knockout import run_knockout_batch

    root = tmp_path / "project"
    log_path = tmp_path / "command-phases.log"
    _write_cross_manifest_project(root, log_path)
    first = load_manifest(root / "manifests/first.manifest.yaml")
    second = load_manifest(root / "manifests/second.manifest.yaml")

    reports = run_knockout_batch(
        (first, second),
        root,
        jobs=2,
        max_processes=2,
        no_cache=True,
    )

    assert reports[first.source_path].success is True, reports[first.source_path].errors
    assert reports[second.source_path].success is True, reports[
        second.source_path
    ].errors
    assert [result.artifact_name for result in reports[first.source_path].results] == [
        "alpha"
    ]
    assert [result.artifact_name for result in reports[second.source_path].results] == [
        "beta"
    ]
    phases = log_path.read_text(encoding="utf-8").splitlines()
    assert phases.count("green") == 3
    assert phases.count("mutant") == 2


def test_default_executor_serializes_identical_ineligible_commands(
    tmp_path: Path,
) -> None:
    from maid_runner.core.knockout import run_knockout_batch

    root = tmp_path / "project"
    log_path = tmp_path / "ineligible-phases.log"
    lock_path = tmp_path / "ineligible-command.lock"
    _write_ineligible_command_project(root, log_path, lock_path)
    first = load_manifest(root / "manifests/first.manifest.yaml")
    second = load_manifest(root / "manifests/second.manifest.yaml")

    reports = run_knockout_batch(
        (first, second),
        root,
        jobs=3,
        max_processes=3,
        no_cache=True,
    )

    assert reports[first.source_path].success is True, reports[first.source_path].errors
    assert reports[second.source_path].success is True, reports[
        second.source_path
    ].errors
    assert [result.artifact_name for result in reports[first.source_path].results] == [
        "shared",
        "alpha",
    ]
    assert [result.artifact_name for result in reports[second.source_path].results] == [
        "shared",
        "beta",
    ]
    phases = log_path.read_text(encoding="utf-8").splitlines()
    assert "overlap" not in phases
    assert phases.count("green") == 8
    assert phases.count("mutant") == 4


def test_default_executor_keeps_distinct_commands_parallel(tmp_path: Path) -> None:
    from maid_runner.core.knockout import run_knockout_batch

    root = tmp_path / "project"
    marker_root = tmp_path / "distinct-markers"
    _write_distinct_command_project(root, marker_root)
    first = load_manifest(root / "manifests/first.manifest.yaml")
    second = load_manifest(root / "manifests/second.manifest.yaml")

    reports = run_knockout_batch(
        (first, second),
        root,
        jobs=2,
        max_processes=2,
        no_cache=True,
    )

    assert reports[first.source_path].success is True, reports[first.source_path].errors
    assert reports[second.source_path].success is True, reports[
        second.source_path
    ].errors
    assert (marker_root / "alpha").is_file()
    assert (marker_root / "beta").is_file()


def test_injected_executor_keeps_identical_commands_parallel(tmp_path: Path) -> None:
    from maid_runner.core.knockout import run_knockout_batch
    from maid_runner.core.result import TestRunResult

    root = tmp_path / "project"
    _write_cross_manifest_project(root, tmp_path / "unused.log")
    first = load_manifest(root / "manifests/first.manifest.yaml")
    second = load_manifest(root / "manifests/second.manifest.yaml")
    barrier = threading.Barrier(2)
    state_lock = threading.Lock()

    class ConcurrentExecutor:
        def __init__(self) -> None:
            self.initial_green_slugs: set[str] = set()
            self.active = 0
            self.max_active = 0

        def execute(
            self,
            command,
            project_root,
            manifest_slug,
            environment_overrides=(),
            environment_removals=(),
        ) -> TestRunResult:
            source = (Path(project_root) / "src/target.py").read_text(encoding="utf-8")
            mutated = 'raise NotImplementedError("maid-knockout")' in source
            should_wait = False
            with state_lock:
                self.active += 1
                self.max_active = max(self.max_active, self.active)
                if not mutated and manifest_slug not in self.initial_green_slugs:
                    self.initial_green_slugs.add(manifest_slug)
                    should_wait = True
            try:
                if should_wait:
                    barrier.wait(timeout=2)
                return TestRunResult(
                    command=tuple(command),
                    exit_code=1 if mutated else 0,
                    stdout="",
                    stderr="",
                    duration_ms=1.0,
                    manifest_slug=manifest_slug,
                )
            finally:
                with state_lock:
                    self.active -= 1

    executor = ConcurrentExecutor()
    reports = run_knockout_batch(
        (first, second),
        root,
        executor=executor,
        jobs=2,
        max_processes=2,
        no_cache=True,
    )

    assert reports[first.source_path].success is True, reports[first.source_path].errors
    assert reports[second.source_path].success is True, reports[
        second.source_path
    ].errors
    assert executor.max_active >= 2


@pytest.mark.parametrize("export_style", ("plain", "aliased"))
def test_knockout_mutates_one_level_package_reexport_implementation(
    tmp_path: Path,
    export_style: str,
) -> None:
    from maid_runner.core.knockout import (
        build_knockout_mutation_specs,
        run_knockout_batch,
    )

    root = tmp_path / export_style
    manifest = _write_reexport_project(root, export_style)
    facade = root / "pkg/__init__.py"
    implementation = root / "pkg/implementation.py"
    original_facade = facade.read_bytes()
    original_implementation = implementation.read_bytes()

    spec = build_knockout_mutation_specs((manifest,), root)[0]
    report = run_knockout_batch((manifest,), root, no_cache=True)[manifest.source_path]

    assert spec.identity.file_path == "pkg/__init__.py"
    assert spec.mutation_file_path == "pkg/implementation.py"
    assert spec.mutation_artifact_name == (
        "run_server" if export_style == "aliased" else "serve"
    )
    assert report.success is True
    assert report.errors == ()
    assert len(report.results) == 1
    result = report.results[0]
    assert result.file_path == "pkg/__init__.py"
    assert result.artifact_name == "serve"
    assert result.detected is True
    assert result.proof is not None
    assert (result.proof.baseline_exit_code, result.proof.mutant_exit_code) == (0, 1)
    assert result.proof.restored_exit_code == 0
    assert facade.read_bytes() == original_facade
    assert implementation.read_bytes() == original_implementation


@pytest.mark.parametrize("layout", ("star", "multi-hop"))
def test_knockout_reexport_resolution_fails_closed_when_target_is_ambiguous(
    tmp_path: Path,
    layout: str,
) -> None:
    from maid_runner.core.knockout import run_knockout_batch

    root = tmp_path / layout
    manifest = _write_reexport_project(root, layout)
    original = {
        path.relative_to(root).as_posix(): path.read_bytes()
        for path in (root / "pkg").glob("*.py")
    }

    report = run_knockout_batch((manifest,), root, no_cache=True)[manifest.source_path]

    assert report.success is False
    assert len(report.results) == 1
    assert report.results[0].file_path == "pkg/__init__.py"
    assert report.results[0].artifact_name == "serve"
    assert report.results[0].detected is False
    assert report.errors
    assert all(error.code.value == "E712" for error in report.errors)
    assert "artifact not found" in report.errors[0].message.lower()
    assert {
        path.relative_to(root).as_posix(): path.read_bytes()
        for path in (root / "pkg").glob("*.py")
    } == original


def _write_cross_manifest_project(root: Path, log_path: Path) -> None:
    (root / "src").mkdir(parents=True)
    (root / "manifests").mkdir()
    (root / "src/__init__.py").write_text("", encoding="utf-8")
    (root / "src/target.py").write_text(
        "def alpha() -> str:\n    return 'alpha'\n\n"
        "def beta() -> str:\n    return 'beta'\n",
        encoding="utf-8",
    )
    (root / "check_knockout.py").write_text(
        "from pathlib import Path\n"
        "import sys\n"
        "source = Path('src/target.py').read_text(encoding='utf-8')\n"
        "mutated = 'raise NotImplementedError(\"maid-knockout\")' in source\n"
        "with Path(sys.argv[1]).open('a', encoding='utf-8') as stream:\n"
        "    stream.write('mutant\\n' if mutated else 'green\\n')\n"
        "raise SystemExit(1 if mutated else 0)\n",
        encoding="utf-8",
    )
    command = f"{sys.executable} check_knockout.py {log_path}"
    for slug, artifact in (("first", "alpha"), ("second", "beta")):
        _write_manifest(
            root,
            slug,
            "src/target.py",
            artifact,
            command,
        )
    _commit_fixture(root)


def _write_ineligible_command_project(
    root: Path,
    log_path: Path,
    lock_path: Path,
) -> None:
    (root / "src").mkdir(parents=True)
    (root / "manifests").mkdir()
    (root / "src/__init__.py").write_text("", encoding="utf-8")
    (root / "src/target.py").write_text(
        "def shared() -> str:\n    return 'shared'\n\n"
        "def alpha() -> str:\n    return 'alpha'\n\n"
        "def beta() -> str:\n    return 'beta'\n",
        encoding="utf-8",
    )
    (root / "check_serialized.py").write_text(
        "import os\n"
        "from pathlib import Path\n"
        "import sys\n"
        "import time\n"
        "lock = Path(sys.argv[1])\n"
        "log = Path(sys.argv[2])\n"
        "try:\n"
        "    descriptor = os.open(lock, os.O_CREAT | os.O_EXCL | os.O_WRONLY)\n"
        "except FileExistsError:\n"
        "    with log.open('a', encoding='utf-8') as stream:\n"
        "        stream.write('overlap\\n')\n"
        "    raise SystemExit(9)\n"
        "try:\n"
        "    os.close(descriptor)\n"
        "    time.sleep(0.15)\n"
        "    source = Path('src/target.py').read_text(encoding='utf-8')\n"
        "    mutated = 'raise NotImplementedError(\"maid-knockout\")' in source\n"
        "    with log.open('a', encoding='utf-8') as stream:\n"
        "        stream.write('mutant\\n' if mutated else 'green\\n')\n"
        "    raise SystemExit(1 if mutated else 0)\n"
        "finally:\n"
        "    lock.unlink(missing_ok=True)\n",
        encoding="utf-8",
    )
    shared_command = f"{sys.executable} check_serialized.py {lock_path} {log_path}"
    never_reached = f'{sys.executable} -c "raise SystemExit(99)"'
    for slug, artifacts in (
        ("first", ("shared", "alpha")),
        ("second", ("shared", "beta")),
    ):
        _write_manifest_with_commands(
            root,
            slug,
            artifacts,
            (shared_command, never_reached),
        )
    _commit_fixture(root)


def _write_distinct_command_project(root: Path, marker_root: Path) -> None:
    (root / "src").mkdir(parents=True)
    (root / "manifests").mkdir()
    marker_root.mkdir()
    (root / "src/__init__.py").write_text("", encoding="utf-8")
    (root / "src/target.py").write_text(
        "def alpha() -> str:\n    return 'alpha'\n\n"
        "def beta() -> str:\n    return 'beta'\n",
        encoding="utf-8",
    )
    (root / "check_distinct.py").write_text(
        "from pathlib import Path\n"
        "import sys\n"
        "import time\n"
        "marker = Path(sys.argv[1])\n"
        "peer = Path(sys.argv[2])\n"
        "marker.touch()\n"
        "deadline = time.monotonic() + 2\n"
        "while not peer.exists() and time.monotonic() < deadline:\n"
        "    time.sleep(0.01)\n"
        "if not peer.exists():\n"
        "    raise SystemExit(8)\n"
        "source = Path('src/target.py').read_text(encoding='utf-8')\n"
        "mutated = 'raise NotImplementedError(\"maid-knockout\")' in source\n"
        "raise SystemExit(1 if mutated else 0)\n",
        encoding="utf-8",
    )
    for slug, artifact, peer in (
        ("first", "alpha", "beta"),
        ("second", "beta", "alpha"),
    ):
        command = (
            f"{sys.executable} check_distinct.py "
            f"{marker_root / artifact} {marker_root / peer}"
        )
        _write_manifest(root, slug, "src/target.py", artifact, command)
    _commit_fixture(root)


def _write_reexport_project(root: Path, layout: str):
    (root / "pkg").mkdir(parents=True)
    (root / "tests").mkdir()
    (root / "manifests").mkdir()
    implementation_name = "serve" if layout != "aliased" else "run_server"
    (root / "pkg/implementation.py").write_text(
        f"def {implementation_name}() -> str:\n" "    return 'served'\n",
        encoding="utf-8",
    )
    if layout == "plain":
        facade = "from .implementation import serve\n"
    elif layout == "aliased":
        facade = "from .implementation import run_server as serve\n"
    elif layout == "star":
        facade = "from .implementation import *\n"
    else:
        (root / "pkg/middle.py").write_text(
            "from .implementation import serve\n", encoding="utf-8"
        )
        facade = "from .middle import serve\n"
    (root / "pkg/__init__.py").write_text(facade, encoding="utf-8")
    (root / "tests/test_api.py").write_text(
        "from pkg import serve\n\n"
        "def test_public_serve():\n"
        "    assert serve() == 'served'\n",
        encoding="utf-8",
    )
    manifest = _write_manifest(
        root,
        "reexport",
        "pkg/__init__.py",
        "serve",
        f"{sys.executable} -m pytest -q tests/test_api.py",
    )
    _commit_fixture(root)
    return load_manifest(manifest)


def _write_manifest(
    root: Path,
    slug: str,
    file_path: str,
    artifact: str,
    command: str,
) -> Path:
    path = root / f"manifests/{slug}.manifest.yaml"
    path.write_text(
        yaml.safe_dump(
            {
                "schema": "2",
                "goal": slug,
                "type": "fix",
                "created": "2026-08-18T00:00:00Z",
                "files": {
                    "edit": [
                        {
                            "path": file_path,
                            "artifacts": [
                                {
                                    "kind": "function",
                                    "name": artifact,
                                    "args": [],
                                    "returns": "str",
                                }
                            ],
                        }
                    ]
                },
                "validate": [command],
            },
            sort_keys=False,
        ),
        encoding="utf-8",
    )
    return path


def _write_manifest_with_commands(
    root: Path,
    slug: str,
    artifacts: tuple[str, ...],
    commands: tuple[str, ...],
) -> Path:
    path = root / f"manifests/{slug}.manifest.yaml"
    path.write_text(
        yaml.safe_dump(
            {
                "schema": "2",
                "goal": slug,
                "type": "fix",
                "created": "2026-08-18T00:00:00Z",
                "files": {
                    "edit": [
                        {
                            "path": "src/target.py",
                            "artifacts": [
                                {
                                    "kind": "function",
                                    "name": artifact,
                                    "args": [],
                                    "returns": "str",
                                }
                                for artifact in artifacts
                            ],
                        }
                    ]
                },
                "validate": list(commands),
            },
            sort_keys=False,
        ),
        encoding="utf-8",
    )
    return path


def _commit_fixture(root: Path) -> None:
    # Commands use an absolute interpreter and need no copied package environment.
    (root / ".venv").mkdir(exist_ok=True)
    subprocess.run(("git", "init"), cwd=root, check=True, capture_output=True)
    subprocess.run(("git", "add", "."), cwd=root, check=True, capture_output=True)
    subprocess.run(
        (
            "git",
            "-c",
            "user.name=MAID Test",
            "-c",
            "user.email=maid-test@example.invalid",
            "commit",
            "-m",
            "fixture",
        ),
        cwd=root,
        check=True,
        capture_output=True,
    )
