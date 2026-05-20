"""Test execution for MAID Runner v2."""

from __future__ import annotations

import os
import subprocess
import time
from collections.abc import Iterable
from pathlib import Path
from typing import Union

from maid_runner.core.chain import ManifestChain
from maid_runner.core._pytest_command_normalization import (
    _is_python_command as _normalization_is_python_command,
)
from maid_runner.core._maid_validate_command_cache import (
    _run_cached_maid_validate_command,
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
    env = _test_command_environment()
    start = time.monotonic()
    try:
        proc = subprocess.run(
            command,
            capture_output=True,
            text=True,
            cwd=str(cwd),
            timeout=timeout,
            env=env,
        )
        duration = (time.monotonic() - start) * 1000
        return TestRunResult(
            manifest_slug=manifest_slug,
            command=command,
            exit_code=proc.returncode,
            stdout=proc.stdout,
            stderr=proc.stderr,
            duration_ms=duration,
            stream=stream,
        )
    except subprocess.TimeoutExpired:
        duration = (time.monotonic() - start) * 1000
        return TestRunResult(
            manifest_slug=manifest_slug,
            command=command,
            exit_code=-1,
            stdout="",
            stderr=f"Command timed out after {timeout}s",
            duration_ms=duration,
            stream=stream,
        )
    except Exception as e:
        duration = (time.monotonic() - start) * 1000
        return TestRunResult(
            manifest_slug=manifest_slug,
            command=command,
            exit_code=-2,
            stdout="",
            stderr=str(e),
            duration_ms=duration,
            stream=stream,
        )


def _test_command_environment() -> dict[str, str]:
    env = dict(os.environ)
    env.pop("PYTEST_ADDOPTS", None)
    return env


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

    # Stream 1: Acceptance tests (run first)
    if manifest.acceptance is not None:
        for cmd in manifest.acceptance.tests:
            result = run_command(
                cmd,
                cwd=project_root,
                manifest_slug=manifest.slug,
                stream=TestStream.ACCEPTANCE,
            )
            results.append(result)
            if result.success:
                passed += 1
            else:
                failed += 1
                if fail_fast:
                    return BatchTestResult(
                        results=results,
                        total=len(results),
                        passed=passed,
                        failed=failed,
                    )

    # Stream 3: Implementation tests
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
) -> BatchTestResult:
    project_root = Path(project_root)
    chain_dir = project_root / manifest_dir

    if not chain_dir.exists():
        return BatchTestResult(results=[], total=0, passed=0, failed=0)

    chain = ManifestChain(chain_dir, project_root)
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

    # Collect all commands with stream tags
    all_commands: list[tuple[tuple[str, ...], str, TestStream]] = []
    for manifest in active:
        # Stream 1: Acceptance tests first
        if manifest.acceptance is not None:
            for cmd in manifest.acceptance.tests:
                all_commands.append((cmd, manifest.slug, TestStream.ACCEPTANCE))
        # Stream 3: Implementation tests
        for cmd in manifest.validate_commands:
            all_commands.append((cmd, manifest.slug, TestStream.IMPLEMENTATION))

    # Split acceptance and implementation commands
    acceptance_commands = [
        (cmd, slug)
        for cmd, slug, stream in all_commands
        if stream == TestStream.ACCEPTANCE
    ]
    impl_commands_with_slug = [
        (cmd, slug)
        for cmd, slug, stream in all_commands
        if stream == TestStream.IMPLEMENTATION
    ]

    results: list[TestRunResult] = []
    passed = 0
    failed = 0
    maid_validate_cache: dict[str, object] = {}

    # Stream 1: Run acceptance tests sequentially first
    for cmd, slug in acceptance_commands:
        result = run_command(
            cmd, cwd=project_root, manifest_slug=slug, stream=TestStream.ACCEPTANCE
        )
        results.append(result)
        if result.success:
            passed += 1
        else:
            failed += 1
            if fail_fast:
                return BatchTestResult(
                    results=results,
                    total=len(results),
                    passed=passed,
                    failed=failed,
                    chain_errors=chain_errors,
                )

    # Stream 3: Run implementation tests (batched or sequential)
    sequential_impl_commands = impl_commands_with_slug
    if batch is not False:
        impl_commands_with_slug = _prune_covered_pytest_commands(
            _dedupe_commands(
                impl_commands_with_slug,
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
        sequential_impl_commands = []
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
            result = run_command(batched_cmd, cwd=project_root, manifest_slug="batch")
            results.append(result)
            if result.success:
                passed += 1
            else:
                failed += 1
                if fail_fast:
                    return BatchTestResult(
                        results=results,
                        total=len(results),
                        passed=passed,
                        failed=failed,
                        chain_errors=chain_errors,
                    )

    for cmd, slug in sequential_impl_commands:
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
                return BatchTestResult(
                    results=results,
                    total=len(results),
                    passed=passed,
                    failed=failed,
                    chain_errors=chain_errors,
                )

    return BatchTestResult(
        results=results,
        total=len(results),
        passed=passed,
        failed=failed,
        chain_errors=chain_errors,
    )


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
