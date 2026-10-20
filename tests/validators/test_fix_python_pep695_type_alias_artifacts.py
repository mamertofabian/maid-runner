"""Public PEP695 module aliases retain their existing artifact metadata contract."""

from __future__ import annotations

import ast
from pathlib import Path

import pytest
import yaml

from maid_runner.core.manifest import load_manifest, save_manifest
from maid_runner.core.result import ErrorCode
from maid_runner.core.snapshot import generate_snapshot
from maid_runner.core.types import ArtifactKind, ValidationMode
from maid_runner.core.validate import ValidationEngine
from maid_runner.validators._python_implementation import (
    collect_implementation_artifacts,
)
from maid_runner.validators.python import PythonValidator

_SUPPORTED = hasattr(ast, "TypeAlias")
_CASES = [
    ("type Conn = tuple[int, ...]", "tuple[int, ...]", ()),
    (
        "# Reported qualified connection target\n\ntype Conn = psycopg.AsyncConnection[tuple[Any, ...]]",
        "psycopg.AsyncConnection[tuple[Any, ...]]",
        (),
    ),
    ("type Conn[T] = tuple[T, T]", "tuple[T, T]", ("T",)),
    ("type Conn[T: int] = list[T]", "list[T]", ("T: int",)),
    ("type Conn[*Ts] = tuple[*Ts]", "tuple[*Ts]", ("*Ts",)),
    ("type Conn[**P] = Callable[P, int]", "Callable[P, int]", ("**P",)),
    ("type Conn = Literal['read', 'write']", "Literal['read', 'write']", ()),
    ("type Conn = str | 'Conn'", "Union[str, Conn]", ()),
]


def _project(root: Path, source: str, target: str, parameters: tuple[str, ...]) -> Path:
    (root / "manifests").mkdir()
    (root / "tests").mkdir()
    (root / "catalog.py").write_text(source + "\n")
    (root / "tests/test_catalog.py").write_text(
        "from catalog import Conn\ndef test_alias():\n    assert Conn is not None\n"
    )
    path = root / "manifests/catalog.manifest.yaml"
    path.write_text(
        yaml.safe_dump(
            {
                "schema": "2",
                "goal": "Declare a module type alias",
                "type": "fix",
                "created": "2026-10-21T00:00:00Z",
                "files": {
                    "create": [
                        {
                            "path": "catalog.py",
                            "artifacts": [
                                {
                                    "kind": "type",
                                    "name": "Conn",
                                    "type": target,
                                    "type_parameters": list(parameters),
                                }
                            ],
                        }
                    ],
                    "read": ["tests/test_catalog.py"],
                },
                "validate": [["python", "-m", "pytest", "tests/test_catalog.py", "-q"]],
            }
        )
    )
    return path


@pytest.mark.skipif(not _SUPPORTED, reason="PEP695 requires Python3.12+")
@pytest.mark.parametrize("source,target,parameters", _CASES)
def test_pep695_alias_metadata_survives_public_collection_and_snapshot(
    tmp_path: Path, source: str, target: str, parameters: tuple[str, ...]
) -> None:
    path = _project(tmp_path, source, target, parameters)
    collector = PythonValidator().collect_implementation_artifacts(source, "catalog.py")
    direct = collect_implementation_artifacts(ast.parse(source), "catalog.py")

    assert not collector.errors
    for artifacts in (collector.artifacts, direct):
        (alias,) = artifacts
        assert (alias.kind, alias.name, alias.of) == (ArtifactKind.TYPE, "Conn", None)
        assert alias.type_annotation == target
        assert alias.type_parameters == parameters
        assert alias.line == len(source.splitlines())
    result = ValidationEngine(project_root=tmp_path).validate(
        path, mode=ValidationMode.IMPLEMENTATION
    )
    assert result.success, result.errors

    snapshot = generate_snapshot(tmp_path / "catalog.py", project_root=tmp_path)
    snapshot_path = tmp_path / "manifests/snapshot.manifest.yaml"
    save_manifest(snapshot, snapshot_path)
    restored = load_manifest(snapshot_path)
    (alias,) = restored.files_snapshot[0].artifacts
    assert (alias.kind, alias.name, alias.type_annotation, alias.type_parameters) == (
        ArtifactKind.TYPE,
        "Conn",
        target,
        parameters,
    )
    roundtrip = ValidationEngine(project_root=tmp_path).validate(
        snapshot_path, mode=ValidationMode.IMPLEMENTATION
    )
    assert roundtrip.success, roundtrip.errors


@pytest.mark.skipif(not _SUPPORTED, reason="PEP695 requires Python3.12+")
@pytest.mark.parametrize("mismatch", ["target", "parameters"])
def test_pep695_exact_implementation_rejects_wrong_contract(
    tmp_path: Path, mismatch: str
) -> None:
    target = "list[T]" if mismatch == "target" else "tuple[T, T]"
    parameters = ("U",) if mismatch == "parameters" else ("T",)
    path = _project(tmp_path, "type Conn[T] = tuple[T, T]", target, parameters)

    result = ValidationEngine(project_root=tmp_path).validate(
        path, mode=ValidationMode.IMPLEMENTATION
    )

    assert ErrorCode.TYPE_MISMATCH in {error.code for error in result.errors}
    assert not any(
        error.code == ErrorCode.ARTIFACT_NOT_DEFINED for error in result.errors
    )


@pytest.mark.parametrize(
    "source",
    [
        "from typing import TypeAlias\nConn: TypeAlias = tuple[int, ...]",
        "import typing as t\nConn: t.TypeAlias = tuple[int, ...]",
    ],
)
def test_legacy_type_alias_definition_and_validation_stay_compatible(
    tmp_path: Path, source: str
) -> None:
    path = _project(tmp_path, source, "tuple[int, ...]", ())

    result = ValidationEngine(project_root=tmp_path).validate(
        path, mode=ValidationMode.IMPLEMENTATION
    )

    assert result.success, result.errors
    snapshot = generate_snapshot(tmp_path / "catalog.py", project_root=tmp_path)
    snapshot_path = tmp_path / "manifests/snapshot.manifest.yaml"
    save_manifest(snapshot, snapshot_path)
    restored = load_manifest(snapshot_path)
    (alias,) = restored.files_snapshot[0].artifacts
    assert (alias.name, alias.type_annotation, alias.type_parameters) == (
        "Conn",
        "tuple[int, ...]",
        (),
    )
    roundtrip = ValidationEngine(project_root=tmp_path).validate(
        snapshot_path, mode=ValidationMode.IMPLEMENTATION
    )
    assert roundtrip.success, roundtrip.errors


@pytest.mark.skipif(not _SUPPORTED, reason="PEP695 requires Python3.12+")
@pytest.mark.parametrize(
    "imports,alias,base",
    [
        ("from typing import Protocol", "Protocol", "Protocol"),
        ("from typing import Protocol as P", "P", "P"),
        ("import typing", "typing", "typing.Protocol"),
        ("import typing_extensions as t", "t", "t.Protocol"),
    ],
)
def test_pep695_alias_binding_invalidates_known_protocol_identity(
    imports: str, alias: str, base: str
) -> None:
    source = f"{imports}\ntype {alias} = int\nclass Reader({base}):\n    def read(self) -> str: ...\n"

    result = PythonValidator().collect_implementation_artifacts(source, "catalog.py")

    assert not result.errors
    method = next(artifact for artifact in result.artifacts if artifact.name == "read")
    assert method.is_stub is True


@pytest.mark.skipif(not _SUPPORTED, reason="PEP695 requires Python3.12+")
def test_pep695_type_parameter_names_do_not_rebind_module_protocol() -> None:
    source = "from typing import Protocol\ntype Conn[Protocol] = list[Protocol]\nclass Reader(Protocol):\n    def read(self) -> str: ...\n"

    result = PythonValidator().collect_implementation_artifacts(source, "catalog.py")

    assert not result.errors
    method = next(artifact for artifact in result.artifacts if artifact.name == "read")
    assert method.is_stub is False


@pytest.mark.skipif(not _SUPPORTED, reason="PEP695 requires Python3.12+")
def test_pep695_private_alias_filtering_and_local_class_scope_are_preserved(
    tmp_path: Path,
) -> None:
    source = "type Conn = int\ntype _Hidden = str\nclass Container:\n    type Member = int\ndef factory():\n    type Local = int\n    return Local\n"
    path = tmp_path / "catalog.py"
    path.write_text(source)

    result = PythonValidator().collect_implementation_artifacts(source, path)
    public = generate_snapshot(path, project_root=tmp_path)
    complete = generate_snapshot(path, project_root=tmp_path, include_private=True)

    assert not result.errors
    assert {
        artifact.name
        for artifact in result.artifacts
        if artifact.kind == ArtifactKind.TYPE
    } == {"Conn", "_Hidden"}
    assert {
        artifact.name
        for artifact in public.files_snapshot[0].artifacts
        if artifact.kind == ArtifactKind.TYPE
    } == {"Conn"}
    assert {
        artifact.name
        for artifact in complete.files_snapshot[0].artifacts
        if artifact.kind == ArtifactKind.TYPE
    } == {"Conn", "_Hidden"}


def test_pep695_unsupported_or_malformed_syntax_is_an_explicit_parse_error() -> None:
    source = (
        "type Conn = tuple[int, ...]"
        if not _SUPPORTED
        else "type Conn[T = tuple[int, ...]"
    )

    result = PythonValidator().collect_implementation_artifacts(source, "catalog.py")

    assert result.errors
    assert not result.artifacts
