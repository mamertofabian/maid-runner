"""Per-file implementation validation helpers."""

from __future__ import annotations

import ast
from dataclasses import replace
from pathlib import Path
from typing import Callable, Optional

from maid_runner.core import _artifact_collection_cache as artifact_cache
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
from maid_runner.core.config import load_config
from maid_runner.core.diagnostic_policy import (
    no_validator_guidance,
    no_validator_severity,
)
from maid_runner.core.result import ErrorCode, Location, Severity, ValidationError
from maid_runner.core.ts_module_paths import resolve_ts_import, resolve_ts_reexport
from maid_runner.core.ts_return_contracts import (
    ReturnContractExpectation,
    ReturnContractResult,
    check_return_contracts,
)
from maid_runner.core.types import ArtifactKind, ArtifactSpec, FileSpec, Manifest
from maid_runner.validators.base import FoundArtifact
from maid_runner.validators.registry import UnsupportedLanguageError, ValidatorRegistry

# Structural artifact kinds that define shapes rather than behavior.
# These don't require manifest declaration in strict mode.
_STRUCTURAL_KINDS = frozenset({ArtifactKind.TYPE, ArtifactKind.INTERFACE})
_DEFAULT_HOOK_KINDS = frozenset({ArtifactKind.FUNCTION, ArtifactKind.METHOD})
_TypeMatcher = Callable[[Optional[str], Optional[str]], bool]
_ReturnContractChecker = Callable[
    [Path, str, str, str, tuple[ReturnContractExpectation, ...]], ReturnContractResult
]
_ReturnDecisions = dict[tuple[str, Optional[int], str], tuple[ValidationError, ...]]


class ImplementationFileValidator:
    """Validate one manifest file spec in implementation mode."""

    def __init__(
        self,
        project_root: Path,
        registry: ValidatorRegistry,
        *,
        check_stubs: bool = False,
        return_contract_checker: Optional[_ReturnContractChecker] = None,
    ) -> None:
        self._project_root = project_root
        self._registry = registry
        self._check_stubs = check_stubs
        self._return_contract_checker = (
            check_return_contracts
            if return_contract_checker is None
            else return_contract_checker
        )

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
            severity = no_validator_severity(fs.path)
            return [
                ValidationError(
                    code=ErrorCode.VALIDATOR_NOT_AVAILABLE,
                    message=f"No validator available for '{fs.path}'",
                    severity=severity,
                    location=Location(file=fs.path),
                    suggestion=(
                        no_validator_guidance()
                        if severity == Severity.WARNING
                        else None
                    ),
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

        if full_path.suffix == ".rs":
            # Rust impl owners depend on the project module graph, not just
            # this source text. Preserve the physical context and recollect.
            collection = validator.collect_implementation_artifacts(source, full_path)
        else:
            collection = artifact_cache.collect_cached_implementation_artifacts(
                validator, source, fs.path
            )
        if collection.errors:
            return collection_errors_to_validation_errors(collection.errors, fs.path)

        expected = self._expected_artifacts(fs, chain)
        is_strict = self._is_strict(fs, chain)
        return_decisions = _compiler_return_decisions(
            expected,
            collection.artifacts,
            fs.path,
            source,
            self._project_root,
            self._return_contract_checker,
            validator.types_match,
        )
        errors = _compare_artifacts(
            expected=expected,
            found=collection.artifacts,
            file_path=fs.path,
            is_strict=is_strict,
            type_matcher=validator.types_match,
            return_decisions=return_decisions,
        )

        if self._check_stubs:
            default_hook_artifacts = _default_hook_artifacts_for_file(fs, chain)
            errors.extend(
                _check_stub_artifacts(
                    expected,
                    collection.artifacts,
                    fs.path,
                    default_hook_artifacts=default_hook_artifacts,
                    type_matcher=validator.types_match,
                )
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
        if chain and (manifests := chain.manifests_for_file(fs.path)):
            is_strict = any(
                chain_fs.is_strict
                for manifest in manifests
                for chain_fs in manifest.all_file_specs
                if chain_fs.path == fs.path
            )
        else:
            is_strict = fs.is_strict

        # Test files naturally contain helpers, fixtures, and utilities that
        # are not manifest artifacts.
        if is_strict and is_test_file(fs.path):
            return False
        return is_strict


def _compiler_return_decisions(
    expected: list[ArtifactSpec],
    found: list[FoundArtifact],
    file_path: str,
    source: str,
    project_root: Path,
    checker: _ReturnContractChecker,
    type_matcher: _TypeMatcher,
) -> _ReturnDecisions:
    """Batch proof requests and keep their decisions separate from raw artifacts."""
    if Path(file_path).suffix not in (".ts", ".tsx"):
        return {}
    found = _project_canonical_artifacts(expected, found)
    by_key: dict[str, list[FoundArtifact]] = {}
    for artifact in found:
        by_key.setdefault(artifact.merge_key(), []).append(artifact)
    by_contract = {artifact.contract_key(): artifact for artifact in found}
    requested: list[tuple[ArtifactSpec, FoundArtifact]] = []
    for spec in expected:
        if not spec.returns or spec.kind not in _DEFAULT_HOOK_KINDS:
            continue
        artifact, _ = _found_artifact_for_spec(
            spec, by_key, by_contract, file_path, type_matcher=type_matcher
        )
        if (
            artifact is not None
            and artifact.kind == spec.kind
            and artifact.returns is None
        ):
            requested.append((spec, artifact))
    if not requested:
        return {}
    config = load_config(project_root).typescript_return_contracts
    if config.mode != "compiler":
        return {}

    decisions: _ReturnDecisions = {}
    supported: list[tuple[ArtifactSpec, FoundArtifact]] = []
    for spec, artifact in requested:
        if (
            spec.kind != ArtifactKind.FUNCTION
            or artifact.of is not None
            or artifact.line is None
        ):
            decisions[_return_decision_key(spec, artifact)] = (
                _return_proof_error(
                    spec,
                    artifact,
                    file_path,
                    ErrorCode.COMPILER_RETURN_CONTRACT_UNAVAILABLE,
                    "Only named top-level function declarations support compiler return proofs",
                ),
            )
        else:
            supported.append((spec, artifact))
    if not supported:
        return decisions
    expectations = tuple(
        ReturnContractExpectation(spec.name, artifact.line, spec.returns)
        for spec, artifact in supported
    )
    try:
        # Compiler mode's validated configuration guarantees an explicit path.
        if config.tsconfig is None:
            raise ValueError("Compiler mode requires explicit owning tsconfig")
        proof = checker(project_root, file_path, config.tsconfig, source, expectations)
        if len(proof.items) != len(supported):
            raise ValueError("Compiler proof batch count mismatch")
    except (OSError, TimeoutError, ValueError) as exc:
        for spec, artifact in supported:
            decisions[_return_decision_key(spec, artifact)] = (
                _return_proof_error(
                    spec,
                    artifact,
                    file_path,
                    ErrorCode.COMPILER_RETURN_CONTRACT_UNAVAILABLE,
                    str(exc),
                ),
            )
        return decisions
    for (spec, artifact), item in zip(supported, proof.items):
        key = _return_decision_key(spec, artifact)
        if (item.name, item.line) != (spec.name, artifact.line):
            code = ErrorCode.COMPILER_RETURN_CONTRACT_UNAVAILABLE
            detail = "Compiler proof declaration identity mismatch"
        elif item.status == "matched":
            decisions[key] = ()
            continue
        elif item.status == "mismatched":
            code = ErrorCode.TYPE_MISMATCH
            detail = f"Expected '{spec.returns}', inferred '{item.inferred_type}'"
        else:
            code = ErrorCode.COMPILER_RETURN_CONTRACT_UNAVAILABLE
            detail = "; ".join(item.diagnostics) or "Compiler return proof unavailable"
        decisions[key] = (_return_proof_error(spec, artifact, file_path, code, detail),)
    return decisions


def _return_decision_key(
    spec: ArtifactSpec, artifact: FoundArtifact
) -> tuple[str, Optional[int], str]:
    return spec.contract_key(), artifact.line, spec.returns or ""


def _return_proof_error(
    spec: ArtifactSpec,
    artifact: FoundArtifact,
    file_path: str,
    code: ErrorCode,
    detail: str,
) -> ValidationError:
    return ValidationError(
        code=code,
        message=f"Compiler return contract for '{spec.qualified_name}': {detail}",
        location=Location(file=file_path, line=artifact.line),
    )


def compare_artifacts(
    expected: list[ArtifactSpec],
    found: list[FoundArtifact],
    file_path: str,
    is_strict: bool,
) -> list[ValidationError]:
    """Compare artifacts, retaining historical Python callable tuple contracts."""
    return _compare_artifacts(
        expected=expected,
        found=found,
        file_path=file_path,
        is_strict=is_strict,
        type_matcher=types_match,
    )


def _compare_artifacts(
    expected: list[ArtifactSpec],
    found: list[FoundArtifact],
    file_path: str,
    is_strict: bool,
    *,
    type_matcher: _TypeMatcher,
    return_decisions: Optional[_ReturnDecisions] = None,
) -> list[ValidationError]:
    errors: list[ValidationError] = []
    found = _project_canonical_artifacts(expected, found)

    found_by_key: dict[str, list[FoundArtifact]] = {}
    found_by_contract_key: dict[str, FoundArtifact] = {}
    for found_art in found:
        found_by_key.setdefault(found_art.merge_key(), []).append(found_art)
        found_by_contract_key[found_art.contract_key()] = found_art

    for spec in expected:
        fa, comparison = _found_artifact_for_spec(
            spec,
            found_by_key,
            found_by_contract_key,
            file_path,
            type_matcher=type_matcher,
            return_decisions=return_decisions,
        )
        if fa is None:
            errors.append(
                ValidationError(
                    code=ErrorCode.ARTIFACT_NOT_DEFINED,
                    message=f"Artifact '{spec.qualified_name}' not defined in {file_path}",
                    location=Location(file=file_path),
                )
            )
            continue

        errors.extend(
            comparison
            if comparison is not None
            else _compare_single(
                spec,
                fa,
                file_path,
                type_matcher=type_matcher,
                return_decisions=return_decisions,
            )
        )

    if is_strict:
        representative_keys = {
            spec.merge_key() for spec in expected if spec.signature is None
        }
        exact_keys = {
            spec.contract_key() for spec in expected if spec.signature is not None
        }
        undeclared_structural = {
            fa.name
            for fa in found
            if fa.kind in _STRUCTURAL_KINDS
            and not fa.is_private
            and not _found_artifact_is_declared(
                fa,
                representative_keys,
                exact_keys,
            )
        }
        for fa in found:
            if fa.is_private:
                continue
            is_declared = _found_artifact_is_declared(
                fa,
                representative_keys,
                exact_keys,
            )
            if fa.kind in _STRUCTURAL_KINDS and not is_declared:
                continue
            if fa.of and fa.of in undeclared_structural:
                continue
            if not is_declared:
                errors.append(
                    ValidationError(
                        code=ErrorCode.UNEXPECTED_ARTIFACT,
                        message=f"Unexpected public artifact '{fa.qualified_name}' in {file_path}",
                        location=Location(file=file_path, line=fa.line),
                    )
                )

    return errors


def _project_canonical_artifacts(
    expected: list[ArtifactSpec],
    found: list[FoundArtifact],
) -> list[FoundArtifact]:
    """Project canonical identities without changing legacy collector output."""
    expected_keys = {(spec.kind, spec.name, spec.of) for spec in expected}
    roots_by_name: dict[str, list[FoundArtifact]] = {}
    for artifact in found:
        if artifact.of is None:
            roots_by_name.setdefault(artifact.name, []).append(artifact)
    projected_roots = {
        artifacts[0].name: artifacts[0]
        for artifacts in roots_by_name.values()
        if len(artifacts) == 1
        and artifacts[0]._canonical_kind is not None
        and (artifacts[0]._canonical_kind, artifacts[0].name, None) in expected_keys
    }
    if not projected_roots:
        return found

    projected: list[FoundArtifact] = []
    for artifact in found:
        if projected_roots.get(artifact.name) is artifact:
            canonical_kind = artifact._canonical_kind
            if canonical_kind is not None:
                projected.append(replace(artifact, kind=canonical_kind))
            if (artifact.kind, artifact.name, None) in expected_keys:
                projected.append(artifact)
            continue
        if (
            artifact.kind == ArtifactKind.ATTRIBUTE
            and artifact.of in projected_roots
            and (artifact.kind, artifact.name, artifact.of) not in expected_keys
        ):
            continue
        projected.append(artifact)
    return projected


def _found_artifact_for_spec(
    spec: ArtifactSpec,
    found_by_key: dict[str, list[FoundArtifact]],
    found_by_contract_key: dict[str, FoundArtifact],
    file_path: str,
    *,
    type_matcher: _TypeMatcher,
    return_decisions: Optional[_ReturnDecisions] = None,
) -> tuple[Optional[FoundArtifact], Optional[list[ValidationError]]]:
    if spec.signature is not None:
        return found_by_contract_key.get(spec.contract_key()), None

    candidates = found_by_key.get(spec.merge_key(), [])
    if not candidates:
        return None, None
    signatures = [candidate.signature for candidate in candidates]
    if (
        len(candidates) == 1
        or any(signature is None for signature in signatures)
        or len(set(signatures)) != len(signatures)
    ):
        return candidates[-1], None

    last_errors: Optional[list[ValidationError]] = None
    for candidate in reversed(candidates):
        candidate_errors = _compare_single(
            spec,
            candidate,
            file_path,
            type_matcher=type_matcher,
            return_decisions=return_decisions,
        )
        if last_errors is None:
            last_errors = candidate_errors
        if not candidate_errors:
            return candidate, []
    return candidates[-1], last_errors


def _found_artifact_is_declared(
    found: FoundArtifact,
    representative_keys: set[str],
    exact_keys: set[str],
) -> bool:
    return (
        found.merge_key() in representative_keys or found.contract_key() in exact_keys
    )


def _legacy_python_tuple_annotation(annotation: Optional[str]) -> Optional[str]:
    """Adapt only expected legacy variadic-tuple markers, not quoted values."""
    if annotation is None or "Ellipsis" not in annotation:
        return None
    try:
        tree = ast.parse(annotation.strip(), mode="eval")
        changed = False
        for node in ast.walk(tree):
            if not isinstance(node, ast.Subscript):
                continue
            base = node.value
            is_tuple = (
                isinstance(base, ast.Name) and base.id in ("tuple", "Tuple")
            ) or (
                isinstance(base, ast.Attribute)
                and base.attr == "Tuple"
                and isinstance(base.value, ast.Name)
                and base.value.id == "typing"
            )
            if not is_tuple or not isinstance(node.slice, ast.Tuple):
                continue
            elements = node.slice.elts
            if (
                len(elements) == 2
                and isinstance(elements[1], ast.Name)
                and elements[1].id == "Ellipsis"
            ):
                elements[1] = ast.copy_location(ast.Constant(Ellipsis), elements[1])
                changed = True
        return ast.unparse(tree) if changed else None
    except (SyntaxError, ValueError, TypeError, RecursionError):
        # The ordinary matcher already rejected this annotation. An invalid
        # legacy spelling must not acquire compatibility through recovery.
        return None


def _callable_type_matches(
    manifest_type: Optional[str],
    implementation_type: Optional[str],
    file_path: str,
    kind: ArtifactKind,
    type_matcher: _TypeMatcher,
) -> bool:
    if type_matcher(manifest_type, implementation_type):
        return True
    if kind not in _DEFAULT_HOOK_KINDS or Path(file_path).suffix != ".py":
        return False
    compatible = _legacy_python_tuple_annotation(manifest_type)
    return compatible is not None and type_matcher(compatible, implementation_type)


def _compare_single(
    spec: ArtifactSpec,
    found: FoundArtifact,
    file_path: str,
    *,
    type_matcher: _TypeMatcher = types_match,
    return_decisions: Optional[_ReturnDecisions] = None,
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

    if spec.kind == ArtifactKind.TYPE and spec.type_annotation:
        if found.type_annotation is None or not type_matcher(
            spec.type_annotation, found.type_annotation
        ):
            errors.append(
                ValidationError(
                    code=ErrorCode.TYPE_MISMATCH,
                    message=(
                        f"Type mismatch for type '{spec.qualified_name}': expected "
                        f"'{spec.type_annotation}', got '{found.type_annotation}'"
                    ),
                    location=Location(file=file_path, line=found.line),
                )
            )

    if spec.args:
        found_args_by_name = {a.name: a for a in found.args}
        for expected_arg in spec.args:
            found_arg = found_args_by_name.get(expected_arg.name)
            if found_arg is None:
                if (
                    expected_arg.name in ("self", "cls")
                    and spec.kind == ArtifactKind.METHOD
                ):
                    continue
                errors.append(
                    ValidationError(
                        code=ErrorCode.SIGNATURE_MISMATCH,
                        message=(
                            f"Signature mismatch for {spec.kind.value} "
                            f"'{spec.qualified_name}': missing parameter "
                            f"'{expected_arg.name}'"
                        ),
                        location=Location(file=file_path, line=found.line),
                    )
                )
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
            elif expected_arg.type and not _callable_type_matches(
                expected_arg.type, found_arg.type, file_path, spec.kind, type_matcher
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

    decision_key = (spec.contract_key(), found.line, spec.returns or "")
    if (
        spec.returns
        and found.returns is None
        and return_decisions is not None
        and decision_key in return_decisions
    ):
        errors.extend(return_decisions[decision_key])
    elif spec.returns and found.returns is None:
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
        if not _callable_type_matches(
            spec.returns, found.returns, file_path, spec.kind, type_matcher
        ):
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
    *,
    default_hook_artifacts: set[tuple[str, str]] | None = None,
    type_matcher: _TypeMatcher = types_match,
) -> list[ValidationError]:
    errors: list[ValidationError] = []
    default_hook_artifacts = default_hook_artifacts or set()
    found_by_key: dict[str, list[FoundArtifact]] = {}
    for artifact in found:
        found_by_key.setdefault(artifact.merge_key(), []).append(artifact)
    found_by_contract_key = {fa.contract_key(): fa for fa in found}
    for spec in expected:
        fa, _ = _found_artifact_for_spec(
            spec,
            found_by_key,
            found_by_contract_key,
            file_path,
            type_matcher=type_matcher,
        )
        if fa and (
            (file_path, fa.contract_key()) in default_hook_artifacts
            or (file_path, fa.merge_key()) in default_hook_artifacts
        ):
            continue
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


def _default_hook_artifacts_for_file(
    fs: FileSpec,
    chain: Optional[ManifestChain],
) -> set[tuple[str, str]]:
    declarations: list[ArtifactSpec] = []
    if chain is not None:
        for manifest in chain.manifests_for_file(fs.path):
            for chain_fs in manifest.all_file_specs:
                if chain_fs.path == fs.path:
                    declarations.extend(chain_fs.artifacts)
    else:
        declarations.extend(fs.artifacts)

    return {
        (fs.path, artifact.contract_key())
        for artifact in declarations
        if artifact.default_hook and artifact.kind in _DEFAULT_HOOK_KINDS
    }


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
