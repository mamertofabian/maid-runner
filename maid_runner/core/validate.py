"""Core validation engine for MAID Runner v2."""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import AbstractContextManager, contextmanager
import time
from pathlib import Path
from typing import Optional, Union

from maid_runner.core._file_discovery import is_test_file
from maid_runner.core import _implementation_validation
from maid_runner.core._artifact_collection_cache import clear_artifact_collection_cache
from maid_runner.core._implementation_runner import _run_implementation_validation
from maid_runner.core._test_function_contracts import (
    merged_test_function_behavior_requirements,
    validate_test_function_behavior,
    validate_test_function_names,
)
from maid_runner.core._file_tracking import _run_file_tracking
from maid_runner.core._behavioral_validation import (
    _check_test_assertions as _behavioral_check_test_assertions,
    _python_func_has_assertion as _behavioral_python_func_has_assertion,
    _python_func_is_pytest_fixture as _behavioral_python_func_is_pytest_fixture,
    _run_behavioral_validation,
)
from maid_runner.core._implementation_coverage import (
    _check_implementation_test_coverage,
)
from maid_runner.core._removed_artifacts import (
    _removed_artifact_merge_key as _removed_artifacts_merge_key,
    _validate_removed_artifacts,
)
from maid_runner.core._validate_all import _run_validate_all
from maid_runner.core._validation_test_artifacts import (
    collect_test_artifacts,
    collection_errors_to_validation_errors,
    find_test_files,
    get_validator_for_test,
)
from maid_runner.core.chain import (
    ManifestChain,
    _enter_manifest_chain_cache_scope,
    _exit_manifest_chain_cache_scope,
    _get_cached_manifest_chain_with_factory,
)
from maid_runner.core.ts_module_paths import (
    clear_ts_resolution_cache,
    resolve_ts_import,
    resolve_ts_reexport,
)
from maid_runner.core.manifest import (
    ManifestLoadError,
    ManifestSchemaError,
    load_manifest,
    validate_manifest_paths,
)
from maid_runner.core.result import (
    BatchValidationResult,
    ErrorCode,
    FileTrackingReport,
    Location,
    Severity,
    ValidationError,
    ValidationResult,
)
from maid_runner.core.types import (
    ArtifactSpec,
    Manifest,
    RemovedArtifactSpec,
    TestFunctionDetails,
    ValidationMode,
)
from maid_runner.validators.base import FoundArtifact
from maid_runner.validators.registry import (
    ValidatorRegistry,
)

_STRUCTURAL_KINDS = _implementation_validation._STRUCTURAL_KINDS


def _get_cached_manifest_chain_for_validate_all(
    manifest_dir: Union[str, Path],
    project_root: Path,
) -> ManifestChain:
    return _get_cached_manifest_chain_with_factory(
        manifest_dir,
        project_root,
        ManifestChain,
    )


class ValidationEngine:
    def __init__(
        self,
        project_root: Union[str, Path] = ".",
        *,
        registry: ValidatorRegistry | None = None,
    ):
        self._project_root = Path(project_root)
        self._registry = registry or ValidatorRegistry.with_builtin_validators()
        self._validation_cache_depth = 0

    def validate(
        self,
        manifest: Union[Manifest, str, Path],
        *,
        mode: ValidationMode = ValidationMode.IMPLEMENTATION,
        use_chain: bool = False,
        chain: Optional[ManifestChain] = None,
        manifest_dir: Union[str, Path] = "manifests/",
        check_stubs: bool = False,
        check_assertions: bool = False,
        fail_on_warnings: bool = False,
        include_chain_diagnostics: bool = True,
        include_plugin_diagnostics: bool = True,
    ) -> ValidationResult:
        outermost = self._enter_validation_cache_scope()
        start = time.monotonic()
        try:
            return self._validate(
                manifest,
                mode=mode,
                use_chain=use_chain,
                chain=chain,
                manifest_dir=manifest_dir,
                check_stubs=check_stubs,
                check_assertions=check_assertions,
                fail_on_warnings=fail_on_warnings,
                include_chain_diagnostics=include_chain_diagnostics,
                include_plugin_diagnostics=include_plugin_diagnostics,
                start=start,
            )
        finally:
            self._exit_validation_cache_scope(outermost)

    def _validate(
        self,
        manifest: Union[Manifest, str, Path],
        *,
        mode: ValidationMode,
        use_chain: bool,
        chain: Optional[ManifestChain],
        manifest_dir: Union[str, Path],
        check_stubs: bool,
        check_assertions: bool,
        fail_on_warnings: bool,
        include_chain_diagnostics: bool,
        include_plugin_diagnostics: bool,
        start: float,
    ) -> ValidationResult:
        # Load manifest if path
        if isinstance(manifest, (str, Path)):
            try:
                manifest = load_manifest(manifest)
            except ManifestLoadError as e:
                code = (
                    ErrorCode.FILE_NOT_FOUND
                    if e.reason == "File not found"
                    else ErrorCode.MANIFEST_PARSE_ERROR
                )
                return ValidationResult(
                    success=False,
                    manifest_slug="unknown",
                    manifest_path=str(e.path),
                    mode=mode,
                    errors=[
                        ValidationError(
                            code=code,
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

        path_errors = validate_manifest_paths(manifest, self._project_root)
        if path_errors:
            duration = (time.monotonic() - start) * 1000
            return ValidationResult(
                success=False,
                manifest_slug=manifest.slug,
                manifest_path=manifest.source_path,
                mode=mode,
                errors=path_errors,
                duration_ms=duration,
            )

        if mode == ValidationMode.SCHEMA:
            duration = (time.monotonic() - start) * 1000
            return ValidationResult(
                success=True,
                manifest_slug=manifest.slug,
                manifest_path=manifest.source_path,
                mode=mode,
                duration_ms=duration,
            )

        if not use_chain:
            chain = None
        elif chain is None:
            chain_dir = self._project_root / manifest_dir
            if chain_dir.exists():
                chain = ManifestChain(chain_dir, self._project_root)

        if mode == ValidationMode.BEHAVIORAL:
            errors = self.validate_behavioral(
                manifest, chain, check_assertions=check_assertions
            )
        else:
            errors = self.validate_implementation(
                manifest, chain, check_stubs=check_stubs
            )

        if include_chain_diagnostics and chain is not None:
            errors.extend(chain.diagnostics())

        if manifest.acceptance is not None:
            errors.extend(self.validate_acceptance(manifest))

        if include_plugin_diagnostics:
            errors.extend(self._registry.plugin_diagnostics())

        duration = (time.monotonic() - start) * 1000

        actual_errors = [e for e in errors if e.severity == Severity.ERROR]
        actual_warnings = [e for e in errors if e.severity == Severity.WARNING]
        success = len(actual_errors) == 0 and not (fail_on_warnings and actual_warnings)

        return ValidationResult(
            success=success,
            manifest_slug=manifest.slug,
            manifest_path=manifest.source_path,
            mode=mode,
            errors=actual_errors,
            warnings=actual_warnings,
            duration_ms=duration,
        )

    def validate_all(
        self,
        manifest_dir: Union[str, Path] = "manifests/",
        *,
        mode: ValidationMode = ValidationMode.IMPLEMENTATION,
        check_file_tracking: bool = False,
        allow_empty: bool = False,
        check_stubs: bool = False,
        check_assertions: bool = False,
        fail_on_warnings: bool = False,
    ) -> BatchValidationResult:
        chain_outermost = _enter_manifest_chain_cache_scope()
        outermost = self._enter_validation_cache_scope()
        try:
            result = _run_validate_all(
                project_root=self._project_root,
                manifest_dir=manifest_dir,
                mode=mode,
                check_file_tracking=check_file_tracking,
                allow_empty=allow_empty,
                check_stubs=check_stubs,
                check_assertions=check_assertions,
                fail_on_warnings=fail_on_warnings,
                validate_manifest=self._validate_for_validate_all,
                run_file_tracking=self.run_file_tracking,
                chain_factory=_get_cached_manifest_chain_for_validate_all,
            )
            if mode != ValidationMode.SCHEMA:
                plugin_diagnostics = self._registry.plugin_diagnostics()
                if plugin_diagnostics:
                    result.chain_errors.extend(plugin_diagnostics)
                    if fail_on_warnings:
                        result.failed += 1
            return result
        finally:
            self._exit_validation_cache_scope(outermost)
            _exit_manifest_chain_cache_scope(chain_outermost)

    def _validate_for_validate_all(self, *args, **kwargs) -> ValidationResult:
        kwargs["include_plugin_diagnostics"] = False
        return self.validate(*args, **kwargs)

    def validation_cache_scope(self) -> AbstractContextManager[None]:
        @contextmanager
        def _scope() -> Iterator[None]:
            outermost = self._enter_validation_cache_scope()
            try:
                yield
            finally:
                self._exit_validation_cache_scope(outermost)

        return _scope()

    def _enter_validation_cache_scope(self) -> bool:
        outermost = self._validation_cache_depth == 0
        if outermost:
            clear_artifact_collection_cache()
            clear_ts_resolution_cache()
        self._validation_cache_depth += 1
        return outermost

    def _exit_validation_cache_scope(self, outermost: bool) -> None:
        self._validation_cache_depth -= 1
        if outermost:
            clear_artifact_collection_cache()
            clear_ts_resolution_cache()

    def validate_behavioral(
        self,
        manifest: Manifest,
        chain: Optional[ManifestChain] = None,
        *,
        check_assertions: bool = False,
    ) -> list[ValidationError]:
        return _run_behavioral_validation(
            manifest=manifest,
            project_root=self._project_root,
            registry=self._registry,
            chain=chain,
            check_assertions=check_assertions,
        )

    def validate_acceptance(
        self,
        manifest: Manifest,
    ) -> list[ValidationError]:
        """Validate acceptance test configuration (Stream 1).

        Verifies that acceptance test files referenced in commands exist.
        """
        errors: list[ValidationError] = []
        errors.extend(validate_manifest_paths(manifest, self._project_root))
        if errors:
            return errors

        if manifest.acceptance is None:
            return errors

        for cmd in manifest.acceptance.tests:
            for part in cmd:
                if is_test_file(part):
                    full_path = self._project_root / part
                    if not full_path.exists():
                        errors.append(
                            ValidationError(
                                code=ErrorCode.ACCEPTANCE_TEST_FILE_NOT_FOUND,
                                message=f"Acceptance test file '{part}' not found",
                                location=Location(file=part),
                                suggestion="Create the acceptance test file before implementation",
                            )
                        )

        return errors

    def _validate_test_function_names(
        self,
        manifest: Manifest,
        *,
        is_behavioral: bool = True,
        chain: Optional[ManifestChain] = None,
    ) -> list[ValidationError]:
        """Guard 3: validate test_function artifacts exist in test files.

        Checks that each declared test_function artifact exists as an
        *actual test declaration* (function/arrow-function definition or
        ``it``/``test`` string label) in the test file — not merely as an
        incidental identifier reference such as an import or variable.

        When ``chain`` is provided, the set of required test functions for
        each file is merged across all active manifests so later manifests
        cannot silently drop historical test_function requirements.
        """
        return validate_test_function_names(
            manifest, self._project_root, self._registry, chain
        )

    def _validate_test_function_behavior(
        self,
        manifest: Manifest,
        *,
        chain: Optional[ManifestChain] = None,
    ) -> list[ValidationError]:
        """Validate behavioral alignment of test_function details.

        Cross-checks that the declared actions in ``test_function_details``
        appear in the *specific* test body, not anywhere in the file.
        Whole-file substring checks let one test satisfy another test's
        manifest metadata, so this scopes each check to the body of the
        named test. If the validator cannot locate a body, Guard 3 will
        already report the missing test declaration separately.
        """
        return validate_test_function_behavior(
            manifest, self._project_root, self._registry, chain
        )

    def _check_test_coverage(
        self,
        manifest: Manifest,
    ) -> list[ValidationError]:
        return _check_implementation_test_coverage(
            manifest=manifest,
            project_root=self._project_root,
            registry=self._registry,
        )

    def validate_implementation(
        self,
        manifest: Manifest,
        chain: Optional[ManifestChain] = None,
        *,
        check_stubs: bool = False,
    ) -> list[ValidationError]:
        return _run_implementation_validation(
            manifest=manifest,
            project_root=self._project_root,
            registry=self._registry,
            chain=chain,
            check_stubs=check_stubs,
            validate_removed_artifacts=self.validate_removed_artifacts,
            check_test_coverage=self._check_test_coverage,
            resolve_ts_import_fn=resolve_ts_import,
            resolve_ts_reexport_fn=resolve_ts_reexport,
        )

    def validate_removed_artifacts(self, manifest: Manifest) -> list[ValidationError]:
        """Verify that artifacts declared in `removed_artifacts` are absent from code.

        Fails closed: a removed_artifacts entry whose file is missing,
        unsupported by any validator, unreadable, unparsable, or whose path
        escapes the project root is reported as an E311 ERROR. Allowing those
        cases to pass silently would let a manifest-only edit suppress a
        supersession violation without proving the symbol was removed.
        """
        return _validate_removed_artifacts(
            manifest=manifest,
            project_root=self._project_root,
            registry=self._registry,
        )

    def run_file_tracking(
        self,
        chain: ManifestChain,
    ) -> FileTrackingReport:
        return _run_file_tracking(self._project_root, chain)


def _merged_test_function_behavior_requirements(
    manifest: Manifest,
    chain: Optional[ManifestChain],
) -> dict[str, dict[str, Optional[TestFunctionDetails]]]:
    """Merge behavioral test requirements across the active manifest chain."""
    return merged_test_function_behavior_requirements(manifest, chain)


def _merge_test_function_details(
    existing: Optional[TestFunctionDetails],
    incoming: Optional[TestFunctionDetails],
) -> Optional[TestFunctionDetails]:
    """Preserve historical behavior metadata unless a newer manifest adds detail."""
    from maid_runner.core._test_function_contracts import _merge_test_function_details

    return _merge_test_function_details(existing, incoming)


def _removed_artifact_merge_key(spec: RemovedArtifactSpec) -> str:
    return _removed_artifacts_merge_key(spec)


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


def validate(
    manifest_path: Union[str, Path],
    *,
    mode: ValidationMode = ValidationMode.IMPLEMENTATION,
    use_chain: bool = True,
    manifest_dir: Union[str, Path] = "manifests/",
    project_root: Union[str, Path] = ".",
    check_stubs: bool = False,
    check_assertions: bool = False,
    fail_on_warnings: bool = False,
    registry: ValidatorRegistry | None = None,
) -> ValidationResult:
    engine = ValidationEngine(project_root=project_root, registry=registry)
    return engine.validate(
        manifest_path,
        mode=mode,
        use_chain=use_chain,
        manifest_dir=manifest_dir,
        check_stubs=check_stubs,
        check_assertions=check_assertions,
        fail_on_warnings=fail_on_warnings,
    )


def validate_all(
    manifest_dir: Union[str, Path] = "manifests/",
    *,
    mode: ValidationMode = ValidationMode.IMPLEMENTATION,
    project_root: Union[str, Path] = ".",
    allow_empty: bool = False,
    check_stubs: bool = False,
    check_assertions: bool = False,
    fail_on_warnings: bool = False,
    registry: ValidatorRegistry | None = None,
) -> BatchValidationResult:
    engine = ValidationEngine(project_root=project_root, registry=registry)
    return engine.validate_all(
        manifest_dir,
        mode=mode,
        allow_empty=allow_empty,
        check_stubs=check_stubs,
        check_assertions=check_assertions,
        fail_on_warnings=fail_on_warnings,
    )


def _compare_artifacts(
    expected: list[ArtifactSpec],
    found: list[FoundArtifact],
    file_path: str,
    is_strict: bool,
) -> list[ValidationError]:
    return _implementation_validation.compare_artifacts(
        expected=expected,
        found=found,
        file_path=file_path,
        is_strict=is_strict,
    )


def _compare_single(
    spec: ArtifactSpec,
    found: FoundArtifact,
    file_path: str,
) -> list[ValidationError]:
    return _implementation_validation._compare_single(spec, found, file_path)


def _find_test_files(manifest: Manifest, project_root: Path) -> list[str]:
    return find_test_files(manifest, project_root)


def _get_validator_for_test(test_path: str, registry: ValidatorRegistry):
    return get_validator_for_test(test_path, registry)


def _collect_test_artifacts(
    test_files: list[str],
    project_root: Path,
    *,
    registry: ValidatorRegistry,
    errors: list[ValidationError],
) -> dict[str, list[FoundArtifact]]:
    return collect_test_artifacts(test_files, project_root, registry, errors)


def _collection_errors_to_validation_errors(
    collection_errors: list[str],
    file_path: str,
) -> list[ValidationError]:
    return collection_errors_to_validation_errors(collection_errors, file_path)


def _check_test_assertions(source: str, test_path: str) -> list[ValidationError]:
    return _behavioral_check_test_assertions(source, test_path)


def _python_func_has_assertion(node) -> bool:
    return _behavioral_python_func_has_assertion(node)


def _python_func_is_pytest_fixture(node) -> bool:
    return _behavioral_python_func_is_pytest_fixture(node)


def _check_required_imports(
    source: str,
    file_path: str,
    required_imports: tuple[str, ...],
    project_root: Optional[Path] = None,
) -> list[ValidationError]:
    _implementation_validation.resolve_ts_import = resolve_ts_import
    _implementation_validation.resolve_ts_reexport = resolve_ts_reexport
    return _implementation_validation._check_required_imports(
        source,
        file_path,
        required_imports,
        project_root,
    )
