"""Vitest command normalization used by maid test batching."""

from __future__ import annotations


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


def _normalize_vitest_command(
    command: tuple[str, ...],
) -> tuple[tuple[str, ...], tuple[str, ...], tuple[str, ...]] | None:
    """Normalize simple Vitest run invocations for safe batching."""
    if not command:
        return None

    if len(command) >= 4 and command[:4] == ("pnpm", "exec", "vitest", "run"):
        prefix = command[:4]
        args = command[4:]
    elif len(command) >= 3 and command[:3] == ("pnpm", "vitest", "run"):
        prefix = command[:3]
        args = command[3:]
    elif len(command) >= 3 and command[:3] == ("npx", "vitest", "run"):
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
