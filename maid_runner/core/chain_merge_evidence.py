"""Recorded detection evidence source for chain-merge (child 2).

A concrete ``DetectionEvidenceSource`` (the child 1 protocol) backed by the
persisted 121-22 knockout evidence cache. It reads already-recorded
detecting-nodeids per artifact and returns ``None`` (UNKNOWN) for anything
unrecorded. It never runs knockout.
"""

from __future__ import annotations

from pathlib import Path
from typing import Sequence

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
