"""Command-integrity behavioral test file discovery helpers."""

from __future__ import annotations

import ast
import re
from pathlib import Path

from maid_runner.core._file_discovery import is_test_file
from maid_runner.core._test_command_targets import test_paths_from_validate_command
from maid_runner.core.types import Manifest

_TEST_DIRECTORY_NAMES = frozenset({"test", "tests", "__tests__", "spec", "specs"})


def find_command_integrity_test_files(
    manifest: Manifest,
    project_root: Path,
    *,
    test_paths_from_validate_command_fn=test_paths_from_validate_command,
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
    for command in manifest.validate_commands:
        for path in test_paths_from_validate_command_fn(command, project_root):
            add_test_path(path)

    return test_files


def is_command_integrity_test_file(path: str, project_root: Path) -> bool:
    name = Path(path).name
    if name == "conftest.py":
        return False
    if not is_test_file(path):
        return False

    if name.endswith(".py"):
        return is_python_behavioral_test_file(path, project_root)

    parts = Path(path).parts
    if any(part.lower() in _TEST_DIRECTORY_NAMES for part in parts[:-1]):
        return True

    return bool(re.search(r"\.(test|spec)\.(ts|tsx|js|jsx)$", name))


def is_python_behavioral_test_file(path: str, project_root: Path) -> bool:
    full_path = project_root / path
    try:
        source = full_path.read_text()
        tree = ast.parse(source, filename=path)
    except (OSError, SyntaxError):
        return True

    for statement in tree.body:
        if isinstance(statement, (ast.FunctionDef, ast.AsyncFunctionDef)):
            if statement.name.startswith("test_"):
                return True
        if isinstance(statement, ast.ClassDef) and statement.name.startswith("Test"):
            for child in statement.body:
                if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    if child.name.startswith("test_"):
                        return True

    return False
