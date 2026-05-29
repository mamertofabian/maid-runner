"""Inspect pytest addopts from project configuration."""

from __future__ import annotations

import configparser
import shlex
from pathlib import Path

try:  # pragma: no cover - exercised only on Python < 3.11
    import tomllib
except ModuleNotFoundError:  # pragma: no cover
    import tomli as tomllib  # type: ignore[no-redef]

from maid_runner.core._test_runner_invocation import _test_runner_invocation


def pyproject_pytest_addopts_args(
    project_root: Path,
    command: "tuple[str, ...]",
) -> "tuple[str, ...]":
    """Return applicable ``pyproject.toml`` pytest addopts arguments."""
    pytest_args = _pytest_args(command)
    if pytest_args is None:
        return ()

    project_root = Path(project_root)
    pyproject_path = project_root / "pyproject.toml"
    if not pyproject_path.exists():
        return ()
    if not _pyproject_applies(project_root, pytest_args):
        return ()

    config = _load_pyproject(pyproject_path)
    addopts = _pytest_addopts_value(config)
    if addopts is None:
        return ()
    return _split_addopts(addopts)


def pyproject_pytest_addopts_errors(
    project_root: Path,
    command: "tuple[str, ...]",
) -> "tuple[str, ...]":
    """Return fail-closed ``pyproject.toml`` pytest addopts inspection errors."""
    pytest_args = _pytest_args(command)
    if pytest_args is None:
        return ()

    project_root = Path(project_root)
    pyproject_path = project_root / "pyproject.toml"
    if not pyproject_path.exists():
        return ()
    if not _pyproject_applies(project_root, pytest_args):
        return ()

    try:
        config = _load_pyproject(pyproject_path)
        addopts = _pytest_addopts_value(config)
        if addopts is not None:
            _split_addopts(addopts)
    except (OSError, tomllib.TOMLDecodeError, ValueError, TypeError) as exc:
        return (f"Could not inspect pyproject.toml pytest addopts: {exc}",)
    return ()


def _pytest_args(command: tuple[str, ...]) -> list[str] | None:
    invocation = _test_runner_invocation(list(command))
    if invocation is None or invocation[0] not in {"pytest", "py.test"}:
        return None
    return invocation[1]


def _pyproject_applies(project_root: Path, pytest_args: list[str]) -> bool:
    if _has_override_ini_addopts(pytest_args):
        return False
    explicit_config = _explicit_config_path(project_root, pytest_args)
    if explicit_config is not None:
        return _same_path(explicit_config, project_root / "pyproject.toml")
    return not _pytest_ini_takes_precedence(project_root)


def _pytest_ini_takes_precedence(project_root: Path) -> bool:
    if (project_root / "pytest.ini").exists():
        return True
    dot_pytest = project_root / ".pytest.ini"
    if not dot_pytest.exists():
        return False
    parser = configparser.ConfigParser()
    try:
        parser.read(dot_pytest)
    except configparser.Error:
        return False
    return parser.has_section("pytest")


def _explicit_config_path(project_root: Path, pytest_args: list[str]) -> Path | None:
    index = 0
    while index < len(pytest_args):
        part = pytest_args[index]
        if part in {"-c", "--config-file", "--config"} and index + 1 < len(pytest_args):
            return _resolve_config_path(project_root, pytest_args[index + 1])
        if part.startswith("--config-file=") or part.startswith("--config="):
            return _resolve_config_path(project_root, part.split("=", 1)[1])
        if part.startswith("-c") and part != "-c":
            value = part[2:]
            if value.startswith("="):
                value = value[1:]
            return _resolve_config_path(project_root, value)
        index += 1
    return None


def _resolve_config_path(project_root: Path, value: str) -> Path:
    path = Path(value)
    if not path.is_absolute():
        path = project_root / path
    return path


def _has_override_ini_addopts(pytest_args: list[str]) -> bool:
    index = 0
    while index < len(pytest_args):
        part = pytest_args[index]
        if part in {"-o", "--override-ini"} and index + 1 < len(pytest_args):
            if _is_addopts_ini_override(pytest_args[index + 1]):
                return True
            index += 2
            continue
        if part.startswith("--override-ini="):
            if _is_addopts_ini_override(part.split("=", 1)[1]):
                return True
        if part.startswith("-o") and part != "-o":
            if _is_addopts_ini_override(part[2:]):
                return True
        index += 1
    return False


def _is_addopts_ini_override(value: str) -> bool:
    return value.startswith("addopts=")


def _same_path(left: Path, right: Path) -> bool:
    try:
        return left.resolve() == right.resolve()
    except OSError:
        return left.absolute() == right.absolute()


def _load_pyproject(path: Path) -> dict:
    with path.open("rb") as handle:
        data = tomllib.load(handle)
    if not isinstance(data, dict):
        raise TypeError("pyproject.toml did not contain a TOML table")
    return data


def _pytest_addopts_value(config: dict) -> object | None:
    tool = config.get("tool")
    if not isinstance(tool, dict):
        return None
    pytest_config = tool.get("pytest")
    if not isinstance(pytest_config, dict):
        return None
    ini_options = pytest_config.get("ini_options")
    if not isinstance(ini_options, dict):
        return None
    return ini_options.get("addopts")


def _split_addopts(addopts: object) -> tuple[str, ...]:
    if isinstance(addopts, str):
        try:
            return tuple(shlex.split(addopts))
        except ValueError as exc:
            raise ValueError(f"invalid addopts string: {exc}") from exc

    if isinstance(addopts, list) and all(isinstance(item, str) for item in addopts):
        return tuple(addopts)

    raise TypeError("addopts must be a string or a list of strings")
