"""Test-runner invocation detection helpers."""

from __future__ import annotations

import re
import shlex
from pathlib import Path

_TEST_RUNNERS = frozenset(
    {
        "pytest",
        "py.test",
        "vitest",
        "jest",
        "playwright",
    }
)
_PYTHON_MODULE_TEST_RUNNERS = frozenset({"pytest", "py.test"})
_DJANGO_TEST_RUNNER = "django"
_DIRECT_TEST_RUNNERS = frozenset({"pytest", "py.test", "jest", "vitest"})
_PACKAGE_RUNNER_WRAPPERS = frozenset({"npx", "pnpm", "yarn", "bunx"})
_PACKAGE_RUNNER_CWD_VALUE_FLAGS = frozenset({"-C", "--cwd", "--dir", "--prefix"})
_DJANGO_TEST_RUNNER_VALUE_FLAGS = frozenset(
    {
        "-p",
        "-t",
        "-v",
        "--exclude-tag",
        "--pattern",
        "--settings",
        "--testrunner",
        "--top-level-directory",
        "--verbosity",
    }
)
_DJANGO_TEST_RUNNER_SELECTOR_FLAGS = frozenset({"-k", "--tag", "--exclude-tag"})
_DJANGO_TEST_RUNNER_PATH_MUTATION_FLAGS = frozenset({"--pythonpath"})
_DJANGO_TEST_RUNNER_OPTIONAL_VALUE_FLAGS = frozenset({"--parallel", "--shuffle"})
_DJANGO_TEST_RUNNER_STANDALONE_FLAGS = frozenset(
    {
        "-b",
        "-f",
        "--buffer",
        "--debug-mode",
        "--debug-sql",
        "--enable-faulthandler",
        "--failfast",
        "--force-color",
        "--keepdb",
        "--no-color",
        "--noinput",
        "--pdb",
        "--reverse",
        "--timing",
        "--traceback",
    }
)
_DOCKER_EXEC_VALUE_FLAGS = frozenset(
    {
        "-e",
        "-u",
        "-w",
        "--detach-keys",
        "--env",
        "--env-file",
        "--user",
        "--workdir",
    }
)
_NON_EXECUTING_TEST_RUNNER_FLAGS = frozenset(
    {
        "-h",
        "--help",
        "--version",
        "--collect-only",
        "--co",
        "--fixtures",
        "--fixtures-per-test",
        "--markers",
        "--setup-only",
        "--setup-plan",
        "--clearCache",
        "--list",
        "--list-tests",
        "--listTests",
        "--showConfig",
        "--dry-run",
        "--dryRun",
        "--deselect",
        "--ignore",
        "--ignore-glob",
    }
)
_NON_EXECUTING_TEST_RUNNER_SUBCOMMANDS = {
    "vitest": frozenset({"list"}),
}
_TEST_RUNNER_SELECTOR_FLAGS = frozenset(
    {
        "-k",
        "-m",
        "--testNamePattern",
        "--testPathPattern",
        "--testPathPatterns",
        "--testPathIgnorePatterns",
        "--testRegex",
        "--testMatch",
        "--runTestsByPath",
        "--findRelatedTests",
        "--changedSince",
        "--changedFilesWithAncestor",
        "--last-failed",
        "--onlyChanged",
        "--onlyFailures",
        "--filter",
        "--grep",
        "--grep-invert",
        "--only-changed",
        "--shard",
        "--lf",
        "-g",
        "-t",
    }
)
_TEST_RUNNER_VALUE_FLAGS = frozenset(
    {
        "-k",
        "-m",
        "-o",
        "--basetemp",
        "--confcutdir",
        "--cov",
        "--import-mode",
        "--junitxml",
        "--maxfail",
        "--override-ini",
        "--rootdir",
        "--tb",
        "--config",
        "-c",
        "--environment",
        "--pool",
        "--reporter",
        "--testNamePattern",
        "-t",
    }
)


def _runs_known_test_runner(segment: list[str]) -> bool:
    return _invokes_known_test_runner(segment)


def _invokes_known_test_runner(segment: list[str]) -> bool:
    return _test_runner_invocation(segment) is not None


def _strip_environment_prefix(segment: list[str]) -> list[str]:
    parts = list(segment)
    while parts and _looks_like_environment_assignment(parts[0]):
        parts.pop(0)

    if not parts or _command_name(parts[0]) != "env":
        return parts

    index = 1
    while index < len(parts):
        part = parts[index]
        if _looks_like_environment_assignment(part):
            index += 1
            continue
        if part in {"-i", "-0"}:
            index += 1
            continue
        if part in {"-u", "--unset"} and index + 1 < len(parts):
            index += 2
            continue
        if part.startswith("-"):
            return parts
        break
    return parts[index:]


def _looks_like_environment_assignment(part: str) -> bool:
    return bool(re.match(r"[A-Za-z_][A-Za-z0-9_]*=", part))


def _command_name(part: str) -> str:
    return Path(part).name


def _is_python_command(command: str) -> bool:
    return command in {"python", "python3", "py"} or command.startswith("python3.")


def _has_non_executing_test_runner_mode(segment: list[str]) -> bool:
    invocation = _effective_test_runner_invocation(segment)
    if invocation is None:
        return False

    runner, args = invocation
    if args:
        first = args[0].split("=", 1)[0]
        if first in _NON_EXECUTING_TEST_RUNNER_SUBCOMMANDS.get(runner, frozenset()):
            return True

    for part in args:
        flag = part.split("=", 1)[0]
        if flag in _NON_EXECUTING_TEST_RUNNER_FLAGS:
            return True
    return False


def _has_test_runner_selector(segment: list[str]) -> bool:
    invocation = _effective_test_runner_invocation(segment)
    if invocation is None:
        return False

    runner, args = invocation
    if runner == _DJANGO_TEST_RUNNER:
        return _has_django_test_runner_selector(args) or _has_pythonpath_assignment(
            segment
        )

    for part in args:
        if _is_test_runner_selector_flag(part):
            return True
    return False


def _has_pythonpath_assignment(segment: list[str]) -> bool:
    for index, part in enumerate(segment):
        if (
            _looks_like_environment_assignment(part)
            and part.split("=", 1)[0] == "PYTHONPATH"
        ):
            return True
        if _is_docker_pythonpath_env_option(segment, index):
            return True
        if _is_docker_env_file_option(segment, index):
            return True
    return False


def _is_docker_env_file_option(segment: list[str], index: int) -> bool:
    part = segment[index]
    if part == "--env-file":
        return True
    return part.startswith("--env-file=")


def _is_docker_pythonpath_env_option(segment: list[str], index: int) -> bool:
    part = segment[index]
    if part in {"-e", "--env"}:
        return index + 1 < len(segment) and _is_pythonpath_env_value(segment[index + 1])
    if part.startswith("--env="):
        return _is_pythonpath_env_value(part.split("=", 1)[1])
    if part.startswith("-e") and part != "-e":
        value = part[2:]
        if value.startswith("="):
            value = value[1:]
        return _is_pythonpath_env_value(value)
    return False


def _is_pythonpath_env_value(value: str) -> bool:
    return value == "PYTHONPATH" or value.startswith("PYTHONPATH=")


def _runs_django_test_runner(segment: list[str]) -> bool:
    invocation = _effective_test_runner_invocation(segment)
    return invocation is not None and invocation[0] == _DJANGO_TEST_RUNNER


def _has_django_test_runner_selector(args: list[str]) -> bool:
    for part in args:
        if _is_django_test_runner_selector_flag(part):
            return True
        if part.split("=", 1)[0] in _DJANGO_TEST_RUNNER_PATH_MUTATION_FLAGS:
            return True
    return False


def _is_django_test_runner_selector_flag(part: str) -> bool:
    flag = part.split("=", 1)[0]
    if flag in _DJANGO_TEST_RUNNER_SELECTOR_FLAGS:
        return True
    return part.startswith("-k") and part != "-k" and not part.startswith("--")


def _is_test_runner_selector_flag(part: str) -> bool:
    flag = part.split("=", 1)[0]
    if flag in _TEST_RUNNER_SELECTOR_FLAGS:
        return True
    if part.startswith("--") or not part.startswith("-") or len(part) <= 2:
        return False

    short_selectors = {
        flag[1:]
        for flag in _TEST_RUNNER_SELECTOR_FLAGS
        if flag.startswith("-") and not flag.startswith("--") and len(flag) == 2
    }
    return any(selector in part[1:] for selector in short_selectors)


def _effective_test_runner_invocation(
    segment: list[str],
) -> tuple[str, list[str]] | None:
    invocation = _test_runner_invocation(segment)
    if invocation is None:
        return None

    runner, args = invocation
    if runner not in _PYTHON_MODULE_TEST_RUNNERS:
        return runner, args

    args = [*_pytest_addopts_args(segment), *args]
    return runner, [
        *_pytest_override_ini_addopts_args(args),
        *args,
    ]


def _pytest_addopts_args(segment: list[str]) -> list[str]:
    args: list[str] = []
    for part in segment:
        if not _looks_like_environment_assignment(part):
            continue
        name, value = part.split("=", 1)
        if name != "PYTEST_ADDOPTS":
            continue
        try:
            args.extend(shlex.split(value))
        except ValueError:
            args.append(value)
    return args


def _pytest_override_ini_addopts_args(args: list[str]) -> list[str]:
    addopts_args: list[str] = []
    index = 0
    while index < len(args):
        part = args[index]
        if part in {"-o", "--override-ini"} and index + 1 < len(args):
            addopts_args.extend(_pytest_ini_addopts_args(args[index + 1]))
            index += 2
            continue
        if part.startswith("--override-ini="):
            addopts_args.extend(_pytest_ini_addopts_args(part.split("=", 1)[1]))
            index += 1
            continue
        if part.startswith("-o") and part != "-o":
            addopts_args.extend(_pytest_ini_addopts_args(part[2:]))
            index += 1
            continue
        index += 1
    return addopts_args


def _pytest_ini_addopts_args(value: str) -> list[str]:
    if not value.startswith("addopts="):
        return []
    try:
        return shlex.split(value.split("=", 1)[1])
    except ValueError:
        return [value.split("=", 1)[1]]


def _test_runner_invocation(segment: list[str]) -> tuple[str, list[str]] | None:
    parts = _strip_environment_prefix(segment)
    if not parts:
        return None

    command = _command_name(parts[0])

    if command == "uv" and len(parts) >= 3 and parts[1] == "run":
        return _test_runner_invocation(parts[2:])

    if command in {"poetry", "pdm"} and len(parts) >= 3 and parts[1] == "run":
        return _test_runner_invocation(parts[2:])

    if command == "docker":
        inner_command = _docker_exec_inner_command(parts)
        if inner_command is not None:
            return _test_runner_invocation(inner_command)

    if command == "coverage" and len(parts) >= 4 and parts[1:3] == ["run", "-m"]:
        return _test_runner_invocation(parts[3:])

    if (
        _is_python_command(command)
        and len(parts) >= 3
        and _command_name(parts[1]) == "manage.py"
    ):
        django_args = _django_test_args_after_subcommand(parts[2:])
        if django_args is not None:
            return _DJANGO_TEST_RUNNER, django_args

    if command in {"django-admin", "django-admin.py"} and len(parts) >= 2:
        django_args = _django_test_args_after_subcommand(parts[1:])
        if django_args is not None:
            return _DJANGO_TEST_RUNNER, django_args

    if (
        _is_python_command(command)
        and len(parts) >= 4
        and parts[1] == "-m"
        and _command_name(parts[2]) == "django"
    ):
        django_args = _django_test_args_after_subcommand(parts[3:])
        if django_args is not None:
            return _DJANGO_TEST_RUNNER, django_args

    if (
        _is_python_command(command)
        and len(parts) >= 3
        and parts[1] == "-m"
        and _command_name(parts[2]) in _PYTHON_MODULE_TEST_RUNNERS
    ):
        return _command_name(parts[2]), parts[3:]

    if command in _DIRECT_TEST_RUNNERS:
        return command, parts[1:]

    if command == "playwright" and len(parts) >= 2 and parts[1] == "test":
        return command, parts[2:]

    if command in _PACKAGE_RUNNER_WRAPPERS and len(parts) >= 2:
        inner_command = _package_runner_inner_command(parts, preserve_cwd_options=False)
        if inner_command is not None:
            return _test_runner_invocation(inner_command)

    if command == "npm" and len(parts) >= 3 and parts[1] == "exec":
        return _test_runner_invocation(parts[2:])

    return None


def _test_runner_target_scan_segment(segment: list[str]) -> list[str]:
    parts = _strip_environment_prefix(segment)
    if not parts:
        return parts

    command = _command_name(parts[0])

    if command == "uv" and len(parts) >= 3 and parts[1] == "run":
        return _test_runner_target_scan_segment(parts[2:])

    if command in {"poetry", "pdm"} and len(parts) >= 3 and parts[1] == "run":
        return _test_runner_target_scan_segment(parts[2:])

    if command == "docker":
        inner_command = _docker_exec_inner_command(parts)
        if inner_command is not None:
            return _test_runner_target_scan_segment(inner_command)

    if command == "coverage" and len(parts) >= 4 and parts[1:3] == ["run", "-m"]:
        return _test_runner_target_scan_segment(parts[3:])

    if command in _PACKAGE_RUNNER_WRAPPERS and len(parts) >= 2:
        inner_command = _package_runner_inner_command(parts, preserve_cwd_options=True)
        if inner_command is not None:
            return _test_runner_target_scan_segment(inner_command)

    if command == "npm" and len(parts) >= 3 and parts[1] == "exec":
        return _test_runner_target_scan_segment(parts[2:])

    return parts


def _package_runner_inner_command(
    parts: list[str], *, preserve_cwd_options: bool
) -> list[str] | None:
    index = 1
    preserved_cwd_options: list[str] = []

    while index < len(parts):
        part = parts[index]
        if part == "exec":
            return [*preserved_cwd_options, *parts[index + 1 :]]
        if part in _PACKAGE_RUNNER_CWD_VALUE_FLAGS and index + 1 < len(parts):
            if preserve_cwd_options:
                preserved_cwd_options.extend([part, parts[index + 1]])
            index += 2
            continue
        if any(part.startswith(f"{flag}=") for flag in _PACKAGE_RUNNER_CWD_VALUE_FLAGS):
            flag, value = part.split("=", 1)
            if preserve_cwd_options:
                preserved_cwd_options.extend([flag, value])
            index += 1
            continue
        if part.startswith("-"):
            index += 1
            continue
        return [*preserved_cwd_options, *parts[index:]]

    return None


def _django_test_args_after_subcommand(parts: list[str]) -> list[str] | None:
    index = 0
    while index < len(parts):
        part = parts[index]
        if part == "test":
            return parts[index + 1 :]
        if not part.startswith("-"):
            return None
        if _is_django_test_runner_selector_flag(part):
            return None

        next_index = _next_django_argument_index(parts, index)
        if next_index is None or next_index <= index:
            return None
        index = next_index
    return None


def _docker_exec_inner_command(parts: list[str]) -> list[str] | None:
    if len(parts) < 4 or parts[1] != "exec":
        return None

    index = 2
    while index < len(parts):
        part = parts[index]
        if not part.startswith("-"):
            break

        flag = part.split("=", 1)[0]
        if _is_detached_docker_exec_option(part):
            return None
        index += 1
        if "=" not in part and flag in _DOCKER_EXEC_VALUE_FLAGS and index < len(parts):
            index += 1

    if index >= len(parts) - 1:
        return None
    return parts[index + 1 :]


def _is_detached_docker_exec_option(part: str) -> bool:
    flag = part.split("=", 1)[0]
    if flag == "--detach":
        return True
    if part.startswith("--") or not part.startswith("-"):
        return False

    short_options = flag[1:]
    if not short_options:
        return False
    if short_options[0] in {"e", "u", "w"}:
        return False
    return "d" in short_options


def _is_django_test_runner_value_flag(part: str) -> bool:
    flag = part.split("=", 1)[0]
    return flag in (
        _DJANGO_TEST_RUNNER_VALUE_FLAGS | _DJANGO_TEST_RUNNER_OPTIONAL_VALUE_FLAGS
    )


def _next_django_argument_index(args: list[str], index: int) -> int | None:
    part = args[index]
    flag = part.split("=", 1)[0]

    if _is_attached_django_short_value(part):
        return index + 1
    if flag in _DJANGO_TEST_RUNNER_VALUE_FLAGS | _DJANGO_TEST_RUNNER_SELECTOR_FLAGS:
        if "=" in part:
            return index + 1
        if index + 1 >= len(args) or args[index + 1].startswith("-"):
            return None
        return index + 2
    if flag in _DJANGO_TEST_RUNNER_PATH_MUTATION_FLAGS:
        return None
    if flag in _DJANGO_TEST_RUNNER_OPTIONAL_VALUE_FLAGS:
        if "=" in part or index + 1 >= len(args) or args[index + 1].startswith("-"):
            return index + 1
        return index + 2
    if flag in _DJANGO_TEST_RUNNER_STANDALONE_FLAGS:
        return index + 1

    return None


def _is_attached_django_short_value(part: str) -> bool:
    return any(
        part.startswith(flag) and part != flag for flag in {"-k", "-p", "-t", "-v"}
    )
