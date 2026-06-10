"""Validate-command suggestions for generated draft manifests."""

from __future__ import annotations

from pathlib import Path
import shlex
from typing import Union

from maid_runner.core._file_discovery import discover_source_files, is_test_file
from maid_runner.core.diff_scope import DiffScopeResult
from maid_runner.core.types import ArtifactSpec
from maid_runner.validators.base import FoundArtifact
from maid_runner.validators.registry import UnsupportedLanguageError, ValidatorRegistry


def suggest_validate_commands(
    diff: DiffScopeResult,
    project_root: Union[str, Path],
    draft_path: Union[str, Path],
) -> "tuple[str, ...]":
    """Return deterministic pytest suggestions plus schema validation."""
    root = Path(project_root)
    changed_artifacts = _changed_artifacts(diff)
    schema_command = _schema_validate_command(Path(draft_path))
    if not changed_artifacts:
        return (schema_command,)

    registry = ValidatorRegistry.with_builtin_validators()
    suggested_tests = [
        path
        for path in discover_source_files(
            root,
            extensions=registry.supported_extensions(),
        )
        if is_test_file(path)
        and _test_references_changed_artifact(root, path, registry, changed_artifacts)
    ]

    return tuple(
        [f"pytest {shlex.quote(path)} -v" for path in sorted(set(suggested_tests))]
        + [schema_command]
    )


def _changed_artifacts(diff: DiffScopeResult) -> tuple[ArtifactSpec, ...]:
    artifacts: list[ArtifactSpec] = []
    for delta in diff.deltas:
        artifacts.extend(delta.added)
        artifacts.extend(delta.signature_changed)
        artifacts.extend(delta.removed)
    return tuple(artifacts)


def _test_references_changed_artifact(
    root: Path,
    test_path: str,
    registry: ValidatorRegistry,
    changed_artifacts: tuple[ArtifactSpec, ...],
) -> bool:
    absolute_path = root / test_path
    if not absolute_path.is_file() or not registry.has_validator(absolute_path):
        return False
    try:
        source = absolute_path.read_text()
    except (OSError, UnicodeDecodeError):
        return False

    try:
        validator = registry.get(absolute_path)
        result = validator.collect_behavioral_artifacts(source, absolute_path)
    except (ImportError, UnsupportedLanguageError):
        return False
    if result.errors:
        return False
    return any(
        _references_artifact(reference, artifact)
        for reference in result.artifacts
        for artifact in changed_artifacts
    )


def _references_artifact(reference: FoundArtifact, artifact: ArtifactSpec) -> bool:
    if reference.name != artifact.name:
        return False
    if artifact.of is not None:
        return reference.of == artifact.of
    return True


def _schema_validate_command(path: Path) -> str:
    return f"maid validate {shlex.quote(path.as_posix())} --mode schema --quiet"
