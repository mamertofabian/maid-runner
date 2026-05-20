"""Scope state objects for Python behavioral artifact collection."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional


_ImportScope = dict[str, tuple[Optional[str], Optional[str]]]
_ModuleImportScope = dict[str, str]
_ModuleAliasShadowScope = set[str]
_LocalValueScope = set[str]
_ObjectOwnerScope = dict[str, tuple[Optional[str], str]]


@dataclass
class _BehavioralClassScope:
    imports: _ImportScope = field(default_factory=dict)
    module_imports: _ModuleImportScope = field(default_factory=dict)
    module_alias_shadows: _ModuleAliasShadowScope = field(default_factory=set)
    local_values: _LocalValueScope = field(default_factory=set)
    object_owners: _ObjectOwnerScope = field(default_factory=dict)

    def push_to(
        self,
        *,
        local_import_scopes: list[_ImportScope],
        module_import_scopes: list[_ModuleImportScope],
        module_alias_shadow_scopes: list[_ModuleAliasShadowScope],
        local_value_scopes: list[_LocalValueScope],
        object_owner_scopes: list[_ObjectOwnerScope],
    ) -> None:
        local_import_scopes.append(self.imports)
        module_import_scopes.append(self.module_imports)
        module_alias_shadow_scopes.append(self.module_alias_shadows)
        local_value_scopes.append(self.local_values)
        object_owner_scopes.append(self.object_owners)

    def pop_from(
        self,
        *,
        local_import_scopes: list[_ImportScope],
        module_import_scopes: list[_ModuleImportScope],
        module_alias_shadow_scopes: list[_ModuleAliasShadowScope],
        local_value_scopes: list[_LocalValueScope],
        object_owner_scopes: list[_ObjectOwnerScope],
    ) -> None:
        object_owner_scopes.pop()
        local_value_scopes.pop()
        module_alias_shadow_scopes.pop()
        module_import_scopes.pop()
        local_import_scopes.pop()

    def is_active_on(
        self,
        *,
        local_import_scopes: list[_ImportScope],
        module_import_scopes: list[_ModuleImportScope],
        module_alias_shadow_scopes: list[_ModuleAliasShadowScope],
        local_value_scopes: list[_LocalValueScope],
        object_owner_scopes: list[_ObjectOwnerScope],
    ) -> bool:
        return (
            bool(local_import_scopes)
            and local_import_scopes[-1] is self.imports
            and bool(module_import_scopes)
            and module_import_scopes[-1] is self.module_imports
            and bool(module_alias_shadow_scopes)
            and module_alias_shadow_scopes[-1] is self.module_alias_shadows
            and bool(local_value_scopes)
            and local_value_scopes[-1] is self.local_values
            and bool(object_owner_scopes)
            and object_owner_scopes[-1] is self.object_owners
        )
