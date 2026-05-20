"""Reference recording helpers for Python behavioral artifact collection."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from maid_runner.core.types import ArtifactKind
from maid_runner.validators.base import FoundArtifact


_ReferenceKey = tuple[
    str,
    Optional[str],
    Optional[str],
    Optional[str],
    Optional[str],
]


@dataclass
class _BehavioralReferenceRecorder:
    artifacts: list[FoundArtifact]
    seen: set[_ReferenceKey]
    seen_test_funcs: set[str]

    def add_test_function(self, name: str, line: int) -> None:
        if name in self.seen_test_funcs:
            return
        self.seen_test_funcs.add(name)
        self.artifacts.append(
            FoundArtifact(
                kind=ArtifactKind.TEST_FUNCTION,
                name=name,
                line=line,
            )
        )

    def add_reference(
        self,
        name: str,
        *,
        of: Optional[str] = None,
        import_source: Optional[str] = None,
        alias_of: Optional[str] = None,
        reference_context: Optional[str] = None,
    ) -> None:
        key = (name, of, import_source, alias_of, reference_context)
        if key in self.seen:
            return
        self.seen.add(key)
        self.artifacts.append(
            FoundArtifact(
                kind=ArtifactKind.FUNCTION,
                name=name,
                of=of,
                import_source=import_source,
                alias_of=alias_of,
                reference_context=reference_context,
            )
        )
