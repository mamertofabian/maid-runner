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
        self._importer_module: Optional[str] = (
            file_to_module_path(file_path, Path(".")) if file_path else None
        ) or None
        # Maps a bound name to the namespace that name refers to. Populated
        # only by plain `import pkg.mod` / `import pkg.mod as pm` so that
        # attribute chains rooted at the bound name (e.g. ``pkg.mod.Foo``)
        # can resolve the leaf reference's import_source.
        self._module_imports: dict[str, str] = {}
        self._imported_names: dict[str, tuple[Optional[str], Optional[str]]] = {}
        self._known_imported_names: set[str] = set()
        self._module_shadowed_imports: set[str] = set()
        self._local_import_scopes: list[
            dict[str, tuple[Optional[str], Optional[str]]]
        ] = []
        self._local_module_import_scopes: list[dict[str, str]] = []
        self._shadowed_import_scopes: list[set[str]] = []
        self._function_import_bound_scopes: list[set[str]] = []

    def scan_imports(self, tree: ast.AST) -> None:
        self._known_imported_names = _all_imported_bound_names(tree)
        self._module_imports.clear()
        self._imported_names.clear()
        self._module_shadowed_imports.clear()

        if not isinstance(tree, ast.Module):
            return
        for statement in tree.body:
            self._apply_module_statement_binding(statement)

    def _apply_module_statement_binding(self, statement: ast.stmt) -> None:
        if isinstance(statement, ast.ImportFrom):
            for bound, source_module, alias_of in self._import_from_entries(statement):
                self._bind_imported_name(bound, source_module, alias_of)
            return
        if isinstance(statement, ast.Import):
            for bound, source_module, alias_of, namespace_root in self._import_entries(
                statement
            ):
                self._bind_imported_name(
                    bound,
                    source_module,
                    alias_of,
                    namespace_root=namespace_root,
                )
            return

        if isinstance(statement, ast.Try):
            for child in statement.body:
                self._apply_module_statement_binding(child)
            for handler in statement.handlers:
                if handler.name:
                    self._unbind_imported_name(handler.name)
                for child in handler.body:
                    self._apply_module_statement_binding(child)
            for child in statement.orelse + statement.finalbody:
                self._apply_module_statement_binding(child)
            return

        if isinstance(statement, (ast.If, ast.While)):
            for child in statement.body + statement.orelse:
                self._apply_module_statement_binding(child)
            return

        if isinstance(statement, (ast.For, ast.AsyncFor)):
            bindings: set[str] = set()
            _collect_target_bindings(statement.target, bindings)
            for name in bindings:
                self._unbind_imported_name(name)
            for child in statement.body + statement.orelse:
                self._apply_module_statement_binding(child)
            return

        if isinstance(statement, (ast.With, ast.AsyncWith)):
            bindings: set[str] = set()
            for item in statement.items:
                if item.optional_vars is not None:
                    _collect_target_bindings(item.optional_vars, bindings)
            for name in bindings:
                self._unbind_imported_name(name)
            for child in statement.body:
                self._apply_module_statement_binding(child)
            return

        bindings: set[str] = set()
        _collect_statement_bindings(statement, bindings)
        for name in bindings & self._known_imported_names:
            self._unbind_imported_name(name)

    def _bind_imported_name(
        self,
        bound: str,
        source_module: Optional[str],
        alias_of: Optional[str],
        *,
        namespace_root: Optional[str] = None,
    ) -> None:
        self._imported_names[bound] = (source_module, alias_of)
        if namespace_root is None:
            self._module_imports.pop(bound, None)
        else:
            self._module_imports[bound] = namespace_root
        self._module_shadowed_imports.discard(bound)

    def _unbind_imported_name(self, name: str) -> None:
        self._imported_names.pop(name, None)
        self._module_imports.pop(name, None)
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
                self._local_module_import_scopes[-1].pop(bound, None)
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
                    "local" if self._attribute_root_is_shadowed(node.func) else "call"
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
        resolved = self._resolve_attribute_chain(node)
        if resolved is not None:
            leaf, source = resolved
            self._add_reference(
                leaf,
                import_source=source,
                reference_context="access",
            )
        else:
            context = "local" if self._attribute_root_is_shadowed(node) else "access"
            self._add_reference(node.attr, reference_context=context)
        self.generic_visit(node)

    def visit_arg(self, node: ast.arg) -> None:
        return None

    def visit_AnnAssign(self, node: ast.AnnAssign) -> None:
        self.visit(node.target)
        if node.value is not None:
            self.visit(node.value)

    def visit_Lambda(self, node: ast.Lambda) -> None:
        bindings: set[str] = set()
        _collect_argument_names(node.args, bindings)
        self._visit_with_expression_shadow_scope(node, bindings)

    def visit_ListComp(self, node: ast.ListComp) -> None:
        self._visit_comprehension(node)

    def visit_SetComp(self, node: ast.SetComp) -> None:
        self._visit_comprehension(node)

    def visit_DictComp(self, node: ast.DictComp) -> None:
        self._visit_comprehension(node)

    def visit_GeneratorExp(self, node: ast.GeneratorExp) -> None:
        self._visit_comprehension(node)

    def _visit_comprehension(
        self,
        node: ast.ListComp | ast.SetComp | ast.DictComp | ast.GeneratorExp,
    ) -> None:
        bindings: set[str] = set()
        for generator in node.generators:
            _collect_target_bindings(generator.target, bindings)
        self._visit_with_expression_shadow_scope(node, bindings)

    def _visit_with_expression_shadow_scope(
        self,
        node: ast.AST,
        bindings: set[str],
    ) -> None:
        scope = bindings & self._known_imported_names
        self._shadowed_import_scopes.append(scope)
        try:
            self.generic_visit(node)
        finally:
            self._shadowed_import_scopes.pop()

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
        if not isinstance(current, ast.Name):
            return None
        if self._name_is_lexically_shadowed_import(current.id):
            return None
        namespace = self._resolve_local_module_import(current.id)
        if namespace is None:
            if self._name_is_function_import_bound(current.id):
                return None
            if current.id in self._module_shadowed_imports:
                return None
            namespace = self._module_imports.get(current.id)
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
        is_top_level = self._function_depth == 0 and not self._class_stack
        self._class_stack.append(
            is_top_level and _is_pytest_discoverable_test_class(node)
        )
        self.generic_visit(node)
        self._class_stack.pop()

    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
        if self._is_pytest_discoverable_test_function(node.name):
            self._add_test_function(node.name, node.lineno)
            self._add_reference(node.name, reference_context="access")
        self._visit_runtime_definition_expressions(node)
        self._push_function_shadow_scope(node)
        self._function_import_bound_scopes.append(
            _function_import_bound_names(node, self._known_imported_names)
        )
        self._local_import_scopes.append({})
        self._local_module_import_scopes.append({})
        self._function_depth += 1
        try:
            self._visit_function_body(node)
        finally:
            self._function_depth -= 1
            self._local_module_import_scopes.pop()
            self._local_import_scopes.pop()
            self._function_import_bound_scopes.pop()
            self._shadowed_import_scopes.pop()

    def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> None:
        if self._is_pytest_discoverable_test_function(node.name):
            self._add_test_function(node.name, node.lineno)
            self._add_reference(node.name, reference_context="access")
        self._visit_runtime_definition_expressions(node)
        self._push_function_shadow_scope(node)
        self._function_import_bound_scopes.append(
            _function_import_bound_names(node, self._known_imported_names)
        )
        self._local_import_scopes.append({})
        self._local_module_import_scopes.append({})
        self._function_depth += 1
        try:
            self._visit_function_body(node)
        finally:
            self._function_depth -= 1
            self._local_module_import_scopes.pop()
            self._local_import_scopes.pop()
            self._function_import_bound_scopes.pop()
            self._shadowed_import_scopes.pop()

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

    def _resolve_local_module_import(self, name: str) -> Optional[str]:
        for scope in reversed(self._local_module_import_scopes):
            if name in scope:
                return scope[name]
        return None

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

    def _name_is_function_import_bound(self, name: str) -> bool:
        return any(name in scope for scope in self._function_import_bound_scopes)

    def _attribute_root_is_shadowed(self, node: ast.Attribute) -> bool:
        current: ast.expr = node
        while isinstance(current, ast.Attribute):
            current = current.value
        return isinstance(current, ast.Name) and self._name_is_shadowed_import(
            current.id
        )


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


def _function_shadowed_imports(
    node: ast.FunctionDef | ast.AsyncFunctionDef,
    imported_names: set[str],
) -> set[str]:
    bindings: set[str] = set()
    _collect_argument_names(node.args, bindings)
    for statement in node.body:
        _collect_statement_bindings(statement, bindings)
    return bindings & imported_names


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
    if isinstance(statement, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
        bindings.add(statement.name)
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


def _collect_expression_bindings(expr: Optional[ast.AST], bindings: set[str]) -> None:
    if expr is None:
        return
    if isinstance(expr, ast.NamedExpr):
        _collect_target_bindings(expr.target, bindings)
        _collect_expression_bindings(expr.value, bindings)
        return
    if isinstance(expr, ast.Lambda):
        return
    for child in ast.iter_child_nodes(expr):
        if isinstance(child, ast.expr):
            _collect_expression_bindings(child, bindings)


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
