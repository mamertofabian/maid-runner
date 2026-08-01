"""Behavioral contract for exact plugin-owned artifact signatures."""

from __future__ import annotations

from copy import deepcopy
from pathlib import Path

import yaml
import pytest

from maid_runner.core._implementation_validation import (
    _check_stub_artifacts,
    compare_artifacts,
)
from maid_runner.core.chain import ManifestChain
from maid_runner.core.diff_scope import DiffScopeResult, FileArtifactDelta, _file_delta
from maid_runner.core.identity import match_artifact_to_references
from maid_runner.core.manifest import (
    load_manifest,
    load_manifest_raw,
    save_manifest,
    validate_manifest_schema,
)
from maid_runner.core.manifest_from_diff import build_from_diff_manifest
from maid_runner.core.plan_lock import compute_manifest_contract_hash
from maid_runner.core.result import ErrorCode
from maid_runner.core.supersession_audit import SupersessionAuditor
from maid_runner.core.types import ArtifactKind, ArtifactSpec, ValidationMode
from maid_runner.core.validate import ValidationEngine
from maid_runner.core.validate_suggestions import _references_artifact
from maid_runner.validators.base import BaseValidator, CollectionResult, FoundArtifact
from maid_runner.validators.registry import ValidatorRegistry

INT_SIGNATURE = "Convert(System.Int32)"
STRING_SIGNATURE = "Convert(System.String)"


def _found_overloads() -> list[FoundArtifact]:
    return [
        FoundArtifact(
            kind=ArtifactKind.METHOD,
            name="Convert",
            of="Converter",
            returns="int",
            signature=INT_SIGNATURE,
            is_stub=True,
            line=10,
        ),
        FoundArtifact(
            kind=ArtifactKind.METHOD,
            name="Convert",
            of="Converter",
            returns="str",
            signature=STRING_SIGNATURE,
            line=20,
        ),
    ]


class _SignatureValidator(BaseValidator):
    @classmethod
    def supported_extensions(cls) -> tuple[str, ...]:
        return (".signed", ".cs")

    def collect_implementation_artifacts(self, source, file_path):
        return CollectionResult(
            artifacts=_found_overloads(),
            language="signed",
            file_path=str(file_path),
        )

    def collect_behavioral_artifacts(self, source, file_path):
        signatures = []
        if "reference:int" in source:
            signatures.append(INT_SIGNATURE)
        if "reference:string" in source:
            signatures.append(STRING_SIGNATURE)
        if not signatures:
            signatures.append(None)
        return CollectionResult(
            artifacts=[
                FoundArtifact(
                    kind=ArtifactKind.METHOD,
                    name="Convert",
                    of="Converter",
                    reference_context="call",
                    signature=signature,
                )
                for signature in signatures
            ],
            language="signed",
            file_path=str(file_path),
        )


def _artifact(signature: str | None) -> ArtifactSpec:
    return ArtifactSpec(
        kind=ArtifactKind.METHOD,
        name="Convert",
        of="Converter",
        signature=signature,
    )


def _manifest_data(signatures: list[str | None]) -> dict:
    artifacts = []
    for signature in signatures:
        artifact = {"kind": "method", "name": "Convert", "of": "Converter"}
        if signature is not None:
            artifact["signature"] = signature
        artifacts.append(artifact)
    return {
        "schema": "2",
        "goal": "Exercise exact overload signatures",
        "files": {
            "create": [
                {
                    "path": "src/Converter.signed",
                    "artifacts": artifacts,
                }
            ],
            "read": ["tests/ConverterTests.cs"],
        },
        "validate": [["pytest", "tests/ConverterTests.cs", "-v"]],
    }


def _write_project(
    root: Path,
    signatures: list[str | None],
    reference_marker: str = "reference:int\nreference:string",
) -> Path:
    source_path = root / "src" / "Converter.signed"
    source_path.parent.mkdir(parents=True)
    source_path.write_text("implementation supplied by signature validator\n")
    test_path = root / "tests" / "ConverterTests.cs"
    test_path.parent.mkdir(parents=True)
    test_path.write_text(reference_marker + "\n")
    manifest_path = root / "manifests" / "overloads.manifest.yaml"
    manifest_path.parent.mkdir(parents=True)
    manifest_path.write_text(
        yaml.safe_dump(_manifest_data(signatures), sort_keys=False)
    )
    return manifest_path


def _registry() -> ValidatorRegistry:
    registry = ValidatorRegistry()
    registry.register(_SignatureValidator)
    return registry


def _supersession_violations(
    root: Path,
    old_signatures: list[str | None],
    replacement_signatures: list[str | None],
):
    manifests = root / "manifests"
    manifests.mkdir(parents=True)
    old_data = _manifest_data(old_signatures)
    old_data["created"] = "2026-08-01T00:00:00Z"
    (manifests / "old.manifest.yaml").write_text(
        yaml.safe_dump(old_data, sort_keys=False)
    )
    replacement = _manifest_data(replacement_signatures)
    replacement["created"] = "2026-08-01T00:01:00Z"
    replacement["supersedes"] = ["old"]
    (manifests / "replacement.manifest.yaml").write_text(
        yaml.safe_dump(replacement, sort_keys=False)
    )
    return SupersessionAuditor(project_root=root).find_violations(
        ManifestChain(manifests, project_root=root)
    )


def test_signature_is_opt_in_exact_identity_without_changing_merge_key() -> None:
    unsigned_spec = _artifact(None)
    int_spec = _artifact(INT_SIGNATURE)
    string_spec = _artifact(STRING_SIGNATURE)
    unsigned_found = FoundArtifact(
        kind=ArtifactKind.METHOD,
        name="Convert",
        of="Converter",
    )
    signed_found = _found_overloads()[0]
    delimiter_like_signature = ArtifactSpec(
        kind=ArtifactKind.FUNCTION,
        name="Convert",
        signature="A::B",
    )
    delimiter_like_name = ArtifactSpec(
        kind=ArtifactKind.FUNCTION,
        name="Convert::A",
        signature="B",
    )

    assert int_spec.signature == INT_SIGNATURE
    assert signed_found.signature == INT_SIGNATURE
    assert unsigned_spec.merge_key() == int_spec.merge_key() == string_spec.merge_key()
    assert unsigned_spec.contract_key() == unsigned_spec.merge_key()
    assert unsigned_found.contract_key() == unsigned_found.merge_key()
    assert int_spec.contract_key() != string_spec.contract_key()
    assert signed_found.contract_key() == int_spec.contract_key()
    assert delimiter_like_signature.contract_key() != delimiter_like_name.contract_key()

    with pytest.raises(ValueError, match="function or method"):
        ArtifactSpec(
            kind=ArtifactKind.CLASS,
            name="Converter",
            signature=INT_SIGNATURE,
        )
    with pytest.raises(ValueError, match="non-empty"):
        FoundArtifact(
            kind=ArtifactKind.METHOD,
            name="Convert",
            signature="",
        )


def test_signature_schema_round_trip_and_snapshot_preserve_exact_value(
    tmp_path: Path,
) -> None:
    data = _manifest_data([INT_SIGNATURE])
    assert validate_manifest_schema(data) == []
    invalid = deepcopy(data)
    invalid_artifact = invalid["files"]["create"][0]["artifacts"][0]
    invalid_artifact["kind"] = "class"
    assert validate_manifest_schema(invalid)
    empty = deepcopy(data)
    empty["files"]["create"][0]["artifacts"][0]["signature"] = ""
    assert any("signature" in error for error in validate_manifest_schema(empty))

    manifest_path = tmp_path / "input.manifest.yaml"
    manifest_path.write_text(yaml.safe_dump(data, sort_keys=False))
    loaded = load_manifest(manifest_path)
    saved_path = tmp_path / "saved.manifest.yaml"
    save_manifest(loaded, saved_path)

    assert loaded.files_create[0].artifacts[0].signature == INT_SIGNATURE
    assert (
        load_manifest_raw(saved_path)["files"]["create"][0]["artifacts"][0]["signature"]
        == INT_SIGNATURE
    )
    snapshot = _SignatureValidator().generate_snapshot("ignored", "Converter.signed")
    assert [artifact["signature"] for artifact in snapshot] == [
        INT_SIGNATURE,
        STRING_SIGNATURE,
    ]


def test_exact_signature_selects_overload_and_strict_mode_rejects_siblings() -> None:
    found = _found_overloads()

    assert (
        compare_artifacts([_artifact(INT_SIGNATURE)], found, "Converter.signed", False)
        == []
    )
    missing = compare_artifacts(
        [_artifact("Convert(System.Boolean)")],
        found,
        "Converter.signed",
        False,
    )
    assert [error.code for error in missing] == [ErrorCode.ARTIFACT_NOT_DEFINED]

    strict = compare_artifacts(
        [_artifact(INT_SIGNATURE)], found, "Converter.signed", True
    )
    assert [error.code for error in strict] == [ErrorCode.UNEXPECTED_ARTIFACT]
    assert strict[0].location.line == 20

    int_stub = _check_stub_artifacts(
        [_artifact(INT_SIGNATURE)], found, "Converter.signed"
    )
    assert [error.code for error in int_stub] == [ErrorCode.STUB_FUNCTION_DETECTED]
    assert (
        _check_stub_artifacts([_artifact(STRING_SIGNATURE)], found, "Converter.signed")
        == []
    )
    assert (
        _check_stub_artifacts(
            [_artifact(INT_SIGNATURE)],
            found,
            "Converter.signed",
            default_hook_artifacts={
                ("Converter.signed", _artifact(INT_SIGNATURE).contract_key())
            },
        )
        == []
    )
    assert [
        error.code
        for error in _check_stub_artifacts(
            [_artifact(INT_SIGNATURE)],
            found,
            "Converter.signed",
            default_hook_artifacts={
                ("Converter.signed", _artifact(STRING_SIGNATURE).contract_key())
            },
        )
    ] == [ErrorCode.STUB_FUNCTION_DETECTED]
    assert (
        _check_stub_artifacts(
            [_artifact(INT_SIGNATURE)],
            found,
            "Converter.signed",
            default_hook_artifacts={("Converter.signed", _artifact(None).merge_key())},
        )
        == []
    )

    representative = ArtifactSpec(
        kind=ArtifactKind.METHOD,
        name="Convert",
        of="Converter",
        returns="str",
    )
    assert compare_artifacts([representative], found, "Converter.signed", True) == []


def test_manifest_chain_and_validation_engine_retain_multiple_exact_overloads(
    tmp_path: Path,
) -> None:
    manifest_path = _write_project(tmp_path, [INT_SIGNATURE, STRING_SIGNATURE])
    chain = ManifestChain(tmp_path / "manifests", project_root=tmp_path)

    assert chain.load_errors == []
    merged = chain.merged_artifacts_for("src/Converter.signed")
    assert [artifact.signature for artifact in merged] == [
        INT_SIGNATURE,
        STRING_SIGNATURE,
    ]

    result = ValidationEngine(project_root=tmp_path, registry=_registry()).validate(
        manifest_path,
        mode=ValidationMode.IMPLEMENTATION,
    )
    assert result.success is True
    assert result.errors == []


def test_behavioral_signature_matching_requires_exact_evidence(tmp_path: Path) -> None:
    exact = FoundArtifact(
        kind=ArtifactKind.METHOD,
        name="Convert",
        of="Converter",
        signature=INT_SIGNATURE,
    )
    representative = FoundArtifact(
        kind=ArtifactKind.METHOD,
        name="Convert",
        of="Converter",
    )
    exact_ref = FoundArtifact(
        kind=ArtifactKind.METHOD,
        name="Convert",
        of="Converter",
        signature=INT_SIGNATURE,
        reference_context="call",
    )
    other_ref = FoundArtifact(
        kind=ArtifactKind.METHOD,
        name="Convert",
        of="Converter",
        signature=STRING_SIGNATURE,
        reference_context="call",
    )
    unsigned_ref = FoundArtifact(
        kind=ArtifactKind.METHOD,
        name="Convert",
        of="Converter",
        reference_context="call",
    )

    assert match_artifact_to_references(exact, [exact_ref], tmp_path) is True
    assert match_artifact_to_references(exact, [other_ref], tmp_path) is False
    assert match_artifact_to_references(exact, [unsigned_ref], tmp_path) is False
    assert (
        match_artifact_to_references(representative, [unsigned_ref], tmp_path) is True
    )
    assert _references_artifact(unsigned_ref, _artifact(INT_SIGNATURE)) is False
    assert _references_artifact(other_ref, _artifact(INT_SIGNATURE)) is False
    assert _references_artifact(exact_ref, _artifact(INT_SIGNATURE)) is True
    assert _references_artifact(exact_ref, _artifact(None)) is True

    unsigned_root = tmp_path / "unsigned"
    unsigned_manifest = _write_project(unsigned_root, [INT_SIGNATURE], "reference:none")
    unsigned_result = ValidationEngine(
        project_root=unsigned_root,
        registry=_registry(),
    ).validate(unsigned_manifest, mode=ValidationMode.BEHAVIORAL)
    assert any(
        error.code == ErrorCode.ARTIFACT_NOT_USED_IN_TESTS
        for error in unsigned_result.errors
    )
    unsigned_implementation_result = ValidationEngine(
        project_root=unsigned_root,
        registry=_registry(),
    ).validate(unsigned_manifest, mode=ValidationMode.IMPLEMENTATION)
    assert any(
        error.code == ErrorCode.ARTIFACT_NOT_USED_IN_TESTS
        for error in unsigned_implementation_result.errors
    )

    exact_root = tmp_path / "exact"
    exact_manifest = _write_project(exact_root, [INT_SIGNATURE], "reference:int")
    exact_result = ValidationEngine(
        project_root=exact_root,
        registry=_registry(),
    ).validate(exact_manifest, mode=ValidationMode.BEHAVIORAL)
    assert exact_result.success is True


def test_signature_survives_from_diff_and_changes_plan_lock_contract_hash(
    tmp_path: Path,
) -> None:
    int_artifact = ArtifactSpec(
        kind=ArtifactKind.METHOD,
        name="Convert",
        of="Converter",
        returns="int",
        signature=INT_SIGNATURE,
    )
    string_artifact = ArtifactSpec(
        kind=ArtifactKind.METHOD,
        name="Convert",
        of="Converter",
        returns="str",
        signature=STRING_SIGNATURE,
    )
    delta = _file_delta(
        "src/Converter.signed",
        (),
        (int_artifact, string_artifact),
    )
    assert [artifact.signature for artifact in delta.added] == [
        INT_SIGNATURE,
        STRING_SIGNATURE,
    ]

    diff = DiffScopeResult(
        created=("src/Converter.signed",),
        edited=(),
        deleted=(),
        deltas=(
            FileArtifactDelta(
                path="src/Converter.signed",
                added=(int_artifact, string_artifact),
            ),
        ),
    )
    generated = build_from_diff_manifest(diff, tmp_path, "signed-overload")
    generated_artifacts = generated["files"]["create"][0]["artifacts"]
    assert [artifact["signature"] for artifact in generated_artifacts] == [
        INT_SIGNATURE,
        STRING_SIGNATURE,
    ]

    manifest_path = tmp_path / "contract.manifest.yaml"
    original = _manifest_data([INT_SIGNATURE, STRING_SIGNATURE])
    original_artifacts = original["files"]["create"][0]["artifacts"]
    original_artifacts[0]["returns"] = "int"
    original_artifacts[1]["returns"] = "str"
    manifest_path.write_text(yaml.safe_dump(original, sort_keys=False))
    original_hash = compute_manifest_contract_hash(manifest_path)

    swapped = deepcopy(original)
    swapped_artifacts = swapped["files"]["create"][0]["artifacts"]
    swapped_artifacts[0]["returns"] = "str"
    swapped_artifacts[1]["returns"] = "int"
    manifest_path.write_text(yaml.safe_dump(swapped, sort_keys=False))
    assert compute_manifest_contract_hash(manifest_path) != original_hash


def test_supersession_audit_detects_one_dropped_exact_overload(
    tmp_path: Path,
) -> None:
    violations = _supersession_violations(
        tmp_path / "dropped-exact",
        [INT_SIGNATURE, STRING_SIGNATURE],
        [INT_SIGNATURE],
    )
    assert len(violations) == 1
    assert violations[0].artifact_key == _artifact(STRING_SIGNATURE).contract_key()

    representative_to_exact = _supersession_violations(
        tmp_path / "representative-to-exact",
        [None],
        [INT_SIGNATURE],
    )
    assert len(representative_to_exact) == 1
    assert representative_to_exact[0].artifact_key == _artifact(None).merge_key()

    exact_to_representative = _supersession_violations(
        tmp_path / "exact-to-representative",
        [INT_SIGNATURE],
        [None],
    )
    assert len(exact_to_representative) == 1
    assert (
        exact_to_representative[0].artifact_key
        == _artifact(INT_SIGNATURE).contract_key()
    )


def test_plugin_authoring_guide_documents_exact_signature_boundary() -> None:
    guide = Path("docs/validator-plugin-authoring.md").read_text().lower()

    assert "signature" in guide
    assert "opaque" in guide
    assert "representative" in guide
    assert "exact" in guide
    assert "do not guess" in guide
