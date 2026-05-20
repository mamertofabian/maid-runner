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


@dataclass
class _BehavioralFunctionScope:
    shadowed_imports: set[str] = field(default_factory=set)
    import_bound_names: set[str] = field(default_factory=set)
    imports: _ImportScope = field(default_factory=dict)
    module_imports: _ModuleImportScope = field(default_factory=dict)
    module_alias_shadows: _ModuleAliasShadowScope = field(default_factory=set)
    local_values: _LocalValueScope = field(default_factory=set)
    object_owners: _ObjectOwnerScope = field(default_factory=dict)
    argument_names: set[str] = field(default_factory=set)

    def push_to(
        self,
        *,
        local_import_scopes: list[_ImportScope],
        module_import_scopes: list[_ModuleImportScope],
        module_alias_shadow_scopes: list[_ModuleAliasShadowScope],
        local_value_scopes: list[_LocalValueScope],
        object_owner_scopes: list[_ObjectOwnerScope],
        argument_name_scopes: list[set[str]],
        shadowed_import_scopes: list[set[str]],
        function_import_bound_scopes: list[set[str]],
    ) -> None:
        shadowed_import_scopes.append(self.shadowed_imports)
        function_import_bound_scopes.append(self.import_bound_names)
        local_import_scopes.append(self.imports)
        module_import_scopes.append(self.module_imports)
        module_alias_shadow_scopes.append(self.module_alias_shadows)
        local_value_scopes.append(self.local_values)
        object_owner_scopes.append(self.object_owners)
        argument_name_scopes.append(self.argument_names)

    def pop_from(
        self,
        *,
        local_import_scopes: list[_ImportScope],
        module_import_scopes: list[_ModuleImportScope],
        module_alias_shadow_scopes: list[_ModuleAliasShadowScope],
        local_value_scopes: list[_LocalValueScope],
        object_owner_scopes: list[_ObjectOwnerScope],
        argument_name_scopes: list[set[str]],
        shadowed_import_scopes: list[set[str]],
        function_import_bound_scopes: list[set[str]],
    ) -> None:
        argument_name_scopes.pop()
        object_owner_scopes.pop()
        local_value_scopes.pop()
        module_alias_shadow_scopes.pop()
        module_import_scopes.pop()
        local_import_scopes.pop()
        function_import_bound_scopes.pop()
        shadowed_import_scopes.pop()


@dataclass
class _BehavioralExpressionScope:
    shadowed_imports: set[str] = field(default_factory=set)
    module_alias_shadows: set[str] = field(default_factory=set)

    def push_to(
        self,
        *,
        shadowed_import_scopes: list[set[str]],
        module_alias_shadow_scopes: list[set[str]],
    ) -> None:
        shadowed_import_scopes.append(self.shadowed_imports)
        module_alias_shadow_scopes.append(self.module_alias_shadows)

    def pop_from(
        self,
        *,
        shadowed_import_scopes: list[set[str]],
        module_alias_shadow_scopes: list[set[str]],
    ) -> None:
        module_alias_shadow_scopes.pop()
        shadowed_import_scopes.pop()


@dataclass
class _BehavioralLazyModuleAliasScope:
    module_imports: _ModuleImportScope = field(default_factory=dict)
    module_alias_shadows: _ModuleAliasShadowScope = field(default_factory=set)

    def push_to(
        self,
        *,
        module_import_scopes: list[_ModuleImportScope],
        module_alias_shadow_scopes: list[_ModuleAliasShadowScope],
    ) -> None:
        module_import_scopes.append(self.module_imports)
        module_alias_shadow_scopes.append(self.module_alias_shadows)

    def pop_from(
        self,
        *,
        module_import_scopes: list[_ModuleImportScope],
        module_alias_shadow_scopes: list[_ModuleAliasShadowScope],
    ) -> None:
        module_alias_shadow_scopes.pop()
        module_import_scopes.pop()


@dataclass
class _BehavioralModuleAliasEvents:
    events: dict[str, list[tuple[tuple[int, int], Optional[str]]]] = field(
        default_factory=dict
    )

    def clear(self) -> None:
        self.events.clear()

    def record(
        self,
        name: str,
        source: Optional[str],
        position: Optional[tuple[int, int]],
    ) -> None:
        if position is None:
            return
        self.events.setdefault(name, []).append((position, source))

    def source_at(
        self,
        name: str,
        position: tuple[int, int],
    ) -> tuple[bool, Optional[str]]:
        events = self.events.get(name, [])
        if not events:
            return False, None

        source: Optional[str] = None
        for event_position, event_source in sorted(events, key=lambda event: event[0]):
            if event_position > position:
                break
            source = event_source
        return True, source
