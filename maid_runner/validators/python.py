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
        self._seen: set[tuple[str, Optional[str], Optional[str]]] = set()
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
        key = (name, import_source, alias_of)
        if key in self._seen:
            return
        self._seen.add(key)
        self.artifacts.append(
            FoundArtifact(
                kind=ArtifactKind.FUNCTION,  # Kind doesn't matter for behavioral
                name=name,
                import_source=import_source,
                alias_of=alias_of,
            )
        )


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
