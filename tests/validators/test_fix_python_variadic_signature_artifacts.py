"""Variadic Python parameters survive the public artifact contract unchanged."""

import ast
import os
import subprocess
import sys
from pathlib import Path

import pytest
import yaml

from maid_runner.core.manifest import load_manifest, save_manifest
from maid_runner.core.result import ErrorCode
from maid_runner.core.snapshot import generate_snapshot
from maid_runner.core.types import ValidationMode
from maid_runner.core.validate import ValidationEngine
from maid_runner.validators._python_implementation import (
    collect_implementation_artifacts,
)
from maid_runner.validators.python import PythonValidator


@pytest.mark.parametrize(
    "definition,expected",
    [
        (
            "def child_env(**extra: str) -> dict[str, str]:\n    return dict(extra)",
            [("**extra", "str", None)],
        ),
        (
            "def gather(*items: int) -> tuple[int, ...]:\n    return items",
            [("*items", "int", None)],
        ),
        (
            "def gather(*items, **options):\n    return items, options",
            [("*items", None, None), ("**options", None, None)],
        ),
        (
            "def gather(first: int = 2, *items: str, flag: bool = False, **options: float):\n    return first, items, flag, options",
            [
                ("first", "int", "2"),
                ("*items", "str", None),
                ("flag", "bool", "False"),
                ("**options", "float", None),
            ],
        ),
        (
            "async def gather(*items: int, **options: str) -> int:\n    return len(items)",
            [("*items", "int", None), ("**options", "str", None)],
        ),
        (
            "class Reader:\n    def read(self, *items: int, flag: bool = True, **options: str) -> int:\n        return len(items)",
            [
                ("*items", "int", None),
                ("flag", "bool", "True"),
                ("**options", "str", None),
            ],
        ),
        (
            "def gather(first: int, /, *items: str, **options: float):\n    return first, items, options",
            [
                ("first", "int", None),
                ("*items", "str", None),
                ("**options", "float", None),
            ],
        ),
        (
            "def gather(first: int = 2, *, flag: bool = False):\n    return first, flag",
            [("first", "int", "2"), ("flag", "bool", "False")],
        ),
    ],
)
def test_variadic_names_types_and_order_survive_both_collectors(
    definition: str, expected: list
) -> None:
    result = PythonValidator().collect_implementation_artifacts(definition, "sample.py")
    assert not result.errors
    direct = collect_implementation_artifacts(ast.parse(definition), "sample.py")
    for artifacts in (result.artifacts, direct):
        callable_artifact = next(
            a for a in artifacts if a.name in {"child_env", "gather", "read"}
        )
        assert [(a.name, a.type, a.default) for a in callable_artifact.args] == expected


def _project(root: Path, parameter: str, name: str, type_name: str = "str") -> Path:
    (root / "sample.py").write_text(
        f"def gather({parameter}: {type_name}) -> int:\n    return 1\n"
    )
    call = "gather(value='x')" if parameter.startswith("**") else "gather('x')"
    (root / "test_sample.py").write_text(
        f"from sample import gather\ndef test_gather():\n    assert {call} == 1\n"
    )
    path = root / "sample.manifest.yaml"
    path.write_text(
        yaml.safe_dump(
            {
                "schema": "2",
                "goal": "Contract variadic parameter",
                "type": "fix",
                "created": "2026-10-21T00:00:00Z",
                "files": {
                    "create": [
                        {
                            "path": "sample.py",
                            "artifacts": [
                                {
                                    "kind": "function",
                                    "name": "gather",
                                    "args": [{"name": name, "type": type_name}],
                                    "returns": "int",
                                }
                            ],
                        }
                    ],
                    "read": ["test_sample.py"],
                },
                "validate": [["python", "-m", "pytest", "test_sample.py", "-q"]],
            }
        )
    )
    return path


@pytest.mark.parametrize("parameter", ["*items", "**options"])
def test_variadic_parameter_validates_and_snapshot_roundtrips(
    tmp_path: Path, parameter: str
) -> None:
    path = _project(tmp_path, parameter, parameter)
    executed = subprocess.run(
        [sys.executable, "-m", "pytest", "test_sample.py", "-q"],
        cwd=tmp_path,
        env={**os.environ, "PYTEST_DISABLE_PLUGIN_AUTOLOAD": "1"},
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert executed.returncode == 0, executed.stdout + executed.stderr
    engine = ValidationEngine(project_root=tmp_path)
    result = engine.validate(path, mode=ValidationMode.IMPLEMENTATION)
    assert result.success, result.errors
    snapshot = generate_snapshot(tmp_path / "sample.py", project_root=tmp_path)
    snapshot_path = tmp_path / "snapshot.manifest.yaml"
    save_manifest(snapshot, snapshot_path)
    restored = load_manifest(snapshot_path)
    (argument,) = restored.files_snapshot[0].artifacts[0].args
    assert (argument.name, argument.type, argument.default) == (parameter, "str", None)
    result = engine.validate(snapshot_path, mode=ValidationMode.IMPLEMENTATION)
    assert result.success, result.errors


@pytest.mark.parametrize(
    "actual,declared",
    [
        ("*items", "items"),
        ("**items", "items"),
        ("*items", "**items"),
        ("**items", "*items"),
        ("items", "*items"),
        ("items", "**items"),
    ],
)
def test_variadic_and_regular_parameters_do_not_match_accidentally(
    tmp_path: Path, actual: str, declared: str
) -> None:
    path = _project(tmp_path, actual, declared)
    result = ValidationEngine(project_root=tmp_path).validate(
        path, mode=ValidationMode.IMPLEMENTATION
    )
    assert not result.success
    assert any(
        error.code == ErrorCode.SIGNATURE_MISMATCH for error in result.errors
    ), result.errors


@pytest.mark.parametrize("parameter", ["*items", "**options"])
def test_variadic_type_mismatch_remains_blocking(
    tmp_path: Path, parameter: str
) -> None:
    path = _project(tmp_path, parameter, parameter)
    manifest = yaml.safe_load(path.read_text())
    manifest["files"]["create"][0]["artifacts"][0]["args"][0]["type"] = "int"
    path.write_text(yaml.safe_dump(manifest))
    result = ValidationEngine(project_root=tmp_path).validate(
        path, mode=ValidationMode.IMPLEMENTATION
    )
    assert not result.success
    assert any(
        error.code == ErrorCode.TYPE_MISMATCH for error in result.errors
    ), result.errors
