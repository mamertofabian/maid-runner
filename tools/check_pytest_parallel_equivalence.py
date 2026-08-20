"""Prove serial/xdist pytest equivalence in fresh subprocesses.

This is an explicit acceptance probe, not a normally collected test.  It keeps
the expensive repository-wide comparison outside pytest so selecting the full
suite cannot recursively launch another full suite.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import stat
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Sequence


_PLUGIN_MODULE = "maid_pytest_equivalence_plugin"
_PLUGIN_OUTPUT_ENV = "MAID_PYTEST_EQUIVALENCE_OUTPUT"
_EXCLUDED_SNAPSHOT_NAMES = frozenset(
    {
        ".claude-automation",
        ".codex-automation",
        ".pytest_cache",
        ".ruff_cache",
        ".mypy_cache",
        "__pycache__",
        "maid_runner.egg-info",
    }
)
_PLUGIN_SOURCE = r"""
import importlib.metadata
import json
import os
import platform
import sys
from pathlib import Path

import pytest


_outcomes = []
_controller_collection = []
_worker_collections = {}
_worker_environments = {}


def _normalize_nodeid(nodeid):
    return nodeid.replace(str(Path.cwd().resolve()), "<PROJECT_ROOT>")


def _environment_identity():
    return [
        [
            "python",
            f"{Path(sys.executable).resolve()}|"
            f"{platform.python_implementation()} {platform.python_version()}",
        ],
        ["pytest", pytest.__version__],
        ["pytest-xdist", importlib.metadata.version("pytest-xdist")],
    ]


def pytest_configure(config):
    worker_input = getattr(config, "workerinput", None)
    if not isinstance(worker_input, dict):
        return
    main_argv = worker_input.get("mainargv", [])
    for index, argument in enumerate(main_argv):
        if argument == "--dist" and index + 1 < len(main_argv):
            config.option.dist = main_argv[index + 1]
            return
        if argument.startswith("--dist="):
            config.option.dist = argument.partition("=")[2]
            return


def pytest_collection_finish(session):
    global _controller_collection
    if not hasattr(session.config, "workerinput"):
        _controller_collection = [_normalize_nodeid(item.nodeid) for item in session.items]


def pytest_runtest_logreport(report):
    _outcomes.append(
        {
            "nodeid": _normalize_nodeid(report.nodeid),
            "phase": report.when,
            "outcome": report.outcome,
        }
    )


@pytest.hookimpl(optionalhook=True)
def pytest_xdist_node_collection_finished(node, ids):
    worker_id = node.gateway.id
    _worker_collections[worker_id] = [_normalize_nodeid(nodeid) for nodeid in ids]


@pytest.hookimpl(optionalhook=True)
def pytest_testnodedown(node, error):
    worker_id = node.gateway.id
    worker_output = getattr(node, "workeroutput", {})
    _worker_environments[worker_id] = worker_output.get("maid_environment")


def pytest_sessionfinish(session, exitstatus):
    config = session.config
    if hasattr(config, "workerinput"):
        config.workeroutput["maid_environment"] = _environment_identity()
        return

    worker_collections = [
        [worker_id, nodeids]
        for worker_id, nodeids in sorted(_worker_collections.items())
    ]
    collection = _controller_collection
    if worker_collections:
        collection = worker_collections[0][1]

    payload = {
        "collection": collection,
        "outcomes": _outcomes,
        "worker_collections": worker_collections,
        "environment": _environment_identity(),
        "worker_environments": [
            [worker_id, environment]
            for worker_id, environment in sorted(_worker_environments.items())
        ],
        "dist_mode": config.getoption("dist", default="no"),
    }
    output_path = Path(os.environ["MAID_PYTEST_EQUIVALENCE_OUTPUT"])
    output_path.write_text(json.dumps(payload, sort_keys=True), encoding="utf-8")
"""


@dataclass(frozen=True, order=True)
class CanonicalPytestOutcome:
    """Immutable canonical outcome for one collected node or test phase."""

    nodeid: str
    phase: str
    outcome: str


@dataclass(frozen=True)
class PytestEquivalenceReport:
    """Comparison evidence from fresh serial and xdist pytest processes."""

    serial_outcomes: tuple[CanonicalPytestOutcome, ...]
    parallel_outcomes: tuple[CanonicalPytestOutcome, ...]
    serial_exit_code: int
    parallel_exit_code: int
    parallel_worker_collections: tuple[tuple[str, tuple[str, ...]], ...]
    serial_environment: tuple[tuple[str, str], ...]
    parallel_environment: tuple[tuple[str, str], ...]
    differences: tuple[str, ...]
    workers: int
    dist_mode: str
    success: bool


@dataclass(frozen=True)
class _PytestRunEvidence:
    outcomes: tuple[CanonicalPytestOutcome, ...]
    exit_code: int
    worker_collections: tuple[tuple[str, tuple[str, ...]], ...]
    environment: tuple[tuple[str, str], ...]
    worker_environments: tuple[tuple[str, tuple[tuple[str, str], ...]], ...]
    dist_mode: str
    evidence_error: str | None = None


def _project_fingerprint(project_root: Path) -> tuple[tuple[str, str], ...]:
    entries: list[tuple[str, str]] = []
    for path in (project_root, *sorted(project_root.rglob("*"))):
        relative = Path(".") if path == project_root else path.relative_to(project_root)
        if relative.parts and relative.parts[0] == ".git":
            continue
        file_stat = path.lstat()
        metadata = (
            f"mode={stat.S_IMODE(file_stat.st_mode):o};"
            f"uid={file_stat.st_uid};gid={file_stat.st_gid};"
            f"nlink={file_stat.st_nlink};ctime={file_stat.st_ctime_ns}"
        )
        if stat.S_ISLNK(file_stat.st_mode):
            value = f"symlink:{metadata};target={os.readlink(path)}"
        elif stat.S_ISREG(file_stat.st_mode):
            digest = hashlib.sha256(path.read_bytes()).hexdigest()
            value = f"file:{metadata};sha256={digest}"
        elif stat.S_ISDIR(file_stat.st_mode):
            value = f"directory:{metadata}"
        else:
            value = (
                f"special:{metadata};type={stat.S_IFMT(file_stat.st_mode):o};"
                f"rdev={file_stat.st_rdev}"
            )
        entries.append((relative.as_posix(), value))
    entries.extend(_git_control_fingerprint(project_root))
    return tuple(sorted(entries))


def _git_control_fingerprint(project_root: Path) -> tuple[tuple[str, str], ...]:
    marker = project_root / ".git"
    if not marker.exists():
        return ()

    entries: list[tuple[str, str]] = []
    if marker.is_file():
        marker_bytes = marker.read_bytes()
        marker_stat = marker.lstat()
        marker_metadata = (
            f"mode={stat.S_IMODE(marker_stat.st_mode):o};"
            f"uid={marker_stat.st_uid};gid={marker_stat.st_gid};"
            f"nlink={marker_stat.st_nlink};ctime={marker_stat.st_ctime_ns}"
        )
        entries.append(
            (
                "@git/pointer",
                f"{marker_metadata};"
                f"sha256={hashlib.sha256(marker_bytes).hexdigest()}",
            )
        )
        prefix, separator, raw_git_dir = (
            marker_bytes.decode("utf-8", errors="strict").strip().partition(":")
        )
        if prefix != "gitdir" or not separator:
            raise ValueError("linked-worktree .git pointer is invalid")
        git_dir_path = Path(raw_git_dir.strip())
        git_dir = (
            git_dir_path if git_dir_path.is_absolute() else marker.parent / git_dir_path
        ).resolve()
    elif marker.is_dir():
        git_dir = marker.resolve()
    else:
        raise ValueError("project .git metadata must be a file or directory")

    common_dir = git_dir
    common_pointer = git_dir / "commondir"
    if common_pointer.is_file():
        raw_common_dir = Path(common_pointer.read_text(encoding="utf-8").strip())
        common_dir = (
            raw_common_dir if raw_common_dir.is_absolute() else git_dir / raw_common_dir
        ).resolve()

    seen: set[Path] = set()
    for label, control_root in (("gitdir", git_dir), ("common", common_dir)):
        if not control_root.is_dir():
            raise ValueError("project Git control directory is missing")
        for path in (control_root, *sorted(control_root.rglob("*"))):
            if path in seen:
                continue
            seen.add(path)
            relative_path = path.relative_to(control_root)
            relative = "." if path == control_root else relative_path.as_posix()
            file_stat = path.lstat()
            mode = stat.S_IMODE(file_stat.st_mode)
            metadata = (
                f"mode={mode:o};uid={file_stat.st_uid};gid={file_stat.st_gid};"
                f"nlink={file_stat.st_nlink};ctime={file_stat.st_ctime_ns}"
            )
            if stat.S_ISDIR(file_stat.st_mode):
                value = f"directory:{metadata}"
            elif stat.S_ISLNK(file_stat.st_mode):
                value = f"symlink:{metadata};target={os.readlink(path)}"
            elif stat.S_ISREG(file_stat.st_mode):
                digest = hashlib.sha256(path.read_bytes()).hexdigest()
                value = f"file:{metadata};sha256={digest}"
            else:
                value = f"special:{metadata};type={stat.S_IFMT(file_stat.st_mode):o}"
            entries.append((f"@git/{label}/{relative}", value))
    return tuple(entries)


def _canonical_outcomes(
    payload: dict[str, object],
) -> tuple[CanonicalPytestOutcome, ...]:
    outcomes: list[CanonicalPytestOutcome] = []
    collection = payload.get("collection", [])
    if isinstance(collection, list):
        outcomes.extend(
            CanonicalPytestOutcome(str(nodeid), "collection", "passed")
            for nodeid in collection
        )
    raw_outcomes = payload.get("outcomes", [])
    if isinstance(raw_outcomes, list):
        for item in raw_outcomes:
            if not isinstance(item, dict):
                continue
            outcomes.append(
                CanonicalPytestOutcome(
                    nodeid=str(item.get("nodeid", "")),
                    phase=str(item.get("phase", "")),
                    outcome=str(item.get("outcome", "")),
                )
            )
    return tuple(sorted(outcomes))


def _worker_collections(
    payload: dict[str, object],
) -> tuple[tuple[str, tuple[str, ...]], ...]:
    collections: list[tuple[str, tuple[str, ...]]] = []
    raw_collections = payload.get("worker_collections", [])
    if not isinstance(raw_collections, list):
        return ()
    for item in raw_collections:
        if not isinstance(item, list) or len(item) != 2:
            continue
        worker_id, nodeids = item
        if not isinstance(nodeids, list):
            continue
        collections.append((str(worker_id), tuple(str(nodeid) for nodeid in nodeids)))
    return tuple(sorted(collections))


def _environment_identity(value: object) -> tuple[tuple[str, str], ...]:
    if not isinstance(value, list):
        return ()
    identity: list[tuple[str, str]] = []
    for item in value:
        if not isinstance(item, list) or len(item) != 2:
            return ()
        name, version = item
        if not isinstance(name, str) or not isinstance(version, str):
            return ()
        identity.append((name, version))
    return tuple(identity)


def _worker_environments(
    payload: dict[str, object],
) -> tuple[tuple[str, tuple[tuple[str, str], ...]], ...]:
    environments: list[tuple[str, tuple[tuple[str, str], ...]]] = []
    raw_environments = payload.get("worker_environments", [])
    if not isinstance(raw_environments, list):
        return ()
    for item in raw_environments:
        if not isinstance(item, list) or len(item) != 2:
            continue
        worker_id, raw_identity = item
        environments.append((str(worker_id), _environment_identity(raw_identity)))
    return tuple(sorted(environments))


def _is_excluded(relative_path: Path) -> bool:
    return any(part in _EXCLUDED_SNAPSHOT_NAMES for part in relative_path.parts)


def _is_venv_interpreter_link(relative_path: Path) -> bool:
    parts = relative_path.parts
    if len(parts) != 3 or parts[0] != ".venv":
        return False
    if parts[1] == "bin":
        return parts[2].startswith("python")
    return parts[1] == "Scripts" and parts[2].lower().startswith("python")


def _validate_snapshot_symlinks(project_root: Path) -> None:
    for current_root, directory_names, file_names in os.walk(
        project_root,
        followlinks=False,
    ):
        current = Path(current_root)
        relative_current = current.relative_to(project_root)
        directory_names[:] = [
            name
            for name in directory_names
            if not _is_excluded(relative_current / name)
        ]
        for name in (*directory_names, *file_names):
            path = current / name
            if not path.is_symlink():
                continue
            relative = path.relative_to(project_root)
            target = Path(os.readlink(path))
            if target.is_absolute():
                if (
                    _is_venv_interpreter_link(relative)
                    and target.resolve() == Path(sys.executable).resolve()
                ):
                    continue
                raise ValueError(f"symlink escapes project root: {relative.as_posix()}")
            resolved_target = Path(os.path.abspath(path.parent / target))
            try:
                resolved_target.relative_to(project_root)
            except ValueError as error:
                raise ValueError(
                    f"symlink escapes project root: {relative.as_posix()}"
                ) from error


def _snapshot_ignore(directory: str, names: list[str]) -> set[str]:
    current = Path(directory)
    return {
        name
        for name in names
        if name in _EXCLUDED_SNAPSHOT_NAMES
        or _is_excluded(Path(name))
        or (current / name).name in _EXCLUDED_SNAPSHOT_NAMES
    }


def _copy_snapshot(project_root: Path, destination: Path) -> None:
    git_metadata = project_root / ".git"
    if git_metadata.is_file():
        env = os.environ.copy()
        env["GIT_OPTIONAL_LOCKS"] = "0"
        completed = subprocess.run(
            [
                "git",
                "clone",
                "--quiet",
                "--no-hardlinks",
                "--no-checkout",
                "--",
                str(project_root),
                str(destination),
            ],
            env=env,
            text=True,
            capture_output=True,
            check=False,
        )
        if completed.returncode != 0:
            raise RuntimeError(
                "could not isolate linked-worktree Git metadata: "
                f"{completed.stderr.strip()}"
            )
        _sanitize_git_remotes(destination, env)

        def ignore_linked_git(directory: str, names: list[str]) -> set[str]:
            ignored = _snapshot_ignore(directory, names)
            if Path(directory) == project_root:
                ignored.add(".git")
            return ignored

        shutil.copytree(
            project_root,
            destination,
            dirs_exist_ok=True,
            symlinks=True,
            copy_function=shutil.copy2,
            ignore=ignore_linked_git,
        )
        return
    shutil.copytree(
        project_root,
        destination,
        symlinks=True,
        copy_function=shutil.copy2,
        ignore=_snapshot_ignore,
    )
    env = os.environ.copy()
    env["GIT_OPTIONAL_LOCKS"] = "0"
    _sanitize_git_remotes(destination, env)


def _snapshot_fingerprint(project_root: Path) -> tuple[tuple[str, str], ...]:
    entries: list[tuple[str, str]] = []
    for path in (project_root, *sorted(project_root.rglob("*"))):
        relative = Path(".") if path == project_root else path.relative_to(project_root)
        file_stat = path.lstat()
        mode = stat.S_IMODE(file_stat.st_mode)
        if stat.S_ISLNK(file_stat.st_mode):
            value = f"symlink:mode={mode:o};target={os.readlink(path)}"
        elif stat.S_ISREG(file_stat.st_mode):
            digest = hashlib.sha256(path.read_bytes()).hexdigest()
            value = f"file:mode={mode:o};sha256={digest}"
        elif stat.S_ISDIR(file_stat.st_mode):
            value = f"directory:mode={mode:o}"
        else:
            value = f"special:mode={mode:o};type={stat.S_IFMT(file_stat.st_mode):o}"
        entries.append((relative.as_posix(), value))
    return tuple(entries)


def _sanitize_git_remotes(project_root: Path, env: dict[str, str]) -> None:
    if not (project_root / ".git").exists():
        return
    listed = subprocess.run(
        ["git", "-C", str(project_root), "remote"],
        env=env,
        text=True,
        capture_output=True,
        check=False,
    )
    if listed.returncode != 0:
        raise RuntimeError(
            f"could not list snapshot Git remotes: {listed.stderr.strip()}"
        )
    for remote in listed.stdout.splitlines():
        removed = subprocess.run(
            ["git", "-C", str(project_root), "remote", "remove", remote],
            env=env,
            text=True,
            capture_output=True,
            check=False,
        )
        if removed.returncode != 0:
            raise RuntimeError(
                "could not sanitize snapshot Git remote "
                f"{remote!r}: {removed.stderr.strip()}"
            )


def _canonical_target(project_root: Path, target: str) -> tuple[Path, str]:
    path_part, separator, node_part = target.partition("::")
    raw_path = Path(path_part)
    if ".." in raw_path.parts:
        raise ValueError("pytest targets must not contain parent segments")
    candidate = raw_path if raw_path.is_absolute() else project_root / raw_path
    resolved = candidate.resolve()
    try:
        relative = resolved.relative_to(project_root)
    except ValueError as error:
        raise ValueError("pytest targets must resolve inside project root") from error
    if _is_excluded(relative):
        raise ValueError("pytest target resolves inside an excluded snapshot path")
    suffix = f"::{node_part}" if separator else ""
    return relative, suffix


def _snapshot_targets(
    project_root: Path,
    snapshot_root: Path,
    targets: Sequence[str],
) -> tuple[str, ...]:
    mapped: list[str] = []
    for target in targets:
        relative, suffix = _canonical_target(project_root, target)
        if Path(target.partition("::")[0]).is_absolute():
            mapped.append(f"{snapshot_root / relative}{suffix}")
        else:
            mapped.append(f"{relative.as_posix()}{suffix}")
    return tuple(mapped)


def _run_pytest(
    project_root: Path,
    targets: Sequence[str],
    *,
    workers: int,
    dist_mode: str,
    parallel: bool,
) -> _PytestRunEvidence:
    with tempfile.TemporaryDirectory(prefix="maid-pytest-equivalence-") as temp_dir:
        plugin_root = Path(temp_dir)
        (plugin_root / f"{_PLUGIN_MODULE}.py").write_text(
            _PLUGIN_SOURCE,
            encoding="utf-8",
        )
        output_path = plugin_root / "pytest-evidence.json"
        env = os.environ.copy()
        for name in tuple(env):
            if name.startswith("PYTEST_XDIST_"):
                env.pop(name)
        env["PYTHONDONTWRITEBYTECODE"] = "1"
        env["GIT_OPTIONAL_LOCKS"] = "0"
        env[_PLUGIN_OUTPUT_ENV] = str(output_path)
        existing_pythonpath = env.get("PYTHONPATH")
        env["PYTHONPATH"] = (
            str(plugin_root)
            if not existing_pythonpath
            else os.pathsep.join((str(plugin_root), existing_pythonpath))
        )

        command = [
            sys.executable,
            "-m",
            "pytest",
            "-q",
            "-p",
            "no:cacheprovider",
            "-p",
            _PLUGIN_MODULE,
        ]
        if parallel:
            command.extend(("-n", str(workers), "--dist", dist_mode))
        else:
            command.extend(("-n", "0"))
        command.extend(targets)

        completed = subprocess.run(
            command,
            cwd=project_root,
            env=env,
            text=True,
            capture_output=True,
            check=False,
        )
        if not output_path.is_file():
            return _PytestRunEvidence(
                outcomes=(),
                exit_code=completed.returncode,
                worker_collections=(),
                environment=(),
                worker_environments=(),
                dist_mode="",
                evidence_error="pytest did not emit equivalence evidence",
            )
        try:
            payload = json.loads(output_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as error:
            return _PytestRunEvidence(
                outcomes=(),
                exit_code=completed.returncode,
                worker_collections=(),
                environment=(),
                worker_environments=(),
                dist_mode="",
                evidence_error=f"pytest emitted invalid equivalence evidence: {error}",
            )
        if not isinstance(payload, dict):
            return _PytestRunEvidence(
                outcomes=(),
                exit_code=completed.returncode,
                worker_collections=(),
                environment=(),
                worker_environments=(),
                dist_mode="",
                evidence_error="pytest emitted non-object equivalence evidence",
            )
        return _PytestRunEvidence(
            outcomes=_canonical_outcomes(payload),
            exit_code=completed.returncode,
            worker_collections=_worker_collections(payload),
            environment=_environment_identity(payload.get("environment")),
            worker_environments=_worker_environments(payload),
            dist_mode=str(payload.get("dist_mode", "")),
        )


def run_pytest_equivalence_probe(
    project_root: Path,
    targets: Sequence[str],
    workers: int,
    dist_mode: str = "loadscope",
) -> PytestEquivalenceReport:
    """Run fresh serial/xdist processes and compare their canonical evidence."""

    root = project_root.resolve()
    if workers < 1:
        raise ValueError("workers must be at least 1")
    if not targets:
        raise ValueError("at least one pytest target is required")
    if any(target.startswith(("-", "@")) for target in targets):
        raise ValueError(
            "pytest targets must be path or node selectors, not options or argument files"
        )
    if _would_recurse(root, targets):
        raise RuntimeError(
            "refusing recursive pytest equivalence probe for repository tests"
        )
    for target in targets:
        _canonical_target(root, target)
    _validate_snapshot_symlinks(root)

    initial_fingerprint = _project_fingerprint(root)
    with tempfile.TemporaryDirectory(prefix="maid-pytest-snapshots-") as temp_dir:
        snapshot_parent = Path(temp_dir)
        serial_root = snapshot_parent / "serial"
        parallel_root = snapshot_parent / "parallel"
        _copy_snapshot(root, serial_root)
        _copy_snapshot(serial_root, parallel_root)
        if _snapshot_fingerprint(serial_root) != _snapshot_fingerprint(parallel_root):
            raise RuntimeError("disposable pytest snapshots are not equivalent")
        serial = _run_pytest(
            serial_root,
            _snapshot_targets(root, serial_root, targets),
            workers=workers,
            dist_mode=dist_mode,
            parallel=False,
        )
        parallel = _run_pytest(
            parallel_root,
            _snapshot_targets(root, parallel_root, targets),
            workers=workers,
            dist_mode=dist_mode,
            parallel=True,
        )
    final_fingerprint = _project_fingerprint(root)

    differences: list[str] = []
    if serial.exit_code != 0:
        differences.append(f"serial pytest exited with code {serial.exit_code}")
    if parallel.exit_code != 0:
        differences.append(f"parallel pytest exited with code {parallel.exit_code}")
    if serial.evidence_error:
        differences.append(f"serial {serial.evidence_error}")
    if parallel.evidence_error:
        differences.append(f"parallel {parallel.evidence_error}")
    if initial_fingerprint != final_fingerprint:
        initial_entries = dict(initial_fingerprint)
        final_entries = dict(final_fingerprint)
        changed_paths = sorted(
            path
            for path in initial_entries.keys() | final_entries.keys()
            if initial_entries.get(path) != final_entries.get(path)
        )
        differences.append(
            "pytest changed source project state: " + ", ".join(changed_paths[:10])
        )

    worker_collections = parallel.worker_collections
    if len(worker_collections) != workers:
        differences.append(
            "parallel pytest observed "
            f"{len(worker_collections)} workers instead of requested {workers}"
        )
    if parallel.dist_mode != dist_mode:
        differences.append(
            "parallel pytest observed dist mode "
            f"{parallel.dist_mode!r} instead of requested {dist_mode!r}"
        )
    unique_collections = {nodeids for _, nodeids in worker_collections}
    if len(unique_collections) > 1:
        differences.append("parallel worker collections differ")
    if serial.outcomes != parallel.outcomes:
        serial_only = sorted(set(serial.outcomes) - set(parallel.outcomes))
        parallel_only = sorted(set(parallel.outcomes) - set(serial.outcomes))
        differences.append(
            "phase outcomes differ: "
            f"serial-only={serial_only[:3]!r}; parallel-only={parallel_only[:3]!r}"
        )

    required_environment_names = {"python", "pytest", "pytest-xdist"}
    serial_environment = serial.environment
    parallel_environment = parallel.environment
    worker_environments = parallel.worker_environments
    collection_worker_ids = {worker_id for worker_id, _ in worker_collections}
    environment_worker_ids = {worker_id for worker_id, _ in worker_environments}
    worker_ids_match = collection_worker_ids == environment_worker_ids
    if not worker_ids_match:
        differences.append("worker environment ids differ from collection ids")
    environment_complete = (
        {name for name, _ in serial_environment} == required_environment_names
        and {name for name, _ in parallel_environment} == required_environment_names
        and len(worker_environments) == workers
        and worker_ids_match
        and all(
            {name for name, _ in identity} == required_environment_names
            for _, identity in worker_environments
        )
    )
    observed_environments = {
        serial_environment,
        parallel_environment,
        *(identity for _, identity in worker_environments),
    }
    if not environment_complete or len(observed_environments) != 1:
        differences.append("execution environments differ")

    return PytestEquivalenceReport(
        serial_outcomes=serial.outcomes,
        parallel_outcomes=parallel.outcomes,
        serial_exit_code=serial.exit_code,
        parallel_exit_code=parallel.exit_code,
        parallel_worker_collections=worker_collections,
        serial_environment=serial_environment,
        parallel_environment=parallel_environment,
        differences=tuple(differences),
        workers=len(worker_collections),
        dist_mode=parallel.dist_mode,
        success=not differences,
    )


def _would_recurse(project_root: Path, targets: Sequence[str]) -> bool:
    inside_pytest = bool(os.environ.get("PYTEST_CURRENT_TEST")) or (
        "pytest" in sys.modules and "_pytest.config" in sys.modules
    )
    if not inside_pytest:
        return False
    probe_test = (
        Path(__file__).resolve().parents[1]
        / "tests"
        / "performance"
        / "test_pytest_parallel_equivalence_probe.py"
    )
    for target in targets:
        path_part = target.split("::", 1)[0]
        candidate = Path(path_part)
        if not candidate.is_absolute():
            candidate = project_root / candidate
        candidate = candidate.resolve()
        if candidate == probe_test:
            return True
        if candidate.is_dir() and probe_test.is_relative_to(candidate):
            return True
    return False


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Compare fresh serial and xdist pytest outcomes.",
    )
    parser.add_argument("--project-root", type=Path, default=Path.cwd())
    parser.add_argument("--workers", type=int, required=True)
    parser.add_argument("--dist", dest="dist_mode", default="loadscope")
    parser.add_argument("targets", nargs="+")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    """Run the probe and print deterministic pass/failure diagnostics."""

    args = _build_parser().parse_args(argv)
    project_root = args.project_root.resolve()
    try:
        report = run_pytest_equivalence_probe(
            project_root,
            args.targets,
            workers=args.workers,
            dist_mode=args.dist_mode,
        )
    except RuntimeError as error:
        print(str(error), file=sys.stderr)
        return 2
    if report.success:
        print(
            "PASS serial/parallel pytest equivalence: "
            f"workers={report.workers} dist={report.dist_mode}"
        )
        return 0

    print(
        "FAIL serial/parallel pytest equivalence: "
        f"workers={report.workers} dist={report.dist_mode}",
        file=sys.stderr,
    )
    for difference in report.differences:
        print(f"- {difference}", file=sys.stderr)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
