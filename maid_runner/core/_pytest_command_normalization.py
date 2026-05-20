"""Pytest command normalization used by maid test batching."""

from __future__ import annotations


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
_PYTEST_VERBOSITY_FLAGS = frozenset({"-q", "-qq", "-v", "-vv", "-vvv"})
_PYTEST_NON_COMBINABLE_FLAGS = frozenset({"-x", "--lf", "--ff", "--maxfail"})


def _is_python_command(cmd: str) -> bool:
    """Check if a command is a Python ecosystem command."""
    if cmd in _PYTHON_COMMANDS:
        return True
    # Versioned interpreters: python3.12, python3.11, etc.
    if cmd.startswith("python3."):
        return True
    return False


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


def _pytest_behavior_options(options: tuple[str, ...]) -> tuple[str, ...]:
    return tuple(option for option in options if option not in _PYTEST_VERBOSITY_FLAGS)


def _has_non_combinable_pytest_options(options: tuple[str, ...]) -> bool:
    for option in options:
        flag = option.split("=", 1)[0]
        if flag in _PYTEST_NON_COMBINABLE_FLAGS:
            return True
    return False


def _looks_like_pytest_invocation(command: tuple[str, ...]) -> bool:
    if len(command) >= 3 and command[0] == "uv" and command[1] == "run":
        command = command[2:]
    if not command:
        return False
    if command[0] in {"pytest", "py.test"}:
        return True
    return (
        len(command) >= 3
        and _is_python_command(command[0])
        and command[1] == "-m"
        and command[2] == "pytest"
    )
