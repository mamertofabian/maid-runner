"""Behavioral test assertion-checking helpers."""

from __future__ import annotations

import ast
from bisect import bisect_left
from dataclasses import dataclass
import re
from pathlib import Path
from typing import Any, Union
import warnings

from maid_runner.core.result import ErrorCode, Location, Severity, ValidationError

_TestAssertionCacheKey = tuple[str, int, int, str]
_TestAssertionFileSignature = tuple[int, int]
_JS_TS_TEST_PATTERN = re.compile(
    r"(?<![\w$.])(?:it|test|fit|xit)\s*\(\s*(['\"])(.*?)\1\s*,\s*(?:async\s*)?"
    r"(?:\(\s*\)\s*=>|function\s*\(\s*\))\s*\{",
    re.DOTALL,
)
# Bounded Vitest/Jest matcher names; arbitrary methods and custom extensions
# cannot be distinguished reliably from non-asserting methods by syntax alone.
_JS_TS_EXPECT_MATCHERS = frozenset(
    name.encode("ascii")
    for name in (
        "toBe",
        "toBeCalled",
        "toBeCalledTimes",
        "toBeCalledWith",
        "toBeCloseTo",
        "toBeDefined",
        "toBeFasterThan",
        "toBeFalsy",
        "toBeGreaterThan",
        "toBeGreaterThanOrEqual",
        "toBeInstanceOf",
        "toBeLessThan",
        "toBeLessThanOrEqual",
        "toBeNaN",
        "toBeNull",
        "toBeNullable",
        "toBeOneOf",
        "toBeSlowerThan",
        "toBeTruthy",
        "toBeTypeOf",
        "toBeUndefined",
        "toContain",
        "toContainEqual",
        "toEqual",
        "toHaveBeenCalled",
        "toHaveBeenCalledAfter",
        "toHaveBeenCalledBefore",
        "toHaveBeenCalledExactlyOnceWith",
        "toHaveBeenCalledOnce",
        "toHaveBeenCalledTimes",
        "toHaveBeenCalledWith",
        "toHaveBeenExhausted",
        "toHaveBeenLastCalledWith",
        "toHaveBeenNthCalledWith",
        "toHaveLastResolvedWith",
        "toHaveLastReturnedWith",
        "toHaveLength",
        "toHaveNthResolvedWith",
        "toHaveNthReturnedWith",
        "toHaveProperty",
        "toHaveResolved",
        "toHaveResolvedTimes",
        "toHaveResolvedWith",
        "toHaveReturned",
        "toHaveReturnedTimes",
        "toHaveReturnedWith",
        "toMatch",
        "toMatchFileSnapshot",
        "toMatchObject",
        "toMatchSnapshot",
        "toMatchInlineSnapshot",
        "toReturn",
        "toReturnTimes",
        "toReturnWith",
        "toSatisfy",
        "toStrictEqual",
        "toThrow",
        "toThrowError",
        "toThrowErrorMatchingSnapshot",
        "toThrowErrorMatchingInlineSnapshot",
    )
)
# Public Python 1.58 Playwright matchers; their not_to_ forms use the same roots.
_PLAYWRIGHT_MATCHERS = frozenset(
    {
        "to_be_attached",
        "to_be_checked",
        "to_be_disabled",
        "to_be_editable",
        "to_be_empty",
        "to_be_enabled",
        "to_be_focused",
        "to_be_hidden",
        "to_be_in_viewport",
        "to_be_visible",
        "to_contain_class",
        "to_contain_text",
        "to_have_accessible_description",
        "to_have_accessible_error_message",
        "to_have_accessible_name",
        "to_have_attribute",
        "to_have_class",
        "to_have_count",
        "to_have_css",
        "to_have_id",
        "to_have_js_property",
        "to_have_role",
        "to_have_text",
        "to_have_value",
        "to_have_values",
        "to_match_aria_snapshot",
        "to_have_title",
        "to_have_url",
        "to_be_ok",
    }
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
        bodies, session = _js_ts_test_bodies(source, test_path)
        context = None
        for match, body, opening_byte in bodies:
            if "expect(" not in body and "assert" not in body.lower():
                if context is None and session is not None:
                    context = _js_ts_assertion_context(session)
                if context is not None and _js_ts_awaits_asserting_helper(
                    context, opening_byte
                ):
                    continue
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


def _parse_js_ts_assertions(source: str, test_path: str) -> Any:
    """Parse once for both regex shielding and bounded helper recognition."""
    try:
        from tree_sitter import Language, Parser
        import tree_sitter_typescript
    except ImportError:
        warnings.warn(
            "JS/TS assertion checking is using the legacy scanner because optional "
            "parsers are unavailable; install maid-runner[typescript] or [all] "
            "for regex-aware boundaries.",
            RuntimeWarning,
            stacklevel=3,
        )
        return None

    from maid_runner.validators._typescript_parse import parse_typescript_source

    return parse_typescript_source(
        source,
        test_path,
        Parser(Language(tree_sitter_typescript.language_typescript())),
        Parser(Language(tree_sitter_typescript.language_tsx())),
    )


def _shield_js_ts_regex_tokens(source: str, session: Any) -> str:
    """Shield grammar-identified regex tokens without changing character offsets."""
    if session is None or "/" not in source:
        return source

    spans: list[tuple[int, int]] = []
    pending = [session.tree.root_node]
    while pending:
        node = pending.pop()
        if node.type == "regex" and not node.has_error:
            spans.append((node.start_byte, node.end_byte))
        else:
            pending.extend(node.named_children)

    # Parse-service spans are byte offsets. Decode each original segment before
    # shielding so multibyte characters still occupy exactly one Python index.
    parts: list[str] = []
    cursor = 0
    for start, end in sorted(spans):
        parts.append(session.source_bytes[cursor:start].decode("utf-8"))
        token = session.source_bytes[start:end].decode("utf-8")
        parts.append("".join(char if char in "\r\n" else " " for char in token))
        cursor = end
    parts.append(session.source_bytes[cursor:].decode("utf-8"))
    return "".join(parts)


def _js_ts_test_bodies(
    source: str, test_path: str
) -> tuple[list[tuple[re.Match[str], str, int]], Any]:
    session = _parse_js_ts_assertions(source, test_path)
    shielded = _shield_js_ts_regex_tokens(source, session)
    bodies: list[tuple[re.Match[str], str, int]] = []
    previous_char = 0
    previous_byte = 0
    for match in _JS_TS_TEST_PATTERN.finditer(shielded):
        opening_brace = match.end() - 1
        closing_brace = _find_matching_js_ts_brace(shielded, opening_brace)
        if closing_brace is None:
            continue
        previous_byte += len(source[previous_char:opening_brace].encode("utf-8"))
        previous_char = opening_brace
        bodies.append((match, source[opening_brace + 1 : closing_brace], previous_byte))
    return bodies, session


@dataclass
class _JsTsAssertionContext:
    session: Any
    writes: dict[bytes, list[Any]]
    global_writes: set[bytes]
    escaped_identifiers: bool
    unknown_global_write: bool
    scopes: dict[int, tuple[dict[bytes, list[Any]], set[bytes]]]
    matcher_results: dict[int, bool]
    write_results: dict[tuple[int, bytes], bool]


def _js_ts_binding_nodes(node: Any) -> list[Any]:
    names = []
    pending = [node]
    while pending:
        current = pending.pop()
        if current.type in {"identifier", "shorthand_property_identifier_pattern"}:
            names.append(current)
            continue
        if current.type in {
            "member_expression",
            "subscript_expression",
            "type_annotation",
        }:
            continue
        if current.type == "pair_pattern":
            value = current.child_by_field_name("value")
            if value is not None:
                pending.append(value)
            continue
        if current.type in {"assignment_pattern", "object_assignment_pattern"}:
            left = current.child_by_field_name("left")
            if left is not None:
                pending.append(left)
            continue
        if current.type in {"required_parameter", "optional_parameter"}:
            pattern = current.child_by_field_name("pattern")
            if pattern is not None:
                pending.append(pattern)
            continue
        pending.extend(current.named_children)
    return names


def _js_ts_binding_names(node: Any) -> set[bytes]:
    return {binding.text for binding in _js_ts_binding_nodes(node)}


def _js_ts_global_writes(
    context: _JsTsAssertionContext, target: Any
) -> tuple[set[bytes], bool]:
    """Collect direct global property writes; unknown keys remain ambiguous."""
    names: set[bytes] = set()
    unknown = False
    pending = [target]
    while pending:
        node = pending.pop()
        if node.type in {"member_expression", "subscript_expression"}:
            receiver = _js_ts_unwrap_global_receiver(node.child_by_field_name("object"))
            if (
                receiver is not None
                and receiver.type == "identifier"
                and receiver.text in {b"globalThis", b"global", b"window", b"self"}
                and not _js_ts_global_receiver_is_shadowed(context, receiver)
            ):
                if node.type == "subscript_expression":
                    index = node.child_by_field_name("index")
                    if (
                        index is not None
                        and index.type == "string"
                        and b"\\" not in index.text
                    ):
                        names.add(index.text[1:-1])
                    else:
                        unknown = True
                else:
                    prop = node.child_by_field_name("property")
                    if prop is not None:
                        names.add(prop.text)
            # The receiver and computed key are reads, not assignment targets.
            continue
        if node.type == "pair_pattern":
            value = node.child_by_field_name("value")
            if value is not None:
                pending.append(value)
            continue
        if node.type in {"assignment_pattern", "object_assignment_pattern"}:
            left = node.child_by_field_name("left")
            if left is not None:
                pending.append(left)
            continue
        pending.extend(node.named_children)
    return names, unknown


def _js_ts_unwrap_global_receiver(node: Any) -> Any:
    while node is not None:
        children = _js_ts_code_children(node)
        if node.type in {"parenthesized_expression", "non_null_expression"}:
            if len(children) != 1:
                return None
            node = children[0]
        elif node.type in {"as_expression", "satisfies_expression"}:
            node = children[0] if children else None
        elif node.type == "type_assertion":
            node = children[-1] if children else None
        else:
            return node
    return None


def _js_ts_assertion_context(session: Any) -> _JsTsAssertionContext:
    """Index writes once; uncertain or escaped names fail conservatively."""
    writes: dict[bytes, list[Any]] = {}
    targets = []
    escaped = False
    pending = [session.tree.root_node]
    while pending:
        node = pending.pop()
        if (
            node.type
            in {
                "identifier",
                "property_identifier",
                "type_identifier",
                "shorthand_property_identifier",
                "shorthand_property_identifier_pattern",
                "private_property_identifier",
            }
            and b"\\" in node.text
        ):
            escaped = True
        target = None
        if node.type in {
            "assignment_expression",
            "augmented_assignment_expression",
            "for_in_statement",
        }:
            target = node.child_by_field_name("left")
        elif node.type == "update_expression":
            target = node
        elif node.type == "unary_expression":
            operator = node.child_by_field_name("operator")
            if operator is not None and operator.text == b"delete":
                target = node.child_by_field_name("argument")
        if target is not None:
            for binding in _js_ts_binding_nodes(target):
                writes.setdefault(binding.text, []).append(binding)
            targets.append(target)
        pending.extend(node.named_children)
    for nodes in writes.values():
        nodes.sort(key=lambda item: item.start_byte)
    context = _JsTsAssertionContext(session, writes, set(), escaped, False, {}, {}, {})
    for target in targets:
        global_names, unknown = _js_ts_global_writes(context, target)
        context.global_writes.update(global_names)
        context.unknown_global_write |= unknown
    return context


def _js_ts_code_children(node: Any) -> list[Any]:
    return [child for child in node.named_children if child.type != "comment"]


def _js_ts_unwrap_parentheses(node: Any) -> Any:
    while node is not None and node.type == "parenthesized_expression":
        children = _js_ts_code_children(node)
        if len(children) != 1:
            return None
        node = children[0]
    return node


def _js_ts_is_optional(node: Any) -> bool:
    return any(child.type in {"?.", "optional_chain"} for child in node.children)


def _js_ts_awaits_asserting_helper(
    context: _JsTsAssertionContext, opening_byte: int
) -> bool:
    if context.escaped_identifiers:
        return False
    body = context.session.tree.root_node.descendant_for_byte_range(
        opening_byte, opening_byte + 1
    )
    while body is not None and body.type != "statement_block":
        body = body.parent
    if body is None or body.start_byte != opening_byte or body.has_error:
        return False

    callback = body.parent
    if callback is None or callback.type not in {
        "arrow_function",
        "function_expression",
    }:
        return False
    if _js_ts_registration_scope(callback, {"it", "test", "fit", "xit"}) is None:
        return False

    for statement in body.named_children:
        expressions = []
        if statement.type in {"expression_statement", "return_statement"}:
            expressions = _js_ts_code_children(statement)[:1]
        elif statement.type in {"lexical_declaration", "variable_declaration"}:
            expressions = [
                value
                for declaration in statement.named_children
                if declaration.type == "variable_declarator"
                if (value := declaration.child_by_field_name("value")) is not None
            ]
        for expression in expressions:
            if _js_ts_awaited_helper_asserts(context, body, expression):
                return True
    return False


def _js_ts_awaited_helper_asserts(
    context: _JsTsAssertionContext, body: Any, expression: Any
) -> bool:
    expression = _js_ts_unwrap_parentheses(expression)
    if (
        expression is not None
        and expression.type == "await_expression"
        and _js_ts_code_children(expression)
    ):
        call = _js_ts_unwrap_parentheses(_js_ts_code_children(expression)[0])
        if call is None:
            return False
        if call.type != "call_expression" or call.has_error or _js_ts_is_optional(call):
            return False
        name = _js_ts_unwrap_parentheses(call.child_by_field_name("function"))
        if name is None or name.type != "identifier":
            return False
        helper = _js_ts_resolve_helper(context, body, name.text)
        if helper is not None:
            key = helper.id
            if key not in context.matcher_results:
                context.matcher_results[key] = _js_ts_helper_has_matcher(
                    context, helper
                )
            return context.matcher_results[key]
    return False


def _js_ts_registration_scope(callback: Any, names: set[str]) -> Any:
    """Return the scope containing a direct test/suite registration callback."""
    arguments = callback.parent
    call = arguments.parent if arguments is not None else None
    if arguments is None or arguments.type != "arguments":
        return None
    if call is None or call.type != "call_expression":
        return None
    callee = call.child_by_field_name("function")
    # A suite may use chained modifiers or modifier factories such as each(...).
    while callee is not None:
        if callee.type == "call_expression":
            factory = callee.child_by_field_name("function")
            prop = (
                factory.child_by_field_name("property") if factory is not None else None
            )
            if (
                factory is None
                or factory.type != "member_expression"
                or prop is None
                or prop.text not in {b"each", b"for", b"runIf", b"skipIf"}
            ):
                return None
            callee = factory
        elif callee.type == "member_expression":
            prop = callee.child_by_field_name("property")
            if prop is None or prop.text not in {
                b"only",
                b"skip",
                b"each",
                b"for",
                b"runIf",
                b"skipIf",
                b"concurrent",
                b"sequential",
                b"shuffle",
                b"todo",
            }:
                return None
            callee = callee.child_by_field_name("object")
        else:
            break
    if callee is None or callee.type != "identifier":
        return None
    if callee.text.decode("utf-8") not in names:
        return None
    value = call
    while value.parent is not None and value.parent.type == "parenthesized_expression":
        value = value.parent
    statement = value.parent
    if statement is not None and statement.type == "variable_declarator":
        if statement.child_by_field_name("value") != value:
            return None
        statement = statement.parent
    elif statement is not None and statement.type == "assignment_expression":
        if statement.child_by_field_name("right") != value:
            return None
        statement = statement.parent
    if statement is None or statement.type not in {
        "expression_statement",
        "return_statement",
        "lexical_declaration",
        "variable_declaration",
    }:
        return None
    if statement.parent is not None and statement.parent.type == "export_statement":
        statement = statement.parent
    scope = statement.parent
    return (
        scope
        if scope is not None and scope.type in {"program", "statement_block"}
        else None
    )


def _js_ts_callback_binds(callback: Any, name: bytes) -> bool:
    declared = callback.child_by_field_name("name")
    if declared is not None and name in _js_ts_binding_names(declared):
        return True
    parameters = callback.child_by_field_name("parameters")
    if parameters is None:
        parameters = callback.child_by_field_name("parameter")
    return parameters is not None and name in _js_ts_binding_names(parameters)


def _js_ts_import_bindings(node: Any) -> set[bytes]:
    """Treat only standard, unaliased expect imports as known assertion APIs."""
    bindings: set[bytes] = set()
    source = node.child_by_field_name("source")
    trusted = source is not None and source.text[1:-1] in {b"vitest", b"@jest/globals"}
    pending = list(node.named_children)
    while pending:
        current = pending.pop()
        if current.type == "import_specifier":
            original = current.child_by_field_name("name")
            alias = current.child_by_field_name("alias")
            local = alias if alias is not None else original
            if local is not None and not (
                trusted
                and original is not None
                and original.text == b"expect"
                and local.text == b"expect"
            ):
                bindings.add(local.text)
            continue
        if current.type == "identifier":
            bindings.add(current.text)
        else:
            pending.extend(current.named_children)
    return bindings


def _js_ts_scope_bindings(
    context: _JsTsAssertionContext, scope: Any
) -> tuple[dict[bytes, list[Any]], set[bytes]]:
    """Index declarations once per scope without interpreting control flow."""
    key = scope.id
    if key in context.scopes:
        return context.scopes[key]
    helpers: dict[bytes, list[Any]] = {}
    blocked: set[bytes] = set()
    parent = scope.parent
    function_scope = scope.type == "program" or (
        parent is not None
        and parent.type
        in {
            "arrow_function",
            "function_expression",
            "function_declaration",
            "method_definition",
            "generator_function",
            "generator_function_declaration",
            "class_static_block",
        }
    )
    pending = [(node, 0) for node in scope.named_children]
    while pending:
        node, depth = pending.pop()
        if node.type in {"statement_block", "switch_body"}:
            pending.extend((child, depth + 1) for child in node.named_children)
            continue
        if node.type == "for_statement":
            initializer = node.child_by_field_name("initializer")
            if initializer is not None and initializer.type == "lexical_declaration":
                pending.extend((child, depth + 1) for child in node.named_children)
                continue
        if node.type in {"function_declaration", "generator_function_declaration"}:
            declared = node.child_by_field_name("name")
            if declared is not None and depth == 0:
                parent = node.parent
                direct = parent == scope or (
                    parent is not None
                    and parent.type == "export_statement"
                    and parent.parent == scope
                )
                if direct and node.type == "function_declaration":
                    helpers.setdefault(declared.text, []).append(node)
                else:
                    blocked.add(declared.text)
            continue
        if node.type in {
            "arrow_function",
            "function_expression",
            "generator_function",
            "method_definition",
            "class",
            "class_static_block",
        }:
            continue
        if node.type in {"class_declaration", "abstract_class_declaration"}:
            declared = node.child_by_field_name("name")
            if declared is not None and depth == 0:
                blocked.add(declared.text)
            continue
        if node.type in {"enum_declaration", "internal_module", "module"}:
            declared = node.child_by_field_name("name")
            if declared is not None and depth == 0:
                blocked.update(_js_ts_binding_names(declared))
            continue
        if node.type == "import_alias":
            if node.named_children and depth == 0:
                blocked.update(_js_ts_binding_names(node.named_children[0]))
            continue
        if node.type == "import_statement":
            if depth == 0:
                blocked.update(_js_ts_import_bindings(node))
            continue
        if node.type == "variable_declarator":
            declared = node.child_by_field_name("name")
            declaration = node.parent
            is_var = (
                declaration is not None and declaration.type == "variable_declaration"
            )
            if declared is not None and (
                (is_var and function_scope) or (not is_var and depth == 0)
            ):
                blocked.update(_js_ts_binding_names(declared))
        if node.type == "for_in_statement" and function_scope:
            if any(child.type == "var" for child in node.children):
                declared = node.child_by_field_name("left")
                if declared is not None:
                    blocked.update(_js_ts_binding_names(declared))
        pending.extend((child, depth) for child in node.named_children)
    context.scopes[key] = (helpers, blocked)
    return helpers, blocked


def _js_ts_node_binds_name(
    context: _JsTsAssertionContext, node: Any, name: bytes
) -> bool:
    if node.type in {"statement_block", "switch_body", "program"}:
        helpers, blocked = _js_ts_scope_bindings(context, node)
        if name in blocked or name in helpers:
            return True
    if node.type == "class":
        declared = node.child_by_field_name("name")
        if declared is not None and declared.text == name:
            return True
    if node.type in {
        "arrow_function",
        "function_expression",
        "function_declaration",
        "generator_function",
        "generator_function_declaration",
        "method_definition",
    }:
        parameters = node.child_by_field_name("parameters")
        if parameters is None:
            parameters = node.child_by_field_name("parameter")
        if parameters is not None and name in _js_ts_binding_names(parameters):
            return True
        declared = node.child_by_field_name("name")
        if (
            node.type in {"function_expression", "generator_function"}
            and declared is not None
            and declared.text == name
        ):
            return True
    if node.type == "catch_clause":
        parameter = node.child_by_field_name("parameter")
        if parameter is not None and name in _js_ts_binding_names(parameter):
            return True
    if node.type == "for_in_statement" and any(
        child.type in {"let", "const"} for child in node.children
    ):
        declared = node.child_by_field_name("left")
        if declared is not None and name in _js_ts_binding_names(declared):
            return True
    if node.type == "for_statement":
        initializer = node.child_by_field_name("initializer")
        if initializer is not None and initializer.type == "lexical_declaration":
            for declaration in initializer.named_children:
                declared = declaration.child_by_field_name("name")
                if declared is not None and name in _js_ts_binding_names(declared):
                    return True
    return False


def _js_ts_enclosing_scope(
    context: _JsTsAssertionContext, scope: Any, name: bytes
) -> Any:
    """Climb ordinary lexical blocks without crossing a function boundary."""
    current = scope.parent
    while current is not None:
        if current.type in {"statement_block", "switch_body", "program"}:
            return current
        if current.type in {
            "arrow_function",
            "function_expression",
            "function_declaration",
            "generator_function",
            "generator_function_declaration",
            "method_definition",
            "class",
            "class_static_block",
        }:
            return None
        if _js_ts_node_binds_name(context, current, name):
            return None
        current = current.parent
    return None


def _js_ts_global_receiver_is_shadowed(
    context: _JsTsAssertionContext, receiver: Any
) -> bool:
    current = receiver.parent
    while current is not None:
        if _js_ts_node_binds_name(context, current, receiver.text):
            return True
        current = current.parent
    return False


def _js_ts_writes_affect(
    context: _JsTsAssertionContext, name: bytes, binding_scope: Any
) -> bool:
    """Match writes against a binding's enclosing lexical scope."""
    key = (binding_scope.id, name)
    if key in context.write_results:
        return context.write_results[key]
    if binding_scope.type == "program" and (
        name in context.global_writes or context.unknown_global_write
    ):
        context.write_results[key] = True
        return True
    writes = context.writes.get(name, [])
    first = bisect_left(
        writes, binding_scope.start_byte, key=lambda item: item.start_byte
    )
    last = bisect_left(writes, binding_scope.end_byte, key=lambda item: item.start_byte)
    for write in writes[first:last]:
        current = write.parent
        while current is not None and current != binding_scope:
            if _js_ts_node_binds_name(context, current, name):
                break
            current = current.parent
        if current == binding_scope:
            context.write_results[key] = True
            return True
    context.write_results[key] = False
    return False


def _js_ts_resolve_helper(
    context: _JsTsAssertionContext, body: Any, name: bytes
) -> Any:
    scope = body
    while scope is not None:
        callback = scope.parent if scope.type == "statement_block" else None
        if (
            callback is not None
            and callback.type in {"arrow_function", "function_expression"}
            and _js_ts_callback_binds(callback, name)
        ):
            return None
        helpers, blocked = _js_ts_scope_bindings(context, scope)
        candidates = helpers.get(name, [])
        if name in blocked or len(candidates) > 1:
            return None
        if candidates:
            if candidates[0].has_error or _js_ts_writes_affect(context, name, scope):
                return None
            return candidates[0]
        if scope.type == "program" or callback is None:
            return None
        if callback.type in {"arrow_function", "function_expression"}:
            scope = _js_ts_registration_scope(
                callback, {"it", "test", "fit", "xit", "describe", "suite"}
            )
        else:
            scope = _js_ts_enclosing_scope(context, scope, name)
    return None


def _js_ts_expect_is_unshadowed(context: _JsTsAssertionContext, helper: Any) -> bool:
    if _js_ts_callback_binds(helper, b"expect"):
        return False
    scope = helper.child_by_field_name("body")
    while scope is not None:
        helpers, blocked = _js_ts_scope_bindings(context, scope)
        if b"expect" in blocked or b"expect" in helpers:
            return False
        if scope.type == "program":
            return not _js_ts_writes_affect(context, b"expect", scope)
        parent = scope.parent
        if parent is None:
            return False
        if parent.type in {"arrow_function", "function_expression"}:
            if _js_ts_callback_binds(parent, b"expect"):
                return False
            scope = _js_ts_registration_scope(parent, {"describe", "suite"})
        elif parent == helper:
            scope = parent.parent
            if scope is not None and scope.type == "export_statement":
                scope = scope.parent
        else:
            scope = _js_ts_enclosing_scope(context, scope, b"expect")
    return False


def _js_ts_helper_has_matcher(context: _JsTsAssertionContext, helper: Any) -> bool:
    body = helper.child_by_field_name("body")
    if body is None or body.type != "statement_block":
        return False
    if not _js_ts_expect_is_unshadowed(context, helper):
        return False
    for statement in body.named_children:
        children = _js_ts_code_children(statement)
        if (
            statement.type not in {"expression_statement", "return_statement"}
            or not children
        ):
            continue
        expression = _js_ts_unwrap_parentheses(children[0])
        if expression is None:
            continue
        children = _js_ts_code_children(expression)
        if expression.type == "await_expression" and children:
            expression = _js_ts_unwrap_parentheses(children[0])
        if expression is None:
            continue
        if (
            expression.type != "call_expression"
            or expression.has_error
            or _js_ts_is_optional(expression)
        ):
            continue
        matcher = expression.child_by_field_name("function")
        if (
            matcher is None
            or matcher.type != "member_expression"
            or _js_ts_is_optional(matcher)
        ):
            continue
        property_node = matcher.child_by_field_name("property")
        if property_node is None or property_node.text not in _JS_TS_EXPECT_MATCHERS:
            continue
        receiver = _js_ts_unwrap_parentheses(matcher.child_by_field_name("object"))
        while receiver is not None and receiver.type == "member_expression":
            if _js_ts_is_optional(receiver):
                break
            modifier = receiver.child_by_field_name("property")
            if modifier is None or modifier.text not in {
                b"not",
                b"resolves",
                b"rejects",
            }:
                break
            receiver = _js_ts_unwrap_parentheses(receiver.child_by_field_name("object"))
        if (
            receiver is None
            or receiver.type != "call_expression"
            or _js_ts_is_optional(receiver)
        ):
            continue
        expect = receiver.child_by_field_name("function")
        arguments = receiver.child_by_field_name("arguments")
        if (
            expect is not None
            and expect.type == "identifier"
            and expect.text == b"expect"
            and arguments is not None
            and bool(_js_ts_code_children(arguments))
        ):
            return True
    return False


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


def _is_playwright_assertion_call(node: ast.Call) -> bool:
    matcher = node.func
    if not isinstance(matcher, ast.Attribute):
        return False
    if matcher.attr.removeprefix("not_") not in _PLAYWRIGHT_MATCHERS:
        return False
    expectation = matcher.value
    return (
        isinstance(expectation, ast.Call)
        and isinstance(expectation.func, ast.Name)
        and expectation.func.id == "expect"
        and (
            bool(expectation.args)
            or any(keyword.arg == "actual" for keyword in expectation.keywords)
        )
    )


def python_func_has_assertion(node) -> bool:
    """Check if a Python function AST node contains any assertion."""
    for child in ast.walk(node):
        if isinstance(child, ast.Assert):
            return True
        if isinstance(child, ast.Call):
            if _is_playwright_assertion_call(child):
                return True
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
