"""Python language validator for MAID Runner v2.

Collects artifact definitions and references from Python source code using AST.
"""

from __future__ import annotations

import ast
from dataclasses import replace
from pathlib import Path
from typing import Optional, Union

from maid_runner.core.module_paths import (
    file_to_module_path,
    resolve_relative_import,
)
from maid_runner.core.types import ArtifactKind, ArgSpec
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

        collector = _ImplementationCollector(file_path=str(file_path))
        collector.visit(tree)

        return CollectionResult(
            artifacts=collector.artifacts,
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


class _ImplementationCollector(ast.NodeVisitor):
    def __init__(self, file_path: str = "") -> None:
        self.artifacts: list[FoundArtifact] = []
        self._current_class: Optional[str] = None
        self._in_function: bool = False
        self._is_init = Path(file_path).name == "__init__.py"
        self._module_path: Optional[str] = (
            file_to_module_path(file_path, Path(".")) if file_path else None
        ) or None

    def _add(self, artifact: FoundArtifact) -> None:
        if self._module_path and artifact.module_path is None:
            artifact = _with_module_path(artifact, self._module_path)
        self.artifacts.append(artifact)

    def visit_ClassDef(self, node: ast.ClassDef) -> None:
        base_names = [_extract_base_name(b) for b in node.bases]
        bases = tuple(name for name in base_names if name is not None)

        self._add(
            FoundArtifact(
                kind=ArtifactKind.CLASS,
                name=node.name,
                bases=bases,
                line=node.lineno,
                column=node.col_offset,
            )
        )

        # Visit class body
        prev_class = self._current_class
        self._current_class = node.name
        for child in node.body:
            self.visit(child)
        self._current_class = prev_class

    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
        self._handle_function(node, is_async=False)

    def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> None:
        self._handle_function(node, is_async=True)

    def _handle_function(
        self, node: ast.FunctionDef | ast.AsyncFunctionDef, is_async: bool
    ) -> None:
        stub = _is_stub_body(node)

        if self._current_class is not None:
            # Inside a class
            if _has_property_decorator(node):
                # Property -> treat as attribute
                self._add(
                    FoundArtifact(
                        kind=ArtifactKind.ATTRIBUTE,
                        name=node.name,
                        of=self._current_class,
                        type_annotation=_get_return_type(node),
                        line=node.lineno,
                        column=node.col_offset,
                    )
                )
            else:
                # Method
                args = _extract_args(node, is_method=True)
                self._add(
                    FoundArtifact(
                        kind=ArtifactKind.METHOD,
                        name=node.name,
                        of=self._current_class,
                        args=args,
                        returns=_get_return_type(node),
                        is_async=is_async,
                        is_stub=stub,
                        line=node.lineno,
                        column=node.col_offset,
                    )
                )

            # Visit method body for self.attr assignments
            prev_in_function = self._in_function
            self._in_function = True
            self.generic_visit(node)
            self._in_function = prev_in_function
        else:
            # Module-level function
            args = _extract_args(node, is_method=False)
            self._add(
                FoundArtifact(
                    kind=ArtifactKind.FUNCTION,
                    name=node.name,
                    args=args,
                    returns=_get_return_type(node),
                    is_async=is_async,
                    is_stub=stub,
                    line=node.lineno,
                    column=node.col_offset,
                )
            )

    def visit_Assign(self, node: ast.Assign) -> None:
        if self._current_class is not None and self._in_function:
            # self.attr = ... inside a method
            for target in node.targets:
                if (
                    isinstance(target, ast.Attribute)
                    and isinstance(target.value, ast.Name)
                    and target.value.id == "self"
                ):
                    attr_name = target.attr
                    if not self._has_artifact(attr_name, self._current_class):
                        self._add(
                            FoundArtifact(
                                kind=ArtifactKind.ATTRIBUTE,
                                name=attr_name,
                                of=self._current_class,
                                line=node.lineno,
                            )
                        )
        elif self._current_class is not None and not self._in_function:
            # Class-level assignment (enum members, class constants)
            for target in node.targets:
                if isinstance(target, ast.Name):
                    if not self._has_artifact(target.id, self._current_class):
                        self._add(
                            FoundArtifact(
                                kind=ArtifactKind.ATTRIBUTE,
                                name=target.id,
                                of=self._current_class,
                                line=node.lineno,
                            )
                        )
        elif self._current_class is None and not self._in_function:
            # Module-level assignment
            for target in node.targets:
                if isinstance(target, ast.Name):
                    self._add(
                        FoundArtifact(
                            kind=ArtifactKind.ATTRIBUTE,
                            name=target.id,
                            line=node.lineno,
                        )
                    )
                elif isinstance(target, ast.Tuple):
                    for elt in target.elts:
                        if isinstance(elt, ast.Name):
                            self._add(
                                FoundArtifact(
                                    kind=ArtifactKind.ATTRIBUTE,
                                    name=elt.id,
                                    line=node.lineno,
                                )
                            )

    def visit_AnnAssign(self, node: ast.AnnAssign) -> None:
        if not node.target:
            return

        type_ann = _ast_to_type_string(node.annotation) if node.annotation else None

        if isinstance(node.target, ast.Name):
            if self._current_class is not None and not self._in_function:
                # Class-level annotated attribute: field: type
                self._add(
                    FoundArtifact(
                        kind=ArtifactKind.ATTRIBUTE,
                        name=node.target.id,
                        of=self._current_class,
                        type_annotation=type_ann,
                        line=node.lineno,
                    )
                )
            elif self._current_class is None and not self._in_function:
                # Module-level annotated attribute
                self._add(
                    FoundArtifact(
                        kind=ArtifactKind.ATTRIBUTE,
                        name=node.target.id,
                        type_annotation=type_ann,
                        line=node.lineno,
                    )
                )
        elif (
            isinstance(node.target, ast.Attribute)
            and isinstance(node.target.value, ast.Name)
            and node.target.value.id == "self"
            and self._current_class is not None
            and self._in_function
        ):
            # Annotated self attribute inside method: self.name: str = value
            attr_name = node.target.attr
            if not self._has_artifact(attr_name, self._current_class):
                self._add(
                    FoundArtifact(
                        kind=ArtifactKind.ATTRIBUTE,
                        name=attr_name,
                        of=self._current_class,
                        type_annotation=type_ann,
                        line=node.lineno,
                    )
                )

    def visit_ImportFrom(self, node: ast.ImportFrom) -> None:
        # Only collect re-exports in __init__.py files at module level.
        # Regular files import for USE, not re-export.
        if not self._is_init:
            return
        if self._current_class is not None:
            return
        if node.names:
            for alias in node.names:
                if alias.name == "*":
                    continue
                name = alias.asname or alias.name
                if name.isupper():
                    kind = ArtifactKind.ATTRIBUTE
                elif name[0].isupper():
                    kind = ArtifactKind.CLASS
                else:
                    kind = ArtifactKind.FUNCTION
                self._add(
                    FoundArtifact(
                        kind=kind,
                        name=name,
                        line=node.lineno,
                        column=node.col_offset,
                    )
                )

    def _has_artifact(self, name: str, of: Optional[str]) -> bool:
        return any(a.name == name and a.of == of for a in self.artifacts)


class _BehavioralCollector(ast.NodeVisitor):
    """Collect artifact references (imports, calls, attribute access)."""

    def __init__(self, file_path: str = "") -> None:
        self.artifacts: list[FoundArtifact] = []
        self._seen: set[str] = set()
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

    def visit_ImportFrom(self, node: ast.ImportFrom) -> None:
        if node.names:
            level = node.level or 0
            if level > 0 and self._importer_module:
                source_module = resolve_relative_import(
                    node.module, level, self._importer_module
                )
            else:
                source_module = node.module or ""
            for alias in node.names:
                if alias.name == "*":
                    continue
                bound = alias.asname or alias.name
                alias_of = alias.name if alias.asname else None
                self._add_reference(
                    bound,
                    import_source=source_module or None,
                    alias_of=alias_of,
                )
        self.generic_visit(node)

    def visit_Import(self, node: ast.Import) -> None:
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
            self._module_imports[bound] = namespace_root
            self._add_reference(bound, import_source=alias.name, alias_of=alias_of)
        self.generic_visit(node)

    def visit_Call(self, node: ast.Call) -> None:
        if isinstance(node.func, ast.Name):
            self._add_reference(node.func.id)
        elif isinstance(node.func, ast.Attribute):
            resolved = self._resolve_attribute_chain(node.func)
            if resolved is not None:
                leaf, source = resolved
                self._add_reference(leaf, import_source=source)
            else:
                self._add_reference(node.func.attr)
        for kw in node.keywords:
            if kw.arg is not None:  # **kwargs has arg=None
                self._add_reference(kw.arg)
        self.generic_visit(node)

    def visit_Name(self, node: ast.Name) -> None:
        self._add_reference(node.id)
        self.generic_visit(node)

    def visit_Attribute(self, node: ast.Attribute) -> None:
        resolved = self._resolve_attribute_chain(node)
        if resolved is not None:
            leaf, source = resolved
            self._add_reference(leaf, import_source=source)
        else:
            self._add_reference(node.attr)
        self.generic_visit(node)

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
        namespace = self._module_imports.get(current.id)
        if namespace is None:
            return None
        attrs.reverse()  # outermost (leaf) is now last
        leaf = attrs[-1]
        middle = attrs[:-1]
        source = ".".join([namespace, *middle]) if middle else namespace
        return leaf, source

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
            self._add_reference(node.name)
        self._function_depth += 1
        self.generic_visit(node)
        self._function_depth -= 1

    def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> None:
        if self._is_pytest_discoverable_test_function(node.name):
            self._add_test_function(node.name, node.lineno)
            self._add_reference(node.name)
        self._function_depth += 1
        self.generic_visit(node)
        self._function_depth -= 1

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
        import_source: Optional[str] = None,
        alias_of: Optional[str] = None,
    ) -> None:
        if name in self._seen:
            return
        self._seen.add(name)
        self.artifacts.append(
            FoundArtifact(
                kind=ArtifactKind.FUNCTION,  # Kind doesn't matter for behavioral
                name=name,
                import_source=import_source,
                alias_of=alias_of,
            )
        )


def _with_module_path(artifact: FoundArtifact, module_path: str) -> FoundArtifact:
    return replace(artifact, module_path=module_path)


def _is_stub_body(node: ast.FunctionDef | ast.AsyncFunctionDef) -> bool:
    """Check if a function body is a stub (no real implementation).

    Detects: pass, ..., raise NotImplementedError, single return with literal,
    or empty body after docstring.
    """
    body = node.body[:]

    # Strip leading docstring
    if (
        body
        and isinstance(body[0], ast.Expr)
        and isinstance(body[0].value, ast.Constant)
        and isinstance(body[0].value.value, str)
    ):
        body = body[1:]

    if not body:
        return True  # empty body after docstring

    if len(body) != 1:
        return False  # multiple statements = likely real code

    stmt = body[0]

    # pass
    if isinstance(stmt, ast.Pass):
        return True

    # ... (Ellipsis)
    if (
        isinstance(stmt, ast.Expr)
        and isinstance(stmt.value, ast.Constant)
        and stmt.value.value is ...
    ):
        return True

    # raise NotImplementedError(...)
    if isinstance(stmt, ast.Raise) and stmt.exc is not None:
        exc = stmt.exc
        if isinstance(exc, ast.Call) and isinstance(exc.func, ast.Name):
            if exc.func.id == "NotImplementedError":
                return True
        elif isinstance(exc, ast.Name) and exc.id == "NotImplementedError":
            return True

    # return <literal> (None, 0, "", False, {}, [], ())
    if isinstance(stmt, ast.Return):
        if stmt.value is None:
            return True
        if isinstance(stmt.value, ast.Constant):
            return True
        # return {} / return [] / return ()
        if isinstance(stmt.value, ast.Dict) and not stmt.value.keys:
            return True
        if isinstance(stmt.value, ast.List) and not stmt.value.elts:
            return True
        if isinstance(stmt.value, ast.Tuple) and not stmt.value.elts:
            return True

    return False


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
    args = node.args
    all_args = list(args.args)

    # Filter self/cls for methods
    if is_method and all_args:
        first_arg_name = all_args[0].arg
        if first_arg_name in ("self", "cls"):
            all_args = all_args[1:]

    # Calculate defaults alignment
    # Defaults align to the right of the args list
    num_args = len(all_args)
    defaults = list(args.defaults)
    num_defaults = len(defaults)
    padded_defaults: list[Optional[ast.expr]] = [None] * (
        num_args - num_defaults
    ) + defaults

    result: list[ArgSpec] = []
    for i, arg in enumerate(all_args):
        type_ann = _ast_to_type_string(arg.annotation) if arg.annotation else None
        default_val = None
        if padded_defaults[i] is not None:
            default_val = _ast_to_default_string(padded_defaults[i])
        result.append(ArgSpec(name=arg.arg, type=type_ann, default=default_val))

    return tuple(result)


def _get_return_type(node: ast.FunctionDef | ast.AsyncFunctionDef) -> Optional[str]:
    if node.returns:
        return _ast_to_type_string(node.returns)
    return None


def _has_property_decorator(node: ast.FunctionDef | ast.AsyncFunctionDef) -> bool:
    for decorator in node.decorator_list:
        if isinstance(decorator, ast.Name) and decorator.id == "property":
            return True
    return False


def _extract_base_name(base: ast.expr) -> Optional[str]:
    if isinstance(base, ast.Name):
        return base.id
    elif isinstance(base, ast.Attribute):
        return _ast_to_type_string(base)
    elif isinstance(base, ast.Subscript):
        # Generic[T] -> "Generic"
        if isinstance(base.value, ast.Name):
            return base.value.id
        return _ast_to_type_string(base.value)
    return None


def _ast_to_type_string(node: Optional[ast.AST]) -> Optional[str]:
    if node is None:
        return None
    try:
        if isinstance(node, ast.Name):
            return node.id
        if isinstance(node, ast.Constant):
            return str(node.value)
        if isinstance(node, ast.Subscript):
            base = _ast_to_type_string(node.value)
            if isinstance(node.slice, ast.Tuple):
                args = [_ast_to_type_string(elt) for elt in node.slice.elts]
                return f"{base}[{', '.join(str(a) for a in args)}]"
            else:
                arg = _ast_to_type_string(node.slice)
                return f"{base}[{arg}]"
        if isinstance(node, ast.Attribute):
            value = _ast_to_type_string(node.value)
            return f"{value}.{node.attr}"
        if isinstance(node, ast.BinOp) and isinstance(node.op, ast.BitOr):
            left = _ast_to_type_string(node.left)
            right = _ast_to_type_string(node.right)
            return f"Union[{left}, {right}]"
        return ast.unparse(node)
    except Exception:
        return str(node)


def _ast_to_default_string(node: Optional[ast.expr]) -> Optional[str]:
    if node is None:
        return None
    try:
        return ast.unparse(node)
    except Exception:
        return str(node)


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
