"""Batching decisions for maid test commands."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path, PurePosixPath
from typing import Union

from maid_runner.core._pytest_command_normalization import (
    _has_non_combinable_pytest_options,
    _looks_like_pytest_invocation,
    _normalize_pytest_command,
    _pytest_behavior_options,
)
from maid_runner.core._vitest_command_normalization import _normalize_vitest_command


_CommandResolver = Callable[..., tuple[str, ...]]
_UvProjectPredicate = Callable[[Union[str, Path]], bool]


def _identity_resolve_command(
    command: tuple[str, ...], *, cwd: Union[str, Path] = "."
) -> tuple[str, ...]:
    return command


def _not_uv_project(cwd: Union[str, Path]) -> bool:
    return False


def _can_batch(
    commands: list[tuple[str, ...]],
    *,
    cwd: Union[str, Path] = ".",
    resolve_command: _CommandResolver = _identity_resolve_command,
    is_uv_project: _UvProjectPredicate = _not_uv_project,
) -> bool:
    """Check if all commands use a compatible test runner and can be batched."""
    if not commands:
        return False
    group_keys = [
        _batch_group_key(
            cmd,
            cwd=cwd,
            resolve_command=resolve_command,
            is_uv_project=is_uv_project,
        )
        for cmd in commands
    ]
    if any(item is None for item in group_keys):
        return False
    return len(set(group_keys)) == 1


def _batch_pytest(commands: list[tuple[str, ...]]) -> tuple[str, ...]:
    """Combine multiple pytest commands into a single invocation.

    Returns the raw command tuple — caller handles command resolution.
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


def _normalize_batchable_test_command(
    command: tuple[str, ...],
) -> tuple[tuple[str, ...], tuple[str, ...], tuple[str, ...]] | None:
    return _normalize_pytest_command(command) or _normalize_vitest_command(command)


def _batch_group_key(
    command: tuple[str, ...],
    *,
    cwd: Union[str, Path] = ".",
    resolve_command: _CommandResolver = _identity_resolve_command,
    is_uv_project: _UvProjectPredicate = _not_uv_project,
) -> tuple[str, tuple[str, ...], tuple[str, ...]] | None:
    resolved_command = resolve_command(command, cwd=cwd)
    pytest_command = _normalize_pytest_command(resolved_command)
    if pytest_command is not None:
        prefix, _, options = pytest_command
        if _has_non_combinable_pytest_options(options):
            return None
        return (
            "pytest",
            _pytest_runner_group_prefix(prefix, cwd=cwd, is_uv_project=is_uv_project),
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
    is_uv_project: _UvProjectPredicate = _not_uv_project,
) -> tuple[str, ...]:
    wrapper: tuple[str, ...] = ()
    inner = prefix
    if prefix[:2] == ("uv", "run"):
        wrapper = prefix[:2]
        inner = prefix[2:]

    if (
        wrapper
        and is_uv_project(cwd)
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
    resolve_command: _CommandResolver = _identity_resolve_command,
    is_uv_project: _UvProjectPredicate = _not_uv_project,
) -> tuple[str, ...]:
    pytest_commands = [_normalize_pytest_command(cmd) for cmd in commands]
    if all(item is not None for item in pytest_commands):
        return _batch_compatible_pytest_commands(
            commands,
            cwd=cwd,
            resolve_command=resolve_command,
            is_uv_project=is_uv_project,
        )
    return _batch_test_commands(commands)


def _batch_compatible_pytest_commands(
    commands: list[tuple[str, ...]],
    *,
    cwd: Union[str, Path] = ".",
    resolve_command: _CommandResolver = _identity_resolve_command,
    is_uv_project: _UvProjectPredicate = _not_uv_project,
) -> tuple[str, ...]:
    normalized = [_normalize_pytest_command(cmd) for cmd in commands]
    if any(item is None for item in normalized):
        raise ValueError("Cannot batch non-pytest commands")
    group_keys = [
        _batch_group_key(
            cmd,
            cwd=cwd,
            resolve_command=resolve_command,
            is_uv_project=is_uv_project,
        )
        for cmd in commands
    ]
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


def _dedupe_commands(
    commands: list[tuple[tuple[str, ...], str]],
    *,
    cwd: Union[str, Path] = ".",
    resolve_command: _CommandResolver = _identity_resolve_command,
) -> list[tuple[tuple[str, ...], str]]:
    seen: set[tuple[str, ...]] = set()
    deduped: list[tuple[tuple[str, ...], str]] = []
    for cmd, slug in commands:
        can_dedupe = _can_dedupe_command(
            cmd,
            cwd=cwd,
            resolve_command=resolve_command,
        )
        if can_dedupe and cmd in seen:
            continue
        if can_dedupe:
            seen.add(cmd)
        deduped.append((cmd, slug))
    return deduped


def _can_dedupe_command(
    command: tuple[str, ...],
    *,
    cwd: Union[str, Path],
    resolve_command: _CommandResolver,
) -> bool:
    resolved_command = resolve_command(command, cwd=cwd)
    pytest_command = _normalize_pytest_command(resolved_command)
    if pytest_command is None:
        return not _looks_like_pytest_invocation(resolved_command)
    _, _, options = pytest_command
    return not _has_non_combinable_pytest_options(options)


def _prune_covered_pytest_commands(
    commands: list[tuple[tuple[str, ...], str]],
    *,
    cwd: Union[str, Path] = ".",
    resolve_command: _CommandResolver = _identity_resolve_command,
    is_uv_project: _UvProjectPredicate = _not_uv_project,
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
        group_key = _batch_group_key(
            cmd,
            cwd=cwd,
            resolve_command=resolve_command,
            is_uv_project=is_uv_project,
        )
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
