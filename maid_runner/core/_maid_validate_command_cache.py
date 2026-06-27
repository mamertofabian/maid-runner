"""In-process execution for cacheable maid validate commands."""

from __future__ import annotations

import time
from collections.abc import Callable
from pathlib import Path
from typing import Union

from maid_runner.core.chain import (
    _enter_manifest_chain_cache_scope,
    _exit_manifest_chain_cache_scope,
    get_cached_manifest_chain,
)
from maid_runner.core.result import TestRunResult
from maid_runner.core.types import TestStream, ValidationMode


_CommandResolver = Callable[..., tuple[str, ...]]


def _identity_resolve_command(
    command: tuple[str, ...], *, cwd: Union[str, Path] = "."
) -> tuple[str, ...]:
    return command


def _run_cached_maid_validate_command(
    command: tuple[str, ...],
    *,
    cwd: Union[str, Path],
    manifest_slug: str,
    stream: TestStream,
    cache: dict[str, object],
    resolve_command: _CommandResolver = _identity_resolve_command,
) -> TestRunResult | None:
    parsed = _parse_maid_validate_command(command)
    if parsed is None:
        return None

    chain_outermost = _enter_manifest_chain_cache_scope()
    try:
        return _run_cached_maid_validate_command_in_scope(
            command,
            cwd=cwd,
            manifest_slug=manifest_slug,
            stream=stream,
            cache=cache,
            resolve_command=resolve_command,
            parsed=parsed,
        )
    finally:
        _exit_manifest_chain_cache_scope(chain_outermost)


def _run_cached_maid_validate_command_in_scope(
    command: tuple[str, ...],
    *,
    cwd: Union[str, Path],
    manifest_slug: str,
    stream: TestStream,
    cache: dict[str, object],
    resolve_command: _CommandResolver,
    parsed: dict[str, object],
) -> TestRunResult:

    from maid_runner.cli.commands._format import (
        format_batch_result,
        format_validation_result,
    )
    from maid_runner.core.validate import ValidationEngine

    project_root = Path(cwd)
    resolved_command = resolve_command(command, cwd=project_root)
    start = time.monotonic()

    try:
        engine = cache.get("engine")
        if engine is None:
            engine = ValidationEngine(project_root=project_root)
            cache["engine"] = engine

        mode = parsed["mode"]
        manifest_dir = parsed["manifest_dir"]
        json_mode = parsed["json_mode"]
        quiet = parsed["quiet"]
        manifest_path = parsed["manifest_path"]
        use_chain = parsed["use_chain"]

        if manifest_path is None:
            result = engine.validate_all(manifest_dir, mode=mode)
            stdout = format_batch_result(result, json_mode=json_mode, quiet=quiet)
            if quiet and not json_mode and stdout == "":
                stdout = "\n"
            success = result.success
        else:
            chain = None
            if use_chain:
                chain_dir = project_root / manifest_dir
                if chain_dir.exists():
                    chain = get_cached_manifest_chain(chain_dir, project_root)
            manifest_to_validate = Path(manifest_path)
            if not manifest_to_validate.is_absolute():
                manifest_to_validate = project_root / manifest_to_validate
            result = engine.validate(
                manifest_to_validate,
                mode=mode,
                use_chain=use_chain,
                chain=chain,
                manifest_dir=manifest_dir,
            )
            stdout = format_validation_result(result, json_mode=json_mode, quiet=quiet)
            success = result.success

        return TestRunResult(
            manifest_slug=manifest_slug,
            command=resolved_command,
            exit_code=0 if success else 1,
            stdout=stdout,
            stderr="",
            duration_ms=(time.monotonic() - start) * 1000,
            stream=stream,
        )
    except Exception as exc:
        return TestRunResult(
            manifest_slug=manifest_slug,
            command=resolved_command,
            exit_code=-2,
            stdout="",
            stderr=str(exc),
            duration_ms=(time.monotonic() - start) * 1000,
            stream=stream,
        )


def _parse_maid_validate_command(command: tuple[str, ...]) -> dict[str, object] | None:
    if not command:
        return None

    inner = command
    if len(inner) >= 3 and inner[0] == "uv" and inner[1] == "run":
        inner = inner[2:]
    if len(inner) < 2 or inner[:2] != ("maid", "validate"):
        return None

    mode = ValidationMode.IMPLEMENTATION
    manifest_dir = "manifests/"
    json_mode = False
    quiet = False
    use_chain = True
    manifest_path: str | None = None

    args = inner[2:]
    index = 0
    while index < len(args):
        part = args[index]
        if part == "--mode":
            if index + 1 >= len(args):
                return None
            try:
                mode = ValidationMode(args[index + 1])
            except ValueError:
                return None
            index += 2
            continue
        if part.startswith("--mode="):
            try:
                mode = ValidationMode(part.split("=", 1)[1])
            except ValueError:
                return None
            index += 1
            continue
        if part == "--manifest-dir":
            if index + 1 >= len(args):
                return None
            manifest_dir = args[index + 1]
            index += 2
            continue
        if part.startswith("--manifest-dir="):
            manifest_dir = part.split("=", 1)[1]
            index += 1
            continue
        if part == "--json":
            json_mode = True
            index += 1
            continue
        if part == "--quiet":
            quiet = True
            index += 1
            continue
        if part == "--no-chain":
            use_chain = False
            index += 1
            continue
        if part.startswith("-"):
            return None
        if manifest_path is not None:
            return None
        manifest_path = part
        index += 1

    return {
        "mode": mode,
        "manifest_dir": manifest_dir,
        "json_mode": json_mode,
        "quiet": quiet,
        "use_chain": use_chain,
        "manifest_path": manifest_path,
    }
