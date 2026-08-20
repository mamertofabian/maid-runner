"""Bounded scheduling for independently isolated knockout mutations."""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from concurrent.futures import FIRST_COMPLETED, Future, ThreadPoolExecutor, wait
from contextlib import nullcontext
from dataclasses import dataclass, replace
from pathlib import Path
import time

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
    KnockoutResult,
    _KnockoutCommandGroup,
    _KnockoutCommandGroupMember,
    _content_hash,
    _exact_transition_error,
    _execute_after_shared_baseline,
    _execute_snapshot_command,
    _harness_error,
    _is_positive_transition,
    _mutation_artifact_name,
    _mutation_file_path,
    _not_detected_error,
    _proof,
    _run_differential_declaration,
    _spec_required_paths,
    _target_path_or_error,
    rewrite_artifact_body,
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
                _spec_required_paths(spec),
                worker_id,
            ) as snapshot:
                mutation_file_path = _mutation_file_path(spec)
                if (
                    snapshot.source_digests.get(mutation_file_path)
                    != spec.source_digest
                ):
                    raise RuntimeError(
                        "Knockout source bytes changed before isolated execution: "
                        f"{mutation_file_path}"
                    )
                target_path, target_error = _target_path_or_error(
                    snapshot.root,
                    mutation_file_path,
                )
                if target_error is not None:
                    raise RuntimeError(target_error.message)
                result, errors = _run_differential_declaration(
                    identity,
                    _mutation_artifact_name(spec),
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
    on_result: Callable[[KnockoutWorkerResult], None] | None = None,
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
            on_result,
        )


def _run_knockout_command_groups(
    groups: Sequence[_KnockoutCommandGroup],
    project_root: Path,
    evidence: RuntimeEvidenceBundle | None,
    snapshot_backend: ProjectSnapshotBackend,
    executor: KnockoutCommandExecutor,
    jobs: int,
    max_processes: int,
    on_result: Callable[[KnockoutWorkerResult], None] | None = None,
) -> tuple[KnockoutWorkerResult, ...]:
    """Schedule exact-command groups within the weighted process budget."""
    _require_positive_integer("jobs", jobs)
    _require_positive_integer("max_processes", max_processes)
    del evidence
    ordered = tuple(groups)
    retain = getattr(snapshot_backend, "retain", None)
    context = retain() if callable(retain) else nullcontext()
    try:
        with context:
            return _schedule_knockout_command_groups(
                ordered,
                Path(project_root),
                snapshot_backend,
                executor,
                jobs,
                max_processes,
                on_result,
            )
    except Exception as exc:
        return tuple(
            _failed_worker(member.spec, 1, str(exc))
            for group in ordered
            for member in group.members
        )


def _schedule_knockout_command_groups(
    groups: tuple[_KnockoutCommandGroup, ...],
    root: Path,
    snapshot_backend: ProjectSnapshotBackend,
    executor: KnockoutCommandExecutor,
    jobs: int,
    max_processes: int,
    on_result: Callable[[KnockoutWorkerResult], None] | None,
) -> tuple[KnockoutWorkerResult, ...]:
    prepared: list[tuple[int, _KnockoutCommandGroup, int]] = []
    immediate: list[KnockoutWorkerResult] = []
    for index, group in enumerate(groups):
        try:
            cost = resolve_knockout_process_cost(group.command, root)
            if cost > max_processes:
                raise ValueError(
                    f"knockout process cost {cost} exceeds budget {max_processes}"
                )
            prepared.append((index, group, cost))
        except Exception as exc:
            immediate.extend(
                _failed_worker(member.spec, 1, str(exc)) for member in group.members
            )

    by_identity = {worker.identity: worker for worker in immediate}
    active: dict[
        Future[tuple[KnockoutWorkerResult, ...]],
        tuple[int, _KnockoutCommandGroup, int],
    ] = {}
    reserved = 0
    with ThreadPoolExecutor(max_workers=min(jobs, len(prepared) or 1)) as pool:
        while prepared or active:
            while len(active) < jobs:
                selected = next(
                    (
                        position
                        for position, (_index, _group, cost) in enumerate(prepared)
                        if reserved + cost <= max_processes
                    ),
                    None,
                )
                if selected is None:
                    break
                item = prepared.pop(selected)
                index, group, cost = item
                future = pool.submit(
                    _execute_knockout_command_group,
                    group,
                    root,
                    snapshot_backend,
                    executor,
                    cost,
                    on_result,
                )
                active[future] = item
                reserved += cost
            if not active:
                break
            completed, _pending = wait(active, return_when=FIRST_COMPLETED)
            for future in completed:
                _index, group, cost = active.pop(future)
                reserved -= cost
                try:
                    workers = future.result()
                except Exception as exc:
                    workers = tuple(
                        _failed_worker(member.spec, cost, str(exc))
                        for member in group.members
                    )
                by_identity.update((worker.identity, worker) for worker in workers)

    for _index, group, cost in prepared:
        for member in group.members:
            failed = _failed_worker(
                member.spec, cost, "Knockout command group produced no result"
            )
            by_identity[failed.identity] = failed
            if on_result is not None:
                on_result(failed)
    ordered_members = sorted(
        (member for group in groups for member in group.members),
        key=lambda member: member.declaration.plan_index,
    )
    return tuple(
        by_identity.get(member.spec.identity)
        or _failed_worker(member.spec, 1, "Knockout command group result is missing")
        for member in ordered_members
    )


def _execute_knockout_command_group(
    group: _KnockoutCommandGroup,
    root: Path,
    snapshot_backend: ProjectSnapshotBackend,
    executor: KnockoutCommandExecutor,
    process_cost: int,
    on_result: Callable[[KnockoutWorkerResult], None] | None,
) -> tuple[KnockoutWorkerResult, ...]:
    stable_group = getattr(snapshot_backend, "_stable_group", None)
    if not callable(stable_group):
        return tuple(
            _failed_worker(
                member.spec,
                process_cost,
                "Snapshot backend does not support stable command groups",
            )
            for member in group.members
        )
    required_paths = tuple(
        dict.fromkeys(
            path
            for member in group.members
            for path in _spec_required_paths(member.spec)
        )
    )
    worker_id = (
        f"group-{group.members[0].declaration.plan_index:06d}-" f"{group.manifest_slug}"
    )
    completed: list[KnockoutWorkerResult] = []
    try:
        with stable_group(root, required_paths, worker_id) as stable:
            snapshot = stable.snapshot
            for member in group.members:
                mutation_file_path = _mutation_file_path(member.spec)
                if (
                    snapshot.source_digests.get(mutation_file_path)
                    != member.spec.source_digest
                ):
                    raise RuntimeError(
                        "Knockout source bytes changed before grouped execution: "
                        f"{mutation_file_path}"
                    )
            baseline = _execute_snapshot_command(
                executor,
                group.command,
                snapshot.root,
                group.manifest_slug,
                snapshot.environment_overrides,
                snapshot.environment_removals,
            )
            for member in group.members:
                mutation_file_path = _mutation_file_path(member.spec)
                target_path, target_error = _target_path_or_error(
                    snapshot.root, mutation_file_path
                )
                if target_error is not None:
                    raise RuntimeError(target_error.message)
                if _content_hash(target_path.read_bytes()) != member.spec.source_digest:
                    raise RuntimeError(
                        "Knockout baseline command changed target bytes before "
                        f"mutation: {mutation_file_path}"
                    )
            stable.verify_identities()
            if baseline.exit_code != 0:
                return tuple(
                    _baseline_failure_worker(member, baseline, process_cost)
                    for member in group.members
                )
            stable.freeze()
            for position, member in enumerate(group.members):
                stable.reset()
                worker, fatal = _execute_group_member(
                    member,
                    baseline,
                    snapshot,
                    root,
                    executor,
                    process_cost,
                )
                stable.verify_identities()
                completed.append(worker)
                if on_result is not None:
                    on_result(worker)
                if fatal:
                    for remaining in group.members[position + 1 :]:
                        completed.append(
                            _failed_worker(
                                remaining.spec,
                                process_cost,
                                "Knockout command group stopped after a prior "
                                "mutation could not complete safely",
                            )
                        )
                    break
            stable.verify_identities()
    except Exception as exc:
        return tuple(
            _failed_worker(member.spec, process_cost, str(exc))
            for member in group.members
        )
    return tuple(completed)


def _execute_group_member(
    member: _KnockoutCommandGroupMember,
    baseline,
    snapshot,
    evidence_root: Path,
    executor: KnockoutCommandExecutor,
    process_cost: int,
) -> tuple[KnockoutWorkerResult, bool]:
    started = time.monotonic()
    identity = member.spec.identity
    errors: list[ValidationError] = []
    proof = None
    fatal = False
    try:
        mutation_file_path = _mutation_file_path(member.spec)
        target_path, target_error = _target_path_or_error(
            snapshot.root, mutation_file_path
        )
        if target_error is not None:
            raise RuntimeError(target_error.message)
        original = target_path.read_bytes()
        original_hash = _content_hash(original)
        if original_hash != member.spec.source_digest:
            raise RuntimeError(
                "Knockout reset source bytes do not match the planned mutation: "
                f"{mutation_file_path}"
            )
        rewritten = rewrite_artifact_body(
            original.decode("utf-8"),
            _mutation_artifact_name(member.spec),
            identity.artifact_kind,
            identity.parent_class,
        ).encode("utf-8")
        transition, transition_error = _execute_after_shared_baseline(
            member.command,
            member.declaration.manifest_slug,
            snapshot.root,
            target_path,
            identity.file_path,
            original,
            original_hash,
            rewritten,
            executor,
            snapshot.environment_overrides,
            snapshot.environment_removals,
            baseline,
        )
        if transition_error is not None:
            errors.append(transition_error)
            fatal = True
        elif (
            member.focused
            and len(transition) == 3
            and _is_positive_transition(*transition)
        ):
            proof = _proof(
                identity,
                member.command,
                *transition,
                member.nodeids,
                used_exact_fallback=False,
            )
        elif member.focused:
            exact_command = member.declaration.commands[0]
            from maid_runner.core.knockout import _execute_transition

            exact, exact_transition_error = _execute_transition(
                exact_command,
                member.declaration.manifest_slug,
                snapshot.root,
                target_path,
                identity.file_path,
                original,
                original_hash,
                rewritten,
                executor,
                snapshot.environment_overrides,
                snapshot.environment_removals,
            )
            if exact_transition_error is not None:
                errors.append(exact_transition_error)
                fatal = True
            else:
                exact_error = _exact_transition_error(
                    identity.file_path, exact_command, exact
                )
                if exact_error is not None:
                    errors.append(exact_error)
                elif len(exact) == 3:
                    proof = _proof(
                        identity,
                        exact_command,
                        *exact,
                        (),
                        used_exact_fallback=True,
                    )
        else:
            exact_error = _exact_transition_error(
                identity.file_path, member.command, transition
            )
            if exact_error is not None:
                errors.append(exact_error)
            elif len(transition) == 3:
                proof = _proof(
                    identity,
                    member.command,
                    *transition,
                    (),
                    used_exact_fallback=True,
                )
    except Exception as exc:
        errors.append(_harness_error(identity.file_path, str(exc)))
        fatal = True
    detected = proof is not None and proof.mutant_exit_code != 0 and not errors
    if not detected and not errors:
        errors.append(_not_detected_error(identity))
    result = KnockoutResult(
        artifact_name=identity.artifact_name,
        artifact_kind=identity.artifact_kind,
        parent_class=identity.parent_class,
        file_path=identity.file_path,
        detected=detected,
        duration_ms=(time.monotonic() - started) * 1000,
        proof=proof,
    )
    report = KnockoutReport(results=(result,), errors=tuple(errors))
    return (
        KnockoutWorkerResult(
            identity,
            {str(member.declaration.plan_index): report},
            process_cost,
            (),
        ),
        fatal,
    )


def _baseline_failure_worker(
    member: _KnockoutCommandGroupMember,
    baseline,
    process_cost: int,
) -> KnockoutWorkerResult:
    identity = member.spec.identity
    result = KnockoutResult(
        artifact_name=identity.artifact_name,
        artifact_kind=identity.artifact_kind,
        parent_class=identity.parent_class,
        file_path=identity.file_path,
        detected=False,
        duration_ms=baseline.duration_ms,
    )
    error = _exact_transition_error(identity.file_path, member.command, (baseline,))
    assert error is not None
    return KnockoutWorkerResult(
        identity,
        {
            str(member.declaration.plan_index): KnockoutReport(
                results=(result,), errors=(error,)
            )
        },
        process_cost,
        (),
    )


def _schedule_knockout_workers(
    specs: Sequence[KnockoutMutationSpec],
    project_root: Path,
    evidence: RuntimeEvidenceBundle | None,
    snapshot_backend: ProjectSnapshotBackend,
    executor: KnockoutCommandExecutor,
    jobs: int,
    max_processes: int,
    on_result: Callable[[KnockoutWorkerResult], None] | None,
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
            if on_result is not None:
                on_result(item)
        else:
            runnable.append(item)

    if jobs == 1:
        for index, spec, cost in runnable:
            result = _execute_safely(
                spec,
                Path(project_root),
                evidence,
                snapshot_backend,
                executor,
                cost,
            )
            results[index] = result
            if on_result is not None:
                on_result(result)
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
                validated = _validated_worker_result(spec, cost, result)
                results[index] = validated
                if on_result is not None:
                    on_result(validated)

    for index, result in enumerate(results):
        if result is None:
            failed = _failed_worker(
                ordered[index], 1, "Knockout worker produced no result"
            )
            results[index] = failed
            if on_result is not None:
                on_result(failed)
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
