"""Bounded scheduling for independently isolated knockout mutations."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from concurrent.futures import FIRST_COMPLETED, Future, ThreadPoolExecutor, wait
from contextlib import nullcontext
from dataclasses import dataclass, replace
from pathlib import Path

from maid_runner.core._knockout_snapshot import ProjectSnapshotBackend
from maid_runner.core._pytest_worker_execution import (
    _bounded_worker_count,
    _configured_workers,
)
from maid_runner.core._test_runner_invocation import _test_runner_invocation
from maid_runner.core.knockout import (
    KnockoutArtifactIdentity,
    KnockoutCommandExecutor,
    KnockoutMutationSpec,
    KnockoutReport,
    _harness_error,
    _run_differential_declaration,
    _target_path_or_error,
)
from maid_runner.core.result import ValidationError
from maid_runner.core.runtime_evidence import RuntimeEvidenceBundle


@dataclass(frozen=True)
class KnockoutWorkerResult:
    """One unique mutation's isolated declaration reports."""

    identity: KnockoutArtifactIdentity
    reports: Mapping[str, KnockoutReport]
    process_cost: int
    errors: tuple[ValidationError, ...]


def execute_knockout_worker(
    spec: KnockoutMutationSpec,
    project_root: Path,
    evidence: RuntimeEvidenceBundle | None,
    snapshot_backend: ProjectSnapshotBackend,
    executor: KnockoutCommandExecutor,
) -> KnockoutWorkerResult:
    """Execute every retained declaration in its own fresh snapshot."""
    root = Path(project_root)
    reports: dict[str, KnockoutReport] = {}
    process_cost = _spec_process_cost(spec, root)
    for declaration in spec.declarations:
        identity = spec.identity
        try:
            worker_id = (
                f"{declaration.plan_index:06d}-{declaration.manifest_slug}-"
                f"{identity.artifact_name}"
            )
            with snapshot_backend.create(
                root,
                (identity.file_path,),
                worker_id,
            ) as snapshot:
                if (
                    snapshot.source_digests.get(identity.file_path)
                    != spec.source_digest
                ):
                    raise RuntimeError(
                        "Knockout source bytes changed before isolated execution: "
                        f"{identity.file_path}"
                    )
                target_path, target_error = _target_path_or_error(
                    snapshot.root,
                    identity.file_path,
                )
                if target_error is not None:
                    raise RuntimeError(target_error.message)
                result, errors = _run_differential_declaration(
                    identity,
                    declaration,
                    snapshot.root,
                    target_path,
                    root,
                    evidence,
                    executor,
                    snapshot.environment_overrides,
                    snapshot.environment_removals,
                )
        except Exception as exc:
            result = None
            errors = [_harness_error(identity.file_path, str(exc))]
        reports[str(declaration.plan_index)] = KnockoutReport(
            results=((result,) if result is not None else ()),
            errors=tuple(errors),
        )
    return KnockoutWorkerResult(spec.identity, reports, process_cost, ())


def resolve_knockout_process_cost(
    command: tuple[str, ...],
    project_root: Path,
) -> int:
    """Resolve the maximum external-process cost of one command."""
    invocation = _test_runner_invocation(list(command))
    if invocation is None or invocation[0] not in {"pytest", "py.test"}:
        return 1
    configured = _configured_workers(command, Path(project_root))
    if configured is not None:
        workers, _source = configured
        if isinstance(workers, str) and workers.startswith("="):
            workers = workers[1:]
        if workers in {0, "0"}:
            return 1
        return _bounded_worker_count(workers)
    return 1


def run_knockout_workers(
    specs: Sequence[KnockoutMutationSpec],
    project_root: Path,
    evidence: RuntimeEvidenceBundle | None,
    snapshot_backend: ProjectSnapshotBackend,
    executor: KnockoutCommandExecutor,
    jobs: int,
    max_processes: int,
) -> tuple[KnockoutWorkerResult, ...]:
    """Schedule weighted workers and return input-identity order."""
    _require_positive_integer("jobs", jobs)
    _require_positive_integer("max_processes", max_processes)
    retain = getattr(snapshot_backend, "retain", None)
    context = retain() if callable(retain) else nullcontext()
    with context:
        return _schedule_knockout_workers(
            specs,
            project_root,
            evidence,
            snapshot_backend,
            executor,
            jobs,
            max_processes,
        )


def _schedule_knockout_workers(
    specs: Sequence[KnockoutMutationSpec],
    project_root: Path,
    evidence: RuntimeEvidenceBundle | None,
    snapshot_backend: ProjectSnapshotBackend,
    executor: KnockoutCommandExecutor,
    jobs: int,
    max_processes: int,
) -> tuple[KnockoutWorkerResult, ...]:
    ordered = tuple(specs)
    prepared: list[tuple[int, KnockoutMutationSpec, int] | KnockoutWorkerResult] = []
    for index, spec in enumerate(ordered):
        try:
            cost = _spec_process_cost(spec, Path(project_root))
            if cost > max_processes:
                raise ValueError(
                    f"knockout process cost {cost} exceeds budget {max_processes}"
                )
            prepared.append((index, spec, cost))
        except Exception as exc:
            prepared.append(_failed_worker(spec, 1, str(exc)))

    results: list[KnockoutWorkerResult | None] = [None] * len(ordered)
    runnable: list[tuple[int, KnockoutMutationSpec, int]] = []
    for index, item in enumerate(prepared):
        if isinstance(item, KnockoutWorkerResult):
            results[index] = item
        else:
            runnable.append(item)

    if jobs == 1:
        for index, spec, cost in runnable:
            results[index] = _execute_safely(
                spec,
                Path(project_root),
                evidence,
                snapshot_backend,
                executor,
                cost,
            )
        return tuple(result for result in results if result is not None)

    active: dict[
        Future[KnockoutWorkerResult], tuple[int, KnockoutMutationSpec, int]
    ] = {}
    reserved = 0
    with ThreadPoolExecutor(max_workers=min(jobs, len(runnable) or 1)) as pool:
        while runnable or active:
            while len(active) < jobs:
                selected = next(
                    (
                        position
                        for position, (_index, _spec, cost) in enumerate(runnable)
                        if reserved + cost <= max_processes
                    ),
                    None,
                )
                if selected is None:
                    break
                index, spec, cost = runnable.pop(selected)
                future = pool.submit(
                    execute_knockout_worker,
                    spec,
                    Path(project_root),
                    evidence,
                    snapshot_backend,
                    executor,
                )
                active[future] = (index, spec, cost)
                reserved += cost
            if not active:
                break
            completed, _pending = wait(active, return_when=FIRST_COMPLETED)
            for future in completed:
                index, spec, cost = active.pop(future)
                reserved -= cost
                try:
                    result = future.result()
                except Exception as exc:
                    result = _failed_worker(spec, cost, str(exc))
                results[index] = _validated_worker_result(spec, cost, result)

    for index, result in enumerate(results):
        if result is None:
            results[index] = _failed_worker(
                ordered[index], 1, "Knockout worker produced no result"
            )
    return tuple(result for result in results if result is not None)


def _execute_safely(
    spec: KnockoutMutationSpec,
    root: Path,
    evidence: RuntimeEvidenceBundle | None,
    snapshot_backend: ProjectSnapshotBackend,
    executor: KnockoutCommandExecutor,
    cost: int,
) -> KnockoutWorkerResult:
    try:
        result = execute_knockout_worker(
            spec, root, evidence, snapshot_backend, executor
        )
    except Exception as exc:
        return _failed_worker(spec, cost, str(exc))
    return _validated_worker_result(spec, cost, result)


def _validated_worker_result(
    spec: KnockoutMutationSpec,
    cost: int,
    result: KnockoutWorkerResult,
) -> KnockoutWorkerResult:
    if result.identity != spec.identity:
        return _failed_worker(spec, cost, "Knockout worker identity mismatch")
    return replace(result, process_cost=cost)


def _failed_worker(
    spec: KnockoutMutationSpec,
    cost: int,
    message: str,
) -> KnockoutWorkerResult:
    return KnockoutWorkerResult(
        spec.identity,
        {},
        cost,
        (_harness_error(spec.identity.file_path, message),),
    )


def _spec_process_cost(
    spec: KnockoutMutationSpec,
    root: Path,
) -> int:
    return max(
        (
            resolve_knockout_process_cost(command, root)
            for declaration in spec.declarations
            for command in declaration.commands
        ),
        default=1,
    )


def _require_positive_integer(name: str, value: int) -> None:
    if isinstance(value, bool) or not isinstance(value, int) or value < 1:
        raise ValueError(f"knockout {name} must be a positive integer")
