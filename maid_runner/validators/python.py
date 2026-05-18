"""Python language validator for MAID Runner v2.

Collects artifact definitions and references from Python source code using AST.
"""

from __future__ import annotations

import ast
from pathlib import Path
from typing import Optional, Union

from maid_runner.core.module_paths import (
    file_to_module_path,
    resolve_relative_import,
    resolve_reexport,
)
from maid_runner.core.types import ArtifactKind, ArgSpec
from maid_runner.validators._python_implementation import (
    _ImplementationCollector as _MovedImplementationCollector,
    _ast_to_default_string as _python_ast_to_default_string,
    _ast_to_type_string as _python_ast_to_type_string,
    _extract_args as _python_extract_args,
    _extract_base_name as _python_extract_base_name,
    _get_return_type as _python_get_return_type,
    _has_property_decorator as _python_has_property_decorator,
    _is_stub_body as _python_is_stub_body,
    collect_implementation_artifacts,
)
from maid_runner.validators.base import BaseValidator, CollectionResult, FoundArtifact


_ImportScope = dict[str, tuple[Optional[str], Optional[str]]]
_ModuleImportScope = dict[str, str]
_ModuleAliasShadowScope = set[str]
_LocalValueScope = set[str]
_ObjectOwnerScope = dict[str, tuple[Optional[str], str]]
_ClassScopeMarker = tuple[
    _ImportScope,
    _ModuleImportScope,
    _ModuleAliasShadowScope,
    _LocalValueScope,
    _ObjectOwnerScope,
]


class PythonValidator(BaseValidator):
    @classmethod
    def supported_extensions(cls) -> tuple[str, ...]:
        return (".py",)

    def collect_implementation_artifacts(
        self,
        source: str,
        file_path: Union[str, Path],
    ) -> CollectionResult:
        try:
            tree = ast.parse(source, filename=str(file_path))
        except SyntaxError as e:
            return CollectionResult(
                artifacts=[],
                language="python",
                file_path=str(file_path),
                errors=[f"Syntax error: {e}"],
            )

        return CollectionResult(
            artifacts=collect_implementation_artifacts(tree, str(file_path)),
            language="python",
            file_path=str(file_path),
        )

    def collect_behavioral_artifacts(
        self,
        source: str,
        file_path: Union[str, Path],
    ) -> CollectionResult:
        try:
            tree = ast.parse(source, filename=str(file_path))
        except SyntaxError as e:
            return CollectionResult(
                artifacts=[],
                language="python",
                file_path=str(file_path),
                errors=[f"Syntax error: {e}"],
            )

        collector = _BehavioralCollector(file_path=str(file_path))
        collector.scan_imports(tree)
        collector.visit(tree)

        return CollectionResult(
            artifacts=collector.artifacts,
            language="python",
            file_path=str(file_path),
        )

    def get_test_function_bodies(
        self,
        source: str,
        file_path: Union[str, Path],
    ) -> dict[str, str]:
        try:
            tree = ast.parse(source, filename=str(file_path))
        except SyntaxError:
            return {}

        bodies: dict[str, str] = {}
        lines = source.splitlines(keepends=True)
        _walk_for_test_bodies(tree, lines, bodies, in_test_class=False)
        return bodies

    def module_path(
        self,
        file_path: Union[str, Path],
        project_root: Path,
    ) -> Optional[str]:
        return file_to_module_path(file_path, project_root) or None

    def resolve_reexport(
        self,
        module: str,
        name: str,
        project_root: Path,
    ) -> Optional[tuple[str, str]]:
        return resolve_reexport(module, name, project_root)


class _ImplementationCollector(_MovedImplementationCollector):
    """Compatibility shim for older active manifests.

    PythonValidator delegates to _python_implementation.collect_implementation_artifacts;
    these private wrappers keep the pre-existing manifest contract valid while
    the collector logic lives in the focused module.
    """

    def __init__(self, file_path: str = "") -> None:
        super().__init__(file_path=file_path)
        self.artifacts = self.artifacts
        self._current_class = self._current_class
        self._in_function = self._in_function
        self._is_init = self._is_init

    def visit_ClassDef(self, node: ast.ClassDef) -> None:
        return super().visit_ClassDef(node)

    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
        return super().visit_FunctionDef(node)

    def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> None:
        return super().visit_AsyncFunctionDef(node)

    def _handle_function(
        self, node: ast.FunctionDef | ast.AsyncFunctionDef, is_async: bool
    ) -> None:
        return super()._handle_function(node, is_async)

    def visit_Assign(self, node: ast.Assign) -> None:
        return super().visit_Assign(node)

    def visit_AnnAssign(self, node: ast.AnnAssign) -> None:
        return super().visit_AnnAssign(node)

    def visit_ImportFrom(self, node: ast.ImportFrom) -> None:
        return super().visit_ImportFrom(node)

    def _has_artifact(self, name: str, of: Optional[str]) -> bool:
        return super()._has_artifact(name, of)


class _BehavioralCollector(ast.NodeVisitor):
    """Collect artifact references (imports, calls, attribute access)."""

    def __init__(self, file_path: str = "") -> None:
        self.artifacts: list[FoundArtifact] = []
        self._seen: set[
            tuple[
                str,
                Optional[str],
                Optional[str],
                Optional[str],
                Optional[str],
            ]
        ] = set()
        self._seen_test_funcs: set[str] = set()
        self._function_depth = 0
        self._class_stack: list[bool] = []
        self._class_scope_markers: list[_ClassScopeMarker] = []
        self._importer_module: Optional[str] = (
            file_to_module_path(file_path, Path(".")) if file_path else None
        ) or None
        # Maps a bound name to the namespace that name refers to. Populated
        # only by plain `import pkg.mod` / `import pkg.mod as pm` so that
        # attribute chains rooted at the bound name (e.g. ``pkg.mod.Foo``)
        # can resolve the leaf reference's import_source.
        self._module_imports: dict[str, str] = {}
        self._dynamic_module_aliases: set[str] = set()
        self._dynamic_module_alias_events: dict[
            str, list[tuple[tuple[int, int], Optional[str]]]
        ] = {}
        self._scanning_module_bindings = False
        self._imported_names: dict[str, tuple[Optional[str], Optional[str]]] = {}
        self._known_imported_names: set[str] = set()
        self._module_shadowed_imports: set[str] = set()
        self._local_import_scopes: list[_ImportScope] = []
        self._local_module_import_scopes: list[_ModuleImportScope] = []
        self._local_module_alias_shadow_scopes: list[_ModuleAliasShadowScope] = []
        self._expression_module_alias_shadow_scopes: list[set[str]] = []
        self._local_value_scopes: list[_LocalValueScope] = [set()]
        self._object_owner_scopes: list[_ObjectOwnerScope] = []
        self._argument_name_scopes: list[set[str]] = []
        self._shadowed_import_scopes: list[set[str]] = []
        self._function_import_bound_scopes: list[set[str]] = []

    def scan_imports(self, tree: ast.AST) -> None:
        self._known_imported_names = _all_imported_bound_names(tree)
        self._module_imports.clear()
        self._dynamic_module_aliases.clear()
        self._dynamic_module_alias_events.clear()
        self._imported_names.clear()
        self._module_shadowed_imports.clear()
        self._local_value_scopes[0].clear()

        if not isinstance(tree, ast.Module):
            return
        self._scanning_module_bindings = True
        try:
            for statement in tree.body:
                self._apply_module_statement_binding(statement)
                self._local_value_scopes[0].update(
                    _module_statement_local_value_bindings(statement)
                )
        finally:
            self._scanning_module_bindings = False

    def _apply_module_statement_binding(self, statement: ast.stmt) -> None:
        if isinstance(statement, ast.ImportFrom):
            position = _node_end_position(statement)
            for bound, source_module, alias_of in self._import_from_entries(statement):
                self._unbind_module_aliases({bound}, position=position)
                self._bind_imported_name(bound, source_module, alias_of)
                self._record_module_alias_event(
                    bound,
                    self._module_imports.get(bound),
                    position,
                )
            return
        if isinstance(statement, ast.Import):
            position = _node_end_position(statement)
            for bound, source_module, alias_of, namespace_root in self._import_entries(
                statement
            ):
                self._unbind_module_aliases({bound}, position=position)
                self._bind_imported_name(
                    bound,
                    source_module,
                    alias_of,
                    namespace_root=namespace_root,
                )
                self._record_module_alias_event(
                    bound,
                    self._module_imports.get(bound),
                    position,
                )
            return

        if isinstance(statement, ast.Assign):
            self._apply_module_assignment_binding(statement.targets, statement.value)
            return

        if isinstance(statement, ast.AnnAssign):
            if statement.value is None:
                self._apply_module_expression_bindings(statement.annotation)
                return
            self._apply_module_assignment_binding([statement.target], statement.value)
            return

        if isinstance(statement, (ast.FunctionDef, ast.AsyncFunctionDef)):
            self._apply_module_function_definition_expression_bindings(statement)
            self._unbind_module_level_bindings(
                {statement.name},
                position=_node_end_position(statement),
            )
            return

        if isinstance(statement, ast.ClassDef):
            self._apply_module_class_definition_expression_bindings(statement)
            self._unbind_module_level_bindings(
                {statement.name},
                position=_node_end_position(statement),
            )
            return

        if isinstance(statement, ast.Try):
            for child in statement.body:
                self._apply_module_statement_binding(child)
            for handler in statement.handlers:
                if handler.name:
                    self._unbind_module_level_bindings(
                        {handler.name},
                        position=_node_start_position(handler),
                    )
                for child in handler.body:
                    self._apply_module_statement_binding(child)
                if handler.name:
                    self._unbind_module_level_bindings(
                        {handler.name},
                        position=_node_end_position(handler),
                    )
            for child in statement.orelse + statement.finalbody:
                self._apply_module_statement_binding(child)
            return

        if isinstance(statement, ast.If):
            self._apply_module_expression_bindings(statement.test)
            for child in _reachable_conditional_statements(
                statement.test,
                statement.body,
                statement.orelse,
            ):
                self._apply_module_statement_binding(child)
            return

        if isinstance(statement, ast.While):
            self._apply_module_expression_bindings(statement.test)
            truth = _static_truth_value(statement.test)
            statements = (
                statement.orelse
                if truth is False
                else (statement.body + statement.orelse)
            )
            for child in statements:
                self._apply_module_statement_binding(child)
            return

        if isinstance(statement, (ast.For, ast.AsyncFor)):
            self._apply_module_expression_bindings(statement.iter)
            target_bindings: set[str] = set()
            _collect_target_bindings(statement.target, target_bindings)
            self._unbind_module_level_bindings(
                target_bindings,
                position=_node_end_position(statement.iter),
            )
            for child in statement.body + statement.orelse:
                self._apply_module_statement_binding(child)
            return

        if isinstance(statement, (ast.With, ast.AsyncWith)):
            for item in statement.items:
                self._apply_module_expression_bindings(item.context_expr)
                if item.optional_vars is not None:
                    bindings: set[str] = set()
                    _collect_target_bindings(item.optional_vars, bindings)
                    self._unbind_module_level_bindings(
                        bindings,
                        position=_node_end_position(item.context_expr),
                    )
            for child in statement.body:
                self._apply_module_statement_binding(child)
            return

        if isinstance(statement, ast.Match):
            self._apply_module_expression_bindings(statement.subject)
            for case in statement.cases:
                bindings: set[str] = set()
                _collect_pattern_bindings(case.pattern, bindings)
                self._unbind_module_level_bindings(
                    bindings,
                    position=_node_end_position(case.pattern),
                )
                self._apply_module_expression_bindings(case.guard)
                for child in case.body:
                    self._apply_module_statement_binding(child)
            return

        if isinstance(statement, ast.Expr):
            self._apply_module_expression_bindings(statement.value)
            return

        if isinstance(statement, ast.Assert):
            self._apply_module_expression_bindings(statement.test)
            self._apply_module_expression_bindings(statement.msg)
            return

        bindings: set[str] = set()
        _collect_statement_bindings(statement, bindings)
        self._unbind_module_level_bindings(
            bindings,
            position=_node_end_position(statement),
        )

    def _apply_module_assignment_binding(
        self,
        targets: list[ast.expr],
        value: Optional[ast.AST],
    ) -> None:
        self._apply_module_expression_bindings(value)
        names: set[str] = set()
        for target in targets:
            _collect_target_bindings(target, names)
        dynamic_module = self._literal_importlib_import_module_path(value)
        if dynamic_module is None:
            self._unbind_module_level_bindings(
                names, position=_binding_position(value, targets)
            )
            return
        direct_names = _direct_name_targets(targets)
        self._unbind_module_aliases(
            names - direct_names, position=_binding_position(value, targets)
        )
        self._bind_module_aliases(
            direct_names,
            dynamic_module,
            position=_binding_position(value, targets),
        )

    def _unbind_module_level_bindings(
        self,
        names: set[str],
        *,
        position: Optional[tuple[int, int]] = None,
    ) -> None:
        self._unbind_module_aliases(names, position=position)
        for name in names & self._known_imported_names:
            self._unbind_imported_name(name)

    def _apply_module_function_definition_expression_bindings(
        self,
        node: ast.FunctionDef | ast.AsyncFunctionDef,
    ) -> None:
        for decorator in node.decorator_list:
            self._apply_module_expression_bindings(decorator)
        for default in list(node.args.defaults) + list(node.args.kw_defaults):
            self._apply_module_expression_bindings(default)

    def _apply_module_class_definition_expression_bindings(
        self,
        node: ast.ClassDef,
    ) -> None:
        for decorator in node.decorator_list:
            self._apply_module_expression_bindings(decorator)
        for base in node.bases:
            self._apply_module_expression_bindings(base)
        for keyword in node.keywords:
            self._apply_module_expression_bindings(keyword.value)

    def _apply_module_expression_bindings(self, expr: Optional[ast.AST]) -> None:
        if expr is None:
            return
        if isinstance(expr, ast.BoolOp):
            self._apply_module_boolop_bindings(expr)
            return
        if isinstance(expr, ast.IfExp):
            self._apply_module_expression_bindings(expr.test)
            for branch in _reachable_conditional_expressions(
                expr.test,
                expr.body,
                expr.orelse,
            ):
                self._apply_module_expression_bindings(branch)
            return
        if isinstance(expr, ast.NamedExpr):
            self._apply_module_expression_bindings(expr.value)
            names: set[str] = set()
            _collect_target_bindings(expr.target, names)
            dynamic_module = self._literal_importlib_import_module_path(expr.value)
            if dynamic_module is not None and isinstance(expr.target, ast.Name):
                self._bind_module_aliases(
                    {expr.target.id},
                    dynamic_module,
                    position=_node_end_position(expr.value),
                )
            else:
                self._unbind_module_level_bindings(
                    names,
                    position=_node_end_position(expr.value),
                )
            return
        if isinstance(expr, ast.Lambda):
            for default in expr.args.defaults:
                self._apply_module_expression_bindings(default)
            for default in expr.args.kw_defaults:
                self._apply_module_expression_bindings(default)
            return
        if isinstance(expr, ast.DictComp):
            self._apply_module_comprehension_bindings(expr)
            self._apply_module_expression_bindings(expr.key)
            self._apply_module_expression_bindings(expr.value)
            return
        if isinstance(expr, (ast.ListComp, ast.SetComp)):
            self._apply_module_comprehension_bindings(expr)
            self._apply_module_expression_bindings(expr.elt)
            return
        if isinstance(expr, ast.GeneratorExp):
            generators = list(expr.generators)
            if generators:
                self._apply_module_expression_bindings(generators[0].iter)
            return
        for child in ast.iter_child_nodes(expr):
            if isinstance(child, ast.AST):
                self._apply_module_expression_bindings(child)

    def _apply_module_boolop_bindings(self, expr: ast.BoolOp) -> None:
        for value in expr.values:
            self._apply_module_expression_bindings(value)
            truth = _static_truth_value(value)
            if isinstance(expr.op, ast.And) and truth is False:
                return
            if isinstance(expr.op, ast.Or) and truth is True:
                return

    def _apply_module_comprehension_bindings(
        self,
        expr: ast.ListComp | ast.SetComp | ast.DictComp,
    ) -> None:
        for generator in expr.generators:
            self._apply_module_expression_bindings(generator.iter)
            for guard in generator.ifs:
                self._apply_module_expression_bindings(guard)

    def _bind_imported_name(
        self,
        bound: str,
        source_module: Optional[str],
        alias_of: Optional[str],
        *,
        namespace_root: Optional[str] = None,
    ) -> None:
        self._imported_names[bound] = (source_module, alias_of)
        self._dynamic_module_aliases.discard(bound)
        if namespace_root is None:
            module_source = _module_member_import_source(
                source_module, alias_of or bound
            )
            if module_source is None:
                self._module_imports.pop(bound, None)
            else:
                self._module_imports[bound] = module_source
        else:
            self._module_imports[bound] = namespace_root
        self._module_shadowed_imports.discard(bound)

    def _unbind_imported_name(self, name: str) -> None:
        self._imported_names.pop(name, None)
        self._module_imports.pop(name, None)
        self._dynamic_module_aliases.discard(name)
        self._module_shadowed_imports.add(name)

    def _import_from_entries(
        self,
        node: ast.ImportFrom,
    ) -> list[tuple[str, Optional[str], Optional[str]]]:
        entries: list[tuple[str, Optional[str], Optional[str]]] = []
        if not node.names:
            return entries
        level = node.level or 0
        if level > 0 and self._importer_module:
            source_module = resolve_relative_import(
                node.module,
                level,
                self._importer_module,
            )
        else:
            source_module = node.module or ""
        for alias in node.names:
            if alias.name == "*":
                continue
            bound = alias.asname or alias.name
            alias_of = alias.name if alias.asname else None
            entries.append((bound, source_module or None, alias_of))
        return entries

    def _import_entries(
        self,
        node: ast.Import,
    ) -> list[tuple[str, str, Optional[str], str]]:
        entries: list[tuple[str, str, Optional[str], str]] = []
        for alias in node.names:
            # `import pkg.mod`       -> Python binds the top-level `pkg`.
            # `import pkg.mod as pm` -> Python binds `pm`.
            if alias.asname:
                bound = alias.asname
                alias_of = alias.name
                namespace_root = alias.name
            else:
                bound = alias.name.split(".", 1)[0]
                alias_of = None
                namespace_root = bound
            entries.append((bound, alias.name, alias_of, namespace_root))
        return entries

    def visit_ImportFrom(self, node: ast.ImportFrom) -> None:
        entries = self._import_from_entries(node)
        if self._local_import_scopes:
            for bound, source_module, alias_of in entries:
                self._local_import_scopes[-1][bound] = (source_module, alias_of)
                module_source = _module_member_import_source(
                    source_module, alias_of or bound
                )
                if module_source is None:
                    self._local_module_import_scopes[-1].pop(bound, None)
                else:
                    self._local_module_import_scopes[-1][bound] = module_source
        self._record_import_from_reference(node)
        self.generic_visit(node)

    def _record_import_from_reference(self, node: ast.ImportFrom) -> None:
        for bound, source_module, alias_of in self._import_from_entries(node):
            self._add_reference(
                bound,
                import_source=source_module,
                alias_of=alias_of,
                reference_context="import",
            )

    def visit_Import(self, node: ast.Import) -> None:
        entries = self._import_entries(node)
        if self._local_import_scopes:
            for bound, source_module, alias_of, namespace_root in entries:
                self._local_import_scopes[-1][bound] = (source_module, alias_of)
                self._local_module_import_scopes[-1][bound] = namespace_root
        self._record_import_reference(node)
        self.generic_visit(node)

    def _record_import_reference(self, node: ast.Import) -> None:
        for bound, source_module, alias_of, _namespace_root in self._import_entries(
            node
        ):
            self._add_reference(
                bound,
                import_source=source_module,
                alias_of=alias_of,
                reference_context="import",
            )

    def visit_Call(self, node: ast.Call) -> None:
        keyword_import_source: Optional[str] = None
        keyword_owner: Optional[str] = None
        if isinstance(node.func, ast.Name):
            keyword_identity = self._keyword_import_identity_for_name(node.func.id)
            if keyword_identity is not None:
                keyword_import_source, keyword_owner = keyword_identity
            self._add_bound_reference(node.func.id, reference_context="call")
        elif isinstance(node.func, ast.Attribute):
            resolved = self._resolve_attribute_chain(node.func)
            if resolved is not None:
                leaf, source = resolved
                keyword_import_source = source
                keyword_owner = leaf
                self._add_reference(
                    leaf,
                    import_source=source,
                    reference_context="call",
                )
            else:
                context = (
                    "local"
                    if (
                        self._attribute_root_is_shadowed(node.func)
                        or self._attribute_root_is_local_value(node.func)
                    )
                    else "call"
                )
                self._add_reference(node.func.attr, reference_context=context)
        for kw in node.keywords:
            if kw.arg is not None:  # **kwargs has arg=None
                self._add_reference(
                    kw.arg,
                    import_source=keyword_import_source,
                    of=keyword_owner,
                    reference_context="keyword",
                )
        self.generic_visit(node)

    def visit_Name(self, node: ast.Name) -> None:
        if not isinstance(node.ctx, ast.Load):
            return None
        self._add_bound_reference(node.id, reference_context="access")
        self.generic_visit(node)

    def visit_Attribute(self, node: ast.Attribute) -> None:
        if not isinstance(node.ctx, ast.Load):
            return None
        owner_identity = self._object_owner_identity_for_member_access(node)
        if owner_identity is not None:
            source, owner = owner_identity
            self._add_reference(
                node.attr,
                import_source=source,
                of=owner,
                reference_context="access",
            )
        elif (resolved := self._resolve_attribute_chain(node)) is not None:
            leaf, source = resolved
            self._add_reference(
                leaf,
                import_source=source,
                reference_context="access",
            )
        else:
            context = (
                "local"
                if (
                    self._attribute_root_is_shadowed(node)
                    or self._attribute_root_is_local_value(node)
                )
                else "access"
            )
            self._add_reference(node.attr, reference_context=context)
        self.generic_visit(node)

    def visit_arg(self, node: ast.arg) -> None:
        return None

    def visit_Assign(self, node: ast.Assign) -> None:
        names: set[str] = set()
        for target in node.targets:
            _collect_target_bindings(target, names)
        self.visit(node.value)
        if self._local_module_import_scopes:
            dynamic_module = self._literal_importlib_import_module_path(node.value)
            if dynamic_module is None:
                self._unbind_module_aliases(names)
            else:
                direct_names = _direct_name_targets(node.targets)
                self._unbind_module_aliases(names - direct_names)
                self._bind_module_aliases(direct_names, dynamic_module)
        if self._assignment_value_is_local_value(node.value):
            self._local_value_scopes[-1].update(names)
        self._record_assignment_owner_bindings(node.targets, node.value)

    def visit_AnnAssign(self, node: ast.AnnAssign) -> None:
        names: set[str] = set()
        _collect_target_bindings(node.target, names)
        self.visit(node.target)
        if node.value is None:
            return
        self.visit(node.value)
        if self._local_module_import_scopes:
            dynamic_module = self._literal_importlib_import_module_path(node.value)
            if dynamic_module is None:
                self._unbind_module_aliases(names)
            else:
                direct_names = (
                    {node.target.id} if isinstance(node.target, ast.Name) else set()
                )
                self._unbind_module_aliases(names - direct_names)
                self._bind_module_aliases(direct_names, dynamic_module)
        if self._assignment_value_is_local_value(node.value):
            self._local_value_scopes[-1].update(names)
        self._record_assignment_owner_bindings([node.target], node.value)

    def visit_AugAssign(self, node: ast.AugAssign) -> None:
        names: set[str] = set()
        _collect_target_bindings(node.target, names)
        self._unbind_module_aliases(names)
        self.visit(node.value)

    def visit_NamedExpr(self, node: ast.NamedExpr) -> None:
        names: set[str] = set()
        _collect_target_bindings(node.target, names)
        self.visit(node.value)
        dynamic_module = self._literal_importlib_import_module_path(node.value)
        if dynamic_module is None:
            self._unbind_module_aliases(names)
        elif isinstance(node.target, ast.Name):
            self._bind_module_aliases({node.target.id}, dynamic_module)
        else:
            self._unbind_module_aliases(names)

    def visit_BoolOp(self, node: ast.BoolOp) -> None:
        for value in node.values:
            self.visit(value)
            truth = _static_truth_value(value)
            if isinstance(node.op, ast.And) and truth is False:
                return
            if isinstance(node.op, ast.Or) and truth is True:
                return

    def visit_IfExp(self, node: ast.IfExp) -> None:
        self.visit(node.test)
        for branch in _reachable_conditional_expressions(
            node.test,
            node.body,
            node.orelse,
        ):
            self.visit(branch)

    def visit_If(self, node: ast.If) -> None:
        self.visit(node.test)
        for statement in _reachable_conditional_statements(
            node.test,
            node.body,
            node.orelse,
        ):
            self.visit(statement)

    def visit_While(self, node: ast.While) -> None:
        self.visit(node.test)
        truth = _static_truth_value(node.test)
        statements = node.orelse if truth is False else node.body + node.orelse
        for statement in statements:
            self.visit(statement)

    def visit_For(self, node: ast.For) -> None:
        self._visit_loop(node)

    def visit_AsyncFor(self, node: ast.AsyncFor) -> None:
        self._visit_loop(node)

    def _visit_loop(self, node: ast.For | ast.AsyncFor) -> None:
        names: set[str] = set()
        _collect_target_bindings(node.target, names)
        self.visit(node.iter)
        self._unbind_module_aliases(names)
        for statement in node.body + node.orelse:
            self.visit(statement)

    def visit_With(self, node: ast.With) -> None:
        self._visit_with(node)

    def visit_AsyncWith(self, node: ast.AsyncWith) -> None:
        self._visit_with(node)

    def _visit_with(self, node: ast.With | ast.AsyncWith) -> None:
        for item in node.items:
            self.visit(item.context_expr)
            if item.optional_vars is not None:
                names: set[str] = set()
                _collect_target_bindings(item.optional_vars, names)
                self._unbind_module_aliases(names)
        for statement in node.body:
            self.visit(statement)

    def visit_Delete(self, node: ast.Delete) -> None:
        names: set[str] = set()
        for target in node.targets:
            _collect_target_bindings(target, names)
        self._unbind_module_aliases(names)

    def visit_Match(self, node: ast.Match) -> None:
        self.visit(node.subject)
        for case in node.cases:
            self._visit_match_pattern_references(case.pattern)
            names: set[str] = set()
            _collect_pattern_bindings(case.pattern, names)
            self._unbind_module_aliases(names)
            if case.guard is not None:
                self.visit(case.guard)
            for statement in case.body:
                self.visit(statement)

    def _visit_match_pattern_references(self, pattern: ast.pattern) -> None:
        if isinstance(pattern, ast.MatchValue):
            self.visit(pattern.value)
            return
        if isinstance(pattern, ast.MatchClass):
            self.visit(pattern.cls)
            for child in list(pattern.patterns) + list(pattern.kwd_patterns):
                self._visit_match_pattern_references(child)
            return
        if isinstance(pattern, ast.MatchMapping):
            for key in pattern.keys:
                self.visit(key)
            for child in pattern.patterns:
                self._visit_match_pattern_references(child)
            return
        if isinstance(pattern, ast.MatchSequence):
            for child in pattern.patterns:
                self._visit_match_pattern_references(child)
            return
        if isinstance(pattern, ast.MatchOr):
            for child in pattern.patterns:
                self._visit_match_pattern_references(child)
            return
        if isinstance(pattern, ast.MatchAs) and pattern.pattern is not None:
            self._visit_match_pattern_references(pattern.pattern)

    def visit_ExceptHandler(self, node: ast.ExceptHandler) -> None:
        if node.type is not None:
            self.visit(node.type)
        if node.name:
            self._unbind_module_aliases({node.name})
        for statement in node.body:
            self.visit(statement)
        if node.name:
            self._unbind_module_aliases({node.name})

    def visit_Lambda(self, node: ast.Lambda) -> None:
        for default in node.args.defaults:
            self.visit(default)
        for default in node.args.kw_defaults:
            if default is not None:
                self.visit(default)

        bindings: set[str] = set()
        _collect_argument_names(node.args, bindings)
        hidden_class_scopes = self._hide_active_class_scopes()
        try:
            self._push_expression_shadow_scope(bindings)
            self._push_lazy_module_alias_scope()
            try:
                self.visit(node.body)
            finally:
                self._pop_lazy_module_alias_scope()
                self._pop_expression_shadow_scope()
        finally:
            self._restore_hidden_class_scopes(hidden_class_scopes)

    def visit_ListComp(self, node: ast.ListComp) -> None:
        self._visit_comprehension(node)

    def visit_SetComp(self, node: ast.SetComp) -> None:
        self._visit_comprehension(node)

    def visit_DictComp(self, node: ast.DictComp) -> None:
        self._visit_comprehension(node)

    def visit_GeneratorExp(self, node: ast.GeneratorExp) -> None:
        generators = list(node.generators)
        if generators:
            self.visit(generators[0].iter)

        bindings: set[str] = set()
        for generator in generators:
            _collect_target_bindings(generator.target, bindings)
        hidden_class_scopes = self._hide_active_class_scopes()
        try:
            self._push_expression_shadow_scope(bindings)
            self._push_lazy_module_alias_scope()
            try:
                for index, generator in enumerate(generators):
                    if index > 0:
                        self.visit(generator.iter)
                    for guard in generator.ifs:
                        self.visit(guard)
                self.visit(node.elt)
            finally:
                self._pop_lazy_module_alias_scope()
                self._pop_expression_shadow_scope()
        finally:
            self._restore_hidden_class_scopes(hidden_class_scopes)

    def _visit_comprehension(
        self,
        node: ast.ListComp | ast.SetComp | ast.DictComp | ast.GeneratorExp,
    ) -> None:
        generators = list(node.generators)
        if generators:
            self.visit(generators[0].iter)

        bindings: set[str] = set()
        for generator in generators:
            _collect_target_bindings(generator.target, bindings)
        hidden_class_scopes = self._hide_active_class_scopes()
        try:
            self._push_expression_shadow_scope(bindings)
            try:
                for index, generator in enumerate(generators):
                    if index > 0:
                        self.visit(generator.iter)
                    for guard in generator.ifs:
                        self.visit(guard)
                if isinstance(node, ast.DictComp):
                    self.visit(node.key)
                    self.visit(node.value)
                else:
                    self.visit(node.elt)
            finally:
                self._pop_expression_shadow_scope()
        finally:
            self._restore_hidden_class_scopes(hidden_class_scopes)

    def _push_expression_shadow_scope(self, bindings: set[str]) -> None:
        import_scope = bindings & self._known_imported_names
        module_scope = bindings & self._active_module_alias_names()
        self._shadowed_import_scopes.append(import_scope)
        self._expression_module_alias_shadow_scopes.append(module_scope)

    def _pop_expression_shadow_scope(self) -> None:
        self._expression_module_alias_shadow_scopes.pop()
        self._shadowed_import_scopes.pop()

    def _push_lazy_module_alias_scope(self) -> None:
        self._local_module_import_scopes.append({})
        self._local_module_alias_shadow_scopes.append(set())

    def _pop_lazy_module_alias_scope(self) -> None:
        self._local_module_alias_shadow_scopes.pop()
        self._local_module_import_scopes.pop()

    def _hide_active_class_scopes(self) -> list[_ClassScopeMarker]:
        hidden: list[_ClassScopeMarker] = []
        while self._class_scope_markers:
            marker = self._class_scope_markers[-1]
            (
                import_scope,
                module_scope,
                module_shadow_scope,
                value_scope,
                owner_scope,
            ) = marker
            if not (
                self._local_import_scopes
                and self._local_import_scopes[-1] is import_scope
                and self._local_module_import_scopes
                and self._local_module_import_scopes[-1] is module_scope
                and self._local_module_alias_shadow_scopes
                and self._local_module_alias_shadow_scopes[-1] is module_shadow_scope
                and self._local_value_scopes
                and self._local_value_scopes[-1] is value_scope
                and self._object_owner_scopes
                and self._object_owner_scopes[-1] is owner_scope
            ):
                break
            self._class_scope_markers.pop()
            self._object_owner_scopes.pop()
            self._local_value_scopes.pop()
            self._local_module_alias_shadow_scopes.pop()
            self._local_module_import_scopes.pop()
            self._local_import_scopes.pop()
            hidden.append(marker)
        return hidden

    def _restore_hidden_class_scopes(self, hidden: list[_ClassScopeMarker]) -> None:
        for marker in reversed(hidden):
            (
                import_scope,
                module_scope,
                module_shadow_scope,
                value_scope,
                owner_scope,
            ) = marker
            self._local_import_scopes.append(import_scope)
            self._local_module_import_scopes.append(module_scope)
            self._local_module_alias_shadow_scopes.append(module_shadow_scope)
            self._local_value_scopes.append(value_scope)
            self._object_owner_scopes.append(owner_scope)
            self._class_scope_markers.append(marker)

    def _resolve_attribute_chain(
        self, node: ast.Attribute
    ) -> Optional[tuple[str, str]]:
        """If the chain is rooted at an imported name, return (leaf, source).

        For ``pkg.mod.Foo`` after ``import pkg.mod``: ("Foo", "pkg.mod").
        For ``pm.Foo`` after ``import pkg.mod as pm``: ("Foo", "pkg.mod").
        Returns None when the root Name is not in the import map.
        """
        attrs: list[str] = []
        current: ast.expr = node
        while isinstance(current, ast.Attribute):
            attrs.append(current.attr)
            current = current.value
        if isinstance(current, ast.Name):
            if self._name_is_expression_module_alias_shadowed(current.id):
                return None
            namespace, shadowed = self._resolve_local_module_import(current.id)
            if namespace is None:
                if shadowed:
                    return None
                if self._name_is_lexically_shadowed_import(current.id):
                    return None
                if self._name_is_function_import_bound(current.id):
                    return None
                namespace = self._module_import_source_for_node(current.id, node)
                if namespace is None and current.id in self._module_shadowed_imports:
                    return None
        elif isinstance(current, ast.Call):
            namespace = self._literal_importlib_import_module_path(current)
        elif isinstance(current, ast.NamedExpr):
            namespace = self._literal_importlib_import_module_path(current.value)
        else:
            return None
        if namespace is None:
            return None
        attrs.reverse()  # outermost (leaf) is now last
        leaf = attrs[-1]
        middle = attrs[:-1]
        source = ".".join([namespace, *middle]) if middle else namespace
        return leaf, source

    def _keyword_import_identity_for_name(
        self, name: str
    ) -> Optional[tuple[Optional[str], str]]:
        if self._name_is_lexically_shadowed_import(name):
            return None
        local_import = self._resolve_local_imported_name(name)
        if local_import is not None:
            import_source, alias_of = local_import
            return import_source, alias_of or name
        if self._name_is_function_import_bound(name):
            return None
        if name in self._module_shadowed_imports:
            return None
        if name not in self._imported_names:
            return None
        import_source, alias_of = self._imported_names[name]
        return import_source, alias_of or name

    def visit_ClassDef(self, node: ast.ClassDef) -> None:
        self._visit_class_runtime_definition_expressions(node)
        self._unbind_module_aliases({node.name})
        self._local_value_scopes[-1].add(node.name)
        hidden_class_scopes = self._hide_active_class_scopes()
        is_top_level = self._function_depth == 0 and not self._class_stack
        self._class_stack.append(
            is_top_level and _is_pytest_discoverable_test_class(node)
        )
        class_import_scope: _ImportScope = {}
        class_module_scope: _ModuleImportScope = {}
        class_module_shadow_scope: _ModuleAliasShadowScope = set()
        class_value_scope: _LocalValueScope = set()
        class_owner_scope: _ObjectOwnerScope = {}
        class_scope_marker: _ClassScopeMarker = (
            class_import_scope,
            class_module_scope,
            class_module_shadow_scope,
            class_value_scope,
            class_owner_scope,
        )
        self._local_import_scopes.append(class_import_scope)
        self._local_module_import_scopes.append(class_module_scope)
        self._local_module_alias_shadow_scopes.append(class_module_shadow_scope)
        self._local_value_scopes.append(class_value_scope)
        self._object_owner_scopes.append(class_owner_scope)
        self._class_scope_markers.append(class_scope_marker)
        try:
            for statement in node.body:
                self.visit(statement)
        finally:
            self._class_scope_markers.pop()
            self._object_owner_scopes.pop()
            self._local_value_scopes.pop()
            self._local_module_alias_shadow_scopes.pop()
            self._local_module_import_scopes.pop()
            self._local_import_scopes.pop()
            self._class_stack.pop()
            self._restore_hidden_class_scopes(hidden_class_scopes)

    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
        self._visit_runtime_definition_expressions(node)
        self._unbind_module_aliases({node.name})
        self._local_value_scopes[-1].add(node.name)
        if self._is_pytest_discoverable_test_function(node.name):
            self._add_test_function(node.name, node.lineno)
            self._add_reference(node.name, reference_context="access")
        self._visit_function_body_without_class_scopes(node)

    def _visit_function_body_without_class_scopes(
        self,
        node: ast.FunctionDef | ast.AsyncFunctionDef,
    ) -> None:
        hidden_class_scopes = self._hide_active_class_scopes()
        try:
            self._visit_function_body_scope(node)
        finally:
            self._restore_hidden_class_scopes(hidden_class_scopes)

    def _visit_function_body_scope(
        self,
        node: ast.FunctionDef | ast.AsyncFunctionDef,
    ) -> None:
        self._push_function_shadow_scope(node)
        self._function_import_bound_scopes.append(
            _function_import_bound_names(node, self._known_imported_names)
        )
        self._local_import_scopes.append({})
        self._local_module_import_scopes.append({})
        self._local_module_alias_shadow_scopes.append(
            _function_module_alias_shadows(node, self._active_module_alias_names())
        )
        self._local_value_scopes.append(set())
        self._object_owner_scopes.append({})
        self._argument_name_scopes.append(_argument_names(node.args))
        self._function_depth += 1
        try:
            self._visit_function_body(node)
        finally:
            self._function_depth -= 1
            self._argument_name_scopes.pop()
            self._object_owner_scopes.pop()
            self._local_value_scopes.pop()
            self._local_module_alias_shadow_scopes.pop()
            self._local_module_import_scopes.pop()
            self._local_import_scopes.pop()
            self._function_import_bound_scopes.pop()
            self._shadowed_import_scopes.pop()

    def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> None:
        self._visit_runtime_definition_expressions(node)
        self._unbind_module_aliases({node.name})
        self._local_value_scopes[-1].add(node.name)
        if self._is_pytest_discoverable_test_function(node.name):
            self._add_test_function(node.name, node.lineno)
            self._add_reference(node.name, reference_context="access")
        self._visit_function_body_without_class_scopes(node)

    def _visit_runtime_definition_expressions(
        self,
        node: ast.FunctionDef | ast.AsyncFunctionDef,
    ) -> None:
        for decorator in node.decorator_list:
            self.visit(decorator)
        for default in node.args.defaults:
            self.visit(default)
        for default in node.args.kw_defaults:
            if default is not None:
                self.visit(default)

    def _visit_class_runtime_definition_expressions(self, node: ast.ClassDef) -> None:
        for decorator in node.decorator_list:
            self.visit(decorator)
        for base in node.bases:
            self.visit(base)
        for keyword in node.keywords:
            self.visit(keyword.value)

    def _visit_function_body(
        self,
        node: ast.FunctionDef | ast.AsyncFunctionDef,
    ) -> None:
        for statement in node.body:
            self.visit(statement)

    def _is_pytest_discoverable_test_function(self, name: str) -> bool:
        if not name.startswith("test_"):
            return False
        if self._function_depth > 0:
            return False
        if not self._class_stack:
            return True
        return len(self._class_stack) == 1 and self._class_stack[-1]

    def _add_test_function(self, name: str, line: int) -> None:
        if name in self._seen_test_funcs:
            return
        self._seen_test_funcs.add(name)
        self.artifacts.append(
            FoundArtifact(
                kind=ArtifactKind.TEST_FUNCTION,
                name=name,
                line=line,
            )
        )

    def _add_reference(
        self,
        name: str,
        *,
        of: Optional[str] = None,
        import_source: Optional[str] = None,
        alias_of: Optional[str] = None,
        reference_context: Optional[str] = None,
    ) -> None:
        key = (name, of, import_source, alias_of, reference_context)
        if key in self._seen:
            return
        self._seen.add(key)
        self.artifacts.append(
            FoundArtifact(
                kind=ArtifactKind.FUNCTION,  # Kind doesn't matter for behavioral
                name=name,
                of=of,
                import_source=import_source,
                alias_of=alias_of,
                reference_context=reference_context,
            )
        )

    def _add_bound_reference(
        self,
        name: str,
        *,
        reference_context: str,
    ) -> None:
        if self._name_is_lexically_shadowed_import(name):
            self._add_reference(name, reference_context="local")
            return
        local_import = self._resolve_local_imported_name(name)
        if local_import is not None:
            import_source, alias_of = local_import
        elif self._name_is_local_value(name) and name not in self._imported_names:
            self._add_reference(name, reference_context="local")
            return
        elif self._name_is_function_import_bound(name):
            self._add_reference(name, reference_context="local")
            return
        elif name in self._module_shadowed_imports:
            self._add_reference(name, reference_context="local")
            return
        else:
            import_source, alias_of = self._imported_names.get(name, (None, None))
        self._add_reference(
            name,
            import_source=import_source,
            alias_of=alias_of,
            reference_context=reference_context,
        )

    def _resolve_local_imported_name(
        self,
        name: str,
    ) -> Optional[tuple[Optional[str], Optional[str]]]:
        for scope in reversed(self._local_import_scopes):
            if name in scope:
                return scope[name]
        return None

    def _active_module_alias_names(self) -> set[str]:
        names = set(self._dynamic_module_aliases)
        for scope in self._local_module_import_scopes:
            names.update(scope)
        return names

    def _resolve_local_module_import(self, name: str) -> tuple[Optional[str], bool]:
        scopes = zip(
            self._local_module_import_scopes,
            self._local_module_alias_shadow_scopes,
        )
        for module_scope, shadow_scope in reversed(list(scopes)):
            if name in module_scope:
                return module_scope[name], False
            if name in shadow_scope:
                return None, True
        return None, False

    def _bind_module_aliases(
        self,
        names: set[str],
        module_path: str,
        *,
        position: Optional[tuple[int, int]] = None,
    ) -> None:
        if not names:
            return
        if self._local_module_import_scopes:
            scope = self._local_module_import_scopes[-1]
            for name in names:
                scope[name] = module_path
                if self._local_module_alias_shadow_scopes:
                    self._local_module_alias_shadow_scopes[-1].discard(name)
            return
        if not self._scanning_module_bindings:
            return
        for name in names:
            self._imported_names.pop(name, None)
            self._module_imports[name] = module_path
            self._dynamic_module_aliases.add(name)
            if position is not None:
                self._record_module_alias_event(name, module_path, position)
            self._module_shadowed_imports.discard(name)

    def _unbind_module_aliases(
        self,
        names: set[str],
        *,
        position: Optional[tuple[int, int]] = None,
    ) -> None:
        if not names:
            return
        if self._local_module_import_scopes:
            scope = self._local_module_import_scopes[-1]
            for name in names:
                scope.pop(name, None)
                if self._local_module_alias_shadow_scopes:
                    self._local_module_alias_shadow_scopes[-1].add(name)
            return
        if not self._scanning_module_bindings:
            return
        for name in names:
            had_module_alias = (
                name in self._module_imports or name in self._dynamic_module_aliases
            )
            self._module_imports.pop(name, None)
            self._dynamic_module_aliases.discard(name)
            if had_module_alias:
                self._record_module_alias_event(name, None, position)

    def _record_module_alias_event(
        self,
        name: str,
        source: Optional[str],
        position: Optional[tuple[int, int]],
    ) -> None:
        if position is None:
            return
        self._dynamic_module_alias_events.setdefault(name, []).append(
            (position, source)
        )

    def _literal_importlib_import_module_path(
        self,
        node: Optional[ast.AST],
    ) -> Optional[str]:
        if not isinstance(node, ast.Call):
            return None
        if not node.args:
            return None
        module_arg = node.args[0]
        if not (
            isinstance(module_arg, ast.Constant) and isinstance(module_arg.value, str)
        ):
            return None

        func = node.func
        if isinstance(func, ast.Attribute) and func.attr == "import_module":
            resolved = self._resolve_attribute_chain(func)
            if resolved == ("import_module", "importlib"):
                return module_arg.value
            return None
        if isinstance(func, ast.Name):
            identity = self._keyword_import_identity_for_name(func.id)
            if identity == ("importlib", "import_module"):
                return module_arg.value
        return None

    def _record_assignment_owner_bindings(
        self,
        targets: list[ast.expr],
        value: Optional[ast.AST],
    ) -> None:
        if not self._object_owner_scopes:
            return
        names: set[str] = set()
        for target in targets:
            _collect_target_bindings(target, names)
        if not names:
            return
        owner_identity = self._constructor_owner_identity(value)
        scope = self._object_owner_scopes[-1]
        for name in names:
            if owner_identity is None:
                scope.pop(name, None)
            else:
                scope[name] = owner_identity

    def _constructor_owner_identity(
        self,
        value: Optional[ast.AST],
    ) -> Optional[tuple[Optional[str], str]]:
        if not isinstance(value, ast.Call):
            return None
        func = value.func
        if isinstance(func, ast.Name):
            identity = self._keyword_import_identity_for_name(func.id)
            if identity is None:
                return None
            source, owner = identity
            if _looks_like_constructor_owner(owner):
                return source, owner
            return None
        if isinstance(func, ast.Attribute):
            resolved = self._resolve_attribute_chain(func)
            if resolved is not None:
                owner, source = resolved
                if _looks_like_constructor_owner(owner):
                    return source, owner
        return None

    def _object_owner_identity_for_member_access(
        self,
        node: ast.Attribute,
    ) -> Optional[tuple[Optional[str], str]]:
        value = node.value
        if isinstance(value, ast.Call):
            return self._constructor_owner_identity(value)
        if isinstance(value, ast.Name):
            return self._resolve_object_owner(value.id)
        return None

    def _resolve_object_owner(
        self,
        name: str,
    ) -> Optional[tuple[Optional[str], str]]:
        for scope in reversed(self._object_owner_scopes):
            if name in scope:
                return scope[name]
        return None

    def _assignment_value_is_local_value(self, value: Optional[ast.AST]) -> bool:
        if value is None:
            return False
        if isinstance(value, (ast.Lambda, ast.FunctionDef, ast.AsyncFunctionDef)):
            return True
        if isinstance(value, ast.Call):
            return self._call_root_is_local_value(value.func)
        return False

    def _call_root_is_local_value(self, func: ast.expr) -> bool:
        root = _callable_root_name(func)
        return (
            root is not None
            and _looks_like_local_constructor_owner(root)
            and self._name_is_local_value(root)
        )

    def _push_function_shadow_scope(
        self,
        node: ast.FunctionDef | ast.AsyncFunctionDef,
    ) -> None:
        self._shadowed_import_scopes.append(
            _function_shadowed_imports(node, self._known_imported_names)
        )

    def _name_is_shadowed_import(self, name: str) -> bool:
        return (
            name in self._module_shadowed_imports
            or self._name_is_function_import_bound(name)
            or any(name in scope for scope in self._shadowed_import_scopes)
        )

    def _name_is_lexically_shadowed_import(self, name: str) -> bool:
        return any(name in scope for scope in self._shadowed_import_scopes)

    def _name_is_expression_module_alias_shadowed(self, name: str) -> bool:
        return any(
            name in scope for scope in self._expression_module_alias_shadow_scopes
        )

    def _module_import_source_for_node(
        self,
        name: str,
        node: ast.AST,
    ) -> Optional[str]:
        node_position = _node_start_position(node)
        events = self._dynamic_module_alias_events.get(name, [])
        if self._function_depth == 0 and node_position is not None and events:
            source: Optional[str] = None
            for event_position, event_source in sorted(
                events, key=lambda event: event[0]
            ):
                if event_position > node_position:
                    break
                source = event_source
            return source
        return self._module_imports.get(name)

    def _name_is_function_import_bound(self, name: str) -> bool:
        return any(name in scope for scope in self._function_import_bound_scopes)

    def _name_is_local_value(self, name: str) -> bool:
        return any(name in scope for scope in self._local_value_scopes)

    def _name_is_argument(self, name: str) -> bool:
        return any(name in scope for scope in self._argument_name_scopes)

    def _attribute_root_is_shadowed(self, node: ast.Attribute) -> bool:
        root = _attribute_root_name(node)
        return root is not None and self._name_is_shadowed_import(root)

    def _attribute_root_is_local_value(self, node: ast.Attribute) -> bool:
        root = _attribute_root_name(node)
        return (
            root is not None
            and not self._name_is_argument(root)
            and self._name_is_local_value(root)
        )


def _attribute_root_name(node: ast.Attribute) -> Optional[str]:
    current: ast.AST = node
    while isinstance(current, ast.Attribute):
        current = current.value
    if isinstance(current, ast.Call):
        current = current.func
        while isinstance(current, ast.Attribute):
            current = current.value
    if isinstance(current, ast.Name):
        return current.id
    return None


def _callable_root_name(node: ast.expr) -> Optional[str]:
    current: ast.AST = node
    while isinstance(current, ast.Attribute):
        current = current.value
    if isinstance(current, ast.Name):
        return current.id
    return None


def _all_imported_bound_names(tree: ast.AST) -> set[str]:
    names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            for alias in node.names:
                if alias.name != "*":
                    names.add(alias.asname or alias.name)
                    names.add(alias.name)
        elif isinstance(node, ast.Import):
            for alias in node.names:
                names.add(alias.asname or alias.name.split(".", 1)[0])
    return names


def _module_statement_local_value_bindings(statement: ast.stmt) -> set[str]:
    if isinstance(statement, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
        return {statement.name}
    if isinstance(statement, ast.Assign):
        if isinstance(statement.value, ast.Lambda):
            bindings: set[str] = set()
            for target in statement.targets:
                _collect_target_bindings(target, bindings)
            return bindings
    if isinstance(statement, ast.AnnAssign) and isinstance(statement.value, ast.Lambda):
        bindings = set()
        _collect_target_bindings(statement.target, bindings)
        return bindings
    return set()


def _function_shadowed_imports(
    node: ast.FunctionDef | ast.AsyncFunctionDef,
    imported_names: set[str],
) -> set[str]:
    bindings: set[str] = set()
    _collect_argument_names(node.args, bindings)
    for statement in node.body:
        _collect_statement_bindings(statement, bindings)
    return bindings & imported_names


def _function_module_alias_shadows(
    node: ast.FunctionDef | ast.AsyncFunctionDef,
    module_alias_names: set[str],
) -> set[str]:
    bindings: set[str] = set()
    _collect_argument_names(node.args, bindings)
    for statement in node.body:
        _collect_statement_bindings(statement, bindings)
    return bindings & module_alias_names


def _argument_names(args: ast.arguments) -> set[str]:
    names: set[str] = set()
    _collect_argument_names(args, names)
    return names


def _module_member_import_source(
    source_module: Optional[str],
    imported_name: str,
) -> Optional[str]:
    if not source_module or not _looks_like_module_member_import(imported_name):
        return None
    return f"{source_module}.{imported_name}"


def _looks_like_module_member_import(name: str) -> bool:
    return bool(name) and (name[0].islower() or name.startswith("_"))


def _looks_like_constructor_owner(name: str) -> bool:
    return bool(name) and (name[0].isupper() or name.startswith("_"))


def _looks_like_local_constructor_owner(name: str) -> bool:
    return bool(name) and name[0].isupper()


def _function_import_bound_names(
    node: ast.FunctionDef | ast.AsyncFunctionDef,
    imported_names: set[str],
) -> set[str]:
    bindings: set[str] = set()
    for statement in node.body:
        _collect_import_statement_bindings(statement, bindings)
    return bindings & imported_names


def _collect_import_statement_bindings(node: ast.AST, bindings: set[str]) -> None:
    if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
        return
    if isinstance(node, ast.ImportFrom):
        for alias in node.names:
            if alias.name != "*":
                bindings.add(alias.asname or alias.name)
        return
    if isinstance(node, ast.Import):
        for alias in node.names:
            bindings.add(alias.asname or alias.name.split(".", 1)[0])
        return
    if isinstance(node, ast.match_case):
        for statement in node.body:
            _collect_import_statement_bindings(statement, bindings)
        return

    for child in ast.iter_child_nodes(node):
        if isinstance(child, (ast.stmt, ast.match_case)):
            _collect_import_statement_bindings(child, bindings)


def _collect_argument_names(args: ast.arguments, bindings: set[str]) -> None:
    for arg in list(args.posonlyargs) + list(args.args) + list(args.kwonlyargs):
        bindings.add(arg.arg)
    if args.vararg is not None:
        bindings.add(args.vararg.arg)
    if args.kwarg is not None:
        bindings.add(args.kwarg.arg)


def _collect_statement_bindings(statement: ast.stmt, bindings: set[str]) -> None:
    if isinstance(statement, (ast.FunctionDef, ast.AsyncFunctionDef)):
        bindings.add(statement.name)
        _collect_function_definition_expression_bindings(statement, bindings)
        return
    if isinstance(statement, ast.ClassDef):
        bindings.add(statement.name)
        _collect_class_definition_expression_bindings(statement, bindings)
        return
    if isinstance(statement, ast.Return):
        _collect_expression_bindings(statement.value, bindings)
        return
    if isinstance(statement, ast.Expr):
        _collect_expression_bindings(statement.value, bindings)
        return
    if isinstance(statement, ast.Assert):
        _collect_expression_bindings(statement.test, bindings)
        _collect_expression_bindings(statement.msg, bindings)
        return
    if isinstance(statement, ast.Assign):
        for target in statement.targets:
            _collect_target_bindings(target, bindings)
        _collect_expression_bindings(statement.value, bindings)
        return
    if isinstance(statement, (ast.AnnAssign, ast.AugAssign)):
        _collect_target_bindings(statement.target, bindings)
        _collect_expression_bindings(statement.value, bindings)
        return
    if isinstance(statement, ast.Delete):
        for target in statement.targets:
            _collect_target_bindings(target, bindings)
        return
    if isinstance(statement, (ast.For, ast.AsyncFor)):
        _collect_target_bindings(statement.target, bindings)
        _collect_expression_bindings(statement.iter, bindings)
        for child in statement.body + statement.orelse:
            _collect_statement_bindings(child, bindings)
        return
    if isinstance(statement, (ast.With, ast.AsyncWith)):
        for item in statement.items:
            _collect_expression_bindings(item.context_expr, bindings)
            if item.optional_vars is not None:
                _collect_target_bindings(item.optional_vars, bindings)
        for child in statement.body:
            _collect_statement_bindings(child, bindings)
        return
    if isinstance(statement, (ast.If, ast.While)):
        _collect_expression_bindings(statement.test, bindings)
        for child in statement.body + statement.orelse:
            _collect_statement_bindings(child, bindings)
        return
    if isinstance(statement, ast.Try):
        for child in statement.body + statement.orelse + statement.finalbody:
            _collect_statement_bindings(child, bindings)
        for handler in statement.handlers:
            if handler.name:
                bindings.add(handler.name)
            for child in handler.body:
                _collect_statement_bindings(child, bindings)
        return
    if isinstance(statement, ast.Match):
        _collect_expression_bindings(statement.subject, bindings)
        for case in statement.cases:
            _collect_pattern_bindings(case.pattern, bindings)
            _collect_expression_bindings(case.guard, bindings)
            for child in case.body:
                _collect_statement_bindings(child, bindings)


def _collect_function_definition_expression_bindings(
    node: ast.FunctionDef | ast.AsyncFunctionDef,
    bindings: set[str],
) -> None:
    for decorator in node.decorator_list:
        _collect_expression_bindings(decorator, bindings)
    for default in list(node.args.defaults) + list(node.args.kw_defaults):
        _collect_expression_bindings(default, bindings)


def _collect_class_definition_expression_bindings(
    node: ast.ClassDef,
    bindings: set[str],
) -> None:
    for decorator in node.decorator_list:
        _collect_expression_bindings(decorator, bindings)
    for base in node.bases:
        _collect_expression_bindings(base, bindings)
    for keyword in node.keywords:
        _collect_expression_bindings(keyword.value, bindings)


def _collect_target_bindings(target: ast.expr, bindings: set[str]) -> None:
    if isinstance(target, ast.Name):
        bindings.add(target.id)
        return
    if isinstance(target, ast.Starred):
        _collect_target_bindings(target.value, bindings)
        return
    if isinstance(target, (ast.Tuple, ast.List)):
        for element in target.elts:
            _collect_target_bindings(element, bindings)


def _direct_name_targets(targets: list[ast.expr]) -> set[str]:
    return {target.id for target in targets if isinstance(target, ast.Name)}


def _node_start_position(node: Optional[ast.AST]) -> Optional[tuple[int, int]]:
    if node is None:
        return None
    line = getattr(node, "lineno", None)
    if line is None:
        return None
    column = getattr(node, "col_offset", None)
    return line, column if column is not None else 0


def _node_end_position(node: Optional[ast.AST]) -> Optional[tuple[int, int]]:
    if node is None:
        return None
    line = getattr(node, "end_lineno", None) or getattr(node, "lineno", None)
    if line is None:
        return None
    column = getattr(node, "end_col_offset", None)
    if column is None:
        column = getattr(node, "col_offset", 0)
    return line, column


def _binding_position(
    value: Optional[ast.AST],
    targets: list[ast.expr],
) -> Optional[tuple[int, int]]:
    value_position = _node_end_position(value)
    if value_position is not None:
        return value_position
    for target in targets:
        target_position = _node_end_position(target)
        if target_position is not None:
            return target_position
    return None


def _reachable_conditional_statements(
    test: ast.AST,
    body: list[ast.stmt],
    orelse: list[ast.stmt],
) -> list[ast.stmt]:
    truth = _static_truth_value(test)
    if truth is True:
        return body
    if truth is False:
        return orelse
    return body + orelse


def _reachable_conditional_expressions(
    test: ast.AST,
    body: ast.expr,
    orelse: ast.expr,
) -> list[ast.expr]:
    truth = _static_truth_value(test)
    if truth is True:
        return [body]
    if truth is False:
        return [orelse]
    return [body, orelse]


def _static_truth_value(expr: ast.AST) -> Optional[bool]:
    if isinstance(expr, ast.Constant):
        return bool(expr.value)
    if isinstance(expr, ast.UnaryOp) and isinstance(expr.op, ast.Not):
        truth = _static_truth_value(expr.operand)
        if truth is not None:
            return not truth
        return None
    if isinstance(expr, ast.BoolOp):
        if isinstance(expr.op, ast.And):
            result: Optional[bool] = True
            for value in expr.values:
                truth = _static_truth_value(value)
                if truth is False:
                    return False
                if truth is None:
                    result = None
            return result
        if isinstance(expr.op, ast.Or):
            result = False
            for value in expr.values:
                truth = _static_truth_value(value)
                if truth is True:
                    return True
                if truth is None:
                    result = None
            return result
    if isinstance(expr, (ast.Tuple, ast.List, ast.Set)):
        return bool(expr.elts)
    if isinstance(expr, ast.Dict):
        return bool(expr.keys)
    return None


def _collect_expression_bindings(expr: Optional[ast.AST], bindings: set[str]) -> None:
    if expr is None:
        return
    if isinstance(expr, ast.NamedExpr):
        _collect_target_bindings(expr.target, bindings)
        _collect_expression_bindings(expr.value, bindings)
        return
    if isinstance(expr, ast.Lambda):
        for default in expr.args.defaults:
            _collect_expression_bindings(default, bindings)
        for default in expr.args.kw_defaults:
            _collect_expression_bindings(default, bindings)
        return
    if isinstance(expr, ast.DictComp):
        _collect_comprehension_expression_bindings(expr, bindings)
        _collect_expression_bindings(expr.key, bindings)
        _collect_expression_bindings(expr.value, bindings)
        return
    if isinstance(expr, (ast.ListComp, ast.SetComp)):
        _collect_comprehension_expression_bindings(expr, bindings)
        _collect_expression_bindings(expr.elt, bindings)
        return
    if isinstance(expr, ast.GeneratorExp):
        _collect_comprehension_expression_bindings(expr, bindings)
        _collect_expression_bindings(expr.elt, bindings)
        return
    for child in ast.iter_child_nodes(expr):
        if isinstance(child, ast.AST):
            _collect_expression_bindings(child, bindings)


def _collect_comprehension_expression_bindings(
    expr: ast.ListComp | ast.SetComp | ast.DictComp | ast.GeneratorExp,
    bindings: set[str],
) -> None:
    for generator in expr.generators:
        _collect_expression_bindings(generator.iter, bindings)
        for guard in generator.ifs:
            _collect_expression_bindings(guard, bindings)


def _collect_pattern_bindings(pattern: ast.pattern, bindings: set[str]) -> None:
    if isinstance(pattern, ast.MatchAs):
        if pattern.name:
            bindings.add(pattern.name)
        if pattern.pattern is not None:
            _collect_pattern_bindings(pattern.pattern, bindings)
        return
    if isinstance(pattern, ast.MatchStar):
        if pattern.name:
            bindings.add(pattern.name)
        return
    if isinstance(pattern, ast.MatchMapping):
        if pattern.rest:
            bindings.add(pattern.rest)
        for child in pattern.patterns:
            _collect_pattern_bindings(child, bindings)
        return
    if isinstance(pattern, ast.MatchClass):
        for child in list(pattern.patterns) + list(pattern.kwd_patterns):
            _collect_pattern_bindings(child, bindings)
        return
    if isinstance(pattern, (ast.MatchSequence, ast.MatchOr)):
        for child in pattern.patterns:
            _collect_pattern_bindings(child, bindings)


def _is_stub_body(node: ast.FunctionDef | ast.AsyncFunctionDef) -> bool:
    return _python_is_stub_body(node)


def _is_pytest_discoverable_test_class(node: ast.ClassDef) -> bool:
    """Return True when pytest would discover tests inside this class."""
    if not node.name.startswith("Test"):
        return False
    return not any(
        isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef))
        and child.name == "__init__"
        for child in node.body
    )


def _extract_args(
    node: ast.FunctionDef | ast.AsyncFunctionDef,
    is_method: bool,
) -> tuple[ArgSpec, ...]:
    return _python_extract_args(node, is_method)


def _get_return_type(node: ast.FunctionDef | ast.AsyncFunctionDef) -> Optional[str]:
    return _python_get_return_type(node)


def _has_property_decorator(node: ast.FunctionDef | ast.AsyncFunctionDef) -> bool:
    return _python_has_property_decorator(node)


def _extract_base_name(base: ast.expr) -> Optional[str]:
    return _python_extract_base_name(base)


def _ast_to_type_string(node: Optional[ast.AST]) -> Optional[str]:
    return _python_ast_to_type_string(node)


def _ast_to_default_string(node: Optional[ast.expr]) -> Optional[str]:
    return _python_ast_to_default_string(node)


def _slice_node_text(node: ast.AST, lines: list[str]) -> Optional[str]:
    start = getattr(node, "lineno", None)
    end = getattr(node, "end_lineno", None)
    if start is None or end is None:
        return None
    return "".join(lines[start - 1 : end])


def _walk_for_test_bodies(
    node: ast.AST,
    lines: list[str],
    bodies: dict[str, str],
    in_test_class: bool,
) -> None:
    """Collect bodies of top-level and Test*-class ``test_*`` functions.

    Nested helper defs named ``test_*`` are intentionally skipped — they
    aren't pytest-discoverable and would pollute the body map.
    """
    for child in ast.iter_child_nodes(node):
        if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef)):
            if not child.name.startswith("test_"):
                continue
            # Accept module-level test_* funcs and methods of test classes.
            if (isinstance(node, ast.Module) and not in_test_class) or (
                isinstance(node, ast.ClassDef) and in_test_class
            ):
                text = _slice_node_text(child, lines)
                if text is not None:
                    bodies.setdefault(child.name, text)
            continue
        if isinstance(child, ast.ClassDef):
            if isinstance(node, ast.Module) and _is_pytest_discoverable_test_class(
                child
            ):
                _walk_for_test_bodies(child, lines, bodies, in_test_class=True)
            continue
        _walk_for_test_bodies(child, lines, bodies, in_test_class=in_test_class)
