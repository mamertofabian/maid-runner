"""Private Python implementation artifact collector."""

from __future__ import annotations

import ast
from dataclasses import replace
from pathlib import Path
from typing import Optional

from maid_runner.core.module_paths import file_to_module_path
from maid_runner.core.types import ArtifactKind, ArgSpec
from maid_runner.validators.base import FoundArtifact


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

    def visit_ImportFrom(self, node: ast.ImportFrom) -> None:
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


def _with_module_path(artifact: FoundArtifact, module_path: str) -> FoundArtifact:
    return replace(artifact, module_path=module_path)


def _is_stub_body(node: ast.FunctionDef | ast.AsyncFunctionDef) -> bool:
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
