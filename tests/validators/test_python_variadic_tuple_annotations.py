"""Behavioral contract for canonical Python variadic-tuple annotations."""

from pathlib import Path

import pytest
import yaml

from maid_runner.core._implementation_validation import compare_artifacts
from maid_runner.core.result import ErrorCode
from maid_runner.core.types import ArgSpec, ArtifactKind, ArtifactSpec, ValidationMode
from maid_runner.core.validate import ValidationEngine
from maid_runner.validators.base import FoundArtifact
from maid_runner.validators.python import PythonValidator


def _collect(annotation: str, *, asynchronous: bool = False):
    prefix = "async " if asynchronous else ""
    source = (
        "import typing\nfrom typing import Callable, Tuple\n"
        f"{prefix}def identity(value: {annotation}) -> {annotation}:\n"
        "    return value\n"
    )
    result = PythonValidator().collect_implementation_artifacts(source, "sample.py")
    assert result.errors == []
    return next(
        artifact for artifact in result.artifacts if artifact.name == "identity"
    )


@pytest.mark.parametrize(
    "annotation",
    [
        "tuple[str, ...]",
        "Tuple[str, ...]",
        "typing.Tuple[str, ...]",
        "dict[str, tuple[int, ...]]",
        "Callable[..., str]",
    ],
)
@pytest.mark.parametrize("asynchronous", [False, True])
def test_python_collection_preserves_ellipsis_annotation_syntax(
    annotation, asynchronous
):
    artifact = _collect(annotation, asynchronous=asynchronous)

    assert artifact.args[0].type == annotation
    assert artifact.returns == annotation


@pytest.mark.parametrize(
    "manifest_type",
    ["tuple[str, ...]", "tuple[str, Ellipsis]", " tuple[str, Ellipsis] "],
)
def test_python_implementation_validation_accepts_canonical_and_legacy_tuple_contracts(
    tmp_path: Path, manifest_type
):
    (tmp_path / "sample.py").write_text(
        "def identity(value: tuple[str, ...]) -> tuple[str, ...]:\n    return value\n"
    )
    (tmp_path / "test_sample.py").write_text(
        "from sample import identity\n"
        "def test_identity():\n"
        "    assert identity(('example',)) == ('example',)\n"
    )
    manifest = tmp_path / "sample.manifest.yaml"
    manifest.write_text(
        yaml.safe_dump(
            {
                "schema": "2",
                "goal": "Variadic tuple fixture",
                "type": "fix",
                "created": "2026-09-30T00:00:00Z",
                "files": {
                    "edit": [
                        {
                            "path": "sample.py",
                            "artifacts": [
                                {
                                    "kind": "function",
                                    "name": "identity",
                                    "args": [{"name": "value", "type": manifest_type}],
                                    "returns": manifest_type,
                                }
                            ],
                        }
                    ],
                    "read": ["test_sample.py"],
                },
                "validate": ["python -m pytest -q test_sample.py"],
            }
        )
    )

    result = ValidationEngine(project_root=tmp_path).validate(
        manifest, mode=ValidationMode.IMPLEMENTATION
    )

    assert result.success, [error.message for error in result.errors]


@pytest.mark.parametrize(
    "annotation",
    [
        "tuple[str, ...]",
        "Tuple[str, ...]",
        "typing.Tuple[str, ...]",
        "dict[str, tuple[int, ...]]",
        "tuple[tuple[str, ...], ...]",
    ],
)
@pytest.mark.parametrize("padding", [False, True])
def test_python_comparison_retains_legacy_expected_tuple_spelling(annotation, padding):
    expected_type = annotation.replace("...", "Ellipsis")
    if padding:
        expected_type = f" {expected_type} "
    expected = ArtifactSpec(
        kind=ArtifactKind.FUNCTION,
        name="identity",
        args=(ArgSpec(name="value", type=expected_type),),
        returns=expected_type,
    )
    artifact = _collect(annotation)

    errors = compare_artifacts([expected], [artifact], "sample.py", False)

    assert errors == []
    assert artifact.returns == annotation


@pytest.mark.parametrize("manifest_type", ["tuple[str, ...]", "tuple[str, Ellipsis]"])
def test_python_method_tuple_annotations_keep_canonical_and_legacy_contracts(
    manifest_type,
):
    source = (
        "class Box:\n"
        "    def identity(self, value: tuple[str, ...]) -> tuple[str, ...]:\n"
        "        return value\n"
    )
    collection = PythonValidator().collect_implementation_artifacts(source, "sample.py")
    assert collection.errors == []
    method = next(
        artifact for artifact in collection.artifacts if artifact.name == "identity"
    )
    expected = ArtifactSpec(
        kind=ArtifactKind.METHOD,
        name="identity",
        of="Box",
        args=(ArgSpec(name="value", type=manifest_type),),
        returns=manifest_type,
    )

    errors = compare_artifacts([expected], [method], "sample.py", False)

    assert errors == []
    assert method.args[0].type == "tuple[str, ...]"
    assert method.returns == "tuple[str, ...]"


@pytest.mark.parametrize(
    "actual", ["tuple[int, ...]", "tuple[str, int]", "tuple[str, Ellipsis]"]
)
def test_python_tuple_comparison_still_rejects_distinct_source_types(actual):
    expected = ArtifactSpec(
        kind=ArtifactKind.FUNCTION,
        name="identity",
        args=(ArgSpec(name="value", type="tuple[str, ...]"),),
        returns="tuple[str, ...]",
    )

    errors = compare_artifacts([expected], [_collect(actual)], "sample.py", False)

    assert len(errors) == 2
    assert all(error.code == ErrorCode.TYPE_MISMATCH for error in errors)


def test_legacy_tuple_compatibility_does_not_relax_type_aliases_or_other_languages():
    alias = ArtifactSpec(
        kind=ArtifactKind.TYPE, name="Items", type_annotation="tuple[str, Ellipsis]"
    )
    actual_alias = FoundArtifact(
        kind=ArtifactKind.TYPE, name="Items", type_annotation="tuple[str, ...]"
    )
    alias_errors = compare_artifacts([alias], [actual_alias], "sample.py", False)
    function = ArtifactSpec(
        kind=ArtifactKind.FUNCTION,
        name="identity",
        args=(),
        returns="tuple[str, Ellipsis]",
    )
    actual_function = FoundArtifact(
        kind=ArtifactKind.FUNCTION, name="identity", returns="tuple[str, ...]"
    )

    other_errors = compare_artifacts([function], [actual_function], "sample.ts", False)

    assert [error.code for error in alias_errors] == [ErrorCode.TYPE_MISMATCH]
    assert [error.code for error in other_errors] == [ErrorCode.TYPE_MISMATCH]


@pytest.mark.parametrize(
    "annotation",
    [
        "list[Ellipsis]",
        "Ellipsis",
        "tuple[Ellipsis, str]",
        "tuple[str, Ellipsis, int]",
        "OtherTuple[str, Ellipsis]",
        "Literal['Ellipsis']",
        "tuple[Literal['Ellipsis'], Ellipsis]",
    ],
)
def test_ellipsis_identifiers_outside_variadic_tuple_positions_remain_distinct(
    annotation,
):
    expected = ArtifactSpec(
        kind=ArtifactKind.FUNCTION, name="identity", args=(), returns=annotation
    )
    actual = FoundArtifact(
        kind=ArtifactKind.FUNCTION,
        name="identity",
        returns=annotation.replace("Ellipsis", "..."),
    )

    errors = compare_artifacts([expected], [actual], "sample.py", False)

    assert [error.code for error in errors] == [ErrorCode.TYPE_MISMATCH]


def test_python_snapshot_uses_canonical_tuple_syntax_without_changing_stub_detection():
    source = "def pending(value: tuple[str, ...]) -> tuple[str, ...]:\n    ...\n"
    validator = PythonValidator()

    snapshots = validator.generate_snapshot(source, "sample.py")
    collection = validator.collect_implementation_artifacts(source, "sample.py")

    assert snapshots[0]["returns"] == "tuple[str, ...]"
    assert snapshots[0]["args"][0]["type"] == "tuple[str, ...]"
    assert collection.artifacts[0].is_stub is True
