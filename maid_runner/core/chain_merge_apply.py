"""Materialize a merged manifest chain (chain-merge child 4).

`maid chain merge <file> --apply` reuses the snapshot primitive to write a
current-state snapshot manifest that supersedes the file's active chain. It
refuses (writing nothing) rather than ever violating the anti-gaming
artifact-preservation audit — on BLOCKED/LEAN verdicts, when a superseded
manifest contains contradictory artifact/delete intent, and when the fresh
snapshot would drop a declared public artifact of this file. Whole-manifest
obligations are carried into the replacement. Tests are never touched; only a
manifest is written.
"""

from __future__ import annotations

import dataclasses
from dataclasses import dataclass
from pathlib import Path

from maid_runner.core.chain import ManifestChain
from maid_runner.core.chain_merge import ChainMergeVerdict, build_chain_merge_report
from maid_runner.core.snapshot import generate_snapshot, save_snapshot
from maid_runner.core.types import (
    AcceptanceConfig,
    ArtifactKind,
    ArtifactSpec,
    FileMode,
    FileSpec,
    Manifest,
    ScopeSpec,
)
from maid_runner.validators.registry import ValidatorRegistry


@dataclass(frozen=True)
class ChainMergeApplyResult:
    """Outcome of an apply attempt."""

    applied: bool
    snapshot_path: str | None
    superseded_slugs: tuple[str, ...]
    refused_reason: str | None
    missing_artifacts: tuple[str, ...]


def apply_chain_merge(
    file_path: str,
    chain: ManifestChain,
    project_root: str = ".",
    output_dir: str = "manifests/",
    registry: ValidatorRegistry | None = None,
) -> ChainMergeApplyResult:
    """Materialize the merged contract for ``file_path`` as a snapshot manifest.

    Refuses (writing nothing) on BLOCKED/LEAN verdicts, contradictory
    artifact/delete path intent, and when the current snapshot drops any public
    artifact the chain declared for this file. Other whole-manifest obligations
    are projected into the replacement before its single save.
    """
    report = build_chain_merge_report(file_path, chain, None)

    if report.verdict is ChainMergeVerdict.BLOCKED:
        return _refused(f"{file_path} is BLOCKED: {'; '.join(report.blocking_reasons)}")
    if report.verdict is ChainMergeVerdict.LEAN:
        return _refused(f"{file_path} is already LEAN; nothing to merge.")

    # Only supersede manifests that actually declare artifacts in this file —
    # scope-only references are not contracts to collapse.
    to_supersede = [
        m
        for m in chain.manifests_for_file(file_path)
        if _declares_artifacts_in(m, file_path)
    ]

    snapshot = generate_snapshot(
        Path(project_root) / file_path,
        project_root=project_root,
        registry=registry,
    )
    snapshot_artifacts = tuple(
        artifact
        for file_spec in snapshot.files_snapshot
        for artifact in file_spec.artifacts
    )
    declared_artifacts = tuple(
        artifact
        for artifact in chain.merged_artifacts_for(file_path)
        if not artifact.is_private
    )
    missing = tuple(
        sorted(
            artifact.contract_key()
            for artifact in declared_artifacts
            if not _snapshot_contains_artifact(snapshot_artifacts, artifact)
        )
    )
    if missing:
        return ChainMergeApplyResult(
            applied=False,
            snapshot_path=None,
            superseded_slugs=(),
            refused_reason=(
                f"Refusing to merge {file_path}: the current snapshot drops "
                f"{len(missing)} declared artifact(s); reconcile the chain first."
            ),
            missing_artifacts=missing,
        )

    carried_specs = _carried_file_specs(to_supersede, file_path, chain)
    artifact_paths = {file_path, *(spec.path for spec in carried_specs)}
    delete_paths = {
        deleted.path for manifest in to_supersede for deleted in manifest.files_delete
    }
    conflicts = sorted(artifact_paths & delete_paths)
    if conflicts:
        return _refused(
            f"Refusing to merge {file_path}: path(s) {', '.join(conflicts)} "
            "are declared both artifact-bearing and deleted. Reconcile the "
            "conflicting whole-manifest obligations first."
        )

    private_only_paths = tuple(
        spec.path for spec in carried_specs if not spec.artifacts
    )
    materialized_specs = tuple(spec for spec in carried_specs if spec.artifacts)
    files_create = tuple(
        spec for spec in materialized_specs if spec.mode is FileMode.CREATE
    )
    files_edit = tuple(
        spec for spec in materialized_specs if spec.mode is FileMode.EDIT
    )
    files_snapshot = snapshot.files_snapshot + tuple(
        spec for spec in materialized_specs if spec.mode is FileMode.SNAPSHOT
    )
    writable_artifact_paths = {spec.path for spec in files_create}
    writable_artifact_paths.update(spec.path for spec in files_edit)
    writable_artifact_paths.update(spec.path for spec in files_snapshot)

    files_delete = _first_by_path(
        deleted for manifest in to_supersede for deleted in manifest.files_delete
    )
    deleted_paths = {deleted.path for deleted in files_delete}
    files_scope = _first_by_path(
        scoped
        for scoped in (
            *(scoped for manifest in to_supersede for scoped in manifest.files_scope),
            *(
                ScopeSpec(
                    path=path,
                    reason=(
                        "Preserve ownership of a private-only writable path "
                        "during chain merge."
                    ),
                )
                for path in private_only_paths
            ),
        )
        if scoped.path not in writable_artifact_paths
        and scoped.path not in deleted_paths
    )
    scoped_paths = {scoped.path for scoped in files_scope}
    files_read = _first_strings(
        path
        for path in (
            *(path for manifest in to_supersede for path in manifest.files_read),
            *snapshot.files_read,
        )
        if path not in writable_artifact_paths
        and path not in deleted_paths
        and path not in scoped_paths
    )

    target_spec = files_snapshot[0]
    target_artifacts = _merge_target_artifacts(
        declared_artifacts,
        target_spec.artifacts,
    )
    target_imports = _first_strings(
        item
        for item in (
            *target_spec.imports,
            *(
                imported
                for manifest in to_supersede
                for spec in manifest.all_file_specs
                if spec.path == file_path
                for imported in spec.imports
            ),
        )
    )
    files_snapshot = (
        dataclasses.replace(
            target_spec,
            artifacts=target_artifacts,
            imports=target_imports,
        ),
        *files_snapshot[1:],
    )

    superseded_slugs = tuple(sorted(m.slug for m in to_supersede))
    snapshot_slug = _noncolliding_snapshot_slug(
        snapshot.slug,
        {manifest.slug for manifest in chain.all_manifests},
        Path(output_dir),
    )
    snapshot = dataclasses.replace(
        snapshot,
        slug=snapshot_slug,
        supersedes=superseded_slugs,
        validate_commands=_first_commands(to_supersede),
        files_create=files_create,
        files_edit=files_edit,
        files_snapshot=files_snapshot,
        files_read=files_read,
        files_scope=files_scope,
        files_delete=files_delete,
        acceptance=_merged_acceptance(to_supersede),
        removed_artifacts=_first_removed_artifacts(to_supersede),
    )
    out_path = save_snapshot(snapshot, output_dir=output_dir)

    return ChainMergeApplyResult(
        applied=True,
        snapshot_path=str(out_path),
        superseded_slugs=superseded_slugs,
        refused_reason=None,
        missing_artifacts=(),
    )


def _declares_artifacts_in(manifest: Manifest, file_path: str) -> bool:
    return any(fs.path == file_path and fs.artifacts for fs in manifest.all_file_specs)


def _carried_file_specs(
    manifests: list[Manifest], target_path: str, chain: ManifestChain
) -> tuple[FileSpec, ...]:
    by_path: dict[str, list[FileSpec]] = {}
    for manifest in manifests:
        for spec in manifest.all_file_specs:
            if spec.path != target_path:
                by_path.setdefault(spec.path, []).append(spec)

    priority = {
        FileMode.CREATE: 0,
        FileMode.SNAPSHOT: 1,
        FileMode.EDIT: 2,
    }
    carried: list[FileSpec] = []
    for path, specs in by_path.items():
        artifacts = tuple(
            artifact
            for artifact in chain.merged_artifacts_for(path)
            if not artifact.is_private
        )
        imports = _first_strings(item for spec in specs for item in spec.imports)
        strictest = min(specs, key=lambda spec: priority[spec.mode])
        carried.append(
            FileSpec(
                path=path,
                artifacts=artifacts,
                status=strictest.status,
                mode=strictest.mode,
                imports=imports,
            )
        )
    return tuple(carried)


def _snapshot_contains_artifact(
    snapshot_artifacts: tuple[ArtifactSpec, ...],
    declared: ArtifactSpec,
) -> bool:
    if declared.signature is not None:
        return any(
            candidate.contract_key() == declared.contract_key()
            for candidate in snapshot_artifacts
        )
    return any(
        _artifacts_structurally_match(declared, candidate)
        for candidate in snapshot_artifacts
    )


def _artifacts_structurally_match(
    declared: ArtifactSpec,
    candidate: ArtifactSpec,
) -> bool:
    if declared.signature is not None or candidate.signature is not None:
        return declared.contract_key() == candidate.contract_key()
    if declared.merge_key() == candidate.merge_key():
        return True
    function_kinds = {ArtifactKind.FUNCTION, ArtifactKind.TEST_FUNCTION}
    return (
        declared.kind in function_kinds
        and candidate.kind in function_kinds
        and declared.of is None
        and candidate.of is None
        and declared.name == candidate.name
    )


def _merge_target_artifacts(
    declared: tuple[ArtifactSpec, ...],
    inferred: tuple[ArtifactSpec, ...],
) -> tuple[ArtifactSpec, ...]:
    merged = list(declared)
    for candidate in inferred:
        if candidate.is_private:
            continue
        if any(
            _artifacts_structurally_match(existing, candidate) for existing in merged
        ):
            continue
        merged.append(candidate)
    return tuple(merged)


def _first_strings(items) -> tuple[str, ...]:
    return tuple(dict.fromkeys(items))


def _first_commands(manifests: list[Manifest]) -> tuple[tuple[str, ...], ...]:
    return tuple(
        dict.fromkeys(
            command for manifest in manifests for command in manifest.validate_commands
        )
    )


def _first_by_path(items):
    by_path = {}
    for item in items:
        by_path.setdefault(item.path, item)
    return tuple(by_path.values())


def _merged_acceptance(manifests: list[Manifest]) -> AcceptanceConfig | None:
    acceptances = [manifest.acceptance for manifest in manifests if manifest.acceptance]
    if not acceptances:
        return None
    return AcceptanceConfig(
        tests=tuple(
            dict.fromkeys(
                command for acceptance in acceptances for command in acceptance.tests
            )
        ),
        immutable=any(acceptance.immutable for acceptance in acceptances),
    )


def _first_removed_artifacts(manifests: list[Manifest]):
    by_key = {}
    for manifest in manifests:
        for removed in manifest.removed_artifacts:
            key = (removed.file, removed.kind, removed.of, removed.name)
            by_key.setdefault(key, removed)
    return tuple(by_key.values())


def _noncolliding_snapshot_slug(
    base_slug: str, existing_slugs: set[str], output_dir: Path
) -> str:
    candidate = base_slug
    suffix = 2
    while (
        candidate in existing_slugs
        or (output_dir / f"{candidate}.manifest.yaml").exists()
    ):
        candidate = f"{base_slug}-{suffix}"
        suffix += 1
    return candidate


def _refused(reason: str) -> ChainMergeApplyResult:
    return ChainMergeApplyResult(
        applied=False,
        snapshot_path=None,
        superseded_slugs=(),
        refused_reason=reason,
        missing_artifacts=(),
    )
