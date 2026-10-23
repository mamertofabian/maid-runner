"""Annotation-position references retain exact imported type identity."""

from __future__ import annotations

import ast
from pathlib import Path
import subprocess
import sys

import pytest
import yaml

from maid_runner.core.result import ErrorCode
from maid_runner.core.types import ValidationMode
from maid_runner.core.validate import ValidationEngine
from maid_runner.validators.python import PythonValidator

_POSITIVE = [
    "from models import Balance\ndef helper(value: Balance) -> Balance:\n    return value\ndef test_value():\n    assert helper(2) == 2\n",
    "from models import Balance as B\ndef helper(value: B) -> B:\n    return value\ndef test_value():\n    assert helper(2) == 2\n",
    "import models as m\ndef helper(value: m.Balance) -> m.Balance:\n    return value\ndef test_value():\n    assert helper(2) == 2\n",
    "from models import Balance\ndef helper(value: 'Balance') -> 'Balance':\n    return value\ndef test_value():\n    assert helper(2) == 2\n",
    "from models import Balance as B\ndef helper(value: list[B | None]) -> list[B | None]:\n    return value\ndef test_value():\n    assert helper([2]) == [2]\n",
    "import models as m\ndef helper(value: 'dict[str, list[m.Balance | None]]'):\n    return value\ndef test_value():\n    assert helper({'x': [2]}) == {'x': [2]}\n",
    "from models import Balance\nvalue: Balance = 2\ndef test_value():\n    assert value == 2\n",
    "from models import Balance\ndef test_value():\n    value: Balance = 2\n    assert value == 2\n",
    "from models import Balance\ndef helper(Balance: Balance) -> Balance:\n    return Balance\ndef test_value():\n    assert helper(2) == 2\n",
    "from models import Balance\ndef helper(*values: Balance, **named: Balance) -> int:\n    return sum(values) + sum(named.values())\ndef test_value():\n    assert helper(2, x=3) == 5\n",
    "from models import Balance\nfrom typing import Annotated as A\ndef helper(value: A['Balance', 'note']):\n    return value\ndef test_value():\n    assert helper(2) == 2\n",
    "from models import Balance\ndef helper(value: tuple['Balance', ...]):\n    return value\ndef test_value():\n    assert helper((2,)) == (2,)\n",
]
_NEGATIVE = [
    "from models import Balance\ndef test_value():\n    assert 2 == 2\n",
    "from other_models import Balance\ndef helper(value: Balance):\n    return value\ndef test_value():\n    assert helper(2) == 2\n",
    "import other_models as m\ndef helper(value: 'list[m.Balance]'):\n    return value\ndef test_value():\n    assert helper([2]) == [2]\n",
    "from models import Balance\nBalance = int\ndef helper(value: Balance):\n    return value\ndef test_value():\n    assert helper(2) == 2\n",
    "from models import Balance\ndef test_value():\n    Balance = int\n    value: Balance = 2\n    assert value == 2\n",
    "from models import Balance\ndef helper(Balance):\n    value: Balance = 2\n    return value\ndef test_value():\n    assert helper(int) == 2\n",
    "import models as m\nm = None\ndef helper(value: 'm.Balance'):\n    return value\ndef test_value():\n    assert helper(2) == 2\n",
    "from models import Balance\nfrom typing import Literal\ndef helper(value: Literal['Balance']):\n    return value\ndef test_value():\n    assert helper('Balance') == 'Balance'\n",
    "from models import Balance\nfrom typing import Literal as L\ndef helper(value: L['Balance']):\n    return value\ndef test_value():\n    assert helper('Balance') == 'Balance'\n",
    "from models import Balance\nimport typing as t\ndef helper(value: \"t.Literal['Balance']\"):\n    return value\ndef test_value():\n    assert helper('Balance') == 'Balance'\n",
    "from models import Balance\nfrom typing import Annotated\ndef helper(value: Annotated[int, Balance]):\n    return value\ndef test_value():\n    assert helper(2) == 2\n",
    "from models import Balance\nfrom typing import Annotated as A\ndef helper(value: A[int, 'Balance']):\n    return value\ndef test_value():\n    assert helper(2) == 2\n",
    "from models import Balance\ndef helper(value: 'Balance['):\n    return value\ndef test_value():\n    assert helper(2) == 2\n",
]

_POSITIVE.append(
    "from models import Balance\nclass C:\n    Balance: object\n"
    "    value: Balance = 2\n    def method(self, value: Balance) -> Balance:\n"
    "        return value\ndef test_value():\n"
    "    assert C.value == 2\n    assert C().method(2) == 2\n"
)
_NEGATIVE.extend(
    [
        "from models import Balance\nclass C:\n    Balance = int\n"
        "    value: Balance = 2\ndef test_value():\n    assert C.value == 2\n",
        "from models import Balance\nclass C:\n    Balance = int\n"
        "    def method(self, value: Balance) -> Balance:\n        return value\n"
        "def test_value():\n    assert C().method(2) == 2\n",
        "from models import Balance\ndef factory():\n    return dict\n"
        "def helper(value: 'factory()[Balance]'):\n    return value\n"
        "def test_value():\n    assert helper(2) == 2\n",
    ]
)
_NEGATIVE.extend(
    [
        "import importlib\ndef helper(value: \"importlib.import_module('models').Balance\"):\n"
        "    return value\ndef test_value():\n    assert helper(2) == 2\n",
        "import importlib\ndef helper(value: \"(m := importlib.import_module('models')).Balance\"):\n"
        "    return value\ndef test_value():\n    assert helper(2) == 2\n",
        "import importlib\ndef helper(value: \"list[importlib.import_module('models').Balance]\"):\n"
        "    return value\ndef test_value():\n    assert helper(2) == 2\n",
        "import importlib\ndef helper(value: importlib.import_module('models').Balance):\n"
        "    return value\ndef test_value():\n    assert helper(2) == 2\n",
    ]
)


def _project(root: Path, test: str, *, kind: str = "type") -> Path:
    root.joinpath("manifests").mkdir()
    source = {
        "type": "from typing import TypeAlias\nBalance: TypeAlias = int\n",
        "function": "def Balance(value: int) -> int:\n    return value + 1\n",
        "class": "class Balance:\n    pass\n",
        "attribute": "Balance: int = 2\n",
    }[kind]
    root.joinpath("models.py").write_text(source)
    root.joinpath("other_models.py").write_text(
        "from typing import TypeAlias\nBalance: TypeAlias = int\n"
    )
    root.joinpath("test_models.py").write_text(
        "from __future__ import annotations\n" + test
    )
    artifact = {"kind": kind, "name": "Balance"}
    if kind in {"type", "attribute"}:
        artifact["type"] = "int"
    if kind == "function":
        artifact.update(args=[{"name": "value", "type": "int"}], returns="int")
    path = root / "manifests/models.manifest.yaml"
    path.write_text(
        yaml.safe_dump(
            {
                "schema": "2",
                "goal": "Check annotation type identity",
                "type": "fix",
                "created": "2026-10-21T00:00:00Z",
                "files": {
                    "create": [{"path": "models.py", "artifacts": [artifact]}],
                    "read": ["test_models.py"],
                },
                "validate": [["python", "-m", "pytest", "test_models.py", "-q"]],
            }
        )
    )
    actual = subprocess.run(
        [sys.executable, "-m", "pytest", "test_models.py", "-q"],
        cwd=root,
        capture_output=True,
        text=True,
    )
    assert actual.returncode == 0, actual.stdout + actual.stderr
    return path


@pytest.mark.parametrize("test", _POSITIVE)
def test_imported_annotation_types_satisfy_public_behavioral_validation(
    tmp_path: Path, test: str
) -> None:
    path = _project(tmp_path, test)

    result = ValidationEngine(project_root=tmp_path).validate(
        path, mode=ValidationMode.BEHAVIORAL
    )
    collected = PythonValidator().collect_behavioral_artifacts(
        "from __future__ import annotations\n" + test, tmp_path / "test_models.py"
    )

    assert result.success, result.errors
    assert not collected.errors
    assert any(
        a.reference_context == "type"
        and a.import_source == "models"
        and (a.alias_of or a.name) == "Balance"
        for a in collected.artifacts
    )


@pytest.mark.parametrize("test", _NEGATIVE)
def test_import_shadowing_wrong_modules_and_metadata_do_not_cover_types(
    tmp_path: Path, test: str
) -> None:
    path = _project(tmp_path, test)

    result = ValidationEngine(project_root=tmp_path).validate(
        path, mode=ValidationMode.BEHAVIORAL
    )

    assert ErrorCode.ARTIFACT_NOT_USED_IN_TESTS in {e.code for e in result.errors}


@pytest.mark.parametrize("kind", ["function", "class", "attribute"])
def test_type_position_cannot_cover_runtime_artifact_kinds(
    tmp_path: Path, kind: str
) -> None:
    path = _project(tmp_path, _POSITIVE[0], kind=kind)

    result = ValidationEngine(project_root=tmp_path).validate(
        path, mode=ValidationMode.BEHAVIORAL
    )

    assert ErrorCode.ARTIFACT_NOT_USED_IN_TESTS in {e.code for e in result.errors}


@pytest.mark.skipif(not hasattr(ast, "TypeAlias"), reason="PEP695 requires Python3.12+")
@pytest.mark.parametrize(
    "binding", ["type Balance = int", "type Helper[Balance] = list[Balance]"]
)
def test_type_alias_binding_and_local_type_parameters_cannot_cover_imported_type(
    tmp_path: Path, binding: str
) -> None:
    suffix = (
        "\ndef helper(value: Balance):\n    return value\n"
        if binding.startswith("type Balance")
        else ""
    )
    test = (
        "from models import Balance\n"
        + binding
        + suffix
        + "\ndef test_value():\n    assert 2 == 2\n"
    )
    path = _project(tmp_path, test)

    result = ValidationEngine(project_root=tmp_path).validate(
        path, mode=ValidationMode.BEHAVIORAL
    )

    assert ErrorCode.ARTIFACT_NOT_USED_IN_TESTS in {e.code for e in result.errors}


@pytest.mark.skipif(not hasattr(ast, "TypeAlias"), reason="PEP695 requires Python3.12+")
def test_type_alias_value_preserves_type_reference_context(tmp_path: Path) -> None:
    test = (
        "from models import Balance\ntype Helper = Balance\n"
        "def test_value():\n    assert Helper is not None\n"
    )
    path = _project(tmp_path, test)

    result = ValidationEngine(project_root=tmp_path).validate(
        path, mode=ValidationMode.BEHAVIORAL
    )
    collected = PythonValidator().collect_behavioral_artifacts(
        test, tmp_path / "test_models.py"
    )

    assert result.success, result.errors
    assert any(
        a.reference_context == "type"
        and a.import_source == "models"
        and (a.alias_of or a.name) == "Balance"
        for a in collected.artifacts
    )


@pytest.mark.skipif(not hasattr(ast, "TypeAlias"), reason="PEP695 requires Python3.12+")
@pytest.mark.parametrize("kind", ["function", "class", "attribute"])
def test_type_alias_value_cannot_cover_runtime_artifact_kinds(
    tmp_path: Path, kind: str
) -> None:
    test = (
        "from models import Balance\ntype Helper = Balance\n"
        "def test_value():\n    assert Helper is not None\n"
    )
    path = _project(tmp_path, test, kind=kind)

    result = ValidationEngine(project_root=tmp_path).validate(
        path, mode=ValidationMode.BEHAVIORAL
    )

    assert ErrorCode.ARTIFACT_NOT_USED_IN_TESTS in {e.code for e in result.errors}


@pytest.mark.skipif(not hasattr(ast, "TypeAlias"), reason="PEP695 requires Python3.12+")
@pytest.mark.parametrize(
    "test",
    [
        "from models import Balance\ndef helper[Balance](value: Balance) -> Balance:\n    return value\ndef test_value():\n    assert helper(2) == 2\n",
        "from models import Balance\nclass Helper[Balance]:\n    def method(self, value: Balance) -> Balance:\n        return value\ndef test_value():\n    assert Helper().method(2) == 2\n",
    ],
)
def test_generic_type_parameters_shadow_imports_in_annotation_scope(
    tmp_path: Path, test: str
) -> None:
    path = _project(tmp_path, test)

    result = ValidationEngine(project_root=tmp_path).validate(
        path, mode=ValidationMode.BEHAVIORAL
    )

    assert ErrorCode.ARTIFACT_NOT_USED_IN_TESTS in {e.code for e in result.errors}
