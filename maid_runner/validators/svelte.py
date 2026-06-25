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
from maid_runner.validators._typescript_parse import parse_typescript_source

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
        script_blocks = _extract_script_blocks(source, self._svelte_parser)
        script_content = _script_content(script_blocks)
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
            artifacts.extend(
                _svelte5_props_artifacts(
                    _script_content(
                        [
                            content
                            for content, is_module in script_blocks
                            if not is_module
                        ]
                    ),
                    file_path,
                    component_artifact,
                    self._ts_validator,
                    artifacts,
                )
            )
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
    return _script_content(
        [content for content, _is_module in _extract_script_blocks(source, parser)]
    )


def _extract_script_blocks(source: str, parser: Parser) -> list[tuple[str, bool]]:
    """Extract real Svelte script block contents with module-script flags."""
    source_bytes = source.encode("utf-8")
    tree = parser.parse(source_bytes)
    scripts: list[tuple[str, bool]] = []
    stack = [tree.root_node]

    while stack:
        node = stack.pop()
        if node.type == "script_element":
            raw_text = None
            for child in node.children:
                if child.type == "raw_text":
                    raw_text = source_bytes[child.start_byte : child.end_byte].decode(
                        "utf-8"
                    )
                    break
            if raw_text is not None:
                scripts.append((raw_text, _is_module_script(node, source_bytes)))
            continue
        stack.extend(reversed(node.children))

    return scripts


def _script_content(script_blocks: list[str] | list[tuple[str, bool]]) -> str:
    if not script_blocks:
        return ""
    first = script_blocks[0]
    if isinstance(first, tuple):
        return "\n".join(content for content, _is_module in script_blocks)
    return "\n".join(script_blocks)


def _is_module_script(script_node, source: bytes) -> bool:
    start_tag = _child_by_type(script_node, "start_tag")
    if start_tag is None:
        return False

    for child in start_tag.children:
        if child.type != "attribute":
            continue
        name_node = _child_by_type(child, "attribute_name")
        if name_node is None:
            continue
        name = _text(name_node, source)
        if name == "module":
            return True
        if name != "context":
            continue
        value_node = _child_by_type(child, "quoted_attribute_value")
        if value_node is not None and "module" in _text(value_node, source).strip(
            "\"'"
        ):
            return True
    return False


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


def _svelte5_props_artifacts(
    script_content: str,
    file_path: Union[str, Path],
    component_artifact: FoundArtifact,
    ts_validator: TypeScriptValidator,
    existing_artifacts: list[FoundArtifact],
) -> list[FoundArtifact]:
    session = parse_typescript_source(
        script_content,
        str(file_path).replace(".svelte", ".ts"),
        ts_validator._ts_parser,
        ts_validator._tsx_parser,
    )
    if session.parse_errors:
        return []

    source = session.source_bytes
    type_by_prop: dict[str, str] = {}
    found: list[FoundArtifact] = []
    stack = [session.tree.root_node]
    while stack:
        node = stack.pop()
        if node.type == "variable_declarator" and _is_top_level_declarator(node):
            found.extend(
                _props_artifacts_from_declarator(
                    node,
                    source,
                    component_artifact,
                    existing_artifacts + found,
                    type_by_prop,
                )
            )
            continue
        stack.extend(reversed(node.children))
    return found


def _props_artifacts_from_declarator(
    node,
    source: bytes,
    component_artifact: FoundArtifact,
    existing_artifacts: list[FoundArtifact],
    type_by_prop: dict[str, str],
) -> list[FoundArtifact]:
    object_pattern = _child_by_type(node, "object_pattern")
    type_annotation = _child_by_type(node, "type_annotation")
    call_expression = _child_by_type(node, "call_expression")
    if (
        object_pattern is None
        or type_annotation is None
        or call_expression is None
        or not _is_props_call(call_expression, source)
    ):
        return []

    type_by_prop.clear()
    type_by_prop.update(_object_type_properties(type_annotation, source))
    if not type_by_prop:
        return []

    artifacts: list[FoundArtifact] = []
    for prop_name, line in _object_pattern_props(object_pattern, source):
        type_annotation_text = type_by_prop.get(prop_name)
        if type_annotation_text is None:
            continue
        artifact = FoundArtifact(
            kind=ArtifactKind.ATTRIBUTE,
            name=prop_name,
            of=component_artifact.name,
            type_annotation=type_annotation_text,
            line=line,
            module_path=component_artifact.module_path,
        )
        if not _has_same_artifact(existing_artifacts + artifacts, artifact):
            artifacts.append(artifact)
    return artifacts


def _object_pattern_props(node, source: bytes) -> list[tuple[str, int]]:
    props: list[tuple[str, int]] = []
    for child in node.children:
        name_node = None
        if child.type == "shorthand_property_identifier_pattern":
            name_node = child
        elif child.type == "object_assignment_pattern":
            name_node = _child_by_type(child, "shorthand_property_identifier_pattern")
        elif child.type == "pair_pattern":
            name_node = _child_by_type(child, "property_identifier")
        if name_node is not None:
            props.append((_text(name_node, source), child.start_point[0] + 1))
    return props


def _object_type_properties(node, source: bytes) -> dict[str, str]:
    object_type = _child_by_type(node, "object_type")
    if object_type is None:
        return {}

    props: dict[str, str] = {}
    for child in object_type.children:
        if child.type != "property_signature":
            continue
        name_node = _child_by_type(child, "property_identifier")
        type_node = _child_by_type(child, "type_annotation")
        if name_node is None or type_node is None:
            continue
        type_text = _text(type_node, source).removeprefix(":").strip()
        if type_text:
            props[_text(name_node, source)] = type_text
    return props


def _is_top_level_declarator(node) -> bool:
    parent = node.parent
    if parent is None or parent.type not in (
        "lexical_declaration",
        "variable_declaration",
    ):
        return False
    return parent.parent is not None and parent.parent.type == "program"


def _is_props_call(node, source: bytes) -> bool:
    callee = _child_by_type(node, "identifier")
    arguments = _child_by_type(node, "arguments")
    return (
        callee is not None
        and _text(callee, source) == "$props"
        and arguments is not None
    )


def _has_same_artifact(
    artifacts: list[FoundArtifact], candidate: FoundArtifact
) -> bool:
    return any(
        artifact.kind == candidate.kind
        and artifact.name == candidate.name
        and artifact.of == candidate.of
        for artifact in artifacts
    )


def _child_by_type(node, type_name: str):
    for child in node.children:
        if child.type == type_name:
            return child
    return None


def _text(node, source: bytes) -> str:
    return source[node.start_byte : node.end_byte].decode("utf-8")
