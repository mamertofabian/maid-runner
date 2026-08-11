"""Subprocess execution for resolved maid test commands."""

from __future__ import annotations

import os
import subprocess
import threading
import time
from collections.abc import Mapping
from contextlib import contextmanager
from contextvars import ContextVar
from pathlib import Path
from typing import Iterator, Union

from maid_runner.core.result import TestRunResult
from maid_runner.core.types import TestStream


_strict_validation_for_tests: ContextVar[bool] = ContextVar(
    "maid_strict_validation_for_tests",
    default=False,
)
_strict_validation_process_lock = threading.Lock()
_strict_validation_process_depth = 0


@contextmanager
def _strict_validation_test_environment(
    enabled: bool,
    *,
    process_wide: bool = False,
) -> Iterator[None]:
    global _strict_validation_process_depth

    context_token = _strict_validation_for_tests.set(enabled)
    if enabled and process_wide:
        with _strict_validation_process_lock:
            _strict_validation_process_depth += 1
    try:
        yield
    finally:
        if enabled and process_wide:
            with _strict_validation_process_lock:
                _strict_validation_process_depth -= 1
        _strict_validation_for_tests.reset(context_token)


def _inherited_strict_validation() -> bool:
    if _strict_validation_for_tests.get():
        return True
    with _strict_validation_process_lock:
        return _strict_validation_process_depth > 0


def _strict_validation_test_active() -> bool:
    return _inherited_strict_validation()


def _run_test_command(
    command: tuple[str, ...],
    *,
    cwd: Union[str, Path] = ".",
    timeout: int = 300,
    manifest_slug: str = "",
    stream: TestStream = TestStream.IMPLEMENTATION,
    environment_overrides: Mapping[str, str] | None = None,
) -> TestRunResult:
    env = _test_command_environment()
    if environment_overrides:
        env.update(environment_overrides)
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
