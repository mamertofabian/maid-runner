"""Bounded isolated execution for exact artifact-coverage fallbacks."""

from __future__ import annotations

import ast
import hashlib
import inspect
import os
import threading
import ctypes
import struct
from collections.abc import Mapping, Sequence
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, replace
from pathlib import Path
from contextlib import contextmanager

from maid_runner.core._knockout_snapshot import ProjectSnapshotBackend
from maid_runner.core._knockout_worker import resolve_knockout_process_cost
from maid_runner.core._pytest_worker_execution import (
    PytestRunnerCapabilities,
    probe_pytest_runner_capabilities,
)
from maid_runner.core._runtime_command_executor import (
    RuntimeCommandExecutor,
    RuntimeCommandRecord,
)
from maid_runner.core.knockout import _harness_error
from maid_runner.core.config import load_config
from maid_runner.core.result import ValidationError
from maid_runner.core.runtime_evidence import RuntimeCommandIdentity


_NON_MATERIAL_PARTS = frozenset(
    {
        ".mypy_cache",
        ".maid-pycache",
        ".pytest_cache",
        ".ruff_cache",
        "__pycache__",
    }
)
_DEPENDENCY_ENVIRONMENT_PARTS = frozenset({".tox", ".venv", "node_modules"})


@dataclass(frozen=True)
class ArtifactCoverageFallbackWorkerResult:
    """One exact fallback command's isolated result and diagnostics."""

    identity: RuntimeCommandIdentity
    command_run: RuntimeCommandRecord | None
    material_project_writes: tuple[str, ...]
    process_cost: int
    errors: tuple[ValidationError, ...]


@dataclass(frozen=True)
class ArtifactCoverageFallbackRun:
    """Ordered isolated results and identities requiring serial replay."""

    results: tuple[ArtifactCoverageFallbackWorkerResult, ...]
    serial_fallback_identities: tuple[RuntimeCommandIdentity, ...]


def run_isolated_artifact_coverage_fallbacks(
    identities: Sequence[RuntimeCommandIdentity],
    project_root: Path,
    target_files: Mapping[RuntimeCommandIdentity, set[str]],
    snapshot_backend: ProjectSnapshotBackend,
    executor: RuntimeCommandExecutor,
    jobs: int,
    max_processes: int,
) -> ArtifactCoverageFallbackRun:
    """Run exact commands in snapshots within one weighted process budget."""
    _require_positive("jobs", jobs)
    _require_positive("max_processes", max_processes)
    ordered = tuple(identities)
    root = Path(project_root).resolve()
    prepared: list[
        tuple[
            int,
            tuple[RuntimeCommandIdentity, ...],
            tuple[str, ...],
            set[str],
            int,
        ]
    ] = []
    results: list[ArtifactCoverageFallbackWorkerResult | None] = [None] * len(ordered)
    unsafe = False
    groups = _identity_groups(ordered, target_files, deduplicate=jobs > 1)
    capability_cache: dict[str, PytestRunnerCapabilities] = {}
    nested_work_cache: dict[Path, int | None] = {}
    for group_index, (group_identities, command, group_targets) in enumerate(groups):
        identity = group_identities[0]
        try:
            prepared_command, cost = _prepared_command(
                identity.command,
                root,
                max_processes,
                optimize=jobs > 1,
                capability_cache=capability_cache,
                nested_work_cache=nested_work_cache,
            )
            if cost > max_processes:
                raise ValueError(
                    f"artifact-coverage process cost {cost} exceeds budget "
                    f"{max_processes}"
                )
            prepared.append(
                (
                    group_index,
                    group_identities,
                    prepared_command,
                    group_targets,
                    cost,
                )
            )
        except Exception as exc:
            for grouped_identity in group_identities:
                results[ordered.index(grouped_identity)] = _failed(
                    grouped_identity, 1, str(exc)
                )
            unsafe = True

    file_work_cache: dict[Path, int] = {}
    work = sorted(
        prepared,
        key=lambda item: _estimated_command_work(
            item[2], root, file_work_cache, nested_work_cache
        )
        / item[-1],
        reverse=True,
    )
    work_lock = threading.Lock()
    required = tuple(
        sorted(
            {
                _relative_to_root(root, path)
                for _index, _identities, _command, targets, _cost in prepared
                for path in targets
            }
            | set(_existing_bootstrap_payloads(root))
        )
    )
    lane_count = min(jobs, len(prepared))
    process_budget = _ProcessBudget(max_processes)
    with ThreadPoolExecutor(max_workers=lane_count or 1) as pool:
        futures = tuple(
            pool.submit(
                _execute_lane,
                work,
                work_lock,
                required,
                root,
                snapshot_backend,
                executor,
                lane_index,
                process_budget,
            )
            for lane_index in range(lane_count)
        )
        lane_results = tuple(future.result() for future in futures)

    for lane in lane_results:
        for _index, group_identities, cost, result in lane:
            identity = group_identities[0]
            if result.identity != identity:
                result = _failed(identity, cost, "fallback worker identity mismatch")
            else:
                result = replace(result, process_cost=cost)
            for grouped_identity in group_identities:
                result_index = ordered.index(grouped_identity)
                results[result_index] = replace(result, identity=grouped_identity)
            unsafe = unsafe or bool(
                result.errors
                or result.material_project_writes
                or (
                    result.command_run is not None
                    and result.command_run.returncode != 0
                )
            )

    for index, result in enumerate(results):
        if result is None:
            results[index] = _failed(
                ordered[index], 1, "fallback worker produced no result"
            )
            unsafe = True
    final = tuple(result for result in results if result is not None)
    return ArtifactCoverageFallbackRun(final, ordered if unsafe else ())


def _execute_lane(
    work,
    work_lock,
    required,
    root: Path,
    snapshot_backend: ProjectSnapshotBackend,
    executor: RuntimeCommandExecutor,
    lane_index: int,
    process_budget,
):
    try:
        with snapshot_backend.create(
            root, required, f"artifact-coverage-lane-{lane_index:03d}"
        ) as snapshot:
            snapshot_root = Path(snapshot.root).resolve()
            baseline = _material_state(snapshot_root)
            with _MaterialChangeJournal(snapshot_root) as journal:
                completed = []
                while True:
                    with work_lock:
                        item = work.pop(0) if work else None
                    if item is None:
                        return tuple(completed)
                    index, identities, command, targets, cost = item
                    completed.append(
                        (
                            index,
                            identities,
                            cost,
                            _execute_with_budget(
                                process_budget,
                                cost,
                                identities[0],
                                command,
                                root,
                                targets,
                                snapshot_root,
                                getattr(snapshot, "environment_overrides", {}),
                                getattr(snapshot, "environment_removals", ()),
                                executor,
                                baseline,
                                journal,
                            ),
                        )
                    )
    except Exception as exc:
        failed = []
        while True:
            with work_lock:
                item = work.pop(0) if work else None
            if item is None:
                return tuple(failed)
            index, identities, _command, _targets, cost = item
            failed.append(
                (index, identities, cost, _failed(identities[0], cost, str(exc)))
            )


def _execute_in_snapshot(
    identity: RuntimeCommandIdentity,
    command: tuple[str, ...],
    root: Path,
    source_targets: set[str],
    snapshot_root: Path,
    environment_overrides: Mapping[str, str],
    environment_removals: Sequence[str],
    executor: RuntimeCommandExecutor,
    process_cost: int,
    baseline: Mapping[str, str],
    journal,
) -> ArtifactCoverageFallbackWorkerResult:
    mapped_targets = {
        str((snapshot_root / _relative_to_root(root, path)).resolve())
        for path in source_targets
    }
    journal.clear()
    command_run = _execute_with_snapshot_environment(
        executor,
        command,
        mapped_targets,
        snapshot_root,
        environment_overrides,
        environment_removals,
    )
    writes = _material_writes(snapshot_root, baseline, journal.changed_paths())
    normalized_data = {}
    for path, data in command_run.execution_data.items():
        if _owned_coverage_helper_path(path):
            continue
        relative = _relative_to_root(snapshot_root, path)
        snapshot_path = str((snapshot_root / relative).resolve())
        if snapshot_path in mapped_targets:
            normalized_data[str((root / relative).resolve())] = data
    normalized = replace(command_run, execution_data=normalized_data)
    return ArtifactCoverageFallbackWorkerResult(
        identity, normalized, writes, process_cost, ()
    )


def _execute_with_budget(
    budget,
    cost: int,
    identity: RuntimeCommandIdentity,
    command: tuple[str, ...],
    root: Path,
    targets: set[str],
    snapshot_root: Path,
    environment_overrides: Mapping[str, str],
    environment_removals: Sequence[str],
    executor: RuntimeCommandExecutor,
    baseline: Mapping[str, str],
    journal,
) -> ArtifactCoverageFallbackWorkerResult:
    with budget.reserve(cost):
        return _execute_in_snapshot(
            identity,
            command,
            root,
            targets,
            snapshot_root,
            environment_overrides,
            environment_removals,
            executor,
            cost,
            baseline,
            journal,
        )


def _execute_with_snapshot_environment(
    executor: RuntimeCommandExecutor,
    command: tuple[str, ...],
    target_files: set[str],
    root: Path,
    overrides: Mapping[str, str],
    removals: Sequence[str],
) -> RuntimeCommandRecord:
    timeout = load_config(root).artifact_coverage.timeout_seconds
    parameters = inspect.signature(executor.execute).parameters.values()
    supports_environment = (
        any(
            parameter.kind in {parameter.VAR_POSITIONAL, parameter.VAR_KEYWORD}
            for parameter in parameters
        )
        or len(tuple(parameters)) >= 6
    )
    if supports_environment:
        return executor.execute(
            command, target_files, root, timeout, overrides, removals
        )
    return executor.execute(command, target_files, root, timeout)


def _material_state(root: Path) -> dict[str, str]:
    discovered: list[Path] = []
    for directory, names, files in os.walk(root, followlinks=False):
        names[:] = [
            name
            for name in names
            if name not in _NON_MATERIAL_PARTS
            and name not in _DEPENDENCY_ENVIRONMENT_PARTS
        ]
        discovered.extend(Path(directory) / name for name in files)
    paths = tuple(discovered)
    state: dict[str, str] = {}
    for path in paths:
        candidate = path if path.is_absolute() else root / path
        relative = candidate.relative_to(root).as_posix()
        if _is_non_material(relative):
            continue
        try:
            state[relative] = hashlib.sha256(candidate.read_bytes()).hexdigest()
        except (FileNotFoundError, IsADirectoryError):
            state[relative] = "<missing>"
    return state


def _material_writes(
    root: Path, baseline: Mapping[str, str], changed_paths: set[str]
) -> tuple[str, ...]:
    candidates = set(changed_paths)
    for changed in tuple(changed_paths):
        prefix = changed.rstrip("/") + "/"
        candidates.update(path for path in baseline if path.startswith(prefix))
        directory = root / changed
        if directory.is_dir():
            candidates.update(
                path.relative_to(root).as_posix()
                for path in directory.rglob("*")
                if path.is_file()
            )
    writes = []
    for relative in candidates:
        if _is_non_material(relative):
            continue
        if set(Path(relative).parts) & _DEPENDENCY_ENVIRONMENT_PARTS:
            writes.append(relative)
            continue
        path = root / relative
        current = (
            hashlib.sha256(path.read_bytes()).hexdigest()
            if path.is_file()
            else "<missing>"
        )
        if baseline.get(relative, "<missing>") != current:
            writes.append(relative)
    return tuple(sorted(writes))


class _MaterialChangeJournal:
    _EVENT_MASK = 0x00000FCE
    _IS_DIRECTORY = 0x40000000
    _QUEUE_OVERFLOW = 0x00004000
    _EVENT = struct.Struct("iIII")

    def __init__(self, root: Path):
        self.root = Path(root).resolve()
        libc = ctypes.CDLL(None, use_errno=True)
        self._add_watch_call = libc.inotify_add_watch
        self._add_watch_call.argtypes = (ctypes.c_int, ctypes.c_char_p, ctypes.c_uint32)
        self._add_watch_call.restype = ctypes.c_int
        self.fd = libc.inotify_init1(os.O_NONBLOCK | os.O_CLOEXEC)
        if self.fd < 0:
            raise OSError(ctypes.get_errno(), "inotify_init1 failed")
        self.directories: dict[int, Path] = {}
        try:
            self._watch_tree(self.root)
        except BaseException:
            os.close(self.fd)
            raise

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, traceback):
        os.close(self.fd)

    def _watch_tree(self, root: Path) -> None:
        for directory, names, _files in os.walk(root, followlinks=False):
            names[:] = [name for name in names if name not in _NON_MATERIAL_PARTS]
            path = Path(directory)
            watch = self._add_watch_call(self.fd, os.fsencode(path), self._EVENT_MASK)
            if watch < 0:
                raise OSError(ctypes.get_errno(), f"inotify watch failed: {path}")
            self.directories[watch] = path

    def clear(self) -> None:
        self.changed_paths()

    def changed_paths(self) -> set[str]:
        changed: set[str] = set()
        while True:
            try:
                payload = os.read(self.fd, 1024 * 1024)
            except BlockingIOError:
                break
            offset = 0
            while offset < len(payload):
                watch, mask, _cookie, length = self._EVENT.unpack_from(payload, offset)
                offset += self._EVENT.size
                raw_name = payload[offset : offset + length].split(b"\0", 1)[0]
                offset += length
                if mask & self._QUEUE_OVERFLOW:
                    raise RuntimeError("material change journal overflowed")
                directory = self.directories.get(watch)
                if directory is None:
                    continue
                path = directory / os.fsdecode(raw_name) if raw_name else directory
                try:
                    relative = path.relative_to(self.root).as_posix()
                except ValueError:
                    continue
                if relative and not _is_non_material(relative):
                    changed.add(relative)
                if (
                    mask & self._IS_DIRECTORY
                    and path.is_dir()
                    and not _is_non_material(relative)
                ):
                    self._watch_tree(path)
                    changed.update(
                        child.relative_to(self.root).as_posix()
                        for child in path.rglob("*")
                        if child.is_file()
                    )
        return changed


def _owned_coverage_helper_path(raw_path: str) -> bool:
    path = Path(raw_path)
    return path.name in {
        "artifact_coverage_runner.py",
        "_maid_artifact_coverage_worker.py",
    } and any(part.startswith("maid-artifact-coverage-command-") for part in path.parts)


def _identity_groups(
    identities: tuple[RuntimeCommandIdentity, ...],
    target_files: Mapping[RuntimeCommandIdentity, set[str]],
    *,
    deduplicate: bool,
) -> tuple[tuple[tuple[RuntimeCommandIdentity, ...], tuple[str, ...], set[str]], ...]:
    from maid_runner.core.artifact_coverage import _pytest_args

    groups: list[tuple[list[RuntimeCommandIdentity], tuple[str, ...], set[str]]] = []
    by_command: dict[tuple[str, ...], int] = {}
    for identity in identities:
        command = _pytest_args(identity.command)
        if command is None:
            raise ValueError("fallback command is not pytest")
        group_index = by_command.get(command) if deduplicate else None
        if group_index is None:
            group_index = len(groups)
            groups.append(([identity], command, set(target_files.get(identity, set()))))
            if deduplicate:
                by_command[command] = group_index
        else:
            groups[group_index][0].append(identity)
            groups[group_index][2].update(target_files.get(identity, set()))
    return tuple(
        (tuple(group_identities), command, targets)
        for group_identities, command, targets in groups
    )


def _estimated_command_work(
    command: tuple[str, ...],
    root: Path,
    file_work_cache: dict[Path, int] | None = None,
    nested_work_cache: dict[Path, int | None] | None = None,
) -> float:
    files = _selected_test_files(command, root)
    cache = file_work_cache if file_work_cache is not None else {}
    total = 0
    for path in files:
        work = cache.get(path)
        if path not in cache:
            nested_cache = nested_work_cache if nested_work_cache is not None else {}
            if path not in nested_cache:
                nested_cache[path] = _nested_process_work(path)
            nested_work = nested_cache[path]
            work = max(1, path.stat().st_size) + (nested_work or 0)
            cache[path] = work
        total += work
    return float(total or 1)


def _selected_test_files(command: tuple[str, ...], root: Path) -> set[Path]:
    files: set[Path] = set()
    for value in command:
        if value.startswith("-") or value.isdigit() or value == "loadscope":
            continue
        candidate = root / value.partition("::")[0]
        if candidate.is_dir():
            files.update(candidate.rglob("test_*.py"))
            files.update(candidate.rglob("*_test.py"))
        elif candidate.is_file():
            files.add(candidate)
    return files


def _nested_process_work(path: Path) -> int | None:
    try:
        tree = ast.parse(path.read_text(encoding="utf-8"))
    except (OSError, SyntaxError, UnicodeError):
        return None
    nested_work = 0
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        function = node.func
        direct_name = function.id if isinstance(function, ast.Name) else None
        is_subprocess = (
            isinstance(function, ast.Attribute)
            and isinstance(function.value, ast.Name)
            and function.value.id == "subprocess"
            and function.attr in {"call", "check_call", "check_output", "Popen", "run"}
        )
        if direct_name in {
            "collect_runtime_evidence",
            "run_knockout_batch",
        }:
            nested_work += 256_000
        elif direct_name in {"_git", "run_validate_commands_for_result"}:
            nested_work += 128_000
        elif is_subprocess:
            nested_work += 64_000
    return min(nested_work, 1_024_000)


def _requires_exclusive_process_budget(
    command: tuple[str, ...],
    root: Path,
    file_work_cache: dict[Path, int | None],
) -> bool:
    for path in _selected_test_files(command, root):
        if path not in file_work_cache:
            file_work_cache[path] = _nested_process_work(path)
        work = file_work_cache[path]
        if work is None or work > 0:
            return True
    return False


def _applicable_conftests(path: Path, root: Path) -> tuple[Path, ...]:
    root = Path(root).resolve()
    current = Path(path).resolve().parent
    boundaries = []
    while True:
        try:
            current.relative_to(root)
        except ValueError:
            return (root / "<unresolved-conftest-boundary>",)
        conftest = current / "conftest.py"
        if conftest.exists():
            boundaries.append(conftest)
        if current == root:
            return tuple(boundaries)
        current = current.parent


def _conftest_process_coordination_uncertain(
    command: tuple[str, ...],
    root: Path,
    file_work_cache: dict[Path, int | None],
) -> bool:
    conftests = {
        conftest
        for path in _selected_test_files(command, root)
        for conftest in _applicable_conftests(path, root)
    }
    for conftest in conftests:
        if conftest not in file_work_cache:
            file_work_cache[conftest] = _nested_process_work(conftest)
        work = file_work_cache[conftest]
        if work is None or work > 0:
            return True
    return False


def _parallel_child_process_permits_available() -> bool:
    try:
        import fcntl
    except ImportError:
        return False
    return all(
        hasattr(fcntl, name) for name in ("flock", "LOCK_EX", "LOCK_NB", "LOCK_UN")
    )


class _ProcessBudget:
    def __init__(self, maximum: int):
        self.maximum = maximum
        self.available = maximum
        self.condition = threading.Condition()

    @contextmanager
    def reserve(self, cost: int):
        with self.condition:
            self.condition.wait_for(lambda: self.available >= cost)
            self.available -= cost
        try:
            yield
        finally:
            with self.condition:
                self.available += cost
                self.condition.notify_all()


def _existing_bootstrap_payloads(root: Path) -> tuple[str, ...]:
    payload_root = root / "maid_runner" / "claude"
    if not (payload_root / "manifest.json").is_file():
        return ()
    return tuple(
        path.relative_to(root).as_posix()
        for path in sorted(payload_root.rglob("*"))
        if path.is_file() and not _is_non_material(path.relative_to(root).as_posix())
    )


def _prepared_command(
    original_command: tuple[str, ...],
    root: Path,
    max_processes: int,
    *,
    optimize: bool,
    capability_cache: dict[str, PytestRunnerCapabilities],
    nested_work_cache: dict[Path, int | None],
) -> tuple[tuple[str, ...], int]:
    from maid_runner.core.artifact_coverage import _pytest_args

    pytest_args = _pytest_args(original_command)
    if pytest_args is None:
        raise ValueError("fallback command is not pytest")
    existing_cost = resolve_knockout_process_cost(original_command, root)
    if not optimize:
        return pytest_args, existing_cost
    selects_directory = _selects_directory(pytest_args, root)
    if not selects_directory:
        return pytest_args, existing_cost
    exclusive = _requires_exclusive_process_budget(pytest_args, root, nested_work_cache)
    conftest_uncertain = _conftest_process_coordination_uncertain(
        pytest_args, root, nested_work_cache
    )
    exclusive = exclusive or conftest_uncertain
    reservation = max_processes if exclusive else existing_cost
    if existing_cost > 1:
        return pytest_args, reservation
    if conftest_uncertain or (
        exclusive and not _parallel_child_process_permits_available()
    ):
        return pytest_args, reservation
    config = load_config(root).test_execution
    configured = config.pytest_workers
    workers = (
        max(config.accepted_pytest_worker_counts)
        if configured == "auto"
        else configured
    )
    if workers == 1:
        return pytest_args, reservation
    if workers not in config.accepted_pytest_worker_counts:
        raise ValueError(f"pytest worker count {workers} is not repository accepted")
    if config.pytest_dist_mode != "loadscope":
        raise ValueError("artifact coverage workers require --dist loadscope")
    if workers > max_processes:
        raise ValueError(
            f"artifact-coverage process cost {workers} exceeds budget "
            f"{max_processes}"
        )
    capabilities = capability_cache.get("pytest")
    if capabilities is None:
        capabilities = probe_pytest_runner_capabilities(("pytest",), root)
        capability_cache["pytest"] = capabilities
    if not capabilities.xdist_available:
        raise ValueError(capabilities.error or "pytest-xdist is unavailable")
    return (
        (
            *pytest_args,
            "-n",
            str(workers),
            "--dist",
            "loadscope",
        ),
        max_processes if exclusive else workers,
    )


def _selects_directory(pytest_args: tuple[str, ...], root: Path) -> bool:
    for value in pytest_args:
        if value.startswith("-"):
            continue
        path_value = value.partition("::")[0]
        if (root / path_value).is_dir():
            return True
    return False


def _is_non_material(path: str) -> bool:
    return bool(set(Path(path).parts) & _NON_MATERIAL_PARTS)


def _relative_to_root(root: Path, raw_path: str) -> str:
    path = Path(raw_path)
    candidate = path if path.is_absolute() else root / path
    try:
        return candidate.resolve(strict=False).relative_to(root).as_posix()
    except (OSError, RuntimeError, ValueError) as exc:
        raise RuntimeError(f"fallback path escapes snapshot root: {raw_path}") from exc


def _failed(
    identity: RuntimeCommandIdentity, process_cost: int, message: str
) -> ArtifactCoverageFallbackWorkerResult:
    return ArtifactCoverageFallbackWorkerResult(
        identity, None, (), process_cost, (_harness_error("", message),)
    )


def _require_positive(name: str, value: int) -> None:
    if isinstance(value, bool) or not isinstance(value, int) or value < 1:
        raise ValueError(f"artifact coverage {name} must be a positive integer")
