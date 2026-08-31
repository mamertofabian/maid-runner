"""Behavioral coverage for TypeScript predicate return annotations."""

from __future__ import annotations

from pathlib import Path

from maid_runner.core.result import ErrorCode
from maid_runner.core.types import ArtifactKind, ValidationMode
from maid_runner.core.validate import ValidationEngine
from maid_runner.validators.typescript import TypeScriptValidator


def _artifact(result, name: str, kind: ArtifactKind):
    return next(
        artifact
        for artifact in result.artifacts
        if artifact.name == name and artifact.kind == kind
    )


def test_collects_type_predicate_returns_from_function_like_declarations() -> None:
    source = """export function isString(value: unknown): value is string {
  return typeof value === "string";
}

export const isNumber = (value: unknown): value is number =>
  typeof value === "number";

export class Guard {
  isDefined(value: unknown): value is object {
    return value !== null;
  }

  isReady(): this is Guard & { ready: true } {
    return true;
  }
}

export interface GuardContract {
  accepts(value: unknown): value is string;
}
"""

    result = TypeScriptValidator().collect_implementation_artifacts(
        source, "src/guards.ts"
    )

    assert result.errors == []
    assert _artifact(result, "isString", ArtifactKind.FUNCTION).returns == (
        "value is string"
    )
    assert _artifact(result, "isNumber", ArtifactKind.FUNCTION).returns == (
        "value is number"
    )
    assert _artifact(result, "isDefined", ArtifactKind.METHOD).returns == (
        "value is object"
    )
    assert _artifact(result, "isReady", ArtifactKind.METHOD).returns == (
        "this is Guard & { ready: true }"
    )
    assert _artifact(result, "accepts", ArtifactKind.METHOD).returns == (
        "value is string"
    )


def test_collects_assertion_signature_returns() -> None:
    source = """export function assertString(
  value: unknown,
): asserts value is string {
  if (typeof value !== "string") throw new TypeError("expected string");
}

export function assertCondition(
  condition: unknown,
): asserts condition {
  if (!condition) throw new Error("assertion failed");
}
"""

    result = TypeScriptValidator().collect_implementation_artifacts(
        source, "src/assertions.ts"
    )

    assert result.errors == []
    assert _artifact(result, "assertString", ArtifactKind.FUNCTION).returns == (
        "asserts value is string"
    )
    assert _artifact(result, "assertCondition", ArtifactKind.FUNCTION).returns == (
        "asserts condition"
    )
    assert [
        (argument.name, argument.type)
        for argument in _artifact(result, "assertString", ArtifactKind.FUNCTION).args
    ] == [("value", "unknown")]


def test_type_predicate_contract_avoids_false_missing_return_warning(
    tmp_path: Path,
) -> None:
    source_path = tmp_path / "src" / "geo-distance.ts"
    source_path.parent.mkdir()
    source_path.write_text(
        """export interface GeoPoint {
  latitude: number;
  longitude: number;
}

export function isUsableGeoPoint(value: unknown): value is GeoPoint {
  return typeof value === "object" && value !== null;
}
"""
    )
    test_path = tmp_path / "tests" / "geo-distance.test.ts"
    test_path.parent.mkdir()
    test_path.write_text(
        """import { isUsableGeoPoint } from "../src/geo-distance";

if (!isUsableGeoPoint({ latitude: 1, longitude: 2 })) {
  throw new Error("expected a usable point");
}
"""
    )
    manifest_path = tmp_path / "manifests" / "geo-distance.manifest.yaml"
    manifest_path.parent.mkdir()
    manifest_path.write_text(
        """schema: "2"
goal: "Validate a geographic point predicate"
files:
  edit:
    - path: src/geo-distance.ts
      artifacts:
        - kind: function
          name: isUsableGeoPoint
          args:
            - name: value
              type: unknown
          returns: 'value is GeoPoint'
  read:
    - tests/geo-distance.test.ts
validate:
  - pytest tests/geo-distance.test.ts -q
"""
    )

    result = ValidationEngine(project_root=tmp_path).validate(
        manifest_path,
        mode=ValidationMode.IMPLEMENTATION,
    )

    predicate_diagnostics = [
        diagnostic
        for diagnostic in [*result.errors, *result.warnings]
        if diagnostic.code in {ErrorCode.MISSING_RETURN_TYPE, ErrorCode.TYPE_MISMATCH}
    ]
    assert predicate_diagnostics == []
