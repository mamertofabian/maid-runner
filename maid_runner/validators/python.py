"""Python language validator for MAID Runner v2.

Collects artifact definitions and references from Python source code using AST.
"""

from __future__ import annotations

import ast
from pathlib import Path
from typing import Optional, Union

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

        collector = _ImplementationCollector()
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

        collector = _BehavioralCollector()
        collector.visit(tree)

        return CollectionResult(
            artifacts=collector.artifacts,
            language="python",
            file_path=str(file_path),
        )


class _ImplementationCollector(ast.NodeVisitor):
    def __init__(self) -> None:
        self.artifacts: list[FoundArtifact] = []
        self._current_class: Optional[str] = None
        self._in_function: bool = False

    def visit_ClassDef(self, node: ast.ClassDef) -> None:
        base_names = [_extract_base_name(b) for b in node.bases]
        bases = tuple(name for name in base_names if name is not None)

        self.artifacts.append(
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
        if self._current_class is not None:
            # Inside a class
            if _has_property_decorator(node):
                # Property -> treat as attribute
                self.artifacts.append(
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
                self.artifacts.append(
                    FoundArtifact(
                        kind=ArtifactKind.METHOD,
                        name=node.name,
                        of=self._current_class,
                        args=args,
                        returns=_get_return_type(node),
                        is_async=is_async,
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
            self.artifacts.append(
                FoundArtifact(
                    kind=ArtifactKind.FUNCTION,
                    name=node.name,
                    args=args,
                    returns=_get_return_type(node),
                    is_async=is_async,
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
                        self.artifacts.append(
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
                        self.artifacts.append(
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
                    self.artifacts.append(
                        FoundArtifact(
                            kind=ArtifactKind.ATTRIBUTE,
                            name=target.id,
                            line=node.lineno,
                        )
                    )
                elif isinstance(target, ast.Tuple):
                    for elt in target.elts:
                        if isinstance(elt, ast.Name):
                            self.artifacts.append(
                                FoundArtifact(
                                    kind=ArtifactKind.ATTRIBUTE,
                                    name=elt.id,
                                    line=node.lineno,
                                )
                            )

    def visit_AnnAssign(self, node: ast.AnnAssign) -> None:
        if node.target and isinstance(node.target, ast.Name):
            type_ann = _ast_to_type_string(node.annotation) if node.annotation else None
            if self._current_class is not None and not self._in_function:
                # Class-level annotated attribute
                self.artifacts.append(
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
                self.artifacts.append(
                    FoundArtifact(
                        kind=ArtifactKind.ATTRIBUTE,
                        name=node.target.id,
                        type_annotation=type_ann,
                        line=node.lineno,
                    )
                )

    def _has_artifact(self, name: str, of: Optional[str]) -> bool:
        return any(a.name == name and a.of == of for a in self.artifacts)


class _BehavioralCollector(ast.NodeVisitor):
    """Collect artifact references (imports, calls, attribute access)."""

    def __init__(self) -> None:
        self.artifacts: list[FoundArtifact] = []
        self._seen: set[str] = set()

    def visit_ImportFrom(self, node: ast.ImportFrom) -> None:
        if node.names:
            for alias in node.names:
                name = alias.asname or alias.name
                self._add_reference(name)
        self.generic_visit(node)

    def visit_Import(self, node: ast.Import) -> None:
        for alias in node.names:
            name = alias.asname or alias.name
            self._add_reference(name)
        self.generic_visit(node)

    def visit_Call(self, node: ast.Call) -> None:
        if isinstance(node.func, ast.Name):
            self._add_reference(node.func.id)
        elif isinstance(node.func, ast.Attribute):
            self._add_reference(node.func.attr)
        self.generic_visit(node)

    def visit_Name(self, node: ast.Name) -> None:
        self._add_reference(node.id)
        self.generic_visit(node)

    def _add_reference(self, name: str) -> None:
        if name not in self._seen:
            self._seen.add(name)
            self.artifacts.append(
                FoundArtifact(
                    kind=ArtifactKind.FUNCTION,  # Kind doesn't matter for behavioral
                    name=name,
                )
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
