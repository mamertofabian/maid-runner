"""Behavioral contract for validator-owned type comparison."""

from __future__ import annotations

from pathlib import Path

import pytest

from maid_runner.core.result import ErrorCode
from maid_runner.core.types import ArgSpec, ArtifactKind, ValidationMode
from maid_runner.core.validate import ValidationEngine
from maid_runner.validators.base import BaseValidator, CollectionResult, FoundArtifact
from maid_runner.validators.python import PythonValidator
from maid_runner.validators.registry import ValidatorRegistry


class _DefaultValidator(BaseValidator):
    @classmethod
    def supported_extensions(cls) -> tuple[str, ...]:
        return (".default",)

    def collect_implementation_artifacts(self, source, file_path):
        return CollectionResult([], "default", str(file_path))

    def collect_behavioral_artifacts(self, source, file_path):
        return CollectionResult([], "default", str(file_path))


class _AliasValidator(BaseValidator):
    def __init__(self) -> None:
        self.comparisons: list[tuple[str | None, str | None]] = []

    @classmethod
    def supported_extensions(cls) -> tuple[str, ...]:
        return (".alias",)

    def collect_implementation_artifacts(self, source, file_path):
        return CollectionResult(
            artifacts=[
                FoundArtifact(
                    kind=ArtifactKind.FUNCTION,
                    name="convert",
                    args=(ArgSpec(name="value", type="System.Int32"),),
                    returns="System.String",
                )
            ],
            language="alias",
            file_path=str(file_path),
        )

    def collect_behavioral_artifacts(self, source, file_path):
        return CollectionResult([], "alias", str(file_path))

    def types_match(
        self,
        manifest_type: str | None,
        implementation_type: str | None,
    ) -> bool:
        self.comparisons.append((manifest_type, implementation_type))
        aliases = {
            "int": "System.Int32",
            "string": "System.String",
        }
        return aliases.get(manifest_type, manifest_type) == implementation_type


class _RejectingValidator(_AliasValidator):
    @classmethod
    def supported_extensions(cls) -> tuple[str, ...]:
        return (".reject",)

    def types_match(
        self,
        manifest_type: str | None,
        implementation_type: str | None,
    ) -> bool:
        self.comparisons.append((manifest_type, implementation_type))
        return False


class _ExplodingValidator(_AliasValidator):
    @classmethod
    def supported_extensions(cls) -> tuple[str, ...]:
        return (".explode",)

    def collect_implementation_artifacts(self, source, file_path):
        return CollectionResult(
            artifacts=[
                FoundArtifact(
                    kind=ArtifactKind.FUNCTION,
                    name="convert",
                    returns="List[str]",
                )
            ],
            language="explode",
            file_path=str(file_path),
        )

    def types_match(
        self,
        manifest_type: str | None,
        implementation_type: str | None,
    ) -> bool:
        raise RuntimeError("plugin comparator failed")


def _write_project(
    project: Path,
    *,
    extension: str,
    manifest_return: str,
    include_argument: bool = False,
) -> Path:
    source_path = project / "src" / f"service{extension}"
    source_path.parent.mkdir()
    source_path.write_text("implementation is supplied by the test validator\n")
    test_path = project / "tests" / "test_service.py"
    test_path.parent.mkdir()
    test_path.write_text(
        "from src.service import convert\n\n"
        "def test_convert_is_exposed():\n"
        "    assert convert is not None\n"
    )

    argument = ""
    if include_argument:
        argument = """\
          args:
            - name: value
              type: int
"""

    manifest_path = project / "manifests" / "feature.manifest.yaml"
    manifest_path.parent.mkdir()
    manifest_path.write_text(
        f"""\
schema: "2"
goal: "Exercise a validator-owned type comparator"
files:
  create:
    - path: src/service{extension}
      artifacts:
        - kind: function
          name: convert
{argument}          returns: {manifest_return}
  read:
    - tests/test_service.py
validate:
  - pytest tests/test_service.py -v
"""
    )
    return manifest_path


def _engine(project: Path, validator_class: type[BaseValidator]):
    registry = ValidatorRegistry()
    registry.register(PythonValidator)
    registry.register(validator_class)
    return ValidationEngine(project_root=project, registry=registry), registry


def test_base_validator_type_match_hook_preserves_default_comparison() -> None:
    validator = _DefaultValidator()

    assert validator.types_match(None, "str") is True
    assert validator.types_match("str", None) is False
    assert validator.types_match("Optional[str]", "str | None") is True
    assert validator.types_match("list[str]", "List[str]") is True


def test_validation_engine_preserves_builtin_default_type_comparison(
    tmp_path: Path,
) -> None:
    source_path = tmp_path / "src" / "service.py"
    source_path.parent.mkdir()
    source_path.write_text(
        "def convert(value: str | None) -> list[str]:\n"
        "    return [] if value is None else [value]\n"
    )
    test_path = tmp_path / "tests" / "test_service.py"
    test_path.parent.mkdir()
    test_path.write_text(
        "from src.service import convert\n\n"
        "def test_convert_handles_none():\n"
        "    assert convert(None) == []\n"
    )
    manifest_path = tmp_path / "manifests" / "feature.manifest.yaml"
    manifest_path.parent.mkdir()
    manifest_path.write_text(
        """\
schema: "2"
goal: "Preserve built-in type comparison"
files:
  create:
    - path: src/service.py
      artifacts:
        - kind: function
          name: convert
          args:
            - name: value
              type: Optional[str]
          returns: List[str]
  read:
    - tests/test_service.py
validate:
  - pytest tests/test_service.py -v
"""
    )
    engine, _ = _engine(tmp_path, _DefaultValidator)

    result = engine.validate(manifest_path, mode=ValidationMode.IMPLEMENTATION)

    assert result.success is True
    assert result.errors == []


def test_validation_engine_uses_registered_validator_type_match_hook(
    tmp_path: Path,
) -> None:
    manifest_path = _write_project(
        tmp_path,
        extension=".alias",
        manifest_return="string",
        include_argument=True,
    )
    engine, registry = _engine(tmp_path, _AliasValidator)

    result = engine.validate(manifest_path, mode=ValidationMode.IMPLEMENTATION)

    assert result.success is True
    validator = registry.get("src/service.alias")
    assert isinstance(validator, _AliasValidator)
    assert validator.comparisons == [
        ("int", "System.Int32"),
        ("string", "System.String"),
    ]
    assert validator.generate_snapshot("ignored", "src/service.alias") == [
        {
            "kind": "function",
            "name": "convert",
            "args": [{"name": "value", "type": "System.Int32"}],
            "returns": "System.String",
        }
    ]


def test_validator_type_match_rejection_preserves_raw_mismatch_diagnostic(
    tmp_path: Path,
) -> None:
    manifest_path = _write_project(
        tmp_path,
        extension=".reject",
        manifest_return="Guid",
    )
    engine, registry = _engine(tmp_path, _RejectingValidator)

    result = engine.validate(manifest_path, mode=ValidationMode.IMPLEMENTATION)

    mismatches = [
        error for error in result.errors if error.code == ErrorCode.TYPE_MISMATCH
    ]
    assert len(mismatches) == 1
    assert "expected 'Guid', got 'System.String'" in mismatches[0].message
    validator = registry.get("src/service.reject")
    assert isinstance(validator, _RejectingValidator)
    assert validator.comparisons == [("Guid", "System.String")]


def test_validator_type_match_failure_does_not_fallback_to_global_comparator(
    tmp_path: Path,
) -> None:
    manifest_path = _write_project(
        tmp_path,
        extension=".explode",
        manifest_return="list[str]",
    )
    engine, _ = _engine(tmp_path, _ExplodingValidator)

    with pytest.raises(RuntimeError, match="plugin comparator failed"):
        engine.validate(manifest_path, mode=ValidationMode.IMPLEMENTATION)


def test_plugin_authoring_guide_documents_type_comparison_hook() -> None:
    guide = (
        Path(__file__).resolve().parents[2] / "docs" / "validator-plugin-authoring.md"
    )
    content = guide.read_text(encoding="utf-8")

    assert "BaseValidator.types_match" in content
    assert "existing default comparator" in content
    assert "raw type spellings" in content
    assert "deterministic" in content
    assert "fail loud" in content
