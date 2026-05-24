"""TypeScript/JavaScript validator for MAID Runner v2.

Uses tree-sitter for accurate AST parsing. Requires tree-sitter-typescript.
"""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path
from typing import Optional, Union

from maid_runner.core.ts_module_paths import (
    resolve_ts_reexport,
    ts_file_to_module_path,
)
from maid_runner.validators.base import BaseValidator, CollectionResult
from maid_runner.validators._typescript_behavioral import (
    collect_behavioral_artifacts as collect_ts_behavioral_artifacts,
    collect_test_function_bodies as collect_ts_test_function_bodies,
)
from maid_runner.validators._typescript_implementation import (
    collect_implementation_artifacts as collect_ts_implementation_artifacts,
)
from maid_runner.validators._typescript_parse import parse_typescript_source

try:
    from tree_sitter import Language, Parser
    import tree_sitter_typescript as ts_ts

    _HAS_TREE_SITTER = True
except ImportError:
    _HAS_TREE_SITTER = False


class TypeScriptValidator(BaseValidator):
    def __init__(self) -> None:
        if not _HAS_TREE_SITTER:
            raise ImportError(
                "tree-sitter-typescript is required for TypeScript validation. "
                "Install with: pip install tree-sitter tree-sitter-typescript"
            )
        self._ts_lang = Language(ts_ts.language_typescript())
        self._tsx_lang = Language(ts_ts.language_tsx())
        self._ts_parser = Parser(self._ts_lang)
        self._tsx_parser = Parser(self._tsx_lang)

    @classmethod
    def supported_extensions(cls) -> tuple[str, ...]:
        return (".ts", ".tsx", ".js", ".jsx", ".mts", ".cts")

    def collect_implementation_artifacts(
        self,
        source: str,
        file_path: Union[str, Path],
    ) -> CollectionResult:
        def _collect_implementation(session):
            artifacts = collect_ts_implementation_artifacts(
                session.tree.root_node, session.source_bytes
            )
            if session.module_id:
                artifacts = [
                    (
                        replace(a, module_path=session.module_id)
                        if a.module_path is None
                        else a
                    )
                    for a in artifacts
                ]
            return artifacts

        return self._collect_with_parse_guard(
            language="typescript",
            file_path=file_path,
            parse_fn=lambda: parse_typescript_source(
                source,
                file_path,
                self._ts_parser,
                self._tsx_parser,
            ),
            collect_fn=_collect_implementation,
            errors_from_session=lambda session: session.parse_errors,
        )

    def collect_behavioral_artifacts(
        self,
        source: str,
        file_path: Union[str, Path],
    ) -> CollectionResult:
        return self._collect_with_parse_guard(
            language="typescript",
            file_path=file_path,
            parse_fn=lambda: parse_typescript_source(
                source,
                file_path,
                self._ts_parser,
                self._tsx_parser,
            ),
            collect_fn=lambda session: collect_ts_behavioral_artifacts(
                session.tree.root_node,
                session.source_bytes,
                file_path,
            ),
            errors_from_session=lambda session: session.parse_errors,
        )

    def module_path(
        self,
        file_path: Union[str, Path],
        project_root: Path,
    ) -> Optional[str]:
        return ts_file_to_module_path(file_path, project_root) or None

    def resolve_reexport(
        self,
        module: str,
        name: str,
        project_root: Path,
    ) -> Optional[tuple[str, str]]:
        return resolve_ts_reexport(module, name, project_root)

    def get_test_function_bodies(
        self,
        source: str,
        file_path: Union[str, Path],
    ) -> dict[str, str]:
        session = parse_typescript_source(
            source, file_path, self._ts_parser, self._tsx_parser
        )
        if session.parse_errors:
            return {}

        return collect_ts_test_function_bodies(
            session.tree.root_node,
            session.source_bytes,
        )
