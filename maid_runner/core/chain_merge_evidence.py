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
from maid_runner.core.knockout import cached_detecting_nodeids
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


def detection_source_for_file(
    chain: ManifestChain,
    file_path: str,
    project_root: str = ".",
) -> RecordedDetectionEvidenceSource:
    """Build a detection source scoped to a single file's manifests.

    Scoping to ``chain.manifests_for_file(file_path)`` keeps
    ``cached_detecting_nodeids`` limited to that file's artifacts, so a merge_key
    shared with another file cannot leak that other file's detecting-nodeids into
    this file's acceptance bar.

    Detection is advisory: if knockout specs cannot be built (e.g. a declared
    source file is missing on disk), this degrades to an empty (UNKNOWN) source
    rather than failing the read-only report.
    """
    try:
        return RecordedDetectionEvidenceSource.from_cache(
            chain.manifests_for_file(file_path), project_root
        )
    except ValueError:
        return RecordedDetectionEvidenceSource({})


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
