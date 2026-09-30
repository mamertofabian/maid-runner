"""Regression contract for grammar-aware regex boundaries in E210 checks."""

import sys

import pytest

from maid_runner.core._test_assertions import check_test_assertions
from maid_runner.core.result import ErrorCode


_REGEXES = (
    r"/\{([^}]*)\}/",
    r"/[\"']/g",
    r"/import\s*(?:type\s*)?\{([^}]*)\}\s*from\s*[\"']viem(?:\/[\w-]+)?[\"']/g",
    r"/[🧪{}'\"]/u",
    r"/https?:\/\/example\.test\/[^}]+/g",
)


@pytest.mark.parametrize("extension", ["js", "jsx", "ts", "tsx"])
@pytest.mark.parametrize("regex", _REGEXES)
def test_regex_setup_does_not_hide_later_assertions(extension, regex):
    source = (
        "it('checks imports', () => {\n"
        f"  const pattern = {regex};\n"
        "  const setup = { nested: { value: 1 } };\n"
        "  expect(pattern.test('example')).toBe(false);\n"
        "});\n"
    )

    errors = check_test_assertions(source, f"tests/example.test.{extension}")

    assert errors == []


@pytest.mark.parametrize("regex", _REGEXES)
def test_regex_only_callbacks_still_report_missing_assertions(regex):
    source = f"it('missing assertion', () => {{ const pattern = {regex}; }});\n"

    errors = check_test_assertions(source, "tests/example.test.ts")

    assert len(errors) == 1
    assert errors[0].code == ErrorCode.MISSING_ASSERTIONS
    assert "missing assertion" in errors[0].message
    assert errors[0].location.line == 1


def test_regex_does_not_leak_assertions_from_a_following_callback():
    source = (
        r"it('missing', () => { const pattern = /[\"']/g; });"
        "\n"
        "it('asserted', () => { expect(1).toBe(1); });\n"
    )

    errors = check_test_assertions(source, "tests/example.test.ts")

    assert len(errors) == 1
    assert "missing" in errors[0].message
    assert errors[0].location.line == 1


def test_duplicate_labels_retain_independent_callback_diagnostics():
    source = (
        r"it('same', () => { const pattern = /\{([^}]*)\}/; expect(pattern).toBeTruthy(); });"
        "\n"
        r"it('same', () => { const pattern = /[\"']/g; });"
        "\n"
    )

    errors = check_test_assertions(source, "tests/example.test.ts")

    assert len(errors) == 1
    assert "same" in errors[0].message
    assert errors[0].location.line == 2


def test_unicode_regex_and_labels_preserve_original_diagnostic_locations():
    source = (
        "// 🧪 source prefix\n"
        r"it('α asserted', () => { const pattern = /[🧪{}'\"]/u; expect(pattern).toBeTruthy(); });"
        "\n"
        "it('β missing', () => { const value = 1; });\n"
    )

    errors = check_test_assertions(source, "tests/🧪.test.ts")

    assert len(errors) == 1
    assert "β missing" in errors[0].message
    assert errors[0].location.file == "tests/🧪.test.ts"
    assert errors[0].location.line == 3


@pytest.mark.parametrize(
    "setup",
    [
        "const ratio = 12 / 3 / 2;",
        "const ratio = 12; let result = ratio; result /= 3;",
        'const text = "braces } and / are string data";',
        '// comment with } / "\n const value = 1;',
        '/* comment with } / " */ const value = 1;',
    ],
)
def test_division_comments_and_strings_keep_existing_assertion_behavior(setup):
    source = f"it('asserted', () => {{ {setup} expect(1).toBe(1); }});\n"

    errors = check_test_assertions(source, "tests/example.test.js")

    assert errors == []


def test_core_assertion_checks_remain_available_without_optional_parser(monkeypatch):
    monkeypatch.setitem(sys.modules, "tree_sitter", None)
    monkeypatch.setitem(sys.modules, "tree_sitter_typescript", None)
    source = (
        "it('asserted', () => { expect(1).toBe(1); });\n"
        "it('missing', () => { const value = 1; });\n"
    )

    with pytest.warns(RuntimeWarning, match="legacy.*scanner"):
        errors = check_test_assertions(source, "tests/example.test.js")

    assert len(errors) == 1
    assert "missing" in errors[0].message
    assert errors[0].location.line == 2
