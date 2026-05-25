"""Behavioral test assertion-checking helpers."""

from __future__ import annotations

import ast
from dataclasses import dataclass
import re
from pathlib import Path
from typing import Union

from maid_runner.core.result import ErrorCode, Location, Severity, ValidationError

_TestAssertionCacheKey = tuple[str, int, int, str]
_TestAssertionFileSignature = tuple[int, int]


@dataclass(frozen=True)
class TestAssertionTable:
    """Assertion-check results for one test file."""

    errors: tuple[ValidationError, ...] = ()


@dataclass(frozen=True)
class _TestAssertionCacheEntry:
    table: TestAssertionTable
    request_path: str


_TEST_ASSERTION_CACHE: dict[_TestAssertionCacheKey, _TestAssertionCacheEntry] = {}


def validate_test_assertions(
    project_root: Path,
    test_files: list[str],
) -> list[ValidationError]:
    errors: list[ValidationError] = []
    for tf_path in test_files:
        table = get_cached_test_assertions(tf_path, project_root)
        errors.extend(table.errors)
    return errors


def get_cached_test_assertions(
    test_file: Union[str, Path],
    project_root: Path,
) -> TestAssertionTable:
    test_path = _normalize_test_file_path(test_file)
    full_path = _resolve_test_file(test_file, project_root)
    if not full_path.exists():
        return TestAssertionTable()

    try:
        signature = _test_assertion_file_signature(full_path)
    except OSError as exc:
        return _test_file_read_error_table(test_path, exc)

    key = _test_assertion_cache_key(full_path, signature, test_path)
    cached = _TEST_ASSERTION_CACHE.get(key)
    if cached is not None:
        return _test_assertion_table_for_request(cached, test_path)

    try:
        source = full_path.read_text()
    except OSError as exc:
        table = _test_file_read_error_table(test_path, exc)
    else:
        table = TestAssertionTable(
            errors=tuple(check_test_assertions(source, test_path))
        )

    _TEST_ASSERTION_CACHE[key] = _TestAssertionCacheEntry(table, test_path)
    return table


def clear_test_assertion_cache() -> None:
    _TEST_ASSERTION_CACHE.clear()


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


def _normalize_test_file_path(test_file: Union[str, Path]) -> str:
    return str(test_file).replace("\\", "/")


def _resolve_test_file(test_file: Union[str, Path], project_root: Path) -> Path:
    return (project_root / Path(test_file)).resolve()


def _test_assertion_file_signature(path: Path) -> _TestAssertionFileSignature:
    stat = path.stat()
    return (stat.st_mtime_ns, stat.st_size)


def _test_assertion_cache_key(
    path: Path,
    signature: _TestAssertionFileSignature,
    test_path: str,
) -> _TestAssertionCacheKey:
    mtime_ns, size = signature
    return (
        str(path),
        mtime_ns,
        size,
        _assertion_checker_identity(test_path),
    )


def _assertion_checker_identity(test_path: str) -> str:
    suffix = Path(test_path).suffix.lower()
    return f"{suffix}:{check_test_assertions.__module__}.{check_test_assertions.__qualname__}"


def _test_assertion_table_for_request(
    entry: _TestAssertionCacheEntry,
    test_path: str,
) -> TestAssertionTable:
    if entry.request_path == test_path:
        return entry.table
    return TestAssertionTable(
        errors=tuple(
            _rewrite_assertion_error_path(error, entry.request_path, test_path)
            for error in entry.table.errors
        )
    )


def _rewrite_assertion_error_path(
    error: ValidationError,
    cached_path: str,
    requested_path: str,
) -> ValidationError:
    location = error.location
    if location is None:
        new_location = None
    else:
        new_location = Location(
            file=requested_path,
            line=location.line,
            column=location.column,
            end_line=location.end_line,
            end_column=location.end_column,
        )

    return ValidationError(
        code=error.code,
        message=error.message.replace(cached_path, requested_path),
        severity=error.severity,
        location=new_location,
        suggestion=error.suggestion,
    )


def _test_file_read_error_table(
    test_path: str,
    exc: OSError,
) -> TestAssertionTable:
    return TestAssertionTable(
        errors=(
            ValidationError(
                code=ErrorCode.FILE_READ_ERROR,
                message=f"Failed to read test file '{test_path}': {exc}",
                location=Location(file=test_path),
            ),
        )
    )
