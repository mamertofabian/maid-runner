"""Repo-wide chain-merge sweep (chain-merge child 6).

Read-only aggregate over :func:`build_chain_merge_report` for every tracked
writable production file — the finish-line view for a defrag program. No
knockout or coverage runs; detection stays UNKNOWN (no detection source).
"""

from __future__ import annotations

from dataclasses import dataclass

from maid_runner.core.chain import ManifestChain
from maid_runner.core.chain_merge import ChainMergeVerdict, build_chain_merge_report


@dataclass(frozen=True)
class ChainMergeSweepSummary:
    """Aggregate repo-wide summary of chain-merge verdicts."""

    defrag_count: int
    lean_count: int
    blocked_count: int
    swept_file_count: int
    worst_offenders: tuple[str, ...]


def build_repo_merge_summary(chain: ManifestChain) -> ChainMergeSweepSummary:
    """Sweep every writable production file and aggregate the verdicts.

    Deterministic: files are swept in sorted order and worst offenders are
    ranked by redundant declarations descending, ties broken by path.
    """
    writable = sorted(chain.all_tracked_paths() - chain.all_read_only_paths())
    reports = [build_chain_merge_report(path, chain, None) for path in writable]

    defrag_count = sum(1 for r in reports if r.verdict is ChainMergeVerdict.DEFRAG)
    lean_count = sum(1 for r in reports if r.verdict is ChainMergeVerdict.LEAN)
    blocked_count = sum(1 for r in reports if r.verdict is ChainMergeVerdict.BLOCKED)

    ranked = sorted(
        (r for r in reports if r.verdict is ChainMergeVerdict.DEFRAG),
        key=lambda r: (-r.redundant_declaration_count, r.file_path),
    )
    worst_offenders = tuple(r.file_path for r in ranked)

    return ChainMergeSweepSummary(
        defrag_count=defrag_count,
        lean_count=lean_count,
        blocked_count=blocked_count,
        swept_file_count=len(writable),
        worst_offenders=worst_offenders,
    )
