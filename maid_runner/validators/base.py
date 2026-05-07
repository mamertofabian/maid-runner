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
    type_parameters: tuple[str, ...] = ()
    type_annotation: Optional[str] = None
    is_stub: bool = False
    line: Optional[int] = None
    column: Optional[int] = None
    module_path: Optional[str] = None
    import_source: Optional[str] = None
    alias_of: Optional[str] = None

    @property
    def is_private(self) -> bool:
        if self.name.startswith("_") or self.name.startswith("#"):
            return True
        if self.of and (self.of.startswith("_") or self.of.startswith("#")):
            return True
        return False

    @property
    def qualified_name(self) -> str:
        if self.of:
            return f"{self.of}.{self.name}"
        return self.name

    def merge_key(self) -> str:
        if self.kind in (ArtifactKind.METHOD, ArtifactKind.ATTRIBUTE) and self.of:
            return f"{self.kind.value}:{self.of}.{self.name}"
        return f"{self.kind.value}:{self.name}"


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

    def module_path(
        self,
        file_path: Union[str, Path],
        project_root: Path,
    ) -> Optional[str]:
        """Return the language-specific module identity for a source file.

        Default returns None; languages that have a stable file→module
        identity (Python dotted, TS path-based) override.
        """
        return None

    def resolve_reexport(
        self,
        module: str,
        name: str,
        project_root: Path,
    ) -> Optional[tuple[str, str]]:
        """Resolve a one-level barrel re-export of ``name`` from ``module``.

        Default returns None; PythonValidator delegates to
        ``__init__.py``-aware resolution and TypeScriptValidator to
        ``index.ts(x)``-aware resolution. The tuple is
        ``(resolved_module, original_source_name)``: for plain
        re-exports the second element equals ``name``; for aliased
        re-exports it is the pre-alias identifier so the matcher can
        bridge a test that imports the alias back to the artifact's
        true name.
        """
        return None

    def get_test_function_bodies(
        self,
        source: str,
        file_path: Union[str, Path],
    ) -> dict[str, str]:
        """Return a mapping of test_function name -> body source text.

        The body is the text of the test's implementation scope, used to
        check behavioral metadata (imports, endpoints, exports) against the
        specific test rather than the whole file. Languages that can parse
        test functions must override this; the default returns an empty
        mapping so callers fall back gracefully.
        """
        return {}

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
        if artifact.type_parameters:
            d["type_parameters"] = list(artifact.type_parameters)
        if artifact.type_annotation:
            d["type"] = artifact.type_annotation
        return d
