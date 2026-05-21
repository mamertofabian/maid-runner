"""Reference recording helpers for Python behavioral artifact collection."""

from __future__ import annotations

import ast
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
_ImportFromEntry = tuple[str, Optional[str], Optional[str]]
_ImportEntry = tuple[str, str, Optional[str], str]
_ImportIdentity = tuple[Optional[str], Optional[str]]
_ObjectOwnerIdentity = tuple[Optional[str], str]
_ResolvedAttribute = tuple[str, str]


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

    def add_keyword_references(
        self,
        keywords: list[ast.keyword],
        *,
        import_source: Optional[str],
        owner: Optional[str],
    ) -> None:
        for keyword in keywords:
            if keyword.arg is not None:
                self.add_reference(
                    keyword.arg,
                    import_source=import_source,
                    of=owner,
                    reference_context="keyword",
                )

    def add_import_from_references(
        self,
        entries: list[_ImportFromEntry],
    ) -> None:
        for bound, source_module, alias_of in entries:
            self.add_reference(
                bound,
                import_source=source_module,
                alias_of=alias_of,
                reference_context="import",
            )

    def add_import_references(
        self,
        entries: list[_ImportEntry],
    ) -> None:
        for bound, source_module, alias_of, _namespace_root in entries:
            self.add_reference(
                bound,
                import_source=source_module,
                alias_of=alias_of,
                reference_context="import",
            )

    def add_bound_reference(
        self,
        name: str,
        *,
        reference_context: str,
        lexically_shadowed_import: bool = False,
        local_import: Optional[_ImportIdentity] = None,
        local_value_without_import: bool = False,
        function_import_bound: bool = False,
        module_shadowed: bool = False,
        imported_identity: _ImportIdentity = (None, None),
    ) -> None:
        if lexically_shadowed_import:
            self.add_reference(name, reference_context="local")
            return
        if local_import is not None:
            import_source, alias_of = local_import
        elif local_value_without_import:
            self.add_reference(name, reference_context="local")
            return
        elif function_import_bound:
            self.add_reference(name, reference_context="local")
            return
        elif module_shadowed:
            self.add_reference(name, reference_context="local")
            return
        else:
            import_source, alias_of = imported_identity
        self.add_reference(
            name,
            import_source=import_source,
            alias_of=alias_of,
            reference_context=reference_context,
        )

    def add_attribute_reference(
        self,
        name: str,
        *,
        object_owner_identity: Optional[_ObjectOwnerIdentity],
        resolved_attribute: Optional[_ResolvedAttribute],
        root_is_local_context: bool,
    ) -> None:
        if object_owner_identity is not None:
            source, owner = object_owner_identity
            self.add_reference(
                name,
                import_source=source,
                of=owner,
                reference_context="access",
            )
            return
        if resolved_attribute is not None:
            leaf, source = resolved_attribute
            self.add_reference(
                leaf,
                import_source=source,
                reference_context="access",
            )
            return
        context = "local" if root_is_local_context else "access"
        self.add_reference(name, reference_context=context)
