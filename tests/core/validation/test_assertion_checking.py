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
