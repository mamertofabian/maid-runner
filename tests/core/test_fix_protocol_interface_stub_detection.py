"""Known Protocol signatures are contracts; concrete placeholders remain stubs."""

import ast
from pathlib import Path
import textwrap

import pytest
import yaml

from maid_runner.core.result import ErrorCode
from maid_runner.core.types import ArtifactKind
from maid_runner.core.validate import validate
from maid_runner.validators._python_implementation import (
    collect_implementation_artifacts,
)
from maid_runner.validators.python import PythonValidator

_IMPORTS = [
    ("from typing import Protocol", "Protocol"),
    ("from typing import Protocol as P", "P"),
    ("import typing", "typing.Protocol"),
    ("import typing as t", "t.Protocol"),
    ("from typing_extensions import Protocol", "Protocol"),
    ("from typing_extensions import Protocol as P", "P"),
    ("import typing_extensions as t", "t.Protocol"),
    ("from typing import *", "Protocol"),
    ("from typing_extensions import *", "Protocol"),
    (
        "import typing as t\nfrom typing import TypeVar\n_T = TypeVar('_T')",
        "t.Protocol[_T]",
    ),
    ("from typing import Protocol, TypeVar\n_T = TypeVar('_T')", "Protocol[_T]"),
]


def _source(imports: str, base: str, body: str, *, async_method: bool = False) -> str:
    bases = f"({base})" if base else ""
    declaration = "async def" if async_method else "def"
    return (
        f"{imports}\nclass Reader{bases}:\n    {declaration} read(self) -> str:\n"
        + textwrap.indent(body, "        ")
        + "\n"
    )


def _artifacts(source: str):
    direct = collect_implementation_artifacts(ast.parse(source), "reader.py")
    wrapped = PythonValidator().collect_implementation_artifacts(source, "reader.py")
    assert not wrapped.errors
    assert wrapped.artifacts == direct
    return direct


def _read(source: str):
    found = [
        artifact
        for artifact in _artifacts(source)
        if artifact.kind == ArtifactKind.METHOD
        and artifact.of == "Reader"
        and artifact.name == "read"
    ]
    assert len(found) == 1
    return found[0]


def _warning_codes(root: Path, source: str):
    (root / "reader.py").write_text(source)
    (root / "test_reader.py").write_text(
        "from reader import Reader\nclass Concrete(Reader):\n"
        "    def read(self):\n        value = 'ok'\n        return value\n"
        "def test_concrete_contract():\n    assert Concrete().read() == 'ok'\n"
    )
    manifest = {
        "schema": "2",
        "goal": "Check Reader declaration",
        "type": "fix",
        "created": "2026-10-21T00:00:00Z",
        "files": {
            "edit": [
                {
                    "path": "reader.py",
                    "artifacts": [
                        {"kind": "class", "name": "Reader"},
                        {
                            "kind": "method",
                            "name": "read",
                            "of": "Reader",
                            "args": [],
                            "returns": "str",
                        },
                    ],
                }
            ],
            "read": ["test_reader.py"],
        },
        "validate": [["python", "-m", "pytest", "test_reader.py", "-q"]],
    }
    path = root / "reader.manifest.yaml"
    path.write_text(yaml.safe_dump(manifest))
    result = validate(path, project_root=root, use_chain=False, check_stubs=True)
    assert not result.errors, result.errors
    return [warning.code for warning in result.warnings]


@pytest.mark.parametrize("imports,base", _IMPORTS)
@pytest.mark.parametrize(
    "body", ["...", "pass", '"Read contract."', '"Read contract."\n...']
)
@pytest.mark.parametrize("async_method", [False, True])
def test_protocol_signature_is_not_e310(
    tmp_path: Path, imports: str, base: str, body: str, async_method: bool
) -> None:
    source = _source(imports, base, body, async_method=async_method)

    artifact = _read(source)

    assert artifact.is_stub is False
    assert artifact.is_async is async_method
    assert ErrorCode.STUB_FUNCTION_DETECTED not in _warning_codes(tmp_path, source)


@pytest.mark.parametrize(
    "body",
    ["...", "pass", '"Read contract."', "raise NotImplementedError", "return None"],
)
def test_concrete_signature_placeholders_remain_e310(tmp_path: Path, body: str) -> None:
    source = _source("from typing import Protocol", "", body)

    assert _read(source).is_stub is True
    assert ErrorCode.STUB_FUNCTION_DETECTED in _warning_codes(tmp_path, source)


@pytest.mark.parametrize(
    "source",
    [
        "class Protocol: pass\nclass Reader(Protocol):\n    def read(self) -> str: ...\n",
        "from typing import Protocol\nProtocol = object\nclass Reader(Protocol):\n    def read(self) -> str: ...\n",
        "from typing import Protocol as P\nP = object\nclass Reader(P):\n    def read(self) -> str: ...\n",
        "import typing as t\nt = object()\nclass Reader(t.Protocol):\n    def read(self) -> str: ...\n",
        "from other import Protocol\nclass Reader(Protocol):\n    def read(self) -> str: ...\n",
        "import typing as t\nt.Protocol = object\nclass Reader(t.Protocol):\n    def read(self) -> str: ...\n",
        "import typing as t\nt.Protocol = object\nfrom typing import Protocol\nclass Reader(Protocol):\n    def read(self) -> str: ...\n",
        "from typing import Protocol as P\nimport typing as t\ndel t.Protocol\nclass Reader(P):\n    def read(self) -> str: ...\n",
        "from .typing import Protocol\nclass Reader(Protocol):\n    def read(self) -> str: ...\n",
        "from typing import Protocol\nfrom unknown import *\nclass Reader(Protocol):\n    def read(self) -> str: ...\n",
        "from typing import Protocol\nclass Base(Protocol):\n    def read(self) -> str: ...\nclass Reader(Base):\n    def read(self) -> str: ...\n",
        "from typing import Protocol\nclass Outer:\n    Protocol = object\n    class Reader(Protocol):\n        def read(self) -> str: ...\n",
        "from typing import Protocol\nclass Outer(Protocol):\n    class Reader:\n        def read(self) -> str: ...\n",
        "if some_condition:\n    from typing import Protocol\nclass Reader(Protocol):\n    def read(self) -> str: ...\n",
    ],
)
def test_unknown_or_shadowed_protocol_base_is_not_exempt(source: str) -> None:
    assert _read(source).is_stub is True


@pytest.mark.parametrize(
    "body,stub",
    [
        ("return None", True),
        ("return 'default'", True),
        ("raise NotImplementedError('unsupported')", True),
        ("value = 'default'\nreturn value", False),
    ],
)
def test_protocol_default_bodies_keep_concrete_stub_policy(
    tmp_path: Path, body: str, stub: bool
) -> None:
    source = _source("from typing import Protocol", "Protocol", body)

    assert _read(source).is_stub is stub
    assert (
        ErrorCode.STUB_FUNCTION_DETECTED in _warning_codes(tmp_path, source)
    ) is stub


def test_protocol_context_does_not_leak_to_free_functions() -> None:
    source = _source("from typing import Protocol", "Protocol", "...")
    source += "\ndef free_function() -> str:\n    ...\n"

    free = next(
        artifact for artifact in _artifacts(source) if artifact.name == "free_function"
    )

    assert free.of is None
    assert free.is_stub is True


def test_existing_abstract_method_exemption_is_preserved(tmp_path: Path) -> None:
    source = "from abc import ABC, abstractmethod\nclass Reader(ABC):\n    @abstractmethod\n    def read(self) -> str:\n        ...\n"

    assert _read(source).is_stub is False
    assert ErrorCode.STUB_FUNCTION_DETECTED not in _warning_codes(tmp_path, source)


def test_async_protocol_parameters_are_preserved() -> None:
    source = (
        "from typing import Protocol, Sequence\nclass Reader(Protocol):\n"
        "    async def origins(self, tx_hashes: Sequence[str]) -> dict[str, str]:\n"
        '        "Signer per transaction hash."\n'
    )

    method = next(
        artifact for artifact in _artifacts(source) if artifact.name == "origins"
    )

    assert method.is_stub is False
    assert method.is_async is True
    assert [(argument.name, argument.type) for argument in method.args] == [
        ("tx_hashes", "Sequence[str]")
    ]
    assert method.returns == "dict[str, str]"


@pytest.mark.parametrize(
    "statement", ["t.Protocol: type = object", "t.Protocol += object"]
)
def test_protocol_member_assignment_forms_are_not_exempt(statement: str) -> None:
    source = _source("import typing as t\n" + statement, "t.Protocol", "...")

    assert _read(source).is_stub is True


def test_protocol_member_annotation_without_assignment_keeps_binding() -> None:
    source = _source("import typing as t\nt.Protocol: type", "t.Protocol", "...")

    assert _read(source).is_stub is False
