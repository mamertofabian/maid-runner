"""Test execution for MAID Runner v2."""

from __future__ import annotations

import subprocess
import time
from pathlib import Path
from typing import Union

from maid_runner.core.chain import ManifestChain
from maid_runner.core.manifest import load_manifest
from maid_runner.core.result import BatchTestResult, TestRunResult
from maid_runner.core.types import TestStream


_PYTHON_COMMANDS = frozenset({"pytest", "python", "python3", "py.test"})


def _is_python_command(cmd: str) -> bool:
    """Check if a command is a Python ecosystem command."""
    if cmd in _PYTHON_COMMANDS:
        return True
    # Versioned interpreters: python3.12, python3.11, etc.
    if cmd.startswith("python3."):
        return True
    return False


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
    start = time.monotonic()
    try:
        proc = subprocess.run(
            command,
            capture_output=True,
            text=True,
            cwd=str(cwd),
            timeout=timeout,
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


def run_manifest_tests(
    manifest_path: Union[str, Path],
    *,
    fail_fast: bool = False,
    project_root: Union[str, Path] = ".",
) -> BatchTestResult:
    manifest = load_manifest(manifest_path)
    project_root = Path(project_root)

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
    """Check if all commands use pytest and can be batched."""
    if not commands:
        return False
    return all(
        _is_python_command(cmd[0]) and "pytest" in " ".join(cmd) for cmd in commands
    )


def _batch_pytest(commands: list[tuple[str, ...]]) -> tuple[str, ...]:
    """Combine multiple pytest commands into a single invocation.

    Returns the raw command tuple — caller (run_command) handles uv resolution.
    """
    test_files: list[str] = []
    seen: set[str] = set()
    for cmd in commands:
        for part in cmd:
            if part.endswith(".py") and part not in seen:
                seen.add(part)
                test_files.append(part)
    return ("pytest",) + tuple(test_files) + ("-v",)


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
    active = chain.active_manifests()

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
    impl_commands = [cmd for cmd, _ in impl_commands_with_slug]

    # Determine batching (only for implementation commands)
    should_batch = batch if batch is not None else _can_batch(impl_commands)

    results: list[TestRunResult] = []
    passed = 0
    failed = 0

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
                )

    # Stream 3: Run implementation tests (batched or sequential)
    if should_batch and _can_batch(impl_commands) and len(impl_commands) > 1:
        batched_cmd = _batch_pytest(impl_commands)
        result = run_command(batched_cmd, cwd=project_root, manifest_slug="batch")
        results.append(result)
        if result.success:
            passed += 1
        else:
            failed += 1
    else:
        for cmd, slug in impl_commands_with_slug:
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
                    )

    return BatchTestResult(
        results=results,
        total=len(results),
        passed=passed,
        failed=failed,
    )
