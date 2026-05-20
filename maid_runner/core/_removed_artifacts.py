"""Removed artifact validation helpers."""

from __future__ import annotations

from pathlib import Path

from maid_runner.core.result import ErrorCode, Location, Severity, ValidationError
from maid_runner.core.supersession_audit import _path_is_within_project
from maid_runner.core.types import ArtifactKind, Manifest, RemovedArtifactSpec
from maid_runner.validators.registry import ValidatorRegistry


def _validate_removed_artifacts(
    *,
    manifest: Manifest,
    project_root: Path,
    registry: ValidatorRegistry,
) -> list[ValidationError]:
    errors: list[ValidationError] = []
    for spec in manifest.removed_artifacts:
        if spec.kind in (ArtifactKind.METHOD, ArtifactKind.ATTRIBUTE) and not spec.of:
            errors.append(
                ValidationError(
                    code=ErrorCode.REMOVED_ARTIFACT_STILL_PRESENT,
                    message=(
                        f"Cannot verify removal of '{spec.name}' "
                        f"({spec.kind.value}) from '{spec.file}': "
                        f"'of' (owner class/interface) is required for "
                        f"{spec.kind.value} entries"
                    ),
                    severity=Severity.ERROR,
                    location=Location(file=spec.file),
                    suggestion=(
                        "Add `of: <OwnerClass>` to the removed_artifacts entry "
                        "so the verifier can match the qualified member name."
                    ),
                )
            )
            continue
        if not _path_is_within_project(project_root, spec.file):
            errors.append(
                ValidationError(
                    code=ErrorCode.REMOVED_ARTIFACT_STILL_PRESENT,
                    message=(
                        f"Cannot verify removal of '{spec.name}' from "
                        f"'{spec.file}': path escapes the project root"
                    ),
                    severity=Severity.ERROR,
                    location=Location(file=spec.file),
                    suggestion=(
                        "Use a project-relative path inside the repository; "
                        "absolute and parent-relative paths are not allowed."
                    ),
                )
            )
            continue
        full_path = project_root / spec.file
        if not full_path.exists():
            errors.append(
                ValidationError(
                    code=ErrorCode.REMOVED_ARTIFACT_STILL_PRESENT,
                    message=(
                        f"Cannot verify removal of '{spec.name}' from "
                        f"'{spec.file}': file does not exist"
                    ),
                    severity=Severity.ERROR,
                    location=Location(file=spec.file),
                    suggestion=(
                        "Point removed_artifacts at the real source file, "
                        "or drop the entry."
                    ),
                )
            )
            continue
        if not registry.has_validator(spec.file):
            errors.append(
                ValidationError(
                    code=ErrorCode.REMOVED_ARTIFACT_STILL_PRESENT,
                    message=(
                        f"Cannot verify removal of '{spec.name}' from "
                        f"'{spec.file}': no validator available for this file type"
                    ),
                    severity=Severity.ERROR,
                    location=Location(file=spec.file),
                    suggestion=(
                        "Point removed_artifacts at a file in a supported "
                        "language, or drop the entry."
                    ),
                )
            )
            continue
        try:
            source = full_path.read_text()
        except OSError as exc:
            errors.append(
                ValidationError(
                    code=ErrorCode.REMOVED_ARTIFACT_STILL_PRESENT,
                    message=(
                        f"Cannot verify removal of '{spec.name}' from "
                        f"'{spec.file}': file is unreadable ({exc})"
                    ),
                    severity=Severity.ERROR,
                    location=Location(file=spec.file),
                )
            )
            continue
        validator = registry.get(spec.file)
        try:
            collection = validator.collect_implementation_artifacts(source, spec.file)
        except Exception as exc:
            errors.append(
                ValidationError(
                    code=ErrorCode.REMOVED_ARTIFACT_STILL_PRESENT,
                    message=(
                        f"Cannot verify removal of '{spec.name}' from "
                        f"'{spec.file}': source is unparsable ({exc})"
                    ),
                    severity=Severity.ERROR,
                    location=Location(file=spec.file),
                )
            )
            continue
        if collection.errors:
            detail = "; ".join(collection.errors[:3])
            errors.append(
                ValidationError(
                    code=ErrorCode.REMOVED_ARTIFACT_STILL_PRESENT,
                    message=(
                        f"Cannot verify removal of '{spec.name}' from "
                        f"'{spec.file}': collector reported errors ({detail})"
                    ),
                    severity=Severity.ERROR,
                    location=Location(file=spec.file),
                    suggestion=(
                        "Fix the source so the validator can parse it, "
                        "or drop the removed_artifacts entry."
                    ),
                )
            )
            continue
        target_key = _removed_artifact_merge_key(spec)
        for found in collection.artifacts:
            if found.merge_key() == target_key:
                errors.append(
                    ValidationError(
                        code=ErrorCode.REMOVED_ARTIFACT_STILL_PRESENT,
                        message=(
                            f"Manifest declares '{spec.name}' as removed from "
                            f"{spec.file} but the symbol is still defined "
                            f"in the source"
                        ),
                        severity=Severity.ERROR,
                        location=Location(file=spec.file, line=found.line),
                        suggestion=(
                            "Remove the symbol from the source, or drop the "
                            "removed_artifacts entry if removal was not intended."
                        ),
                    )
                )
                break
    return errors


def _removed_artifact_merge_key(spec: RemovedArtifactSpec) -> str:
    if spec.kind in (ArtifactKind.METHOD, ArtifactKind.ATTRIBUTE) and spec.of:
        return f"{spec.kind.value}:{spec.of}.{spec.name}"
    return f"{spec.kind.value}:{spec.name}"
