"""Artifact knockout rewrite/run/restore engine."""

from __future__ import annotations

import ast
import hashlib
import time
from collections.abc import Sequence
from dataclasses import dataclass, replace
from pathlib import Path

from maid_runner.core._pytest_command_normalization import _normalize_pytest_command
from maid_runner.core._test_command_execution import _run_test_command
from maid_runner.core.result import ErrorCode, Location, TestRunResult, ValidationError
from maid_runner.core.runtime_evidence import (
    RuntimeCommandEvidence,
    RuntimeEvidenceBundle,
    runtime_evidence_is_current,
)
from maid_runner.core.types import ArtifactKind, ArtifactSpec, Manifest
from maid_runner.core.worktree import changed_files


@dataclass(frozen=True)
class KnockoutResult:
    artifact_name: str
    artifact_kind: str
    parent_class: str | None
    file_path: str
    detected: bool
    duration_ms: float
    proof: KnockoutDifferentialProof | None = None


@dataclass(frozen=True)
class KnockoutReport:
    results: tuple[KnockoutResult, ...]
    errors: tuple[ValidationError, ...]

    @property
    def success(self) -> bool:
        return not self.errors

    def to_dict(self) -> dict:
        return {
            "success": self.success,
            "results": [_result_to_dict(result) for result in self.results],
            "errors": [error.to_dict() for error in self.errors],
        }


@dataclass(frozen=True)
class KnockoutArtifactIdentity:
    """Normalized identity for one unique Python artifact mutation."""

    file_path: str
    artifact_name: str
    artifact_kind: str
    parent_class: str | None


@dataclass(frozen=True)
class KnockoutDeclaration:
    """Original manifest declaration and exact validate-command attribution."""

    manifest_path: str
    manifest_slug: str
    declaration_index: int
    plan_index: int
    commands: tuple[tuple[str, ...], ...]


@dataclass(frozen=True)
class KnockoutMutationSpec:
    """One immutable current-source mutation with all declaring records."""

    identity: KnockoutArtifactIdentity
    source_digest: str
    declarations: tuple[KnockoutDeclaration, ...]


@dataclass(frozen=True)
class KnockoutDifferentialProof:
    """Three-point mutation evidence for one command and artifact."""

    identity: KnockoutArtifactIdentity
    command: tuple[str, ...]
    baseline_exit_code: int
    mutant_exit_code: int
    restored_exit_code: int
    detecting_nodeids: tuple[str, ...]
    used_exact_fallback: bool
    diagnostics: tuple[ValidationError, ...]


class KnockoutCommandExecutor:
    """Owned command boundary for differential knockout execution."""

    def execute(
        self,
        command: tuple[str, ...],
        project_root: Path,
        manifest_slug: str,
    ) -> TestRunResult:
        return _run_test_command(
            command,
            cwd=project_root,
            manifest_slug=manifest_slug,
        )


def build_knockout_mutation_specs(
    manifests: Sequence[Manifest],
    project_root: Path,
    limit: int | None = None,
) -> tuple[KnockoutMutationSpec, ...]:
    """Deduplicate selected declarations without changing legacy execution order."""
    root = Path(project_root)
    selected_limit = None if limit is None else max(limit, 0)
    grouped: dict[
        KnockoutArtifactIdentity,
        tuple[str, list[KnockoutDeclaration]],
    ] = {}
    plan_index = 0

    for manifest in manifests:
        for declaration_index, (file_path, artifact) in enumerate(
            _knockout_targets(manifest)
        ):
            if selected_limit is not None and plan_index >= selected_limit:
                break
            normalized_path = _normalize_project_path(root, file_path)
            target_path, target_error = _target_path_or_error(root, normalized_path)
            if target_error is not None:
                raise ValueError(target_error.message)
            try:
                source_digest = hashlib.sha256(target_path.read_bytes()).hexdigest()
            except Exception as exc:
                raise ValueError(
                    f"Knockout could not read source file {normalized_path}: {exc}"
                ) from exc

            identity = KnockoutArtifactIdentity(
                file_path=normalized_path,
                artifact_name=artifact.name,
                artifact_kind=artifact.kind.value,
                parent_class=artifact.of,
            )
            declaration = KnockoutDeclaration(
                manifest_path=manifest.source_path,
                manifest_slug=manifest.slug,
                declaration_index=declaration_index,
                plan_index=plan_index,
                commands=tuple(
                    tuple(command) for command in manifest.validate_commands
                ),
            )
            existing = grouped.get(identity)
            if existing is None:
                grouped[identity] = (source_digest, [declaration])
            else:
                existing_digest, declarations = existing
                if existing_digest != source_digest:
                    raise ValueError(
                        "Knockout source changed while building mutation plan for "
                        f"{normalized_path}"
                    )
                declarations.append(declaration)
            plan_index += 1
        if selected_limit is not None and plan_index >= selected_limit:
            break

    return tuple(
        KnockoutMutationSpec(
            identity=identity,
            source_digest=source_digest,
            declarations=tuple(declarations),
        )
        for identity, (source_digest, declarations) in grouped.items()
    )


def knockout_mutation_spec_is_current(
    spec: KnockoutMutationSpec,
    project_root: Path,
) -> bool:
    """Return whether a planned mutation still matches current target bytes."""
    root = Path(project_root)
    target_path, target_error = _target_path_or_error(root, spec.identity.file_path)
    if target_error is not None:
        return False
    try:
        return (
            hashlib.sha256(target_path.read_bytes()).hexdigest() == spec.source_digest
        )
    except Exception:
        return False


def rewrite_artifact_body(
    source: str,
    artifact_name: str,
    artifact_kind: str,
    parent_class: str | None = None,
) -> str:
    tree = ast.parse(source)
    node = _find_artifact_node(tree, artifact_name, artifact_kind, parent_class)
    if node is None:
        qualified = f"{parent_class}.{artifact_name}" if parent_class else artifact_name
        raise ValueError(f"Python artifact not found for knockout: {qualified}")
    if not node.body:
        raise ValueError(f"Python artifact has no body for knockout: {artifact_name}")

    lines = source.splitlines(keepends=True)
    first_body = node.body[0]
    last_body = node.body[-1]
    start = first_body.lineno - 1
    end = getattr(last_body, "end_lineno", last_body.lineno)
    indent = " " * first_body.col_offset
    newline = _source_newline(source)
    replacement = f'{indent}raise NotImplementedError("maid-knockout"){newline}'

    if first_body.lineno == node.lineno:
        signature = lines[start][: first_body.col_offset].rstrip()
        lines[start:end] = [f"{signature}{newline}", replacement]
    else:
        lines[start:end] = [replacement]
    return "".join(lines)


def _source_newline(source: str) -> str:
    """Preserve the source's first observed newline convention."""
    newline_index = source.find("\n")
    if newline_index > 0 and source[newline_index - 1] == "\r":
        return "\r\n"
    return "\n"


def run_knockout(
    manifest: Manifest,
    project_root: Path,
    limit: int | None = None,
    allow_dirty: bool = False,
    evidence: RuntimeEvidenceBundle | None = None,
    executor: KnockoutCommandExecutor | None = None,
) -> KnockoutReport:
    return run_knockout_batch(
        (manifest,),
        project_root,
        evidence=evidence,
        limit=limit,
        allow_dirty=allow_dirty,
        executor=executor,
    )[manifest.source_path]


def run_knockout_batch(
    manifests: Sequence[Manifest],
    project_root: Path,
    evidence: RuntimeEvidenceBundle | None = None,
    limit: int | None = None,
    allow_dirty: bool = False,
    executor: KnockoutCommandExecutor | None = None,
) -> dict[str, KnockoutReport]:
    """Run declarations independently with focused proof or exact fallback."""
    ordered_manifests = tuple(manifests)
    root = Path(project_root)
    command_executor = executor or KnockoutCommandExecutor()
    trusted_evidence = None
    if evidence is not None:
        try:
            if _knockout_evidence_is_current(evidence, ordered_manifests, root):
                trusted_evidence = evidence
        except Exception:
            trusted_evidence = None
    results_by_manifest: dict[str, list[KnockoutResult]] = {
        manifest.source_path: [] for manifest in ordered_manifests
    }
    errors_by_manifest: dict[str, list[ValidationError]] = {
        manifest.source_path: [] for manifest in ordered_manifests
    }

    try:
        specs = build_knockout_mutation_specs(ordered_manifests, root, limit=limit)
    except Exception as exc:
        error = _harness_error("", str(exc))
        return {
            manifest.source_path: KnockoutReport(results=(), errors=(error,))
            for manifest in ordered_manifests
        }

    planned = sorted(
        (
            (declaration.plan_index, spec.identity, declaration)
            for spec in specs
            for declaration in spec.declarations
        ),
        key=lambda item: item[0],
    )
    for _plan_index, identity, declaration in planned:
        target_path, target_error = _target_path_or_error(root, identity.file_path)
        if target_error is not None:
            errors_by_manifest[declaration.manifest_path].append(target_error)
            continue
        if not allow_dirty:
            dirty_error = _dirty_target_error(root, identity.file_path)
            if dirty_error is not None:
                errors_by_manifest[declaration.manifest_path].append(dirty_error)
                continue
        result, errors = _run_differential_declaration(
            identity,
            declaration,
            root,
            target_path,
            trusted_evidence,
            command_executor,
        )
        results_by_manifest[declaration.manifest_path].append(result)
        errors_by_manifest[declaration.manifest_path].extend(errors)

    return {
        manifest.source_path: KnockoutReport(
            results=tuple(results_by_manifest[manifest.source_path]),
            errors=tuple(errors_by_manifest[manifest.source_path]),
        )
        for manifest in ordered_manifests
    }


def _knockout_evidence_is_current(
    evidence: RuntimeEvidenceBundle,
    manifests: Sequence[Manifest],
    root: Path,
) -> bool:
    relevant = tuple(manifest for manifest in manifests if _knockout_targets(manifest))
    relevant_paths = {manifest.source_path for manifest in relevant}
    commands = tuple(
        command
        for command in evidence.commands
        if command.identity.manifest_path in relevant_paths
    )
    used_environments = {command.environment_identity for command in commands}
    projected = replace(
        evidence,
        commands=commands,
        environment_identities=tuple(
            environment
            for environment in evidence.environment_identities
            if environment in used_environments
        ),
    )
    return runtime_evidence_is_current(
        projected,
        relevant,
        root,
        pytest_workers=evidence.pytest_workers,
    )


def _find_artifact_node(
    tree: ast.AST,
    artifact_name: str,
    artifact_kind: str,
    parent_class: str | None,
) -> ast.FunctionDef | ast.AsyncFunctionDef | None:
    if artifact_kind == ArtifactKind.FUNCTION.value:
        for child in getattr(tree, "body", []):
            if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef)):
                if child.name == artifact_name:
                    return child
        return None

    if artifact_kind != ArtifactKind.METHOD.value or parent_class is None:
        return None

    for child in getattr(tree, "body", []):
        if not isinstance(child, ast.ClassDef) or child.name != parent_class:
            continue
        for class_child in child.body:
            if isinstance(class_child, (ast.FunctionDef, ast.AsyncFunctionDef)):
                if class_child.name == artifact_name:
                    return class_child
    return None


def _knockout_targets(manifest: Manifest) -> list[tuple[str, ArtifactSpec]]:
    targets: list[tuple[str, ArtifactSpec]] = []
    for file_spec in manifest.all_file_specs:
        if not file_spec.path.endswith(".py"):
            continue
        for artifact in file_spec.artifacts:
            if artifact.is_private:
                continue
            if artifact.kind in (ArtifactKind.FUNCTION, ArtifactKind.METHOD):
                targets.append((file_spec.path, artifact))
    return targets


def _dirty_target_error(root: Path, file_path: str) -> ValidationError | None:
    try:
        dirty_paths = {
            _normalize_project_path(root, path) for path in changed_files(root)
        }
    except RuntimeError as exc:
        return ValidationError(
            code=ErrorCode.KNOCKOUT_HARNESS_FAILURE,
            message=f"Knockout could not inspect worktree state: {exc}",
        )

    normalized = _normalize_project_path(root, file_path)
    if normalized not in dirty_paths:
        return None
    return ValidationError(
        code=ErrorCode.KNOCKOUT_HARNESS_FAILURE,
        message=(
            "Knockout refused to modify dirty source file "
            f"{file_path}; rerun with allow_dirty only after reviewing it."
        ),
        location=Location(file=file_path),
    )


def _normalize_project_path(root: Path, file_path: str) -> str:
    try:
        return (root / file_path).resolve().relative_to(root.resolve()).as_posix()
    except (OSError, RuntimeError, ValueError):
        return Path(file_path).as_posix()


def _target_path_or_error(
    root: Path,
    file_path: str,
) -> tuple[Path, ValidationError | None]:
    target_path = root / file_path
    try:
        root_resolved = root.resolve()
        target_resolved = target_path.resolve(strict=False)
        target_resolved.relative_to(root_resolved)
    except (OSError, RuntimeError, ValueError):
        return target_path, _harness_error(
            file_path,
            f"Knockout target path escapes the project root: {file_path}",
        )
    return target_path, None


def _run_differential_declaration(
    identity: KnockoutArtifactIdentity,
    declaration: KnockoutDeclaration,
    root: Path,
    target_path: Path,
    evidence: RuntimeEvidenceBundle | None,
    executor: KnockoutCommandExecutor,
) -> tuple[KnockoutResult, list[ValidationError]]:
    started = time.monotonic()
    errors: list[ValidationError] = []
    proof: KnockoutDifferentialProof | None = None
    original = ""
    original_bytes = b""
    original_hash = ""

    try:
        original_bytes = target_path.read_bytes()
        original = original_bytes.decode("utf-8")
        original_hash = _content_hash(original_bytes)
        rewritten = rewrite_artifact_body(
            original,
            identity.artifact_name,
            identity.artifact_kind,
            identity.parent_class,
        ).encode("utf-8")
        for command_index, command in enumerate(declaration.commands):
            focused = _focused_command(
                evidence, declaration, command_index, identity, root
            )
            if focused is not None:
                focused_command, nodeids = focused
                transition, transition_error = _execute_transition(
                    focused_command,
                    declaration.manifest_slug,
                    root,
                    target_path,
                    identity.file_path,
                    original_bytes,
                    original_hash,
                    rewritten,
                    executor,
                )
                if transition_error is not None:
                    errors.append(transition_error)
                    break
                if len(transition) == 3 and _is_positive_transition(*transition):
                    baseline, mutant, restored = transition
                    proof = _proof(
                        identity,
                        focused_command,
                        baseline,
                        mutant,
                        restored,
                        nodeids,
                        used_exact_fallback=False,
                    )
                    break

            transition, transition_error = _execute_transition(
                command,
                declaration.manifest_slug,
                root,
                target_path,
                identity.file_path,
                original_bytes,
                original_hash,
                rewritten,
                executor,
            )
            if transition_error is not None:
                errors.append(transition_error)
                break
            exact_error = _exact_transition_error(
                identity.file_path, command, transition
            )
            if exact_error is not None:
                errors.append(exact_error)
                break
            if len(transition) < 3:
                continue
            baseline, mutant, restored = transition
            proof = _proof(
                identity,
                command,
                baseline,
                mutant,
                restored,
                (),
                used_exact_fallback=True,
            )
            if mutant.exit_code != 0:
                break
    except Exception as exc:
        errors.append(_harness_error(identity.file_path, str(exc)))
    detected = proof is not None and proof.mutant_exit_code != 0 and not errors
    if not detected and not errors:
        errors.append(_not_detected_error(identity))
    result = KnockoutResult(
        artifact_name=identity.artifact_name,
        artifact_kind=identity.artifact_kind,
        parent_class=identity.parent_class,
        file_path=identity.file_path,
        detected=detected,
        duration_ms=(time.monotonic() - started) * 1000,
        proof=proof,
    )
    return result, errors


def _execute_transition(
    command: tuple[str, ...],
    manifest_slug: str,
    root: Path,
    target_path: Path,
    file_path: str,
    original: bytes,
    original_hash: str,
    rewritten: bytes,
    executor: KnockoutCommandExecutor,
) -> tuple[tuple[TestRunResult, ...], ValidationError | None]:
    try:
        baseline = executor.execute(command, root, manifest_slug)
    except Exception as exc:
        return (), _harness_error(file_path, str(exc))
    try:
        baseline_content = target_path.read_bytes()
    except Exception as exc:
        return (), _harness_error(
            file_path, f"Knockout could not verify baseline target bytes: {exc}"
        )
    if _content_hash(baseline_content) != original_hash:
        return (), _harness_error(
            file_path,
            "Knockout baseline command changed target bytes before mutation; "
            "the command-written file was preserved.",
        )
    if baseline.exit_code != 0:
        return (baseline,), None

    mutation_error: ValidationError | None = None
    mutant: TestRunResult | None = None
    try:
        target_path.write_bytes(rewritten)
        mutant = executor.execute(command, root, manifest_slug)
    except Exception as exc:
        mutation_error = _harness_error(file_path, str(exc))
    finally:
        restore_error = _restore_and_verify(
            target_path,
            file_path,
            original,
            original_hash,
        )
    if restore_error is not None:
        return (), restore_error
    if mutation_error is not None or mutant is None:
        return (), mutation_error or _harness_error(
            file_path, "Knockout mutant command produced no result."
        )
    if mutant.exit_code == 0:
        return (baseline, mutant), None

    restored_error: ValidationError | None = None
    restored: TestRunResult | None = None
    try:
        restored = executor.execute(command, root, manifest_slug)
    except Exception as exc:
        restored_error = _harness_error(
            file_path, f"Knockout restored control failed: {exc}"
        )
    try:
        post_control = target_path.read_bytes()
    except Exception as exc:
        recovery_error = _restore_and_verify(
            target_path,
            file_path,
            original,
            original_hash,
        )
        if recovery_error is not None:
            return (), recovery_error
        return (), _harness_error(
            file_path,
            "Knockout restored control removed or made the target unreadable; "
            f"the original bytes were restored before continuing ({exc}).",
        )
    if _content_hash(post_control) != original_hash:
        recovery_error = _restore_and_verify(
            target_path,
            file_path,
            original,
            original_hash,
        )
        if recovery_error is not None:
            return (), recovery_error
        return (), _harness_error(
            file_path,
            "Knockout restored control changed target bytes; the original bytes "
            "were restored before continuing.",
        )
    if restored_error is not None or restored is None:
        return (), restored_error or _harness_error(
            file_path, "Knockout restored control produced no result."
        )
    return (baseline, mutant, restored), None


def _focused_command(
    evidence: RuntimeEvidenceBundle | None,
    declaration: KnockoutDeclaration,
    command_index: int,
    identity: KnockoutArtifactIdentity,
    root: Path,
) -> tuple[tuple[str, ...], tuple[str, ...]] | None:
    if evidence is None or not evidence.completeness.complete:
        return None
    command_evidence = next(
        (
            item
            for item in evidence.commands
            if item.identity.manifest_path == declaration.manifest_path
            and item.identity.command_index == command_index
            and item.identity.command == declaration.commands[command_index]
        ),
        None,
    )
    if command_evidence is None or not command_evidence.completeness.complete:
        return None
    nodeids = _artifact_nodeids(command_evidence, identity, root)
    if not nodeids:
        return None
    normalized = _normalize_pytest_command(declaration.commands[command_index])
    if normalized is None:
        return None
    prefix, _targets, options = normalized
    return prefix + nodeids + options, nodeids


def _artifact_nodeids(
    evidence: RuntimeCommandEvidence,
    identity: KnockoutArtifactIdentity,
    root: Path,
) -> tuple[str, ...]:
    target = str((root / identity.file_path).resolve())
    qualified = (
        f"{identity.parent_class}.{identity.artifact_name}"
        if identity.parent_class
        else identity.artifact_name
    )
    selected = set(evidence.selected_nodeids)
    nodeids: list[str] = []
    for context in evidence.contexts:
        execution = context.execution_data.get(target)
        if execution is None or qualified not in execution.called_qualnames:
            continue
        if context.kind != "node" or not context.lifecycle_equivalent:
            return ()
        for nodeid in context.consuming_nodeids:
            if nodeid in selected and nodeid not in nodeids:
                nodeids.append(nodeid)
    return tuple(nodeids)


def _is_positive_transition(
    baseline: TestRunResult,
    mutant: TestRunResult,
    restored: TestRunResult,
) -> bool:
    return baseline.exit_code == 0 and mutant.exit_code > 0 and restored.exit_code == 0


def _exact_transition_error(
    file_path: str,
    command: tuple[str, ...],
    transition: tuple[TestRunResult, ...],
) -> ValidationError | None:
    rendered = " ".join(command)
    baseline = transition[0]
    if baseline.exit_code != 0:
        return _harness_error(
            file_path,
            f"Knockout baseline command failed before mutation ({rendered}).",
        )
    mutant = transition[1]
    if mutant.exit_code < 0:
        return _harness_error(
            file_path,
            f"Knockout mutant command could not complete ({rendered}).",
        )
    if len(transition) < 3:
        return None
    restored = transition[2]
    if restored.exit_code != 0:
        return _harness_error(
            file_path,
            f"Knockout restored command failed after mutation ({rendered}).",
        )
    return None


def _proof(
    identity: KnockoutArtifactIdentity,
    command: tuple[str, ...],
    baseline: TestRunResult,
    mutant: TestRunResult,
    restored: TestRunResult,
    nodeids: tuple[str, ...],
    *,
    used_exact_fallback: bool,
) -> KnockoutDifferentialProof:
    return KnockoutDifferentialProof(
        identity=identity,
        command=command,
        baseline_exit_code=baseline.exit_code,
        mutant_exit_code=mutant.exit_code,
        restored_exit_code=restored.exit_code,
        detecting_nodeids=nodeids,
        used_exact_fallback=used_exact_fallback,
        diagnostics=(),
    )


def _not_detected_error(identity: KnockoutArtifactIdentity) -> ValidationError:
    qualified = (
        f"{identity.parent_class}.{identity.artifact_name}"
        if identity.parent_class
        else identity.artifact_name
    )
    return ValidationError(
        code=ErrorCode.ARTIFACT_KNOCKOUT_NOT_DETECTED,
        message=(
            "Validate commands did not provide mutation-caused differential "
            f"detection for {qualified} in {identity.file_path}."
        ),
        location=Location(file=identity.file_path),
        suggestion=(
            "Add behavioral tests that are green before mutation, fail when the "
            'artifact raises NotImplementedError("maid-knockout"), and pass after '
            "restoration."
        ),
    )


def _restore_and_verify(
    target_path: Path,
    file_path: str,
    original: bytes,
    original_hash: str,
) -> ValidationError | None:
    try:
        _restore_file(target_path, original)
        restored = target_path.read_bytes()
    except Exception as exc:
        return _restore_error(file_path, f"Knockout could not restore file: {exc}")

    if _content_hash(restored) != original_hash:
        return _restore_error(
            file_path,
            "Knockout restore hash verification failed.",
        )
    return None


def _restore_file(path: Path, content: bytes) -> None:
    path.write_bytes(content)


def _restore_error(file_path: str, message: str) -> ValidationError:
    return _harness_error(
        file_path,
        message,
        suggestion=f"Recover the file with: git checkout -- {file_path}",
    )


def _harness_error(
    file_path: str,
    message: str,
    *,
    suggestion: str | None = None,
) -> ValidationError:
    return ValidationError(
        code=ErrorCode.KNOCKOUT_HARNESS_FAILURE,
        message=message,
        location=Location(file=file_path),
        suggestion=suggestion,
    )


def _content_hash(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


def _result_to_dict(result: KnockoutResult) -> dict:
    return {
        "artifact_name": result.artifact_name,
        "artifact_kind": result.artifact_kind,
        "parent_class": result.parent_class,
        "file_path": result.file_path,
        "detected": result.detected,
        "duration_ms": result.duration_ms,
        "proof": _proof_to_dict(result.proof) if result.proof is not None else None,
    }


def _proof_to_dict(proof: KnockoutDifferentialProof) -> dict:
    return {
        "identity": {
            "file_path": proof.identity.file_path,
            "artifact_name": proof.identity.artifact_name,
            "artifact_kind": proof.identity.artifact_kind,
            "parent_class": proof.identity.parent_class,
        },
        "command": list(proof.command),
        "baseline_exit_code": proof.baseline_exit_code,
        "mutant_exit_code": proof.mutant_exit_code,
        "restored_exit_code": proof.restored_exit_code,
        "detecting_nodeids": list(proof.detecting_nodeids),
        "used_exact_fallback": proof.used_exact_fallback,
        "diagnostics": [item.to_dict() for item in proof.diagnostics],
    }
