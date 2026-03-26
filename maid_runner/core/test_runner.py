"""Test execution for MAID Runner v2."""

from __future__ import annotations

import subprocess
import time
from pathlib import Path
from typing import Union

from maid_runner.core.chain import ManifestChain
from maid_runner.core.manifest import load_manifest
from maid_runner.core.result import BatchTestResult, TestRunResult


def run_command(
    command: tuple[str, ...],
    *,
    cwd: Union[str, Path] = ".",
    timeout: int = 300,
    manifest_slug: str = "",
) -> TestRunResult:
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
        cmd[0] in ("pytest", "python") and "pytest" in " ".join(cmd) for cmd in commands
    )


def _batch_pytest(commands: list[tuple[str, ...]]) -> tuple[str, ...]:
    """Combine multiple pytest commands into a single invocation."""
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

    # Collect all commands
    all_commands: list[tuple[tuple[str, ...], str]] = []
    for manifest in active:
        for cmd in manifest.validate_commands:
            all_commands.append((cmd, manifest.slug))

    # Determine batching
    commands_only = [cmd for cmd, _ in all_commands]
    should_batch = batch if batch is not None else _can_batch(commands_only)

    if should_batch and _can_batch(commands_only) and len(commands_only) > 1:
        batched_cmd = _batch_pytest(commands_only)
        result = run_command(batched_cmd, cwd=project_root, manifest_slug="batch")
        if result.success:
            return BatchTestResult(results=[result], total=1, passed=1, failed=0)
        else:
            return BatchTestResult(results=[result], total=1, passed=0, failed=1)

    # Sequential execution
    results: list[TestRunResult] = []
    passed = 0
    failed = 0

    for cmd, slug in all_commands:
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
