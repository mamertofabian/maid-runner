"""Private Python implementation artifact collector."""

from __future__ import annotations

import ast
from dataclasses import replace
from pathlib import Path
from typing import Optional

from maid_runner.core.module_paths import file_to_module_path
from maid_runner.core.types import ArtifactKind, ArgSpec
from maid_runner.validators.base import FoundArtifact


_STDLIB_ENUM_BASES = frozenset({"Enum", "IntEnum", "StrEnum", "Flag", "IntFlag"})


def collect_implementation_artifacts(
    tree: ast.AST,
    file_path: str,
) -> list[FoundArtifact]:
    collector = _ImplementationCollector(file_path=file_path)
    collector.visit(tree)
    return collector.artifacts


class _ImplementationCollector(ast.NodeVisitor):
    def __init__(self, file_path: str = "") -> None:
        self.artifacts: list[FoundArtifact] = []
        self._current_class: Optional[str] = None
        self._in_function: bool = False
        self._enum_base_names: set[str] = set()
        self._enum_module_names: set[str] = set()
        self._control_flow_depth = 0
        self._is_init = Path(file_path).name == "__init__.py"
        self._module_path: Optional[str] = (
            file_to_module_path(file_path, Path(".")) if file_path else None
        ) or None

    def _add(self, artifact: FoundArtifact) -> None:
        if self._module_path and artifact.module_path is None:
            artifact = _with_module_path(artifact, self._module_path)
        self.artifacts.append(artifact)

    def visit_ClassDef(self, node: ast.ClassDef) -> None:
        if self._current_class is None and not self._in_function:
            self._visit_class_definition_header(node)
        base_names = [_extract_base_name(b) for b in node.bases]
        bases = tuple(name for name in base_names if name is not None)
        is_enum = any(self._is_stdlib_enum_base(name) for name in bases)

        self._add(
            FoundArtifact(
                kind=ArtifactKind.CLASS,
                name=node.name,
                _canonical_kind=ArtifactKind.ENUM if is_enum else None,
                bases=bases,
                line=node.lineno,
                column=node.col_offset,
            )
        )

        prev_class = self._current_class
        self._current_class = node.name
        for child in node.body:
            self.visit(child)
        self._current_class = prev_class
        if prev_class is None:
            self._unbind_enum_import_names({node.name})

    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
        self._handle_function(node, is_async=False)

    def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> None:
        self._handle_function(node, is_async=True)

    def _handle_function(
        self, node: ast.FunctionDef | ast.AsyncFunctionDef, is_async: bool
    ) -> None:
        if self._current_class is None and not self._in_function:
            self._visit_function_definition_header(node)
        stub = _is_stub_body(node)

        if self._current_class is not None:
            if _has_property_decorator(node):
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

            prev_in_function = self._in_function
            self._in_function = True
            self.generic_visit(node)
            self._in_function = prev_in_function
        else:
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
            self._unbind_enum_import_names({node.name})

    def visit_Assign(self, node: ast.Assign) -> None:
        if self._current_class is not None and self._in_function:
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
            self._unbind_enum_import_names(_assignment_target_names(node.targets))
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
                self._unbind_enum_import_names({node.target.id})
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

    def visit_Import(self, node: ast.Import) -> None:
        if self._current_class is not None or self._in_function:
            return
        for alias in node.names:
            bound = alias.asname or alias.name.split(".", maxsplit=1)[0]
            self._unbind_enum_import_names({bound})
            if self._control_flow_depth == 0 and alias.name == "enum":
                self._enum_module_names.add(bound)

    def visit_ImportFrom(self, node: ast.ImportFrom) -> None:
        if self._current_class is None and not self._in_function:
            if any(alias.name == "*" for alias in node.names) and (
                node.module != "enum" or node.level or self._control_flow_depth
            ):
                self._enum_base_names.clear()
                self._enum_module_names.clear()
            elif node.module != "enum" or node.level or self._control_flow_depth:
                self._unbind_enum_import_names(
                    {
                        alias.asname or alias.name
                        for alias in node.names
                        if alias.name != "*"
                    }
                )
            else:
                for alias in node.names:
                    if alias.name == "*":
                        self._enum_base_names.update(_STDLIB_ENUM_BASES)
                        continue
                    bound = alias.asname or alias.name
                    self._unbind_enum_import_names({bound})
                    if alias.name in _STDLIB_ENUM_BASES:
                        self._enum_base_names.add(bound)
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

    def visit_If(self, node: ast.If) -> None:
        self._visit_control_flow(node)

    def visit_While(self, node: ast.While) -> None:
        self._visit_control_flow(node)

    def visit_For(self, node: ast.For) -> None:
        self._unbind_module_target(node.target)
        self._visit_control_flow(node)

    def visit_AsyncFor(self, node: ast.AsyncFor) -> None:
        self._unbind_module_target(node.target)
        self._visit_control_flow(node)

    def visit_With(self, node: ast.With) -> None:
        for item in node.items:
            if item.optional_vars is not None:
                self._unbind_module_target(item.optional_vars)
        self._visit_control_flow(node)

    def visit_AsyncWith(self, node: ast.AsyncWith) -> None:
        for item in node.items:
            if item.optional_vars is not None:
                self._unbind_module_target(item.optional_vars)
        self._visit_control_flow(node)

    def visit_Try(self, node: ast.Try) -> None:
        self._visit_control_flow(node)

    def visit_TryStar(self, node: ast.TryStar) -> None:
        self._visit_control_flow(node)

    def visit_Match(self, node: ast.Match) -> None:
        if self._current_class is None and not self._in_function:
            names = {
                name
                for case in node.cases
                for name in _match_pattern_names(case.pattern)
            }
            self._unbind_enum_import_names(names)
        self._visit_control_flow(node)

    def visit_ExceptHandler(self, node: ast.ExceptHandler) -> None:
        if node.name and self._current_class is None and not self._in_function:
            self._unbind_enum_import_names({node.name})
        self.generic_visit(node)

    def visit_AugAssign(self, node: ast.AugAssign) -> None:
        self._unbind_module_target(node.target)
        self.generic_visit(node)

    def visit_NamedExpr(self, node: ast.NamedExpr) -> None:
        self._unbind_module_target(node.target)
        self.generic_visit(node)

    def visit_Delete(self, node: ast.Delete) -> None:
        if self._current_class is None and not self._in_function:
            self._unbind_enum_import_names(_assignment_target_names(node.targets))
        self.generic_visit(node)

    def _visit_control_flow(self, node: ast.AST) -> None:
        self._control_flow_depth += 1
        try:
            self.generic_visit(node)
        finally:
            self._control_flow_depth -= 1

    def _unbind_module_target(self, target: ast.expr) -> None:
        if self._current_class is None and not self._in_function:
            self._unbind_enum_import_names(_assignment_target_names([target]))

    def _visit_class_definition_header(self, node: ast.ClassDef) -> None:
        for decorator in node.decorator_list:
            self.visit(decorator)
        for base in node.bases:
            self.visit(base)
        for keyword in node.keywords:
            self.visit(keyword.value)
        for type_parameter in getattr(node, "type_params", ()):  # Python 3.12+
            self.visit(type_parameter)

    def _visit_function_definition_header(
        self, node: ast.FunctionDef | ast.AsyncFunctionDef
    ) -> None:
        for decorator in node.decorator_list:
            self.visit(decorator)
        for default in (*node.args.defaults, *node.args.kw_defaults):
            if default is not None:
                self.visit(default)
        annotations = [
            argument.annotation
            for argument in (
                *node.args.posonlyargs,
                *node.args.args,
                *node.args.kwonlyargs,
            )
            if argument.annotation is not None
        ]
        if node.args.vararg and node.args.vararg.annotation is not None:
            annotations.append(node.args.vararg.annotation)
        if node.args.kwarg and node.args.kwarg.annotation is not None:
            annotations.append(node.args.kwarg.annotation)
        if node.returns is not None:
            annotations.append(node.returns)
        for annotation in annotations:
            self.visit(annotation)
        for type_parameter in getattr(node, "type_params", ()):  # Python 3.12+
            self.visit(type_parameter)

    def _is_stdlib_enum_base(self, name: str) -> bool:
        if name in self._enum_base_names:
            return True
        namespace, separator, member = name.rpartition(".")
        return bool(
            separator
            and namespace in self._enum_module_names
            and member in _STDLIB_ENUM_BASES
        )

    def _unbind_enum_import_names(self, names: set[str]) -> None:
        self._enum_base_names.difference_update(names)
        self._enum_module_names.difference_update(names)

    def _has_artifact(self, name: str, of: Optional[str]) -> bool:
        return any(a.name == name and a.of == of for a in self.artifacts)


def _with_module_path(artifact: FoundArtifact, module_path: str) -> FoundArtifact:
    return replace(artifact, module_path=module_path)


def _assignment_target_names(targets: list[ast.expr]) -> set[str]:
    names: set[str] = set()
    pending = list(targets)
    while pending:
        target = pending.pop()
        if isinstance(target, ast.Name):
            names.add(target.id)
        elif isinstance(target, (ast.Tuple, ast.List)):
            pending.extend(target.elts)
    return names


def _match_pattern_names(pattern: ast.pattern) -> set[str]:
    names: set[str] = set()
    if isinstance(pattern, ast.MatchAs):
        if pattern.name:
            names.add(pattern.name)
        if pattern.pattern is not None:
            names.update(_match_pattern_names(pattern.pattern))
    elif isinstance(pattern, ast.MatchStar):
        if pattern.name:
            names.add(pattern.name)
    elif isinstance(pattern, ast.MatchMapping):
        if pattern.rest:
            names.add(pattern.rest)
        for child in pattern.patterns:
            names.update(_match_pattern_names(child))
    elif isinstance(pattern, ast.MatchSequence):
        for child in pattern.patterns:
            names.update(_match_pattern_names(child))
    elif isinstance(pattern, ast.MatchClass):
        for child in (*pattern.patterns, *pattern.kwd_patterns):
            names.update(_match_pattern_names(child))
    elif isinstance(pattern, ast.MatchOr):
        for child in pattern.patterns:
            names.update(_match_pattern_names(child))
    return names


def _is_stub_body(node: ast.FunctionDef | ast.AsyncFunctionDef) -> bool:
    if _has_abstractmethod_decorator(node):
        return False

    body = node.body[:]

    if (
        body
        and isinstance(body[0], ast.Expr)
        and isinstance(body[0].value, ast.Constant)
        and isinstance(body[0].value.value, str)
    ):
        body = body[1:]

    if not body:
        return True

    if len(body) != 1:
        return False

    stmt = body[0]

    if isinstance(stmt, ast.Pass):
        return True

    if (
        isinstance(stmt, ast.Expr)
        and isinstance(stmt.value, ast.Constant)
        and stmt.value.value is ...
    ):
        return True

    if isinstance(stmt, ast.Raise) and stmt.exc is not None:
        exc = stmt.exc
        if isinstance(exc, ast.Call) and isinstance(exc.func, ast.Name):
            if exc.func.id == "NotImplementedError":
                return True
        elif isinstance(exc, ast.Name) and exc.id == "NotImplementedError":
            return True

    if isinstance(stmt, ast.Return):
        if stmt.value is None:
            return True
        if isinstance(stmt.value, ast.Constant):
            return True
        if isinstance(stmt.value, ast.Dict) and not stmt.value.keys:
            return True
        if isinstance(stmt.value, ast.List) and not stmt.value.elts:
            return True
        if isinstance(stmt.value, ast.Tuple) and not stmt.value.elts:
            return True

    return False


def _has_abstractmethod_decorator(node: ast.FunctionDef | ast.AsyncFunctionDef) -> bool:
    for decorator in node.decorator_list:
        if isinstance(decorator, ast.Name) and decorator.id == "abstractmethod":
            return True
        if (
            isinstance(decorator, ast.Attribute)
            and decorator.attr == "abstractmethod"
            and isinstance(decorator.value, ast.Name)
            and decorator.value.id == "abc"
        ):
            return True
    return False


def _extract_args(
    node: ast.FunctionDef | ast.AsyncFunctionDef,
    is_method: bool,
) -> tuple[ArgSpec, ...]:
    args = node.args
    all_args = list(args.args)

    if is_method and all_args:
        first_arg_name = all_args[0].arg
        if first_arg_name in ("self", "cls"):
            all_args = all_args[1:]

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
