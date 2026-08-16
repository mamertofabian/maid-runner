"""Deterministic manifest-chain merge report (chain-merge child 1).

Read-only decision layer for `maid chain merge <file> --dry-run`. Builds a
:class:`ChainMergeReport` purely by aggregating :class:`ManifestChain`
primitives — it never runs knockout or coverage. Detecting-nodeids are read only
through an injected :class:`DetectionEvidenceSource`; when none is supplied the
report marks detection UNKNOWN and never fabricates evidence.
"""

from __future__ import annotations

from abc import abstractmethod
from dataclasses import dataclass
from enum import Enum
from typing import Protocol, runtime_checkable

from maid_runner.core.chain import ManifestChain


class ChainMergeVerdict(Enum):
    """Structural verdict for a file's manifest chain."""

    DEFRAG = "defrag"
    LEAN = "lean"
    BLOCKED = "blocked"


@runtime_checkable
class DetectionEvidenceSource(Protocol):
    """Reads recorded knockout detecting-nodeids for one artifact.

    Returns ``None`` when no evidence is recorded for the artifact — that is
    UNKNOWN, never an empty success.
    """

    @abstractmethod
    def detecting_nodeids_for(self, artifact_key: str) -> tuple[str, ...] | None:
        raise NotImplementedError


@runtime_checkable
class CoverageEvidenceSource(Protocol):
    """Reads recorded execution coverage for one file-qualified artifact."""

    @abstractmethod
    def coverage_for(self, file_path: str, artifact_key: str) -> bool | None:
        raise NotImplementedError


@dataclass(frozen=True)
class ChainMergeAcceptanceSpec:
    """The deterministic bar a future collapse must clear."""

    required_artifacts: tuple[str, ...]
    detection_available: bool
    required_detecting_nodeids: dict[str, tuple[str, ...]]
    unknown_detection_artifacts: tuple[str, ...]
    coverage_available: bool = False
    required_covered_artifacts: tuple[str, ...] = ()
    uncovered_coverage_artifacts: tuple[str, ...] = ()
    unknown_coverage_artifacts: tuple[str, ...] = ()


@dataclass(frozen=True)
class ChainMergeReport:
    """The full read-only report for one production file."""

    file_path: str
    verdict: ChainMergeVerdict
    active_manifest_count: int
    superseded_manifest_count: int
    distinct_artifact_count: int
    total_declaration_count: int
    redundant_declaration_count: int
    blocking_reasons: tuple[str, ...]
    acceptance: ChainMergeAcceptanceSpec


def build_chain_merge_report(
    file_path: str,
    chain: ManifestChain,
    detection_source: DetectionEvidenceSource | None,
    coverage_source: CoverageEvidenceSource | None = None,
) -> ChainMergeReport:
    """Build the merge report for ``file_path`` from ``chain``.

    Pure aggregation over ManifestChain: no I/O of its own, no knockout or
    coverage execution.
    """
    # Only manifests that actually declare artifacts in this file count — a
    # scope-only reference is not a contract declaration and must not inflate the
    # fragmentation verdict.
    active = [
        manifest
        for manifest in chain.manifests_for_file(file_path)
        if any(fs.path == file_path and fs.artifacts for fs in manifest.all_file_specs)
    ]
    merged = chain.merged_artifacts_for(file_path)

    active_manifest_count = len(active)
    distinct_artifact_count = len(merged)

    total_declaration_count = 0
    for manifest in active:
        for file_spec in manifest.all_file_specs:
            if file_spec.path == file_path:
                total_declaration_count += len(file_spec.artifacts)
    redundant_declaration_count = total_declaration_count - distinct_artifact_count

    superseded_manifest_count = sum(
        1
        for manifest in chain.superseded_manifests()
        if file_path in manifest.all_writable_paths
    )

    required_artifacts = tuple(sorted(a.contract_key() for a in merged))

    blocking_reasons: list[str] = []
    if active_manifest_count == 0 and distinct_artifact_count == 0:
        verdict = ChainMergeVerdict.BLOCKED
        blocking_reasons.append(
            f"No active writable manifest declares {file_path}; nothing to merge."
        )
    elif active_manifest_count <= 1 and redundant_declaration_count == 0:
        verdict = ChainMergeVerdict.LEAN
    else:
        verdict = ChainMergeVerdict.DEFRAG

    acceptance = _build_acceptance(
        file_path,
        required_artifacts,
        detection_source,
        coverage_source,
    )
    if acceptance.uncovered_coverage_artifacts:
        verdict = ChainMergeVerdict.BLOCKED
        blocking_reasons.append(
            "Recorded artifact coverage has E710 gaps: "
            + ", ".join(acceptance.uncovered_coverage_artifacts)
        )

    return ChainMergeReport(
        file_path=file_path,
        verdict=verdict,
        active_manifest_count=active_manifest_count,
        superseded_manifest_count=superseded_manifest_count,
        distinct_artifact_count=distinct_artifact_count,
        total_declaration_count=total_declaration_count,
        redundant_declaration_count=redundant_declaration_count,
        blocking_reasons=tuple(blocking_reasons),
        acceptance=acceptance,
    )


def _build_acceptance(
    file_path: str,
    required_artifacts: tuple[str, ...],
    detection_source: DetectionEvidenceSource | None,
    coverage_source: CoverageEvidenceSource | None,
) -> ChainMergeAcceptanceSpec:
    if detection_source is None:
        detection_found: dict[str, tuple[str, ...]] = {}
        detection_unknown = required_artifacts
    else:
        detection_found = {}
        unknown: list[str] = []
        for key in required_artifacts:
            nodeids = detection_source.detecting_nodeids_for(key)
            if nodeids is None:
                unknown.append(key)
            else:
                detection_found[key] = tuple(nodeids)
        detection_unknown = tuple(unknown)

    covered: list[str] = []
    uncovered: list[str] = []
    coverage_unknown: list[str] = []
    if coverage_source is None:
        coverage_unknown.extend(required_artifacts)
    else:
        for key in required_artifacts:
            status = coverage_source.coverage_for(file_path, key)
            if status is True:
                covered.append(key)
            elif status is False:
                uncovered.append(key)
            else:
                coverage_unknown.append(key)

    return ChainMergeAcceptanceSpec(
        required_artifacts=required_artifacts,
        detection_available=detection_source is not None,
        required_detecting_nodeids=detection_found,
        unknown_detection_artifacts=detection_unknown,
        coverage_available=coverage_source is not None,
        required_covered_artifacts=tuple(covered),
        uncovered_coverage_artifacts=tuple(uncovered),
        unknown_coverage_artifacts=tuple(coverage_unknown),
    )
