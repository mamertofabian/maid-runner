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
from maid_runner.validators.typescript import TypeScriptValidator


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
    assert validator.types_match("(int,)", "(int)") is False


@pytest.mark.parametrize(
    "manifest_type,implementation_type",
    [
        (
            "{ id: string; active: boolean }",
            "{\n  id: string;\n  active: boolean;\n}",
        ),
        (
            "(from: number, to: number) => PromiseLike<{ data: T[] | null }>",
            "(\n  from: number,\n  to: number,\n) => PromiseLike<{\n  data: T[] | null;\n}>",
        ),
        (
            "{ allowed: true; reason: 'ready now' } | "
            "{ allowed: false; reason: 'not ready' }",
            '\n  | { allowed: false; reason: "not ready" }\n'
            '  | { allowed: true; reason: "ready now" }',
        ),
        ("{ status: 'it\\'s ready' }", '{ status: "it\'s ready" }'),
        ("{ status: '\\x72eady' }", '{ status: "ready" }'),
        ("{}", "{\n}"),
        ("[]", "[\n]"),
        ("A | B", "B | A /* formatter note */"),
        ("string", "string\n// formatter note"),
        ("A | (B | C)", "C | B | A"),
    ],
)
def test_typescript_formatter_expanded_type_targets_match(
    manifest_type: str,
    implementation_type: str,
) -> None:
    validator = TypeScriptValidator()

    assert validator.types_match(manifest_type, implementation_type) is True


@pytest.mark.parametrize(
    "manifest_type,implementation_type",
    [
        ("{ id: string; active: boolean }", "{ active: boolean; id: string }"),
        ("{ id?: string }", "{ id: string }"),
        ("`a b`", "`a\nb`"),
        ("`a b`", "`ab`"),
        ("`a .< b`", "`a.<b`"),
        ("{ value: `a b` }", "{ value: `ab` }"),
        ("keyof T /* .< */", "keyofT /* .< */"),
        ("Promise<string>", "Promise<string;>"),
        ("'\\01'", "'\\x001'"),
        (r"'\u{110000}'", r'"\u{110000}"'),
        ("string", "string; type Escaped = number"),
        ("string", "string; const escaped = 1"),
        ("A & (B & C)", "C & B & A"),
        (
            '((x: string) => "first") & ((x: string) => "second")',
            '((x: string) => "second") & ((x: string) => "first")',
        ),
    ],
)
def test_typescript_semantically_distinct_type_targets_do_not_match(
    manifest_type: str,
    implementation_type: str,
) -> None:
    validator = TypeScriptValidator()

    assert validator.types_match(manifest_type, implementation_type) is False


def test_typescript_baseline_comparator_errors_propagate(monkeypatch) -> None:
    def raise_comparator_error(self, manifest_type, implementation_type):
        raise RuntimeError("baseline comparator failed")

    monkeypatch.setattr(BaseValidator, "types_match", raise_comparator_error)

    with pytest.raises(RuntimeError, match="baseline comparator failed"):
        TypeScriptValidator().types_match("string", "number")


def test_typescript_excessive_type_depth_fails_closed() -> None:
    validator = TypeScriptValidator()
    deeply_nested = "Box<" * 300 + "string" + ">" * 300

    assert (
        validator.types_match(
            deeply_nested,
            deeply_nested.replace("string", "string /* formatted */"),
        )
        is False
    )
    assert validator.types_match(deeply_nested, deeply_nested) is True
    assert deeply_nested not in validator._type_fingerprints


def test_typescript_string_edge_cases_are_bounded_and_semantic() -> None:
    validator = TypeScriptValidator()
    continued = '"a\\' + chr(0x2028) + 'b"'
    arabic_zero = chr(0x0660)

    assert validator.types_match(continued, '"ab"') is True
    assert validator.types_match(f"'\\{arabic_zero}'", f"'{arabic_zero}'") is True
    assert (
        validator.types_match(
            r"'\uD83D\uDE00\uD800'",
            r"'\u{1F600}\uD800'",
        )
        is True
    )
    assert validator.types_match(chr(0xD800), "string") is False


def test_typescript_wide_type_tree_preserves_baseline_comparison() -> None:
    validator = TypeScriptValidator()
    wide_type = (
        "{ " + "; ".join(f"property{index}: string" for index in range(1_500)) + " }"
    )
    wide_tuple = "[" + ",".join("T" for _ in range(4_095)) + "]"

    assert validator.types_match(wide_type, wide_type.replace("; ", ";\n")) is False
    assert validator.types_match(wide_tuple, wide_tuple.replace(",", ", ")) is True
    assert wide_type not in validator._type_fingerprints
    assert wide_tuple not in validator._type_fingerprints


def test_typescript_parser_failure_preserves_baseline_comparison() -> None:
    class _ExplodingParser:
        def parse(self, source: bytes):
            raise RuntimeError("parser failed")

    validator = TypeScriptValidator()
    parser = validator._ts_parser
    validator._ts_parser = _ExplodingParser()

    assert validator.types_match("Type", " Type ") is True
    validator._ts_parser = parser
    assert validator.types_match("`a b`", "`ab`") is False


@pytest.mark.parametrize(
    "jsdoc_type",
    [
        "Array.<string>",
        "function(string): number",
        "?string",
        "*",
    ],
)
def test_javascript_jsdoc_type_spelling_preserves_exact_match(
    jsdoc_type: str,
) -> None:
    validator = TypeScriptValidator()

    assert validator.types_match(jsdoc_type, jsdoc_type) is True


def test_javascript_jsdoc_preserves_existing_spacing_equivalence() -> None:
    validator = TypeScriptValidator()

    assert validator.types_match("string|number", "string | number") is True
    assert validator.types_match("Array.<string>", "Array.< string >") is True
    assert (
        validator.types_match(
            "function(string): number",
            "function( string ):number",
        )
        is True
    )


def test_typescript_type_fingerprint_cache_is_bounded() -> None:
    validator = TypeScriptValidator()

    for index in range(300):
        type_name = f"Type{index}"
        assert validator.types_match(type_name, f" {type_name} ") is True

    assert len(validator._type_fingerprints) == 256

    oversized = "T" * 65_537
    assert validator.types_match(oversized, f" {oversized}") is True
    assert oversized not in validator._type_fingerprints

    oversized_surrogate = chr(0xD800) + oversized
    assert validator.types_match(oversized_surrogate, "string") is False
    assert oversized_surrogate not in validator._type_fingerprints


def test_formatted_typescript_alias_passes_implementation_validation(
    tmp_path: Path,
) -> None:
    source_path = tmp_path / "src" / "decision.ts"
    source_path.parent.mkdir()
    source_path.write_text(
        "export type Decision =\n"
        '  | { allowed: true; reason: "ready now" }\n'
        '  | { allowed: false; reason: "not ready" };\n'
    )
    test_path = tmp_path / "tests" / "decision.test.ts"
    test_path.parent.mkdir()
    test_path.write_text(
        "import type { Decision } from '../src/decision';\n\n"
        "const decision: Decision = { allowed: true, reason: 'ready now' };\n"
        "if (!decision.allowed) throw new Error('unexpected decision');\n"
    )
    manifest_path = tmp_path / "manifests" / "decision.manifest.yaml"
    manifest_path.parent.mkdir()
    manifest_path.write_text(
        """schema: "2"
goal: "Declare a decision result"
files:
  create:
    - path: src/decision.ts
      artifacts:
        - kind: type
          name: Decision
          type: >-
            { allowed: true; reason: 'ready now' } | { allowed: false; reason: 'not ready' }
  read:
    - tests/decision.test.ts
validate:
  - pytest tests/decision.test.ts -q
"""
    )

    result = ValidationEngine(project_root=tmp_path).validate(
        manifest_path,
        mode=ValidationMode.IMPLEMENTATION,
    )

    type_mismatches = [
        error for error in result.errors if error.code == ErrorCode.TYPE_MISMATCH
    ]
    assert type_mismatches == []
    assert result.success is True, [error.message for error in result.errors]


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
