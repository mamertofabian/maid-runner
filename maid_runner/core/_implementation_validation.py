"""Per-file implementation validation helpers."""

from __future__ import annotations

from pathlib import Path
from typing import Optional

from maid_runner.core._file_discovery import is_test_file
from maid_runner.core._js_ts_imports import (
    collect_import_module_bindings,
    collect_import_modules,
    collect_required_imports,
    import_may_satisfy_required,
)
from maid_runner.core._type_compare import types_match
from maid_runner.core._validation_test_artifacts import (
    collection_errors_to_validation_errors,
)
from maid_runner.core.chain import ManifestChain
from maid_runner.core.result import ErrorCode, Location, Severity, ValidationError
from maid_runner.core.ts_module_paths import resolve_ts_import, resolve_ts_reexport
from maid_runner.core.types import ArtifactKind, ArtifactSpec, FileSpec, Manifest
from maid_runner.validators.base import FoundArtifact
from maid_runner.validators.registry import UnsupportedLanguageError, ValidatorRegistry

# Structural artifact kinds that define shapes rather than behavior.
# These don't require manifest declaration in strict mode.
_STRUCTURAL_KINDS = frozenset({ArtifactKind.TYPE, ArtifactKind.INTERFACE})


class ImplementationFileValidator:
    """Validate one manifest file spec in implementation mode."""

    def __init__(
        self,
        project_root: Path,
        registry: ValidatorRegistry,
        *,
        check_stubs: bool = False,
    ) -> None:
        self._project_root = project_root
        self._registry = registry
        self._check_stubs = check_stubs

    def validate_file_spec(
        self,
        fs: FileSpec,
        manifest: Manifest,
        chain: Optional[ManifestChain],
    ) -> list[ValidationError]:
        del manifest

        if fs.is_absent:
            return self._validate_absent_file(fs)

        full_path = self._project_root / fs.path
        if not full_path.exists():
            return [
                ValidationError(
                    code=ErrorCode.FILE_SHOULD_BE_PRESENT,
                    message=f"File '{fs.path}' not found",
                    location=Location(file=fs.path),
                )
            ]

        try:
            validator = self._registry.get(fs.path)
        except UnsupportedLanguageError:
            return [
                ValidationError(
                    code=ErrorCode.VALIDATOR_NOT_AVAILABLE,
                    message=f"No validator available for '{fs.path}'",
                    severity=Severity.WARNING,
                    location=Location(file=fs.path),
                )
            ]

        try:
            source = full_path.read_text()
        except OSError as exc:
            return [
                ValidationError(
                    code=ErrorCode.FILE_READ_ERROR,
                    message=f"Failed to read file '{fs.path}': {exc}",
                    location=Location(file=fs.path),
                )
            ]

        collection = validator.collect_implementation_artifacts(source, fs.path)
        if collection.errors:
            return collection_errors_to_validation_errors(collection.errors, fs.path)

        expected = self._expected_artifacts(fs, chain)
        is_strict = self._is_strict(fs, chain)
        errors = compare_artifacts(
            expected=expected,
            found=collection.artifacts,
            file_path=fs.path,
            is_strict=is_strict,
        )

        if self._check_stubs:
            errors.extend(
                _check_stub_artifacts(expected, collection.artifacts, fs.path)
            )

        if fs.imports:
            errors.extend(
                _check_required_imports(source, fs.path, fs.imports, self._project_root)
            )

        return errors

    def _validate_absent_file(self, fs: FileSpec) -> list[ValidationError]:
        full_path = self._project_root / fs.path
        if not full_path.exists():
            return []
        return [
            ValidationError(
                code=ErrorCode.FILE_SHOULD_BE_ABSENT,
                message=f"File '{fs.path}' should be absent but still exists",
                location=Location(file=fs.path),
            )
        ]

    def _expected_artifacts(
        self,
        fs: FileSpec,
        chain: Optional[ManifestChain],
    ) -> list[ArtifactSpec]:
        if chain:
            expected = chain.merged_artifacts_for(fs.path)
            if not expected:
                expected = list(fs.artifacts)
        else:
            expected = list(fs.artifacts)

        # TEST_FUNCTION artifacts are validated via the behavioral collector
        # because implementation collectors cannot see string-label tests.
        return [a for a in expected if a.kind != ArtifactKind.TEST_FUNCTION]

    def _is_strict(self, fs: FileSpec, chain: Optional[ManifestChain]) -> bool:
        if chain and chain.manifests_for_file(fs.path):
            is_strict = True
        else:
            is_strict = fs.is_strict

        # Test files naturally contain helpers, fixtures, and utilities that
        # are not manifest artifacts.
        if is_strict and is_test_file(fs.path):
            return False
        return is_strict


def compare_artifacts(
    expected: list[ArtifactSpec],
    found: list[FoundArtifact],
    file_path: str,
    is_strict: bool,
) -> list[ValidationError]:
    errors: list[ValidationError] = []

    found_by_key: dict[str, FoundArtifact] = {}
    for found_art in found:
        found_by_key[found_art.merge_key()] = found_art

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

        errors.extend(_compare_single(spec, fa, file_path))

    if is_strict:
        expected_keys = {spec.merge_key() for spec in expected}
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
            if fa.kind in _STRUCTURAL_KINDS and fa.merge_key() not in expected_keys:
                continue
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

    if spec.kind != found.kind:
        errors.append(
            ValidationError(
                code=ErrorCode.ARTIFACT_NOT_DEFINED,
                message=(
                    f"Artifact '{spec.qualified_name}' expected kind "
                    f"'{spec.kind.value}' but found '{found.kind.value}' in {file_path}"
                ),
                location=Location(file=file_path, line=found.line),
            )
        )
        return errors

    if spec.type_parameters and spec.type_parameters != found.type_parameters:
        errors.append(
            ValidationError(
                code=ErrorCode.TYPE_MISMATCH,
                message=(
                    f"type parameters mismatch for {spec.kind.value} "
                    f"'{spec.qualified_name}': expected "
                    f"{list(spec.type_parameters)}, got {list(found.type_parameters)}"
                ),
                location=Location(file=file_path, line=found.line),
            )
        )

    if spec.args:
        found_args_by_name = {a.name: a for a in found.args}
        for expected_arg in spec.args:
            found_arg = found_args_by_name.get(expected_arg.name)
            if found_arg is None:
                continue
            if expected_arg.type and found_arg.type is None:
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

    if spec.returns and found.returns is None:
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


def _check_stub_artifacts(
    expected: list[ArtifactSpec],
    found: list[FoundArtifact],
    file_path: str,
) -> list[ValidationError]:
    errors: list[ValidationError] = []
    found_by_key = {fa.merge_key(): fa for fa in found}
    for spec in expected:
        fa = found_by_key.get(spec.merge_key())
        if fa and fa.is_stub and not fa.is_private:
            errors.append(
                ValidationError(
                    code=ErrorCode.STUB_FUNCTION_DETECTED,
                    message=(
                        f"Function '{fa.qualified_name}' appears to be "
                        f"a stub in {file_path}"
                    ),
                    severity=Severity.WARNING,
                    location=Location(file=file_path, line=fa.line),
                    suggestion="Implement the function body with real logic",
                )
            )
    return errors


def _check_required_imports(
    source: str,
    file_path: str,
    required_imports: tuple[str, ...],
    project_root: Optional[Path] = None,
) -> list[ValidationError]:
    """Check that required import modules/symbols appear in the source file."""
    import ast as _ast

    errors: list[ValidationError] = []
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
        import posixpath

        js_extensions = (".ts", ".tsx", ".js", ".jsx", ".mjs", ".cjs", ".mts", ".cts")

        found_imports = collect_required_imports(source, file_path)
        raw_import_modules = collect_import_modules(source, file_path)
        raw_import_bindings = collect_import_module_bindings(source, file_path)

        file_dir = posixpath.dirname(file_path)
        normalized: set[str] = set()
        non_relative_raw: list[str] = []
        for imp in raw_import_modules:
            if imp.startswith("."):
                resolved = posixpath.normpath(posixpath.join(file_dir, imp))
                if resolved.startswith(".."):
                    continue
                normalized.add(resolved)
                if resolved.endswith("/index"):
                    normalized.add(posixpath.dirname(resolved))
                for ext in js_extensions:
                    if resolved.endswith(ext):
                        extensionless = resolved[: -len(ext)]
                        normalized.add(extensionless)
                        if extensionless.endswith("/index"):
                            normalized.add(posixpath.dirname(extensionless))
                        break
            else:
                for ext in js_extensions:
                    if imp.endswith(ext):
                        extensionless = imp[: -len(ext)]
                        normalized.add(extensionless)
                        if extensionless.endswith("/index"):
                            normalized.add(posixpath.dirname(extensionless))
                        break
                non_relative_raw.append(imp)
        found_imports |= normalized

        unresolved_required_imports = {
            req for req in required_imports if req not in found_imports
        }
        if (
            project_root is not None
            and non_relative_raw
            and unresolved_required_imports
        ):
            importer_module = posixpath.splitext(file_path.replace("\\", "/"))[0]
            for imp in non_relative_raw:
                if not import_may_satisfy_required(
                    imp,
                    unresolved_required_imports,
                    raw_import_bindings.get(imp, set()),
                ):
                    continue
                resolved = resolve_ts_import(imp, importer_module, project_root)
                if resolved != imp:
                    found_imports.add(resolved)
                    if resolved.endswith("/index"):
                        found_imports.add(posixpath.dirname(resolved))
                    for binding in raw_import_bindings.get(imp, set()):
                        reexport = resolve_ts_reexport(resolved, binding, project_root)
                        if reexport is not None:
                            found_imports.add(reexport[0])
                    unresolved_required_imports = {
                        req
                        for req in unresolved_required_imports
                        if req not in found_imports
                    }
                    if not unresolved_required_imports:
                        break

    for req in required_imports:
        candidates = {req}
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
