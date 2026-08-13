"""Materialize a merged manifest chain (chain-merge child 4).

`maid chain merge <file> --apply` reuses the snapshot primitive to write a
current-state snapshot manifest that supersedes the file's active chain. It
refuses (writing nothing) when the fresh snapshot would drop a declared
artifact — so the anti-gaming artifact-preservation audit is never violated —
and on BLOCKED/LEAN verdicts. Tests are never touched; only a manifest is
written.
"""

from __future__ import annotations

import dataclasses
from dataclasses import dataclass
from pathlib import Path

from maid_runner.core.chain import ManifestChain
from maid_runner.core.chain_merge import ChainMergeVerdict, build_chain_merge_report
from maid_runner.core.snapshot import generate_snapshot, save_snapshot


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

    Refuses (writing nothing) on BLOCKED/LEAN verdicts, and when the current
    snapshot drops any artifact the active chain declared.
    """
    report = build_chain_merge_report(file_path, chain, None)

    if report.verdict is ChainMergeVerdict.BLOCKED:
        return _refused(f"{file_path} is BLOCKED: {'; '.join(report.blocking_reasons)}")
    if report.verdict is ChainMergeVerdict.LEAN:
        return _refused(f"{file_path} is already LEAN; nothing to merge.")

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

    superseded_slugs = tuple(
        sorted(m.slug for m in chain.manifests_for_file(file_path))
    )
    snapshot = dataclasses.replace(snapshot, supersedes=superseded_slugs)
    out_path = save_snapshot(snapshot, output_dir=output_dir)

    return ChainMergeApplyResult(
        applied=True,
        snapshot_path=str(out_path),
        superseded_slugs=superseded_slugs,
        refused_reason=None,
        missing_artifacts=(),
    )


def _refused(reason: str) -> ChainMergeApplyResult:
    return ChainMergeApplyResult(
        applied=False,
        snapshot_path=None,
        superseded_slugs=(),
        refused_reason=reason,
        missing_artifacts=(),
    )
