"""Public Python signatures compare nested types without erasing value metadata."""

import ast
from pathlib import Path

import pytest
import yaml

from maid_runner.core._type_compare import normalize_type, types_match
from maid_runner.core.manifest import load_manifest, save_manifest
from maid_runner.core.result import ErrorCode
from maid_runner.core.snapshot import generate_snapshot
from maid_runner.core.types import ValidationMode
from maid_runner.core.validate import ValidationEngine
from maid_runner.validators._python_implementation import (
    collect_implementation_artifacts,
)
from maid_runner.validators.python import PythonValidator

_EQUIVALENT = [
    ("list[int | None]", "list[Union[None, int]]"),
    ("dict[str, dict[str, float | None]]", "dict[str, dict[str, Union[float, None]]]"),
    (
        "tuple[list[int | str], dict[str, Optional[float]]]",
        "tuple[list[Union[str, int]], dict[str, float | None]]",
    ),
    (
        "Callable[[int | None, str], list[str | None]]",
        "Callable[[Union[None, int], str], list[Optional[str]]]",
    ),
    ("list[Union[int, Union[str, None]]]", "list[None | str | int]"),
    (
        'Annotated[list[int | None], "label | note"]',
        "Annotated[list[Optional[int]], 'label | note']",
    ),
    ("Literal['PROXY', 'CANDIDATE']", 'Literal["PROXY", "CANDIDATE"]'),
]
_DISTINCT = [
    ("list[int | None]", "list[str | None]"),
    ("dict[str, int | None]", "dict[str, int]"),
    ("Literal['1']", "Literal[1]"),
    ("Literal['None']", "Literal[None]"),
    ("Literal['PROXY']", "Literal[PROXY]"),
    ("Literal['read']", "Literal['write']"),
    ("Literal['A|B']", "Literal['A', 'B']"),
    ("Annotated[int, '1']", "Annotated[int, 1]"),
    ("Annotated[int, 'A | B']", "Annotated[int, 'A|B']"),
    ("Annotated[int, A | B]", "Annotated[int, Union[A, B]]"),
    ("Other.Union[int, None]", "int | None"),
    ('"string"', "string"),
    ('"A|B"', '"B|A"'),
    ("Array<string>", "Array<number>"),
    ("{ value: string }", "{ value: number }"),
]
_ANNOTATIONS = [
    "list[int | None]",
    "dict[str, dict[str, float | None]]",
    "tuple[list[int | str], dict[str, Optional[float]]]",
    "Callable[[int | None], list[str | None]]",
    'Literal["PROXY", "CANDIDATE"]',
    'Literal["A|B", "a,b", "a b", "None"]',
    'typing.Literal["PROXY", 1, None, True]',
    'Annotated[Literal["PROXY"], "label | note", 1]',
    'Annotated[list[int | None], " spaced metadata "]',
]


def _project(root: Path, annotation: str, expected: str | None = None) -> Path:
    source = (
        "from __future__ import annotations\nimport typing\n"
        "from typing import Annotated, Callable, Literal, Optional, Union\n"
        f"def identity(value: {annotation}) -> {annotation}:\n"
        "    result = value\n    return result\n"
    )
    (root / "sample.py").write_text(source)
    (root / "test_sample.py").write_text(
        "from sample import identity\ndef test_identity():\n    assert identity(2) == 2\n"
    )
    path = root / "sample.manifest.yaml"
    spec_type = expected if expected is not None else annotation
    path.write_text(
        yaml.safe_dump(
            {
                "schema": "2",
                "goal": "Check signature type identity",
                "type": "fix",
                "created": "2026-10-21T00:00:00Z",
                "files": {
                    "create": [
                        {
                            "path": "sample.py",
                            "artifacts": [
                                {
                                    "kind": "function",
                                    "name": "identity",
                                    "args": [{"name": "value", "type": spec_type}],
                                    "returns": spec_type,
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


@pytest.mark.parametrize("left,right", _EQUIVALENT)
def test_nested_type_equivalence_is_symmetric_and_canonical(
    left: str, right: str
) -> None:
    assert types_match(left, right)
    assert types_match(right, left)
    assert normalize_type(left) == normalize_type(right)


@pytest.mark.parametrize("left,right", _DISTINCT)
def test_type_values_metadata_and_plugin_types_remain_distinct(
    left: str, right: str
) -> None:
    assert not types_match(left, right)
    assert not types_match(right, left)


@pytest.mark.parametrize("annotation", _ANNOTATIONS)
def test_python_source_signature_validates_and_snapshot_roundtrips(
    tmp_path: Path, annotation: str
) -> None:
    path = _project(tmp_path, annotation)
    source = (tmp_path / "sample.py").read_text()

    collected = PythonValidator().collect_implementation_artifacts(source, "sample.py")
    assert not collected.errors
    direct = collect_implementation_artifacts(ast.parse(source), "sample.py")
    for artifacts in (collected.artifacts, direct):
        artifact = next(a for a in artifacts if a.name == "identity")
        assert types_match(annotation, artifact.args[0].type)
        assert types_match(artifact.returns, annotation)
    result = ValidationEngine(project_root=tmp_path).validate(
        path, mode=ValidationMode.IMPLEMENTATION
    )
    assert result.success, result.errors

    snapshot = generate_snapshot(tmp_path / "sample.py", project_root=tmp_path)
    snapshot_path = tmp_path / "snapshot.manifest.yaml"
    save_manifest(snapshot, snapshot_path)
    restored = load_manifest(snapshot_path)
    spec = restored.files_snapshot[0].artifacts[0]
    assert types_match(spec.args[0].type, annotation)
    assert types_match(annotation, spec.returns)
    roundtrip = ValidationEngine(project_root=tmp_path).validate(
        snapshot_path, mode=ValidationMode.IMPLEMENTATION
    )
    assert roundtrip.success, roundtrip.errors


@pytest.mark.parametrize(
    "source,expected",
    [
        ("list[int | None]", "list[str | None]"),
        ('Literal["PROXY"]', 'Literal["CANDIDATE"]'),
        ('Literal["1"]', "Literal[1]"),
        ('Annotated[int, "x"]', 'Annotated[int, "y"]'),
    ],
)
def test_public_signature_validation_rejects_semantic_differences(
    tmp_path: Path, source: str, expected: str
) -> None:
    path = _project(tmp_path, source, expected)

    result = ValidationEngine(project_root=tmp_path).validate(
        path, mode=ValidationMode.IMPLEMENTATION
    )

    assert ErrorCode.TYPE_MISMATCH in {e.code for e in result.errors}


@pytest.mark.parametrize("annotation", ["tuple[str, ...]", "tuple[str, Ellipsis]"])
def test_python_legacy_tuple_ellipsis_validation_is_preserved(
    tmp_path: Path, annotation: str
) -> None:
    path = _project(tmp_path, "tuple[str, ...]", annotation)

    result = ValidationEngine(project_root=tmp_path).validate(
        path, mode=ValidationMode.IMPLEMENTATION
    )

    assert result.success, result.errors


@pytest.mark.parametrize(
    "left,right",
    [
        ("Array<string>", "Array< string >"),
        ("Promise<void>", "Promise< void >"),
        ("uint256[]", "uint256 []"),
        ("Option<String>", "Option< String >"),
    ],
)
def test_existing_nonpython_type_spelling_compatibility_is_preserved(
    left: str, right: str
) -> None:
    assert types_match(left, right)
    assert types_match(right, left)
