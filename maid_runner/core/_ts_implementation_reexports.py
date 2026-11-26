"""Resolve bounded TypeScript function re-exports for implementation checks."""

from __future__ import annotations

from dataclasses import dataclass, replace
import glob
from pathlib import Path
import re
from typing import Any

from maid_runner.core import _artifact_collection_cache as artifact_cache
from maid_runner.core._tsconfig_paths import load_tsconfig
from maid_runner.core.ts_compiler_resolver import _run_compiler_request
from maid_runner.core.types import ArtifactKind, ArtifactSpec
from maid_runner.validators._jsdoc import (
    _JSDOC_RETURN,
    extract_leading_jsdoc_return_type,
)
from maid_runner.validators._typescript_parse import parse_typescript_source
from maid_runner.validators.base import BaseValidator, FoundArtifact


@dataclass(frozen=True)
class _ResolvedFunction:
    public: FoundArtifact
    declaration: FoundArtifact
    file_path: str
    source: str


def _collect_reexported_functions(
    source: str,
    file_path: str,
    project_root: Path,
    expected: list[ArtifactSpec],
    validator: BaseValidator,
    *,
    include_unexpected: bool = False,
) -> tuple[set[str], list[_ResolvedFunction]]:
    """Collect named value imports re-exported from their declaring module.

    This deliberately handles one import hop, not arbitrary barrel chains.
    Unverified bindings remain missing so the ordinary E300 path is retained.
    """
    requested = {
        spec.name
        for spec in expected
        if spec.kind == ArtifactKind.FUNCTION and spec.of is None
    }
    if not requested and not include_unexpected:
        return set(), []

    root = _parse(source, Path(file_path))
    if root is None:
        return set(), []
    source_bytes = source.encode("utf-8")
    imports = _named_value_imports(root, source_bytes)
    exports = _named_value_exports(root, source_bytes)
    if include_unexpected:
        requested.update(exports)
    masked = _import_export_lookalikes(root, source, file_path, validator)
    resolved: list[_ResolvedFunction] = []
    origins: dict[str, Path | None] = {}
    for public_name in requested:
        local_names = exports.get(public_name, [])
        if any(local_name in imports for local_name in local_names):
            masked.add(public_name)
        if len(local_names) != 1:
            continue
        bindings = imports.get(local_names[0], [])
        if len(bindings) != 1:
            continue
        if _has_top_level_value_binding(root, source_bytes, local_names[0]):
            continue
        specifier, original_name = bindings[0]
        if specifier not in origins:
            origins[specifier] = _origin_path(specifier, file_path, project_root)
        origin = origins[specifier]
        if origin is None:
            continue
        try:
            origin_source = origin.read_text()
        except (OSError, UnicodeError):
            continue
        origin_root = _parse(origin_source, origin)
        if origin_root is None:
            continue
        if _has_unsupported_string_export(
            origin_root, origin_source.encode("utf-8"), original_name
        ):
            continue
        origin_bindings = _value_export_bindings(
            origin_root, origin_source.encode("utf-8")
        ).get(original_name, [])
        if len(origin_bindings) != 1:
            continue
        declaration_name = origin_bindings[0]
        relative_origin = origin.relative_to(Path(project_root).resolve()).as_posix()
        resolved.extend(
            _ResolvedFunction(
                public=replace(artifact, name=public_name, line=None, column=None),
                declaration=artifact,
                file_path=relative_origin,
                source=origin_source,
            )
            for artifact in _runtime_function_artifacts(
                origin_root, origin_source, relative_origin, declaration_name, validator
            )
        )
    return masked, resolved


def _import_export_lookalikes(
    root: Any, source: str, file_path: str, validator: BaseValidator
) -> set[str]:
    """Mask collector results for imported names even when syntax is unsupported."""
    source_bytes = source.encode("utf-8")
    imported = _imported_bindings(root, source_bytes)
    masked: set[str] = set()
    for statement in root.children:
        if (
            statement.type != "export_statement"
            or _child(statement, "string") is not None
        ):
            continue
        clause = _child(statement, "export_clause")
        if clause is None:
            if any(child.type in {"default", "="} for child in statement.children):
                for child in statement.children:
                    if child.type == "identifier":
                        local_name = _text(child, source_bytes)
                        if local_name in imported:
                            masked.add(local_name)
            continue
        for item in clause.children:
            if item.type != "export_specifier":
                continue
            local = item.child_by_field_name("name")
            if local is None or local.type != "identifier":
                continue
            local_name = _text(local, source_bytes)
            if local_name not in imported:
                continue
            alias = item.child_by_field_name("alias")
            public = local if alias is None else alias
            is_value_export = not _has_type_token(statement) and not _has_type_token(
                item
            )
            if (
                all(imported[local_name])
                and is_value_export
                and public.type == "identifier"
                and _runtime_function_artifacts(
                    root, source, file_path, local_name, validator
                )
            ):
                continue
            masked.add(local_name)
            if public.type == "identifier":
                masked.add(_text(public, source_bytes))
    return masked


def _imported_bindings(root: Any, source_bytes: bytes) -> dict[str, list[bool]]:
    imported: dict[str, list[bool]] = {}
    for statement in root.children:
        if statement.type != "import_statement":
            continue
        clause = _child(statement, "import_clause")
        if clause is None:
            continue
        statement_type_only = _has_type_token(statement)
        for child in clause.children:
            if child.type == "identifier":
                imported.setdefault(_text(child, source_bytes), []).append(
                    statement_type_only
                )
            elif child.type == "namespace_import":
                identifiers = _identifiers(child, source_bytes)
                if identifiers:
                    imported.setdefault(identifiers[-1], []).append(statement_type_only)
            elif child.type == "named_imports":
                for item in child.children:
                    if item.type != "import_specifier":
                        continue
                    local = item.child_by_field_name(
                        "alias"
                    ) or item.child_by_field_name("name")
                    if local is not None and local.type == "identifier":
                        imported.setdefault(_text(local, source_bytes), []).append(
                            statement_type_only or _has_type_token(item)
                        )
    return imported


def _has_top_level_value_binding(root: Any, source: bytes, name: str) -> bool:
    for statement in root.children:
        if statement.type == "export_statement":
            nodes = statement.children
        elif statement.type == "expression_statement":
            nodes = statement.named_children
        else:
            nodes = [statement]
        for node in nodes:
            if node.type in {
                "function_declaration",
                "generator_function_declaration",
                "function_signature",
                "class_declaration",
                "enum_declaration",
                "internal_module",
            }:
                binding = node.child_by_field_name("name")
                if binding is not None and _text(binding, source) == name:
                    return True
            elif node.type in {"lexical_declaration", "variable_declaration"}:
                for item in node.children:
                    if item.type != "variable_declarator":
                        continue
                    binding = item.child_by_field_name("name")
                    if binding is not None and _pattern_mentions_name(
                        binding, source, name
                    ):
                        return True
    return False


def _has_unsupported_string_export(root: Any, source: bytes, name: str) -> bool:
    for statement in root.children:
        if statement.type != "export_statement":
            continue
        clause = _child(statement, "export_clause")
        if clause is None:
            continue
        for item in clause.children:
            if item.type != "export_specifier":
                continue
            local = item.child_by_field_name("name")
            alias = item.child_by_field_name("alias")
            if local is None or (
                local.type != "string" and (alias is None or alias.type != "string")
            ):
                continue
            public = alias if alias is not None else local
            text = _text(public, source)
            if public.type == "identifier" and text == name:
                return True
            if public.type == "string" and ("\\" in text or text[1:-1] == name):
                return True
    return False


def _runtime_function_artifacts(
    root: Any,
    source: str,
    file_path: str,
    name: str,
    validator: BaseValidator,
) -> list[FoundArtifact]:
    """Collect only the named top-level declaration, excluding nested lookalikes."""
    source_bytes = source.encode("utf-8")
    imported = _imported_bindings(root, source_bytes).get(name, [])
    if imported and not all(imported):
        return []
    declarations: list[tuple[Any, str, Any, tuple[Any, ...]]] = []
    value_declarations = 0
    unsupported_contract = False
    for statement in root.children:
        nodes = (
            statement.children if statement.type == "export_statement" else [statement]
        )
        for node in nodes:
            if node.type == "function_signature":
                node_name = node.child_by_field_name("name")
                if node_name is not None and _text(node_name, source_bytes) == name:
                    unsupported_contract = True
            if node.type in {
                "class_declaration",
                "enum_declaration",
                "internal_module",
            }:
                node_name = node.child_by_field_name("name")
                if node_name is not None and _text(node_name, source_bytes) == name:
                    value_declarations += 1
            if node.type in {"function_declaration", "generator_function_declaration"}:
                node_name = node.child_by_field_name("name")
                if (
                    node_name is not None
                    and _text(node_name, source_bytes) == name
                    and node.child_by_field_name("body") is not None
                ):
                    value_declarations += 1
                    declarations.append(
                        (node, "export " + _text(node, source_bytes), node, ())
                    )
            elif node.type in {"lexical_declaration", "variable_declaration"}:
                first_declarator = next(
                    (
                        child
                        for child in node.children
                        if child.type == "variable_declarator"
                    ),
                    None,
                )
                for item in node.children:
                    if item.type != "variable_declarator":
                        continue
                    node_name = item.child_by_field_name("name")
                    value = item.child_by_field_name("value")
                    if node_name is None:
                        continue
                    if node_name.type != "identifier":
                        if _pattern_mentions_name(node_name, source_bytes, name):
                            unsupported_contract = True
                        continue
                    if _text(node_name, source_bytes) != name:
                        continue
                    value_declarations += 1
                    if _child(item, "type_annotation") is not None:
                        unsupported_contract = True
                    inline_nodes: list[Any] = []
                    while (
                        value is not None and value.type == "parenthesized_expression"
                    ):
                        inline_nodes.append(value)
                        children = [
                            child
                            for child in value.named_children
                            if child.type != "comment"
                        ]
                        value = children[0] if len(children) == 1 else None
                    if value is not None:
                        inline_nodes.append(value)
                    if value is not None and value.type in {
                        "arrow_function",
                        "function_expression",
                        "generator_function",
                    }:
                        snippet = f"export const {name} = {_text(value, source_bytes)}"
                        declarations.append(
                            (
                                item,
                                snippet,
                                node if item == first_declarator else None,
                                tuple(inline_nodes),
                            )
                        )
    if (
        unsupported_contract
        or value_declarations != 1
        or _has_additional_module_var(root, source_bytes, name)
    ):
        return []
    if Path(file_path).suffix.lower() in {".js", ".jsx", ".mjs"}:
        for _node, _snippet, jsdoc_node, inline_nodes in declarations:
            if jsdoc_node is not None and _jsdoc_has_callable_type(
                jsdoc_node, source_bytes
            ):
                return []
            if any(
                _jsdoc_has_callable_type(node, source_bytes, inline=True)
                for node in inline_nodes
            ):
                return []
    artifacts: list[FoundArtifact] = []
    for node, snippet, jsdoc_node, inline_nodes in declarations:
        collection = artifact_cache.collect_cached_implementation_artifacts(
            validator, snippet, file_path
        )
        if collection.errors:
            continue
        jsdoc_return = None
        if Path(file_path).suffix.lower() in {".js", ".jsx", ".mjs"}:
            for inline_node in reversed(inline_nodes):
                jsdoc_return = _inline_jsdoc_return(inline_node, source_bytes)
                if jsdoc_return is not None:
                    break
            if jsdoc_return is None and jsdoc_node is not None:
                jsdoc_return = extract_leading_jsdoc_return_type(
                    jsdoc_node, source_bytes
                )
        artifacts.extend(
            replace(
                artifact,
                line=node.start_point[0] + 1,
                returns=(
                    artifact.returns if artifact.returns is not None else jsdoc_return
                ),
            )
            for artifact in collection.artifacts
            if artifact.kind == ArtifactKind.FUNCTION
            and artifact.name == name
            and artifact.of is None
        )
    return artifacts


def _has_additional_module_var(root: Any, source: bytes, name: str) -> bool:
    """Find extra module-scoped var bindings in non-declaration statements."""
    declaration_types = {
        "export_statement",
        "lexical_declaration",
        "variable_declaration",
        "function_declaration",
        "generator_function_declaration",
        "class_declaration",
    }
    function_scopes = {
        "function_declaration",
        "function_expression",
        "generator_function_declaration",
        "generator_function",
        "arrow_function",
        "method_definition",
        "class_declaration",
        "class",
        "internal_module",
        "ambient_declaration",
    }
    pending = [child for child in root.children if child.type not in declaration_types]
    while pending:
        current = pending.pop()
        if current.type in function_scopes:
            continue
        if current.type == "variable_declaration":
            for child in current.children:
                if child.type != "variable_declarator":
                    continue
                binding = child.child_by_field_name("name")
                if binding is not None and _pattern_mentions_name(
                    binding, source, name
                ):
                    return True
        elif current.type == "for_in_statement" and any(
            child.type == "var" for child in current.children
        ):
            binding = current.child_by_field_name("left")
            if binding is not None and _pattern_mentions_name(binding, source, name):
                return True
        pending.extend(current.named_children)
    return False


def _pattern_mentions_name(node: Any, source: bytes, name: str) -> bool:
    pending = [node]
    while pending:
        current = pending.pop()
        if current.type in {"identifier", "shorthand_property_identifier_pattern"}:
            if _text(current, source) == name:
                return True
        elif current.type == "pair_pattern":
            value = current.child_by_field_name("value")
            if value is None:
                return name in _text(current, source)
            pending.append(value)
        elif current.type in {"assignment_pattern", "object_assignment_pattern"}:
            left = current.child_by_field_name("left")
            if left is None:
                return name in _text(current, source)
            pending.append(left)
        elif current.type in {"object_pattern", "array_pattern", "rest_pattern"}:
            pending.extend(
                child for child in current.named_children if child.type != "comment"
            )
        elif name in _text(current, source):
            # Unknown binding syntax must not silently certify a duplicate.
            return True
    return False


def _inline_jsdoc_return(node: Any, source: bytes) -> str | None:
    comment = node.prev_named_sibling
    if comment is None or comment.type != "comment":
        return None
    text = _text(comment, source)
    gap = source[comment.end_byte : node.start_byte].replace(b"\r\n", b"\n")
    if not text.startswith("/**") or gap.strip() or gap.count(b"\n") > 1:
        return None
    match = _JSDOC_RETURN.search(text)
    if match is None:
        return None
    return match.group(1).strip() or None


def _jsdoc_has_callable_type(node: Any, source: bytes, *, inline: bool = False) -> bool:
    anchor = node
    if (
        not inline
        and anchor.parent is not None
        and anchor.parent.type == "export_statement"
    ):
        anchor = anchor.parent
    while True:
        comment = anchor.prev_named_sibling
        if comment is None or comment.type != "comment":
            return False
        gap = source[comment.end_byte : anchor.start_byte].replace(b"\r\n", b"\n")
        if gap.strip() or gap.count(b"\n") > 1:
            return False
        text = _text(comment, source)
        if text.startswith("/**") and re.search(r"@(?:type|overload)\b", text):
            return True
        if inline:
            return False
        anchor = comment


def _parse(source: str, file_path: Path) -> Any | None:
    try:
        from tree_sitter import Language, Parser
        import tree_sitter_typescript as ts_ts
    except ImportError:
        return None
    session = parse_typescript_source(
        source,
        file_path,
        Parser(Language(ts_ts.language_typescript())),
        Parser(Language(ts_ts.language_tsx())),
    )
    return None if session.parse_errors else session.tree.root_node


def _named_value_imports(root: Any, source: bytes) -> dict[str, list[tuple[str, str]]]:
    bindings: dict[str, list[tuple[str, str]]] = {}
    for statement in root.children:
        if statement.type != "import_statement" or _has_type_token(statement):
            continue
        module = _child(statement, "string")
        clause = _child(statement, "import_clause")
        named = _child(clause, "named_imports") if clause is not None else None
        if module is None or named is None:
            continue
        fragments = module.named_children
        if len(fragments) != 1 or fragments[0].type != "string_fragment":
            continue
        specifier = _text(fragments[0], source)
        if "\\" in specifier:
            continue
        for item in named.children:
            if item.type != "import_specifier" or _has_type_token(item):
                continue
            names = _identifiers(item, source)
            if len(names) in (1, 2):
                bindings.setdefault(names[-1], []).append((specifier, names[0]))
    return bindings


def _named_value_exports(root: Any, source: bytes) -> dict[str, list[str]]:
    exports: dict[str, list[str]] = {}
    for statement in root.children:
        if (
            statement.type != "export_statement"
            or _has_type_token(statement)
            or _child(statement, "string") is not None
        ):
            continue
        clause = _child(statement, "export_clause")
        if clause is None:
            continue
        for item in clause.children:
            if item.type != "export_specifier" or _has_type_token(item):
                continue
            names = _identifiers(item, source)
            if len(names) in (1, 2):
                exports.setdefault(names[-1], []).append(names[0])
    return exports


def _value_export_bindings(root: Any, source: bytes) -> dict[str, list[str]]:
    names = _named_value_exports(root, source)
    for statement in root.children:
        if (
            statement.type != "export_statement"
            or _has_type_token(statement)
            or any(child.type == "default" for child in statement.children)
        ):
            continue
        for declaration in statement.children:
            if declaration.type in {
                "function_declaration",
                "generator_function_declaration",
            }:
                node = declaration.child_by_field_name("name")
                if node is not None:
                    name = _text(node, source)
                    names.setdefault(name, []).append(name)
            elif declaration.type in {"lexical_declaration", "variable_declaration"}:
                for declarator in declaration.children:
                    if declarator.type == "variable_declarator":
                        node = declarator.child_by_field_name("name")
                        if node is not None and node.type == "identifier":
                            name = _text(node, source)
                            names.setdefault(name, []).append(name)
    return names


def _origin_path(specifier: str, file_path: str, project_root: Path) -> Path | None:
    root = Path(project_root).resolve()
    importer = root / file_path
    relative = specifier.startswith(("./", "../"))
    raw_target = importer.parent / specifier if relative else None
    if raw_target is not None and not _inside_project(raw_target, root):
        return None

    config_dir = _owning_config_dir(importer, root)
    response = _run_compiler_request(
        {
            "command": "resolveImportFile",
            "projectRoot": str(root),
            "compilerRoot": str(config_dir or root),
            "importerFile": file_path,
            "specifier": specifier,
        }
    )
    result = response.get("result") if response is not None else None
    if isinstance(result, dict) and result.get("status") == "resolved":
        resolved_path = result.get("path")
        if not isinstance(resolved_path, str) or not resolved_path:
            return None
        return _verified_origin(root / resolved_path, root)
    if isinstance(result, dict) and result.get("status") == "unresolved":
        return None
    if relative and raw_target is not None:
        if config_dir is not None:
            config = load_tsconfig(config_dir)
            if config is None or "extends" in config:
                return None
            references = config.get("references")
            if references is not None and (
                not isinstance(references, list) or references
            ):
                return None
            options = config.get("compilerOptions", {})
            if (
                not isinstance(options, dict)
                or "moduleSuffixes" in options
                or str(options.get("moduleResolution", "")).lower()
                in {"node16", "nodenext"}
                or str(options.get("module", "")).lower() in {"node16", "nodenext"}
            ):
                return None
            if not _fallback_config_owns_importer(config, config_dir, importer):
                return None
        base = raw_target
    else:
        return None

    path = _typescript_module_file(base, suffix_hint=Path(specifier).suffix)
    if path is None:
        return None
    return _verified_origin(path, root)


def _fallback_config_owns_importer(
    config: dict[str, Any], config_dir: Path, importer: Path
) -> bool:
    try:
        relative = importer.resolve().relative_to(config_dir.resolve())
    except (OSError, RuntimeError, ValueError):
        return False
    if any(
        part.startswith(".")
        or part in {"node_modules", "bower_components", "jspm_packages"}
        for part in relative.parts
    ):
        return False
    options = config.get("compilerOptions", {})
    if not isinstance(options, dict):
        return False
    if importer.suffix.lower() not in {
        ".ts",
        ".tsx",
        ".mts",
        ".cts",
    } and not options.get("allowJs"):
        return False
    output = options.get("outDir")
    if isinstance(output, str):
        try:
            importer.resolve().relative_to((config_dir / output).resolve())
        except ValueError:
            pass
        else:
            return False
    files = config.get("files")
    if files is not None:
        if not isinstance(files, list) or not all(
            isinstance(item, str) for item in files
        ):
            return False
        if any((config_dir / item).resolve() == importer.resolve() for item in files):
            return True
    excluded = config.get("exclude")
    if excluded is not None and excluded != []:
        return False
    includes = config.get("include")
    if includes is None:
        return files is None
    if not isinstance(includes, list) or not all(
        isinstance(item, str) for item in includes
    ):
        return False
    for pattern in includes:
        path = Path(pattern)
        if path.is_absolute() or ".." in path.parts or "[" in pattern or "]" in pattern:
            continue
        for match in glob.iglob(str(config_dir / pattern), recursive=True):
            candidate = Path(match).resolve()
            if candidate == importer.resolve():
                return True
            if candidate.is_dir():
                try:
                    importer.resolve().relative_to(candidate)
                except ValueError:
                    continue
                return True
    return False


def _verified_origin(path: Path, root: Path) -> Path | None:
    if not _inside_project(path, root):
        return None
    resolved = path.resolve()
    if resolved.suffix not in {".ts", ".tsx", ".js", ".jsx", ".mjs", ".mts", ".cts"}:
        return None
    if resolved.name.endswith((".d.ts", ".d.mts", ".d.cts")):
        return None
    return resolved


def _owning_config_dir(importer: Path, root: Path) -> Path | None:
    for directory in (importer.parent, *importer.parent.parents):
        if not _inside_project(directory, root):
            return None
        if (directory / "tsconfig.json").is_file():
            return directory
    return None


def _typescript_module_file(base: Path, *, suffix_hint: str) -> Path | None:
    # Preserve explicit suffixes and follow ordinary TypeScript precedence.
    suffixes = (".ts", ".tsx", ".d.ts", ".js", ".jsx")
    if suffix_hint in {".ts", ".tsx", ".js", ".jsx", ".mts", ".cts", ".mjs", ".cjs"}:
        if base.name.endswith(suffix_hint):
            base = base.with_suffix("")
        if suffix_hint in {".tsx", ".jsx"}:
            suffixes = (".tsx", ".ts", ".d.ts", ".jsx", ".js")
        elif suffix_hint in {".mts", ".mjs"}:
            suffixes = (".mts", ".d.mts", ".mjs")
        elif suffix_hint in {".cts", ".cjs"}:
            suffixes = (".cts", ".d.cts", ".cjs")
    candidates = [Path(f"{base}{suffix}") for suffix in suffixes]
    if base.is_dir():
        return next(
            (
                path
                for path, suffix in zip(candidates, suffixes)
                if suffix
                in {".ts", ".tsx", ".d.ts", ".mts", ".d.mts", ".cts", ".d.cts"}
                and path.is_file()
            ),
            None,
        )
    existing = [path for path in candidates if path.is_file()]
    return existing[0] if existing else None


def _inside_project(path: Path, root: Path) -> bool:
    try:
        relative = path.resolve().relative_to(root)
    except (OSError, RuntimeError, ValueError):
        return False
    return "node_modules" not in relative.parts


def _has_type_token(node: Any) -> bool:
    return any(child.type == "type" for child in node.children)


def _child(node: Any, kind: str) -> Any | None:
    return next((child for child in node.children if child.type == kind), None)


def _identifiers(node: Any, source: bytes) -> list[str]:
    children = [child for child in node.named_children if child.type != "comment"]
    if any(child.type != "identifier" for child in children):
        return []
    return [_text(child, source) for child in children]


def _text(node: Any, source: bytes) -> str:
    return source[node.start_byte : node.end_byte].decode("utf-8")
