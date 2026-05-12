"""Validation helpers for manifest-declared test_function contracts."""

from __future__ import annotations

from pathlib import Path
from typing import Optional

from maid_runner.core._validation_test_artifacts import (
    collection_errors_to_validation_errors,
)
from maid_runner.core.chain import ManifestChain
from maid_runner.core.result import ErrorCode, Location, Severity, ValidationError
from maid_runner.core.types import (
    ArtifactKind,
    Manifest,
    TestFunctionDetails,
    TestFunctionSetup,
)
from maid_runner.validators.registry import UnsupportedLanguageError, ValidatorRegistry


def validate_test_function_names(
    manifest: Manifest,
    project_root: Path,
    registry: ValidatorRegistry,
    chain: Optional[ManifestChain] = None,
) -> list[ValidationError]:
    """Guard 3: validate test_function artifacts exist in test files."""
    errors: list[ValidationError] = []

    required = _merged_test_function_name_requirements(manifest, chain)
    for path, specs_by_name in required.items():
        full_path = project_root / path
        if not full_path.exists():
            errors.append(
                ValidationError(
                    code=ErrorCode.TEST_FILE_NOT_FOUND,
                    message=f"Test file '{path}' not found",
                    location=Location(file=path),
                )
            )
            continue

        try:
            source = full_path.read_text()
        except OSError as exc:
            errors.append(
                ValidationError(
                    code=ErrorCode.FILE_READ_ERROR,
                    message=f"Failed to read test file '{path}': {exc}",
                    location=Location(file=path),
                )
            )
            continue

        try:
            validator = registry.get(path)
        except UnsupportedLanguageError:
            continue

        collection = validator.collect_behavioral_artifacts(source, path)
        if collection.errors:
            errors.extend(collection_errors_to_validation_errors(collection.errors, path))
            continue

        found_names = {
            a.name for a in collection.artifacts if a.kind == ArtifactKind.TEST_FUNCTION
        }

        for name in specs_by_name:
            if name not in found_names:
                errors.append(
                    ValidationError(
                        code=ErrorCode.TEST_FUNCTION_MISSING_IN_CODE,
                        message=(
                            f"Test function '{name}' declared in manifest "
                            f"not found as a test declaration in {path}"
                        ),
                        location=Location(file=path),
                        suggestion="Add the test function to the test file",
                    )
                )

    return errors


def validate_test_function_behavior(
    manifest: Manifest,
    project_root: Path,
    registry: ValidatorRegistry,
    chain: Optional[ManifestChain] = None,
) -> list[ValidationError]:
    """Validate behavioral alignment of test_function details."""
    errors: list[ValidationError] = []

    required = merged_test_function_behavior_requirements(manifest, chain)
    for path, details_by_name in required.items():
        if not details_by_name:
            continue

        full_path = project_root / path
        if not full_path.exists():
            continue

        try:
            source = full_path.read_text()
        except OSError:
            continue

        try:
            validator = registry.get(path)
        except UnsupportedLanguageError:
            continue

        bodies = validator.get_test_function_bodies(source, path)

        for name, details in details_by_name.items():
            if details is None:
                continue

            body = bodies.get(name)
            if body is None:
                # No body available: either the language doesn't support body
                # extraction or the test is missing. Guard 3 handles missing
                # declarations, so behavior checks stay silent here.
                continue

            for action in details.actions:
                if not isinstance(action, dict):
                    continue
                if action.get("type") != "api_call":
                    continue
                subject = action.get("subject", {})
                export = subject.get("export")
                if export and export not in body:
                    errors.append(
                        ValidationError(
                            code=ErrorCode.TEST_FUNCTION_BEHAVIOR_MISMATCH,
                            message=(
                                f"Test function '{name}' declares api_call "
                                f"to '{export}' but it is not referenced in its body in {path}"
                            ),
                            severity=Severity.WARNING,
                            location=Location(file=path),
                        )
                    )

                endpoint = action.get("endpoint")
                if endpoint and endpoint not in body:
                    errors.append(
                        ValidationError(
                            code=ErrorCode.TEST_FUNCTION_BEHAVIOR_MISMATCH,
                            message=(
                                f"Test function '{name}' declares endpoint "
                                f"'{endpoint}' not found in its body in {path}"
                            ),
                            severity=Severity.WARNING,
                            location=Location(file=path),
                        )
                    )

    return errors


def merged_test_function_behavior_requirements(
    manifest: Manifest,
    chain: Optional[ManifestChain],
) -> dict[str, dict[str, Optional[TestFunctionDetails]]]:
    """Merge behavioral test requirements across the active manifest chain."""
    required: dict[str, dict[str, Optional[TestFunctionDetails]]] = {}
    paths = {fs.path for fs in manifest.all_file_specs}

    if chain is not None:
        for path in paths:
            for historical in chain.manifests_for_file(path):
                fs = historical.file_spec_for(path)
                if fs is None:
                    continue
                for artifact in fs.artifacts:
                    if artifact.kind != ArtifactKind.TEST_FUNCTION:
                        continue
                    names = required.setdefault(path, {})
                    names[artifact.name] = _merge_test_function_details(
                        names.get(artifact.name), artifact.test_details
                    )

    for fs in manifest.all_file_specs:
        for artifact in fs.artifacts:
            if artifact.kind != ArtifactKind.TEST_FUNCTION:
                continue
            names = required.setdefault(fs.path, {})
            names[artifact.name] = _merge_test_function_details(
                names.get(artifact.name), artifact.test_details
            )

    return required


def _merged_test_function_name_requirements(
    manifest: Manifest,
    chain: Optional[ManifestChain],
) -> dict[str, dict[str, object]]:
    required: dict[str, dict[str, object]] = {}
    for fs in manifest.all_file_specs:
        for artifact in fs.artifacts:
            if artifact.kind != ArtifactKind.TEST_FUNCTION:
                continue
            required.setdefault(fs.path, {}).setdefault(artifact.name, artifact)

    if chain is not None:
        paths = {fs.path for fs in manifest.all_file_specs}
        for path in paths:
            for artifact in chain.merged_artifacts_for(path):
                if artifact.kind != ArtifactKind.TEST_FUNCTION:
                    continue
                required.setdefault(path, {}).setdefault(artifact.name, artifact)

    return required


def _merge_test_function_details(
    existing: Optional[TestFunctionDetails],
    incoming: Optional[TestFunctionDetails],
) -> Optional[TestFunctionDetails]:
    """Preserve historical behavior metadata unless a newer manifest adds detail."""
    if existing is None:
        return incoming
    if incoming is None:
        return existing

    return TestFunctionDetails(
        source_scenario=incoming.source_scenario or existing.source_scenario,
        tags=_dedupe_preserve_order(existing.tags + incoming.tags),
        setup=TestFunctionSetup(
            auth_required=existing.setup.auth_required or incoming.setup.auth_required,
            test_data={**existing.setup.test_data, **incoming.setup.test_data},
            setup_actions=_dedupe_preserve_order(
                existing.setup.setup_actions + incoming.setup.setup_actions
            ),
        ),
        actions=_dedupe_preserve_order(existing.actions + incoming.actions),
        expected={**existing.expected, **incoming.expected},
        dependencies={**existing.dependencies, **incoming.dependencies},
    )


def _dedupe_preserve_order(values):
    seen: set[str] = set()
    result = []
    for value in values:
        marker = repr(value)
        if marker in seen:
            continue
        seen.add(marker)
        result.append(value)
    return tuple(result)
