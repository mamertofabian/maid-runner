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
_JS_TS_TEST_PATTERN = re.compile(
    r"(?<![\w$.])(?:it|test|fit|xit)\s*\(\s*(['\"])(.*?)\1\s*,\s*(?:async\s*)?"
    r"(?:\(\s*\)\s*=>|function\s*\(\s*\))\s*\{",
    re.DOTALL,
)


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
        for match, body in _js_ts_test_bodies(source):
            if "expect(" not in body and "assert" not in body.lower():
                test_name = match.group(2) or "unknown"
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


def _js_ts_test_bodies(source: str) -> list[tuple[re.Match[str], str]]:
    bodies: list[tuple[re.Match[str], str]] = []
    for match in _JS_TS_TEST_PATTERN.finditer(source):
        opening_brace = match.end() - 1
        closing_brace = _find_matching_js_ts_brace(source, opening_brace)
        if closing_brace is None:
            continue
        bodies.append((match, source[opening_brace + 1 : closing_brace]))
    return bodies


def _find_matching_js_ts_brace(source: str, opening_brace: int) -> int | None:
    depth = 0
    quote: str | None = None
    line_comment = False
    block_comment = False
    escaped = False
    index = opening_brace

    while index < len(source):
        char = source[index]
        next_char = source[index + 1] if index + 1 < len(source) else ""

        if line_comment:
            if char == "\n":
                line_comment = False
            index += 1
            continue

        if block_comment:
            if char == "*" and next_char == "/":
                block_comment = False
                index += 2
            else:
                index += 1
            continue

        if quote is not None:
            if escaped:
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == quote:
                quote = None
            index += 1
            continue

        if char == "/" and next_char == "/":
            line_comment = True
            index += 2
            continue
        if char == "/" and next_char == "*":
            block_comment = True
            index += 2
            continue
        if char in {"'", '"', "`"}:
            quote = char
            index += 1
            continue
        if char == "{":
            depth += 1
        elif char == "}":
            depth -= 1
            if depth == 0:
                return index

        index += 1

    return None


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
