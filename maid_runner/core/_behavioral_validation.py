"""Behavioral validation helpers."""

from __future__ import annotations

from pathlib import Path
from typing import Optional

from maid_runner.core._test_function_contracts import (
    validate_test_function_behavior,
    validate_test_function_names,
)
from maid_runner.core._test_assertions import (
    check_test_assertions,
    python_func_has_assertion,
    python_func_is_pytest_fixture,
    validate_test_assertions,
)
from maid_runner.core._validation_test_artifacts import (
    collect_test_artifacts,
    find_test_files,
    get_validator_for_test,
)
from maid_runner.core.chain import ManifestChain
from maid_runner.core.identity import match_artifact_to_references
from maid_runner.core.manifest import validate_manifest_paths
from maid_runner.core.module_paths import file_to_module_path
from maid_runner.core.result import ErrorCode, Location, ValidationError
from maid_runner.core.types import ArtifactKind, Manifest
from maid_runner.validators.base import FoundArtifact
from maid_runner.validators.registry import ValidatorRegistry


def _run_behavioral_validation(
    *,
    manifest: Manifest,
    project_root: Path,
    registry: ValidatorRegistry,
    chain: Optional[ManifestChain],
    check_assertions: bool,
) -> list[ValidationError]:
    errors: list[ValidationError] = []
    errors.extend(validate_manifest_paths(manifest, project_root))
    if errors:
        return errors

    test_files = find_test_files(manifest, project_root)
    test_artifacts = collect_test_artifacts(test_files, project_root, registry, errors)

    if not (
        manifest.task_type
        and manifest.task_type.value in ("snapshot", "system-snapshot")
    ):
        errors.extend(
            _validate_artifacts_used_in_tests(
                manifest=manifest,
                project_root=project_root,
                registry=registry,
                test_artifacts=test_artifacts,
            )
        )

    errors.extend(validate_test_function_names(manifest, project_root, registry, chain))
    errors.extend(
        validate_test_function_behavior(manifest, project_root, registry, chain)
    )

    if check_assertions:
        errors.extend(_validate_test_assertions(project_root, test_files))

    return errors


def _validate_artifacts_used_in_tests(
    *,
    manifest: Manifest,
    project_root: Path,
    registry: ValidatorRegistry,
    test_artifacts: dict[str, list[FoundArtifact]],
) -> list[ValidationError]:
    errors: list[ValidationError] = []

    for fs in manifest.all_file_specs:
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
            if artifact.is_private:
                continue
            if artifact.kind == ArtifactKind.TEST_FUNCTION:
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
                            f"Artifact '{artifact.name}' not used in any test file"
                        ),
                        location=Location(file=fs.path),
                    )
                )

    return errors


def _validate_test_assertions(
    project_root: Path,
    test_files: list[str],
) -> list[ValidationError]:
    return validate_test_assertions(project_root, test_files)


def _check_test_assertions(source: str, test_path: str) -> list[ValidationError]:
    return check_test_assertions(source, test_path)


def _python_func_has_assertion(node) -> bool:
    return python_func_has_assertion(node)


def _python_func_is_pytest_fixture(node) -> bool:
    return python_func_is_pytest_fixture(node)
