"""Svelte validator for MAID Runner v2.

Extracts script blocks from .svelte files and delegates to TypeScriptValidator.
Requires tree-sitter-svelte.
"""

from __future__ import annotations

from pathlib import Path
from typing import Optional, Union

from maid_runner.core.ts_module_paths import (
    resolve_ts_reexport,
    ts_file_to_module_path,
)
from maid_runner.core.types import ArtifactKind
from maid_runner.validators.base import BaseValidator, CollectionResult, FoundArtifact

try:
    from maid_runner.validators.typescript import TypeScriptValidator

    _HAS_TS = True
except ImportError:
    _HAS_TS = False

try:
    from tree_sitter import Language, Parser
    import tree_sitter_svelte

    _HAS_SVELTE = True
except ImportError:
    _HAS_SVELTE = False


class SvelteValidator(BaseValidator):
    def __init__(self) -> None:
        if not _HAS_TS:
            raise ImportError(
                "TypeScriptValidator is required for Svelte validation. "
                "Install tree-sitter-typescript."
            )
        if not _HAS_SVELTE:
            raise ImportError(
                "tree-sitter-svelte is required for Svelte validation. "
                "Install tree-sitter-svelte."
            )
        self._ts_validator = TypeScriptValidator()
        self._svelte_lang = Language(tree_sitter_svelte.language())
        self._svelte_parser = Parser(self._svelte_lang)

    @classmethod
    def supported_extensions(cls) -> tuple[str, ...]:
        return (".svelte",)

    def collect_implementation_artifacts(
        self,
        source: str,
        file_path: Union[str, Path],
    ) -> CollectionResult:
        script_content = _extract_script(source, self._svelte_parser)
        component_artifact = _component_artifact(file_path, bool(script_content))
        if not script_content:
            return CollectionResult(
                artifacts=(
                    [component_artifact] if component_artifact is not None else []
                ),
                language="svelte",
                file_path=str(file_path),
            )
        # Delegate to TypeScript validator with .ts extension
        result = self._ts_validator.collect_implementation_artifacts(
            script_content, str(file_path).replace(".svelte", ".ts")
        )
        artifacts = list(result.artifacts)
        if component_artifact is not None:
            artifacts = [
                artifact
                for artifact in artifacts
                if not (
                    artifact.kind == ArtifactKind.FUNCTION
                    and artifact.of is None
                    and artifact.name == component_artifact.name
                )
            ]
            artifacts.append(component_artifact)
        return CollectionResult(
            artifacts=artifacts,
            language="svelte",
            file_path=str(file_path),
            errors=result.errors,
        )

    def collect_behavioral_artifacts(
        self,
        source: str,
        file_path: Union[str, Path],
    ) -> CollectionResult:
        script_content = _extract_script(source, self._svelte_parser)
        if not script_content:
            return CollectionResult(
                artifacts=[], language="svelte", file_path=str(file_path)
            )
        result = self._ts_validator.collect_behavioral_artifacts(
            script_content, str(file_path).replace(".svelte", ".ts")
        )
        return CollectionResult(
            artifacts=result.artifacts,
            language="svelte",
            file_path=str(file_path),
            errors=result.errors,
        )

    def get_test_function_bodies(
        self,
        source: str,
        file_path: Union[str, Path],
    ) -> dict[str, str]:
        script_content = _extract_script(source, self._svelte_parser)
        if not script_content:
            return {}
        return self._ts_validator.get_test_function_bodies(
            script_content, str(file_path).replace(".svelte", ".ts")
        )

    def module_path(
        self, file_path: Union[str, Path], project_root: Path
    ) -> Optional[str]:
        return ts_file_to_module_path(file_path, project_root) or None

    def resolve_reexport(
        self, module: str, name: str, project_root: Path
    ) -> Optional[tuple[str, str]]:
        return resolve_ts_reexport(module, name, project_root)


def _extract_script(source: str, parser: Parser) -> str:
    """Extract real Svelte script block contents in document order."""
    source_bytes = source.encode("utf-8")
    tree = parser.parse(source_bytes)
    scripts: list[str] = []
    stack = [tree.root_node]

    while stack:
        node = stack.pop()
        if node.type == "script_element":
            for child in node.children:
                if child.type == "raw_text":
                    scripts.append(
                        source_bytes[child.start_byte : child.end_byte].decode("utf-8")
                    )
                    break
            continue
        stack.extend(reversed(node.children))

    return "\n".join(scripts)


def _component_artifact(
    file_path: Union[str, Path], has_script_content: bool
) -> Optional[FoundArtifact]:
    if not has_script_content:
        return None

    component_name = Path(file_path).stem
    if not component_name.isidentifier():
        return None

    module_path = ts_file_to_module_path(file_path, Path(".")) or None
    return FoundArtifact(
        kind=ArtifactKind.FUNCTION,
        name=component_name,
        returns="Svelte component instance",
        line=1,
        module_path=module_path,
    )
