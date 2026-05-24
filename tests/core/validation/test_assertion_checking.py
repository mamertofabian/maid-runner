"""Focused characterization tests for behavioral assertion checking."""

import ast

from maid_runner.core._test_assertions import (
    check_test_assertions,
    python_func_has_assertion,
    python_func_is_pytest_fixture,
    validate_test_assertions,
)
from maid_runner.core.result import ErrorCode


def test_check_test_assertions_warns_for_python_test_without_assertions():
    source = "def test_example():\n    value = 1 + 1\n    print(value)\n"

    errors = check_test_assertions(source, "tests/test_example.py")

    assert len(errors) == 1
    assert errors[0].code == ErrorCode.MISSING_ASSERTIONS
    assert errors[0].location.file == "tests/test_example.py"
    assert errors[0].location.line == 1
    assert "test_example" in errors[0].message


def test_check_test_assertions_allows_python_assert_statement():
    source = "def test_example():\n    assert 1 + 1 == 2\n"

    errors = check_test_assertions(source, "tests/test_example.py")

    assert errors == []


def test_check_test_assertions_allows_python_pytest_raises():
    source = (
        "import pytest\n\n"
        "def test_error():\n"
        "    with pytest.raises(ValueError):\n"
        "        raise ValueError('boom')\n"
    )

    errors = check_test_assertions(source, "tests/test_error.py")

    assert errors == []


def test_check_test_assertions_ignores_non_test_python_functions():
    source = "def helper():\n    value = 1\n"

    errors = check_test_assertions(source, "tests/test_helpers.py")

    assert errors == []


def test_check_test_assertions_reports_only_assertion_free_python_tests():
    source = (
        "def test_good():\n    assert True\n\n"
        "def test_bad():\n    value = 1\n\n"
        "def test_also_good():\n    assert 1 == 1\n"
    )

    errors = check_test_assertions(source, "tests/test_multi.py")

    assert len(errors) == 1
    assert errors[0].code == ErrorCode.MISSING_ASSERTIONS
    assert "test_bad" in errors[0].message


def test_check_test_assertions_reports_javascript_test_without_expect():
    source = "test('does something', () => {\n  const x = 1;\n  console.log(x);\n});\n"

    errors = check_test_assertions(source, "tests/example.test.js")

    assert len(errors) == 1
    assert errors[0].code == ErrorCode.MISSING_ASSERTIONS


def test_check_test_assertions_allows_javascript_expect():
    source = "test('does something', () => {\n  expect(1 + 1).toBe(2);\n});\n"

    errors = check_test_assertions(source, "tests/example.test.js")

    assert errors == []


def test_check_test_assertions_reports_typescript_it_without_expect():
    source = (
        "it('should work', () => {\n"
        "  const val = calculate();\n"
        "  console.log(val);\n"
        "});\n"
    )

    errors = check_test_assertions(source, "tests/example.test.ts")

    assert len(errors) == 1
    assert errors[0].code == ErrorCode.MISSING_ASSERTIONS


def test_check_test_assertions_ignores_non_test_files():
    source = "package main\nfunc main() {}\n"

    errors = check_test_assertions(source, "main.go")

    assert errors == []


def test_check_test_assertions_tolerates_python_syntax_errors():
    source = "def test_broken(:\n    assert True\n"

    errors = check_test_assertions(source, "tests/test_broken.py")

    assert errors == []


def test_check_test_assertions_skips_pytest_fixture():
    source = (
        "import pytest\n\n"
        "@pytest.fixture\n"
        "def test_fixture():\n"
        "    return object()\n"
    )

    errors = check_test_assertions(source, "tests/test_fixture.py")

    assert errors == []


def test_python_func_has_assertion_recognizes_pytest_raises():
    tree = ast.parse(
        "def test_raises():\n"
        "    with pytest.raises(ValueError):\n"
        "        raise ValueError('boom')\n"
    )
    function = tree.body[0]

    assert python_func_has_assertion(function) is True


def test_python_func_is_pytest_fixture_recognizes_attribute_decorator():
    tree = ast.parse(
        "import pytest\n\n"
        "@pytest.fixture\n"
        "def test_fixture():\n"
        "    return object()\n"
    )
    function = tree.body[1]

    assert python_func_is_pytest_fixture(function) is True


def test_validate_test_assertions_reports_file_read_errors(tmp_path):
    (tmp_path / "tests").mkdir()
    (tmp_path / "tests" / "test_unreadable.py").mkdir()

    errors = validate_test_assertions(tmp_path, ["tests/test_unreadable.py"])

    assert len(errors) == 1
    assert errors[0].code == ErrorCode.FILE_READ_ERROR
    assert errors[0].location.file == "tests/test_unreadable.py"
