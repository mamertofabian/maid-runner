"""Baseline diff-scope collection for MAID Runner v2.

Partitions baseline-changed files into created/edited/deleted sets and
collects per-file public artifact deltas, reusing the changed-scope git
plumbing from :mod:`maid_runner.core.worktree` and the snapshot artifact
collectors. This is the foundation for `maid manifest from-diff`.
"""

from __future__ import annotations

import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Optional, Union

from maid_runner.core.snapshot import _found_to_spec
from maid_runner.core.types import ArtifactSpec
from maid_runner.core.worktree import (
    ChangedScopeBaseline,
    _baseline_commitish,
    changed_files,
    changed_files_since,
)
from maid_runner.validators.base import FoundArtifact
from maid_runner.validators.registry import ValidatorRegistry

_BASELINE_SOURCES = ("since", "base-ref", "worktree")


class DiffScopeError(Exception):
    """Raised for missing/invalid baselines or unparseable changed sources."""


@dataclass(frozen=True)
class DiffScopeBaseline:
    """Resolved baseline for diff-scope collection."""

    source: str
    commitish: str | None = None


@dataclass(frozen=True)
class FileArtifactDelta:
    """Public artifact delta for one changed file."""

    path: str
    added: tuple[ArtifactSpec, ...] = ()
    signature_changed: tuple[ArtifactSpec, ...] = ()
    removed: tuple[ArtifactSpec, ...] = ()


@dataclass(frozen=True)
class DiffScopeResult:
    """Deterministic partition of changed paths plus per-file deltas."""

    created: tuple[str, ...]
    edited: tuple[str, ...]
    deleted: tuple[str, ...]
    deltas: tuple[FileArtifactDelta, ...]


def collect_diff_scope(
    project_root: Union[str, Path],
    baseline: DiffScopeBaseline,
) -> DiffScopeResult:
    """Collect baseline-changed files and their public artifact deltas."""
    root = Path(project_root).resolve()
    _validate_baseline(baseline)
    paths = _changed_paths(root, baseline)
    commitish = _resolve_baseline_commitish(root, baseline)
    registry = ValidatorRegistry.with_builtin_validators()

    created: list[str] = []
    edited: list[str] = []
    deleted: list[str] = []
    deltas: list[FileArtifactDelta] = []

    for path in sorted(set(paths)):
        in_worktree = (root / path).is_file()
        baseline_content = _baseline_file_content(root, commitish, path)
        if not in_worktree and baseline_content is None:
            # Path is gone on both sides (e.g. created and deleted within the
            # task window); there is no contract to report for it.
            continue

        if baseline_content is None:
            created.append(path)
        elif in_worktree:
            edited.append(path)
        else:
            deleted.append(path)

        # Content is only decoded for files a validator can parse; binary
        # and other non-source files stay in the partitions with empty deltas.
        has_validator = registry.has_validator(root / path)
        baseline_specs = (
            _public_artifact_specs(
                registry, root, path, _decode_source(baseline_content, path)
            )
            if has_validator and baseline_content is not None
            else ()
        )
        current_specs = (
            _public_artifact_specs(
                registry, root, path, _read_worktree_source(root, path)
            )
            if has_validator and in_worktree
            else ()
        )
        deltas.append(_file_delta(path, baseline_specs, current_specs))

    return DiffScopeResult(
        created=tuple(created),
        edited=tuple(edited),
        deleted=tuple(deleted),
        deltas=tuple(deltas),
    )


def _validate_baseline(baseline: DiffScopeBaseline) -> None:
    if baseline.source not in _BASELINE_SOURCES:
        raise DiffScopeError(
            f"Unknown diff-scope baseline source {baseline.source!r}; "
            f"expected one of: {', '.join(_BASELINE_SOURCES)}"
        )
    if baseline.source == "worktree":
        if baseline.commitish is not None:
            raise DiffScopeError(
                "Worktree diff-scope baseline must not carry a commitish"
            )
        return
    if not baseline.commitish:
        raise DiffScopeError(
            f"Diff-scope baseline source {baseline.source!r} requires a "
            "commitish; MAID will not guess main, dev, or a remote branch"
        )


def _changed_paths(root: Path, baseline: DiffScopeBaseline) -> tuple[str, ...]:
    try:
        if baseline.source == "worktree":
            return changed_files(root)
        assert baseline.commitish is not None
        return changed_files_since(
            root,
            ChangedScopeBaseline(source=baseline.source, commitish=baseline.commitish),
        )
    except RuntimeError as exc:
        raise DiffScopeError(str(exc)) from exc


def _resolve_baseline_commitish(root: Path, baseline: DiffScopeBaseline) -> str:
    if baseline.source == "worktree":
        return "HEAD"
    assert baseline.commitish is not None
    if baseline.source == "since":
        return baseline.commitish
    try:
        return _baseline_commitish(
            root,
            ChangedScopeBaseline(source=baseline.source, commitish=baseline.commitish),
        )
    except RuntimeError as exc:
        raise DiffScopeError(str(exc)) from exc


def _baseline_file_content(root: Path, commitish: str, path: str) -> Optional[bytes]:
    try:
        result = subprocess.run(
            ["git", "show", f"{commitish}:{path}"],
            cwd=root,
            capture_output=True,
            timeout=10,
        )
    except FileNotFoundError as exc:
        raise DiffScopeError(
            "Diff-scope collection requires git metadata: git executable not found"
        ) from exc
    except subprocess.TimeoutExpired as exc:
        raise DiffScopeError(
            "Diff-scope collection requires git metadata: git show timed out"
        ) from exc

    if result.returncode != 0:
        return None
    return result.stdout


def _decode_source(content: bytes, path: str) -> str:
    try:
        return content.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise DiffScopeError(f"Failed to decode {path} as UTF-8 source") from exc


def _read_worktree_source(root: Path, path: str) -> str:
    try:
        return (root / path).read_text()
    except (UnicodeDecodeError, OSError) as exc:
        raise DiffScopeError(f"Failed to read {path} as UTF-8 source") from exc


def _public_artifact_specs(
    registry: ValidatorRegistry,
    root: Path,
    path: str,
    source: str,
) -> tuple[ArtifactSpec, ...]:
    abs_path = root / path
    if not registry.has_validator(abs_path):
        return ()
    validator = registry.get(abs_path)
    result = validator.collect_implementation_artifacts(source, abs_path)
    if result.errors:
        raise DiffScopeError(f"Failed to parse {path}: {'; '.join(result.errors)}")
    return _sorted_specs(
        _found_to_spec(artifact)
        for artifact in result.artifacts
        if _is_public(artifact)
    )


def _is_public(artifact: FoundArtifact) -> bool:
    return not artifact.is_private


def _file_delta(
    path: str,
    baseline_specs: tuple[ArtifactSpec, ...],
    current_specs: tuple[ArtifactSpec, ...],
) -> FileArtifactDelta:
    baseline_by_identity = {_identity(spec): spec for spec in baseline_specs}
    current_by_identity = {_identity(spec): spec for spec in current_specs}

    added = [
        spec
        for identity, spec in current_by_identity.items()
        if identity not in baseline_by_identity
    ]
    removed = [
        spec
        for identity, spec in baseline_by_identity.items()
        if identity not in current_by_identity
    ]
    signature_changed = [
        spec
        for identity, spec in current_by_identity.items()
        if identity in baseline_by_identity
        and _signature_differs(baseline_by_identity[identity], spec)
    ]

    return FileArtifactDelta(
        path=path,
        added=_sorted_specs(added),
        signature_changed=_sorted_specs(signature_changed),
        removed=_sorted_specs(removed),
    )


def _identity(spec: ArtifactSpec) -> tuple[str, str]:
    return (spec.name, spec.of or "")


def _signature_differs(baseline: ArtifactSpec, current: ArtifactSpec) -> bool:
    return (baseline.kind, baseline.args, baseline.returns) != (
        current.kind,
        current.args,
        current.returns,
    )


def _sorted_specs(specs) -> tuple[ArtifactSpec, ...]:
    return tuple(sorted(specs, key=_identity))
