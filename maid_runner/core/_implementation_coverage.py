"""Implementation test coverage validation helpers."""

from __future__ import annotations

from pathlib import Path

from maid_runner.core._file_discovery import is_test_file
from maid_runner.core._validation_test_artifacts import (
    collect_test_artifacts,
    find_test_files,
    get_validator_for_test,
)
from maid_runner.core.identity import match_artifact_to_references
from maid_runner.core.module_paths import file_to_module_path
from maid_runner.core.result import ErrorCode, Location, ValidationError
from maid_runner.core.types import ArtifactKind, Manifest
from maid_runner.validators.base import FoundArtifact
from maid_runner.validators.registry import ValidatorRegistry


def _check_implementation_test_coverage(
    *,
    manifest: Manifest,
    project_root: Path,
    registry: ValidatorRegistry,
) -> list[ValidationError]:
    errors: list[ValidationError] = []

    if manifest.task_type and manifest.task_type.value in (
        "snapshot",
        "system-snapshot",
    ):
        return errors

    source_file_specs = [
        fs for fs in manifest.all_file_specs if not is_test_file(fs.path)
    ]

    has_public_artifacts = any(
        not artifact.is_private and artifact.kind != ArtifactKind.TEST_FUNCTION
        for fs in source_file_specs
        for artifact in fs.artifacts
    )

    if not has_public_artifacts:
        return errors

    test_files = find_test_files(manifest, project_root)
    test_artifacts = collect_test_artifacts(test_files, project_root, registry, errors)

    if not test_files:
        errors.append(
            ValidationError(
                code=ErrorCode.NO_TEST_FILES,
                message=(
                    f"Manifest '{manifest.slug}' declares public artifacts "
                    f"but has no test files — add test file paths to "
                    f"files.read or validate commands"
                ),
                suggestion=(
                    "Add test files to the 'files.read' section or reference "
                    "them in 'validate' commands (e.g., pytest tests/test_foo.py -v)"
                ),
            )
        )
        return errors

    for fs in source_file_specs:
        artifact_validator = (
            get_validator_for_test(fs.path, registry) if fs.path else None
        )
        if artifact_validator is not None:
            artifact_module = artifact_validator.module_path(fs.path, project_root)
            resolver = artifact_validator.resolve_reexport
        else:
            artifact_module = (
                file_to_module_path(fs.path, project_root) if fs.path else None
            )
            resolver = None
        for artifact in fs.artifacts:
            if artifact.is_private or artifact.kind == ArtifactKind.TEST_FUNCTION:
                continue
            identity = FoundArtifact(
                kind=artifact.kind,
                name=artifact.name,
                of=artifact.of,
                module_path=artifact_module,
            )
            used = False
            for refs in test_artifacts.values():
                if match_artifact_to_references(
                    identity,
                    refs,
                    project_root,
                    reexport_resolver=resolver,
                ):
                    used = True
                    break
            if not used:
                errors.append(
                    ValidationError(
                        code=ErrorCode.ARTIFACT_NOT_USED_IN_TESTS,
                        message=(
                            f"Artifact '{artifact.name}' not referenced in "
                            f"any test file"
                        ),
                        location=Location(file=fs.path),
                        suggestion=(
                            f"Add a test that imports and exercises '{artifact.name}'"
                        ),
                    )
                )

    return errors
