"""Resolved-environment pytest worker execution and timing lifecycle."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
import hashlib
import json
import math
import os
from pathlib import Path
import re
import subprocess
import tempfile
from typing import Any

from maid_runner.core._pytest_config_addopts import pytest_config_addopts_args
from maid_runner.core._pytest_parallelism import (
    PytestWorkerDecision,
    choose_pytest_worker_policy,
    load_pytest_timing_history,
    record_pytest_timing_history,
)
from maid_runner.core._test_runner_invocation import _test_runner_invocation
from maid_runner.core.config import load_config
from maid_runner.core.result import TestRunResult


@dataclass(frozen=True)
class PytestRunnerCapabilities:
    """Resolved consumer-runner xdist capability and probe diagnostic."""

    xdist_available: bool
    xdist_version: str | None
    error: str | None


@dataclass(frozen=True)
class TestSchedulingNotice:
    """Stable automation-visible scheduling decision or fallback notice."""

    command_group: tuple[str, ...]
    mode: str
    workers: int | str
    reason: str


@dataclass(frozen=True)
class PytestCollectionResult:
    """Exact node IDs or a typed collection error."""

    nodeids: tuple[str, ...]
    error: str | None


@dataclass(frozen=True)
class PreparedPytestCommand:
    """Prepared command plus timing evidence lifecycle."""

    command: tuple[str, ...]
    environment_overrides: Mapping[str, str]
    notice: TestSchedulingNotice | None
    selected_nodeids: tuple[str, ...]
    behavior_group_digest: str | None
    input_digest: str | None
    _temporary_directory: tempfile.TemporaryDirectory[str] | None = field(
        default=None, repr=False, compare=False
    )


def probe_pytest_runner_capabilities(
    resolved_command: tuple[str, ...],
    cwd: Path,
) -> PytestRunnerCapabilities:
    """Probe xdist through the exact resolved pytest command prefix."""
    return _probe_pytest_runner_capabilities(
        resolved_command,
        cwd,
        _clean_child_environment(),
    )


def _probe_pytest_runner_capabilities(
    resolved_command: tuple[str, ...],
    cwd: Path,
    environment: Mapping[str, str],
) -> PytestRunnerCapabilities:
    prefix = _pytest_command_prefix(resolved_command)
    if prefix is None:
        return PytestRunnerCapabilities(False, None, "command is not pytest")
    probe = (*prefix, "--version", "--version")
    try:
        completed = subprocess.run(
            probe,
            cwd=str(cwd),
            capture_output=True,
            text=True,
            timeout=30,
            env=dict(environment),
            check=False,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        return PytestRunnerCapabilities(False, None, f"pytest probe failed: {exc}")
    output = "\n".join((completed.stdout, completed.stderr))
    match = re.search(r"(?:pytest-)?xdist[- ]([0-9][^\s,]*)", output, re.I)
    if completed.returncode != 0:
        detail = completed.stderr.strip() or completed.stdout.strip()
        return PytestRunnerCapabilities(
            False,
            None,
            f"pytest capability probe failed: {detail or completed.returncode}",
        )
    if match is None:
        return PytestRunnerCapabilities(False, None, "pytest-xdist is unavailable")
    return PytestRunnerCapabilities(True, match.group(1), None)


def build_pytest_timing_identity(
    command: tuple[str, ...],
    project_root: Path,
) -> tuple[str, str]:
    """Build deterministic command behavior and relevant content digests."""
    root = Path(project_root).resolve()
    behavior = hashlib.sha256()
    behavior.update(json.dumps(list(command), separators=(",", ":")).encode())
    for name in (
        ".maidrc.yaml",
        "pyproject.toml",
        "pytest.ini",
        ".pytest.ini",
        "tox.ini",
        "setup.cfg",
    ):
        path = root / name
        if path.is_file():
            _update_file_digest(behavior, path, root)

    inputs = hashlib.sha256()
    for path in sorted(root.rglob("*")):
        if not path.is_file():
            continue
        relative = path.relative_to(root)
        if _excluded_identity_path(relative):
            continue
        _update_file_digest(inputs, path, root)
    return behavior.hexdigest(), inputs.hexdigest()


def collect_pytest_nodeids(
    resolved_command: tuple[str, ...],
    cwd: Path,
) -> PytestCollectionResult:
    """Collect exact node IDs through a standalone plugin in the consumer env."""
    return _collect_pytest_nodeids(
        resolved_command,
        cwd,
        _clean_child_environment(),
    )


def _collect_pytest_nodeids(
    resolved_command: tuple[str, ...],
    cwd: Path,
    environment: Mapping[str, str],
) -> PytestCollectionResult:
    if not _looks_like_resolved_pytest(resolved_command):
        return PytestCollectionResult((), "command is not pytest")
    with tempfile.TemporaryDirectory(prefix="maid-pytest-collect-") as directory_name:
        directory = Path(directory_name)
        env = dict(environment)
        overrides, plugin_name = _timing_plugin_environment(
            directory,
            env.get("PYTHONPATH"),
        )
        output = directory / "collection.json"
        env.update(overrides)
        env.update(
            {
                "PYTEST_PLUGINS": _merged_pytest_plugins(
                    env.get("PYTEST_PLUGINS"), plugin_name
                ),
                "MAID_COLLECTION_OUTPUT": str(output),
            }
        )
        command = (*resolved_command, "--collect-only", "-q")
        try:
            completed = subprocess.run(
                command,
                cwd=str(cwd),
                capture_output=True,
                text=True,
                timeout=120,
                env=env,
                check=False,
            )
        except (OSError, subprocess.SubprocessError) as exc:
            return PytestCollectionResult((), f"pytest collection failed: {exc}")
        if completed.returncode not in {0, 5}:
            detail = completed.stderr.strip() or completed.stdout.strip()
            return PytestCollectionResult(
                (), f"pytest collection failed: {detail or completed.returncode}"
            )
        try:
            payload = json.loads(output.read_text(encoding="utf-8"))
        except (OSError, UnicodeError, json.JSONDecodeError) as exc:
            return PytestCollectionResult(
                (), f"pytest collection evidence malformed: {exc}"
            )
        if not isinstance(payload, dict) or set(payload) != {"nodeids"}:
            return PytestCollectionResult((), "pytest collection evidence malformed")
        nodeids = payload["nodeids"]
        if not isinstance(nodeids, list) or not all(
            isinstance(nodeid, str) and nodeid for nodeid in nodeids
        ):
            return PytestCollectionResult((), "pytest collection evidence malformed")
        if len(set(nodeids)) != len(nodeids):
            return PytestCollectionResult(
                (), "pytest collection evidence has duplicate node IDs"
            )
        return PytestCollectionResult(tuple(nodeids), None)


def timing_plugin_environment(directory: Path) -> tuple[dict[str, str], str]:
    """Materialize a standalone plugin in a child-only import path."""
    return _timing_plugin_environment(directory, os.environ.get("PYTHONPATH"))


def _timing_plugin_environment(
    directory: Path,
    existing_pythonpath: str | None,
) -> tuple[dict[str, str], str]:
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=True)
    plugin_name = "_maid_pytest_timing_plugin"
    source = (
        Path(__file__).with_name("_pytest_timing_plugin.py").read_text(encoding="utf-8")
    )
    (directory / f"{plugin_name}.py").write_text(source, encoding="utf-8")
    pythonpath = str(directory)
    if existing_pythonpath:
        pythonpath = pythonpath + os.pathsep + existing_pythonpath
    return {"PYTHONPATH": pythonpath}, plugin_name


def apply_pytest_worker_decision(
    command: tuple[str, ...],
    decision: PytestWorkerDecision,
    capabilities: PytestRunnerCapabilities,
    *,
    dist_mode: str,
    accepted_worker_counts: tuple[int, ...],
    max_processes: int,
    command_jobs: int,
    project_root: Path,
    explicit: bool,
) -> tuple[tuple[str, ...], TestSchedulingNotice]:
    """Apply only bounded, proven workers without overriding existing flags."""
    configured = _configured_workers(command, project_root)
    if configured is not None:
        workers, source = configured
        numeric = _bounded_worker_count(workers)
        _require_process_budget(numeric, command_jobs, max_processes)
        if not capabilities.xdist_available:
            raise ValueError(capabilities.error or "pytest-xdist is unavailable")
        return command, TestSchedulingNotice(
            command,
            "preconfigured",
            numeric,
            f"preconfigured:{source}",
        )

    if not decision.use_workers:
        return command, TestSchedulingNotice(command, "serial", 1, decision.reason)

    workers = _bounded_worker_count(decision.workers)
    problem: str | None = None
    if not capabilities.xdist_available:
        problem = capabilities.error or "pytest-xdist is unavailable"
    elif dist_mode != "loadscope":
        problem = "automatic pytest workers require proven --dist loadscope"
    elif workers not in accepted_worker_counts:
        problem = f"pytest worker count {workers} is not repository accepted"
    else:
        try:
            _require_process_budget(workers, command_jobs, max_processes)
        except ValueError as exc:
            problem = str(exc)

    if problem is not None:
        if explicit:
            raise ValueError(problem)
        return command, TestSchedulingNotice(command, "serial-fallback", 1, problem)

    scheduled = (*command, "-n", str(workers), "--dist", "loadscope")
    return scheduled, TestSchedulingNotice(command, "workers", workers, decision.reason)


def prepare_pytest_command(
    resolved_command: tuple[str, ...],
    project_root: Path,
    pytest_workers: int | str | None,
    command_jobs: int,
) -> PreparedPytestCommand:
    """Compose exact collection, policy, capability, scheduling, and timing."""
    return _prepare_pytest_command(
        resolved_command,
        project_root,
        pytest_workers,
        command_jobs,
    )


def _prepare_pytest_command(
    resolved_command: tuple[str, ...],
    project_root: Path,
    pytest_workers: int | str | None,
    command_jobs: int,
    *,
    environment_overrides: Mapping[str, str] | None = None,
    environment_removals: Sequence[str] = (),
) -> PreparedPytestCommand:
    root = Path(project_root)
    if not _looks_like_resolved_pytest(resolved_command):
        return PreparedPytestCommand(resolved_command, {}, None, (), None, None)

    config = load_config(root).test_execution
    if (
        pytest_workers is None
        and config.pytest_workers == 1
        and not config.accepted_pytest_worker_counts
    ):
        return PreparedPytestCommand(resolved_command, {}, None, (), None, None)
    explicit = pytest_workers is not None
    configured_workers: int | str = (
        config.pytest_workers if pytest_workers is None else pytest_workers
    )
    if configured_workers == "auto":
        if not config.accepted_pytest_worker_counts:
            raise ValueError("pytest_workers auto requires an accepted worker count")
        configured_workers = max(config.accepted_pytest_worker_counts)

    behavior_digest, input_digest = build_pytest_timing_identity(resolved_command, root)
    preparation_environment = (
        _explicit_child_environment(environment_overrides, environment_removals)
        if environment_overrides is not None or environment_removals
        else None
    )
    collection = (
        _collect_pytest_nodeids(
            resolved_command,
            root,
            preparation_environment,
        )
        if preparation_environment is not None
        else collect_pytest_nodeids(resolved_command, root)
    )
    if collection.error is not None:
        if explicit and configured_workers != 1:
            raise ValueError(collection.error)
        return _instrumented_prepared_command(
            resolved_command,
            TestSchedulingNotice(
                resolved_command, "serial-fallback", 1, collection.error
            ),
            (),
            behavior_digest,
            input_digest,
            environment=preparation_environment,
        )

    history = load_pytest_timing_history(root, behavior_digest, input_digest)
    decision = choose_pytest_worker_policy(
        selected_nodeids=collection.nodeids,
        history_load=history,
        configured_workers=configured_workers,
        threshold_ms=config.parallel_threshold_seconds * 1000.0,
        parallel_without_history=config.parallel_without_history,
    )
    configured = _configured_workers(resolved_command, root)
    needs_capability = decision.use_workers or configured is not None
    if not needs_capability:
        capabilities = PytestRunnerCapabilities(True, None, None)
    elif preparation_environment is not None:
        capabilities = _probe_pytest_runner_capabilities(
            resolved_command,
            root,
            preparation_environment,
        )
    else:
        capabilities = probe_pytest_runner_capabilities(resolved_command, root)
    scheduled, notice = apply_pytest_worker_decision(
        resolved_command,
        decision,
        capabilities,
        dist_mode=config.pytest_dist_mode,
        accepted_worker_counts=config.accepted_pytest_worker_counts,
        max_processes=config.max_processes,
        command_jobs=command_jobs,
        project_root=root,
        explicit=explicit,
    )
    return _instrumented_prepared_command(
        scheduled,
        notice,
        collection.nodeids,
        behavior_digest,
        input_digest,
        environment=preparation_environment,
    )


def finalize_pytest_timing(
    prepared: PreparedPytestCommand,
    result: TestRunResult,
    project_root: Path,
) -> TestSchedulingNotice | None:
    """Refresh advisory history only from successful exact-complete evidence."""
    temporary = prepared._temporary_directory
    if (
        temporary is None
        or prepared.behavior_group_digest is None
        or prepared.input_digest is None
    ):
        return None
    try:
        if not result.success:
            return _timing_discard_notice(prepared, "test command did not succeed")
        output_value = prepared.environment_overrides.get("MAID_TIMING_OUTPUT")
        if output_value is None:
            return _timing_discard_notice(prepared, "timing output was not configured")
        try:
            payload = json.loads(Path(output_value).read_text(encoding="utf-8"))
        except (OSError, UnicodeError, json.JSONDecodeError) as exc:
            return _timing_discard_notice(
                prepared, f"timing evidence unavailable: {exc}"
            )
        durations = _validated_timing_payload(payload, prepared.selected_nodeids)
        if durations is None:
            return _timing_discard_notice(prepared, "incomplete timing evidence")
        try:
            record_pytest_timing_history(
                Path(project_root),
                prepared.behavior_group_digest,
                prepared.input_digest,
                durations,
            )
        except (OSError, UnicodeError, TypeError, ValueError) as exc:
            return _timing_discard_notice(
                prepared, f"timing history was not persisted: {exc}"
            )
        return None
    finally:
        temporary.cleanup()


def _instrumented_prepared_command(
    command: tuple[str, ...],
    notice: TestSchedulingNotice,
    nodeids: tuple[str, ...],
    behavior_digest: str,
    input_digest: str,
    *,
    environment: Mapping[str, str] | None = None,
) -> PreparedPytestCommand:
    temporary = tempfile.TemporaryDirectory(prefix="maid-pytest-timing-")
    directory = Path(temporary.name)
    base_environment = (
        dict(environment) if environment is not None else _clean_child_environment()
    )
    overrides, plugin_name = _timing_plugin_environment(
        directory,
        base_environment.get("PYTHONPATH"),
    )
    timing_output = directory / "timings.json"
    selected_output = directory / "selected.json"
    selected_output.write_text(json.dumps(list(nodeids)), encoding="utf-8")
    overrides.update(
        {
            "PYTEST_PLUGINS": _merged_pytest_plugins(
                base_environment.get("PYTEST_PLUGINS"), plugin_name
            ),
            "MAID_TIMING_OUTPUT": str(timing_output),
            "MAID_SELECTED_NODEIDS_FILE": str(selected_output),
        }
    )
    return PreparedPytestCommand(
        command,
        overrides,
        notice,
        nodeids,
        behavior_digest,
        input_digest,
        temporary,
    )


def _configured_workers(
    command: tuple[str, ...], project_root: Path
) -> tuple[int | str, str] | None:
    invocation = _test_runner_invocation(list(command))
    command_args = (
        tuple(invocation[1])
        if invocation and invocation[0] in {"pytest", "py.test"}
        else ()
    )
    command_workers = _worker_option(command_args)
    if command_workers is not None:
        return command_workers, "command"
    config_workers = _worker_option(pytest_config_addopts_args(project_root, command))
    if config_workers is not None:
        return config_workers, "config"
    return None


def _worker_option(args: tuple[str, ...]) -> int | str | None:
    index = 0
    while index < len(args):
        part = args[index]
        if part in {"-n", "--numprocesses"}:
            if index + 1 >= len(args):
                raise ValueError(f"{part} requires a worker value")
            return _parse_worker_value(args[index + 1])
        if part.startswith("--numprocesses="):
            return _parse_worker_value(part.split("=", 1)[1])
        if part.startswith("-n") and part != "-n":
            return _parse_worker_value(part[2:])
        index += 1
    return None


def _parse_worker_value(value: str) -> int | str:
    try:
        return int(value)
    except ValueError:
        return value


def _bounded_worker_count(value: int | str) -> int:
    if isinstance(value, bool):
        raise ValueError("pytest workers must be a bounded integer")
    try:
        workers = int(value)
    except (TypeError, ValueError) as exc:
        raise ValueError("pytest workers must be a bounded integer") from exc
    if workers < 1 or str(value).strip() != str(workers):
        raise ValueError("pytest workers must be a bounded integer")
    return workers


def _require_process_budget(workers: int, command_jobs: int, maximum: int) -> None:
    if workers * command_jobs > maximum:
        raise ValueError(
            f"pytest workers exceed process budget: {command_jobs} * {workers} > {maximum}"
        )


def _pytest_command_prefix(command: tuple[str, ...]) -> tuple[str, ...] | None:
    invocation = _test_runner_invocation(list(command))
    if invocation is None or invocation[0] not in {"pytest", "py.test"}:
        return None
    for index, part in enumerate(command):
        if Path(part).name in {"pytest", "py.test"}:
            return command[: index + 1]
    return None


def _looks_like_resolved_pytest(command: tuple[str, ...]) -> bool:
    invocation = _test_runner_invocation(list(command))
    return invocation is not None and invocation[0] in {"pytest", "py.test"}


def _clean_child_environment() -> dict[str, str]:
    env = dict(os.environ)
    for name in (
        "PYTEST_ADDOPTS",
        "PYTEST_XDIST_WORKER",
        "PYTEST_XDIST_WORKER_COUNT",
    ):
        env.pop(name, None)
    return env


def _explicit_child_environment(
    overrides: Mapping[str, str] | None,
    removals: Sequence[str],
) -> dict[str, str]:
    environment = _clean_child_environment()
    for name in removals:
        environment.pop(name, None)
    environment.update(overrides or {})
    return environment


def _merged_pytest_plugins(existing: str | None, plugin_name: str) -> str:
    plugins = [
        plugin.strip()
        for plugin in (existing or "").split(",")
        if plugin.strip() and plugin.strip() != plugin_name
    ]
    plugins.append(plugin_name)
    return ",".join(plugins)


def _validated_timing_payload(
    payload: Any, expected_nodeids: tuple[str, ...]
) -> dict[str, float] | None:
    if not isinstance(payload, dict) or set(payload) != {"durations_ms"}:
        return None
    raw = payload["durations_ms"]
    if not isinstance(raw, dict) or set(raw) != set(expected_nodeids):
        return None
    durations: dict[str, float] = {}
    for nodeid, value in raw.items():
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            return None
        duration = float(value)
        if not math.isfinite(duration) or duration < 0:
            return None
        durations[nodeid] = duration
    return durations


def _timing_discard_notice(
    prepared: PreparedPytestCommand, reason: str
) -> TestSchedulingNotice:
    workers = prepared.notice.workers if prepared.notice is not None else 1
    return TestSchedulingNotice(prepared.command, "timing-discarded", workers, reason)


def _update_file_digest(digest: Any, path: Path, root: Path) -> None:
    relative = path.relative_to(root).as_posix()
    digest.update(relative.encode("utf-8"))
    digest.update(b"\0")
    digest.update(path.read_bytes())
    digest.update(b"\0")


def _excluded_identity_path(relative: Path) -> bool:
    parts = relative.parts
    if not parts:
        return True
    if parts[:2] == (".maid", "cache"):
        return True
    return any(
        part
        in {
            ".git",
            ".pytest_cache",
            ".venv",
            "venv",
            "node_modules",
            "__pycache__",
        }
        for part in parts
    )
