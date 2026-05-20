"""Behavioral test assertion-checking helpers."""

from __future__ import annotations

import ast
import re
from pathlib import Path

from maid_runner.core.result import ErrorCode, Location, Severity, ValidationError


def validate_test_assertions(
    project_root: Path,
    test_files: list[str],
) -> list[ValidationError]:
    errors: list[ValidationError] = []
    for tf_path in test_files:
        full_path = project_root / tf_path
        if not full_path.exists():
            continue
        try:
            source = full_path.read_text()
        except OSError as exc:
            errors.append(
                ValidationError(
                    code=ErrorCode.FILE_READ_ERROR,
                    message=f"Failed to read test file '{tf_path}': {exc}",
                    location=Location(file=tf_path),
                )
            )
            continue
        errors.extend(check_test_assertions(source, tf_path))
    return errors


def check_test_assertions(source: str, test_path: str) -> list[ValidationError]:
    """Check that test functions in a file contain at least one assertion."""
    errors: list[ValidationError] = []

    if test_path.endswith(".py"):
        try:
            tree = ast.parse(source, filename=test_path)
        except SyntaxError:
            return errors

        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                if not node.name.startswith("test_"):
                    continue
                if python_func_is_pytest_fixture(node):
                    continue
                if python_func_has_assertion(node):
                    continue
                errors.append(
                    ValidationError(
                        code=ErrorCode.MISSING_ASSERTIONS,
                        message=(
                            f"Test function '{node.name}' has no assertions "
                            f"in {test_path}"
                        ),
                        severity=Severity.WARNING,
                        location=Location(file=test_path, line=node.lineno),
                        suggestion="Add assert statements to verify behavior",
                    )
                )
    elif test_path.endswith((".ts", ".tsx", ".js", ".jsx")):
        test_pattern = re.compile(
            r"(?:it|test)\s*\(\s*['\"].*?['\"]\s*,\s*(?:async\s*)?"
            r"(?:\(\s*\)\s*=>|function\s*\(\s*\))\s*\{(.*?)\}",
            re.DOTALL,
        )
        for match in test_pattern.finditer(source):
            body = match.group(1)
            if "expect(" not in body and "assert" not in body.lower():
                name_match = re.search(r"['\"](.+?)['\"]", match.group(0))
                test_name = name_match.group(1) if name_match else "unknown"
                line = source[: match.start()].count("\n") + 1
                errors.append(
                    ValidationError(
                        code=ErrorCode.MISSING_ASSERTIONS,
                        message=(
                            f"Test '{test_name}' has no assertions in {test_path}"
                        ),
                        severity=Severity.WARNING,
                        location=Location(file=test_path, line=line),
                        suggestion="Add expect() statements to verify behavior",
                    )
                )

    return errors


def python_func_has_assertion(node) -> bool:
    """Check if a Python function AST node contains any assertion."""
    for child in ast.walk(node):
        if isinstance(child, ast.Assert):
            return True
        if isinstance(child, ast.Call):
            func = child.func
            if isinstance(func, ast.Attribute) and func.attr == "raises":
                return True
            if isinstance(func, ast.Attribute) and func.attr.startswith("assert"):
                return True
            if isinstance(func, ast.Name) and func.id.startswith("assert"):
                return True
    return False


def python_func_is_pytest_fixture(node) -> bool:
    def is_fixture_decorator(decorator) -> bool:
        if isinstance(decorator, ast.Call):
            decorator = decorator.func
        if isinstance(decorator, ast.Name):
            return decorator.id == "fixture"
        if isinstance(decorator, ast.Attribute):
            return decorator.attr == "fixture"
        return False

    return any(is_fixture_decorator(decorator) for decorator in node.decorator_list)
