"""Recorded detection evidence source for chain-merge (child 2).

A concrete ``DetectionEvidenceSource`` (the child 1 protocol) backed by the
persisted 121-22 knockout evidence cache. It reads already-recorded
detecting-nodeids per artifact and returns ``None`` (UNKNOWN) for anything
unrecorded. It never runs knockout.
"""

from __future__ import annotations

from pathlib import Path
from typing import Sequence

from maid_runner.core.chain import ManifestChain
from maid_runner.core.knockout import (
    cached_detecting_nodeids,
    cached_detecting_nodeids_for_file,
)
from maid_runner.core.types import Manifest


class RecordedDetectionEvidenceSource:
    """DetectionEvidenceSource over a merge_key -> detecting-nodeids map."""

    def __init__(self, detection_by_merge_key: dict[str, tuple[str, ...]]) -> None:
        self._by_merge_key = dict(detection_by_merge_key)

    @classmethod
    def from_cache(
        cls,
        manifests: Sequence[Manifest],
        project_root: str,
    ) -> "RecordedDetectionEvidenceSource":
        """Build a source from the persisted knockout evidence cache."""
        return cls(cached_detecting_nodeids(manifests, Path(project_root)))

    def detecting_nodeids_for(self, artifact_key: str) -> tuple[str, ...] | None:
        return self._by_merge_key.get(_merge_key_from_contract_key(artifact_key))


class RecordedCoverageEvidenceSource:
    """File-qualified coverage evidence read from the persisted deep cache."""

    def __init__(
        self,
        coverage_by_artifact: dict[tuple[str, str], bool],
    ) -> None:
        self._by_artifact = dict(coverage_by_artifact)

    @classmethod
    def from_cache(
        cls,
        manifests: Sequence[Manifest],
        project_root: str,
        manifest_dir: str,
    ) -> "RecordedCoverageEvidenceSource":
        """Read current full-repository/default-worker coverage evidence."""
        from maid_runner.core._artifact_coverage_cache import (
            _load_artifact_coverage_cache,
        )

        report = _load_artifact_coverage_cache(
            Path(project_root),
            manifest_dir=manifest_dir,
            pytest_workers=None,
            manifest_paths=None,
        )
        if report is None:
            return cls({})

        paths = {
            file_spec.path
            for manifest in manifests
            for file_spec in manifest.all_file_specs
            if file_spec.artifacts
        }
        indexed: dict[tuple[str, str], bool] = {}
        for finding in report.findings:
            if finding.file_path not in paths:
                continue
            key = (
                finding.file_path,
                _coverage_finding_merge_key(
                    finding.artifact_kind,
                    finding.artifact_name,
                    finding.parent_class,
                ),
            )
            # A fragmented chain may produce duplicate findings. Any E710 must
            # dominate covered evidence so iteration order cannot hide debt.
            indexed[key] = indexed.get(key, True) and finding.executed
        return cls(indexed)

    def coverage_for(self, file_path: str, artifact_key: str) -> bool | None:
        return self._by_artifact.get(
            (file_path, _merge_key_from_contract_key(artifact_key))
        )


def detection_source_for_file(
    chain: ManifestChain,
    file_path: str,
    project_root: str = ".",
) -> RecordedDetectionEvidenceSource:
    """Build a detection source scoped to one file from the full active plan.

    The cache key is reconstructed from every active manifest before the
    requested file is selected. This preserves repository-wide declaration
    indices while preventing a merge_key shared by another file from leaking
    into this file's acceptance bar.

    Detection is advisory: if knockout specs cannot be built (e.g. a declared
    source file is missing on disk), this degrades to an empty (UNKNOWN) source
    rather than failing the read-only report.
    """
    try:
        return RecordedDetectionEvidenceSource(
            cached_detecting_nodeids_for_file(
                chain.active_manifests(),
                Path(project_root),
                file_path,
            )
        )
    except ValueError:
        return RecordedDetectionEvidenceSource({})


def coverage_source_for_file(
    chain: ManifestChain,
    file_path: str,
    project_root: str = ".",
    manifest_dir: str = "manifests",
) -> RecordedCoverageEvidenceSource:
    """Build a recorded coverage source scoped to one file's manifests."""
    return RecordedCoverageEvidenceSource.from_cache(
        chain.manifests_for_file(file_path),
        project_root,
        manifest_dir,
    )


def _merge_key_from_contract_key(contract_key: str) -> str:
    """Recover the merge_key embedded in a contract_key.

    ``_artifact_contract_key`` returns the merge_key verbatim when there is no
    signature, else ``exact:{len(merge_key)}:{merge_key}{len(sig)}:{sig}``.
    """
    if not contract_key.startswith("exact:"):
        return contract_key
    body = contract_key[len("exact:") :]
    length_str, sep, remainder = body.partition(":")
    if not sep or not length_str.isdigit():
        return contract_key
    return remainder[: int(length_str)]


def _coverage_finding_merge_key(
    artifact_kind: str,
    artifact_name: str,
    parent_class: str | None,
) -> str:
    if parent_class:
        return f"{artifact_kind}:{parent_class}.{artifact_name}"
    return f"{artifact_kind}:{artifact_name}"
