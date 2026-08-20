"""Test execution for MAID Runner v2."""

from __future__ import annotations

import argparse
from concurrent.futures import Future, ThreadPoolExecutor
from collections.abc import Iterable, Mapping
from pathlib import Path
from typing import Union

from maid_runner.core.chain import (
    _enter_manifest_chain_cache_scope,
    _exit_manifest_chain_cache_scope,
    get_cached_manifest_chain,
)
from maid_runner.core._pytest_command_normalization import (
    _is_python_command as _normalization_is_python_command,
)
from maid_runner.core._pytest_worker_execution import (
    PreparedPytestCommand,
    TestSchedulingNotice,
    finalize_pytest_timing,
    prepare_pytest_command,
)
from maid_runner.core._maid_validate_command_cache import (
    _parse_maid_validate_command,
    _run_cached_maid_validate_command,
)
from maid_runner.core._test_command_execution import (
    _run_test_command,
    _test_command_environment as _execution_test_command_environment,
)
from maid_runner.core._test_command_batching import (
    _batch_compatible_test_commands,
    _batch_group_key,
    _batch_pytest as _batching_batch_pytest,
    _can_batch as _batching_can_batch,
    _dedupe_commands,
    _prune_covered_pytest_commands,
)
from maid_runner.core.manifest import load_manifest, validate_manifest_paths
from maid_runner.core.result import (
    BatchTestResult,
    Severity,
    TestRunResult,
    ValidationError,
)
from maid_runner.core.types import Manifest, TestStream


_MANIFEST_TEST_COMMAND_TIMEOUT_SECONDS = 600


def _is_python_command(cmd: str) -> bool:
    return _normalization_is_python_command(cmd)


def _is_uv_project(cwd: Union[str, Path]) -> bool:
    """Check if directory is a uv-managed project (uv.lock present)."""
    return Path(cwd).joinpath("uv.lock").exists()


def _resolve_command(
    command: tuple[str, ...], *, cwd: Union[str, Path] = "."
) -> tuple[str, ...]:
    """Prepend ``uv run`` to Python commands when running in a uv-managed project."""
    if not command:
        return command
    # Already wrapped — don't double-prefix
    if command[0] == "uv":
        return command
    # Only wrap known Python ecosystem commands
    if not _is_python_command(command[0]):
        return command
    # Only when uv.lock exists (definitive uv-managed project marker)
    if not _is_uv_project(cwd):
        return command
    return ("uv", "run") + command


def run_command(
    command: tuple[str, ...],
    *,
    cwd: Union[str, Path] = ".",
    timeout: int = 300,
    manifest_slug: str = "",
    stream: TestStream = TestStream.IMPLEMENTATION,
    environment_overrides: Mapping[str, str] | None = None,
) -> TestRunResult:
    command = _resolve_command(command, cwd=cwd)
    return _run_test_command(
        command,
        cwd=cwd,
        timeout=timeout,
        manifest_slug=manifest_slug,
        stream=stream,
        environment_overrides=environment_overrides,
    )


def _test_command_environment() -> dict[str, str]:
    return _execution_test_command_environment()


def run_manifest_tests(
    manifest_path: Union[str, Path],
    *,
    fail_fast: bool = False,
    project_root: Union[str, Path] = ".",
    pytest_workers: int | str | None = None,
) -> BatchTestResult:
    manifest = load_manifest(manifest_path)
    project_root = Path(project_root)

    integrity_errors = _validate_manifest_test_command_integrity(
        [manifest], project_root
    )
    if integrity_errors:
        return BatchTestResult(
            results=[],
            total=0,
            passed=0,
            failed=0,
            chain_errors=integrity_errors,
        )

    results: list[TestRunResult] = []
    passed = 0
    failed = 0
    scheduling_notices: list[TestSchedulingNotice] = []

    for cmd in manifest.validate_commands:
        result = _run_external_test_command(
            cmd,
            project_root,
            manifest.slug,
            pytest_workers=pytest_workers,
            command_jobs=1,
            scheduling_notices=scheduling_notices,
        )
        results.append(result)
        if result.success:
            passed += 1
        else:
            failed += 1
            if fail_fast:
                break

    return BatchTestResult(
        results=results,
        total=len(results),
        passed=passed,
        failed=failed,
        scheduling_notices=tuple(scheduling_notices),
    )


def _can_batch(commands: list[tuple[str, ...]]) -> bool:
    return _batching_can_batch(
        commands,
        resolve_command=_resolve_command,
        is_uv_project=_is_uv_project,
    )


def _batch_pytest(commands: list[tuple[str, ...]]) -> tuple[str, ...]:
    return _batching_batch_pytest(commands)


def run_tests(
    manifest_dir: Union[str, Path] = "manifests/",
    *,
    fail_fast: bool = False,
    project_root: Union[str, Path] = ".",
    batch: bool | None = None,
    jobs: int = 1,
    pytest_workers: int | str | None = None,
) -> BatchTestResult:
    chain_outermost = _enter_manifest_chain_cache_scope()
    try:
        return _run_tests_cached(
            manifest_dir=manifest_dir,
            fail_fast=fail_fast,
            project_root=project_root,
            batch=batch,
            jobs=jobs,
            pytest_workers=pytest_workers,
        )
    finally:
        _exit_manifest_chain_cache_scope(chain_outermost)


def _run_tests_cached(
    manifest_dir: Union[str, Path] = "manifests/",
    *,
    fail_fast: bool = False,
    project_root: Union[str, Path] = ".",
    batch: bool | None = None,
    jobs: int = 1,
    pytest_workers: int | str | None = None,
) -> BatchTestResult:
    project_root = Path(project_root)
    chain_dir = project_root / manifest_dir

    if not chain_dir.exists():
        return BatchTestResult(results=[], total=0, passed=0, failed=0)

    chain = get_cached_manifest_chain(chain_dir, project_root)
    chain_errors = chain.diagnostics()
    if any(error.severity == Severity.ERROR for error in chain_errors):
        return BatchTestResult(
            results=[],
            total=0,
            passed=0,
            failed=0,
            chain_errors=chain_errors,
        )
    active = chain.active_manifests()
    integrity_errors = _validate_manifest_test_command_integrity(active, project_root)
    if integrity_errors:
        return BatchTestResult(
            results=[],
            total=0,
            passed=0,
            failed=0,
            chain_errors=[*chain_errors, *integrity_errors],
        )

    _, implementation_commands = _collect_test_command_streams(active)

    scheduling_notices: list[TestSchedulingNotice] = []
    results, passed, failed, early_result = _run_implementation_commands(
        implementation_commands,
        project_root,
        batch,
        fail_fast,
        chain_errors,
        [],
        0,
        0,
        jobs=jobs,
        pytest_workers=pytest_workers,
        scheduling_notices=scheduling_notices,
    )
    if early_result is not None:
        return early_result

    return BatchTestResult(
        results=results,
        total=len(results),
        passed=passed,
        failed=failed,
        chain_errors=chain_errors,
        scheduling_notices=tuple(scheduling_notices),
    )


def _collect_test_command_streams(
    manifests: Iterable[Manifest],
) -> tuple[list[tuple[tuple[str, ...], str]], list[tuple[tuple[str, ...], str]]]:
    acceptance_commands: list[tuple[tuple[str, ...], str]] = []
    implementation_commands: list[tuple[tuple[str, ...], str]] = []
    for manifest in manifests:
        if manifest.acceptance is not None:
            for cmd in manifest.acceptance.tests:
                acceptance_commands.append((cmd, manifest.slug))
        for cmd in manifest.validate_commands:
            implementation_commands.append((cmd, manifest.slug))
    return acceptance_commands, implementation_commands


def _run_acceptance_commands(
    commands: list[tuple[tuple[str, ...], str]],
    project_root: Path,
    fail_fast: bool,
    chain_errors: list[ValidationError],
) -> tuple[list[TestRunResult], int, int, BatchTestResult | None]:
    results: list[TestRunResult] = []
    passed = 0
    failed = 0
    for cmd, slug in commands:
        result = run_command(
            cmd, cwd=project_root, manifest_slug=slug, stream=TestStream.ACCEPTANCE
        )
        results.append(result)
        if result.success:
            passed += 1
        else:
            failed += 1
            if fail_fast:
                return (
                    results,
                    passed,
                    failed,
                    BatchTestResult(
                        results=results,
                        total=len(results),
                        passed=passed,
                        failed=failed,
                        chain_errors=chain_errors,
                    ),
                )

    return results, passed, failed, None


def _run_implementation_commands(
    commands: list[tuple[tuple[str, ...], str]],
    project_root: Path,
    batch: bool | None,
    fail_fast: bool,
    chain_errors: list[ValidationError],
    previous_results: list[TestRunResult],
    previous_passed: int,
    previous_failed: int,
    jobs: int = 1,
    pytest_workers: int | str | None = None,
    scheduling_notices: list[TestSchedulingNotice] | None = None,
) -> tuple[list[TestRunResult], int, int, BatchTestResult | None]:
    results = list(previous_results)
    passed = previous_passed
    failed = previous_failed
    maid_validate_cache: dict[str, object] = {}
    notices = scheduling_notices if scheduling_notices is not None else []
    ordered_impl_commands = commands
    if batch is not False:
        impl_commands_with_slug = _prune_covered_pytest_commands(
            _dedupe_commands(
                commands,
                cwd=project_root,
                resolve_command=_resolve_command,
            ),
            cwd=project_root,
            resolve_command=_resolve_command,
            is_uv_project=_is_uv_project,
        )
        batch_groups: dict[
            tuple[tuple[str, ...], tuple[str, ...]],
            list[tuple[tuple[str, ...], str]],
        ] = {}
        sequential_impl_commands: list[tuple[tuple[str, ...], str]] = []
        for cmd, slug in impl_commands_with_slug:
            group_key = _batch_group_key(
                cmd,
                cwd=project_root,
                resolve_command=_resolve_command,
                is_uv_project=_is_uv_project,
            )
            if group_key is None:
                sequential_impl_commands.append((cmd, slug))
                continue
            _, prefix, options = group_key
            batch_groups.setdefault((prefix, options), []).append((cmd, slug))

        batched_impl_commands: list[tuple[tuple[str, ...], str]] = []
        for group in batch_groups.values():
            if len(group) <= 1:
                sequential_impl_commands.extend(group)
                continue
            batched_cmd = _batch_compatible_test_commands(
                [cmd for cmd, _ in group],
                cwd=project_root,
                resolve_command=_resolve_command,
                is_uv_project=_is_uv_project,
            )
            batched_impl_commands.append((batched_cmd, "batch"))
        ordered_impl_commands = [*batched_impl_commands, *sequential_impl_commands]

    if jobs > 1 and not fail_fast:
        has_cached_commands = any(
            _parse_maid_validate_command(command) is not None
            for command, _slug in ordered_impl_commands
        )
        external_workers = jobs - 1 if has_cached_commands else jobs
        result_slots: list[
            TestRunResult | tuple[PreparedPytestCommand, Future[TestRunResult]]
        ] = []
        with ThreadPoolExecutor(max_workers=external_workers) as executor:
            for cmd, slug in ordered_impl_commands:
                result = _run_cached_maid_validate_command(
                    cmd,
                    cwd=project_root,
                    manifest_slug=slug,
                    stream=TestStream.IMPLEMENTATION,
                    cache=maid_validate_cache,
                    resolve_command=_resolve_command,
                )
                if result is not None:
                    result_slots.append(result)
                    continue

                prepared = _prepare_external_test_command(
                    cmd,
                    project_root,
                    pytest_workers=pytest_workers,
                    command_jobs=jobs,
                    scheduling_notices=notices,
                )
                future = executor.submit(
                    _run_prepared_test_command,
                    prepared,
                    project_root,
                    slug,
                )
                result_slots.append((prepared, future))

            for slot in result_slots:
                if isinstance(slot, TestRunResult):
                    result = slot
                else:
                    prepared, future = slot
                    result = future.result()
                    _finalize_prepared_test_command(
                        prepared,
                        result,
                        project_root,
                        notices,
                    )
                results.append(result)
                if result.success:
                    passed += 1
                else:
                    failed += 1

        return results, passed, failed, None

    for cmd, slug in ordered_impl_commands:
        result = _run_cached_maid_validate_command(
            cmd,
            cwd=project_root,
            manifest_slug=slug,
            stream=TestStream.IMPLEMENTATION,
            cache=maid_validate_cache,
            resolve_command=_resolve_command,
        )
        if result is None:
            result = _run_external_test_command(
                cmd,
                project_root,
                slug,
                pytest_workers=pytest_workers,
                command_jobs=jobs,
                scheduling_notices=notices,
            )
        results.append(result)
        if result.success:
            passed += 1
        else:
            failed += 1
            if fail_fast:
                return (
                    results,
                    passed,
                    failed,
                    BatchTestResult(
                        results=results,
                        total=len(results),
                        passed=passed,
                        failed=failed,
                        chain_errors=chain_errors,
                        scheduling_notices=tuple(notices),
                    ),
                )

    return results, passed, failed, None


def _prepare_external_test_command(
    command: tuple[str, ...],
    project_root: Path,
    *,
    pytest_workers: int | str | None,
    command_jobs: int,
    scheduling_notices: list[TestSchedulingNotice],
) -> PreparedPytestCommand:
    resolved = _resolve_command(command, cwd=project_root)
    prepared = prepare_pytest_command(
        resolved,
        project_root=project_root,
        pytest_workers=pytest_workers,
        command_jobs=command_jobs,
    )
    if (
        isinstance(prepared, PreparedPytestCommand)
        and prepared.notice is None
        and prepared.behavior_group_digest is None
    ):
        prepared = PreparedPytestCommand(
            command,
            prepared.environment_overrides,
            prepared.notice,
            prepared.selected_nodeids,
            prepared.behavior_group_digest,
            prepared.input_digest,
            prepared._temporary_directory,
        )
    if prepared.notice is not None:
        scheduling_notices.append(prepared.notice)
    return prepared


def _run_prepared_test_command(
    prepared: PreparedPytestCommand,
    project_root: Path,
    manifest_slug: str,
) -> TestRunResult:
    return run_command(
        prepared.command,
        cwd=project_root,
        timeout=_MANIFEST_TEST_COMMAND_TIMEOUT_SECONDS,
        manifest_slug=manifest_slug,
        environment_overrides=prepared.environment_overrides,
    )


def _finalize_prepared_test_command(
    prepared: PreparedPytestCommand,
    result: TestRunResult,
    project_root: Path,
    scheduling_notices: list[TestSchedulingNotice],
) -> None:
    notice = finalize_pytest_timing(prepared, result, project_root)
    if notice is not None:
        scheduling_notices.append(notice)


def _run_external_test_command(
    command: tuple[str, ...],
    project_root: Path,
    manifest_slug: str,
    *,
    pytest_workers: int | str | None,
    command_jobs: int,
    scheduling_notices: list[TestSchedulingNotice],
) -> TestRunResult:
    prepared = _prepare_external_test_command(
        command,
        project_root,
        pytest_workers=pytest_workers,
        command_jobs=command_jobs,
        scheduling_notices=scheduling_notices,
    )
    result = _run_prepared_test_command(prepared, project_root, manifest_slug)
    _finalize_prepared_test_command(prepared, result, project_root, scheduling_notices)
    return result


def _run_parallel_prepared_commands(
    commands: list[tuple[PreparedPytestCommand, str]],
    project_root: Path,
    jobs: int,
    scheduling_notices: list[TestSchedulingNotice],
) -> list[TestRunResult]:
    max_workers = min(jobs, len(commands))
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = [
            executor.submit(_run_prepared_test_command, prepared, project_root, slug)
            for prepared, slug in commands
        ]
        results = [future.result() for future in futures]
    for (prepared, _), result in zip(commands, results):
        _finalize_prepared_test_command(
            prepared, result, project_root, scheduling_notices
        )
    return results


def _run_parallel_test_commands(
    commands: list[tuple[tuple[str, ...], str]],
    project_root: Path,
    jobs: int,
) -> list[TestRunResult]:
    if not commands:
        return []

    max_workers = min(jobs, len(commands))
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = [
            executor.submit(run_command, cmd, cwd=project_root, manifest_slug=slug)
            for cmd, slug in commands
        ]
        return [future.result() for future in futures]


def _positive_jobs_arg(value: str) -> int:
    try:
        jobs = int(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError("jobs must be a positive integer") from exc
    if jobs < 1:
        raise argparse.ArgumentTypeError("jobs must be a positive integer")
    return jobs


def _validate_manifest_test_command_integrity(
    manifests: Iterable[Manifest],
    project_root: Path,
) -> list[ValidationError]:
    from maid_runner.core._validation_test_artifacts import (
        validate_manifest_test_commands,
    )

    errors = []
    for manifest in manifests:
        path_errors = validate_manifest_paths(manifest, project_root)
        if path_errors:
            errors.extend(path_errors)
            continue
        errors.extend(validate_manifest_test_commands(manifest, project_root))
    return errors
