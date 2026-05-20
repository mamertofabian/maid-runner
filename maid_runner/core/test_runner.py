"""Test execution for MAID Runner v2."""

from __future__ import annotations

import os
import subprocess
import time
from collections.abc import Iterable
from pathlib import Path, PurePosixPath
from typing import Union

from maid_runner.core.chain import ManifestChain
from maid_runner.core._pytest_command_normalization import (
    _has_non_combinable_pytest_options,
    _is_python_command as _normalization_is_python_command,
    _looks_like_pytest_invocation,
    _normalize_pytest_command,
    _pytest_behavior_options,
)
from maid_runner.core.manifest import load_manifest, validate_manifest_paths
from maid_runner.core.result import (
    BatchTestResult,
    Severity,
    TestRunResult,
    ValidationError,
)
from maid_runner.core.types import Manifest, TestStream


_SAFE_VITEST_VALUE_FLAGS = frozenset(
    {
        "--config",
        "-c",
        "--environment",
        "--pool",
        "--reporter",
        "--testNamePattern",
        "-t",
    }
)
_SAFE_VITEST_STANDALONE_FLAGS = frozenset(
    {
        "--passWithNoTests",
        "--runInBand",
        "--silent",
    }
)


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
    """Check if all commands use pytest and can be batched."""
    if not commands:
        return False
    group_keys = [_batch_group_key(cmd) for cmd in commands]
    if any(item is None for item in group_keys):
        return False
    return len(set(group_keys)) == 1


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


def _normalize_vitest_command(
    command: tuple[str, ...],
) -> tuple[tuple[str, ...], tuple[str, ...], tuple[str, ...]] | None:
    """Normalize simple Vitest run invocations for safe batching."""
    if not command:
        return None

    if len(command) >= 3 and command[:3] == ("npx", "vitest", "run"):
        prefix = command[:3]
        args = command[3:]
    elif len(command) >= 2 and command[:2] == ("vitest", "run"):
        prefix = command[:2]
        args = command[2:]
    else:
        return None

    targets: list[str] = []
    options: list[str] = []
    idx = 0
    while idx < len(args):
        part = args[idx]
        if part.startswith("-"):
            if "=" in part:
                flag, value = part.split("=", 1)
                if flag not in _SAFE_VITEST_VALUE_FLAGS or not value:
                    return None
                options.append(part)
                idx += 1
                continue
            if part in _SAFE_VITEST_VALUE_FLAGS:
                if idx + 1 >= len(args):
                    return None
                options.append(part)
                options.append(args[idx + 1])
                idx += 2
                continue
            if part in _SAFE_VITEST_STANDALONE_FLAGS:
                options.append(part)
                idx += 1
                continue
            return None
        targets.append(part)
        idx += 1

    if not targets:
        return None

    return prefix, tuple(targets), tuple(options)


def _normalize_batchable_test_command(
    command: tuple[str, ...],
) -> tuple[tuple[str, ...], tuple[str, ...], tuple[str, ...]] | None:
    return _normalize_pytest_command(command) or _normalize_vitest_command(command)


def _batch_group_key(
    command: tuple[str, ...],
    *,
    cwd: Union[str, Path] = ".",
) -> tuple[str, tuple[str, ...], tuple[str, ...]] | None:
    resolved_command = _resolve_command(command, cwd=cwd)
    pytest_command = _normalize_pytest_command(resolved_command)
    if pytest_command is not None:
        prefix, _, options = pytest_command
        if _has_non_combinable_pytest_options(options):
            return None
        return (
            "pytest",
            _pytest_runner_group_prefix(prefix, cwd=cwd),
            _pytest_behavior_options(options),
        )

    vitest_command = _normalize_vitest_command(resolved_command)
    if vitest_command is not None:
        prefix, _, options = vitest_command
        return ("vitest", prefix, options)

    return None


def _pytest_runner_group_prefix(
    prefix: tuple[str, ...],
    *,
    cwd: Union[str, Path] = ".",
) -> tuple[str, ...]:
    wrapper: tuple[str, ...] = ()
    inner = prefix
    if prefix[:2] == ("uv", "run"):
        wrapper = prefix[:2]
        inner = prefix[2:]

    if (
        wrapper
        and _is_uv_project(cwd)
        and inner
        in {
            ("pytest",),
            ("python", "-m", "pytest"),
        }
    ):
        return wrapper + ("pytest",)

    return prefix


def _batch_test_commands(commands: list[tuple[str, ...]]) -> tuple[str, ...]:
    normalized = [_normalize_batchable_test_command(cmd) for cmd in commands]
    if any(item is None for item in normalized):
        raise ValueError("Cannot batch non-equivalent test commands")

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


def _batch_compatible_test_commands(
    commands: list[tuple[str, ...]],
    *,
    cwd: Union[str, Path] = ".",
) -> tuple[str, ...]:
    pytest_commands = [_normalize_pytest_command(cmd) for cmd in commands]
    if all(item is not None for item in pytest_commands):
        return _batch_compatible_pytest_commands(commands, cwd=cwd)
    return _batch_test_commands(commands)


def _batch_compatible_pytest_commands(
    commands: list[tuple[str, ...]],
    *,
    cwd: Union[str, Path] = ".",
) -> tuple[str, ...]:
    normalized = [_normalize_pytest_command(cmd) for cmd in commands]
    if any(item is None for item in normalized):
        raise ValueError("Cannot batch non-pytest commands")
    group_keys = [_batch_group_key(cmd, cwd=cwd) for cmd in commands]
    if any(item is None for item in group_keys) or len(set(group_keys)) != 1:
        raise ValueError("Cannot batch pytest commands with different runners")

    assert normalized[0] is not None
    prefix, _, first_options = normalized[0]
    behavior_options = _pytest_behavior_options(first_options)
    test_files: list[str] = []
    seen: set[str] = set()
    option_sets: set[tuple[str, ...]] = set()

    for item in normalized:
        assert item is not None
        _, targets, options = item
        if _pytest_behavior_options(options) != behavior_options:
            raise ValueError("Cannot batch pytest commands with different options")
        option_sets.add(options)
        for part in targets:
            if part not in seen:
                seen.add(part)
                test_files.append(part)

    options = first_options if len(option_sets) == 1 else behavior_options
    return prefix + tuple(test_files) + options


def _run_cached_maid_validate_command(
    command: tuple[str, ...],
    *,
    cwd: Union[str, Path],
    manifest_slug: str,
    stream: TestStream,
    cache: dict[str, object],
) -> TestRunResult | None:
    parsed = _parse_maid_validate_command(command)
    if parsed is None:
        return None

    from maid_runner.cli.commands._format import (
        format_batch_result,
        format_validation_result,
    )
    from maid_runner.core.validate import ValidationEngine

    project_root = Path(cwd)
    resolved_command = _resolve_command(command, cwd=project_root)
    start = time.monotonic()

    try:
        engine = cache.get("engine")
        if engine is None:
            engine = ValidationEngine(project_root=project_root)
            cache["engine"] = engine

        mode = parsed["mode"]
        manifest_dir = parsed["manifest_dir"]
        json_mode = parsed["json_mode"]
        manifest_path = parsed["manifest_path"]
        use_chain = parsed["use_chain"]

        if manifest_path is None:
            result = engine.validate_all(manifest_dir, mode=mode)
            stdout = format_batch_result(result, json_mode=json_mode)
            success = result.success
        else:
            chain = None
            if use_chain:
                chain_key = f"chain:{manifest_dir}"
                chain_dir = project_root / manifest_dir
                if chain_dir.exists():
                    chain = cache.get(chain_key)
                    if chain is None:
                        chain = ManifestChain(chain_dir, project_root)
                        cache[chain_key] = chain
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
            stdout = format_validation_result(result, json_mode=json_mode)
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

    from maid_runner.core.types import ValidationMode

    mode = ValidationMode.IMPLEMENTATION
    manifest_dir = "manifests/"
    json_mode = False
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
        "use_chain": use_chain,
        "manifest_path": manifest_path,
    }


def _dedupe_commands(
    commands: list[tuple[tuple[str, ...], str]],
    *,
    cwd: Union[str, Path] = ".",
) -> list[tuple[tuple[str, ...], str]]:
    seen: set[tuple[str, ...]] = set()
    deduped: list[tuple[tuple[str, ...], str]] = []
    for cmd, slug in commands:
        can_dedupe = _can_dedupe_command(cmd, cwd=cwd)
        if can_dedupe and cmd in seen:
            continue
        if can_dedupe:
            seen.add(cmd)
        deduped.append((cmd, slug))
    return deduped


def _can_dedupe_command(command: tuple[str, ...], *, cwd: Union[str, Path]) -> bool:
    resolved_command = _resolve_command(command, cwd=cwd)
    pytest_command = _normalize_pytest_command(resolved_command)
    if pytest_command is None:
        return not _looks_like_pytest_invocation(resolved_command)
    _, _, options = pytest_command
    return not _has_non_combinable_pytest_options(options)


def _prune_covered_pytest_commands(
    commands: list[tuple[tuple[str, ...], str]],
    *,
    cwd: Union[str, Path] = ".",
) -> list[tuple[tuple[str, ...], str]]:
    normalized_by_index: dict[
        int, tuple[tuple[str, ...], tuple[str, ...], tuple[str, ...]]
    ] = {}
    group_key_by_index: dict[int, tuple[str, tuple[str, ...], tuple[str, ...]]] = {}
    target_order_by_group: dict[
        tuple[str, tuple[str, ...], tuple[str, ...]], list[tuple[int, str]]
    ] = {}

    for index, (cmd, _) in enumerate(commands):
        normalized = _normalize_pytest_command(cmd)
        if normalized is None:
            continue
        group_key = _batch_group_key(cmd, cwd=cwd)
        if group_key is None:
            continue
        normalized_by_index[index] = normalized
        group_key_by_index[index] = group_key
        _, targets, _ = normalized
        for target in targets:
            group_targets = target_order_by_group.setdefault(group_key, [])
            group_targets.append((len(group_targets), target))

    if not target_order_by_group:
        return commands

    pruned: list[tuple[tuple[str, ...], str]] = []
    target_position_by_group: dict[
        tuple[str, tuple[str, ...], tuple[str, ...]], int
    ] = {}
    for index, (cmd, slug) in enumerate(commands):
        normalized = normalized_by_index.get(index)
        if normalized is None:
            pruned.append((cmd, slug))
            continue

        group_key = group_key_by_index[index]
        target_order = target_order_by_group[group_key]
        current_order = target_position_by_group.get(group_key, 0)
        prefix, targets, options = normalized
        kept_targets: list[str] = []
        for target in targets:
            if not _is_pytest_target_redundant(
                current_order,
                target,
                target_order,
            ):
                kept_targets.append(target)
            current_order += 1
        target_position_by_group[group_key] = current_order

        if kept_targets:
            pruned.append((prefix + tuple(kept_targets) + options, slug))

    return pruned


def _is_pytest_target_redundant(
    current_order: int,
    target: str,
    target_order: list[tuple[int, str]],
) -> bool:
    if _is_pytest_directory_target(target):
        for other_order, other_target in target_order:
            if other_order == current_order:
                continue
            if other_target == target:
                return other_order < current_order
            if _pytest_target_covers(target, other_target):
                return True
        return False

    for other_order, other_target in target_order:
        if other_order == current_order:
            continue
        if other_target == target:
            return other_order < current_order
        if _pytest_target_covers(
            other_target, target
        ) and not _is_pytest_directory_target(other_target):
            return True
    return False


def _pytest_target_covers(covering: str, target: str) -> bool:
    covering_path, covering_nodeid = _split_pytest_target(covering)
    target_path, _ = _split_pytest_target(target)

    if covering_nodeid:
        return covering == target
    if covering_path == target_path:
        return True
    if _is_directory_pytest_target(covering_path, covering):
        return target_path.startswith(f"{covering_path}/")
    return False


def _split_pytest_target(target: str) -> tuple[str, str]:
    path, _, nodeid = target.partition("::")
    return path.rstrip("/"), nodeid


def _is_directory_pytest_target(path: str, original_target: str) -> bool:
    if "::" in original_target:
        return False
    if original_target.endswith("/"):
        return True
    return PurePosixPath(path).suffix == ""


def _is_pytest_directory_target(target: str) -> bool:
    path, _ = _split_pytest_target(target)
    return _is_directory_pytest_target(path, target)


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
            _dedupe_commands(impl_commands_with_slug, cwd=project_root),
            cwd=project_root,
        )
        batch_groups: dict[
            tuple[tuple[str, ...], tuple[str, ...]],
            list[tuple[tuple[str, ...], str]],
        ] = {}
        sequential_impl_commands = []
        for cmd, slug in impl_commands_with_slug:
            group_key = _batch_group_key(cmd, cwd=project_root)
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
