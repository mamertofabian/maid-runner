"""Core validation engine for MAID Runner v2."""

from __future__ import annotations

import time
from pathlib import Path
from typing import Optional, Union

from maid_runner.core._file_discovery import is_test_file
from maid_runner.core._type_compare import types_match
from maid_runner.core.chain import ManifestChain
from maid_runner.core.manifest import (
    ManifestLoadError,
    ManifestSchemaError,
    load_manifest,
)
from maid_runner.core.result import (
    BatchValidationResult,
    ErrorCode,
    FileTrackingEntry,
    FileTrackingReport,
    FileTrackingStatus,
    Location,
    Severity,
    ValidationError,
    ValidationResult,
)
from maid_runner.core.types import (
    ArtifactSpec,
    Manifest,
    ValidationMode,
)
from maid_runner.validators.base import FoundArtifact
from maid_runner.validators.registry import (
    UnsupportedLanguageError,
    ValidatorRegistry,
    auto_register,
)

# Register all built-in validators (Python always, TS/Svelte if available)
auto_register()


class ValidationEngine:
    def __init__(self, project_root: Union[str, Path] = "."):
        self._project_root = Path(project_root)

    def validate(
        self,
        manifest: Union[Manifest, str, Path],
        *,
        mode: ValidationMode = ValidationMode.IMPLEMENTATION,
        use_chain: bool = False,
        manifest_dir: Union[str, Path] = "manifests/",
    ) -> ValidationResult:
        start = time.monotonic()

        # Load manifest if path
        if isinstance(manifest, (str, Path)):
            try:
                manifest = load_manifest(manifest)
            except ManifestLoadError as e:
                return ValidationResult(
                    success=False,
                    manifest_slug="unknown",
                    manifest_path=str(e.path),
                    mode=mode,
                    errors=[
                        ValidationError(
                            code=ErrorCode.FILE_NOT_FOUND,
                            message=str(e),
                        )
                    ],
                )
            except ManifestSchemaError as e:
                return ValidationResult(
                    success=False,
                    manifest_slug="unknown",
                    manifest_path=str(e.path),
                    mode=mode,
                    errors=[
                        ValidationError(
                            code=ErrorCode.SCHEMA_VALIDATION_ERROR,
                            message=str(e),
                        )
                    ],
                )

        chain: Optional[ManifestChain] = None
        if use_chain:
            chain_dir = self._project_root / manifest_dir
            if chain_dir.exists():
                chain = ManifestChain(chain_dir, self._project_root)

        if mode == ValidationMode.BEHAVIORAL:
            errors = self.validate_behavioral(manifest, chain)
        else:
            errors = self.validate_implementation(manifest, chain)

        duration = (time.monotonic() - start) * 1000

        return ValidationResult(
            success=len(errors) == 0,
            manifest_slug=manifest.slug,
            manifest_path=manifest.source_path,
            mode=mode,
            errors=[e for e in errors if e.severity == Severity.ERROR],
            warnings=[e for e in errors if e.severity == Severity.WARNING],
            duration_ms=duration,
        )

    def validate_all(
        self,
        manifest_dir: Union[str, Path] = "manifests/",
        *,
        mode: ValidationMode = ValidationMode.IMPLEMENTATION,
    ) -> BatchValidationResult:
        start = time.monotonic()
        chain_dir = self._project_root / manifest_dir

        if not chain_dir.exists():
            return BatchValidationResult(
                results=[], total_manifests=0, passed=0, failed=0, skipped=0
            )

        chain = ManifestChain(chain_dir, self._project_root)
        active = chain.active_manifests()
        superseded = chain.superseded_manifests()

        results: list[ValidationResult] = []
        passed = 0
        failed = 0

        for manifest in active:
            result = self.validate(
                manifest, mode=mode, use_chain=True, manifest_dir=manifest_dir
            )
            results.append(result)
            if result.success:
                passed += 1
            else:
                failed += 1

        duration = (time.monotonic() - start) * 1000

        return BatchValidationResult(
            results=results,
            total_manifests=len(active) + len(superseded),
            passed=passed,
            failed=failed,
            skipped=len(superseded),
            duration_ms=duration,
        )

    def validate_behavioral(
        self,
        manifest: Manifest,
        chain: Optional[ManifestChain] = None,
    ) -> list[ValidationError]:
        errors: list[ValidationError] = []

        # Find test files
        test_files = _find_test_files(manifest, self._project_root)

        # Check each artifact is used in at least one test
        for fs in manifest.all_file_specs:
            for artifact in fs.artifacts:
                if artifact.is_private:
                    continue
                used = False
                for tf_path in test_files:
                    full_path = self._project_root / tf_path
                    if not full_path.exists():
                        continue
                    source = full_path.read_text()
                    validator = _get_validator_for_test(tf_path)
                    if validator is None:
                        continue
                    result = validator.collect_behavioral_artifacts(source, tf_path)
                    ref_names = {a.name for a in result.artifacts}
                    if artifact.name in ref_names:
                        used = True
                        break
                if not used:
                    errors.append(
                        ValidationError(
                            code=ErrorCode.ARTIFACT_NOT_USED_IN_TESTS,
                            message=f"Artifact '{artifact.name}' not used in any test file",
                            location=Location(file=fs.path),
                        )
                    )

        return errors

    def validate_implementation(
        self,
        manifest: Manifest,
        chain: Optional[ManifestChain] = None,
    ) -> list[ValidationError]:
        errors: list[ValidationError] = []

        # Check delete files
        for ds in manifest.files_delete:
            full_path = self._project_root / ds.path
            if full_path.exists():
                errors.append(
                    ValidationError(
                        code=ErrorCode.FILE_SHOULD_BE_ABSENT,
                        message=f"File '{ds.path}' should be absent but still exists",
                        location=Location(file=ds.path),
                    )
                )

        # Check file specs
        for fs in manifest.all_file_specs:
            if fs.is_absent:
                full_path = self._project_root / fs.path
                if full_path.exists():
                    errors.append(
                        ValidationError(
                            code=ErrorCode.FILE_SHOULD_BE_ABSENT,
                            message=f"File '{fs.path}' should be absent but still exists",
                            location=Location(file=fs.path),
                        )
                    )
                continue

            full_path = self._project_root / fs.path
            if not full_path.exists():
                errors.append(
                    ValidationError(
                        code=ErrorCode.FILE_SHOULD_BE_PRESENT,
                        message=f"File '{fs.path}' not found",
                        location=Location(file=fs.path),
                    )
                )
                continue

            # Get validator
            try:
                validator = ValidatorRegistry.get(fs.path)
            except UnsupportedLanguageError:
                errors.append(
                    ValidationError(
                        code=ErrorCode.VALIDATOR_NOT_AVAILABLE,
                        message=f"No validator available for '{fs.path}'",
                        severity=Severity.WARNING,
                        location=Location(file=fs.path),
                    )
                )
                continue

            # Collect artifacts from source
            source = full_path.read_text()
            collection = validator.collect_implementation_artifacts(source, fs.path)

            # Get expected artifacts (chain may not cover this file)
            if chain:
                expected = chain.merged_artifacts_for(fs.path)
                if not expected:
                    expected = list(fs.artifacts)
            else:
                expected = list(fs.artifacts)

            # Compare
            file_errors = _compare_artifacts(
                expected=expected,
                found=collection.artifacts,
                file_path=fs.path,
                is_strict=fs.is_strict,
            )
            errors.extend(file_errors)

        return errors

    def run_file_tracking(
        self,
        chain: ManifestChain,
    ) -> FileTrackingReport:
        from maid_runner.core._file_discovery import discover_source_files

        source_files = discover_source_files(self._project_root)
        tracked_paths = chain.all_tracked_paths()

        entries: list[FileTrackingEntry] = []
        for path in source_files:
            if is_test_file(path):
                continue
            manifests = chain.manifests_for_file(path)
            manifest_slugs = tuple(m.slug for m in manifests)

            if path not in tracked_paths and not manifests:
                entries.append(
                    FileTrackingEntry(
                        path=path,
                        status=FileTrackingStatus.UNDECLARED,
                    )
                )
            elif manifests:
                has_artifacts = any(
                    m.file_spec_for(path) and m.file_spec_for(path).artifacts  # type: ignore[union-attr]
                    for m in manifests
                )
                if has_artifacts:
                    entries.append(
                        FileTrackingEntry(
                            path=path,
                            status=FileTrackingStatus.TRACKED,
                            manifests=manifest_slugs,
                        )
                    )
                else:
                    entries.append(
                        FileTrackingEntry(
                            path=path,
                            status=FileTrackingStatus.REGISTERED,
                            manifests=manifest_slugs,
                            issues=("No artifacts declared",),
                        )
                    )
            else:
                entries.append(
                    FileTrackingEntry(
                        path=path,
                        status=FileTrackingStatus.REGISTERED,
                        manifests=manifest_slugs,
                        issues=("Only in read section",),
                    )
                )

        return FileTrackingReport(entries=tuple(entries))


def validate(
    manifest_path: Union[str, Path],
    *,
    mode: ValidationMode = ValidationMode.IMPLEMENTATION,
    use_chain: bool = True,
    manifest_dir: Union[str, Path] = "manifests/",
    project_root: Union[str, Path] = ".",
) -> ValidationResult:
    engine = ValidationEngine(project_root=project_root)
    return engine.validate(
        manifest_path, mode=mode, use_chain=use_chain, manifest_dir=manifest_dir
    )


def validate_all(
    manifest_dir: Union[str, Path] = "manifests/",
    *,
    mode: ValidationMode = ValidationMode.IMPLEMENTATION,
    project_root: Union[str, Path] = ".",
) -> BatchValidationResult:
    engine = ValidationEngine(project_root=project_root)
    return engine.validate_all(manifest_dir, mode=mode)


def _compare_artifacts(
    expected: list[ArtifactSpec],
    found: list[FoundArtifact],
    file_path: str,
    is_strict: bool,
) -> list[ValidationError]:
    errors: list[ValidationError] = []

    # Build lookup of found artifacts by merge_key
    found_by_key: dict[str, FoundArtifact] = {}
    for found_art in found:
        found_by_key[found_art.merge_key()] = found_art

    # Check each expected artifact exists
    for spec in expected:
        key = spec.merge_key()
        fa = found_by_key.get(key)
        if fa is None:
            errors.append(
                ValidationError(
                    code=ErrorCode.ARTIFACT_NOT_DEFINED,
                    message=f"Artifact '{spec.qualified_name}' not defined in {file_path}",
                    location=Location(file=file_path),
                )
            )
            continue

        # Type comparison
        type_errors = _compare_single(spec, fa, file_path)
        errors.extend(type_errors)

    # Strict mode: check for unexpected public artifacts
    if is_strict:
        expected_keys = {spec.merge_key() for spec in expected}
        for fa in found:
            if fa.is_private:
                continue
            if fa.merge_key() not in expected_keys:
                errors.append(
                    ValidationError(
                        code=ErrorCode.UNEXPECTED_ARTIFACT,
                        message=f"Unexpected public artifact '{fa.qualified_name}' in {file_path}",
                        location=Location(file=file_path, line=fa.line),
                    )
                )

    return errors


def _compare_single(
    spec: ArtifactSpec,
    found: FoundArtifact,
    file_path: str,
) -> list[ValidationError]:
    errors: list[ValidationError] = []

    # Compare args types
    if spec.args:
        for i, expected_arg in enumerate(spec.args):
            if i < len(found.args):
                found_arg = found.args[i]
                if expected_arg.type and not types_match(
                    expected_arg.type, found_arg.type
                ):
                    errors.append(
                        ValidationError(
                            code=ErrorCode.TYPE_MISMATCH,
                            message=(
                                f"Type mismatch for parameter '{expected_arg.name}' "
                                f"in {spec.kind.value} '{spec.qualified_name}': "
                                f"expected '{expected_arg.type}', got '{found_arg.type}'"
                            ),
                            location=Location(file=file_path, line=found.line),
                        )
                    )

    # Compare return type
    if spec.returns and found.returns:
        if not types_match(spec.returns, found.returns):
            errors.append(
                ValidationError(
                    code=ErrorCode.TYPE_MISMATCH,
                    message=(
                        f"Return type mismatch for {spec.kind.value} '{spec.qualified_name}': "
                        f"expected '{spec.returns}', got '{found.returns}'"
                    ),
                    location=Location(file=file_path, line=found.line),
                )
            )

    return errors


def _find_test_files(manifest: Manifest, project_root: Path) -> list[str]:
    test_files: list[str] = []

    # From read files
    for path in manifest.files_read:
        if is_test_file(path):
            test_files.append(path)

    # From validate commands
    for cmd in manifest.validate_commands:
        for part in cmd:
            if is_test_file(part) and part not in test_files:
                test_files.append(part)

    return test_files


def _get_validator_for_test(test_path: str):
    """Get a validator for a test file, or None if unsupported."""
    try:
        return ValidatorRegistry.get(test_path)
    except UnsupportedLanguageError:
        return None
