"""Bounded native collection proof for pytest configuration selectors."""

from __future__ import annotations

import configparser
import json
import os
import tempfile
from collections.abc import Sequence
from pathlib import Path

from maid_runner.core._pytest_config_addopts import (
    _PytestConfigInspectionError,
    pytest_config_addopts_args,
    pytest_config_addopts_errors,
)
from maid_runner.core._test_runner_invocation import _test_runner_invocation
from maid_runner.core._pytest_worker_execution import (
    PytestCollectionResult as _CollectionResult,
)


_BENIGN_FLAGS = frozenset(
    {
        "-q",
        "-qq",
        "-v",
        "-vv",
        "-vvv",
        "-s",
        "-ra",
        "-rA",
        "--disable-warnings",
        "--strict-markers",
        "--strict-config",
    }
)
_SELECTION_FLAGS = frozenset({"-m", "-k", "--ignore", "--ignore-glob", "--deselect"})
_CONFIG_FLAGS = frozenset({"-c", "--config-file"})
_CONFIG_NAMES = ("pytest.ini", ".pytest.ini", "pyproject.toml", "tox.ini", "setup.cfg")
_CONFIG_CAPTURE_PLUGIN = """
import json
import os
from pathlib import Path
import pytest

class _SelectionProbe:
    def __init__(self, output):
        self.output = output

    @pytest.hookimpl(tryfirst=True)
    def pytest_runtestloop(self, session):
        if session.testsfailed:
            raise pytest.UsageError("selection proof cannot ignore collection failures")
        config = session.config
        runnable = not any(
            config.getoption(name, default=False)
            for name in ("collectonly", "setuponly", "setupplan")
        )
        if self.output:
            Path(self.output).write_text(json.dumps({
                "addopts": config.getini("addopts"),
                "nodeids": [item.nodeid for item in session.items],
                "runnable": runnable,
            }), encoding="utf-8")
        return True

    @pytest.hookimpl(tryfirst=True)
    def pytest_runtest_protocol(self, item, nextitem):
        raise pytest.UsageError("selection proof refuses test or fixture dispatch")

@pytest.hookimpl(trylast=True)
def pytest_configure(config):
    output = os.environ.pop("MAID_ADDOPTS_PROOF_CONFIG", None)
    config.pluginmanager.register(_SelectionProbe(output), __name__ + ":selection")
    retained = [
        name.strip() for name in os.environ.get("PYTEST_PLUGINS", "").split(",")
        if name.strip() and name.strip() != __name__
    ]
    if retained:
        os.environ["PYTEST_PLUGINS"] = ",".join(retained)
    else:
        os.environ.pop("PYTEST_PLUGINS", None)
"""


def pytest_addopts_collection_error(
    project_root: Path, command: Sequence[str]
) -> str | None:
    """Prove configured selectors retain identical nonempty native test IDs.

    Two guarded child processes import consumer tests and conftest files,
    preserve native collection-mode flags, and stop normal test/fixture
    dispatch. Unknown syntax and incomplete evidence fail closed. Only the
    baseline probe overrides addopts; execution is not rewritten. No successful
    verdict is retained between calls.
    """
    from maid_runner.core._test_command_execution import _test_command_environment
    from maid_runner.core.test_runner import _resolve_command

    root = Path(project_root)
    command = tuple(command)
    if not _supported_command(command):
        return "collection proof does not support this pytest command syntax"
    try:
        if not root.is_dir():
            return "collection proof requires an existing project directory"
        errors = pytest_config_addopts_errors(root, command)
        if errors:
            return "; ".join(errors)
        addopts = pytest_config_addopts_args(root, command)
        if not _supported_options(addopts, config=True):
            return "collection proof does not support these addopts options"
        config_error = _implicit_config_error(root, command)
        if config_error is not None:
            return config_error
        resolved = _resolve_command(command, cwd=root)
        environment = _test_command_environment()
        baseline = _collect_with_config(
            (*resolved, "-o", "addopts="), root, environment, ()
        )
        if baseline.error is not None:
            return f"unfiltered collection failed: {baseline.error}"
        if not baseline.nodeids:
            return "unfiltered collection did not discover any behavioral test cases"
        effective = _collect_with_config(resolved, root, environment, addopts)
        if effective.error is not None:
            return f"configured collection failed: {effective.error}"
        errors = pytest_config_addopts_errors(root, command)
        if errors:
            return "; ".join(errors)
        if pytest_config_addopts_args(root, command) != addopts:
            return "pytest addopts changed while collection evidence was gathered"
        if set(baseline.nodeids) != set(effective.nodeids):
            return (
                "configured collection changes behavioral test identities "
                f"(unfiltered {len(baseline.nodeids)}, configured {len(effective.nodeids)})"
            )
    except (
        OSError,
        ValueError,
        TypeError,
        configparser.Error,
        _PytestConfigInspectionError,
    ) as exc:
        return f"pytest collection proof failed: {exc}"
    return None


def _collect_with_config(
    command: tuple[str, ...],
    root: Path,
    environment: dict[str, str],
    expected_addopts: tuple[str, ...],
) -> _CollectionResult:
    from maid_runner.core._pytest_worker_execution import _merged_pytest_plugins
    from maid_runner.core._test_command_execution import _run_test_command

    with tempfile.TemporaryDirectory(prefix="maid-addopts-config-") as directory_name:
        directory = Path(directory_name)
        plugin_name = "_" + directory.name.replace("-", "_")
        (directory / f"{plugin_name}.py").write_text(
            _CONFIG_CAPTURE_PLUGIN, encoding="utf-8"
        )
        output = directory / "config.json"
        child_environment = dict(environment)
        pythonpath = environment.get("PYTHONPATH")
        child_environment["PYTHONPATH"] = str(directory) + (
            os.pathsep + pythonpath if pythonpath else ""
        )
        child_environment["PYTEST_PLUGINS"] = _merged_pytest_plugins(
            environment.get("PYTEST_PLUGINS"), plugin_name
        )
        child_environment["MAID_ADDOPTS_PROOF_CONFIG"] = str(output)
        result = _run_test_command(
            command, cwd=root, timeout=120, environment_overrides=child_environment
        )
        if result.exit_code not in {0, 5}:
            detail = result.stderr.strip() or result.stdout.strip()
            return _CollectionResult(
                (), f"pytest collection failed: {detail or result.exit_code}"
            )
        try:
            payload = json.loads(output.read_text(encoding="utf-8"))
        except (OSError, UnicodeError, json.JSONDecodeError) as exc:
            return _CollectionResult(
                (), f"native pytest config evidence unavailable: {exc}"
            )
        if not isinstance(payload, dict) or set(payload) != {
            "addopts",
            "nodeids",
            "runnable",
        }:
            return _CollectionResult((), "native pytest config evidence is malformed")
        if payload["runnable"] is not True:
            return _CollectionResult((), "native pytest command does not execute tests")
        actual = payload["addopts"]
        if not isinstance(actual, list) or not all(
            isinstance(arg, str) for arg in actual
        ):
            return _CollectionResult((), "native pytest config addopts are malformed")
        if tuple(actual) != expected_addopts:
            return _CollectionResult(
                (), "native pytest addopts differ from the inspected configuration"
            )
        nodeids = payload["nodeids"]
        if not isinstance(nodeids, list) or not all(
            isinstance(nodeid, str) and nodeid for nodeid in nodeids
        ):
            return _CollectionResult((), "native pytest test identities are malformed")
        if len(set(nodeids)) != len(nodeids):
            return _CollectionResult((), "native pytest test identities are duplicated")
        return _CollectionResult(tuple(nodeids), None)


def _supported_command(command: tuple[str, ...]) -> bool:
    inner = command[2:] if command[:2] == ("uv", "run") else command
    if not inner:
        return False
    invocation = _test_runner_invocation(list(inner))
    if invocation is None or invocation[0] not in {"pytest", "py.test"}:
        return False
    if Path(inner[0]).name in {"pytest", "py.test"}:
        args = inner[1:]
    elif len(inner) >= 3 and inner[1] == "-m" and inner[2] in {"pytest", "py.test"}:
        args = inner[3:]
    else:
        return False
    return _supported_options(args, config=False)


def _supported_options(args: tuple[str, ...], *, config: bool) -> bool:
    if any(part.startswith("@") for part in args):
        return False
    value_flags = _SELECTION_FLAGS if config else _CONFIG_FLAGS
    has_target = False
    has_config = False
    index = 0
    while index < len(args):
        part = args[index]
        if part in _BENIGN_FLAGS:
            index += 1
            continue
        flag, separator, _value = part.partition("=")
        if flag in value_flags:
            if not config:
                if has_config:
                    return False
                has_config = True
            if separator:
                index += 1
            elif index + 1 < len(args):
                index += 2
            else:
                return False
            continue
        if config and part.startswith(("-m", "-k")) and len(part) > 2:
            index += 1
            continue
        if (
            config
            or not part
            or part.startswith("-")
            or part in {";", "&&", "||"}
            or "::" in part
        ):
            return False
        has_target = True
        index += 1
    return config or has_target


def _implicit_config_error(root: Path, command: tuple[str, ...]) -> str | None:
    invocation = _test_runner_invocation(list(command))
    if invocation is None:
        return "collection proof requires an explicit pytest invocation"
    args = invocation[1]
    if any(part.partition("=")[0] in _CONFIG_FLAGS for part in args):
        return None
    resolved_root = root.resolve()
    for target in (part for part in args if part not in _BENIGN_FLAGS):
        lexical = (resolved_root / target).absolute()
        resolved = lexical.resolve()
        if lexical != resolved or (
            resolved != resolved_root and resolved_root not in resolved.parents
        ):
            return "collection proof for aliased or outside-root targets requires an explicit -c/--config-file choice"
        directory = resolved if resolved.is_dir() else resolved.parent
        while directory != resolved_root:
            if any((directory / name).is_file() for name in _CONFIG_NAMES):
                return "collection proof with a nearer pytest config requires an explicit -c/--config-file choice"
            directory = directory.parent
    return None
