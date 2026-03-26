"""Base validator ABC and data types for MAID Runner v2."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional, Union

from maid_runner.core.types import ArtifactKind, ArgSpec


@dataclass(frozen=True)
class FoundArtifact:
    """An artifact found by a language validator in source code."""

    kind: ArtifactKind
    name: str
    of: Optional[str] = None
    args: tuple[ArgSpec, ...] = ()
    returns: Optional[str] = None
    is_async: bool = False
    bases: tuple[str, ...] = ()
    type_annotation: Optional[str] = None
    line: Optional[int] = None
    column: Optional[int] = None

    @property
    def is_private(self) -> bool:
        return self.name.startswith("_") or self.name.startswith("#")

    @property
    def qualified_name(self) -> str:
        if self.of:
            return f"{self.of}.{self.name}"
        return self.name

    def merge_key(self) -> str:
        if self.kind in (ArtifactKind.METHOD, ArtifactKind.ATTRIBUTE) and self.of:
            return f"{self.of}.{self.name}"
        return self.name


@dataclass
class CollectionResult:
    """Result of collecting artifacts from a source file."""

    artifacts: list[FoundArtifact]
    language: str
    file_path: str
    errors: list[str] = field(default_factory=list)


class BaseValidator(ABC):
    """Abstract base for language-specific code validators."""

    @classmethod
    @abstractmethod
    def supported_extensions(cls) -> tuple[str, ...]:
        """File extensions this validator handles (e.g. ('.py',))."""

    def can_validate(self, file_path: Union[str, Path]) -> bool:
        return Path(file_path).suffix in self.supported_extensions()

    @abstractmethod
    def collect_implementation_artifacts(
        self,
        source: str,
        file_path: Union[str, Path],
    ) -> CollectionResult:
        """Collect artifact DEFINITIONS from source code."""

    @abstractmethod
    def collect_behavioral_artifacts(
        self,
        source: str,
        file_path: Union[str, Path],
    ) -> CollectionResult:
        """Collect artifact REFERENCES from source code (test files)."""

    def generate_test_stub(
        self,
        artifacts: list[FoundArtifact],
        file_path: Union[str, Path],
    ) -> str:
        """Generate test stub code for the given artifacts.

        Default implementation returns empty string.
        Override to generate language-specific test templates.
        """
        return ""

    def generate_snapshot(
        self,
        source: str,
        file_path: Union[str, Path],
    ) -> list[dict]:
        result = self.collect_implementation_artifacts(source, file_path)
        return [self._artifact_to_dict(a) for a in result.artifacts if not a.is_private]

    @staticmethod
    def _artifact_to_dict(artifact: FoundArtifact) -> dict:
        d: dict = {"kind": artifact.kind.value, "name": artifact.name}
        if artifact.of:
            d["of"] = artifact.of
        if artifact.args:
            d["args"] = [
                {
                    k: v
                    for k, v in {
                        "name": a.name,
                        "type": a.type,
                        "default": a.default,
                    }.items()
                    if v is not None
                }
                for a in artifact.args
            ]
        if artifact.returns:
            d["returns"] = artifact.returns
        if artifact.is_async:
            d["async"] = True
        if artifact.bases:
            d["bases"] = list(artifact.bases)
        if artifact.type_annotation:
            d["type"] = artifact.type_annotation
        return d
