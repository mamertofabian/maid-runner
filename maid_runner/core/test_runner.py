"""Test execution for MAID Runner v2."""

from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor
from collections.abc import Iterable
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
from maid_runner.core._maid_validate_command_cache import (
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
) -> TestRunResult:
    command = _resolve_command(command, cwd=cwd)
    return _run_test_command(
        command,
        cwd=cwd,
        timeout=timeout,
        manifest_slug=manifest_slug,
        stream=stream,
    )


def _test_command_environment() -> dict[str, str]:
    return _execution_test_command_environment()


def run_manifest_tests(
    manifest_path: Union[str, Path],
    *,
    fail_fast: bool = False,
    project_root: Union[str, Path] = ".",
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

    for cmd in manifest.validate_commands:
        result = run_command(cmd, cwd=project_root, manifest_slug=manifest.slug)
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
) -> BatchTestResult:
    chain_outermost = _enter_manifest_chain_cache_scope()
    try:
        return _run_tests_cached(
            manifest_dir=manifest_dir,
            fail_fast=fail_fast,
            project_root=project_root,
            batch=batch,
            jobs=jobs,
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
    )
    if early_result is not None:
        return early_result

    return BatchTestResult(
        results=results,
        total=len(results),
        passed=passed,
        failed=failed,
        chain_errors=chain_errors,
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
) -> tuple[list[TestRunResult], int, int, BatchTestResult | None]:
    results = list(previous_results)
    passed = previous_passed
    failed = previous_failed
    maid_validate_cache: dict[str, object] = {}
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
        pending_external_commands: list[tuple[tuple[str, ...], str]] = []

        def flush_external_commands() -> None:
            nonlocal passed, failed
            if not pending_external_commands:
                return
            parallel_results = _run_parallel_test_commands(
                pending_external_commands,
                project_root,
                jobs,
            )
            results.extend(parallel_results)
            passed += sum(1 for result in parallel_results if result.success)
            failed += sum(1 for result in parallel_results if not result.success)
            pending_external_commands.clear()

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
                pending_external_commands.append((cmd, slug))
                continue

            flush_external_commands()
            results.append(result)
            if result.success:
                passed += 1
            else:
                failed += 1

        flush_external_commands()
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
            result = run_command(cmd, cwd=project_root, manifest_slug=slug)
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
