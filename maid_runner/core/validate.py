"""Core validation engine for MAID Runner v2."""

from __future__ import annotations

import time
from pathlib import Path
import re
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
    ArtifactKind,
    ArtifactSpec,
    Manifest,
    ValidationMode,
)
from maid_runner.validators.base import FoundArtifact
from maid_runner.validators.registry import (
    UnsupportedLanguageError,
    ValidatorRegistry,
)

# Structural artifact kinds that define shapes rather than behavior.
# These don't require manifest declaration in strict mode.
_STRUCTURAL_KINDS = frozenset({ArtifactKind.TYPE, ArtifactKind.INTERFACE})


class ValidationEngine:
    def __init__(
        self,
        project_root: Union[str, Path] = ".",
        *,
        registry: ValidatorRegistry | None = None,
    ):
        self._project_root = Path(project_root)
        self._registry = registry or ValidatorRegistry.with_builtin_validators()

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
        include_chain_diagnostics: bool = True,
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

        duration = (time.monotonic() - start) * 1000

        actual_errors = [e for e in errors if e.severity == Severity.ERROR]
        actual_warnings = [e for e in errors if e.severity == Severity.WARNING]

        return ValidationResult(
            success=len(actual_errors) == 0,
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
    ) -> BatchValidationResult:
        start = time.monotonic()
        chain_dir = self._project_root / manifest_dir

        if not chain_dir.exists():
            return BatchValidationResult(
                results=[], total_manifests=0, passed=0, failed=0, skipped=0
            )

        chain = ManifestChain(chain_dir, self._project_root)
        chain_errors = chain.diagnostics()
        active = chain.active_manifests()
        superseded = chain.superseded_manifests()

        results: list[ValidationResult] = []
        passed = 0
        failed = 0

        for manifest in active:
            result = self.validate(
                manifest,
                mode=mode,
                use_chain=True,
                chain=chain,
                manifest_dir=manifest_dir,
                include_chain_diagnostics=False,
            )
            results.append(result)
            if result.success:
                passed += 1
            else:
                failed += 1

        duration = (time.monotonic() - start) * 1000

        return BatchValidationResult(
            results=results,
            total_manifests=len(active) + len(superseded) + len(chain.load_errors),
            passed=passed,
            failed=failed,
            skipped=len(superseded),
            chain_errors=chain_errors,
            duration_ms=duration,
        )

    def validate_behavioral(
        self,
        manifest: Manifest,
        chain: Optional[ManifestChain] = None,
        *,
        check_assertions: bool = False,
    ) -> list[ValidationError]:
        errors: list[ValidationError] = []

        # Find test files
        test_files = _find_test_files(manifest, self._project_root)
        test_artifacts = _collect_test_artifacts(
            test_files, self._project_root, registry=self._registry, errors=errors
        )

        # Check each artifact is used in at least one test
        for fs in manifest.all_file_specs:
            for artifact in fs.artifacts:
                if artifact.is_private:
                    continue
                used = False
                for ref_names in test_artifacts.values():
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

        # Check assertions in test files
        if check_assertions:
            for tf_path in test_files:
                full_path = self._project_root / tf_path
                if not full_path.exists():
                    continue
                try:
                    source = full_path.read_text()
                except OSError as exc:
                    errors.append(
                        ValidationError(
                            code=ErrorCode.FILE_READ_ERROR,
                            message=f"Failed to read test file '{tf_path}': {exc}",
                            location=Location(file=tf_path),
                        )
                    )
                    continue
                assertion_errors = _check_test_assertions(source, tf_path)
                errors.extend(assertion_errors)

        return errors

    def validate_acceptance(
        self,
        manifest: Manifest,
    ) -> list[ValidationError]:
        """Validate acceptance test configuration (Stream 1).

        Verifies that acceptance test files referenced in commands exist.
        """
        errors: list[ValidationError] = []

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

    def _check_test_coverage(
        self,
        manifest: Manifest,
    ) -> list[ValidationError]:
        """Check that manifests with public artifacts have test coverage.

        Returns errors/warnings:
        - E220 (ERROR) if manifest has public artifacts but zero test files
        - E200 (WARNING) if a public artifact is not referenced in any test
        """
        errors: list[ValidationError] = []

        # Snapshot manifests capture existing state — exempt from test coverage
        if manifest.task_type and manifest.task_type.value in (
            "snapshot",
            "system-snapshot",
        ):
            return errors

        # Only check artifacts from non-test source files.
        # Manifests that create/edit test files don't need meta-test coverage.
        source_file_specs = [
            fs for fs in manifest.all_file_specs if not is_test_file(fs.path)
        ]

        has_public_artifacts = any(
            not artifact.is_private
            for fs in source_file_specs
            for artifact in fs.artifacts
        )

        if not has_public_artifacts:
            return errors

        # Find test files
        test_files = _find_test_files(manifest, self._project_root)
        test_artifacts = _collect_test_artifacts(
            test_files, self._project_root, registry=self._registry, errors=errors
        )

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

        # Check each public artifact is referenced in at least one test (WARNING)
        for fs in source_file_specs:
            for artifact in fs.artifacts:
                if artifact.is_private:
                    continue
                used = False
                for ref_names in test_artifacts.values():
                    if artifact.name in ref_names:
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
                            severity=Severity.WARNING,
                            location=Location(file=fs.path),
                            suggestion=(
                                f"Add a test that imports and exercises '{artifact.name}'"
                            ),
                        )
                    )

        return errors

    def validate_implementation(
        self,
        manifest: Manifest,
        chain: Optional[ManifestChain] = None,
        *,
        check_stubs: bool = False,
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
                validator = self._registry.get(fs.path)
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
            try:
                source = full_path.read_text()
            except OSError as exc:
                errors.append(
                    ValidationError(
                        code=ErrorCode.FILE_READ_ERROR,
                        message=f"Failed to read file '{fs.path}': {exc}",
                        location=Location(file=fs.path),
                    )
                )
                continue
            collection = validator.collect_implementation_artifacts(source, fs.path)
            if collection.errors:
                errors.extend(
                    _collection_errors_to_validation_errors(collection.errors, fs.path)
                )
                continue

            # Get expected artifacts (chain may not cover this file)
            if chain:
                expected = chain.merged_artifacts_for(fs.path)
                if not expected:
                    expected = list(fs.artifacts)
            else:
                expected = list(fs.artifacts)

            # Determine strict mode: when chain is active, the merged
            # artifacts represent the COMPLETE declared public API for
            # this file. Enforce strict mode so any undeclared public
            # artifact is flagged. Without chain, only CREATE/SNAPSHOT
            # files can be strict (EDIT has an incomplete picture).
            if chain and chain.manifests_for_file(fs.path):
                is_strict = True
            else:
                is_strict = fs.is_strict

            # Test files always use permissive mode — they naturally contain
            # helpers, fixtures, and utilities that aren't manifest artifacts.
            if is_strict and is_test_file(fs.path):
                is_strict = False

            # Compare
            file_errors = _compare_artifacts(
                expected=expected,
                found=collection.artifacts,
                file_path=fs.path,
                is_strict=is_strict,
            )
            errors.extend(file_errors)

            # Stub detection: check matched artifacts for stub bodies
            if check_stubs:
                found_by_key = {fa.merge_key(): fa for fa in collection.artifacts}
                for spec in expected:
                    fa = found_by_key.get(spec.merge_key())
                    if fa and fa.is_stub and not fa.is_private:
                        errors.append(
                            ValidationError(
                                code=ErrorCode.STUB_FUNCTION_DETECTED,
                                message=(
                                    f"Function '{fa.qualified_name}' appears to be "
                                    f"a stub in {fs.path}"
                                ),
                                severity=Severity.WARNING,
                                location=Location(file=fs.path, line=fa.line),
                                suggestion="Implement the function body with real logic",
                            )
                        )

            # Import verification: check required imports exist
            if fs.imports:
                import_errors = _check_required_imports(source, fs.path, fs.imports)
                errors.extend(import_errors)

        # Test coverage: verify artifacts have tests
        test_coverage_errors = self._check_test_coverage(manifest)
        errors.extend(test_coverage_errors)

        return errors

    def run_file_tracking(
        self,
        chain: ManifestChain,
    ) -> FileTrackingReport:
        from maid_runner.core._file_discovery import discover_source_files

        source_files = discover_source_files(self._project_root)
        tracked_paths = chain.all_tracked_paths()
        read_only_paths = chain.all_read_only_paths()

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
            elif path in read_only_paths and not manifests:
                # File appears only in files.read — REGISTERED, not UNDECLARED
                read_manifest_slugs = tuple(
                    m.slug for m in chain.active_manifests() if path in m.files_read
                )
                entries.append(
                    FileTrackingEntry(
                        path=path,
                        status=FileTrackingStatus.REGISTERED,
                        manifests=read_manifest_slugs,
                        issues=("Only in readonlyFiles",),
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
    check_stubs: bool = False,
    check_assertions: bool = False,
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
    )


def validate_all(
    manifest_dir: Union[str, Path] = "manifests/",
    *,
    mode: ValidationMode = ValidationMode.IMPLEMENTATION,
    project_root: Union[str, Path] = ".",
    registry: ValidatorRegistry | None = None,
) -> BatchValidationResult:
    engine = ValidationEngine(project_root=project_root, registry=registry)
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
        # Collect names of undeclared structural artifacts whose members
        # should also be exempt from strict checking.
        undeclared_structural = {
            fa.name
            for fa in found
            if fa.kind in _STRUCTURAL_KINDS
            and not fa.is_private
            and fa.merge_key() not in expected_keys
        }
        for fa in found:
            if fa.is_private:
                continue
            # Skip undeclared structural artifacts (type aliases, interfaces)
            if fa.kind in _STRUCTURAL_KINDS and fa.merge_key() not in expected_keys:
                continue
            # Skip members of undeclared structural artifacts
            if fa.of and fa.of in undeclared_structural:
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

    # Compare args types by NAME (not position), matching v1 behavior.
    # Code may have extra params (e.g. ctx: Context) not in manifest.
    if spec.args:
        found_args_by_name = {a.name: a for a in found.args}
        for expected_arg in spec.args:
            found_arg = found_args_by_name.get(expected_arg.name)
            if found_arg is None:
                continue  # Parameter not found in code (separate validation)
            if expected_arg.type and found_arg.type is None:
                # Manifest declares type but code has no annotation -> WARNING
                errors.append(
                    ValidationError(
                        code=ErrorCode.MISSING_RETURN_TYPE,
                        message=(
                            f"Missing type annotation for parameter '{expected_arg.name}' "
                            f"in {spec.kind.value} '{spec.qualified_name}': "
                            f"expected '{expected_arg.type}'"
                        ),
                        severity=Severity.WARNING,
                        location=Location(file=file_path, line=found.line),
                    )
                )
            elif expected_arg.type and not types_match(
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
    if spec.returns and found.returns is None:
        # Manifest declares return type but code has no annotation -> WARNING
        errors.append(
            ValidationError(
                code=ErrorCode.MISSING_RETURN_TYPE,
                message=(
                    f"Missing return type annotation for {spec.kind.value} "
                    f"'{spec.qualified_name}': expected '{spec.returns}'"
                ),
                severity=Severity.WARNING,
                location=Location(file=file_path, line=found.line),
            )
        )
    elif spec.returns and found.returns:
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


def _get_validator_for_test(test_path: str, registry: ValidatorRegistry):
    """Get a validator for a test file, or None if unsupported."""
    try:
        return registry.get(test_path)
    except UnsupportedLanguageError:
        return None


def _collect_test_artifacts(
    test_files: list[str],
    project_root: Path,
    *,
    registry: ValidatorRegistry,
    errors: list[ValidationError],
) -> dict[str, set[str]]:
    collected: dict[str, set[str]] = {}

    for tf_path in test_files:
        full_path = project_root / tf_path
        if not full_path.exists():
            continue

        try:
            source = full_path.read_text()
        except OSError as exc:
            errors.append(
                ValidationError(
                    code=ErrorCode.FILE_READ_ERROR,
                    message=f"Failed to read test file '{tf_path}': {exc}",
                    location=Location(file=tf_path),
                )
            )
            continue

        validator = _get_validator_for_test(tf_path, registry)
        if validator is None:
            continue

        result = validator.collect_behavioral_artifacts(source, tf_path)
        if result.errors:
            errors.extend(_collection_errors_to_validation_errors(result.errors, tf_path))
            continue

        collected[tf_path] = {artifact.name for artifact in result.artifacts}

    return collected


def _collection_errors_to_validation_errors(
    collection_errors: list[str],
    file_path: str,
) -> list[ValidationError]:
    errors: list[ValidationError] = []
    for message in collection_errors:
        line = None
        match = re.search(r"line\s+(\d+)", message)
        if match:
            line = int(match.group(1))
        errors.append(
            ValidationError(
                code=ErrorCode.SOURCE_PARSE_ERROR,
                message=f"Failed to parse '{file_path}': {message}",
                location=Location(file=file_path, line=line),
                suggestion="Fix syntax errors before re-running validation",
            )
        )
    return errors


def _check_test_assertions(source: str, test_path: str) -> list[ValidationError]:
    """Check that test functions in a file contain at least one assertion.

    For Python: checks for assert statements, pytest.raises, or assert* calls.
    For TypeScript/JavaScript: checks for expect() calls.
    """
    import ast as _ast

    errors: list[ValidationError] = []

    if test_path.endswith(".py"):
        try:
            tree = _ast.parse(source, filename=test_path)
        except SyntaxError:
            return errors

        for node in _ast.walk(tree):
            if isinstance(node, (_ast.FunctionDef, _ast.AsyncFunctionDef)):
                if not node.name.startswith("test_"):
                    continue
                if _python_func_has_assertion(node):
                    continue
                errors.append(
                    ValidationError(
                        code=ErrorCode.MISSING_ASSERTIONS,
                        message=(
                            f"Test function '{node.name}' has no assertions "
                            f"in {test_path}"
                        ),
                        severity=Severity.WARNING,
                        location=Location(file=test_path, line=node.lineno),
                        suggestion="Add assert statements to verify behavior",
                    )
                )
    elif test_path.endswith((".ts", ".tsx", ".js", ".jsx")):
        # Simple text-based check for expect() in test blocks
        # This is approximate but catches the common case
        import re

        test_pattern = re.compile(
            r"(?:it|test)\s*\(\s*['\"].*?['\"]\s*,\s*(?:async\s*)?"
            r"(?:\(\s*\)\s*=>|function\s*\(\s*\))\s*\{(.*?)\}",
            re.DOTALL,
        )
        for match in test_pattern.finditer(source):
            body = match.group(1)
            if "expect(" not in body and "assert" not in body.lower():
                # Extract test name from the match
                name_match = re.search(r"['\"](.+?)['\"]", match.group(0))
                test_name = name_match.group(1) if name_match else "unknown"
                # Find line number
                line = source[: match.start()].count("\n") + 1
                errors.append(
                    ValidationError(
                        code=ErrorCode.MISSING_ASSERTIONS,
                        message=(
                            f"Test '{test_name}' has no assertions in {test_path}"
                        ),
                        severity=Severity.WARNING,
                        location=Location(file=test_path, line=line),
                        suggestion="Add expect() statements to verify behavior",
                    )
                )

    return errors


def _python_func_has_assertion(node) -> bool:
    """Check if a Python function AST node contains any assertion."""
    import ast as _ast

    for child in _ast.walk(node):
        # Direct assert statement
        if isinstance(child, _ast.Assert):
            return True
        # pytest.raises or similar context managers
        if isinstance(child, _ast.Call):
            func = child.func
            # pytest.raises(...)
            if isinstance(func, _ast.Attribute) and func.attr == "raises":
                return True
            # assertXxx() calls (unittest style)
            if isinstance(func, _ast.Attribute) and func.attr.startswith("assert"):
                return True
            if isinstance(func, _ast.Name) and func.id.startswith("assert"):
                return True
    return False


def _check_required_imports(
    source: str, file_path: str, required_imports: tuple[str, ...]
) -> list[ValidationError]:
    """Check that required import modules/symbols appear in the source file."""
    import ast as _ast

    errors: list[ValidationError] = []

    # Collect all import references from the source
    found_imports: set[str] = set()

    if file_path.endswith(".py"):
        try:
            tree = _ast.parse(source, filename=file_path)
        except SyntaxError:
            return errors

        for node in _ast.walk(tree):
            if isinstance(node, _ast.ImportFrom):
                if node.module:
                    found_imports.add(node.module)
                    # Also add each dotted prefix
                    parts = node.module.split(".")
                    for i in range(1, len(parts) + 1):
                        found_imports.add(".".join(parts[:i]))
                if node.names:
                    for alias in node.names:
                        found_imports.add(alias.name)
            elif isinstance(node, _ast.Import):
                for alias in node.names:
                    found_imports.add(alias.name)
    else:
        # TypeScript/JavaScript: simple text search for import patterns
        import posixpath
        import re

        _JS_EXTENSIONS = (".ts", ".tsx", ".js", ".jsx", ".mjs", ".cjs")

        # import/export ... from 'module' (covers default, namespace, re-exports)
        for match in re.finditer(
            r"""(?:import|export)\s+.*?from\s+['"](.+?)['"]""", source
        ):
            found_imports.add(match.group(1))
        # import 'module' (side-effect imports)
        for match in re.finditer(r"""import\s+['"](.+?)['"]""", source):
            found_imports.add(match.group(1))
        # import { X, Y } from 'module' / export { X, Y } from 'module'
        for match in re.finditer(
            r"""(?:import|export)\s+\{([^}]+)\}\s+from\s+['"](.+?)['"]""", source
        ):
            names = match.group(1)
            module = match.group(2)
            found_imports.add(module)
            for name in names.split(","):
                name = name.strip().split(" as ")[0].strip()
                if name:
                    found_imports.add(name)
        # import * as X from 'module'
        for match in re.finditer(
            r"""import\s+\*\s+as\s+(\w+)\s+from\s+['"](.+?)['"]""", source
        ):
            found_imports.add(match.group(1))  # namespace name
            found_imports.add(match.group(2))  # module path
        # CommonJS require('module') — also captures destructured: const { X } = require('...')
        for match in re.finditer(r"""require\s*\(\s*['"](.+?)['"]\s*\)""", source):
            found_imports.add(match.group(1))

        # Resolve relative imports against the importing file's directory
        # so that ../../src/models/Budget matches manifest's src/models/Budget.
        # Also strip known JS/TS extensions for extensionless matching.
        file_dir = posixpath.dirname(file_path)
        normalized: set[str] = set()
        for imp in list(found_imports):
            if imp.startswith("."):
                resolved = posixpath.normpath(posixpath.join(file_dir, imp))
                # Skip paths that escape the project root (start with ..)
                if resolved.startswith(".."):
                    continue
                normalized.add(resolved)
                # Also add without extension so "src/models/Budget.ts"
                # matches manifest's "src/models/Budget"
                for ext in _JS_EXTENSIONS:
                    if resolved.endswith(ext):
                        normalized.add(resolved[: -len(ext)])
                        break
            else:
                # Strip extensions from non-relative imports too
                for ext in _JS_EXTENSIONS:
                    if imp.endswith(ext):
                        normalized.add(imp[: -len(ext)])
                        break
        found_imports |= normalized

    # Check each required import
    for req in required_imports:
        candidates = {req}
        # Normalize path-style imports to dotted module notation for Python files
        # (arch-spec generates "src/models/user.py" but Python AST collects "src.models.user")
        if file_path.endswith(".py") and "/" in req:
            dotted = req.replace("/", ".")
            if dotted.endswith(".py"):
                dotted = dotted[:-3]
            candidates.add(dotted)
        if not candidates & found_imports:
            errors.append(
                ValidationError(
                    code=ErrorCode.MISSING_REQUIRED_IMPORT,
                    message=f"Required import '{req}' not found in {file_path}",
                    location=Location(file=file_path),
                    suggestion=f"Add an import for '{req}'",
                )
            )

    return errors
