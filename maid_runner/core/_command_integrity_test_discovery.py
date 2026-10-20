"""Command-integrity behavioral test file discovery helpers."""

from __future__ import annotations

import ast
import re
from pathlib import Path

from maid_runner.core._file_discovery import is_test_file
from maid_runner.core._rust_support import _is_inline_rust_test
from maid_runner.core._test_command_targets import test_paths_from_validate_command
from maid_runner.core.types import Manifest

_TEST_DIRECTORY_NAMES = frozenset({"test", "tests", "__tests__", "spec", "specs"})


def find_command_integrity_test_files(
    manifest: Manifest,
    project_root: Path,
    *,
    test_paths_from_validate_command_fn=test_paths_from_validate_command,
    include_scope: bool = False,
) -> list[str]:
    test_files: list[str] = []

    def add_test_file(path: str) -> None:
        if (
            is_command_integrity_test_file(path, project_root)
            and path not in test_files
        ):
            test_files.append(path)

    def add_test_path(path: str) -> None:
        add_test_file(path)

        full_path = project_root / path
        if not full_path.is_dir():
            return

        for child in sorted(full_path.rglob("*")):
            if not child.is_file():
                continue
            rel_path = str(child.relative_to(project_root))
            add_test_file(rel_path)

    for path in manifest.files_read:
        add_test_path(path)
    for file_spec in manifest.all_file_specs:
        add_test_path(file_spec.path)
    if include_scope:
        for scope_spec in manifest.files_scope:
            add_test_path(scope_spec.path)
    for command in manifest.validate_commands:
        for path in test_paths_from_validate_command_fn(command, project_root):
            add_test_path(path)

    return test_files


def is_command_integrity_test_file(path: str, project_root: Path) -> bool:
    name = Path(path).name
    if Path(path).suffix == ".rs":
        return is_test_file(path) or _is_inline_rust_test(path, project_root)
    if name == "conftest.py":
        return False
    if not is_test_file(path):
        return False

    if name.endswith(".py"):
        return is_python_behavioral_test_file(path, project_root)

    parts = Path(path).parts
    if any(part.lower() in _TEST_DIRECTORY_NAMES for part in parts[:-1]):
        return True

    return bool(re.search(r"\.(test|spec)\.(ts|tsx|js|jsx|mjs|cjs)$", name))


def is_python_behavioral_test_file(path: str, project_root: Path) -> bool:
    full_path = project_root / path
    try:
        source = full_path.read_text()
        tree = ast.parse(source, filename=path)
    except (OSError, SyntaxError):
        return True

    # Resolve only explicit stdlib/Django imports and local class inheritance.
    # This does not execute imports or infer arbitrary third-party base classes.
    imports: dict[str, str] = {}
    test_bases = {
        "unittest.TestCase",
        "unittest.IsolatedAsyncioTestCase",
        "unittest.async_case.IsolatedAsyncioTestCase",
        "unittest.case.TestCase",
        "django.test.TestCase",
        "django.test.TransactionTestCase",
        "django.test.SimpleTestCase",
        "django.test.LiveServerTestCase",
        "django.contrib.staticfiles.testing.StaticLiveServerTestCase",
    }
    test_bases.update(
        f"django.test.testcases.{name.rsplit('.', 1)[-1]}"
        for name in tuple(test_bases)
        if name.startswith("django.test.")
    )
    local_test_classes: set[str] = set()

    def resolved_name(node: ast.expr) -> str:
        if isinstance(node, ast.Name):
            return imports.get(node.id, node.id)
        if isinstance(node, ast.Attribute):
            return f"{resolved_name(node.value)}.{node.attr}"
        return ""

    for statement in tree.body:
        if isinstance(statement, ast.Import):
            for alias in statement.names:
                imports[alias.asname or alias.name.split(".")[0]] = (
                    alias.name if alias.asname else alias.name.split(".")[0]
                )
        elif isinstance(statement, ast.ImportFrom) and statement.level == 0:
            for alias in statement.names:
                imports[alias.asname or alias.name] = f"{statement.module}.{alias.name}"
        if isinstance(statement, (ast.FunctionDef, ast.AsyncFunctionDef)):
            if statement.name.startswith("test_"):
                return True
        if not isinstance(statement, ast.ClassDef):
            continue
        is_test_case = any(
            resolved_name(base) in test_bases
            or (isinstance(base, ast.Name) and base.id in local_test_classes)
            for base in statement.bases
        )
        if is_test_case:
            local_test_classes.add(statement.name)
        if statement.name.startswith("Test") or is_test_case:
            for child in statement.body:
                if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    if child.name.startswith("test" if is_test_case else "test_") or (
                        is_test_case and child.name == "runTest"
                    ):
                        return True

    return False
