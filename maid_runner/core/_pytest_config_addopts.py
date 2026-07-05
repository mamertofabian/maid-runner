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


_PYPROJECT = "pyproject"
_PYTEST_INI = "pytest_ini"
_TOX_INI = "tox_ini"
_SETUP_CFG = "setup_cfg"


class _PytestConfigInspectionError(Exception):
    """Carry the config path when discovery fails while inspecting a candidate."""

    def __init__(self, path: Path, error: Exception) -> None:
        self.path = path
        self.error = error
        super().__init__(str(error))


def pytest_config_addopts_args(
    project_root: Path,
    command: "tuple[str, ...]",
) -> "tuple[str, ...]":
    """Return applicable pytest addopts from the effective project config."""
    config = _effective_pytest_config(project_root, command)
    if config is None:
        return ()

    path, kind = config
    addopts = _config_addopts_value(path, kind)
    if addopts is None:
        return ()
    return _split_addopts(addopts)


def pytest_config_addopts_errors(
    project_root: Path,
    command: "tuple[str, ...]",
) -> "tuple[str, ...]":
    """Return fail-closed pytest project-config addopts inspection errors."""
    try:
        config = _effective_pytest_config(project_root, command)
        if config is None:
            return ()
        path, kind = config
        addopts = _config_addopts_value(path, kind)
        if addopts is not None:
            _split_addopts(addopts)
    except _PytestConfigInspectionError as exc:
        return (f"Could not inspect {exc.path.name} pytest addopts: {exc.error}",)
    except (
        OSError,
        configparser.Error,
        tomllib.TOMLDecodeError,
        ValueError,
        TypeError,
    ) as exc:
        name = path.name if "path" in locals() else "pytest config"
        return (f"Could not inspect {name} pytest addopts: {exc}",)
    return ()


def _pytest_config_addopts_source(
    project_root: Path,
    command: "tuple[str, ...]",
) -> str | None:
    """Return the effective pytest config filename for diagnostics."""
    config = _effective_pytest_config(project_root, command)
    if config is None:
        return None
    return config[0].name


def pyproject_pytest_addopts_args(
    project_root: Path,
    command: "tuple[str, ...]",
) -> "tuple[str, ...]":
    """Return applicable ``pyproject.toml`` pytest addopts arguments."""
    config = _effective_pytest_config(project_root, command)
    if config is None:
        return ()
    path, kind = config
    if kind != _PYPROJECT:
        return ()

    addopts = _config_addopts_value(path, kind)
    if addopts is None:
        return ()
    return _split_addopts(addopts)


def pyproject_pytest_addopts_errors(
    project_root: Path,
    command: "tuple[str, ...]",
) -> "tuple[str, ...]":
    """Return fail-closed ``pyproject.toml`` pytest addopts inspection errors."""
    try:
        config = _effective_pytest_config(project_root, command)
        if config is None:
            return ()
        path, kind = config
        if kind != _PYPROJECT:
            return ()
        addopts = _config_addopts_value(path, kind)
        if addopts is not None:
            _split_addopts(addopts)
    except _PytestConfigInspectionError as exc:
        if exc.path.name != "pyproject.toml":
            return ()
        return (f"Could not inspect pyproject.toml pytest addopts: {exc.error}",)
    except (OSError, tomllib.TOMLDecodeError, ValueError, TypeError) as exc:
        return (f"Could not inspect pyproject.toml pytest addopts: {exc}",)
    return ()


def _pytest_args(command: tuple[str, ...]) -> list[str] | None:
    invocation = _test_runner_invocation(list(command))
    if invocation is None or invocation[0] not in {"pytest", "py.test"}:
        return None
    return invocation[1]


def _effective_pytest_config(
    project_root: Path,
    command: tuple[str, ...],
) -> tuple[Path, str] | None:
    pytest_args = _pytest_args(command)
    if pytest_args is None:
        return None

    project_root = Path(project_root)
    if _has_override_ini_addopts(pytest_args):
        return None

    explicit_config = _explicit_config_path(project_root, pytest_args)
    if explicit_config is not None:
        return _inspect_explicit_pytest_config(explicit_config)

    return _discover_pytest_config(project_root)


def _inspect_explicit_pytest_config(path: Path) -> tuple[Path, str] | None:
    if path.name in {"pytest.ini", ".pytest.ini"}:
        return path, _PYTEST_INI
    if path.name == "pyproject.toml":
        return path, _PYPROJECT
    if path.name == "tox.ini":
        return path, _TOX_INI
    if path.name == "setup.cfg":
        return path, _SETUP_CFG
    if path.suffix == ".toml":
        try:
            if _pyproject_has_pytest_section(path):
                return path, _PYPROJECT
        except (OSError, tomllib.TOMLDecodeError, TypeError) as exc:
            raise _PytestConfigInspectionError(path, exc) from exc
        return None
    try:
        if _ini_has_section(path, "pytest"):
            return path, _PYTEST_INI
        if _ini_has_section(path, "tool:pytest"):
            return path, _SETUP_CFG
    except (OSError, configparser.Error) as exc:
        raise _PytestConfigInspectionError(path, exc) from exc
    return None


def _discover_pytest_config(project_root: Path) -> tuple[Path, str] | None:
    pytest_ini = project_root / "pytest.ini"
    if pytest_ini.exists():
        return pytest_ini, _PYTEST_INI

    dot_pytest_ini = project_root / ".pytest.ini"
    if dot_pytest_ini.exists():
        try:
            if _ini_has_section(dot_pytest_ini, "pytest"):
                return dot_pytest_ini, _PYTEST_INI
        except (OSError, configparser.Error) as exc:
            raise _PytestConfigInspectionError(dot_pytest_ini, exc) from exc

    pyproject = project_root / "pyproject.toml"
    if pyproject.exists():
        try:
            if _pyproject_has_pytest_section(pyproject):
                return pyproject, _PYPROJECT
        except (OSError, tomllib.TOMLDecodeError, TypeError) as exc:
            raise _PytestConfigInspectionError(pyproject, exc) from exc

    tox_ini = project_root / "tox.ini"
    if tox_ini.exists():
        try:
            if _ini_has_section(tox_ini, "pytest"):
                return tox_ini, _TOX_INI
        except (OSError, configparser.Error) as exc:
            raise _PytestConfigInspectionError(tox_ini, exc) from exc

    setup_cfg = project_root / "setup.cfg"
    if setup_cfg.exists():
        try:
            if _ini_has_section(setup_cfg, "tool:pytest"):
                return setup_cfg, _SETUP_CFG
        except (OSError, configparser.Error) as exc:
            raise _PytestConfigInspectionError(setup_cfg, exc) from exc

    return None


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


def _pyproject_has_pytest_section(path: Path) -> bool:
    return _has_pytest_ini_options(_load_pyproject(path))


def _has_pytest_ini_options(config: dict) -> bool:
    tool = config.get("tool")
    if not isinstance(tool, dict):
        return False
    pytest_config = tool.get("pytest")
    if not isinstance(pytest_config, dict):
        return False
    return isinstance(pytest_config.get("ini_options"), dict)


def _ini_has_section(path: Path, section: str) -> bool:
    return _load_ini(path).has_section(section)


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


def _load_ini(path: Path) -> configparser.ConfigParser:
    parser = configparser.ConfigParser(interpolation=None)
    with path.open("r", encoding="utf-8") as handle:
        parser.read_file(handle)
    return parser


def _config_addopts_value(path: Path, kind: str) -> object | None:
    if kind == _PYPROJECT:
        return _pytest_addopts_value(_load_pyproject(path))
    if kind == _PYTEST_INI:
        return _ini_addopts_value(_load_ini(path), "pytest")
    if kind == _TOX_INI:
        return _ini_addopts_value(_load_ini(path), "pytest")
    if kind == _SETUP_CFG:
        return _ini_addopts_value(_load_ini(path), "tool:pytest")
    return None


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


def _ini_addopts_value(
    parser: configparser.ConfigParser, section: str
) -> object | None:
    if not parser.has_section(section):
        return None
    if not parser.has_option(section, "addopts"):
        return None
    return parser.get(section, "addopts")


def _split_addopts(addopts: object) -> tuple[str, ...]:
    if isinstance(addopts, str):
        try:
            return tuple(shlex.split(addopts))
        except ValueError as exc:
            raise ValueError(f"invalid addopts string: {exc}") from exc

    if isinstance(addopts, list) and all(isinstance(item, str) for item in addopts):
        return tuple(addopts)

    raise TypeError("addopts must be a string or a list of strings")
