"""Materialize a merged manifest chain (chain-merge child 4).

`maid chain merge <file> --apply` reuses the snapshot primitive to write a
current-state snapshot manifest that supersedes the file's active chain. It
refuses (writing nothing) rather than ever violating the anti-gaming
artifact-preservation audit — on BLOCKED/LEAN verdicts, when a superseded
manifest declares artifacts in OTHER files a single-file snapshot cannot
preserve, and when the fresh snapshot would drop a declared artifact of this
file. Tests are never touched; only a manifest is written.
"""

from __future__ import annotations

import dataclasses
from dataclasses import dataclass
from pathlib import Path

from maid_runner.core.chain import ManifestChain
from maid_runner.core.chain_merge import ChainMergeVerdict, build_chain_merge_report
from maid_runner.core.snapshot import generate_snapshot, save_snapshot
from maid_runner.core.types import Manifest


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
) -> ChainMergeApplyResult:
    """Materialize the merged contract for ``file_path`` as a snapshot manifest.

    Refuses (writing nothing) on BLOCKED/LEAN verdicts, when superseding a
    manifest would drop artifacts it declares in other files, and when the
    current snapshot drops any artifact the chain declared for this file.
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

    # A single-file snapshot cannot preserve artifacts a superseded manifest
    # declares in OTHER files; superseding it would drop those and violate the
    # artifact-preservation audit. Refuse rather than orphan them.
    multi_file = sorted(
        m.slug for m in to_supersede if _declares_other_files(m, file_path)
    )
    if multi_file:
        return _refused(
            f"Refusing to merge {file_path}: it would supersede multi-file "
            f"manifest(s) {', '.join(multi_file)}, dropping their other-file "
            f"artifacts. Split or reconcile those manifests first."
        )

    snapshot = generate_snapshot(
        Path(project_root) / file_path, project_root=project_root
    )
    snapshot_keys = {
        artifact.contract_key()
        for file_spec in snapshot.files_snapshot
        for artifact in file_spec.artifacts
    }
    declared_keys = {
        artifact.contract_key() for artifact in chain.merged_artifacts_for(file_path)
    }
    missing = tuple(sorted(declared_keys - snapshot_keys))
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

    superseded_slugs = tuple(sorted(m.slug for m in to_supersede))
    snapshot = dataclasses.replace(snapshot, supersedes=superseded_slugs)
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


def _declares_other_files(manifest: Manifest, file_path: str) -> bool:
    return any(fs.path != file_path and fs.artifacts for fs in manifest.all_file_specs)


def _refused(reason: str) -> ChainMergeApplyResult:
    return ChainMergeApplyResult(
        applied=False,
        snapshot_path=None,
        superseded_slugs=(),
        refused_reason=reason,
        missing_artifacts=(),
    )
