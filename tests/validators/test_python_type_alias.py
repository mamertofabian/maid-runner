"""Behavioral contract for Python 3.10-compatible public type aliases."""

from __future__ import annotations

from pathlib import Path

import pytest

from maid_runner.core.result import ErrorCode
from maid_runner.core.types import ValidationMode
from maid_runner.core.validate import ValidationEngine


def _write_alias_project(tmp_path: Path, source: str, alias_type: str) -> Path:
    (tmp_path / "manifests").mkdir()
    (tmp_path / "src").mkdir()
    (tmp_path / "tests").mkdir()
    (tmp_path / "src" / "catalog.py").write_text(source)
    (tmp_path / "tests" / "test_catalog.py").write_text(
        "from src.catalog import JsonObject, JsonValue\n\n"
        "def test_aliases_are_importable():\n"
        "    value: JsonObject = {'answer': 42}\n"
        "    assert isinstance(value['answer'], int)\n"
        "    assert JsonObject is not None\n"
        "    assert JsonValue is not None\n"
    )
    manifest_path = tmp_path / "manifests" / "catalog.manifest.yaml"
    manifest_path.write_text(
        f"""schema: "2"
goal: "Declare JSON aliases"
type: feature
created: "2026-08-20T00:00:00Z"
files:
  create:
    - path: src/catalog.py
      artifacts:
        - kind: type
          name: JsonValue
          type: "str | int | None | list[JsonValue] | dict[str, JsonValue]"
        - kind: type
          name: JsonObject
          type: "{alias_type}"
  read:
    - tests/test_catalog.py
validate:
  - pytest tests/test_catalog.py -q
"""
    )
    return manifest_path


@pytest.mark.parametrize(
    "source",
    (
        """from typing import TypeAlias

JsonValue: TypeAlias = str | int | None | list[\"JsonValue\"] | dict[str, \"JsonValue\"]
JsonObject: TypeAlias = dict[str, JsonValue]
""",
        """import typing as t

JsonValue: t.TypeAlias = str | int | None | list[\"JsonValue\"] | dict[str, \"JsonValue\"]
JsonObject: t.TypeAlias = dict[str, JsonValue]
""",
    ),
)
def test_python_type_aliases_pass_exact_implementation_validation(
    tmp_path: Path, source: str
) -> None:
    manifest_path = _write_alias_project(tmp_path, source, "dict[str, JsonValue]")

    result = ValidationEngine(project_root=tmp_path).validate(
        manifest_path, mode=ValidationMode.IMPLEMENTATION
    )

    assert result.success is True, [error.message for error in result.errors]


def test_python_type_alias_target_mismatch_reports_e302(tmp_path: Path) -> None:
    manifest_path = _write_alias_project(
        tmp_path,
        """from typing import TypeAlias

JsonValue: TypeAlias = str | int | None | list[\"JsonValue\"] | dict[str, \"JsonValue\"]
JsonObject: TypeAlias = list[JsonValue]
""",
        "dict[str, JsonValue]",
    )

    result = ValidationEngine(project_root=tmp_path).validate(
        manifest_path, mode=ValidationMode.IMPLEMENTATION
    )

    assert ErrorCode.TYPE_MISMATCH in {error.code for error in result.errors}
    assert any("JsonObject" in error.message for error in result.errors)


def test_python_type_alias_literal_target_preserves_quoted_values(
    tmp_path: Path,
) -> None:
    manifest_path = _write_alias_project(
        tmp_path,
        """from typing import Literal, TypeAlias

JsonValue: TypeAlias = str | int | None | list["JsonValue"] | dict[str, "JsonValue"]
JsonObject: TypeAlias = Literal["read", "write"]
""",
        "Literal['read', 'write']",
    )

    exact_result = ValidationEngine(project_root=tmp_path).validate(
        manifest_path, mode=ValidationMode.IMPLEMENTATION
    )

    assert exact_result.success is True, [
        error.message for error in exact_result.errors
    ]

    manifest_path.write_text(
        manifest_path.read_text().replace(
            "type: \"Literal['read', 'write']\"",
            'type: \'Literal["read", "write"]\'',
        )
    )
    equivalent_result = ValidationEngine(project_root=tmp_path).validate(
        manifest_path, mode=ValidationMode.IMPLEMENTATION
    )

    assert equivalent_result.success is True, [
        error.message for error in equivalent_result.errors
    ]

    manifest_path.write_text(
        manifest_path.read_text().replace(
            'type: \'Literal["read", "write"]\'',
            'type: "Literal[read, write]"',
        )
    )
    mismatch_result = ValidationEngine(project_root=tmp_path).validate(
        manifest_path, mode=ValidationMode.IMPLEMENTATION
    )

    assert ErrorCode.TYPE_MISMATCH in {error.code for error in mismatch_result.errors}
    assert any("JsonObject" in error.message for error in mismatch_result.errors)

    manifest_path.write_text(
        manifest_path.read_text().replace(
            "Literal[read, write]",
            "Literal[__maid_quoted_277265616427__, write]",
        )
    )
    collision_result = ValidationEngine(project_root=tmp_path).validate(
        manifest_path, mode=ValidationMode.IMPLEMENTATION
    )

    assert ErrorCode.TYPE_MISMATCH in {error.code for error in collision_result.errors}


def test_python_type_alias_value_metadata_preserves_source_semantics(
    tmp_path: Path,
) -> None:
    json_value = 'str | int | None | list["JsonValue"] | dict[str, "JsonValue"]'

    ellipsis_root = tmp_path / "ellipsis"
    ellipsis_root.mkdir()
    ellipsis_manifest = _write_alias_project(
        ellipsis_root,
        f"""from typing import TypeAlias

JsonValue: TypeAlias = {json_value}
JsonObject: TypeAlias = tuple[int, ...]
""",
        "tuple[int, ...]",
    )
    ellipsis_exact = ValidationEngine(project_root=ellipsis_root).validate(
        ellipsis_manifest, mode=ValidationMode.IMPLEMENTATION
    )
    assert ellipsis_exact.success is True, [
        error.message for error in ellipsis_exact.errors
    ]

    ellipsis_manifest.write_text(
        ellipsis_manifest.read_text().replace("tuple[int, ...]", "tuple[int, Ellipsis]")
    )
    ellipsis_mismatch = ValidationEngine(project_root=ellipsis_root).validate(
        ellipsis_manifest, mode=ValidationMode.IMPLEMENTATION
    )
    assert ErrorCode.TYPE_MISMATCH in {error.code for error in ellipsis_mismatch.errors}

    annotated_root = tmp_path / "annotated"
    annotated_root.mkdir()
    annotated_manifest = _write_alias_project(
        annotated_root,
        f"""from typing import Annotated, TypeAlias

JsonValue: TypeAlias = {json_value}
JsonObject: TypeAlias = Annotated[str, "tag"]
""",
        "Annotated[str, 'tag']",
    )
    annotated_exact = ValidationEngine(project_root=annotated_root).validate(
        annotated_manifest, mode=ValidationMode.IMPLEMENTATION
    )
    assert annotated_exact.success is True, [
        error.message for error in annotated_exact.errors
    ]

    annotated_manifest.write_text(
        annotated_manifest.read_text().replace(
            "Annotated[str, 'tag']", "Annotated[str, tag]"
        )
    )
    annotated_mismatch = ValidationEngine(project_root=annotated_root).validate(
        annotated_manifest, mode=ValidationMode.IMPLEMENTATION
    )
    assert ErrorCode.TYPE_MISMATCH in {
        error.code for error in annotated_mismatch.errors
    }


def test_literal_value_rendering_change_is_scoped_to_alias_targets(
    tmp_path: Path,
) -> None:
    (tmp_path / "manifests").mkdir()
    (tmp_path / "src").mkdir()
    (tmp_path / "tests").mkdir()
    (tmp_path / "src" / "mode.py").write_text(
        """from typing import Literal

def choose(mode: Literal["read", "write"]) -> Literal["read", "write"]:
    return mode
"""
    )
    (tmp_path / "tests" / "test_mode.py").write_text(
        "from src.mode import choose\n\n"
        "def test_choose():\n"
        "    assert choose('read') == 'read'\n"
    )
    manifest_path = tmp_path / "manifests" / "mode.manifest.yaml"
    manifest_path.write_text(
        """schema: "2"
goal: "Keep ordinary Literal annotations stable"
type: fix
created: "2026-08-20T00:00:00Z"
files:
  create:
    - path: src/mode.py
      artifacts:
        - kind: function
          name: choose
          args:
            - {name: mode, type: "Literal[read, write]"}
          returns: "Literal[read, write]"
  read:
    - tests/test_mode.py
validate:
  - pytest tests/test_mode.py -q
"""
    )

    result = ValidationEngine(project_root=tmp_path).validate(
        manifest_path, mode=ValidationMode.IMPLEMENTATION
    )

    assert result.success is True, [error.message for error in result.errors]


def test_ordinary_annotated_assignment_does_not_satisfy_type_artifact(
    tmp_path: Path,
) -> None:
    manifest_path = _write_alias_project(
        tmp_path,
        """from typing import Any

JsonValue: Any = str
JsonObject: Any = dict
""",
        "dict[str, JsonValue]",
    )

    result = ValidationEngine(project_root=tmp_path).validate(
        manifest_path, mode=ValidationMode.IMPLEMENTATION
    )

    assert ErrorCode.ARTIFACT_NOT_DEFINED in {error.code for error in result.errors}
