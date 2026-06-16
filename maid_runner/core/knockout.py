"""Artifact knockout rewrite/run/restore engine."""

from __future__ import annotations

import ast
import hashlib
import time
from dataclasses import dataclass
from pathlib import Path

from maid_runner.core._test_command_execution import _run_test_command
from maid_runner.core.result import ErrorCode, Location, ValidationError
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
    replacement = f'{indent}raise NotImplementedError("maid-knockout")\n'

    if first_body.lineno == node.lineno:
        signature = lines[start][: first_body.col_offset].rstrip()
        lines[start:end] = [f"{signature}\n", replacement]
    else:
        lines[start:end] = [replacement]
    return "".join(lines)


def run_knockout(
    manifest: Manifest,
    project_root: Path,
    limit: int | None = None,
    allow_dirty: bool = False,
) -> KnockoutReport:
    root = Path(project_root)
    targets = _knockout_targets(manifest)
    if limit is not None:
        targets = targets[: max(limit, 0)]

    results: list[KnockoutResult] = []
    errors: list[ValidationError] = []
    for file_path, artifact in targets:
        target_path, target_error = _target_path_or_error(root, file_path)
        if target_error is not None:
            errors.append(target_error)
            continue
        if not allow_dirty:
            dirty_error = _dirty_target_error(root, file_path)
            if dirty_error is not None:
                errors.append(dirty_error)
                continue
        result, artifact_errors = _run_single_knockout(
            manifest,
            root,
            file_path,
            target_path,
            artifact,
        )
        results.append(result)
        errors.extend(artifact_errors)
    return KnockoutReport(results=tuple(results), errors=tuple(errors))


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


def _run_single_knockout(
    manifest: Manifest,
    root: Path,
    file_path: str,
    target_path: Path,
    artifact: ArtifactSpec,
) -> tuple[KnockoutResult, list[ValidationError]]:
    started = time.monotonic()
    detected = False
    errors: list[ValidationError] = []
    original = ""
    original_hash = ""

    try:
        original = target_path.read_text()
        original_hash = _content_hash(original)
        rewritten = rewrite_artifact_body(
            original,
            artifact.name,
            artifact.kind.value,
            artifact.of,
        )
        target_path.write_text(rewritten)
        detected, errors = _run_validate_commands(manifest, root, file_path, artifact)
    except Exception as exc:
        errors.append(_harness_error(file_path, str(exc)))
    finally:
        if original:
            restore_error = _restore_and_verify(
                target_path,
                file_path,
                original,
                original_hash,
            )
            if restore_error is not None:
                errors.append(restore_error)

    duration_ms = (time.monotonic() - started) * 1000
    result = KnockoutResult(
        artifact_name=artifact.name,
        artifact_kind=artifact.kind.value,
        parent_class=artifact.of,
        file_path=file_path,
        detected=detected,
        duration_ms=duration_ms,
    )
    return result, errors


def _run_validate_commands(
    manifest: Manifest,
    root: Path,
    file_path: str,
    artifact: ArtifactSpec,
) -> tuple[bool, list[ValidationError]]:
    errors: list[ValidationError] = []
    detected = False
    for command in manifest.validate_commands:
        try:
            result = _run_test_command(
                command,
                cwd=root,
                manifest_slug=manifest.slug,
            )
        except Exception as exc:
            errors.append(_harness_error(file_path, str(exc)))
            continue
        if result.exit_code == -2:
            errors.append(
                _harness_error(
                    file_path,
                    "Knockout validate command could not be spawned: "
                    f"{result.stderr or result.stdout}",
                )
            )
            continue
        if result.exit_code != 0:
            detected = True

    if not detected and not errors:
        qualified = artifact.qualified_name
        errors.append(
            ValidationError(
                code=ErrorCode.ARTIFACT_KNOCKOUT_NOT_DETECTED,
                message=(
                    "Validate commands still passed with knocked-out artifact "
                    f"{qualified} in {file_path}."
                ),
                location=Location(file=file_path),
                suggestion=(
                    "Add behavioral tests that fail when this artifact raises "
                    'NotImplementedError("maid-knockout").'
                ),
            )
        )
    return detected, errors


def _restore_and_verify(
    target_path: Path,
    file_path: str,
    original: str,
    original_hash: str,
) -> ValidationError | None:
    try:
        _restore_file(target_path, original)
        restored = target_path.read_text()
    except Exception as exc:
        return _restore_error(file_path, f"Knockout could not restore file: {exc}")

    if _content_hash(restored) != original_hash:
        return _restore_error(
            file_path,
            "Knockout restore hash verification failed.",
        )
    return None


def _restore_file(path: Path, content: str) -> None:
    path.write_text(content)


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


def _content_hash(content: str) -> str:
    return hashlib.sha256(content.encode("utf-8")).hexdigest()


def _result_to_dict(result: KnockoutResult) -> dict:
    return {
        "artifact_name": result.artifact_name,
        "artifact_kind": result.artifact_kind,
        "parent_class": result.parent_class,
        "file_path": result.file_path,
        "detected": result.detected,
        "duration_ms": result.duration_ms,
    }
