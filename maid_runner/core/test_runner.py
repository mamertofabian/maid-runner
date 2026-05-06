"""Test execution for MAID Runner v2."""

from __future__ import annotations

import subprocess
import time
from pathlib import Path
from typing import Union

from maid_runner.core.chain import ManifestChain
from maid_runner.core.manifest import load_manifest
from maid_runner.core.result import BatchTestResult, Severity, TestRunResult
from maid_runner.core.types import TestStream


_PYTHON_COMMANDS = frozenset({"pytest", "python", "python3", "py.test"})
_SAFE_PYTEST_FLAGS = frozenset(
    {
        "-q",
        "-qq",
        "-v",
        "-vv",
        "-vvv",
        "-s",
        "-x",
        "--lf",
        "--ff",
        "--maxfail",
    }
)


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
    normalized = [_normalize_pytest_command(cmd) for cmd in commands]
    if any(item is None for item in normalized):
        return False
    assert normalized[0] is not None
    base_prefix, _, base_options = normalized[0]
    return all(
        item is not None and item[0] == base_prefix and item[2] == base_options
        for item in normalized
    )


def _batch_pytest(commands: list[tuple[str, ...]]) -> tuple[str, ...]:
    """Combine multiple pytest commands into a single invocation.

    Returns the raw command tuple — caller (run_command) handles uv resolution.
    """
    normalized = [_normalize_pytest_command(cmd) for cmd in commands]
    if any(item is None for item in normalized):
        raise ValueError("Cannot batch non-equivalent pytest commands")

    assert normalized[0] is not None
    prefix, _, options = normalized[0]
    test_files: list[str] = []
    seen: set[str] = set()
    for item in normalized:
        assert item is not None
        _, targets, _ = item
        for part in targets:
            if part not in seen:
                seen.add(part)
                test_files.append(part)
    return prefix + tuple(test_files) + options


def _normalize_pytest_command(
    command: tuple[str, ...],
) -> tuple[tuple[str, ...], tuple[str, ...], tuple[str, ...]] | None:
    """Normalize simple pytest invocations for safe batching.

    Only batches commands when we can preserve semantics exactly:
    direct ``pytest`` or ``python -m pytest`` invocations, explicit test file
    targets, and only simple standalone flags or ``--opt=value`` style options.
    """
    if not command:
        return None

    wrapper: tuple[str, ...] = ()
    inner = command
    if len(command) >= 3 and command[0] == "uv" and command[1] == "run":
        wrapper = command[:2]
        inner = command[2:]

    prefix: tuple[str, ...]
    args: tuple[str, ...]
    if inner[0] == "pytest":
        prefix = wrapper + ("pytest",)
        args = inner[1:]
    elif (
        len(inner) >= 3
        and _is_python_command(inner[0])
        and inner[1] == "-m"
        and inner[2] == "pytest"
    ):
        prefix = wrapper + inner[:3]
        args = inner[3:]
    else:
        return None

    targets: list[str] = []
    options: list[str] = []
    idx = 0
    while idx < len(args):
        part = args[idx]
        if part.startswith("-"):
            if "=" in part:
                options.append(part)
                idx += 1
                continue
            if part not in _SAFE_PYTEST_FLAGS:
                return None
            options.append(part)
            if part == "--maxfail":
                if idx + 1 >= len(args):
                    return None
                options.append(args[idx + 1])
                idx += 2
                continue
            idx += 1
            continue
        targets.append(part)
        idx += 1

    if not targets:
        return None

    return prefix, tuple(targets), tuple(options)


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
        batch_groups: dict[
            tuple[tuple[str, ...], tuple[str, ...]],
            list[tuple[tuple[str, ...], str]],
        ] = {}
        sequential_impl_commands = []
        for cmd, slug in impl_commands_with_slug:
            normalized = _normalize_pytest_command(cmd)
            if normalized is None:
                sequential_impl_commands.append((cmd, slug))
                continue
            prefix, _, options = normalized
            batch_groups.setdefault((prefix, options), []).append((cmd, slug))

        for group in batch_groups.values():
            if len(group) <= 1:
                sequential_impl_commands.extend(group)
                continue
            batched_cmd = _batch_pytest([cmd for cmd, _ in group])
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
