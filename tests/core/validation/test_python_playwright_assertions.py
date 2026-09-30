"""Behavioral contract for direct Python Playwright expect assertion chains."""

import pytest

from maid_runner.core._test_assertions import check_test_assertions
from maid_runner.core.result import ErrorCode


# Public matcher signatures in Playwright Python 1.58.0, used as source fixtures.
_ASSERTION_CALLS = (
    "to_be_attached()",
    "to_be_checked()",
    "to_be_disabled()",
    "to_be_editable()",
    "to_be_empty()",
    "to_be_enabled()",
    "to_be_focused()",
    "to_be_hidden()",
    "to_be_in_viewport()",
    "to_be_visible()",
    "to_contain_class('active')",
    "to_contain_text('Ready')",
    "to_have_accessible_description('Details')",
    "to_have_accessible_error_message('Required')",
    "to_have_accessible_name('Save')",
    "to_have_attribute('role', 'button')",
    "to_have_class('button')",
    "to_have_count(1)",
    "to_have_css('display', 'block')",
    "to_have_id('search')",
    "to_have_js_property('muted', False)",
    "to_have_role('dialog')",
    "to_have_text('Ready')",
    "to_have_value('query')",
    "to_have_values(['a', 'b'])",
    "to_match_aria_snapshot('- button \"Save\"')",
    "to_have_title('Search')",
    "to_have_url('https://example.test/search')",
    "to_be_ok()",
)


@pytest.mark.parametrize("assertion_call", _ASSERTION_CALLS)
@pytest.mark.parametrize("negated", [False, True])
def test_python_playwright_matcher_calls_are_recognized(assertion_call, negated):
    method = f"not_{assertion_call}" if negated else assertion_call
    source = (
        "from playwright.sync_api import expect\n"
        "def test_subject(subject):\n"
        f"    expect(subject).{method}\n"
    )

    errors = check_test_assertions(source, "tests/test_subject.py")

    assert errors == []


@pytest.mark.parametrize(
    "expression",
    [
        "await expect(subject).to_be_visible()",
        "await expect(subject).not_to_have_text('Loading')",
        "await expect(subject, 'reviewed message').to_have_count(1)",
        "await expect(actual=subject).to_have_text('Ready')",
    ],
)
def test_async_python_playwright_assertions_are_recognized(expression):
    source = (
        "from playwright.async_api import expect\n"
        "async def test_subject(subject):\n"
        f"    {expression}\n"
    )

    errors = check_test_assertions(source, "tests/test_subject.py")

    assert errors == []


@pytest.mark.parametrize(
    "expression",
    [
        "subject.to_be_visible()",
        "build(subject).to_be_visible()",
        "expect(subject)",
        "expect(subject).to_be_visible",
        "expect(subject).to_make_visible()",
        "expect(subject).click()",
        "expect().to_be_visible()",
        "expect(message='Missing actual').to_be_visible()",
        "expect(subject).negated.to_be_visible()",
        "expect(subject).not_not_to_be_visible()",
        "print('expect(subject).to_be_visible()')",
    ],
)
def test_nonasserting_python_calls_still_report_e210(expression):
    source = f"def test_subject(subject):\n    {expression}\n"

    errors = check_test_assertions(source, "tests/test_subject.py")

    assert len(errors) == 1
    assert errors[0].code == ErrorCode.MISSING_ASSERTIONS
    assert errors[0].location.file == "tests/test_subject.py"
    assert errors[0].location.line == 1


def test_python_playwright_recognition_preserves_per_test_diagnostics():
    source = (
        "from playwright.sync_api import expect\n"
        "class TestDialog:\n"
        "    def test_visible(self, page):\n"
        "        expect(page.get_by_role('dialog')).to_be_visible()\n"
        "    def test_count(self, page):\n"
        "        expect(page.get_by_role('dialog')).to_have_count(1)\n"
        "    def test_click_only(self, page):\n"
        "        page.click('button')\n"
    )

    errors = check_test_assertions(source, "tests/test_dialog.py")

    assert len(errors) == 1
    assert errors[0].code == ErrorCode.MISSING_ASSERTIONS
    assert "test_click_only" in errors[0].message
    assert errors[0].location.line == 7


@pytest.mark.parametrize(
    "body",
    [
        "assert subject is not None",
        "assert_equal(subject, 1)",
        "subject.assert_ready()",
        "with pytest.raises(ValueError):\n        subject()",
    ],
)
def test_existing_python_assertion_forms_remain_recognized(body):
    source = f"import pytest\ndef test_subject(subject):\n    {body}\n"

    errors = check_test_assertions(source, "tests/test_subject.py")

    assert errors == []
