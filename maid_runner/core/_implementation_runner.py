"""Implementation validation orchestration helpers."""

from __future__ import annotations

from pathlib import Path
from typing import Callable, Optional

from maid_runner.core import _implementation_validation
from maid_runner.core._implementation_validation import ImplementationFileValidator
from maid_runner.core._test_function_contracts import validate_test_function_names
from maid_runner.core.chain import ManifestChain
from maid_runner.core.manifest import validate_manifest_paths
from maid_runner.core.result import ErrorCode, Location, ValidationError
from maid_runner.core.types import Manifest
from maid_runner.validators.registry import ValidatorRegistry


def _run_implementation_validation(
    *,
    manifest: Manifest,
    project_root: Path,
    registry: ValidatorRegistry,
    chain: Optional[ManifestChain],
    check_stubs: bool,
    validate_removed_artifacts: Callable[[Manifest], list[ValidationError]],
    check_test_coverage: Callable[[Manifest], list[ValidationError]],
    resolve_ts_import_fn: Callable,
    resolve_ts_reexport_fn: Callable,
) -> list[ValidationError]:
    errors: list[ValidationError] = []
    errors.extend(validate_manifest_paths(manifest, project_root))
    if errors:
        return errors

    errors.extend(_validate_deleted_files_absent(manifest, project_root))

    _implementation_validation.resolve_ts_import = resolve_ts_import_fn
    _implementation_validation.resolve_ts_reexport = resolve_ts_reexport_fn
    file_validator = ImplementationFileValidator(
        project_root,
        registry,
        check_stubs=check_stubs,
    )
    for fs in manifest.all_file_specs:
        errors.extend(file_validator.validate_file_spec(fs, manifest, chain))

    errors.extend(validate_test_function_names(manifest, project_root, registry, chain))
    errors.extend(validate_removed_artifacts(manifest))
    errors.extend(check_test_coverage(manifest))

    return errors


def _validate_deleted_files_absent(
    manifest: Manifest,
    project_root: Path,
) -> list[ValidationError]:
    errors: list[ValidationError] = []
    for ds in manifest.files_delete:
        full_path = project_root / ds.path
        if full_path.exists():
            errors.append(
                ValidationError(
                    code=ErrorCode.FILE_SHOULD_BE_ABSENT,
                    message=f"File '{ds.path}' should be absent but still exists",
                    location=Location(file=ds.path),
                )
            )
    return errors
