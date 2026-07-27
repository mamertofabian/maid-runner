"""Render schema-valid draft manifests from diff-scope collection."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
import shlex
from typing import Union

import yaml

from maid_runner.core.diff_scope import (
    DiffScopeBaseline,
    DiffScopeError,
    DiffScopeResult,
    FileArtifactDelta,
    _resolve_baseline_commitish,
)
from maid_runner.core.manifest import (
    _SUFFIX_FORMATS,
    prepend_manifest_header,
    validate_manifest_schema,
)
from maid_runner.core.types import ArtifactKind, ArtifactSpec
from maid_runner.core.validate_suggestions import suggest_validate_commands

_GOAL_PLACEHOLDER = "TODO: describe this change"
_GENERATED_BY = "maid-manifest-from-diff"


class FromDiffRenderError(Exception):
    """Raised when generated draft validation or output writing fails."""


def default_from_diff_slug(
    project_root: Union[str, Path],
    baseline: DiffScopeBaseline,
) -> str:
    """Return the default from-diff slug for a resolved baseline."""
    root = Path(project_root).resolve()
    try:
        commitish = _resolve_baseline_commitish(root, baseline)
    except DiffScopeError:
        raise
    short_hash = _short_commit_hash(root, commitish)
    date = datetime.now(timezone.utc).date().isoformat()
    return f"from-diff-{date}-{short_hash}"


def build_from_diff_manifest(
    diff: DiffScopeResult,
    project_root: Union[str, Path],
    slug: str,
) -> dict:
    """Render diff-scope data into deterministic draft manifest data."""
    if not diff.created and not diff.edited and not diff.deleted:
        raise FromDiffRenderError("No changed files found for diff-scope manifest.")

    delta_by_path = {delta.path: delta for delta in diff.deltas}
    files: dict = {}

    create_entries = [
        {
            "path": path,
            "artifacts": _artifact_dicts(
                _created_artifacts(delta_by_path.get(path), path)
            ),
        }
        for path in sorted(diff.created)
    ]
    if create_entries:
        files["create"] = create_entries

    edit_entries = [
        {
            "path": path,
            "artifacts": _artifact_dicts(
                _edited_artifacts(delta_by_path.get(path), path)
            ),
        }
        for path in sorted(diff.edited)
    ]
    if edit_entries:
        files["edit"] = edit_entries

    delete_entries = [
        {"path": path, "reason": "File was removed in the diff."}
        for path in sorted(diff.deleted)
    ]
    if delete_entries:
        files["delete"] = delete_entries

    return {
        "schema": "2",
        "goal": _GOAL_PLACEHOLDER,
        "type": "feature",
        "metadata": {
            "generated_by": _GENERATED_BY,
            "needs_review": True,
        },
        "files": files,
        "validate": list(
            suggest_validate_commands(
                diff,
                project_root,
                Path("manifests") / "drafts" / f"{slug}.manifest.yaml",
            )
        ),
    }


def validate_from_diff_output_suffix(output_path: Union[str, Path]) -> None:
    """Reject an output suffix this writer cannot correctly emit.

    ``write_from_diff_manifest`` always emits YAML, and ``load_manifest_raw``
    dispatches on the output suffix when reading the file back, so a suffix the
    reader maps to any other format would produce a draft MAID cannot load. The
    accepted set is derived from ``_SUFFIX_FORMATS`` rather than restated, so
    this guard cannot drift away from the reader it has to agree with.

    from-diff is YAML-only by design: a draft exists to be promoted, and
    ``maid manifest promote`` accepts only ``*.manifest.yaml`` and
    ``*.manifest.yml``, so a JSON draft would be a dead end even if it were
    written as well-formed JSON.
    """
    # Matched case-sensitively on purpose: load_manifest_raw and manifest chain
    # discovery both dispatch on the exact lowercase suffix, so accepting
    # ".YAML" here would write a draft MAID cannot load back.
    suffix = Path(output_path).suffix
    supported = sorted(
        candidate
        for candidate, output_format in _SUFFIX_FORMATS.items()
        if output_format == "yaml"
    )
    if suffix not in supported:
        raise FromDiffRenderError(
            f"Manifest from-diff writes YAML; unsupported output suffix "
            f"{suffix!r}: use one of {', '.join(supported)}"
        )


def write_from_diff_manifest(
    data: dict,
    output_path: Union[str, Path],
    force: bool = False,
) -> Path:
    """Validate and write a byte-stable draft manifest."""
    path = Path(output_path)
    if not _is_draft_output_path(path):
        raise FromDiffRenderError(
            f"Manifest from-diff output must be under manifests/drafts/: {path}"
        )
    # Ahead of the force/exists branch, the schema check, and the parent mkdir,
    # so a rejected suffix leaves no filesystem effect behind.
    validate_from_diff_output_suffix(path)
    if path.exists() and not force:
        raise FromDiffRenderError(f"Manifest already exists: {path}")

    errors = validate_manifest_schema(data)
    if errors:
        raise FromDiffRenderError(
            f"Generated manifest schema validation failed: {errors[0]}"
        )

    rendered = prepend_manifest_header(
        yaml.safe_dump(data, default_flow_style=False, sort_keys=False)
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(rendered)
    return path


def _short_commit_hash(root: Path, commitish: str) -> str:
    import subprocess

    try:
        result = subprocess.run(
            ["git", "rev-parse", "--short", commitish],
            cwd=root,
            check=True,
            capture_output=True,
            text=True,
            timeout=10,
        )
    except (
        FileNotFoundError,
        subprocess.CalledProcessError,
        subprocess.TimeoutExpired,
    ) as exc:
        raise DiffScopeError(
            f"Invalid diff-scope baseline commitish: {commitish}"
        ) from exc
    return result.stdout.strip()


def _created_artifacts(
    delta: FileArtifactDelta | None,
    path: str,
) -> tuple[ArtifactSpec, ...]:
    artifacts = delta.added if delta is not None else ()
    return artifacts or (_placeholder_artifact(path),)


def _edited_artifacts(
    delta: FileArtifactDelta | None,
    path: str,
) -> tuple[ArtifactSpec, ...]:
    artifacts = ()
    if delta is not None:
        artifacts = delta.added + delta.signature_changed
    return tuple(sorted(artifacts, key=_artifact_sort_key)) or (
        _placeholder_artifact(path),
    )


def _placeholder_artifact(path: str) -> ArtifactSpec:
    stem = Path(path).stem.replace("-", "_") or "changed_file"
    return ArtifactSpec(
        kind=ArtifactKind.ATTRIBUTE,
        name=f"_generated_placeholder_{stem}",
        description=(
            "Generated placeholder for a changed file with no detected public "
            "artifact delta; replace during draft review."
        ),
    )


def _artifact_dicts(artifacts: tuple[ArtifactSpec, ...]) -> list[dict]:
    return [
        _artifact_to_dict(artifact)
        for artifact in sorted(artifacts, key=_artifact_sort_key)
    ]


def _artifact_to_dict(artifact: ArtifactSpec) -> dict:
    data = {
        "kind": artifact.kind.value,
        "name": artifact.name,
    }
    if artifact.description:
        data["description"] = artifact.description
    if artifact.args:
        data["args"] = [_arg_to_dict(arg) for arg in artifact.args]
    if artifact.returns:
        data["returns"] = artifact.returns
    if artifact.raises:
        data["raises"] = list(artifact.raises)
    if artifact.is_async:
        data["async"] = True
    if artifact.bases:
        data["bases"] = list(artifact.bases)
    if artifact.type_parameters:
        data["type_parameters"] = list(artifact.type_parameters)
    if artifact.of:
        data["of"] = artifact.of
    if artifact.type_annotation:
        data["type"] = artifact.type_annotation
    return data


def _arg_to_dict(arg) -> dict:
    data = {"name": arg.name}
    if arg.type:
        data["type"] = arg.type
    if arg.default is not None:
        data["default"] = arg.default
    return data


def _artifact_sort_key(artifact: ArtifactSpec) -> tuple[str, str, str]:
    return (artifact.name, artifact.of or "", artifact.kind.value)


def _schema_validate_command(path: Path) -> str:
    return f"maid validate {shlex.quote(path.as_posix())} --mode schema --quiet"


def _is_draft_output_path(path: Path) -> bool:
    root = Path.cwd().resolve(strict=False)
    draft_root = (root / "manifests" / "drafts").resolve(strict=False)
    candidate = path if path.is_absolute() else root / path
    try:
        candidate.resolve(strict=False).relative_to(draft_root)
    except ValueError:
        return False
    return True
